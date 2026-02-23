"""Session management API routes for cross-modal persistence.

Provides endpoints for:
- Creating new sessions
- Getting active session for the current user
- Updating session state
- Archiving sessions
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import NotFoundError, sanitize_error
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SessionData(BaseModel):
    """The session_data JSONB payload."""

    current_route: str = "/"
    active_modality: str = "text"
    conversation_thread: list[str] = []
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    current_route: str = "/"
    active_modality: str = "text"
    conversation_thread: list[str] = []
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSessionRequest(BaseModel):
    """Request to update session state."""

    current_route: str | None = None
    active_modality: str | None = None
    conversation_thread: list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class SessionResponse(BaseModel):
    """Response for session operations."""

    id: str
    user_id: str
    session_data: SessionData
    is_active: bool
    day_date: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    sessions: list[SessionResponse]
    total: int


# =============================================================================
# Helper Functions
# =============================================================================


def _row_to_response(row: dict[str, Any]) -> SessionResponse:
    """Convert a database row to SessionResponse."""
    session_data = row.get("session_data", {})
    if isinstance(session_data, str):
        import json
        session_data = json.loads(session_data)

    # Support both 'id' and 'session_id' column names (schema uses session_id as PK)
    session_id = row.get("session_id") or row.get("id")
    if not session_id:
        raise ValueError("Session row missing both session_id and id columns")

    return SessionResponse(
        id=session_id,
        user_id=row["user_id"],
        session_data=SessionData(
            current_route=session_data.get("current_route", "/"),
            active_modality=session_data.get("active_modality", "text"),
            conversation_thread=session_data.get("conversation_thread", []),
            metadata=session_data.get("metadata", {}),
        ),
        is_active=row["is_active"],
        day_date=row["day_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=SessionResponse)
async def create_session(
    current_user: CurrentUser,
    request: CreateSessionRequest,
) -> SessionResponse:
    """Create a new session for the current user.

    If an active session already exists for today, returns that session.
    Otherwise, archives any previous active sessions and creates a new one.

    Args:
        current_user: The authenticated user.
        request: Session creation parameters.

    Returns:
        The created or existing session.
    """
    db = get_supabase_client()
    today = date.today().isoformat()

    # Check for existing active session today
    existing = (
        db.table("user_sessions")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("day_date", today)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )

    if existing.data:
        logger.info(
            "Returning existing session for user",
            extra={"user_id": current_user.id, "session_id": existing.data["id"]},
        )
        return _row_to_response(existing.data)

    # Archive previous active sessions
    (
        db.table("user_sessions")
        .update({"is_active": False, "updated_at": datetime.now(UTC).isoformat()})
        .eq("user_id", current_user.id)
        .eq("is_active", True)
        .execute()
    )

    # Create new session
    session_data = {
        "current_route": request.current_route,
        "active_modality": request.active_modality,
        "conversation_thread": request.conversation_thread,
        "metadata": request.metadata,
    }

    result = (
        db.table("user_sessions")
        .insert(
            {
                "user_id": current_user.id,
                "session_data": session_data,
                "is_active": True,
                "day_date": today,
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create session")

    logger.info(
        "Created new session for user",
        extra={"user_id": current_user.id, "session_id": result.data[0]["id"]},
    )

    return _row_to_response(result.data[0])


@router.get("/active", response_model=SessionResponse | None)
async def get_active_session(
    current_user: CurrentUser,
) -> SessionResponse | None:
    """Get the active session for the current user.

    Returns the active session for today if it exists.
    Creates a new session if none exists.

    Args:
        current_user: The authenticated user.

    Returns:
        The active session or None.
    """
    try:
        db = get_supabase_client()
        today = date.today().isoformat()

        result = (
            db.table("user_sessions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("day_date", today)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )

        if result.data:
            return _row_to_response(result.data)

        # No active session - return None to signal frontend to create one
        logger.info(
            "No active session found for user",
            extra={"user_id": current_user.id},
        )
        return None
    except Exception as e:
        logger.exception(
            "Error fetching active session for user %s: %s",
            current_user.id,
            e,
        )
        raise HTTPException(status_code=500, detail="Failed to fetch session") from e


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    current_user: CurrentUser,
    session_id: str,
) -> SessionResponse:
    """Get a specific session by ID.

    Args:
        current_user: The authenticated user.
        session_id: The session ID.

    Returns:
        The session data.

    Raises:
        HTTPException: If session not found or doesn't belong to user.
    """
    db = get_supabase_client()

    result = (
        db.table("user_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    return _row_to_response(result.data)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    current_user: CurrentUser,
    session_id: str,
    request: UpdateSessionRequest,
) -> SessionResponse:
    """Update session state.

    Only provided fields are updated. This is called periodically by the
    frontend to sync session state.

    Args:
        current_user: The authenticated user.
        session_id: The session ID.
        request: Fields to update.

    Returns:
        The updated session.

    Raises:
        HTTPException: If session not found or doesn't belong to user.
    """
    db = get_supabase_client()

    # First verify ownership and get current session
    current = (
        db.table("user_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )

    if not current.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build update payload
    current_data = current.data.get("session_data", {})
    if isinstance(current_data, str):
        import json
        current_data = json.loads(current_data)

    new_session_data = current_data.copy()

    if request.current_route is not None:
        new_session_data["current_route"] = request.current_route
    if request.active_modality is not None:
        new_session_data["active_modality"] = request.active_modality
    if request.conversation_thread is not None:
        new_session_data["conversation_thread"] = request.conversation_thread
    if request.metadata is not None:
        # Merge metadata
        new_session_data["metadata"] = {**current_data.get("metadata", {}), **request.metadata}

    update_payload: dict[str, Any] = {
        "session_data": new_session_data,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    if request.is_active is not None:
        update_payload["is_active"] = request.is_active

    # Perform update
    result = (
        db.table("user_sessions")
        .update(update_payload)
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update session")

    logger.debug(
        "Updated session",
        extra={"user_id": current_user.id, "session_id": session_id},
    )

    return _row_to_response(result.data[0])


@router.post("/{session_id}/archive", response_model=SessionResponse)
async def archive_session(
    current_user: CurrentUser,
    session_id: str,
) -> SessionResponse:
    """Archive a session by setting is_active to false.

    Called when a new session is started or when user explicitly starts fresh.

    Args:
        current_user: The authenticated user.
        session_id: The session ID.

    Returns:
        The archived session.

    Raises:
        HTTPException: If session not found.
    """
    db = get_supabase_client()

    result = (
        db.table("user_sessions")
        .update(
            {
                "is_active": False,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", session_id)
        .eq("user_id", current_user.id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(
        "Archived session",
        extra={"user_id": current_user.id, "session_id": session_id},
    )

    return _row_to_response(result.data[0])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: CurrentUser,
    limit: int = 10,
    offset: int = 0,
    include_archived: bool = False,
) -> SessionListResponse:
    """List sessions for the current user.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of sessions to return.
        offset: Number of sessions to skip.
        include_archived: Whether to include archived sessions.

    Returns:
        List of sessions.
    """
    db = get_supabase_client()

    query = db.table("user_sessions").select("*").eq("user_id", current_user.id)

    if not include_archived:
        query = query.eq("is_active", True)

    result = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

    # Get total count
    count_query = db.table("user_sessions").select("id", count="exact").eq("user_id", current_user.id)
    if not include_archived:
        count_query = count_query.eq("is_active", True)
    count_result = count_query.execute()

    total = count_result.count if hasattr(count_result, "count") and count_result.count else len(result.data)

    return SessionListResponse(
        sessions=[_row_to_response(row) for row in result.data],
        total=total,
    )
