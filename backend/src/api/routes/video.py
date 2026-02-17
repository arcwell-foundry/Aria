"""Video session API routes for Tavus avatar integration."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.core.ws import ws_manager
from src.db.supabase import get_supabase_client
from src.integrations.tavus import get_tavus_client
from src.integrations.tavus_tool_executor import VideoToolExecutor
from src.integrations.tavus_tools import VALID_TOOL_NAMES
from src.models.video import (
    TranscriptEntryResponse,
    VideoSessionCreate,
    VideoSessionListResponse,
    VideoSessionResponse,
    VideoSessionStatus,
    VideoToolCallRequest,
    VideoToolCallResponse,
)
from src.models.ws_events import AriaSpeakingEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


async def build_aria_context(user_id: str, session_type: str, lead_id: str | None = None) -> str:
    """Build conversational context for Tavus session based on ARIA intelligence.

    Gathers user profile, active goals, recent activity, and lead context
    to provide rich context for the avatar conversation.

    Args:
        user_id: The user's ID.
        session_type: Type of video session (chat, briefing, debrief, consultation).
        lead_id: Optional lead ID for lead-specific context.

    Returns:
        Context string for the Tavus conversation.
    """
    db = get_supabase_client()
    context_parts: list[str] = []

    # Get user profile summary
    try:
        profile_result = (
            db.table("profiles")
            .select("first_name, last_name, role, company_name")
            .eq("id", user_id)
            .execute()
        )
        if profile_result.data:
            profile = profile_result.data[0]
            name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            role = profile.get("role", "")
            company = profile.get("company_name", "")
            if name:
                context_parts.append(f"User: {name}")
            if role:
                context_parts.append(f"Role: {role}")
            if company:
                context_parts.append(f"Company: {company}")
    except Exception as e:
        logger.warning(
            "Failed to fetch user profile for context",
            extra={"user_id": user_id, "error": str(e)},
        )

    # Get active goals summary
    try:
        goals_result = (
            db.table("goals")
            .select("title, status, priority")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("priority", desc=True)
            .limit(3)
            .execute()
        )
        if goals_result.data:
            goal_titles = [g["title"] for g in goals_result.data]
            context_parts.append(f"Active Goals: {', '.join(goal_titles)}")
    except Exception as e:
        logger.warning(
            "Failed to fetch active goals for context",
            extra={"user_id": user_id, "error": str(e)},
        )

    # Get lead context if provided
    if lead_id:
        try:
            lead_result = (
                db.table("leads")
                .select("company_name, contact_name, status, priority, notes")
                .eq("id", lead_id)
                .execute()
            )
            if lead_result.data:
                lead = lead_result.data[0]
                context_parts.append(f"Lead Company: {lead.get('company_name', 'Unknown')}")
                if lead.get("contact_name"):
                    context_parts.append(f"Lead Contact: {lead['contact_name']}")
                if lead.get("status"):
                    context_parts.append(f"Lead Status: {lead['status']}")
                if lead.get("priority"):
                    context_parts.append(f"Lead Priority: {lead['priority']}")
        except Exception as e:
            logger.warning(
                "Failed to fetch lead context",
                extra={"user_id": user_id, "lead_id": lead_id, "error": str(e)},
            )

    # Add session type context
    session_contexts = {
        "briefing": "This is a briefing session. Provide concise updates on key metrics and priorities.",
        "debrief": "This is a debrief session. Help the user reflect on recent activities and outcomes.",
        "consultation": "This is a consultation session. Provide expert guidance and strategic advice.",
        "chat": "This is a general chat session. Be helpful and conversational.",
    }
    if session_type in session_contexts:
        context_parts.append(session_contexts[session_type])

    return "\n".join(context_parts) if context_parts else ""


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

    # Build ARIA context for the session
    aria_context = await build_aria_context(
        user_id=current_user.id,
        session_type=request.session_type.value,
        lead_id=request.lead_id,
    )

    # Combine user-provided context with ARIA context
    full_context = aria_context
    if request.context:
        full_context = f"{request.context}\n\n{aria_context}" if aria_context else request.context

    try:
        tavus_response = await tavus.create_conversation(
            user_id=current_user.id,
            conversation_name=f"aria-{request.session_type.value}-{session_id[:8]}",
            context=full_context or None,
            custom_greeting=request.custom_greeting,
            memory_stores=[{"memory_store_id": f"aria-user-{current_user.id}"}],
            document_tags=["aria-context"],
            retrieval_strategy="balanced",
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
        "lead_id": request.lead_id,
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

    # Notify frontend that ARIA avatar is now speaking
    await ws_manager.send_to_user(current_user.id, AriaSpeakingEvent(is_speaking=True))

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
        lead_id=saved.get("lead_id"),
        perception_analysis=saved.get("perception_analysis"),
    )


@router.get("/sessions", response_model=VideoSessionListResponse)
async def list_video_sessions(
    current_user: CurrentUser,
    limit: int = Query(
        default=20, ge=1, le=100, description="Maximum number of sessions to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of sessions to skip"),
    session_type: str | None = Query(default=None, description="Filter by session type"),
    status: str | None = Query(default=None, description="Filter by session status"),
) -> VideoSessionListResponse:
    """List video sessions for the current user.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of sessions to return (1-100, default 20).
        offset: Number of sessions to skip for pagination.
        session_type: Optional filter by session type (chat, briefing, debrief, consultation).
        status: Optional filter by status (created, active, ended, error).

    Returns:
        Paginated list of video sessions.
    """
    db = get_supabase_client()

    # Build query with filters
    query = db.table("video_sessions").select("*", count="exact").eq("user_id", current_user.id)

    if session_type:
        query = query.eq("session_type", session_type)
    if status:
        query = query.eq("status", status)

    # Apply pagination and ordering
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    sessions = result.data or []
    total = result.count if hasattr(result, "count") and result.count is not None else len(sessions)

    items = [
        VideoSessionResponse(
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
            lead_id=session.get("lead_id"),
            perception_analysis=session.get("perception_analysis"),
        )
        for session in sessions
    ]

    return VideoSessionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
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
        The video session details including transcripts and perception
        analysis for ended sessions.

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

    # Fetch transcripts for ended sessions
    transcripts: list[TranscriptEntryResponse] | None = None
    if session["status"] == VideoSessionStatus.ENDED.value:
        try:
            transcript_result = (
                db.table("video_transcript_entries")
                .select("*")
                .eq("video_session_id", session_id)
                .order("timestamp_ms")
                .execute()
            )
            if transcript_result.data:
                transcripts = [
                    TranscriptEntryResponse(
                        id=entry["id"],
                        video_session_id=entry["video_session_id"],
                        speaker=entry["speaker"],
                        content=entry["content"],
                        timestamp_ms=entry["timestamp_ms"],
                        created_at=entry["created_at"],
                    )
                    for entry in transcript_result.data
                ]
        except Exception as e:
            logger.warning(
                "Failed to fetch transcripts for session",
                extra={"session_id": session_id, "error": str(e)},
            )

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
        lead_id=session.get("lead_id"),
        perception_analysis=session.get("perception_analysis"),
        transcripts=transcripts,
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

    # Notify frontend that ARIA avatar has stopped speaking
    await ws_manager.send_to_user(current_user.id, AriaSpeakingEvent(is_speaking=False))

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
        lead_id=updated.get("lead_id"),
        perception_analysis=updated.get("perception_analysis"),
    )


@router.post("/tools/execute", response_model=VideoToolCallResponse)
async def execute_video_tool(
    current_user: CurrentUser,
    request: VideoToolCallRequest,
) -> VideoToolCallResponse:
    """Execute a tool call triggered by the Tavus CVI LLM during a video conversation.

    The frontend receives a ``conversation.tool_call`` event via Daily's
    WebRTC data channel, calls this endpoint, then echoes the result back
    to the conversation via ``conversation.echo``.

    Args:
        current_user: The authenticated user.
        request: Tool name and arguments from the tool call event.

    Returns:
        Spoken-ready result string for the avatar to speak.
    """
    if request.tool_name not in VALID_TOOL_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tool: {request.tool_name}",
        )

    logger.info(
        "Executing video tool call",
        extra={
            "user_id": current_user.id,
            "tool_name": request.tool_name,
            "conversation_id": request.conversation_id,
        },
    )

    executor = VideoToolExecutor(user_id=current_user.id)
    result = await executor.execute(
        tool_name=request.tool_name,
        arguments=request.arguments,
    )

    return VideoToolCallResponse(
        tool_name=request.tool_name,
        result=result,
        success=not result.startswith("I ran into an issue"),
    )
