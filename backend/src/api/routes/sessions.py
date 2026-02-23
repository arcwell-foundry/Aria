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
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# =============================================================================
# PK column detection — handles both 'id' and 'session_id' schemas
# =============================================================================

_SESSION_PK_COL: str | None = None


def _detect_pk_col(db: Any) -> str:
    """Auto-detect whether user_sessions PK column is 'id' or 'session_id'.

    Caches after first *successful* detection. Transient errors (network,
    timeout) are NOT cached so the next call retries the probe.
    """
    global _SESSION_PK_COL
    if _SESSION_PK_COL is not None:
        return _SESSION_PK_COL

    # Probe: try selecting 'session_id' first (matches the earliest migration)
    for candidate in ("session_id", "id"):
        try:
            db.table("user_sessions").select(candidate).limit(1).execute()
            _SESSION_PK_COL = candidate
            logger.info("Detected user_sessions PK column: %s", candidate)
            return candidate
        except Exception as exc:
            exc_str = str(exc)
            # Column-not-found from PostgREST → try next candidate
            if "column" in exc_str.lower() or "400" in exc_str or "PGRST" in exc_str:
                continue
            # Transient error (network, timeout) — don't cache, raise
            logger.warning(
                "Transient error probing user_sessions PK column '%s': %s",
                candidate,
                exc,
            )
            raise

    # Both candidates failed → default to 'session_id' (earliest migration)
    _SESSION_PK_COL = "session_id"
    logger.warning("Could not detect user_sessions PK column; defaulting to 'session_id'")
    return _SESSION_PK_COL


def _select_by_pk(db: Any, session_id: str, user_id: str) -> Any:
    """Select a session by PK + user_id guard. Returns execute() result."""
    pk = _detect_pk_col(db)
    return (
        db.table("user_sessions")
        .select("*")
        .eq(pk, session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )


def _update_by_pk(db: Any, session_id: str, user_id: str, payload: dict) -> Any:
    """Update a session by PK + user_id guard. Returns execute() result.

    If the update succeeds but returns no data (some Supabase SDK / PostgREST
    configurations omit the response body), a follow-up SELECT is issued to
    return the updated row.
    """
    pk = _detect_pk_col(db)
    try:
        result = (
            db.table("user_sessions")
            .update(payload)
            .eq(pk, session_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "user_sessions UPDATE failed",
            extra={"session_id": session_id, "user_id": user_id, "pk_col": pk},
        )
        raise

    # Fallback: some SDK versions don't return data after UPDATE.
    # Re-fetch the row so callers always get the updated record.
    if not result.data:
        logger.debug(
            "UPDATE returned no data; re-fetching row (pk=%s, session_id=%s)",
            pk,
            session_id,
        )
        fallback = _select_by_pk(db, session_id, user_id)
        if fallback and fallback.data:
            # Wrap in a list to match the normal update response shape
            result.data = [fallback.data] if isinstance(fallback.data, dict) else fallback.data

    return result


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

    # Support both 'id' and 'session_id' column names
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

    if existing and existing.data:
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

    if not result or not result.data:
        raise HTTPException(status_code=500, detail="Failed to create session")

    logger.info(
        "Created new session for user",
        extra={"user_id": current_user.id},
    )

    return _row_to_response(result.data[0])


@router.get("/active", response_model=SessionResponse | None)
async def get_active_session(
    current_user: CurrentUser,
) -> SessionResponse | None:
    """Get the active session for the current user.

    Returns the active session for today if it exists, or None.
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

        if result and result.data:
            return _row_to_response(result.data)

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

    Always enforces user_id ownership guard.
    """
    db = get_supabase_client()

    result = _select_by_pk(db, session_id, current_user.id)

    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    return _row_to_response(result.data)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    current_user: CurrentUser,
    session_id: str,
    request: UpdateSessionRequest,
) -> SessionResponse:
    """Update session state.

    Only provided fields are updated. Always enforces user_id ownership guard.
    """
    db = get_supabase_client()

    # Verify ownership and get current session
    try:
        current = _select_by_pk(db, session_id, current_user.id)
    except Exception:
        logger.exception(
            "Session SELECT failed",
            extra={"user_id": current_user.id, "session_id": session_id},
        )
        raise HTTPException(status_code=500, detail="Failed to read session") from None

    if not current or not current.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build update payload
    current_data = current.data.get("session_data") if isinstance(current.data, dict) else None
    if current_data is None:
        current_data = {}
    if isinstance(current_data, str):
        import json
        current_data = json.loads(current_data)

    new_session_data = dict(current_data)

    if request.current_route is not None:
        new_session_data["current_route"] = request.current_route
    if request.active_modality is not None:
        new_session_data["active_modality"] = request.active_modality
    if request.conversation_thread is not None:
        new_session_data["conversation_thread"] = request.conversation_thread
    if request.metadata is not None:
        new_session_data["metadata"] = {**current_data.get("metadata", {}), **request.metadata}

    update_payload: dict[str, Any] = {
        "session_data": new_session_data,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    if request.is_active is not None:
        update_payload["is_active"] = request.is_active

    # Perform update with user_id guard
    try:
        result = _update_by_pk(db, session_id, current_user.id, update_payload)
    except Exception:
        logger.exception(
            "Session UPDATE failed",
            extra={"user_id": current_user.id, "session_id": session_id},
        )
        raise HTTPException(status_code=500, detail="Failed to update session") from None

    if not result or not result.data:
        logger.error(
            "Session UPDATE returned no data",
            extra={
                "user_id": current_user.id,
                "session_id": session_id,
                "pk_col": _SESSION_PK_COL,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to update session")

    # Normalize: result.data may be a list or a dict depending on the query path
    row = result.data[0] if isinstance(result.data, list) else result.data

    logger.debug(
        "Updated session",
        extra={"user_id": current_user.id, "session_id": session_id},
    )

    return _row_to_response(row)


@router.post("/{session_id}/archive", response_model=SessionResponse)
async def archive_session(
    current_user: CurrentUser,
    session_id: str,
) -> SessionResponse:
    """Archive a session by setting is_active to false.

    Always enforces user_id ownership guard.
    """
    db = get_supabase_client()

    try:
        result = _update_by_pk(
            db,
            session_id,
            current_user.id,
            {
                "is_active": False,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        logger.exception(
            "Session archive failed",
            extra={"user_id": current_user.id, "session_id": session_id},
        )
        raise HTTPException(status_code=500, detail="Failed to archive session") from None

    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Session not found")

    row = result.data[0] if isinstance(result.data, list) else result.data

    logger.info(
        "Archived session",
        extra={"user_id": current_user.id, "session_id": session_id},
    )

    return _row_to_response(row)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: CurrentUser,
    limit: int = 10,
    offset: int = 0,
    include_archived: bool = False,
) -> SessionListResponse:
    """List sessions for the current user."""
    db = get_supabase_client()

    query = db.table("user_sessions").select("*").eq("user_id", current_user.id)

    if not include_archived:
        query = query.eq("is_active", True)

    result = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

    # Get total count — use '*' which always works regardless of PK column name
    count_query = db.table("user_sessions").select("*", count="exact").eq("user_id", current_user.id)
    if not include_archived:
        count_query = count_query.eq("is_active", True)
    count_result = count_query.execute()

    total = count_result.count if hasattr(count_result, "count") and count_result.count else len(result.data or [])

    return SessionListResponse(
        sessions=[_row_to_response(row) for row in (result.data or [])],
        total=total,
    )
