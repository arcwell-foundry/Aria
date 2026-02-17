"""Perception intelligence service for ARIA.

Orchestrates Raven-1 perception analysis data into lead health scores,
conversion predictions, and actionable follow-up insights. Serves as
the central coordinator for all perception → lead intelligence flows.

Usage:
    ```python
    from src.services.perception_intelligence import PerceptionIntelligenceService

    service = PerceptionIntelligenceService()

    # After a video session ends with perception data
    await service.process_perception_analysis(session_id, analysis_data)

    # Get meeting quality score
    score = await service.calculate_meeting_quality_score(session_id)

    # Generate human-readable insights
    insights = await service.generate_perception_insights(session_id)

    # Feed perception features to conversion scoring
    await service.feed_to_conversion_scoring(lead_memory_id)
    ```
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class PerceptionIntelligenceService:
    """Orchestrate Raven-1 perception data into lead intelligence.

    Bridges video session perception analysis with lead health scores,
    conversion predictions, and follow-up recommendations.
    """

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()

    # ─────────────────────────────────────────────────────────────────────
    # process_perception_analysis
    # ─────────────────────────────────────────────────────────────────────

    async def process_perception_analysis(
        self,
        session_id: str,
        analysis_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process Raven-1 perception analysis for a completed video session.

        Parses the perception payload, extracts key metrics, and — when the
        session is linked to a lead — updates lead memory events, stakeholder
        sentiment, and health score.

        Args:
            session_id: The video session UUID.
            analysis_data: Raven-1 perception_analysis event data containing
                engagement_score, emotion, attention_level, sentiment, and
                optional raw_data / perception_events.

        Returns:
            Dict with processing results, or None on failure.
        """
        try:
            # Extract core metrics
            engagement = float(analysis_data.get("engagement_score", 0.5))
            attention = float(analysis_data.get("attention_level", engagement))
            emotional_trajectory = analysis_data.get("sentiment", "neutral")
            confusion_events = int(analysis_data.get("confusion_events", 0))
            disengagement_events = int(analysis_data.get("disengagement_events", 0))

            # Fetch session to check lead linkage
            session_result = (
                self._db.table("video_sessions")
                .select("id, user_id, lead_id, started_at, ended_at, perception_events")
                .eq("id", session_id)
                .execute()
            )

            if not session_result.data:
                logger.warning(
                    "No video session found for perception processing",
                    extra={"session_id": session_id},
                )
                return None

            session = session_result.data[0]
            lead_id = session.get("lead_id")
            user_id = session.get("user_id")

            # Calculate meeting quality
            quality_score = self._compute_quality_score(
                engagement=engagement,
                attention=attention,
                confusion_events=confusion_events,
                disengagement_events=disengagement_events,
                session=session,
            )

            result: dict[str, Any] = {
                "session_id": session_id,
                "engagement": engagement,
                "attention": attention,
                "emotional_trajectory": emotional_trajectory,
                "quality_score": quality_score,
                "lead_id": lead_id,
            }

            if not lead_id:
                logger.info(
                    "Perception processed (no lead linked)",
                    extra={"session_id": session_id, "quality_score": quality_score},
                )
                return result

            # ── Lead-linked updates ──────────────────────────────────

            # 1. Add perception_data event to lead_memory_events
            self._db.table("lead_memory_events").insert({
                "lead_memory_id": lead_id,
                "event_type": "meeting",
                "direction": "outbound",
                "subject": "Video session perception analysis",
                "content": (
                    f"Engagement: {engagement:.0%}, Attention: {attention:.0%}, "
                    f"Trajectory: {emotional_trajectory}, "
                    f"Quality: {quality_score}/100"
                ),
                "source": "tavus_perception",
                "source_id": session_id,
                "occurred_at": datetime.now(UTC).isoformat(),
                "metadata": {
                    "perception_data": True,
                    "engagement_score": engagement,
                    "attention_score": attention,
                    "emotional_trajectory": emotional_trajectory,
                    "confusion_events": confusion_events,
                    "disengagement_events": disengagement_events,
                    "quality_score": quality_score,
                },
            }).execute()

            # 2. Update stakeholder sentiment based on emotional trajectory
            sentiment_map = {
                "positive": "positive",
                "very_positive": "positive",
                "neutral": "neutral",
                "negative": "negative",
                "very_negative": "negative",
            }
            mapped_sentiment = sentiment_map.get(emotional_trajectory, "neutral")

            # Only update if perception provides clear signal
            if emotional_trajectory in ("positive", "very_positive", "negative", "very_negative"):
                self._db.table("lead_memory_stakeholders").update({
                    "sentiment": mapped_sentiment,
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("lead_memory_id", lead_id).execute()

            # 3. Factor engagement into health_score
            await self._update_health_score_from_perception(
                lead_id=lead_id,
                quality_score=quality_score,
            )

            # 4. Log to activity feed
            self._db.table("aria_activity").insert({
                "user_id": user_id,
                "activity_type": "perception.intelligence_processed",
                "description": (
                    f"Perception intelligence: quality={quality_score}/100, "
                    f"engagement={engagement:.0%}"
                ),
                "metadata": {
                    "session_id": session_id,
                    "lead_id": lead_id,
                    "quality_score": quality_score,
                    "engagement": engagement,
                    "emotional_trajectory": emotional_trajectory,
                },
            }).execute()

            logger.info(
                "Perception intelligence processed for lead",
                extra={
                    "session_id": session_id,
                    "lead_id": lead_id,
                    "quality_score": quality_score,
                },
            )

            result["health_score_updated"] = True
            return result

        except Exception as e:
            logger.error(
                "Failed to process perception analysis",
                extra={"session_id": session_id, "error": str(e)},
                exc_info=True,
            )
            return None

    # ─────────────────────────────────────────────────────────────────────
    # calculate_meeting_quality_score
    # ─────────────────────────────────────────────────────────────────────

    async def calculate_meeting_quality_score(self, session_id: str) -> int:
        """Calculate a 0-100 meeting quality score for a video session.

        Inputs: engagement %, confusion event count, attention score, and
        call duration. High engagement + few confusion events + good
        attention = high score.

        Args:
            session_id: The video session UUID.

        Returns:
            Meeting quality score between 0 and 100.
        """
        session_result = (
            self._db.table("video_sessions")
            .select("perception_analysis, perception_events, started_at, ended_at")
            .eq("id", session_id)
            .execute()
        )

        if not session_result.data:
            return 50  # Neutral default

        session = session_result.data[0]
        analysis = session.get("perception_analysis") or {}
        events = session.get("perception_events") or []

        engagement = float(analysis.get("engagement_score", 0.5))
        attention = float(analysis.get("attention_level", engagement))
        confusion_events = int(analysis.get("confusion_events", 0))
        disengagement_events = int(analysis.get("disengagement_events", 0))

        # Fall back to counting raw events if aggregated counts missing
        if not confusion_events and not disengagement_events and events:
            for evt in events:
                tool_name = evt.get("tool_name", "")
                if tool_name == "adapt_to_confusion":
                    confusion_events += 1
                elif tool_name == "note_engagement_drop":
                    disengagement_events += 1

        return self._compute_quality_score(
            engagement=engagement,
            attention=attention,
            confusion_events=confusion_events,
            disengagement_events=disengagement_events,
            session=session,
        )

    # ─────────────────────────────────────────────────────────────────────
    # generate_perception_insights
    # ─────────────────────────────────────────────────────────────────────

    async def generate_perception_insights(self, session_id: str) -> list[str]:
        """Generate human-readable insights from perception analysis.

        Produces actionable observations like engagement levels, skepticism
        signals, and attention drop-offs that ARIA can surface in briefings
        and follow-up recommendations.

        Args:
            session_id: The video session UUID.

        Returns:
            List of insight strings.
        """
        session_result = (
            self._db.table("video_sessions")
            .select("perception_analysis, perception_events, started_at, ended_at")
            .eq("id", session_id)
            .execute()
        )

        if not session_result.data:
            return []

        session = session_result.data[0]
        analysis = session.get("perception_analysis") or {}
        events = session.get("perception_events") or []

        insights: list[str] = []

        engagement = float(analysis.get("engagement_score", 0.5))
        attention = float(analysis.get("attention_level", engagement))
        confused_topics = analysis.get("confused_topics", [])
        engagement_trend = analysis.get("engagement_trend", "stable")

        # ── Engagement level ─────────────────────────────────────────
        if engagement >= 0.8:
            insights.append(
                f"User was highly engaged ({engagement:.0%} engagement score) "
                "throughout the session"
            )
        elif engagement >= 0.6:
            insights.append(
                f"User showed moderate engagement ({engagement:.0%} engagement score)"
            )
        elif engagement >= 0.4:
            insights.append(
                f"User engagement was below average ({engagement:.0%}) — "
                "consider a more focused follow-up"
            )
        else:
            insights.append(
                f"User showed low engagement ({engagement:.0%}) — "
                "session may not have resonated; follow up to reassess interest"
            )

        # ── Attention vs engagement divergence ───────────────────────
        if attention >= 0.8 and engagement < 0.6:
            insights.append(
                "User was attentive but not engaged — they were listening but "
                "may not have found the content compelling"
            )

        # ── Confusion signals ────────────────────────────────────────
        if confused_topics:
            topics_str = ", ".join(confused_topics[:3])
            insights.append(
                f"Detected confusion during discussion of: {topics_str} — "
                "consider clarifying these points in follow-up"
            )

        # ── Engagement trend ─────────────────────────────────────────
        if engagement_trend == "declining":
            # Check if decline was in last portion via events
            insights.append(
                "Engagement declined in the second half of the session — "
                "meeting may have run long or lost focus"
            )
        elif engagement_trend == "improving":
            insights.append(
                "Engagement improved during the session — "
                "later discussion points resonated well"
            )

        # ── Disengagement events ─────────────────────────────────────
        disengagement_count = sum(
            1 for evt in events if evt.get("tool_name") == "note_engagement_drop"
        )
        if disengagement_count >= 3:
            insights.append(
                f"Multiple disengagement signals detected ({disengagement_count} events) — "
                "consider shorter, more targeted meetings"
            )

        # ── Emotional trajectory from raw events ─────────────────────
        sentiment = analysis.get("sentiment", "")
        if sentiment in ("negative", "very_negative"):
            insights.append(
                "Detected skepticism or negative sentiment — "
                "suggest addressing concerns directly in follow-up"
            )
        elif sentiment in ("positive", "very_positive"):
            insights.append(
                "Positive emotional trajectory detected — "
                "momentum is favorable for advancing the conversation"
            )

        # ── Duration context ─────────────────────────────────────────
        duration_seconds = self._get_duration_seconds(session)
        if duration_seconds and duration_seconds > 2700 and engagement_trend == "declining":
            insights.append(
                f"Session ran {duration_seconds // 60} minutes with declining engagement — "
                "consider keeping future calls under 30 minutes"
            )

        return insights

    # ─────────────────────────────────────────────────────────────────────
    # feed_to_conversion_scoring
    # ─────────────────────────────────────────────────────────────────────

    async def feed_to_conversion_scoring(self, lead_memory_id: str) -> dict[str, Any]:
        """Compute perception-based features for conversion scoring.

        Averages meeting quality scores across all video sessions linked
        to a lead and returns normalized features that the conversion
        scoring service can consume.

        Args:
            lead_memory_id: The lead memory UUID.

        Returns:
            Dict with normalized perception features:
                - avg_meeting_engagement: 0-1
                - emotional_trajectory_positive: bool
                - confusion_frequency: 0-1 (inverse, less = higher)
        """
        # Fetch all ended sessions for this lead
        result = (
            self._db.table("video_sessions")
            .select("perception_analysis, perception_events, started_at, ended_at")
            .eq("lead_id", lead_memory_id)
            .eq("status", "ended")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        sessions = result.data or []

        if not sessions:
            return {
                "avg_meeting_engagement": 0.5,
                "emotional_trajectory_positive": True,
                "confusion_frequency": 1.0,  # No confusion = max score
            }

        engagement_scores: list[float] = []
        positive_count = 0
        negative_count = 0
        total_confusion = 0
        total_events = 0

        for session in sessions:
            analysis = session.get("perception_analysis")
            if not isinstance(analysis, dict):
                continue

            eng = analysis.get("engagement_score")
            if isinstance(eng, (int, float)):
                engagement_scores.append(float(eng))

            sentiment = analysis.get("sentiment", "neutral")
            if sentiment in ("positive", "very_positive"):
                positive_count += 1
            elif sentiment in ("negative", "very_negative"):
                negative_count += 1

            total_confusion += int(analysis.get("confusion_events", 0))
            events = session.get("perception_events") or []
            total_events += max(len(events), 1)

        avg_engagement = (
            sum(engagement_scores) / len(engagement_scores)
            if engagement_scores
            else 0.5
        )

        # Emotional trajectory: positive if majority of sessions are positive
        total_sentiment = positive_count + negative_count
        emotional_positive = (
            positive_count > negative_count if total_sentiment > 0 else True
        )

        # Confusion frequency: inverse normalized
        # 0 confusion events → 1.0, high confusion → approaches 0.0
        confusion_rate = total_confusion / total_events if total_events > 0 else 0
        confusion_frequency = max(0.0, 1.0 - min(confusion_rate * 0.2, 1.0))

        features = {
            "avg_meeting_engagement": round(avg_engagement, 3),
            "emotional_trajectory_positive": emotional_positive,
            "confusion_frequency": round(confusion_frequency, 3),
        }

        logger.info(
            "Perception features computed for conversion scoring",
            extra={"lead_memory_id": lead_memory_id, "features": features},
        )

        return features

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _compute_quality_score(
        self,
        engagement: float,
        attention: float,
        confusion_events: int,
        disengagement_events: int,
        session: dict[str, Any],
    ) -> int:
        """Compute meeting quality score 0-100 from perception metrics.

        Weights:
        - Engagement: 40%
        - Attention: 25%
        - Confusion penalty: 20% (fewer = better)
        - Duration factor: 15% (penalise very short / very long)

        Args:
            engagement: 0-1 engagement score.
            attention: 0-1 attention score.
            confusion_events: Count of confusion tool calls.
            disengagement_events: Count of disengagement tool calls.
            session: Video session row (needs started_at, ended_at).

        Returns:
            Quality score 0-100.
        """
        # Engagement component (0-40)
        engagement_component = engagement * 40

        # Attention component (0-25)
        attention_component = attention * 25

        # Confusion/disengagement penalty (0-20, starts at 20 and decreases)
        event_penalty = min((confusion_events * 3 + disengagement_events * 4), 20)
        clarity_component = 20 - event_penalty

        # Duration factor (0-15)
        duration_seconds = self._get_duration_seconds(session)
        if duration_seconds is None:
            duration_component = 10.0  # Neutral if unknown
        elif duration_seconds < 120:
            # Very short call — likely disconnected
            duration_component = 5.0
        elif duration_seconds <= 1800:
            # 2-30 min: ideal range
            duration_component = 15.0
        elif duration_seconds <= 2700:
            # 30-45 min: still good
            duration_component = 12.0
        else:
            # >45 min: diminishing returns
            duration_component = max(8.0 - (duration_seconds - 2700) / 900, 3.0)

        raw_score = (
            engagement_component
            + attention_component
            + clarity_component
            + duration_component
        )

        return max(0, min(100, int(round(raw_score))))

    async def _update_health_score_from_perception(
        self,
        lead_id: str,
        quality_score: int,
    ) -> None:
        """Adjust lead health_score based on perception quality.

        Applies a bounded adjustment (-8 to +5 points) based on the
        meeting quality score relative to a neutral threshold of 60.

        Args:
            lead_id: The lead memory UUID.
            quality_score: The computed 0-100 quality score.
        """
        lead_result = (
            self._db.table("lead_memories")
            .select("health_score")
            .eq("id", lead_id)
            .execute()
        )

        if not lead_result.data:
            return

        current_score = lead_result.data[0].get("health_score", 50)

        # Quality > 60 → positive adjustment, < 60 → negative
        if quality_score >= 75:
            adjustment = 5
        elif quality_score >= 60:
            adjustment = 2
        elif quality_score >= 40:
            adjustment = -2
        elif quality_score >= 20:
            adjustment = -5
        else:
            adjustment = -8

        new_score = max(0, min(100, current_score + adjustment))

        if new_score != current_score:
            self._db.table("lead_memories").update({
                "health_score": new_score,
                "last_activity_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", lead_id).execute()

            # Record in health_score_history for trend analysis
            self._db.table("health_score_history").insert({
                "lead_memory_id": lead_id,
                "score": new_score,
                "source": "perception_intelligence",
                "calculated_at": datetime.now(UTC).isoformat(),
            }).execute()

            logger.info(
                "Health score updated from perception",
                extra={
                    "lead_id": lead_id,
                    "old_score": current_score,
                    "new_score": new_score,
                    "quality_score": quality_score,
                    "adjustment": adjustment,
                },
            )

    @staticmethod
    def _get_duration_seconds(session: dict[str, Any]) -> int | None:
        """Extract session duration in seconds from started_at / ended_at.

        Args:
            session: Video session row dict.

        Returns:
            Duration in seconds, or None if timestamps are missing.
        """
        started = session.get("started_at")
        ended = session.get("ended_at")
        if not started or not ended:
            return None
        try:
            start_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(str(ended).replace("Z", "+00:00"))
            return max(0, int((end_dt - start_dt).total_seconds()))
        except (ValueError, TypeError):
            return None
