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


# ---------------------------------------------------------------------------
# New models for topic stats, session events, and engagement history
# ---------------------------------------------------------------------------


class TopicStat(BaseModel):
    """Statistics for a single topic from perception analysis."""

    topic: str
    confusion_count: int = 0
    disengagement_count: int = 0
    total_mentions: int = 0
    confusion_rate: float = 0.0
    last_confused_at: str | None = None
    last_disengaged_at: str | None = None


class SessionPerceptionEvents(BaseModel):
    """Perception events for a specific video session."""

    session_id: str
    events: list[dict] = Field(default_factory=list)
    total_events: int = 0


class EngagementHistoryEntry(BaseModel):
    """A single entry in the user's engagement history."""

    session_id: str
    engagement_score: float | None = None
    confusion_events: int = 0
    disengagement_events: int = 0
    engagement_trend: str | None = None
    session_date: str | None = None
    duration_seconds: int | None = None


# ---------------------------------------------------------------------------
# New endpoints: topic-stats, session events, engagement-history
# ---------------------------------------------------------------------------


@router.get("/topic-stats", response_model=list[TopicStat])
async def get_topic_stats(
    current_user: CurrentUser,
) -> list[TopicStat]:
    """Get topic-level perception statistics for the current user.

    Queries perception_topic_stats ordered by confusion_count descending,
    calculates confusion_rate as confusion_count / total_mentions.

    Args:
        current_user: The authenticated user.

    Returns:
        List of TopicStat entries, up to 50 topics.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("perception_topic_stats")
            .select("*")
            .eq("user_id", current_user.id)
            .order("confusion_count", desc=True)
            .limit(50)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch topic stats",
            extra={"user_id": current_user.id},
        )
        return []

    stats: list[TopicStat] = []
    for row in result.data or []:
        total = row.get("total_mentions", 0)
        confusion = row.get("confusion_count", 0)
        confusion_rate = confusion / total if total > 0 else 0.0

        stats.append(
            TopicStat(
                topic=row.get("topic", ""),
                confusion_count=confusion,
                disengagement_count=row.get("disengagement_count", 0),
                total_mentions=total,
                confusion_rate=round(confusion_rate, 4),
                last_confused_at=row.get("last_confused_at"),
                last_disengaged_at=row.get("last_disengaged_at"),
            )
        )

    return stats


@router.get("/session/{session_id}/events", response_model=SessionPerceptionEvents)
async def get_session_events(
    session_id: str,
    current_user: CurrentUser,
) -> SessionPerceptionEvents:
    """Get perception events for a specific video session.

    Queries video_sessions by id and user_id (auth check). Returns the
    perception_events array stored on the session.

    Args:
        session_id: The video session ID.
        current_user: The authenticated user.

    Returns:
        SessionPerceptionEvents with the events list and count.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("video_sessions")
            .select("id, perception_events")
            .eq("id", session_id)
            .eq("user_id", current_user.id)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch session events",
            extra={"user_id": current_user.id, "session_id": session_id},
        )
        return SessionPerceptionEvents(session_id=session_id)

    if not result.data:
        return SessionPerceptionEvents(session_id=session_id)

    row = result.data[0]
    events = row.get("perception_events") or []

    return SessionPerceptionEvents(
        session_id=session_id,
        events=events,
        total_events=len(events),
    )


@router.get("/engagement-history", response_model=list[EngagementHistoryEntry])
async def get_engagement_history(
    current_user: CurrentUser,
    limit: int = 10,
) -> list[EngagementHistoryEntry]:
    """Get engagement history from completed video sessions.

    Queries video_sessions where status='ended' for the current user,
    extracts engagement metrics from the perception_analysis JSONB column.

    Args:
        current_user: The authenticated user.
        limit: Number of sessions to return (max 50, default 10).

    Returns:
        List of EngagementHistoryEntry ordered by most recent first.
    """
    capped_limit = min(limit, 50)
    db = get_supabase_client()

    try:
        result = (
            db.table("video_sessions")
            .select("id, perception_analysis, created_at, duration_seconds")
            .eq("user_id", current_user.id)
            .eq("status", "ended")
            .order("created_at", desc=True)
            .limit(capped_limit)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch engagement history",
            extra={"user_id": current_user.id},
        )
        return []

    entries: list[EngagementHistoryEntry] = []
    for row in result.data or []:
        analysis = row.get("perception_analysis") or {}

        entries.append(
            EngagementHistoryEntry(
                session_id=row.get("id", ""),
                engagement_score=analysis.get("engagement_score"),
                confusion_events=analysis.get("confusion_events", 0),
                disengagement_events=analysis.get("disengagement_events", 0),
                engagement_trend=analysis.get("engagement_trend"),
                session_date=row.get("created_at"),
                duration_seconds=row.get("duration_seconds"),
            )
        )

    return entries
