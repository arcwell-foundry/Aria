"""Briefing API routes for daily morning briefings."""

import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.config import settings
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services.briefing import BriefingService
from src.services.thesys_service import get_thesys_service
from src.services.thesys_system_prompt import build_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefings", tags=["briefings"])


class BriefingContent(BaseModel):
    """Content of a daily briefing."""

    summary: str = Field(..., min_length=1, max_length=5000, description="Executive summary")
    calendar: dict[str, Any] = Field(..., description="Calendar information")
    leads: dict[str, Any] = Field(..., description="Lead status summary")
    signals: dict[str, Any] = Field(..., description="Market signals")
    tasks: dict[str, Any] = Field(..., description="Task status")
    generated_at: str = Field(
        ..., min_length=1, max_length=100, description="ISO timestamp of generation"
    )


class BriefingResponse(BaseModel):
    """Response model for a briefing."""

    id: str = Field(..., min_length=1, max_length=50, description="Briefing ID")
    user_id: str = Field(..., min_length=1, max_length=50, description="User ID")
    briefing_date: str = Field(
        ..., min_length=10, max_length=10, description="Briefing date (ISO format)"
    )
    content: BriefingContent = Field(..., description="Briefing content")


class BriefingListResponse(BaseModel):
    """Response model for listing briefings."""

    id: str
    briefing_date: str
    content: dict[str, Any]


class GenerateBriefingRequest(BaseModel):
    """Request body for generating a briefing."""

    briefing_date: str | None = Field(None, description="ISO date string (e.g., 2026-02-01)")


def _sse_event(data: dict[str, Any] | str) -> str:
    """Format a server-sent event line."""
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


async def _generate_briefing_narrative(
    content: dict[str, Any],
    user_id: str,
) -> str:
    """Transform structured briefing data into a Claude narrative for C1 rendering.

    Takes the briefing content dict and produces a structured text narrative
    that C1 can visualize as an interactive dashboard.
    """
    # Determine time-appropriate greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Check if user has any data at all
    calendar = content.get("calendar", {})
    leads = content.get("leads", {})
    signals = content.get("signals", {})
    tasks = content.get("tasks", {})
    email_data = content.get("email_summary", {})
    causal_actions = content.get("causal_actions", [])
    intelligence_insights = content.get("intelligence_insights", [])

    meeting_count = calendar.get("meeting_count", 0)
    hot_leads = leads.get("hot_leads", [])
    attention_leads = leads.get("needs_attention", [])
    company_news = signals.get("company_news", [])
    market_trends = signals.get("market_trends", [])
    competitive_intel = signals.get("competitive_intel", [])
    overdue_tasks = tasks.get("overdue", [])
    due_today_tasks = tasks.get("due_today", [])
    emails_needing_attention = email_data.get("needs_attention", [])
    total_emails = email_data.get("total_received", 0)
    drafts_waiting = email_data.get("drafts_waiting", 0)

    total_activity = (
        meeting_count
        + len(hot_leads)
        + len(attention_leads)
        + len(company_news)
        + len(market_trends)
        + len(competitive_intel)
        + len(overdue_tasks)
        + len(due_today_tasks)
        + total_emails
    )

    if total_activity == 0:
        # New user with no data — return simple welcome
        return (
            f"{greeting}. Your intelligence feeds are still initializing. "
            "Connect your calendar, email, and CRM so I can start building "
            "your daily intelligence briefing."
        )

    # Build structured sections for the LLM
    sections: list[str] = []

    # Calendar section
    if meeting_count > 0:
        meetings_text = f"## Calendar\n{meeting_count} meetings today.\n"
        for m in calendar.get("key_meetings", [])[:8]:
            raw_att = m.get("attendees", [])[:3]
            attendees = ", ".join(
                a.get("name") or a.get("email", "") if isinstance(a, dict) else str(a)
                for a in raw_att
            )
            meetings_text += f"- {m.get('time', '')} — {m.get('title', 'Meeting')}"
            if attendees:
                meetings_text += f" (with {attendees})"
            meetings_text += "\n"
        sections.append(meetings_text)

    # Email section
    if total_emails > 0 or drafts_waiting > 0:
        email_text = f"## Emails\n{total_emails} received"
        if drafts_waiting > 0:
            email_text += f", {drafts_waiting} drafts waiting for your review"
        email_text += ".\n"
        for e in emails_needing_attention[:5]:
            draft_id_str = f" [draft_id:{e.get('draft_id', '')}]" if e.get("draft_id") else ""
            email_text += (
                f"- From {e.get('sender', 'Unknown')} ({e.get('company', '')}) — "
                f"\"{e.get('subject', '')}\" — urgency: {e.get('urgency', 'normal')}"
                f"{draft_id_str}\n"
            )
            if e.get("aria_notes"):
                email_text += f"  ARIA note: {e['aria_notes']}\n"
        sections.append(email_text)

    # Leads section
    if hot_leads or attention_leads:
        leads_text = "## Pipeline & Leads\n"
        if hot_leads:
            leads_text += f"{len(hot_leads)} hot leads:\n"
            for ld in hot_leads[:5]:
                health = f" (health: {ld.get('health_score', '—')})" if ld.get("health_score") else ""
                leads_text += (
                    f"- {ld.get('name', 'Unknown')} at {ld.get('company', '')} "
                    f"[lead_id:{ld.get('id', '')}]{health}\n"
                )
        if attention_leads:
            leads_text += f"{len(attention_leads)} need attention:\n"
            for ld in attention_leads[:5]:
                health = f" (health: {ld.get('health_score', '—')})" if ld.get("health_score") else ""
                leads_text += (
                    f"- {ld.get('name', 'Unknown')} at {ld.get('company', '')} "
                    f"[lead_id:{ld.get('id', '')}]{health}\n"
                )
        sections.append(leads_text)

    # Signals section
    all_signals = company_news + market_trends + competitive_intel
    if all_signals:
        signals_text = f"## Market Signals\n{len(all_signals)} signals detected.\n"
        for sig in all_signals[:6]:
            severity = sig.get("relevance", 0)
            severity_label = "High" if severity >= 80 else "Medium" if severity >= 50 else "Low"
            signals_text += (
                f"- [{severity_label}] {sig.get('title', 'Signal')} "
                f"[signal_id:{sig.get('id', '')}] — {sig.get('summary', '')}\n"
            )
        sections.append(signals_text)

    # Tasks section
    if overdue_tasks or due_today_tasks:
        tasks_text = "## Tasks\n"
        if overdue_tasks:
            tasks_text += f"{len(overdue_tasks)} overdue:\n"
            for t in overdue_tasks[:5]:
                priority = f" (priority: {t.get('priority', 'normal')})" if t.get("priority") else ""
                tasks_text += f"- {t.get('title', 'Task')} [task_id:{t.get('id', '')}]{priority}\n"
        if due_today_tasks:
            tasks_text += f"{len(due_today_tasks)} due today:\n"
            for t in due_today_tasks[:5]:
                priority = f" (priority: {t.get('priority', 'normal')})" if t.get("priority") else ""
                tasks_text += f"- {t.get('title', 'Task')} [task_id:{t.get('id', '')}]{priority}\n"
        sections.append(tasks_text)

    # Causal actions section
    if causal_actions:
        causal_text = "## Recommended Actions\n"
        for action in causal_actions[:3]:
            causal_text += (
                f"- {action.get('recommended_action', '')} "
                f"(urgency: {action.get('urgency', 'normal')}, "
                f"timing: {action.get('timing', 'flexible')})\n"
            )
        sections.append(causal_text)

    # Intelligence insights section
    if intelligence_insights:
        insights_text = "## Intelligence Insights\n"
        for insight in intelligence_insights[:3]:
            insights_text += f"- {insight.get('title', insight.get('message', ''))}\n"
        sections.append(insights_text)

    structured_data = "\n".join(sections)

    # Get personality calibration for tone
    tone_guidance = ""
    try:
        calibrator = PersonalityCalibrator()
        calibration = await calibrator.get_calibration(user_id)
        if calibration:
            tone_guidance = calibration.tone_guidance
    except Exception:
        logger.debug("Personality calibration unavailable for briefing narrative", extra={"user_id": user_id})

    prompt = f"""Write a structured morning briefing narrative based on this data. The narrative will be rendered as an interactive dashboard by a UI component, so:

1. Use markdown headers (##) to separate sections — the UI will create distinct card groups for each section.
2. Keep IDs in brackets (e.g. [draft_id:xxx], [lead_id:xxx], [signal_id:xxx], [task_id:xxx]) — the UI uses these to wire action buttons.
3. For emails with drafts, clearly indicate which ones have drafts ready for approval.
4. For signals, include the severity level so the UI can render appropriate badges.
5. For leads, include health scores so the UI can show status indicators.
6. Skip any section that has no data — do not mention empty sections.
7. Be concise and professional. Do not use emojis.
8. Start with "{greeting}." and a brief 1-sentence executive summary before the sections.

Data:
{structured_data}"""

    if tone_guidance:
        prompt = f"TONE: {tone_guidance}\n\n{prompt}"

    llm = LLMClient()
    try:
        narrative = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            task=TaskType.ANALYST_SUMMARIZE,
            agent_id="briefing",
            user_id=user_id,
        )
        return narrative
    except Exception:
        logger.warning(
            "LLM narrative generation failed, using existing summary",
            extra={"user_id": user_id},
            exc_info=True,
        )
        return content.get("summary", f"{greeting}. Your briefing is ready.")


@router.post("/stream")
async def stream_briefing(
    current_user: CurrentUser,
) -> StreamingResponse:
    """Stream today's briefing as a C1-rendered interactive dashboard.

    Generates or retrieves the cached briefing, transforms it into a
    Claude narrative, and streams it through C1 for interactive rendering.
    Falls back to markdown if C1 is unavailable.
    """

    async def event_stream():  # noqa: C901
        message_id = str(uuid.uuid4())

        # Emit metadata event
        yield _sse_event({
            "type": "metadata",
            "message_id": message_id,
            "conversation_id": "briefing",
        })

        try:
            # Get briefing data (cached, 1hr TTL)
            service = BriefingService()
            content = await service.get_or_generate_briefing(current_user.id)
        except Exception:
            logger.exception(
                "BriefingService failed during streaming",
                extra={"user_id": current_user.id},
            )
            # Minimal greeting on total failure
            hour = datetime.now().hour
            greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
            fallback = f"{greeting}. I'm having trouble loading your briefing right now. Please try refreshing."
            yield _sse_event({"type": "token", "content": fallback})
            yield _sse_event({
                "type": "complete",
                "render_mode": "markdown",
                "suggestions": ["Refresh briefing", "Show me today's meetings"],
            })
            yield _sse_event("[DONE]")
            return

        # Generate narrative from structured data
        narrative = await _generate_briefing_narrative(content, current_user.id)

        # Try C1 streaming
        thesys = get_thesys_service()
        c1_system_prompt = build_system_prompt("briefing")

        try:
            # Send readable narrative as token while C1 renders server-side
            yield _sse_event({"type": "token", "content": narrative})

            # Buffer C1 chunks internally — do NOT stream as tokens
            c1_chunks: list[str] = []
            async for chunk in thesys.visualize_stream(narrative, c1_system_prompt):
                c1_chunks.append(chunk)

            c1_response = "".join(c1_chunks)

            # Build suggestions from briefing content
            suggestions = content.get("suggestions", [
                "Show me today's meetings",
                "Any urgent signals?",
                "Check pipeline health",
            ])

            yield _sse_event({
                "type": "complete",
                "render_mode": "c1",
                "c1_response": c1_response,
                "suggestions": suggestions[:4],
            })
        except Exception:
            logger.warning(
                "C1 streaming failed, falling back to markdown",
                extra={"user_id": current_user.id},
                exc_info=True,
            )
            # Markdown fallback — emit narrative as single token
            yield _sse_event({"type": "token", "content": narrative})

            suggestions = content.get("suggestions", [
                "Show me today's meetings",
                "Any urgent signals?",
                "Check pipeline health",
            ])

            yield _sse_event({
                "type": "complete",
                "render_mode": "markdown",
                "rich_content": [{"type": "briefing", "data": content}],
                "suggestions": suggestions[:4],
            })

        yield _sse_event("[DONE]")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/today")
async def get_today_briefing(
    current_user: CurrentUser,
    regenerate: bool = Query(False, description="Force regenerate briefing"),
) -> dict[str, Any]:
    """Get today's briefing, generating if needed.

    Returns the daily briefing content for the current user.
    If no briefing exists yet and regenerate is not requested,
    returns a not_generated status so the dashboard can show
    an empty state.
    """
    service = BriefingService()

    if regenerate:
        content = await service.generate_briefing(current_user.id)
        return {"briefing": content, "status": "ready"}

    existing = await service.get_briefing(current_user.id)
    if existing:
        content = existing.get("content")
        if isinstance(content, dict):
            return {"briefing": content, "status": "ready"}

    # No briefing yet — return empty default instead of generating
    logger.info(
        "No briefing available for user",
        extra={"user_id": current_user.id},
    )
    return {"briefing": None, "status": "not_generated"}


def _is_buffer_event(title: str | None) -> bool:
    """Check if an event is a buffer event (should not count as real meeting)."""
    if not title:
        return False
    title_lower = title.lower()
    return "[buffer" in title_lower or "buffer]" in title_lower


def _format_time_12hr(time_str: str | None) -> str | None:
    """Format time string to 12-hour format like '11:00 AM'.

    Args:
        time_str: Time string in format like '11:00' or '14:30'

    Returns:
        Formatted time like '11:00 AM' or '2:30 PM', or None if invalid
    """
    if not time_str:
        return None
    try:
        # Handle various time formats
        if ':' in time_str:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            return time_str

        # Convert to 12-hour format
        period = 'AM' if hour < 12 else 'PM'
        hour_12 = hour if hour <= 12 else hour - 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{minute:02d} {period}"
    except (ValueError, IndexError):
        return time_str


@router.get("/status")
async def get_briefing_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get the current briefing status for the user.

    Returns whether a briefing is ready, whether it has been viewed,
    and metadata about the briefing. Used by the dashboard on page load.
    """
    try:
        service = BriefingService()
        existing = await service.get_briefing(current_user.id)

        if existing and isinstance(existing.get("content"), dict):
            briefing_content = existing["content"]
            topics: list[str] = []

            # Get user's timezone for accurate meeting filtering
            user_tz_str = await service._get_user_timezone(current_user.id)
            user_tz = ZoneInfo(user_tz_str)
            now_local = datetime.now(user_tz)
            now_utc = now_local.astimezone(UTC)

            # Calculate today's and tomorrow's date ranges in user's timezone
            today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end_local = today_start_local + timedelta(days=1)
            tomorrow_end_local = today_start_local + timedelta(days=2)

            # Convert to UTC for database queries
            today_start_utc = today_start_local.astimezone(UTC)
            today_end_utc = today_end_local.astimezone(UTC)
            tomorrow_end_utc = tomorrow_end_local.astimezone(UTC)

            # Query calendar_events table for fresh, accurate meeting counts
            from src.db.supabase import SupabaseClient
            db = SupabaseClient.get_client()

            # Get today's FUTURE meetings (excluding buffers)
            today_result = (
                db.table("calendar_events")
                .select("id, title, start_time")
                .eq("user_id", current_user.id)
                .gte("start_time", now_utc.isoformat())  # Only future meetings
                .lt("start_time", today_end_utc.isoformat())  # Still today
                .order("start_time", desc=False)
                .limit(20)
                .execute()
            )

            # Filter out buffer events
            today_meetings = [
                m for m in (today_result.data or [])
                if not _is_buffer_event(m.get("title") if isinstance(m, dict) else None)
            ]

            # Get tomorrow's meetings (excluding buffers)
            tomorrow_result = (
                db.table("calendar_events")
                .select("id, title, start_time")
                .eq("user_id", current_user.id)
                .gte("start_time", today_end_utc.isoformat())
                .lt("start_time", tomorrow_end_utc.isoformat())
                .order("start_time", desc=False)
                .limit(10)
                .execute()
            )

            tomorrow_meetings = [
                m for m in (tomorrow_result.data or [])
                if not _is_buffer_event(m.get("title") if isinstance(m, dict) else None)
            ]

            # Build calendar preview text
            if today_meetings:
                # Show today's future meetings with first meeting preview
                first_meeting = today_meetings[0] if isinstance(today_meetings[0], dict) else {}
                first_title = first_meeting.get("title", "Meeting")
                truncated_title = first_title[:30] + "..." if len(first_title) > 30 else first_title

                # Format the first meeting time in user's timezone
                first_time_formatted = await service._format_time_in_user_timezone(
                    first_meeting.get("start_time", ""), current_user.id
                )
                first_time_12hr = _format_time_12hr(first_time_formatted)

                meeting_count = len(today_meetings)
                if first_time_12hr:
                    topics.append(f"Today: {meeting_count} meeting{'s' if meeting_count != 1 else ''} · First at {first_time_12hr} — {truncated_title}")
                else:
                    topics.append(f"Today: {meeting_count} meeting{'s' if meeting_count != 1 else ''}")
            elif tomorrow_meetings:
                # Show tomorrow's meetings with first meeting preview
                first_meeting = tomorrow_meetings[0] if isinstance(tomorrow_meetings[0], dict) else {}
                first_title = first_meeting.get("title", "Meeting")
                truncated_title = first_title[:30] + "..." if len(first_title) > 30 else first_title

                # Format the first meeting time in user's timezone
                first_time_formatted = await service._format_time_in_user_timezone(
                    first_meeting.get("start_time", ""), current_user.id
                )
                first_time_12hr = _format_time_12hr(first_time_formatted)

                meeting_count = len(tomorrow_meetings)
                if first_time_12hr:
                    topics.append(f"Tomorrow: {meeting_count} meeting{'s' if meeting_count != 1 else ''} · First at {first_time_12hr} — {truncated_title}")
                else:
                    topics.append(f"Tomorrow: {meeting_count} meeting{'s' if meeting_count != 1 else ''}")
            # If no meetings today or tomorrow, don't add calendar topic

            # Query goals table for accurate open tasks count
            goals_result = (
                db.table("goals")
                .select("id, status")
                .eq("user_id", current_user.id)
                .not_.in_("status", ["complete", "failed", "cancelled"])
                .execute()
            )
            open_tasks_count = len(goals_result.data or [])
            if open_tasks_count > 0:
                topics.append(f"{open_tasks_count} open task{'s' if open_tasks_count != 1 else ''}")

            # Leads (from cached briefing content - this is less time-sensitive)
            leads_data = briefing_content.get("leads", {})
            if isinstance(leads_data, dict):
                hot_count = len(leads_data.get("hot_leads", []))
                attention_count = len(leads_data.get("needs_attention", []))
                if hot_count > 0:
                    topics.append(f"{hot_count} hot lead{'s' if hot_count != 1 else ''}")
                if attention_count > 0:
                    topics.append(f"{attention_count} need{'s' if attention_count == 1 else ''} attention")

            # Signals (from cached briefing content - this is less time-sensitive)
            signals_data = briefing_content.get("signals", {})
            if isinstance(signals_data, dict):
                signal_total = sum(
                    len(signals_data.get(k, []))
                    for k in ("company_news", "market_trends", "competitive_intel")
                )
                if signal_total > 0:
                    topics.append(f"{signal_total} market signal{'s' if signal_total != 1 else ''}")

            if not topics:
                topics.append("Your daily briefing")

            return {
                "ready": True,
                "viewed": existing.get("viewed", False),
                "briefing_id": existing.get("id"),
                "duration": 0,
                "topics": topics[:5],
            }
    except Exception:
        logger.warning(
            "Failed to fetch briefing status",
            extra={"user_id": current_user.id},
            exc_info=True,
        )

    return {
        "ready": False,
        "viewed": False,
        "briefing_id": None,
        "duration": 0,
        "topics": [],
    }


@router.get("", response_model=list[BriefingListResponse])
async def list_briefings(
    current_user: CurrentUser,
    limit: int = Query(7, ge=1, le=30, description="Maximum number of briefings"),
) -> list[BriefingListResponse]:
    """List recent briefings.

    Returns a list of recent briefings for the current user.
    """
    service = BriefingService()
    briefings = await service.list_briefings(current_user.id, limit)

    logger.info(
        "Briefings listed",
        extra={"user_id": current_user.id, "count": len(briefings)},
    )

    return [BriefingListResponse(**b) for b in briefings]


@router.post("/{briefing_id}/view")
async def mark_briefing_viewed(
    current_user: CurrentUser,
    briefing_id: str,
) -> dict[str, Any]:
    """Mark a briefing as viewed and return summary data.

    Updates the viewed flag on the briefing and returns key points
    and action items for the post-briefing summary card.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        # Update viewed flag
        db.table("daily_briefings").update(
            {"viewed": True}
        ).eq("id", briefing_id).eq("user_id", current_user.id).execute()

        # Fetch the briefing content for summary
        result = (
            db.table("daily_briefings")
            .select("content")
            .eq("id", briefing_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
        record = result.data[0] if result and result.data else None
        content = record.get("content", {}) if record and result.data else None
        summary = content.get("summary", "") if isinstance(content, dict) else ""

        return {
            "key_points": [summary] if summary else ["Briefing reviewed"],
            "action_items": [],
            "completed_at": datetime.now(UTC).isoformat(),
        }

    except Exception:
        logger.warning(
            "Failed to mark briefing viewed",
            extra={"user_id": current_user.id, "briefing_id": briefing_id},
            exc_info=True,
        )
        return {
            "key_points": [],
            "action_items": [],
            "completed_at": datetime.now(UTC).isoformat(),
        }


@router.get("/{briefing_id}/text")
async def get_briefing_text(
    current_user: CurrentUser,
    briefing_id: str,
) -> dict[str, Any]:
    """Get the text version of a specific briefing.

    Returns the summary text content of a briefing by its ID.
    Used by the 'Read instead' option on the video briefing card.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("daily_briefings")
            .select("content")
            .eq("id", briefing_id)
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
        record = result.data[0] if result and result.data else None
        if not record:
            raise HTTPException(status_code=404, detail="Briefing not found")

        content = record.get("content", {})
        summary = content.get("summary", "") if isinstance(content, dict) else ""

        if not summary:
            # Generate a text version from the briefing data
            summary = "Your daily briefing is available. Check the dashboard for details."

        return {"text": summary, "briefing_id": briefing_id}

    except HTTPException:
        raise
    except Exception:
        logger.warning(
            "Failed to get briefing text",
            extra={"user_id": current_user.id, "briefing_id": briefing_id},
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail="Briefing not found")


@router.get("/{briefing_date}", response_model=BriefingResponse)
async def get_briefing_by_date(
    current_user: CurrentUser,
    briefing_date: date,
) -> BriefingResponse:
    """Get briefing for specific date.

    Returns the briefing for the specified date.
    Raises 404 if not found.
    """
    service = BriefingService()
    briefing = await service.get_briefing(current_user.id, briefing_date)

    if not briefing:
        raise HTTPException(status_code=404, detail=f"Briefing for {briefing_date} not found")

    logger.info(
        "Briefing retrieved by date",
        extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
    )

    return BriefingResponse(**briefing)


@router.post("/generate", response_model=BriefingContent)
async def generate_briefing(
    current_user: CurrentUser,
    request: GenerateBriefingRequest | None = None,
) -> BriefingContent:
    """Force generate a new briefing.

    Generates a new briefing for today or the specified date.
    """
    briefing_date = None
    if request and request.briefing_date:
        briefing_date = date.fromisoformat(request.briefing_date)

    try:
        service = BriefingService()
        content = await service.generate_briefing(current_user.id, briefing_date)

        logger.info(
            "Briefing generated",
            extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
        )

        return BriefingContent(**content)
    except Exception:
        logger.exception(
            "Briefing generation failed, returning minimal briefing",
            extra={"user_id": current_user.id, "briefing_date": str(briefing_date)},
        )
        # Return a minimal but valid briefing so the frontend doesn't crash
        from datetime import UTC
        from datetime import datetime as dt

        return BriefingContent(
            summary="Your briefing is being prepared. Please try refreshing in a moment.",
            calendar={"meeting_count": 0, "key_meetings": []},
            leads={"hot_leads": [], "needs_attention": [], "recently_active": []},
            signals={"company_news": [], "market_trends": [], "competitive_intel": []},
            tasks={"overdue": [], "due_today": []},
            generated_at=dt.now(UTC).isoformat(),
        )


@router.post("/regenerate", response_model=BriefingContent)
async def regenerate_briefing(
    current_user: CurrentUser,
) -> BriefingContent:
    """Regenerate today's briefing with fresh data.

    Forces regeneration of today's briefing, useful when
    underlying data has changed (new leads, signals, etc.).
    """
    try:
        service = BriefingService()
        content = await service.generate_briefing(current_user.id)

        logger.info(
            "Briefing regenerated",
            extra={"user_id": current_user.id},
        )

        return BriefingContent(**content)
    except Exception:
        logger.exception(
            "Briefing regeneration failed, returning minimal briefing",
            extra={"user_id": current_user.id},
        )
        # Return a minimal but valid briefing so the frontend doesn't crash
        from datetime import UTC
        from datetime import datetime as dt

        return BriefingContent(
            summary="Your briefing is being prepared. Please try refreshing in a moment.",
            calendar={"meeting_count": 0, "key_meetings": []},
            leads={"hot_leads": [], "needs_attention": [], "recently_active": []},
            signals={"company_news": [], "market_trends": [], "competitive_intel": []},
            tasks={"overdue": [], "due_today": []},
            generated_at=dt.now(UTC).isoformat(),
        )


@router.post("/deliver")
async def deliver_briefing(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate today's briefing and deliver via WebSocket or text-only mode.

    Generates a fresh briefing and pushes it to the user's active
    WebSocket connection as an AriaMessageEvent with rich content
    cards, UI commands, and suggestions.

    Falls back to text-only mode when Tavus video avatar is not configured.
    In text-only mode, returns the briefing content directly for frontend rendering.

    NEVER returns a non-200 status code - always returns valid JSON with text_only mode
    as a guaranteed fallback.
    """
    content: dict[str, Any] | None = None

    # GUARANTEED FALLBACK PATTERN: Try video/Tavus path, but always return text_only on any failure
    try:
        # Check if Tavus video service is configured
        tavus_configured = bool(settings.TAVUS_API_KEY)

        service = BriefingService()
        content = await service.generate_briefing(current_user.id)

        # If Tavus not configured, return text-only mode immediately
        if not tavus_configured:
            logger.info(
                "Briefing delivered in text-only mode (Tavus not configured)",
                extra={"user_id": current_user.id},
            )
            return {
                "mode": "text_only",
                "content": content,
                "message": "Video avatar not configured. Text briefing available.",
                "status": "delivered",
            }

        # Tavus configured - try WebSocket delivery
        try:
            from src.core.ws import ws_manager
            from src.models.ws_events import AriaMessageEvent

            event = AriaMessageEvent(
                message=content.get("summary", ""),
                rich_content=content.get("rich_content", []),
                ui_commands=content.get("ui_commands", []),
                suggestions=content.get("suggestions", []),
            )
            await ws_manager.send_to_user(current_user.id, event)
            logger.info("Briefing delivered via WebSocket", extra={"user_id": current_user.id})
            return {"mode": "video", "briefing": content, "status": "delivered"}
        except Exception as ws_error:
            logger.warning(
                f"WebSocket briefing delivery failed, falling back to text-only: {ws_error}",
                extra={"user_id": current_user.id},
            )
            # Fall back to text-only if WebSocket fails
            if content:
                return {
                    "mode": "text_only",
                    "content": content,
                    "message": "Video delivery unavailable. Text briefing available.",
                    "status": "delivered",
                }
    except Exception as e:
        logger.error(
            f"Briefing delivery failed, falling back to text query: {e}",
            extra={"user_id": current_user.id},
            exc_info=True,
        )

    # GUARANTEED FALLBACK - Try to get existing briefing from database
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        today_str = date.today().isoformat()

        result = (
            db.table("daily_briefings")
            .select("id, content, briefing_date")
            .eq("user_id", current_user.id)
            .eq("briefing_date", today_str)
            .order("briefing_date", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            briefing = result.data[0]
            raw_content = briefing.get("content")
            fallback_content = (
                json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            )
            logger.info(
                "Briefing delivered from database fallback",
                extra={"user_id": current_user.id},
            )
            return {
                "mode": "text_only",
                "briefing_id": briefing.get("id"),
                "content": fallback_content,
                "briefing_date": briefing.get("briefing_date"),
                "message": "Text briefing mode",
                "status": "delivered",
            }
    except Exception as db_error:
        logger.error(
            f"Even database fallback failed: {db_error}",
            extra={"user_id": current_user.id},
            exc_info=True,
        )

    # ABSOLUTE LAST RESORT - return empty but valid 200
    return {
        "mode": "text_only",
        "content": {
            "summary": "Briefing unavailable. Please try again later.",
            "calendar": {"meeting_count": 0, "key_meetings": []},
            "leads": {"hot_leads": [], "needs_attention": []},
            "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
            "tasks": {"overdue": [], "due_today": []},
        },
        "message": "Briefing generation failed. Please try refreshing.",
        "status": "delivered",
    }


@router.post("/replay")
async def replay_briefing(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Replay today's briefing without regenerating.

    Fetches the existing daily briefing for today and returns it
    in text-only mode. Used when navigating to /briefing?replay=true.

    Returns the briefing content directly for frontend rendering.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        today_str = date.today().isoformat()

        # Fetch today's existing briefing
        result = (
            db.table("daily_briefings")
            .select("id, content")
            .eq("user_id", current_user.id)
            .eq("briefing_date", today_str)
            .limit(1)
            .execute()
        )

        if not result.data:
            # No briefing exists - generate one
            service = BriefingService()
            content = await service.generate_briefing(current_user.id)
            logger.info(
                "Briefing generated for replay (none existed)",
                extra={"user_id": current_user.id},
            )
        else:
            # Use existing briefing
            raw_content = result.data[0].get("content")
            content = (
                json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            )
            logger.info(
                "Briefing replayed from cache",
                extra={"user_id": current_user.id},
            )

        return {
            "mode": "text_only",
            "content": content,
            "message": "Briefing ready for replay.",
            "status": "delivered",
        }
    except Exception:
        logger.exception(
            "Briefing replay failed",
            extra={"user_id": current_user.id},
        )
        return {
            "mode": "text_only",
            "content": None,
            "status": "failed",
            "error": "Could not load briefing. Please try refreshing.",
        }
