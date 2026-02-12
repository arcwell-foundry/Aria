"""Meeting debrief API routes for ARIA.

This module provides endpoints for:
- Creating and querying meeting debriefs
- Managing post-meeting insights and action items
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.debrief_service import DebriefService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debriefs", tags=["debriefs"])


def _get_service() -> DebriefService:
    """Get debrief service instance."""
    return DebriefService()


class DebriefCreate(BaseModel):
    """Request model for creating a debrief."""

    meeting_id: str = Field(
        ..., min_length=1, max_length=100, description="The meeting's unique identifier"
    )
    notes: str = Field(..., min_length=1, max_length=10000, description="User's debrief notes")
    meeting_context: dict[str, Any] | None = Field(
        None, description="Optional meeting context (title, attendees, etc)"
    )


class DebriefResponse(BaseModel):
    """Response model for a debrief."""

    id: str
    user_id: str
    meeting_id: str
    meeting_title: str | None
    meeting_time: str | None
    raw_notes: str
    summary: str
    outcome: str
    action_items: list[dict[str, Any]]
    commitments_ours: list[str]
    commitments_theirs: list[str]
    insights: list[dict[str, Any]]
    follow_up_needed: bool
    follow_up_draft: str | None
    linked_lead_id: str | None
    created_at: str


# Debrief Endpoints


@router.post("")
async def create_debrief(
    data: DebriefCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create a new meeting debrief.

    Processes user's debrief notes and extracts structured data including
    action items, commitments, and insights.

    Args:
        data: Debrief creation request.
        current_user: The authenticated user.

    Returns:
        Created debrief data.
    """
    service = _get_service()
    result = await service.create_debrief(
        user_id=current_user.id,
        meeting_id=data.meeting_id,
        user_notes=data.notes,
        meeting_context=data.meeting_context,
    )

    logger.info(
        "Debrief created",
        extra={
            "user_id": current_user.id,
            "meeting_id": data.meeting_id,
            "debrief_id": result["id"],
        },
    )

    return result


@router.get("")
async def list_debriefs(
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of debriefs to return"),
) -> list[dict[str, Any]]:
    """List recent debriefs.

    Returns a list of the user's most recent meeting debriefs.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of debriefs to return.

    Returns:
        List of recent debrief data.
    """
    service = _get_service()
    debriefs = await service.list_recent_debriefs(current_user.id, limit)

    logger.info(
        "Debriefs listed",
        extra={
            "user_id": current_user.id,
            "count": len(debriefs),
        },
    )

    return debriefs


@router.get("/{debrief_id}")
async def get_debrief(
    debrief_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a specific debrief.

    Returns detailed information about a specific meeting debrief.

    Args:
        debrief_id: The debrief's UUID.
        current_user: The authenticated user.

    Returns:
        Debrief data.

    Raises:
        HTTPException: If debrief not found.
    """
    service = _get_service()
    result = await service.get_debrief(current_user.id, debrief_id)

    if result is None:
        logger.warning(
            "Debrief not found",
            extra={
                "user_id": current_user.id,
                "debrief_id": debrief_id,
            },
        )
        raise HTTPException(status_code=404, detail="Debrief not found")

    logger.info(
        "Debrief retrieved",
        extra={
            "user_id": current_user.id,
            "debrief_id": debrief_id,
        },
    )

    return result


@router.get("/meeting/{meeting_id}")
async def get_debriefs_for_meeting(
    meeting_id: str,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get all debriefs for a specific meeting.

    Returns all debriefs associated with a given meeting.

    Args:
        meeting_id: The meeting's unique identifier.
        current_user: The authenticated user.

    Returns:
        List of debrief data for the meeting.
    """
    service = _get_service()
    debriefs = await service.get_debriefs_for_meeting(current_user.id, meeting_id)

    logger.info(
        "Meeting debriefs retrieved",
        extra={
            "user_id": current_user.id,
            "meeting_id": meeting_id,
            "count": len(debriefs),
        },
    )

    return debriefs
