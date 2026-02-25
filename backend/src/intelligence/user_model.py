"""User Mental Model Service for ARIA cognition.

Provides a persistent behavioral profile for each user, computed entirely
from heuristics (zero LLM calls). Tracks:
- Stress trend over the past 7 days
- Decision style inferred from conversation summaries
- Preferred communication depth from message length patterns
- Current focus from active goals
- Workload metrics (active/overdue goals, session patterns)

Data sources (all existing tables):
- cognitive_load_snapshots — stress trend
- conversation_episodes — session patterns, topic analysis
- goals — active/overdue counts, focus areas
- digital_twin_profiles — communication preferences
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Decision style keywords
ANALYTICAL_KEYWORDS = [
    "data", "numbers", "metrics", "analyze", "compare", "evidence",
    "research", "quantify", "benchmark", "roi", "statistical", "measure",
    "percentage", "ratio", "correlation", "findings", "methodology",
]

INTUITIVE_KEYWORDS = [
    "gut", "feel", "sense", "hunch", "instinct", "vibe", "impression",
    "quickly", "just do", "go with", "trust", "obvious", "clearly",
]

COLLABORATIVE_KEYWORDS = [
    "team", "together", "align", "consensus", "stakeholder", "discuss",
    "meeting", "input", "feedback", "agree", "collaborate", "coordinate",
]

# Cache TTL
_CACHE_TTL_SECONDS = 600  # 10 minutes


@dataclass
class UserMentalModel:
    """Persistent behavioral profile for a user.

    All fields are computed from existing database tables
    using pure heuristics — no LLM calls.
    """

    user_id: str
    stress_trend: str  # "improving" | "stable" | "worsening"
    decision_style: str  # "analytical" | "intuitive" | "collaborative" | "unknown"
    preferred_depth: str  # "brief" | "standard" | "detailed"
    current_focus: str  # Most recent active goal title
    active_goal_count: int
    overdue_goal_count: int
    avg_messages_per_session: float
    peak_activity_hour: int | None  # 0-23, or None if unknown
    communication_preferences: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_prompt_section(self) -> str:
        """Format as a system prompt section for LLM context."""
        lines = [
            f"- Stress trend (7-day): {self.stress_trend}",
            f"- Decision style: {self.decision_style}",
            f"- Preferred depth: {self.preferred_depth}",
            f"- Current focus: {self.current_focus}",
            f"- Active goals: {self.active_goal_count} ({self.overdue_goal_count} overdue)",
        ]
        if self.avg_messages_per_session > 0:
            lines.append(
                f"- Avg messages/session: {self.avg_messages_per_session:.1f}"
            )
        if self.peak_activity_hour is not None:
            lines.append(f"- Peak activity hour: {self.peak_activity_hour}:00")
        if self.communication_preferences:
            prefs = self.communication_preferences
            if prefs.get("preferred_tone"):
                lines.append(f"- Preferred tone: {prefs['preferred_tone']}")
            if prefs.get("communication_style"):
                lines.append(f"- Communication style: {prefs['communication_style']}")
        return "\n".join(lines)


class UserMentalModelService:
    """Service for computing persistent user behavioral profiles.

    Pure heuristics, zero LLM calls. Results are cached with a
    10-minute TTL to avoid redundant DB queries.
    """

    def __init__(self, db_client: Any) -> None:
        """Initialize the service.

        Args:
            db_client: Supabase client for database queries.
        """
        self._db = db_client
        self._cache: dict[str, tuple[UserMentalModel, float]] = {}

    async def get_model(self, user_id: str) -> UserMentalModel:
        """Get or compute the user mental model.

        Returns cached model if within TTL, otherwise recomputes.

        Args:
            user_id: User identifier.

        Returns:
            UserMentalModel with all behavioral profile fields.
        """
        now = time.monotonic()
        cached = self._cache.get(user_id)
        if cached:
            model, cached_at = cached
            if now - cached_at < _CACHE_TTL_SECONDS:
                return model

        start = time.monotonic()
        model = await self._compute_model(user_id)
        elapsed_ms = (time.monotonic() - start) * 1000

        self._cache[user_id] = (model, now)

        logger.info(
            "Computed user mental model",
            extra={
                "user_id": user_id,
                "stress_trend": model.stress_trend,
                "decision_style": model.decision_style,
                "preferred_depth": model.preferred_depth,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )

        return model

    async def _compute_model(self, user_id: str) -> UserMentalModel:
        """Compute a fresh user mental model from database sources."""
        stress_trend = await self._compute_stress_trend(user_id)
        decision_style = await self._compute_decision_style(user_id)
        preferred_depth = await self._compute_preferred_depth(user_id)
        current_focus, active_count, overdue_count = await self._compute_goal_metrics(user_id)
        avg_messages, peak_hour = await self._compute_session_patterns(user_id)
        comm_prefs = await self._get_communication_preferences(user_id)

        return UserMentalModel(
            user_id=user_id,
            stress_trend=stress_trend,
            decision_style=decision_style,
            preferred_depth=preferred_depth,
            current_focus=current_focus,
            active_goal_count=active_count,
            overdue_goal_count=overdue_count,
            avg_messages_per_session=avg_messages,
            peak_activity_hour=peak_hour,
            communication_preferences=comm_prefs,
        )

    async def _compute_stress_trend(self, user_id: str) -> str:
        """Compute 7-day stress trend from cognitive_load_snapshots.

        Compares average load score of the last 3 days vs the prior 4 days.

        Returns:
            "improving" if recent stress is lower, "worsening" if higher,
            "stable" otherwise.
        """
        try:
            seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("load_score, measured_at")
                .eq("user_id", user_id)
                .gte("measured_at", seven_days_ago)
                .order("measured_at", desc=False)
                .limit(100)
                .execute()
            )

            if not result.data or len(result.data) < 4:
                return "stable"

            snapshots = result.data
            midpoint = len(snapshots) // 2
            older = snapshots[:midpoint]
            recent = snapshots[midpoint:]

            older_avg = sum(s["load_score"] for s in older) / len(older)
            recent_avg = sum(s["load_score"] for s in recent) / len(recent)

            delta = recent_avg - older_avg
            if delta < -0.1:
                return "improving"
            elif delta > 0.1:
                return "worsening"
            return "stable"

        except Exception as e:
            logger.warning("Failed to compute stress trend: %s", e)
            return "stable"

    async def _compute_decision_style(self, user_id: str) -> str:
        """Infer decision style from conversation_episodes summaries.

        Counts keyword occurrences for analytical, intuitive, and
        collaborative patterns.

        Returns:
            "analytical", "intuitive", "collaborative", or "unknown"
        """
        try:
            thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
            result = (
                self._db.table("conversation_episodes")
                .select("summary")
                .eq("user_id", user_id)
                .gte("created_at", thirty_days_ago)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )

            if not result.data:
                return "unknown"

            combined_text = " ".join(
                (ep.get("summary") or "") for ep in result.data
            ).lower()

            if not combined_text.strip():
                return "unknown"

            analytical_count = sum(1 for kw in ANALYTICAL_KEYWORDS if kw in combined_text)
            intuitive_count = sum(1 for kw in INTUITIVE_KEYWORDS if kw in combined_text)
            collaborative_count = sum(1 for kw in COLLABORATIVE_KEYWORDS if kw in combined_text)

            scores = {
                "analytical": analytical_count,
                "intuitive": intuitive_count,
                "collaborative": collaborative_count,
            }

            max_style = max(scores, key=scores.get)  # type: ignore[arg-type]
            if scores[max_style] < 3:
                return "unknown"

            return max_style

        except Exception as e:
            logger.warning("Failed to compute decision style: %s", e)
            return "unknown"

    async def _compute_preferred_depth(self, user_id: str) -> str:
        """Compute preferred communication depth from message length patterns.

        Uses cognitive_load_snapshots factors (message_brevity) as a proxy
        for how terse or verbose the user tends to be.

        Returns:
            "brief", "standard", or "detailed"
        """
        try:
            fourteen_days_ago = (datetime.now(UTC) - timedelta(days=14)).isoformat()
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("factors")
                .eq("user_id", user_id)
                .gte("measured_at", fourteen_days_ago)
                .order("measured_at", desc=True)
                .limit(50)
                .execute()
            )

            if not result.data:
                return "standard"

            brevity_scores = []
            for snapshot in result.data:
                factors = snapshot.get("factors") or {}
                if "message_brevity" in factors:
                    brevity_scores.append(factors["message_brevity"])

            if not brevity_scores:
                return "standard"

            avg_brevity = sum(brevity_scores) / len(brevity_scores)

            # High brevity score = short messages = user prefers brief
            if avg_brevity > 0.65:
                return "brief"
            elif avg_brevity < 0.35:
                return "detailed"
            return "standard"

        except Exception as e:
            logger.warning("Failed to compute preferred depth: %s", e)
            return "standard"

    async def _compute_goal_metrics(
        self, user_id: str
    ) -> tuple[str, int, int]:
        """Compute goal-related metrics.

        Returns:
            Tuple of (current_focus, active_count, overdue_count)
        """
        try:
            result = (
                self._db.table("goals")
                .select("id, title, status, due_date")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("updated_at", desc=True)
                .limit(20)
                .execute()
            )

            goals = result.data or []
            active_count = len(goals)

            # Current focus = most recently updated active goal
            current_focus = goals[0]["title"] if goals else "No active goals"

            # Count overdue goals
            now = datetime.now(UTC)
            overdue_count = 0
            for goal in goals:
                due_date_str = goal.get("due_date")
                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(
                            due_date_str.replace("Z", "+00:00")
                        )
                        if due_date < now:
                            overdue_count += 1
                    except (ValueError, TypeError):
                        pass

            return current_focus, active_count, overdue_count

        except Exception as e:
            logger.warning("Failed to compute goal metrics: %s", e)
            return "Unknown", 0, 0

    async def _compute_session_patterns(
        self, user_id: str
    ) -> tuple[float, int | None]:
        """Compute session patterns from conversation_episodes.

        Returns:
            Tuple of (avg_messages_per_session, peak_activity_hour)
        """
        try:
            thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
            result = (
                self._db.table("conversation_episodes")
                .select("message_count, created_at")
                .eq("user_id", user_id)
                .gte("created_at", thirty_days_ago)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )

            if not result.data:
                return 0.0, None

            episodes = result.data

            # Average messages per session
            msg_counts = [
                ep.get("message_count", 0) for ep in episodes
                if ep.get("message_count") is not None
            ]
            avg_messages = (
                sum(msg_counts) / len(msg_counts) if msg_counts else 0.0
            )

            # Peak activity hour
            hour_counts: dict[int, int] = {}
            for ep in episodes:
                created_at = ep.get("created_at")
                if created_at:
                    try:
                        dt = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                        hour = dt.hour
                        hour_counts[hour] = hour_counts.get(hour, 0) + 1
                    except (ValueError, TypeError):
                        pass

            peak_hour = (
                max(hour_counts, key=hour_counts.get)  # type: ignore[arg-type]
                if hour_counts
                else None
            )

            return avg_messages, peak_hour

        except Exception as e:
            logger.warning("Failed to compute session patterns: %s", e)
            return 0.0, None

    async def _get_communication_preferences(
        self, user_id: str
    ) -> dict[str, Any]:
        """Get communication preferences from digital_twin_profiles.

        Returns:
            Dict with preferred_tone, communication_style, etc.
        """
        try:
            result = (
                self._db.table("digital_twin_profiles")
                .select("preferred_tone, communication_style, risk_tolerance")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            if result.data:
                return result.data[0]
            return {}

        except Exception as e:
            logger.warning("Failed to get communication preferences: %s", e)
            return {}
