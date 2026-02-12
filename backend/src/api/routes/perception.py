"""Perception API routes for Raven-0 emotion detection and engagement tracking."""

import logging
from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/perception", tags=["perception"])


class EmotionEvent(BaseModel):
    """A single emotion detection event from Raven-0."""

    emotion: str = Field(
        ...,
        description="Detected emotion label (neutral, engaged, frustrated, etc.)",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    timestamp: str | None = Field(default=None, description="ISO timestamp of the detection")


class EmotionResponse(BaseModel):
    """Response after processing an emotion event."""

    stored: bool
    engagement_hint: str | None = None


class EngagementSummary(BaseModel):
    """Summary of user engagement patterns."""

    engagement_level: str
    dominant_emotion: str | None = None
    reading_count: int = 0
    period_start: str | None = None
    period_end: str | None = None


@router.post("/emotion", response_model=EmotionResponse)
async def record_emotion(
    current_user: CurrentUser,
    event: EmotionEvent,
) -> EmotionResponse:
    """Record a Raven-0 emotion detection event.

    Stores the reading in procedural_patterns for long-term engagement
    analysis. Returns an optional hint the frontend can use to adjust
    ARIA's response style.

    Args:
        current_user: The authenticated user.
        event: The emotion detection event.

    Returns:
        Storage confirmation and optional engagement hint.
    """
    now = event.timestamp or datetime.now(UTC).isoformat()

    db = get_supabase_client()

    try:
        db.table("procedural_patterns").insert(
            {
                "user_id": current_user.id,
                "pattern_type": "emotion_detection",
                "pattern_data": {
                    "emotion": event.emotion,
                    "confidence": event.confidence,
                    "source": "raven_0",
                },
                "created_at": now,
            }
        ).execute()
    except Exception:
        logger.exception(
            "Failed to store emotion event",
            extra={"user_id": current_user.id, "emotion": event.emotion},
        )
        return EmotionResponse(stored=False)

    engagement_hint = None
    if event.emotion in ("frustrated", "confused"):
        engagement_hint = "concise"
    elif event.emotion in ("excited", "engaged"):
        engagement_hint = "elaborate"
    elif event.emotion == "distracted":
        engagement_hint = "re-engage"

    logger.info(
        "Emotion recorded",
        extra={
            "user_id": current_user.id,
            "emotion": event.emotion,
            "confidence": event.confidence,
            "hint": engagement_hint,
        },
    )

    return EmotionResponse(stored=True, engagement_hint=engagement_hint)


@router.get("/engagement", response_model=EngagementSummary)
async def get_engagement_summary(
    current_user: CurrentUser,
) -> EngagementSummary:
    """Get a summary of the user's recent engagement patterns.

    Aggregates the last 20 emotion readings to determine overall
    engagement level.

    Args:
        current_user: The authenticated user.

    Returns:
        Engagement summary with dominant emotion and level.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("procedural_patterns")
            .select("pattern_data, created_at")
            .eq("user_id", current_user.id)
            .eq("pattern_type", "emotion_detection")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch engagement data",
            extra={"user_id": current_user.id},
        )
        return EngagementSummary(engagement_level="unknown")

    if not result.data:
        return EngagementSummary(engagement_level="unknown", reading_count=0)

    readings = result.data
    emotions = [r["pattern_data"]["emotion"] for r in readings]

    engaged_emotions = {"engaged", "focused", "excited"}
    engaged_count = sum(1 for e in emotions if e in engaged_emotions)

    if len(emotions) < 3:
        level = "unknown"
    elif engaged_count / len(emotions) >= 0.7:
        level = "high"
    elif engaged_count / len(emotions) >= 0.4:
        level = "medium"
    else:
        level = "low"

    emotion_counts = Counter(emotions)
    dominant = emotion_counts.most_common(1)[0][0] if emotion_counts else None

    return EngagementSummary(
        engagement_level=level,
        dominant_emotion=dominant,
        reading_count=len(readings),
        period_start=readings[-1]["created_at"] if readings else None,
        period_end=readings[0]["created_at"] if readings else None,
    )
