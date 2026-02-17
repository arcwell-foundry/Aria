"""Health score calculator for lead memory.

Calculates lead health score (0-100) based on 5 weighted factors:
- Communication frequency (0.25): How consistently we're in touch
- Response time (0.20): How quickly we respond to inbound
- Sentiment (0.20): Overall sentiment of interactions
- Stakeholder breadth (0.20): How many stakeholders we engage
- Stage velocity (0.15): How fast lead progresses through stages

Health scores are recalculated on new events and tracked over time.
Alerts are generated when health drops significantly.

Usage:
    ```python
    from src.memory.health_score import HealthScoreCalculator

    calculator = HealthScoreCalculator()

    # Calculate health score
    score = calculator.calculate(
        lead=lead_memory,
        events=lead_events,
        insights=lead_insights,
        stakeholders=lead_stakeholders,
        stage_history=stage_transitions,
    )

    # Check if alert needed
    history = await get_score_history(lead_id)
    if calculator._should_alert(score, history):
        # Send alert
        pass
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.memory.lead_memory_events import LeadEvent
from src.models.lead_memory import Direction, Sentiment

logger = logging.getLogger(__name__)


@dataclass
class HealthScoreHistory:
    """A historical health score record.

    Attributes:
        score: The health score value (0-100).
        calculated_at: When the score was calculated.
    """

    score: int
    calculated_at: datetime


class HealthScoreCalculator:
    """Calculate lead health scores from activity data.

    Health scores range from 0-100 and are calculated from 5 weighted
    factors. Higher scores indicate healthier leads more likely to close.
    """

    # Weight for each factor (sums to 1.0)
    WEIGHTS: dict[str, float] = {
        "communication_frequency": 0.25,
        "response_time": 0.20,
        "sentiment": 0.20,
        "stakeholder_breadth": 0.20,
        "stage_velocity": 0.15,
    }

    # Scoring constants
    IDEAL_CONTACT_FREQUENCY_DAYS = 7  # Ideal: contact every week
    STALE_AFTER_DAYS = 30  # Lead is stale after 30 days no contact
    FAST_RESPONSE_HOURS = 4  # Fast response: within 4 hours
    SLOW_RESPONSE_HOURS = 72  # Slow response: after 72 hours

    def _score_frequency(self, events: list[LeadEvent]) -> float:
        """Score communication frequency.

        0.0 = no events or events >90 days old
        1.0 = events at least once per week

        Args:
            events: List of lead events.

        Returns:
            Score between 0.0 and 1.0.
        """
        if not events:
            return 0.0

        now = datetime.now(UTC)
        sorted_events = sorted(events, key=lambda e: e.occurred_at, reverse=True)

        # Get most recent event
        most_recent = sorted_events[0].occurred_at
        days_since_contact = (now - most_recent).days

        # No contact in 90 days = 0 score
        if days_since_contact > 90:
            return 0.0

        # No contact in 30 days = low score
        if days_since_contact > 30:
            return 0.2

        # Count events in last 30 days
        recent_events = [e for e in events if (now - e.occurred_at).days <= 30]

        # Ideal: at least 4 contacts per month (~weekly)
        target_count = 4
        event_ratio = min(len(recent_events) / target_count, 2.0)

        # Base score from recency + bonus for frequency
        base_score = 1.0 - (days_since_contact / 30)
        frequency_bonus = min(event_ratio - 1.0, 0.5)

        return float(min(base_score + frequency_bonus, 1.0))

    def _score_response_time(self, events: list[LeadEvent]) -> float:
        """Score response time to inbound communications.

        0.5 = neutral (no inbound events)
        0.0 = very slow response (>72 hours)
        1.0 = fast response (<4 hours)

        Args:
            events: List of lead events.

        Returns:
            Score between 0.0 and 1.0.
        """
        # Separate inbound and outbound events
        inbound_events = [
            e for e in events if hasattr(e, "direction") and e.direction == Direction.INBOUND
        ]

        if not inbound_events:
            return 0.5  # Neutral if no inbound

        outbound_events = [
            e for e in events if hasattr(e, "direction") and e.direction == Direction.OUTBOUND
        ]

        if not outbound_events:
            return 0.0  # No responses = 0 score

        # Calculate average response time
        response_times = []
        sorted_inbound = sorted(inbound_events, key=lambda e: e.occurred_at)

        for inbound in sorted_inbound:
            # Find first outbound after this inbound
            responses = [o for o in outbound_events if o.occurred_at > inbound.occurred_at]

            if responses:
                first_response = min(responses, key=lambda o: o.occurred_at)
                response_hours = (
                    first_response.occurred_at - inbound.occurred_at
                ).total_seconds() / 3600
                response_times.append(response_hours)

        if not response_times:
            return 0.0  # No valid responses found

        avg_response_hours = sum(response_times) / len(response_times)

        # Score based on response time
        if avg_response_hours <= self.FAST_RESPONSE_HOURS:
            return 1.0
        elif avg_response_hours >= self.SLOW_RESPONSE_HOURS:
            return 0.0
        else:
            # Linear interpolation between fast and slow
            ratio = (avg_response_hours - self.FAST_RESPONSE_HOURS) / (
                self.SLOW_RESPONSE_HOURS - self.FAST_RESPONSE_HOURS
            )
            return float(1.0 - ratio)

    def _score_sentiment(
        self,
        insights: list[Any],
        perception_data: dict[str, Any] | None = None,
    ) -> float:
        """Score overall sentiment from insights, optionally blended with video perception.

        When ``perception_data`` is ``None`` the method behaves exactly as
        before (backward compatible).  When perception data from a Tavus
        video session is supplied, the final score is a weighted blend of
        insight-based sentiment (70%) and perception-based engagement (30%).

        0.5 = neutral (no insights, no perception)
        0.0 = all negative / fully disengaged
        1.0 = all positive / fully engaged

        Args:
            insights: List of insight objects with sentiment field.
            perception_data: Optional dict with keys ``engagement_score``,
                ``confusion_events``, and ``disengagement_events`` from the
                Tavus Raven-0 perception pipeline.

        Returns:
            Score between 0.0 and 1.0.
        """
        # --- Insight-based score (unchanged logic) ---
        if not insights:
            insight_score = 0.5  # Neutral default
        else:
            positive_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.POSITIVE
            )
            negative_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.NEGATIVE
            )
            neutral_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.NEUTRAL
            )
            unknown_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.UNKNOWN
            )

            total = len(insights)
            if total == 0:
                insight_score = 0.5
            else:
                sentiment_sum = (
                    positive_count * 1.0
                    + (neutral_count + unknown_count) * 0.5
                    + negative_count * 0.0
                )
                insight_score = sentiment_sum / total

        # --- Backward compatible: no perception data ---
        if perception_data is None:
            return insight_score

        # --- Perception-based score ---
        engagement = float(perception_data.get("engagement_score", 0.5))
        confusion = int(perception_data.get("confusion_events", 0))
        disengagement = int(perception_data.get("disengagement_events", 0))

        perception_score = engagement
        perception_score -= min(confusion * 0.03, 0.3)
        perception_score -= min(disengagement * 0.04, 0.3)
        perception_score = max(0.0, min(perception_score, 1.0))

        # --- Blend: 70% insight, 30% perception ---
        return insight_score * 0.7 + perception_score * 0.3

    def _score_breadth(self, stakeholders: list[Any]) -> float:
        """Score stakeholder breadth.

        0.0 = no stakeholders
        1.0 = 4+ stakeholders across different roles

        Args:
            stakeholders: List of stakeholder objects with role field.

        Returns:
            Score between 0.0 and 1.0.
        """
        if not stakeholders:
            return 0.0

        # Count unique roles
        roles = {getattr(s, "role", None) for s in stakeholders}
        roles.discard(None)  # Remove None values

        unique_roles = len(roles)
        total_stakeholders = len(stakeholders)

        # Score based on unique roles (ideal: 4+ different roles)
        role_score = min(unique_roles / 4.0, 1.0)

        # Bonus for multiple stakeholders per role
        stakeholder_bonus = min((total_stakeholders - unique_roles) / 4.0, 0.2)

        return float(min(role_score + stakeholder_bonus, 1.0))

    def _score_velocity(self, lead: Any, stage_history: list[dict[str, Any]]) -> float:
        """Score stage progression velocity.

        0.5 = neutral (new lead)
        0.0 = stalled (>90 days in same stage)
        1.0 = fast progression (<30 days per stage)

        Args:
            lead: LeadMemory object.
            stage_history: List of stage transition dicts.

        Returns:
            Score between 0.0 and 1.0.
        """
        now = datetime.now(UTC)
        # Access first_touch_at from lead object (type: ignore for dynamic attribute)
        first_touch_at = getattr(lead, "first_touch_at", None)
        if first_touch_at is None:
            return 0.5  # Neutral if no first_touch_at
        days_since_first_touch = (now - first_touch_at).days

        # New lead (<7 days) = neutral
        if days_since_first_touch < 7:
            return 0.5

        # Check how long in current stage
        if stage_history:
            # Get most recent transition
            last_transition = max(
                stage_history,
                key=lambda h: datetime.fromisoformat(h["transitioned_at"]),
            )
            stage_entered_at = datetime.fromisoformat(last_transition["transitioned_at"])
        else:
            # No transitions yet, use first_touch_at as stage entry time
            stage_entered_at = first_touch_at  # Already retrieved above

        days_in_stage = (now - stage_entered_at).days

        # Stalled: >90 days in same stage
        if days_in_stage > 90:
            return 0.0

        # Fast progression: moved stages in <30 days
        if days_in_stage < 30:
            return 1.0

        # Linear interpolation
        return 1.0 - ((days_in_stage - 30) / 60)

    def calculate(
        self,
        lead: Any,
        events: list[LeadEvent],
        insights: list[Any],
        stakeholders: list[Any],
        stage_history: list[dict[str, Any]],
    ) -> int:
        """Calculate overall health score.

        Args:
            lead: LeadMemory object.
            events: List of lead events.
            insights: List of insight objects.
            stakeholders: List of stakeholder objects.
            stage_history: List of stage transition dicts.

        Returns:
            Health score between 0 and 100.
        """
        scores = {
            "communication_frequency": self._score_frequency(events),
            "response_time": self._score_response_time(events),
            "sentiment": self._score_sentiment(insights),
            "stakeholder_breadth": self._score_breadth(stakeholders),
            "stage_velocity": self._score_velocity(lead, stage_history),
        }

        # Calculate weighted sum
        weighted_sum = sum(scores[factor] * weight for factor, weight in self.WEIGHTS.items())

        health_score = int(weighted_sum * 100)

        logger.info(
            "Calculated health score",
            extra={
                "lead_id": getattr(lead, "id", "unknown"),
                "health_score": health_score,
                "component_scores": scores,
            },
        )

        return health_score

    def _should_alert(
        self,
        current_score: int,
        history: list[HealthScoreHistory],
        threshold: int = 20,
    ) -> bool:
        """Check if health score drop should trigger alert.

        Args:
            current_score: The newly calculated health score.
            history: List of historical scores.
            threshold: Minimum drop to trigger alert (default: 20).

        Returns:
            True if alert should be sent.
        """
        if not history:
            return False  # No previous score to compare

        # Get most recent score
        most_recent = max(history, key=lambda h: h.calculated_at)
        previous_score = most_recent.score

        # Alert on drop of threshold or more
        score_drop = previous_score - current_score
        return score_drop >= threshold
