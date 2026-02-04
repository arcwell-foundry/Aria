"""Proactive Memory Service for ARIA.

This service finds and surfaces relevant memories to volunteer
to users based on current conversation context. Key responsibilities:

- Calculate relevance scores combining topic overlap and salience
- Apply cooldown filtering to avoid surfacing same insights repeatedly
- Record surfaced insights for analytics and cooldown tracking
- Track engagement to improve future relevance scoring
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.models.proactive_insight import ProactiveInsight

logger = logging.getLogger(__name__)


class ProactiveMemoryService:
    """Service for proactive memory surfacing.

    Finds memories worth volunteering to the user based on:
    - Topic overlap with current conversation
    - Memory salience (importance/recency)
    - Cooldown periods (avoid repeating same insights)
    - Engagement history (learn what user finds valuable)

    Attributes:
        SURFACING_THRESHOLD: Minimum relevance score to surface (0.0-1.0)
        MAX_INSIGHTS_PER_RESPONSE: Maximum insights to return per request
        COOLDOWN_HOURS: Hours before same memory can be surfaced again
    """

    SURFACING_THRESHOLD: float = 0.6
    MAX_INSIGHTS_PER_RESPONSE: int = 2
    COOLDOWN_HOURS: int = 24

    def __init__(self, db_client: Any) -> None:
        """Initialize the proactive memory service.

        Args:
            db_client: Supabase client for database operations
        """
        self._db = db_client

    def _calculate_base_relevance(
        self,
        topic_overlap: float,
        salience: float,
    ) -> float:
        """Calculate base relevance score from topic overlap and salience.

        The formula multiplies topic overlap by salience, meaning:
        - High overlap + high salience = high relevance
        - High overlap + low salience = moderate relevance
        - Low overlap = low relevance regardless of salience

        Args:
            topic_overlap: How much the memory relates to current topic (0.0-1.0)
            salience: Memory importance/recency score (0.0-1.0)

        Returns:
            Base relevance score between 0.0 and 1.0
        """
        return topic_overlap * salience

    async def _filter_by_cooldown(
        self,
        user_id: str,
        insights: list[ProactiveInsight],
    ) -> list[ProactiveInsight]:
        """Filter out insights that were recently surfaced.

        Queries the surfaced_insights table to find memories that have
        been shown to this user within the cooldown period.

        Args:
            user_id: User identifier
            insights: List of candidate insights

        Returns:
            Filtered list with recently surfaced insights removed
        """
        if not insights:
            return []

        # Calculate cutoff time
        cutoff = datetime.now(UTC) - timedelta(hours=self.COOLDOWN_HOURS)
        cutoff_iso = cutoff.isoformat()

        try:
            # Get recently surfaced memory IDs
            result = (
                self._db.table("surfaced_insights")
                .select("memory_id")
                .eq("user_id", user_id)
                .gte("surfaced_at", cutoff_iso)
                .execute()
            )

            recent_ids = {row["memory_id"] for row in (result.data or [])}

            # Filter out insights whose source memory was recently surfaced
            filtered = [
                insight for insight in insights if insight.source_memory_id not in recent_ids
            ]

            return filtered

        except Exception as e:
            logger.warning("Failed to check cooldown, returning all insights: %s", e)
            return insights

    def _filter_by_threshold(
        self,
        insights: list[ProactiveInsight],
    ) -> list[ProactiveInsight]:
        """Filter insights below the surfacing threshold.

        Args:
            insights: List of candidate insights

        Returns:
            Filtered list with only insights at or above threshold
        """
        return [
            insight for insight in insights if insight.relevance_score >= self.SURFACING_THRESHOLD
        ]

    async def record_surfaced(
        self,
        user_id: str,
        insight: ProactiveInsight,
        context: str,
    ) -> str | None:
        """Record that an insight was surfaced to the user.

        Creates a record in surfaced_insights for cooldown tracking
        and analytics purposes.

        Args:
            user_id: User identifier
            insight: The insight that was surfaced
            context: Context in which it was surfaced (e.g., conversation topic)

        Returns:
            ID of the created record, or None if insert failed
        """
        try:
            result = (
                self._db.table("surfaced_insights")
                .insert(
                    {
                        "user_id": user_id,
                        "memory_type": insight.source_memory_type,
                        "memory_id": insight.source_memory_id,
                        "insight_type": insight.insight_type.value,
                        "context": context,
                        "relevance_score": insight.relevance_score,
                        "explanation": insight.explanation,
                        "engaged": False,
                        "dismissed": False,
                    }
                )
                .execute()
            )

            if result.data:
                logger.debug(
                    "Recorded surfaced insight %s for user %s",
                    insight.source_memory_id,
                    user_id,
                )
                record_id: str | None = result.data[0].get("id")
                return record_id

            return None

        except Exception as e:
            logger.error("Failed to record surfaced insight: %s", e)
            return None

    async def record_engagement(
        self,
        insight_id: str,
        engaged: bool,
    ) -> None:
        """Record user engagement with a surfaced insight.

        Updates the surfaced_insights record to track whether
        the user engaged with or dismissed the insight.

        Args:
            insight_id: ID of the surfaced_insights record
            engaged: True if user engaged, False if dismissed
        """
        try:
            update_data: dict[str, Any] = {}

            if engaged:
                update_data["engaged"] = True
                update_data["engaged_at"] = datetime.now(UTC).isoformat()
            else:
                update_data["dismissed"] = True
                update_data["dismissed_at"] = datetime.now(UTC).isoformat()

            self._db.table("surfaced_insights").update(update_data).eq("id", insight_id).execute()

            logger.debug(
                "Recorded engagement for insight %s: engaged=%s",
                insight_id,
                engaged,
            )

        except Exception as e:
            logger.warning("Failed to record engagement: %s", e)

    async def find_volunteerable_context(
        self,
        user_id: str,
        current_message: str,
        conversation_messages: list[dict[str, Any]],
    ) -> list[ProactiveInsight]:
        """Find memories worth volunteering to the user.

        Searches across memory types for relevant context to surface:
        - Pattern matches: Same topics discussed in past
        - Temporal triggers: Upcoming deadlines, anniversaries
        - Goal relevance: Relates to active user goals

        Args:
            user_id: User identifier
            current_message: The current user message
            conversation_messages: Recent conversation history

        Returns:
            List of insights to volunteer, limited to MAX_INSIGHTS_PER_RESPONSE
        """
        # Gather candidates from all finder methods
        candidates: list[ProactiveInsight] = []

        # Pattern matches (placeholder - returns [])
        pattern_matches = self._find_pattern_matches(
            user_id=user_id,
            current_message=current_message,
            conversation_messages=conversation_messages,
        )
        candidates.extend(pattern_matches)

        # Temporal triggers (placeholder - returns [])
        temporal_triggers = self._find_temporal_triggers(user_id=user_id)
        candidates.extend(temporal_triggers)

        # Goal relevance (placeholder - returns [])
        goal_relevant = self._find_goal_relevant(
            user_id=user_id,
            current_message=current_message,
        )
        candidates.extend(goal_relevant)

        # Apply threshold filter
        above_threshold = self._filter_by_threshold(candidates)

        # Apply cooldown filter
        not_recently_shown = await self._filter_by_cooldown(
            user_id=user_id,
            insights=above_threshold,
        )

        # Sort by relevance and limit
        sorted_insights = sorted(
            not_recently_shown,
            key=lambda x: x.relevance_score,
            reverse=True,
        )

        return sorted_insights[: self.MAX_INSIGHTS_PER_RESPONSE]

    def _find_pattern_matches(
        self,
        user_id: str,
        current_message: str,
        conversation_messages: list[dict[str, Any]],
    ) -> list[ProactiveInsight]:
        """Find memories with topic pattern matches.

        Placeholder implementation - will be enhanced in future tasks
        to query Graphiti for episodic/semantic memories matching
        current conversation topics.

        Args:
            user_id: User identifier
            current_message: The current user message
            conversation_messages: Recent conversation history

        Returns:
            List of pattern-matched insights (currently empty)
        """
        # TODO: Implement Graphiti integration to query episodic/semantic memories
        # matching current conversation topics (Phase 8 AGI Companion)
        _ = user_id, current_message, conversation_messages
        return []

    def _find_temporal_triggers(
        self,
        user_id: str,
    ) -> list[ProactiveInsight]:
        """Find time-based triggers (deadlines, follow-ups).

        Checks prospective memory for upcoming tasks within
        the next 3 days.

        Args:
            user_id: User identifier

        Returns:
            List of temporal trigger insights
        """
        from src.models.proactive_insight import InsightType

        insights: list[ProactiveInsight] = []

        try:
            now = datetime.now(UTC)
            three_days = now + timedelta(days=3)

            result = (
                self._db.table("prospective_tasks")
                .select("id, task, description, trigger_config, status, priority")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

            for task in result.data or []:
                # Check trigger_config for trigger_date
                trigger_config = task.get("trigger_config", {})
                trigger_date_str = trigger_config.get("trigger_date")

                if not trigger_date_str:
                    continue

                try:
                    trigger_date = datetime.fromisoformat(
                        trigger_date_str.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    continue

                if now <= trigger_date <= three_days:
                    days_until = (trigger_date - now).days
                    # Higher urgency = higher score
                    urgency = 1.0 - (days_until / 3.0)

                    insights.append(
                        ProactiveInsight(
                            insight_type=InsightType.TEMPORAL,
                            content=task.get("task", "Upcoming task"),
                            relevance_score=max(0.6, urgency),
                            source_memory_id=task["id"],
                            source_memory_type="prospective",
                            explanation=f"Due in {days_until} day(s)"
                            if days_until > 0
                            else "Due today",
                        )
                    )

        except Exception as e:
            logger.warning("Failed to find temporal triggers: %s", e)

        return insights

    def _find_goal_relevant(
        self,
        user_id: str,
        current_message: str,
    ) -> list[ProactiveInsight]:
        """Find memories relevant to active user goals.

        Placeholder implementation - will be enhanced to:
        - Query active goals for the user
        - Find memories that could help achieve those goals
        - Surface when conversation touches on goal topics

        Args:
            user_id: User identifier
            current_message: The current user message

        Returns:
            List of goal-relevant insights (currently empty)
        """
        # TODO: Implement goal relevance matching - query active goals and
        # find memories that could help achieve them (Phase 8 AGI Companion)
        _ = user_id, current_message
        return []

    async def get_surfaced_history(
        self,
        user_id: str,
        limit: int = 20,
        engaged_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Get history of surfaced insights for a user.

        Useful for analytics and understanding what insights
        resonate with the user.

        Args:
            user_id: User identifier
            limit: Maximum number of records to return
            engaged_only: If True, only return insights user engaged with

        Returns:
            List of surfaced insight records ordered by most recent
        """
        try:
            query = self._db.table("surfaced_insights").select("*").eq("user_id", user_id)

            if engaged_only:
                query = query.eq("engaged", True)

            result = query.order("surfaced_at", desc=True).limit(limit).execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error("Failed to get surfaced history: %s", e)
            return []
