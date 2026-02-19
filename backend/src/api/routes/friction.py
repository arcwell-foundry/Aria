"""Cognitive Friction API routes.

Provides endpoints for managing friction decisions — the mechanism by
which ARIA pushes back on user requests before execution.

Friction states are stored in the ``friction_decisions`` table when
available, falling back to an in-process cache otherwise.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.api.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/friction", tags=["friction"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

VALID_RESPONSES = {"approve", "modify", "cancel"}


class FrictionRespondRequest(BaseModel):
    """Request body for responding to a friction decision."""

    response: str

    @field_validator("response")
    @classmethod
    def validate_response(cls, v: str) -> str:
        if v not in VALID_RESPONSES:
            raise ValueError(f"Invalid response. Must be one of: {sorted(VALID_RESPONSES)}")
        return v


class FrictionItemResponse(BaseModel):
    """A single pending friction decision."""

    friction_id: str
    level: str
    reasoning: str
    user_message: str | None
    original_request: str
    created_at: str


# ---------------------------------------------------------------------------
# In-memory fallback cache (used when friction_decisions table is missing)
# ---------------------------------------------------------------------------

_friction_cache: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _store_friction(friction_id: str, user_id: str, data: dict[str, Any]) -> None:
    """Persist a friction decision to the database, falling back to cache."""
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        client.table("friction_decisions").insert({
            "id": friction_id,
            "user_id": user_id,
            "level": data["level"],
            "reasoning": data["reasoning"],
            "user_message": data.get("user_message"),
            "original_request": data.get("original_request", ""),
            "status": "pending",
            "created_at": data.get("created_at", datetime.now(timezone.utc).isoformat()),
        }).execute()
    except Exception:
        logger.debug(
            "friction_decisions table unavailable — using in-memory cache",
            exc_info=True,
        )
        _friction_cache[friction_id] = {**data, "user_id": user_id, "status": "pending"}


def _get_pending(user_id: str) -> list[dict[str, Any]]:
    """Retrieve pending friction decisions for a user."""
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        result = (
            client.table("friction_decisions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data if result and result.data else []
    except Exception:
        logger.debug(
            "friction_decisions table unavailable — reading from cache",
            exc_info=True,
        )
        return [
            {"friction_id": fid, **v}
            for fid, v in _friction_cache.items()
            if v.get("user_id") == user_id and v.get("status") == "pending"
        ]


def _resolve_friction(friction_id: str, user_id: str, response: str) -> dict[str, Any] | None:
    """Mark a friction decision as resolved and return its data."""
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        result = (
            client.table("friction_decisions")
            .select("*")
            .eq("id", friction_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None

        client.table("friction_decisions").update({
            "status": "resolved",
            "user_response": response,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", friction_id).execute()

        return result.data
    except Exception:
        logger.debug(
            "friction_decisions table unavailable — resolving from cache",
            exc_info=True,
        )
        entry = _friction_cache.get(friction_id)
        if entry is None or entry.get("user_id") != user_id:
            return None

        entry["status"] = "resolved"
        entry["user_response"] = response
        entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return entry


# ---------------------------------------------------------------------------
# Public helper — called by chat service to create a friction entry
# ---------------------------------------------------------------------------

def create_friction_entry(
    user_id: str,
    level: str,
    reasoning: str,
    user_message: str | None,
    original_request: str,
) -> str:
    """Create a new friction decision entry and return its ID.

    This is called from the chat/OODA pipeline when the Cognitive Friction
    Engine returns a non-comply decision.

    Args:
        user_id: The requesting user's ID.
        level: One of 'flag', 'challenge', 'refuse'.
        reasoning: Internal reasoning for audit.
        user_message: ARIA's pushback message shown to the user.
        original_request: The user's original request text.

    Returns:
        The friction_id for the new entry.
    """
    friction_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "level": level,
        "reasoning": reasoning,
        "user_message": user_message,
        "original_request": original_request,
        "created_at": now,
    }

    _store_friction(friction_id, user_id, data)
    logger.info(
        "Created friction entry %s for user %s (level=%s)",
        friction_id,
        user_id,
        level,
    )
    return friction_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/pending")
async def get_pending_friction(current_user: CurrentUser) -> list[FrictionItemResponse]:
    """Get all pending friction decisions for the current user."""
    rows = _get_pending(current_user.id)

    items: list[FrictionItemResponse] = []
    for row in rows:
        items.append(
            FrictionItemResponse(
                friction_id=row.get("friction_id") or row.get("id", ""),
                level=row.get("level", ""),
                reasoning=row.get("reasoning", ""),
                user_message=row.get("user_message"),
                original_request=row.get("original_request", ""),
                created_at=row.get("created_at", ""),
            )
        )

    return items


@router.post("/{friction_id}/respond")
async def respond_to_friction(
    friction_id: str,
    data: FrictionRespondRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Respond to a pending friction decision.

    Args:
        friction_id: The friction decision ID.
        data: The user's response (approve / modify / cancel).
        current_user: The authenticated user.

    Returns:
        Confirmation with the resolved friction state.
    """
    resolved = _resolve_friction(friction_id, current_user.id, data.response)

    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="Friction decision not found or already resolved",
        )

    logger.info(
        "Friction %s resolved by user %s with response=%s",
        friction_id,
        current_user.id,
        data.response,
    )

    return {
        "friction_id": friction_id,
        "response": data.response,
        "status": "resolved",
        "proceed": data.response == "approve",
    }
