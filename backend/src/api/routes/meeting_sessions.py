"""Meeting session API routes for MeetingBaaS bot management."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("/sessions")
async def list_sessions(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List active meeting sessions for the current user.

    Returns sessions with status in ('joining', 'in_meeting').
    """
    db = SupabaseClient.get_client()
    result = (
        db.table("meeting_sessions")
        .select("*")
        .eq("user_id", current_user.id)
        .in_("status", ["joining", "in_meeting"])
        .order("started_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/sessions/{session_id}")
async def get_session(
    current_user: CurrentUser,
    session_id: str,
) -> dict[str, Any]:
    """Get details of a specific meeting session."""
    db = SupabaseClient.get_client()
    result = (
        db.table("meeting_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Meeting session not found")
    return result.data[0]


@router.post("/{calendar_event_id}/join", status_code=201)
async def join_meeting(
    current_user: CurrentUser,
    calendar_event_id: str,
) -> dict[str, Any]:
    """Manually trigger bot dispatch for a specific calendar event.

    Extracts the meeting URL from the calendar event metadata and dispatches
    a MeetingBaaS bot to join the call.

    Returns the created meeting_sessions row.
    """
    from src.integrations.meetingbaas.client import MeetingBaaSError, get_meetingbaas_client
    from src.jobs.meeting_bot_dispatcher import _extract_meeting_url

    db = SupabaseClient.get_client()

    # Fetch the calendar event
    event_resp = (
        db.table("calendar_events")
        .select("id, user_id, title, start_time, metadata")
        .eq("id", calendar_event_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not event_resp.data:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    event = event_resp.data[0]

    # Check for existing session
    existing_resp = (
        db.table("meeting_sessions")
        .select("id, status, bot_id")
        .eq("calendar_event_id", calendar_event_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if existing_resp.data:
        existing = existing_resp.data[0]
        if existing["status"] in ("joining", "in_meeting"):
            raise HTTPException(
                status_code=409,
                detail=f"Bot already active for this event (status: {existing['status']})",
            )

    # Extract meeting URL
    meeting_url = _extract_meeting_url(event.get("metadata"), event.get("title"))
    if not meeting_url:
        raise HTTPException(
            status_code=422,
            detail="No Zoom or Teams meeting URL found in this calendar event",
        )

    # Get user profile for bot name
    user_first_name = "Your"
    try:
        profile_resp = (
            db.table("user_profiles")
            .select("full_name")
            .eq("user_id", current_user.id)
            .limit(1)
            .execute()
        )
        if profile_resp.data and profile_resp.data[0].get("full_name"):
            user_first_name = profile_resp.data[0]["full_name"].split()[0]
    except Exception:
        logger.debug("Could not fetch user profile for %s", current_user.id)

    bot_name = f"ARIA — {user_first_name}'s AI Colleague"

    # Dispatch bot
    client = get_meetingbaas_client()
    try:
        bot_response = await client.create_bot(
            meeting_url=meeting_url,
            bot_name=bot_name,
        )
    except MeetingBaaSError as e:
        logger.error(
            "Failed to dispatch bot for event %s: %s",
            calendar_event_id,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail=f"MeetingBaaS bot dispatch failed: {e}",
        ) from e

    bot_id = bot_response.get("bot_id")
    now = datetime.now(timezone.utc).isoformat()

    # Insert or upsert meeting_sessions row
    session_row = {
        "calendar_event_id": calendar_event_id,
        "user_id": current_user.id,
        "bot_id": bot_id,
        "status": "joining",
        "meeting_url": meeting_url,
        "meeting_title": event.get("title"),
        "started_at": now,
    }

    insert_resp = (
        db.table("meeting_sessions")
        .upsert(session_row, on_conflict="calendar_event_id,user_id")
        .execute()
    )

    if not insert_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create meeting session")

    session = insert_resp.data[0]

    logger.info(
        "Manual bot dispatch for meeting",
        extra={
            "calendar_event_id": calendar_event_id,
            "user_id": current_user.id,
            "bot_id": bot_id,
            "meeting_title": event.get("title"),
        },
    )

    return session


@router.delete("/sessions/{session_id}/leave")
async def leave_meeting(
    current_user: CurrentUser,
    session_id: str,
) -> dict[str, Any]:
    """Remove a bot from a meeting.

    Calls MeetingBaaS to delete the bot and updates the session status to 'left'.
    """
    from src.integrations.meetingbaas.client import MeetingBaaSError, get_meetingbaas_client

    db = SupabaseClient.get_client()

    # Fetch the session
    session_resp = (
        db.table("meeting_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not session_resp.data:
        raise HTTPException(status_code=404, detail="Meeting session not found")

    session = session_resp.data[0]

    if session["status"] in ("ended", "left"):
        raise HTTPException(
            status_code=409,
            detail=f"Session already {session['status']}",
        )

    bot_id = session.get("bot_id")
    if bot_id:
        client = get_meetingbaas_client()
        try:
            await client.delete_bot(bot_id)
        except MeetingBaaSError as e:
            logger.warning("Failed to delete bot %s: %s", bot_id, e)
            # Continue with status update even if bot deletion fails

    # Update session status
    now = datetime.now(timezone.utc).isoformat()
    update_resp = (
        db.table("meeting_sessions")
        .update({"status": "left", "ended_at": now})
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not update_resp.data:
        raise HTTPException(status_code=500, detail="Failed to update meeting session")

    logger.info(
        "Bot removed from meeting",
        extra={
            "session_id": session_id,
            "user_id": current_user.id,
            "bot_id": bot_id,
        },
    )

    return update_resp.data[0]
