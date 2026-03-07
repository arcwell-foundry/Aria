"""Watch Topics API routes.

Endpoints for managing user-defined monitoring topics.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence/watch-topics", tags=["intelligence"])


class WatchTopicCreate(BaseModel):
    """Request model for creating a watch topic."""

    topic_type: str = Field(..., description="Type: keyword, company, therapeutic_area")
    topic_value: str = Field(..., min_length=2, max_length=200, description="Topic to watch")
    description: str | None = Field(None, max_length=500, description="Why to watch this")


class WatchTopicResponse(BaseModel):
    """Response model for a watch topic."""

    id: str
    topic_type: str
    topic_value: str
    description: str | None = None
    keywords: list[str] = []
    signal_count: int = 0
    is_active: bool = True
    last_matched_at: str | None = None
    created_at: str | None = None


class WatchTopicCreateResponse(BaseModel):
    """Response model for creating a watch topic."""

    topic: dict[str, Any] | None = None
    retroactive_matches: int = 0


@router.post("", response_model=WatchTopicCreateResponse)
async def add_watch_topic(
    data: WatchTopicCreate,
    current_user: CurrentUser,
) -> WatchTopicCreateResponse:
    """Add a new watch topic.

    Creates a monitoring topic and retroactively matches against existing signals.
    """
    from src.intelligence.watch_topics_service import WatchTopicsService

    db = SupabaseClient.get_client()
    service = WatchTopicsService(db)

    try:
        result = await service.add_topic(
            user_id=str(current_user.id),
            topic_type=data.topic_type,
            topic_value=data.topic_value,
            description=data.description,
        )

        logger.info(
            "Watch topic created",
            extra={
                "user_id": current_user.id,
                "topic_value": data.topic_value,
                "retroactive_matches": result.get("retroactive_matches", 0),
            },
        )

        return WatchTopicCreateResponse(
            topic=result.get("topic"),
            retroactive_matches=result.get("retroactive_matches", 0),
        )
    except Exception as e:
        logger.exception("Failed to create watch topic")
        raise HTTPException(status_code=500, detail="Failed to create watch topic") from e


@router.get("", response_model=list[WatchTopicResponse])
async def list_watch_topics(
    current_user: CurrentUser,
) -> list[WatchTopicResponse]:
    """List user's watch topics."""
    from src.intelligence.watch_topics_service import WatchTopicsService

    db = SupabaseClient.get_client()
    service = WatchTopicsService(db)

    topics = await service.get_topics(user_id=str(current_user.id))

    return [
        WatchTopicResponse(
            id=t["id"],
            topic_type=t.get("topic_type", "keyword"),
            topic_value=t.get("topic_value", ""),
            description=t.get("description"),
            keywords=t.get("keywords") or [],
            signal_count=t.get("signal_count", 0),
            is_active=t.get("is_active", True),
            last_matched_at=t.get("last_matched_at"),
            created_at=t.get("created_at"),
        )
        for t in topics
    ]


@router.delete("/{topic_id}")
async def remove_watch_topic(
    topic_id: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Remove (deactivate) a watch topic."""
    from src.intelligence.watch_topics_service import WatchTopicsService

    db = SupabaseClient.get_client()
    service = WatchTopicsService(db)

    success = await service.remove_topic(
        user_id=str(current_user.id),
        topic_id=topic_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Watch topic not found")

    logger.info(
        "Watch topic removed",
        extra={"user_id": current_user.id, "topic_id": topic_id},
    )

    return {"status": "removed"}
