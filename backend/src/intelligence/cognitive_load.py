"""Cognitive Load Monitor service for ARIA.

This service estimates user cognitive load based on:
- Message brevity (short messages indicate urgency/stress)
- Typo rate (corrections and repeated chars indicate rushed typing)
- Message velocity (rapid messages indicate stress)
- Calendar density (busy calendar increases cognitive load)
- Time of day (late night/early morning indicate fatigue)
"""

import logging
import re
from datetime import datetime
from typing import Any

from src.models.cognitive_load import CognitiveLoadState, LoadLevel

logger = logging.getLogger(__name__)


class CognitiveLoadMonitor:
    """Monitor and estimate user cognitive load to adapt response style.

    Attributes:
        WEIGHTS: Factor weights that sum to 1.0
        THRESHOLDS: Score boundaries for load levels
    """

    WEIGHTS: dict[str, float] = {
        "message_brevity": 0.25,
        "typo_rate": 0.15,
        "message_velocity": 0.20,
        "calendar_density": 0.25,
        "time_of_day": 0.15,
    }

    THRESHOLDS: dict[str, float] = {
        "low": 0.3,  # Score >= this enters MEDIUM
        "medium": 0.5,  # Score >= this enters HIGH
        "high": 0.7,  # Score >= this remains HIGH (until critical)
        "critical": 0.85,  # Score >= this enters CRITICAL
    }

    # Brevity normalization constants
    _BREVITY_MIN_CHARS: int = 20  # Messages this short or shorter = 1.0
    _BREVITY_MAX_CHARS: int = 200  # Messages this long or longer = 0.0

    # Velocity normalization constants
    _VELOCITY_RAPID_SECONDS: float = 5.0  # Messages this fast = 1.0
    _VELOCITY_RELAXED_SECONDS: float = 60.0  # Messages this slow = 0.0

    # Time of day constants
    _CORE_HOURS_START: int = 8
    _CORE_HOURS_END: int = 18
    _LATE_NIGHT_START: int = 22
    _LATE_NIGHT_END: int = 6

    def __init__(self, db_client: Any) -> None:
        """Initialize the cognitive load monitor.

        Args:
            db_client: Supabase client for database operations
        """
        self._db = db_client

    def _normalize_brevity(self, avg_length: float) -> float:
        """Normalize average message length to a 0-1 score.

        Shorter messages indicate higher cognitive load (user being terse).

        Args:
            avg_length: Average character count of recent messages

        Returns:
            Score from 0.0 (long messages) to 1.0 (short messages)
        """
        if avg_length <= self._BREVITY_MIN_CHARS:
            return 1.0
        if avg_length >= self._BREVITY_MAX_CHARS:
            return 0.0

        # Linear interpolation between min and max
        range_span = self._BREVITY_MAX_CHARS - self._BREVITY_MIN_CHARS
        normalized = (self._BREVITY_MAX_CHARS - avg_length) / range_span
        return normalized

    def _calculate_typo_rate(self, messages: list[dict[str, Any]]) -> float:
        """Calculate typo/error rate from messages.

        Indicators of rushed typing:
        - Messages starting with * (correction marker)
        - Repeated characters (e.g., 'helllp')

        Args:
            messages: List of message dicts with 'content' field

        Returns:
            Score from 0.0 (clean) to 1.0 (many errors)
        """
        if not messages:
            return 0.0

        error_count = 0
        total_messages = len(messages)

        # Regex for 3+ repeated chars (e.g., 'helllp', 'stresssed')
        repeated_pattern = re.compile(r"(.)\1{2,}")

        for msg in messages:
            content = msg.get("content", "")

            # Check for correction marker
            if content.startswith("*"):
                error_count += 1
                continue

            # Check for repeated characters
            if repeated_pattern.search(content):
                error_count += 1

        # Normalize: 50%+ error messages = 1.0
        rate = min(error_count / total_messages, 1.0) * 2.0
        return min(rate, 1.0)

    def _calculate_velocity(self, messages: list[dict[str, Any]]) -> float:
        """Calculate message velocity (speed between messages).

        Rapid-fire messages indicate urgency/stress.

        Args:
            messages: List of message dicts with 'created_at' field

        Returns:
            Score from 0.0 (relaxed) to 1.0 (rapid)
        """
        if len(messages) < 2:
            return 0.0

        intervals: list[float] = []

        for i in range(1, len(messages)):
            prev_time = self._parse_timestamp(messages[i - 1].get("created_at", ""))
            curr_time = self._parse_timestamp(messages[i].get("created_at", ""))

            if prev_time and curr_time:
                delta = (curr_time - prev_time).total_seconds()
                intervals.append(abs(delta))

        if not intervals:
            return 0.0

        avg_interval = sum(intervals) / len(intervals)

        # Normalize: fast = 1.0, slow = 0.0
        if avg_interval <= self._VELOCITY_RAPID_SECONDS:
            return 1.0
        if avg_interval >= self._VELOCITY_RELAXED_SECONDS:
            return 0.0

        # Linear interpolation
        range_span = self._VELOCITY_RELAXED_SECONDS - self._VELOCITY_RAPID_SECONDS
        normalized = (self._VELOCITY_RELAXED_SECONDS - avg_interval) / range_span
        return normalized

    def _parse_timestamp(self, timestamp_str: str) -> datetime | None:
        """Parse ISO timestamp string to datetime.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            datetime object or None if parsing fails
        """
        if not timestamp_str:
            return None
        try:
            # Handle Z suffix and various ISO formats
            clean = timestamp_str.replace("Z", "+00:00")
            return datetime.fromisoformat(clean)
        except (ValueError, TypeError):
            return None

    def _time_of_day_factor(self) -> float:
        """Calculate time-of-day cognitive load factor.

        Late night/early morning = higher load (fatigue)
        Core business hours = lower load

        Returns:
            Score from 0.2 (core hours) to 0.8 (late night)
        """
        current_hour = datetime.now().hour

        # Late night: 10pm (22) to 6am
        if current_hour >= self._LATE_NIGHT_START or current_hour < self._LATE_NIGHT_END:
            return 0.8

        # Core hours: 8am to 6pm
        if self._CORE_HOURS_START <= current_hour < self._CORE_HOURS_END:
            return 0.2

        # Transition periods (6-8am, 6-10pm): moderate load
        return 0.5

    def _calculate_weighted_score(self, factors: dict[str, float]) -> float:
        """Calculate weighted cognitive load score.

        Args:
            factors: Dict mapping factor names to their 0-1 scores

        Returns:
            Weighted average score between 0.0 and 1.0
        """
        score = 0.0
        for factor_name, weight in self.WEIGHTS.items():
            factor_value = factors.get(factor_name, 0.0)
            score += factor_value * weight
        return score

    def _determine_level(self, score: float) -> LoadLevel:
        """Determine load level enum from score.

        Thresholds define boundaries between levels:
        - score < 0.3 -> LOW
        - score >= 0.3 and < 0.5 -> MEDIUM
        - score >= 0.5 and < 0.85 -> HIGH
        - score >= 0.85 -> CRITICAL

        Args:
            score: Weighted score between 0.0 and 1.0

        Returns:
            LoadLevel enum value
        """
        if score >= self.THRESHOLDS["critical"]:
            return LoadLevel.CRITICAL
        if score >= self.THRESHOLDS["medium"]:
            return LoadLevel.HIGH
        if score >= self.THRESHOLDS["low"]:
            return LoadLevel.MEDIUM
        return LoadLevel.LOW

    def _get_recommendation(self, level: LoadLevel, factors: dict[str, float]) -> str:
        """Get response style recommendation based on load level.

        Args:
            level: Current cognitive load level
            factors: Individual factor scores (for future context-aware recommendations)

        Returns:
            Recommendation string: 'detailed', 'balanced', 'concise', or 'concise_urgent'
        """
        # Note: factors param reserved for future context-aware recommendations
        _ = factors  # Unused for now but part of interface

        if level == LoadLevel.CRITICAL:
            return "concise_urgent"
        if level == LoadLevel.HIGH:
            return "concise"
        if level == LoadLevel.MEDIUM:
            return "balanced"
        return "detailed"

    async def estimate_load(
        self,
        user_id: str,
        recent_messages: list[dict[str, Any]],
        session_id: str | None = None,
        calendar_density: float = 0.0,
    ) -> CognitiveLoadState:
        """Estimate current cognitive load for a user.

        Analyzes recent messages and context to determine how stressed
        or overwhelmed the user might be.

        Args:
            user_id: User identifier
            recent_messages: List of recent messages with 'content' and 'created_at'
            session_id: Optional session ID for tracking
            calendar_density: Optional calendar busy-ness score (0-1)

        Returns:
            CognitiveLoadState with level, score, factors, and recommendation
        """
        # Calculate individual factors
        avg_length = 0.0
        if recent_messages:
            lengths = [len(msg.get("content", "")) for msg in recent_messages]
            avg_length = sum(lengths) / len(lengths) if lengths else 0.0

        factors = {
            "message_brevity": self._normalize_brevity(avg_length),
            "typo_rate": self._calculate_typo_rate(recent_messages),
            "message_velocity": self._calculate_velocity(recent_messages),
            "calendar_density": calendar_density,
            "time_of_day": self._time_of_day_factor(),
        }

        # Calculate weighted score and determine level
        score = self._calculate_weighted_score(factors)
        level = self._determine_level(score)
        recommendation = self._get_recommendation(level, factors)

        state = CognitiveLoadState(
            level=level,
            score=score,
            factors=factors,
            recommendation=recommendation,
        )

        # Store snapshot for history
        await self._store_snapshot(user_id, state, session_id)

        logger.debug(
            "Estimated cognitive load for user %s: %s (score=%.2f)",
            user_id,
            level.value,
            score,
        )

        return state

    async def _store_snapshot(
        self,
        user_id: str,
        state: CognitiveLoadState,
        session_id: str | None = None,
    ) -> None:
        """Persist cognitive load snapshot to database.

        Args:
            user_id: User identifier
            state: Current cognitive load state
            session_id: Optional session identifier
        """
        try:
            self._db.table("cognitive_load_snapshots").insert(
                {
                    "user_id": user_id,
                    "load_level": state.level.value,
                    "load_score": state.score,
                    "factors": state.factors,
                    "session_id": session_id,
                }
            ).execute()
        except Exception as e:
            # Log but don't fail - snapshot storage is not critical
            logger.warning("Failed to store cognitive load snapshot: %s", e)

    async def get_current_load(self, user_id: str) -> CognitiveLoadState | None:
        """Get the most recent cognitive load state for a user.

        Args:
            user_id: User identifier

        Returns:
            Most recent CognitiveLoadState or None if no data
        """
        try:
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("*")
                .eq("user_id", user_id)
                .order("measured_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            snapshot = result.data[0]
            return CognitiveLoadState(
                level=LoadLevel(snapshot["load_level"]),
                score=snapshot["load_score"],
                factors=snapshot.get("factors", {}),
                recommendation=self._get_recommendation(
                    LoadLevel(snapshot["load_level"]),
                    snapshot.get("factors", {}),
                ),
            )
        except Exception as e:
            logger.error("Failed to get current cognitive load: %s", e)
            return None

    async def get_load_history(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get cognitive load history for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshot dicts ordered by most recent first
        """
        try:
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("*")
                .eq("user_id", user_id)
                .order("measured_at", desc=True)
                .limit(limit)
                .execute()
            )

            return result.data if result.data else []
        except Exception as e:
            logger.error("Failed to get cognitive load history: %s", e)
            return []
