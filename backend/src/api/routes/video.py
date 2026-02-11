"""Video session API routes for Tavus avatar integration."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.integrations.tavus import get_tavus_client
from src.models.video import (
    VideoSessionCreate,
    VideoSessionResponse,
    VideoSessionStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/sessions", response_model=VideoSessionResponse)
async def create_video_session(
    current_user: CurrentUser,
    request: VideoSessionCreate,
) -> VideoSessionResponse:
    """Create a new video session with Tavus avatar.

    Calls the Tavus API to create a conversation, then persists the
    session record in the video_sessions table.

    Args:
        current_user: The authenticated user.
        request: Video session creation parameters.

    Returns:
        The created video session details.

    Raises:
        HTTPException: 502 if the Tavus API call fails.
    """
    session_id = str(uuid.uuid4())
    tavus = get_tavus_client()

    try:
        tavus_response = await tavus.create_conversation(
            user_id=current_user.id,
            conversation_name=f"aria-{request.session_type.value}-{session_id[:8]}",
            context=request.context,
            custom_greeting=request.custom_greeting,
        )
    except httpx.HTTPStatusError:
        logger.exception(
            "Tavus API error creating conversation",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=502,
            detail="Video service temporarily unavailable",
        ) from None
    except Exception:
        logger.exception(
            "Unexpected error calling Tavus API",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=502,
            detail="Video service temporarily unavailable",
        ) from None

    tavus_conversation_id = str(tavus_response.get("conversation_id", ""))
    room_url = str(tavus_response.get("conversation_url", "")) or None

    now = datetime.now(UTC).isoformat()

    row = {
        "id": session_id,
        "user_id": current_user.id,
        "tavus_conversation_id": tavus_conversation_id,
        "room_url": room_url,
        "status": VideoSessionStatus.ACTIVE.value,
        "session_type": request.session_type.value,
        "started_at": now,
        "ended_at": None,
        "duration_seconds": None,
        "created_at": now,
    }

    db = get_supabase_client()
    result = db.table("video_sessions").insert(row).execute()

    if not result.data or len(result.data) == 0:
        logger.error(
            "Failed to insert video session",
            extra={"session_id": session_id, "user_id": current_user.id},
        )
        raise HTTPException(status_code=500, detail="Failed to create video session")

    saved = result.data[0]

    logger.info(
        "Video session created",
        extra={
            "session_id": session_id,
            "user_id": current_user.id,
            "tavus_conversation_id": tavus_conversation_id,
        },
    )

    return VideoSessionResponse(
        id=saved["id"],
        user_id=saved["user_id"],
        tavus_conversation_id=saved["tavus_conversation_id"],
        room_url=saved.get("room_url"),
        status=saved["status"],
        session_type=saved["session_type"],
        started_at=saved.get("started_at"),
        ended_at=saved.get("ended_at"),
        duration_seconds=saved.get("duration_seconds"),
        created_at=saved["created_at"],
    )


@router.get("/sessions/{session_id}", response_model=VideoSessionResponse)
async def get_video_session(
    current_user: CurrentUser,
    session_id: str,
) -> VideoSessionResponse:
    """Get details for a specific video session.

    Args:
        current_user: The authenticated user.
        session_id: The video session ID.

    Returns:
        The video session details.

    Raises:
        HTTPException: 404 if session not found or does not belong to user.
    """
    db = get_supabase_client()
    result = (
        db.table("video_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Video session not found")

    session = result.data[0]

    return VideoSessionResponse(
        id=session["id"],
        user_id=session["user_id"],
        tavus_conversation_id=session["tavus_conversation_id"],
        room_url=session.get("room_url"),
        status=session["status"],
        session_type=session["session_type"],
        started_at=session.get("started_at"),
        ended_at=session.get("ended_at"),
        duration_seconds=session.get("duration_seconds"),
        created_at=session["created_at"],
    )


@router.post("/sessions/{session_id}/end", response_model=VideoSessionResponse)
async def end_video_session(
    current_user: CurrentUser,
    session_id: str,
) -> VideoSessionResponse:
    """End an active video session.

    Calls the Tavus API to end the conversation, calculates the session
    duration, and updates the database record.

    Args:
        current_user: The authenticated user.
        session_id: The video session ID to end.

    Returns:
        The updated video session details.

    Raises:
        HTTPException: 404 if session not found, 400 if already ended.
    """
    db = get_supabase_client()
    result = (
        db.table("video_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=404, detail="Video session not found")

    session = result.data[0]

    if session["status"] == VideoSessionStatus.ENDED.value:
        raise HTTPException(status_code=400, detail="Video session already ended")

    # End conversation on Tavus side
    tavus = get_tavus_client()
    try:
        await tavus.end_conversation(session["tavus_conversation_id"])
    except Exception:
        logger.warning(
            "Failed to end Tavus conversation (may already be ended)",
            extra={
                "session_id": session_id,
                "tavus_conversation_id": session["tavus_conversation_id"],
            },
        )

    # Calculate duration
    now = datetime.now(UTC)
    started_at = session.get("started_at")
    duration_seconds: int | None = None
    if started_at:
        started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        duration_seconds = int((now - started_dt).total_seconds())

    # Update the session record
    update_data = {
        "status": VideoSessionStatus.ENDED.value,
        "ended_at": now.isoformat(),
        "duration_seconds": duration_seconds,
    }

    update_result = (
        db.table("video_sessions")
        .update(update_data)
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not update_result.data or len(update_result.data) == 0:
        logger.error(
            "Failed to update video session",
            extra={"session_id": session_id, "user_id": current_user.id},
        )
        raise HTTPException(status_code=500, detail="Failed to update video session")

    updated = update_result.data[0]

    logger.info(
        "Video session ended",
        extra={
            "session_id": session_id,
            "user_id": current_user.id,
            "duration_seconds": duration_seconds,
        },
    )

    return VideoSessionResponse(
        id=updated["id"],
        user_id=updated["user_id"],
        tavus_conversation_id=updated["tavus_conversation_id"],
        room_url=updated.get("room_url"),
        status=updated["status"],
        session_type=updated["session_type"],
        started_at=updated.get("started_at"),
        ended_at=updated.get("ended_at"),
        duration_seconds=updated.get("duration_seconds"),
        created_at=updated["created_at"],
    )
