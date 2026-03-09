"""MeetingBaaS webhook receiver for bot status updates and transcript processing.

Handles two event types from MeetingBaaS:
- bot.status_change: Updates meeting_sessions.status
- complete: Triggers transcript storage and auto-debrief generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/meetingbaas")
async def meetingbaas_webhook(request: Request) -> JSONResponse:
    """Receive MeetingBaaS webhook events.

    No auth required — MeetingBaaS does not sign payloads.
    Returns 200 immediately for all events to avoid retries.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("MeetingBaaS webhook: invalid JSON body")
        return JSONResponse({"ok": True}, status_code=200)

    event = payload.get("event", "")
    data = payload.get("data", {}) or {}
    bot_id = data.get("bot_id") or payload.get("bot_id", "")

    logger.info(
        "MeetingBaaS webhook received",
        extra={"event": event, "bot_id": bot_id},
    )

    db = get_supabase_client()

    if event == "bot.status_change":
        status = data.get("status") or payload.get("status", "")
        _handle_status_change(bot_id, status, db)
    elif event == "complete":
        asyncio.create_task(_process_transcript(payload, db))

    return JSONResponse({"ok": True}, status_code=200)


def _handle_status_change(
    bot_id: str,
    status: str,
    db: Any,
) -> None:
    """Update meeting_sessions status based on bot status change.

    Maps MeetingBaaS status strings to our internal status values.
    """
    # Map MeetingBaaS statuses to our schema constraint values
    status_map: dict[str, str] = {
        "joining": "joining",
        "joined": "in_meeting",
        "in_meeting": "in_meeting",
        "ended": "ended",
        "failed": "failed",
        "error": "failed",
        "left": "left",
    }
    mapped_status = status_map.get(status)
    if not mapped_status:
        logger.warning(
            "MeetingBaaS unknown status: %s for bot %s",
            status,
            bot_id,
        )
        return

    try:
        db.table("meeting_sessions").update(
            {"status": mapped_status, "updated_at": datetime.now(UTC).isoformat()}
        ).eq("bot_id", bot_id).execute()
        logger.info(
            "Meeting session status updated",
            extra={"bot_id": bot_id, "status": mapped_status},
        )
    except Exception:
        logger.exception("Failed to update meeting session status for bot %s", bot_id)


async def _process_transcript(payload: dict[str, Any], db: Any) -> None:
    """Process completed meeting transcript and generate debrief.

    Called as a background task after receiving a 'complete' event.
    Stores the transcript, generates an AI debrief, and queues a review action.
    """
    data = payload.get("data", {}) or {}
    bot_id = data.get("bot_id") or payload.get("bot_id", "")

    try:
        # Extract transcript from payload
        raw_transcript: list[dict[str, Any]] = data.get("transcript") or payload.get("transcript", [])
        transcript_text = _flatten_transcript(raw_transcript)

        # Look up the meeting session
        result = (
            db.table("meeting_sessions")
            .select("*")
            .eq("bot_id", bot_id)
            .execute()
        )
        if not result.data:
            logger.warning(
                "No meeting session found for bot_id=%s, skipping transcript",
                bot_id,
            )
            return

        session = result.data[0]
        session_id = session["id"]
        user_id = session["user_id"]
        calendar_event_id = session.get("calendar_event_id")

        # Store transcript
        transcript_id = str(uuid.uuid4())
        db.table("meeting_transcripts").insert({
            "id": transcript_id,
            "meeting_session_id": session_id,
            "calendar_event_id": calendar_event_id,
            "user_id": user_id,
            "raw_transcript": raw_transcript,
            "transcript_text": transcript_text,
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()

        logger.info(
            "Meeting transcript stored",
            extra={
                "transcript_id": transcript_id,
                "meeting_session_id": session_id,
                "bot_id": bot_id,
            },
        )

        # Generate debrief
        debrief_data = await _generate_debrief(
            session, transcript_text
        )

        # Store debrief
        debrief_id = str(uuid.uuid4())
        db.table("meeting_debriefs").insert({
            "id": debrief_id,
            "meeting_session_id": session_id,
            "calendar_event_id": calendar_event_id,
            "user_id": user_id,
            "summary": debrief_data.get("summary", ""),
            "key_decisions": debrief_data.get("key_decisions", []),
            "action_items": debrief_data.get("action_items", []),
            "objections": debrief_data.get("objections", []),
            "stakeholder_signals": debrief_data.get("stakeholder_signals", []),
            "next_steps": debrief_data.get("next_steps", []),
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()

        logger.info(
            "Meeting debrief generated",
            extra={
                "debrief_id": debrief_id,
                "meeting_session_id": session_id,
            },
        )

        # Update meeting session to completed
        db.table("meeting_sessions").update({
            "status": "completed",
            "ended_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", session_id).execute()

        # Queue action for user review
        db.table("aria_action_queue").insert({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "agent": "scribe",
            "action_type": "debrief_review",
            "title": "Meeting debrief ready for review",
            "description": f"Debrief for: {session.get('meeting_title', 'Untitled meeting')}",
            "risk_level": "low",
            "status": "pending",
            "payload": {
                "meeting_session_id": session_id,
                "debrief_id": debrief_id,
                "reference_id": debrief_id,
                "reference_type": "meeting_debrief",
                "meeting_title": session.get("meeting_title", ""),
            },
        }).execute()

        logger.info(
            "Debrief review action queued",
            extra={
                "debrief_id": debrief_id,
                "user_id": user_id,
            },
        )

    except Exception:
        logger.exception(
            "Failed to process transcript for bot_id=%s", bot_id
        )


def _flatten_transcript(
    transcript: list[dict[str, Any]],
) -> str:
    """Flatten MeetingBaaS transcript array to readable text.

    Args:
        transcript: List of {speaker, words} objects from MeetingBaaS.

    Returns:
        Formatted transcript text with "Speaker: sentence" per line.
    """
    lines: list[str] = []
    for entry in transcript:
        speaker = entry.get("speaker", "Unknown")
        words = entry.get("words", "")
        if words:
            lines.append(f"{speaker}: {words}")
    return "\n".join(lines)


async def _generate_debrief(
    session: dict[str, Any],
    transcript_text: str,
) -> dict[str, Any]:
    """Generate a structured meeting debrief using LLM.

    Args:
        session: The meeting_sessions row.
        transcript_text: Flattened transcript text.

    Returns:
        Dict with summary, key_decisions, action_items, objections,
        stakeholder_signals, and next_steps.
    """
    meeting_title = session.get("meeting_title", "Untitled meeting")

    prompt = (
        f"You are a sales intelligence analyst. Analyze this meeting transcript "
        f'from "{meeting_title}" and extract structured insights.\n\n'
        f"TRANSCRIPT:\n{transcript_text}\n\n"
        f"Return a JSON object with exactly these keys:\n"
        f'- "summary": A concise 2-3 sentence summary of the meeting\n'
        f'- "key_decisions": Array of strings, each a decision made during the meeting\n'
        f'- "action_items": Array of objects with keys "item" (string), '
        f'"owner" (string), "due" (string or null)\n'
        f'- "objections": Array of strings, any objections or concerns raised\n'
        f'- "stakeholder_signals": Array of strings, signals about stakeholder '
        f"sentiment, buying intent, or relationship dynamics\n"
        f'- "next_steps": Array of strings, agreed next steps\n\n'
        f"Return ONLY the JSON object, no other text."
    )

    llm = LLMClient()
    try:
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.1,
            task=TaskType.SCRIBE_CLASSIFY_EMAIL,
            agent_id="meeting_debrief",
        )

        # Parse JSON from response
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        return json.loads(cleaned)

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning(
            "Failed to parse debrief JSON, returning defaults: %s", exc
        )
        return {
            "summary": "Debrief generation failed — transcript stored for manual review.",
            "key_decisions": [],
            "action_items": [],
            "objections": [],
            "stakeholder_signals": [],
            "next_steps": [],
        }
