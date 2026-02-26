"""Briefing API routes for daily morning briefings."""

import logging
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.briefing import BriefingService

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
            # Extract meaningful topic names from briefing sections
            leads_data = briefing_content.get("leads", {})
            if isinstance(leads_data, dict):
                hot_count = len(leads_data.get("hot_leads", []))
                attention_count = len(leads_data.get("needs_attention", []))
                if hot_count > 0:
                    topics.append(f"{hot_count} hot lead{'s' if hot_count != 1 else ''}")
                if attention_count > 0:
                    topics.append(f"{attention_count} need{'s' if attention_count == 1 else ''} attention")

            signals_data = briefing_content.get("signals", {})
            if isinstance(signals_data, dict):
                signal_total = sum(
                    len(signals_data.get(k, []))
                    for k in ("company_news", "market_trends", "competitive_intel")
                )
                if signal_total > 0:
                    topics.append(f"{signal_total} market signal{'s' if signal_total != 1 else ''}")

            tasks_data = briefing_content.get("tasks", {})
            if isinstance(tasks_data, dict):
                overdue_count = len(tasks_data.get("overdue", []))
                if overdue_count > 0:
                    topics.append(f"{overdue_count} overdue task{'s' if overdue_count != 1 else ''}")

            calendar_data = briefing_content.get("calendar", {})
            if isinstance(calendar_data, dict):
                meeting_count = calendar_data.get("meeting_count", 0)
                if meeting_count > 0:
                    topics.append(f"{meeting_count} meeting{'s' if meeting_count != 1 else ''}")

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
            .maybe_single()
            .execute()
        )

        content = result.data.get("content", {}) if result and result.data else {}
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
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            raise HTTPException(status_code=404, detail="Briefing not found")

        content = result.data.get("content", {})
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
    """Generate today's briefing and deliver via WebSocket.

    Generates a fresh briefing and pushes it to the user's active
    WebSocket connection as an AriaMessageEvent with rich content
    cards, UI commands, and suggestions.
    """
    try:
        service = BriefingService()
        content = await service.generate_briefing(current_user.id)

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
            return {"briefing": content, "status": "delivered"}
        except Exception as e:
            logger.warning(f"WebSocket briefing delivery failed: {e}")
            return {"briefing": content, "status": "generated_not_delivered"}
    except Exception:
        logger.exception(
            "Briefing delivery failed",
            extra={"user_id": current_user.id},
        )
        return {
            "briefing": None,
            "status": "failed",
            "error": "Briefing generation failed. Please try again.",
        }
