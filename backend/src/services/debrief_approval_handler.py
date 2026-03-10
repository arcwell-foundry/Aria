"""Debrief approval handler — Stream C1.

When a user approves a debrief_review action in the Action Queue,
this handler:
1. Generates follow-up email drafts for external attendees
2. Writes semantic memory facts for each attendee interaction
3. Marks the action as completed
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


async def handle_debrief_approval(
    action_item: dict[str, Any],
    user_id: str,
    db: Any,
) -> dict[str, Any]:
    """Process an approved debrief_review action.

    Generates follow-up emails for external meeting attendees and
    writes semantic memory facts about the meeting interaction.

    Args:
        action_item: The aria_action_queue row dict.
        user_id: The approving user's ID.
        db: Supabase client instance.

    Returns:
        Result dict with status, email_drafts_created, memory_facts_written.
    """
    payload = action_item.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)

    debrief_id = payload.get("reference_id") or payload.get("debrief_id")
    if not debrief_id:
        logger.warning("[DebriefApproval] No debrief_id in payload")
        return {"status": "error", "message": "No debrief_id in payload"}

    # ------------------------------------------------------------------
    # 1. Load debrief + related records
    # ------------------------------------------------------------------
    debrief_result = (
        db.table("meeting_debriefs")
        .select("*")
        .eq("id", debrief_id)
        .limit(1)
        .execute()
    )
    if not debrief_result.data:
        logger.warning("[DebriefApproval] Debrief not found: %s", debrief_id)
        return {"status": "error", "message": "Debrief not found"}

    debrief = debrief_result.data[0]
    meeting_title = debrief.get("meeting_title") or "Meeting"
    summary = debrief.get("summary") or ""
    action_items = debrief.get("action_items") or []
    next_steps = debrief.get("next_steps") or []
    stakeholder_signals = debrief.get("stakeholder_signals") or []
    meeting_time = debrief.get("meeting_time") or debrief.get("created_at", "")

    # Fetch calendar event (for attendees)
    calendar_event_id = debrief.get("calendar_event_id")
    calendar_event = None
    if calendar_event_id:
        ce_result = (
            db.table("calendar_events")
            .select("*")
            .eq("id", calendar_event_id)
            .limit(1)
            .execute()
        )
        if ce_result.data:
            calendar_event = ce_result.data[0]

    # Fetch meeting session
    meeting_session_id = (
        debrief.get("meeting_session_id") or payload.get("meeting_session_id")
    )
    session = None
    if meeting_session_id:
        sess_result = (
            db.table("meeting_sessions")
            .select("*")
            .eq("id", meeting_session_id)
            .limit(1)
            .execute()
        )
        if sess_result.data:
            session = sess_result.data[0]

    # Fill in title/time from related records if debrief lacks them
    if meeting_title == "Meeting":
        if calendar_event:
            meeting_title = calendar_event.get("title") or meeting_title
        elif session:
            meeting_title = session.get("meeting_title") or meeting_title

    if not meeting_time and calendar_event:
        meeting_time = calendar_event.get("start_time") or ""

    # ------------------------------------------------------------------
    # 2. Extract attendees
    # ------------------------------------------------------------------
    attendees = _extract_attendees(calendar_event)

    # ------------------------------------------------------------------
    # 3. Draft follow-up emails
    # ------------------------------------------------------------------
    email_drafts_created = 0
    try:
        email_drafts_created = await _create_followup_drafts(
            db=db,
            user_id=user_id,
            debrief_id=debrief_id,
            meeting_session_id=str(meeting_session_id) if meeting_session_id else "",
            meeting_title=meeting_title,
            summary=summary,
            action_items=action_items,
            next_steps=next_steps,
            attendees=attendees,
        )
    except Exception:
        logger.exception("[DebriefApproval] Failed to create email drafts")

    # ------------------------------------------------------------------
    # 4. Memory update (legacy + universal router)
    # ------------------------------------------------------------------
    memory_facts_written = 0
    try:
        memory_facts_written = _write_memory_facts(
            db=db,
            user_id=user_id,
            debrief_id=debrief_id,
            meeting_title=meeting_title,
            meeting_time=meeting_time,
            summary=summary,
            stakeholder_signals=stakeholder_signals,
            action_items=action_items,
            attendees=attendees,
        )
    except Exception:
        logger.exception("[DebriefApproval] Failed to write memory facts")

    # Universal memory router for comprehensive lead memory updates
    try:
        from src.services.memory_writer import write_memory

        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        await write_memory(db, user_id, "meeting_debrief_approved", {
            "debrief_id": str(debrief_id),
            "meeting_title": meeting_title,
            "summary": summary,
            "action_items": action_items,
            "next_steps": next_steps,
            "stakeholder_signals": stakeholder_signals,
            "attendee_emails": attendee_emails,
            "meeting_time": meeting_time,
        })
    except Exception:
        logger.exception("[DebriefApproval] Failed to route via memory_writer")

    # ------------------------------------------------------------------
    # 5. Update action queue
    # ------------------------------------------------------------------
    try:
        db.table("aria_action_queue").update({
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", action_item["id"]).execute()
    except Exception:
        logger.exception("[DebriefApproval] Failed to mark action completed")

    result = {
        "status": "completed",
        "email_drafts_created": email_drafts_created,
        "memory_facts_written": memory_facts_written,
    }

    logger.info(
        "[DebriefApproval] Completed",
        extra={
            "debrief_id": debrief_id,
            "email_drafts_created": email_drafts_created,
            "memory_facts_written": memory_facts_written,
        },
    )

    return result


# ======================================================================
# Helpers
# ======================================================================


def _extract_attendees(
    calendar_event: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Extract attendee list from calendar event.

    Handles two formats in calendar_events.attendees:
    - Array of email strings: ["email@example.com"]
    - Array of objects: [{"email": "email@example.com", "name": "John"}]

    Falls back to calendar_events.metadata.attendees.
    Filters out hello@luminone.com.
    """
    raw_attendees: list[Any] = []

    if calendar_event:
        raw_attendees = calendar_event.get("attendees") or []
        if not raw_attendees:
            metadata = calendar_event.get("metadata") or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            raw_attendees = metadata.get("attendees", [])

    attendees: list[dict[str, str]] = []
    for att in raw_attendees:
        if isinstance(att, str):
            email = att.strip().lower()
            if email and email != "hello@luminone.com":
                attendees.append({"email": email, "name": ""})
        elif isinstance(att, dict):
            email = (att.get("email") or "").strip().lower()
            name = att.get("name") or att.get("displayName") or ""
            if email and email != "hello@luminone.com":
                attendees.append({"email": email, "name": name})

    if not attendees:
        attendees = [
            {"email": "attendee@unknown.com", "name": "Meeting Attendee"}
        ]

    return attendees


async def _create_followup_drafts(
    db: Any,
    user_id: str,
    debrief_id: str,
    meeting_session_id: str,
    meeting_title: str,
    summary: str,
    action_items: list[Any],
    next_steps: list[Any],
    attendees: list[dict[str, str]],
) -> int:
    """Generate and insert follow-up email drafts for each attendee."""
    action_items_text = _format_items(action_items)
    next_steps_text = _format_items(next_steps)

    email_body = await _generate_followup_email(
        meeting_title=meeting_title,
        summary=summary,
        action_items_text=action_items_text,
        next_steps_text=next_steps_text,
    )

    count = 0
    for attendee in attendees:
        try:
            db.table("email_drafts").insert({
                "user_id": user_id,
                "recipient_email": attendee["email"],
                "recipient_name": attendee.get("name") or None,
                "subject": f"Following up \u2014 {meeting_title}",
                "body": email_body,
                "purpose": "follow_up",
                "status": "draft",
                "draft_type": "debrief_followup",
                "context": json.dumps({
                    "debrief_id": debrief_id,
                    "meeting_session_id": meeting_session_id,
                    "source": "debrief_approval",
                }),
            }).execute()
            count += 1
        except Exception:
            logger.exception(
                "[DebriefApproval] Failed to insert email draft for %s",
                attendee["email"],
            )

    return count


def _format_items(items: list[Any]) -> str:
    """Format action items / next steps into readable text for LLM prompt."""
    parts: list[str] = []
    for item in items:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = (
                item.get("item")
                or item.get("task")
                or item.get("description")
                or str(item)
            )
            owner = item.get("owner", "")
            due = item.get("due") or item.get("due_date") or ""
            if owner:
                text += f" (owner: {owner})"
            if due:
                text += f" (due: {due})"
            parts.append(text)
    return "; ".join(parts) if parts else "None specified"


async def _generate_followup_email(
    meeting_title: str,
    summary: str,
    action_items_text: str,
    next_steps_text: str,
) -> str:
    """Generate follow-up email body using LLM, with fallback template."""
    try:
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        prompt = (
            "Write a warm, professional follow-up email (max 150 words) "
            "from Dhruv Patwardhan.\n"
            f"Meeting: {meeting_title}.\n"
            f"Summary: {summary}\n"
            f"Action items: {action_items_text}\n"
            f"Next steps: {next_steps_text}\n"
            "Reference specific discussion points. "
            "Confirm action items with owners and deadlines.\n"
            "Return only the email body, no subject line."
        )

        llm = LLMClient()
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
            task=TaskType.SCRIBE_DRAFT_EMAIL,
            agent_id="debrief_followup",
        )
        return response.strip()

    except Exception:
        logger.exception(
            "[DebriefApproval] LLM email generation failed, using fallback"
        )
        return (
            f"Hi,\n\n"
            f"Thank you for the productive conversation during our meeting "
            f'"{meeting_title}." I wanted to follow up on what we discussed.\n\n'
            f"Key points from our discussion:\n{summary}\n\n"
            f"Action items we agreed on:\n{action_items_text}\n\n"
            f"Next steps:\n{next_steps_text}\n\n"
            f"Please let me know if I missed anything or if you have questions.\n\n"
            f"Best regards,\nDhruv"
        )


def _write_memory_facts(
    db: Any,
    user_id: str,
    debrief_id: str,
    meeting_title: str,
    meeting_time: str,
    summary: str,
    stakeholder_signals: list[Any],
    action_items: list[Any],
    attendees: list[dict[str, str]],
) -> int:
    """Write semantic memory facts for each external attendee."""
    meeting_date = meeting_time[:10] if meeting_time else "recently"

    signals_text = ""
    if stakeholder_signals:
        signal_parts: list[str] = []
        for s in stakeholder_signals:
            if isinstance(s, str):
                signal_parts.append(s)
            elif isinstance(s, dict):
                signal_parts.append(
                    s.get("content") or s.get("signal") or str(s)
                )
        signals_text = "; ".join(signal_parts[:3])

    count = 0
    for attendee in attendees:
        attendee_name = attendee.get("name") or attendee.get("email", "Unknown")

        fact = (
            f"{attendee_name} met with Dhruv on {meeting_date}. "
            f"{summary}"
        )
        if signals_text:
            fact += f" Signals: {signals_text}"

        try:
            db.table("memory_semantic").insert({
                "user_id": user_id,
                "fact": fact,
                "confidence": 0.9,
                "source": "meeting_debrief",
                "metadata": json.dumps({
                    "debrief_id": debrief_id,
                    "meeting_title": meeting_title,
                    "action_items": action_items,
                    "reference_id": debrief_id,
                }),
            }).execute()
            count += 1
        except Exception:
            logger.exception(
                "[DebriefApproval] Failed to write memory fact for %s",
                attendee_name,
            )

    return count
