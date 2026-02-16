"""Theory of Mind module for ARIA companion.

This module implements ARIA's ability to understand and adapt to the user's
mental state, including stress levels, confidence, emotional tone, and
support needs. This enables appropriate response adaptation.

Key features:
- StressLevel enum: relaxed, normal, elevated, high, critical
- ConfidenceLevel enum: very_uncertain to very_confident
- MentalState dataclass: captures full mental state snapshot
- TheoryOfMindModule: main class for inferring and tracking mental states
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.models.cognitive_load import LoadLevel

logger = logging.getLogger(__name__)


class StressLevel(str, Enum):
    """User stress level categories."""

    RELAXED = "relaxed"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    """User confidence level categories."""

    VERY_UNCERTAIN = "very_uncertain"
    UNCERTAIN = "uncertain"
    NEUTRAL = "neutral"
    CONFIDENT = "confident"
    VERY_CONFIDENT = "very_confident"


# Keyword patterns for confidence detection
HEDGING_WORDS: list[str] = [
    "maybe",
    "perhaps",
    "i think",
    "might",
    "could",
    "not sure",
    "i guess",
    "possibly",
    "probably",
    "sort of",
    "kind of",
    "i suppose",
    "i believe",
    "it seems",
]

CERTAINTY_WORDS: list[str] = [
    "definitely",
    "certainly",
    "i know",
    "clearly",
    "obviously",
    "absolutely",
    "must",
    "will",
    "for sure",
    "without a doubt",
    "undoubtedly",
    "positively",
]


@dataclass
class MentalState:
    """Current mental state inference for a user.

    Contains stress level, confidence, emotional tone, and support needs
    to guide ARIA's response style.
    """

    stress_level: StressLevel
    confidence: ConfidenceLevel
    current_focus: str
    emotional_tone: str
    needs_support: bool
    needs_space: bool
    recommended_response_style: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize mental state to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "stress_level": self.stress_level.value,
            "confidence": self.confidence.value,
            "current_focus": self.current_focus,
            "emotional_tone": self.emotional_tone,
            "needs_support": self.needs_support,
            "needs_space": self.needs_space,
            "recommended_response_style": self.recommended_response_style,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MentalState":
        """Create a MentalState from a dictionary.

        Args:
            data: Dictionary containing mental state data.

        Returns:
            MentalState instance.
        """
        return cls(
            stress_level=StressLevel(data.get("stress_level", "normal")),
            confidence=ConfidenceLevel(data.get("confidence", "neutral")),
            current_focus=data.get("current_focus", ""),
            emotional_tone=data.get("emotional_tone", "neutral"),
            needs_support=data.get("needs_support", False),
            needs_space=data.get("needs_space", False),
            recommended_response_style=data.get("recommended_response_style", "standard"),
        )


@dataclass
class StatePattern:
    """A detected behavioral pattern for a user."""

    pattern_type: str
    pattern_data: dict[str, Any]
    confidence: float = 0.5
    observed_count: int = 1
    last_observed: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize pattern to a dictionary."""
        return {
            "pattern_type": self.pattern_type,
            "pattern_data": self.pattern_data,
            "confidence": self.confidence,
            "observed_count": self.observed_count,
            "last_observed": self.last_observed.isoformat(),
        }


class TheoryOfMindModule:
    """Module for understanding and adapting to user mental states.

    This module handles:
    - Inferring mental states from message patterns and context
    - Integrating with CognitiveLoadMonitor for stress estimation
    - Detecting confidence levels from language patterns
    - Analyzing emotional tone via LLM
    - Recommending appropriate response styles
    - Storing and retrieving mental state history and patterns
    """

    # Emotional tone categories for LLM analysis
    EMOTIONAL_TONES: list[str] = [
        "frustrated",
        "anxious",
        "confident",
        "excited",
        "neutral",
        "overwhelmed",
        "curious",
        "focused",
    ]

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
        cognitive_load_monitor: CognitiveLoadMonitor | None = None,
    ) -> None:
        """Initialize the Theory of Mind module.

        Args:
            db_client: Optional Supabase client (will create if not provided).
            llm_client: Optional LLM client (will create if not provided).
            cognitive_load_monitor: Optional CognitiveLoadMonitor for stress
                estimation. If None, stress will be estimated from messages.
        """
        self._db = db_client or SupabaseClient.get_client()
        self._llm = llm_client or LLMClient()
        self._cognitive_load_monitor = cognitive_load_monitor

    def _map_load_to_stress(self, load_level: LoadLevel) -> StressLevel:
        """Map cognitive load level to stress level.

        Args:
            load_level: CognitiveLoadMonitor's LoadLevel.

        Returns:
            Corresponding StressLevel.
        """
        mapping: dict[LoadLevel, StressLevel] = {
            LoadLevel.LOW: StressLevel.RELAXED,
            LoadLevel.MEDIUM: StressLevel.NORMAL,
            LoadLevel.HIGH: StressLevel.ELEVATED,
            LoadLevel.CRITICAL: StressLevel.CRITICAL,
        }
        return mapping.get(load_level, StressLevel.NORMAL)

    def _estimate_stress_from_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> StressLevel:
        """Estimate stress level from message patterns when no monitor available.

        Analyzes message brevity, punctuation patterns, and urgency indicators.

        Args:
            messages: List of message dicts with 'content' field.

        Returns:
            Estimated StressLevel.
        """
        if not messages:
            return StressLevel.NORMAL

        stress_indicators = 0.0
        total_messages = len(messages)

        for msg in messages:
            content = msg.get("content", "").lower()

            # Short, terse messages indicate stress
            if len(content) < 20:
                stress_indicators += 0.3

            # Multiple exclamation marks indicate urgency
            if content.count("!") >= 2:
                stress_indicators += 0.2

            # All caps words indicate stress
            caps_words = sum(1 for word in content.split() if word.isupper() and len(word) > 2)
            stress_indicators += caps_words * 0.1

            # Urgency words
            urgency_words = ["asap", "urgent", "immediately", "now", "quickly", "emergency"]
            for word in urgency_words:
                if word in content:
                    stress_indicators += 0.2
                    break

        # Normalize score
        avg_stress = stress_indicators / total_messages

        if avg_stress >= 0.8:
            return StressLevel.CRITICAL
        if avg_stress >= 0.6:
            return StressLevel.HIGH
        if avg_stress >= 0.4:
            return StressLevel.ELEVATED
        if avg_stress >= 0.2:
            return StressLevel.NORMAL
        return StressLevel.RELAXED

    def _detect_confidence(self, messages: list[dict[str, Any]]) -> ConfidenceLevel:
        """Detect confidence level from message language patterns.

        Looks for hedging words (uncertainty) and certainty words.

        Args:
            messages: List of message dicts with 'content' field.

        Returns:
            Detected ConfidenceLevel.
        """
        if not messages:
            return ConfidenceLevel.NEUTRAL

        hedging_count = 0
        certainty_count = 0
        total_messages = len(messages)

        for msg in messages:
            content = msg.get("content", "").lower()

            # Check for hedging words
            for word in HEDGING_WORDS:
                if word in content:
                    hedging_count += 1
                    break  # Only count once per message

            # Check for certainty words
            for word in CERTAINTY_WORDS:
                if word in content:
                    certainty_count += 1
                    break

        # Calculate ratios
        hedging_ratio = hedging_count / total_messages
        certainty_ratio = certainty_count / total_messages

        # Determine confidence level
        if certainty_ratio >= 0.6:
            return ConfidenceLevel.VERY_CONFIDENT
        if certainty_ratio >= 0.3:
            return ConfidenceLevel.CONFIDENT
        if hedging_ratio >= 0.6:
            return ConfidenceLevel.VERY_UNCERTAIN
        if hedging_ratio >= 0.3:
            return ConfidenceLevel.UNCERTAIN
        return ConfidenceLevel.NEUTRAL

    async def _detect_emotional_tone(
        self,
        messages: list[dict[str, Any]],
    ) -> str:
        """Detect emotional tone from messages using LLM analysis.

        Args:
            messages: List of message dicts with 'content' field.

        Returns:
            Detected emotional tone string.
        """
        if not messages:
            return "neutral"

        # Combine recent message content
        combined_content = " ".join(
            msg.get("content", "")
            for msg in messages[-5:]  # Last 5 messages
        )

        if not combined_content.strip():
            return "neutral"

        prompt = f"""Analyze the emotional tone of this user's messages.
Return ONLY one of these tones: frustrated, anxious, confident, excited, neutral, overwhelmed, curious, focused

User messages:
{combined_content[:1000]}

Tone:"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=20,
            )

            tone = response.strip().lower()

            # Validate response is a known tone
            if tone in self.EMOTIONAL_TONES:
                return tone
            return "neutral"

        except Exception as e:
            logger.warning(
                "Failed to detect emotional tone",
                extra={"error": str(e)},
            )
            return "neutral"

    async def _identify_focus(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None,
    ) -> str:
        """Identify the user's current focus/topic from messages.

        Args:
            messages: List of message dicts with 'content' field.
            context: Optional additional context (current goal, etc.).

        Returns:
            String describing current focus.
        """
        if not messages:
            # Check context for focus
            if context and "current_goal" in context:
                return str(context["current_goal"])
            return "unknown"

        # Combine recent messages
        combined_content = " ".join(msg.get("content", "") for msg in messages[-3:])

        if not combined_content.strip():
            return "unknown"

        # Build context string
        context_str = ""
        if context:
            context_items = [f"{k}: {v}" for k, v in context.items() if v]
            if context_items:
                context_str = "\n\nContext:\n" + "\n".join(f"- {item}" for item in context_items)

        prompt = f"""Extract the main topic or focus from this user's recent messages.
Return a brief phrase (2-5 words) describing what the user is focused on.

User messages:
{combined_content[:500]}
{context_str}

Focus:"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=30,
            )

            focus = response.strip()
            return focus if focus else "unknown"

        except Exception as e:
            logger.warning(
                "Failed to identify focus",
                extra={"error": str(e)},
            )
            return "unknown"

    def _recommend_response_style(
        self,
        stress_level: StressLevel,
        needs_support: bool,
        needs_space: bool,
    ) -> str:
        """Recommend response style based on mental state.

        Args:
            stress_level: Current stress level.
            needs_support: Whether user needs emotional support.
            needs_space: Whether user needs space.

        Returns:
            Response style string: concise, detailed, supportive, space, standard
        """
        if needs_space:
            return "space"
        if stress_level in [StressLevel.HIGH, StressLevel.CRITICAL]:
            return "concise"
        if needs_support:
            return "supportive"
        if stress_level == StressLevel.RELAXED:
            return "detailed"
        return "standard"

    async def infer_state(
        self,
        user_id: str,
        recent_messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> MentalState:
        """Infer the current mental state for a user.

        This is the main entry point for mental state inference. It combines
        cognitive load data (if available) with message analysis.

        Args:
            user_id: User identifier.
            recent_messages: List of recent messages with 'content' and 'created_at'.
            context: Optional additional context (current goal, etc.).
            session_id: Optional session ID for tracking.

        Returns:
            MentalState with inferred mental state.
        """
        # 1. Determine stress level
        if self._cognitive_load_monitor:
            try:
                load_state = await self._cognitive_load_monitor.estimate_load(
                    user_id=user_id,
                    recent_messages=recent_messages,
                    session_id=session_id,
                )
                stress_level = self._map_load_to_stress(load_state.level)
            except Exception as e:
                logger.warning(
                    "CognitiveLoadMonitor failed, using fallback",
                    extra={"user_id": user_id, "error": str(e)},
                )
                stress_level = self._estimate_stress_from_messages(recent_messages)
        else:
            stress_level = self._estimate_stress_from_messages(recent_messages)

        # 2. Detect confidence
        confidence = self._detect_confidence(recent_messages)

        # 3. Identify focus (LLM-based)
        focus = await self._identify_focus(recent_messages, context)

        # 4. Detect emotional tone (LLM-based)
        tone = await self._detect_emotional_tone(recent_messages)

        # 5. Determine support needs
        needs_support = stress_level in [StressLevel.HIGH, StressLevel.CRITICAL] or tone in [
            "frustrated",
            "anxious",
            "overwhelmed",
        ]
        needs_space = tone in ["frustrated", "overwhelmed"]

        # 6. Recommend style
        style = self._recommend_response_style(stress_level, needs_support, needs_space)

        state = MentalState(
            stress_level=stress_level,
            confidence=confidence,
            current_focus=focus,
            emotional_tone=tone,
            needs_support=needs_support,
            needs_space=needs_space,
            recommended_response_style=style,
        )

        logger.debug(
            "Inferred mental state for user %s: stress=%s, confidence=%s, tone=%s",
            user_id,
            stress_level.value,
            confidence.value,
            tone,
        )

        return state

    async def store_state(
        self,
        user_id: str,
        state: MentalState,
        session_id: str | None = None,
    ) -> str:
        """Persist mental state to database.

        Args:
            user_id: User identifier.
            state: MentalState to persist.
            session_id: Optional session ID for tracking.

        Returns:
            The ID of the stored state record.
        """
        state_id = str(uuid.uuid4())

        try:
            self._db.table("user_mental_states").insert(
                {
                    "id": state_id,
                    "user_id": user_id,
                    "stress_level": state.stress_level.value,
                    "confidence": state.confidence.value,
                    "current_focus": state.current_focus,
                    "emotional_tone": state.emotional_tone,
                    "needs_support": state.needs_support,
                    "needs_space": state.needs_space,
                    "recommended_response_style": state.recommended_response_style,
                    "session_id": session_id,
                    "inferred_at": datetime.now(UTC).isoformat(),
                }
            ).execute()

            logger.info(
                "Stored mental state",
                extra={
                    "state_id": state_id,
                    "user_id": user_id,
                    "stress_level": state.stress_level.value,
                },
            )

            return state_id

        except Exception:
            logger.exception(
                "Failed to store mental state",
                extra={"user_id": user_id},
            )
            raise

    async def get_current_state(self, user_id: str) -> MentalState | None:
        """Get the most recent mental state for a user.

        Args:
            user_id: User identifier.

        Returns:
            Most recent MentalState or None if no data.
        """
        try:
            result = (
                self._db.table("user_mental_states")
                .select("*")
                .eq("user_id", user_id)
                .order("inferred_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            row = result.data[0]
            return MentalState(
                stress_level=StressLevel(row["stress_level"]),
                confidence=ConfidenceLevel(row["confidence"]),
                current_focus=row.get("current_focus", ""),
                emotional_tone=row["emotional_tone"],
                needs_support=row.get("needs_support", False),
                needs_space=row.get("needs_space", False),
                recommended_response_style=row["recommended_response_style"],
            )

        except Exception as e:
            logger.error(
                "Failed to get current mental state",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def get_patterns(self, user_id: str) -> list[StatePattern]:
        """Get detected behavioral patterns for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of StatePattern objects.
        """
        try:
            result = (
                self._db.table("user_state_patterns")
                .select("*")
                .eq("user_id", user_id)
                .order("last_observed", desc=True)
                .limit(50)
                .execute()
            )

            if not result.data:
                return []

            patterns = []
            for row in result.data:
                last_observed = datetime.fromisoformat(row["last_observed"].replace("Z", "+00:00"))
                patterns.append(
                    StatePattern(
                        pattern_type=row["pattern_type"],
                        pattern_data=row["pattern_data"],
                        confidence=row.get("confidence", 0.5),
                        observed_count=row.get("observed_count", 1),
                        last_observed=last_observed,
                    )
                )

            return patterns

        except Exception as e:
            logger.error(
                "Failed to get state patterns",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def record_pattern(
        self,
        user_id: str,
        pattern_type: str,
        pattern_data: dict[str, Any],
    ) -> None:
        """Record or update a behavioral pattern for a user.

        If a pattern of this type already exists, it increments the observed
        count and updates confidence. Otherwise, creates a new pattern.

        Args:
            user_id: User identifier.
            pattern_type: Type of pattern (e.g., 'monday_stress', 'late_night_focus').
            pattern_data: Pattern-specific data.
        """
        try:
            # Check for existing pattern
            existing = (
                self._db.table("user_state_patterns")
                .select("*")
                .eq("user_id", user_id)
                .eq("pattern_type", pattern_type)
                .limit(1)
                .execute()
            )

            now = datetime.now(UTC).isoformat()

            if existing.data:
                # Update existing pattern
                row = existing.data[0]
                new_count = row.get("observed_count", 1) + 1
                # Increase confidence with more observations, cap at 0.95
                new_confidence = min(0.95, row.get("confidence", 0.5) + 0.05)

                self._db.table("user_state_patterns").update(
                    {
                        "observed_count": new_count,
                        "confidence": new_confidence,
                        "last_observed": now,
                        "pattern_data": pattern_data,  # Update with latest data
                    }
                ).eq("id", row["id"]).execute()

                logger.debug(
                    "Updated pattern %s for user %s (count=%d)",
                    pattern_type,
                    user_id,
                    new_count,
                )
            else:
                # Create new pattern
                self._db.table("user_state_patterns").insert(
                    {
                        "user_id": user_id,
                        "pattern_type": pattern_type,
                        "pattern_data": pattern_data,
                        "confidence": 0.5,
                        "observed_count": 1,
                        "last_observed": now,
                    }
                ).execute()

                logger.debug(
                    "Created pattern %s for user %s",
                    pattern_type,
                    user_id,
                )

        except Exception as e:
            logger.warning(
                "Failed to record pattern",
                extra={
                    "user_id": user_id,
                    "pattern_type": pattern_type,
                    "error": str(e),
                },
            )
