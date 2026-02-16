"""Context gatherer for the Predictive Processing Engine.

Aggregates context from multiple sources (conversations, goals, meetings,
signals, leads, episodic memories) to inform prediction generation.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.intelligence.predictive.models import (
    EpisodicMemory,
    PredictionContext,
    RecentConversation,
    RecentLeadActivity,
    RecentSignal,
    UpcomingMeeting,
)

logger = logging.getLogger(__name__)


class PredictionContextGatherer:
    """Gathers context from multiple sources for prediction generation.

    Collects data in parallel from:
    - Recent conversations
    - Active goals
    - Upcoming meetings (next 48 hours)
    - Recent market signals (last 7 days)
    - Recent lead activity
    - Recent episodic memories

    Attributes:
        CONTEXT_CONVERSATION_LIMIT: Number of recent conversations to fetch
        CONTEXT_MEETING_HORIZON_HOURS: Hours ahead to look for meetings
        CONTEXT_SIGNAL_DAYS: Days back to look for signals
    """

    CONTEXT_CONVERSATION_LIMIT: int = 3
    CONTEXT_MEETING_HORIZON_HOURS: int = 48
    CONTEXT_SIGNAL_DAYS: int = 7
    CONTEXT_MEMORY_LIMIT: int = 5

    def __init__(self, db_client: Any, llm_client: Any | None = None) -> None:
        """Initialize the context gatherer.

        Args:
            db_client: Supabase client for database queries
            llm_client: Optional LLM client for summarization
        """
        self._db = db_client
        self._llm = llm_client

    async def gather(self, user_id: str) -> PredictionContext:
        """Gather all context for prediction generation.

        Fetches data from all sources in parallel for efficiency.

        Args:
            user_id: User ID to gather context for

        Returns:
            PredictionContext with all gathered data
        """
        logger.info("Gathering prediction context", extra={"user_id": user_id})

        # Gather all context sources in parallel
        conversations_task = self._get_recent_conversations(user_id)
        goals_task = self._get_active_goals(user_id)
        meetings_task = self._get_upcoming_meetings(user_id)
        signals_task = self._get_recent_signals(user_id)
        lead_activity_task = self._get_recent_lead_activity(user_id)
        episodic_task = self._get_recent_episodic_memories(user_id)

        (
            conversations,
            goals,
            meetings,
            signals,
            lead_activity,
            episodic,
        ) = await asyncio.gather(
            conversations_task,
            goals_task,
            meetings_task,
            signals_task,
            lead_activity_task,
            episodic_task,
        )

        context = PredictionContext(
            recent_conversations=conversations,
            active_goals=goals,
            upcoming_meetings=meetings,
            recent_market_signals=signals,
            recent_lead_activity=lead_activity,
            recent_episodic_memories=episodic,
        )

        logger.info(
            "Prediction context gathered",
            extra={
                "user_id": user_id,
                "conversations": len(conversations),
                "goals": len(goals),
                "meetings": len(meetings),
                "signals": len(signals),
                "lead_activities": len(lead_activity),
                "memories": len(episodic),
            },
        )

        return context

    async def _get_recent_conversations(self, user_id: str) -> list[RecentConversation]:
        """Get recent conversations for the user.

        Args:
            user_id: User ID

        Returns:
            List of recent conversation summaries
        """
        try:
            result = (
                self._db.table("conversations")
                .select("id, summary, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(self.CONTEXT_CONVERSATION_LIMIT)
                .execute()
            )

            conversations = []
            for row in result.data or []:
                # Extract topics and entities if available
                topics: list[str] = []
                entities: list[str] = []

                # Try to get more details from messages
                messages_result = (
                    self._db.table("messages")
                    .select("content")
                    .eq("conversation_id", row["id"])
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )

                if messages_result.data:
                    # Simple entity/topic extraction from messages
                    content = " ".join(
                        m["content"] for m in messages_result.data if m.get("content")
                    )
                    # Extract potential entities (capitalized words)
                    words = content.split()
                    entities = list(
                        {w.strip(".,!?;:") for w in words if w and w[0].isupper() and len(w) > 2}
                    )[:10]

                conversations.append(
                    RecentConversation(
                        id=row["id"],
                        summary=row.get("summary", "Recent conversation"),
                        topics=topics,
                        entities=entities,
                        created_at=row.get("created_at"),
                    )
                )

            return conversations

        except Exception as e:
            logger.warning(
                "Failed to get recent conversations",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_active_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Get active goals for the user.

        Args:
            user_id: User ID

        Returns:
            List of active goal dictionaries
        """
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description, status, priority, target_date")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("priority", desc=True)
                .limit(10)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.warning(
                "Failed to get active goals",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_upcoming_meetings(self, user_id: str) -> list[UpcomingMeeting]:
        """Get upcoming meetings within the horizon.

        Args:
            user_id: User ID

        Returns:
            List of upcoming meetings
        """
        try:
            now = datetime.now(UTC)
            horizon = now + timedelta(hours=self.CONTEXT_MEETING_HORIZON_HOURS)

            result = (
                self._db.table("calendar_events")
                .select("id, title, start_time, attendees, related_goal_id")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", horizon.isoformat())
                .order("start_time")
                .limit(10)
                .execute()
            )

            meetings = []
            for row in result.data or []:
                meetings.append(
                    UpcomingMeeting(
                        id=row["id"],
                        title=row.get("title", "Untitled meeting"),
                        start_time=datetime.fromisoformat(row["start_time"])
                        if row.get("start_time")
                        else now,
                        attendees=row.get("attendees") or [],
                        related_goal_id=row.get("related_goal_id"),
                    )
                )

            return meetings

        except Exception as e:
            logger.warning(
                "Failed to get upcoming meetings",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_recent_signals(self, user_id: str) -> list[RecentSignal]:
        """Get recent market signals.

        Args:
            user_id: User ID

        Returns:
            List of recent signals
        """
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.CONTEXT_SIGNAL_DAYS)

            result = (
                self._db.table("market_signals")
                .select("id, signal_type, summary, relevance_score, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff.isoformat())
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )

            signals = []
            for row in result.data or []:
                # Extract entities from summary
                entities: list[str] = []
                summary = row.get("summary", "")
                if summary:
                    words = summary.split()
                    entities = [
                        w.strip(".,!?;:") for w in words if w and w[0].isupper() and len(w) > 2
                    ][:5]

                signals.append(
                    RecentSignal(
                        id=row["id"],
                        signal_type=row.get("signal_type", "unknown"),
                        content=summary,
                        entities=entities,
                        relevance_score=row.get("relevance_score", 0.5),
                        created_at=row.get("created_at"),
                    )
                )

            return signals

        except Exception as e:
            logger.warning(
                "Failed to get recent signals",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_recent_lead_activity(self, user_id: str) -> list[RecentLeadActivity]:
        """Get recent lead activity.

        Args:
            user_id: User ID

        Returns:
            List of recent lead activities
        """
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.CONTEXT_SIGNAL_DAYS)

            # Get recent lead activities from lead_activities table if it exists
            # Otherwise fall back to checking leads table for recent updates
            result = (
                self._db.table("leads")
                .select("id, company_name, lifecycle_stage, updated_at")
                .eq("user_id", user_id)
                .gte("updated_at", cutoff.isoformat())
                .order("updated_at", desc=True)
                .limit(10)
                .execute()
            )

            activities = []
            for row in result.data or []:
                activities.append(
                    RecentLeadActivity(
                        lead_id=row["id"],
                        lead_name=row.get("company_name", "Unknown"),
                        activity_type="status_change",
                        activity_description=f"Lead status: {row.get('lifecycle_stage', 'unknown')}",
                        created_at=row.get("updated_at"),
                    )
                )

            return activities

        except Exception as e:
            logger.warning(
                "Failed to get recent lead activity",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_recent_episodic_memories(self, user_id: str) -> list[EpisodicMemory]:
        """Get recent episodic memories.

        Args:
            user_id: User ID

        Returns:
            List of recent episodic memories
        """
        try:
            cutoff = datetime.now(UTC) - timedelta(days=self.CONTEXT_SIGNAL_DAYS)

            result = (
                self._db.table("memory_episodic")
                .select("id, content, importance, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff.isoformat())
                .order("importance", desc=True)
                .limit(self.CONTEXT_MEMORY_LIMIT)
                .execute()
            )

            memories = []
            for row in result.data or []:
                # Extract entities from content
                entities: list[str] = []
                content = row.get("content", "")
                if content:
                    words = str(content).split()
                    entities = [
                        w.strip(".,!?;:") for w in words if w and w[0].isupper() and len(w) > 2
                    ][:5]

                memories.append(
                    EpisodicMemory(
                        id=row["id"],
                        content=content[:500] if content else "",
                        entities=entities,
                        importance=row.get("importance", 0.5),
                        created_at=row.get("created_at"),
                    )
                )

            return memories

        except Exception as e:
            logger.warning(
                "Failed to get recent episodic memories",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []
