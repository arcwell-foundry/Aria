"""API routes for US-940 Activity Feed / Command Center."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.activity import ActivityCreate
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])


def _get_service() -> ActivityService:
    return ActivityService()


@router.get("")
async def get_activity_feed(
    current_user: CurrentUser,
    agent: str | None = Query(None, description="Filter by agent"),
    activity_type: str | None = Query(None, description="Filter by type"),
    date_start: str | None = Query(None, description="ISO start date"),
    date_end: str | None = Query(None, description="ISO end date"),
    search: str | None = Query(None, description="Search title/description"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Get activity feed with pagination and filters."""
    service = _get_service()
    activities = await service.get_feed(
        user_id=current_user.id,
        agent=agent,
        activity_type=activity_type,
        date_start=date_start,
        date_end=date_end,
        search=search,
        limit=limit,
        offset=offset,
    )
    logger.info(
        "Activity feed requested",
        extra={"user_id": current_user.id, "count": len(activities)},
    )
    return {"activities": activities, "count": len(activities)}


@router.get("/agents")
async def get_agent_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current status of each ARIA agent."""
    service = _get_service()
    status = await service.get_agent_status(current_user.id)
    return {"agents": status}


@router.get("/{activity_id}")
async def get_activity_detail(
    activity_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a single activity with full reasoning chain."""
    service = _get_service()
    activity = await service.get_activity_detail(current_user.id, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("")
async def record_activity(
    current_user: CurrentUser,
    body: ActivityCreate,
) -> dict[str, Any]:
    """Record a new activity (internal use by agents)."""
    service = _get_service()
    result = await service.record(
        user_id=current_user.id,
        agent=body.agent,
        activity_type=body.activity_type,
        title=body.title,
        description=body.description,
        reasoning=body.reasoning,
        confidence=body.confidence,
        related_entity_type=body.related_entity_type,
        related_entity_id=body.related_entity_id,
        metadata=body.metadata,
    )
    return result
