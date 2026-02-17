"""API routes for activity feed, polling, and stats."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.activity import ActivityCreate
from src.services.activity_feed_service import ActivityFeedService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])

VALID_PERIODS = {"1d", "7d", "30d", "day", "week", "month"}


def _get_service() -> ActivityFeedService:
    """Get ActivityFeedService instance."""
    return ActivityFeedService()


@router.get("")
async def get_activity_feed(
    current_user: CurrentUser,
    type: str | None = Query(None, description="Filter by activity type"),
    agent: str | None = Query(None, description="Filter by agent"),
    entity_type: str | None = Query(None, description="Filter by related entity type"),
    entity_id: str | None = Query(None, description="Filter by related entity ID"),
    since: str | None = Query(None, description="ISO timestamp lower bound"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
) -> dict[str, Any]:
    """Get paginated activity feed with filters.

    Args:
        current_user: Authenticated user.
        type: Filter by activity_type.
        agent: Filter by agent name.
        entity_type: Filter by related_entity_type (lead, goal, contact, company).
        entity_id: Filter by related_entity_id UUID.
        since: ISO datetime lower bound for created_at.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        Dict with items, total, page.
    """
    filters: dict[str, str] = {}
    if type:
        filters["activity_type"] = type
    if agent:
        filters["agent"] = agent
    if entity_type:
        filters["related_entity_type"] = entity_type
    if entity_id:
        filters["related_entity_id"] = entity_id
    if since:
        filters["date_start"] = since

    service = _get_service()
    try:
        result = await service.get_activity_feed(
            user_id=current_user.id,
            filters=filters,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("Failed to fetch activity feed")
        raise HTTPException(status_code=500, detail="Failed to fetch activity feed")

    logger.info(
        "Activity feed requested",
        extra={
            "user_id": current_user.id,
            "count": result["total_count"],
            "page": page,
        },
    )

    return {
        "items": result["activities"],
        "total": result["total_count"],
        "page": result["page"],
    }


@router.get("/poll")
async def poll_activity(
    current_user: CurrentUser,
    since: str = Query(..., description="ISO timestamp; returns activities after this"),
) -> dict[str, Any]:
    """Poll for new activities since a timestamp.

    Lightweight endpoint designed for frequent polling (every ~10s).

    Args:
        current_user: Authenticated user.
        since: ISO timestamp; only activities created after this are returned.

    Returns:
        Dict with items list and count.
    """
    service = _get_service()
    try:
        activities = await service.get_real_time_updates(
            user_id=current_user.id,
            since_timestamp=since,
        )
    except Exception:
        logger.exception("Failed to poll activity")
        raise HTTPException(status_code=500, detail="Failed to poll activity")

    return {"items": activities, "count": len(activities)}


@router.get("/stats")
async def get_activity_stats(
    current_user: CurrentUser,
    period: str = Query("7d", description="Period: 1d, 7d, 30d, day, week, month"),
) -> dict[str, Any]:
    """Get activity summary stats for a period.

    Args:
        current_user: Authenticated user.
        period: One of 1d, 7d, 30d, day, week, month.

    Returns:
        Dict with total, by_type, by_agent, period, since.
    """
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Must be one of: {', '.join(sorted(VALID_PERIODS))}",
        )

    service = _get_service()
    try:
        stats = await service.get_activity_stats(
            user_id=current_user.id,
            period=period,
        )
    except Exception:
        logger.exception("Failed to fetch activity stats")
        raise HTTPException(status_code=500, detail="Failed to fetch activity stats")

    return stats


@router.get("/{activity_id}")
async def get_activity_detail(
    activity_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a single activity with full reasoning chain."""
    from src.services.activity_service import ActivityService

    service = ActivityService()
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
    try:
        result = await service.create_activity(
            user_id=current_user.id,
            activity_type=body.activity_type,
            title=body.title,
            description=body.description,
            agent=body.agent,
            reasoning=body.reasoning,
            confidence=body.confidence,
            related_entity_type=body.related_entity_type,
            related_entity_id=body.related_entity_id,
            metadata=body.metadata,
        )
    except Exception:
        logger.exception("Failed to record activity")
        raise HTTPException(status_code=500, detail="Failed to record activity")

    return result
