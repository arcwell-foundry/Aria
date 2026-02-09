"""Personality Calibration from Onboarding Data (US-919).

Calibrates ARIA's personality to match each user's communication preferences.
Reads the Digital Twin writing fingerprint and maps dimensions to personality
trait adjustments. NOT mimicry -- ARIA maintains her own personality but adjusts
the dial on directness, warmth, assertiveness, detail orientation, and formality.

Calibration is stored in the Digital Twin for use by all ARIA features.
Recalibrates on every user edit to an ARIA draft (highest-signal event).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel

from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
from src.memory.episodic import Episode, EpisodicMemory

logger = logging.getLogger(__name__)


class PersonalityCalibration(BaseModel):
    """ARIA's personality adjustments for a specific user.

    Each trait is a float from 0 to 1 representing a spectrum:
    - directness: 0=diplomatic, 1=blunt
    - warmth: 0=clinical, 1=personal
    - assertiveness: 0=suggestive, 1=commanding
    - detail_orientation: 0=high-level, 1=granular
    - formality: 0=casual, 1=formal
    """

    directness: float = 0.5
    warmth: float = 0.5
    assertiveness: float = 0.5
    detail_orientation: float = 0.5
    formality: float = 0.5

    tone_guidance: str = ""
    example_adjustments: list[str] = []


class PersonalityCalibrator:
    """Calibrates ARIA's personality to match user preferences.

    Reads Digital Twin writing fingerprint and maps dimensions
    to personality trait adjustments. Stored in Digital Twin
    for use by all ARIA features.
    """

    def __init__(self) -> None:
        """Initialize with Supabase client and episodic memory."""
        self._db = SupabaseClient.get_client()
        self._episodic = EpisodicMemory()

    async def calibrate(self, user_id: str) -> PersonalityCalibration:
        """Generate personality calibration from Digital Twin data.

        Reads the writing fingerprint, maps to personality traits,
        generates tone guidance, stores calibration, records episodic
        event, and updates readiness score.

        Args:
            user_id: The user to calibrate for.

        Returns:
            PersonalityCalibration with computed traits and guidance.
        """
        fingerprint = await self._get_writing_fingerprint(user_id)

        if not fingerprint:
            return self._default_calibration()

        calibration = PersonalityCalibration(
            directness=fingerprint.get("directness", 0.5),
            warmth=fingerprint.get("warmth", 0.5),
            assertiveness=fingerprint.get("assertiveness", 0.5),
            detail_orientation=self._infer_detail_orientation(fingerprint),
            formality=fingerprint.get("formality_index", 0.5),
        )

        calibration.tone_guidance = self._generate_tone_guidance(calibration, fingerprint)
        calibration.example_adjustments = self._generate_examples(calibration)

        # Store calibration in Digital Twin
        await self._store_calibration(user_id, calibration)

        # Record episodic memory
        await self._record_episodic_event(user_id, calibration)

        # Update readiness score
        await self._update_readiness(user_id)

        # Audit log
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=f"personality_calibration_{user_id}",
            metadata={
                "event": "onboarding_personality_calibrated",
                "directness": calibration.directness,
                "warmth": calibration.warmth,
                "assertiveness": calibration.assertiveness,
                "formality": calibration.formality,
            },
            suppress_errors=True,
        )

        return calibration

    def _infer_detail_orientation(self, fingerprint: dict[str, Any]) -> float:
        """Infer detail preference from writing patterns.

        Long sentences + long paragraphs + data references = detail-oriented.
        Short punchy style = high-level preference.

        Args:
            fingerprint: Writing style fingerprint dict.

        Returns:
            Detail orientation score clamped to [0.0, 1.0].
        """
        avg_sentence = fingerprint.get("avg_sentence_length", 15)
        paragraph_style = fingerprint.get("paragraph_style", "medium")
        data_driven = fingerprint.get("data_driven", False)

        score = 0.5

        if avg_sentence > 20:
            score += 0.15
        elif avg_sentence < 10:
            score -= 0.15

        if paragraph_style == "long_detailed":
            score += 0.15
        elif paragraph_style == "short_punchy":
            score -= 0.15

        if data_driven:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _generate_tone_guidance(
        self,
        cal: PersonalityCalibration,
        fingerprint: dict[str, Any] | None = None,
    ) -> str:
        """Generate a prompt-ready tone guidance string.

        Incorporates all 20 writing fingerprint fields when available,
        producing a concise guidance block (3-4 sentences) for LLM
        prompt injection.

        Args:
            cal: The computed calibration.
            fingerprint: Optional full writing fingerprint dict for
                extended style dimensions.

        Returns:
            Concise guidance string for LLM prompts.
        """
        parts: list[str] = []
        fp = fingerprint or {}

        # --- Core 5 traits ---
        if cal.directness > 0.7:
            parts.append("Be direct and concise.")
        elif cal.directness < 0.3:
            parts.append("Be diplomatic; frame suggestions gently.")

        if cal.warmth > 0.7:
            parts.append("Use a warm, personal tone.")
        elif cal.warmth < 0.3:
            parts.append("Keep tone professional and focused.")

        if cal.assertiveness > 0.7:
            parts.append("Be confident in recommendations.")
        elif cal.assertiveness < 0.3:
            parts.append("Present options rather than directives.")

        if cal.detail_orientation > 0.7:
            parts.append("Include detailed analysis and data points.")
        elif cal.detail_orientation < 0.3:
            parts.append("Keep it high-level; lead with conclusions.")

        if cal.formality > 0.7:
            parts.append("Use formal, professional language.")
        elif cal.formality < 0.3:
            parts.append("Keep it casual and conversational.")

        # --- Extended fingerprint dimensions (P2-8) ---

        # Opening/closing style
        opening = fp.get("opening_style", "")
        closing = fp.get("closing_style", "")
        if opening or closing:
            style_hints: list[str] = []
            if opening:
                style_hints.append(f"open with a {opening} style")
            if closing:
                style_hints.append(f"close with a {closing} style")
            parts.append("When drafting messages, " + " and ".join(style_hints) + ".")

        # Rhetorical style
        rhetorical = fp.get("rhetorical_style", "")
        if rhetorical:
            parts.append(f"Use a {rhetorical} argumentation approach.")

        # Data-driven
        if fp.get("data_driven"):
            parts.append("Include evidence and data to support points.")

        # Emoji usage
        emoji_usage = fp.get("emoji_usage", "")
        if emoji_usage == "frequent":
            parts.append("Use emojis occasionally to match their style.")
        elif emoji_usage == "never":
            parts.append("Avoid emojis entirely.")

        # Punctuation preferences
        punctuation_notes: list[str] = []
        if fp.get("uses_em_dashes"):
            punctuation_notes.append("em dashes")
        if fp.get("uses_semicolons"):
            punctuation_notes.append("semicolons")
        if fp.get("ellipsis_usage") == "frequent":
            punctuation_notes.append("ellipses")
        if punctuation_notes:
            parts.append(
                "Mirror their punctuation: use " + ", ".join(punctuation_notes) + "."
            )

        # Exclamation frequency
        excl = fp.get("exclamation_frequency", "")
        if excl == "frequent":
            parts.append("Match their enthusiasm with occasional exclamation marks.")
        elif excl == "never":
            parts.append("Avoid exclamation marks.")

        # Paragraph style
        para = fp.get("paragraph_style", "")
        if para == "short_punchy":
            parts.append("Keep paragraphs short and punchy.")
        elif para == "long_detailed":
            parts.append("Use longer, detailed paragraphs.")

        # Lexical diversity / vocabulary
        lexical = fp.get("lexical_diversity", "")
        if lexical == "high":
            parts.append("Use varied, sophisticated vocabulary.")
        elif lexical == "low":
            parts.append("Use simple, consistent vocabulary.")

        if not parts:
            return "Balanced, professional tone with moderate warmth."

        # Cap at 3-4 sentences to avoid bloating prompts
        return " ".join(parts[:8])

    def _generate_examples(self, cal: PersonalityCalibration) -> list[str]:
        """Generate example phrasings showing calibrated style.

        Provides concrete before/after examples so the LLM understands
        the desired tone shift.

        Args:
            cal: The computed calibration.

        Returns:
            List of example adjustment strings.
        """
        examples: list[str] = []

        if cal.directness > 0.7:
            examples.append(
                "Instead of 'You might want to consider...' "
                "-> 'I'd push back on that discount.'"
            )
        elif cal.directness < 0.3:
            examples.append(
                "Instead of 'Don't do that.' "
                "-> 'Have you considered holding at 15%?'"
            )

        if cal.warmth > 0.7:
            examples.append(
                "Open with 'Hey [Name], hope you had a great weekend -' "
                "before getting to business."
            )

        if cal.assertiveness > 0.7:
            examples.append(
                "Instead of 'We could maybe try...' "
                "-> 'I recommend we move forward with...'"
            )

        return examples

    def _default_calibration(self) -> PersonalityCalibration:
        """Default calibration when no fingerprint exists.

        Returns:
            Neutral calibration with balanced professional guidance.
        """
        return PersonalityCalibration(
            tone_guidance=(
                "Balanced professional tone. Direct but warm. "
                "Data-informed but not overwhelming."
            ),
        )

    async def _get_writing_fingerprint(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve writing fingerprint from Digital Twin.

        Args:
            user_id: The user whose fingerprint to fetch.

        Returns:
            Writing style dict or None if not available.
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                prefs: dict[str, Any] = row.get("preferences", {}) or {}
                dt: dict[str, Any] = prefs.get("digital_twin", {})
                ws: dict[str, Any] | None = dt.get("writing_style")
                return ws
        except Exception as e:
            logger.warning("Failed to get writing fingerprint: %s", e)
        return None

    async def _store_calibration(
        self,
        user_id: str,
        calibration: PersonalityCalibration,
    ) -> None:
        """Store calibration in Digital Twin (user_settings).

        Merges into existing preferences to avoid overwriting
        other Digital Twin data.

        Args:
            user_id: The user whose calibration to store.
            calibration: The computed calibration.
        """
        try:
            # Read current preferences to merge
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            current_prefs: dict[str, Any] = {}
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                current_prefs = row.get("preferences", {}) or {}

            digital_twin = current_prefs.get("digital_twin", {})
            digital_twin["personality_calibration"] = calibration.model_dump()
            digital_twin["personality_calibrated_at"] = datetime.now(UTC).isoformat()
            current_prefs["digital_twin"] = digital_twin

            (
                self._db.table("user_settings")
                .update({"preferences": current_prefs})
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as e:
            logger.warning("Failed to store personality calibration: %s", e)

    async def _record_episodic_event(
        self,
        user_id: str,
        calibration: PersonalityCalibration,
    ) -> None:
        """Record calibration event to episodic memory.

        Args:
            user_id: The user who was calibrated.
            calibration: The computed calibration.
        """
        try:
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_personality_calibrated",
                content=(
                    f"Calibrated personality profile: "
                    f"directness={calibration.directness:.1f}, "
                    f"warmth={calibration.warmth:.1f}, "
                    f"assertiveness={calibration.assertiveness:.1f}, "
                    f"formality={calibration.formality:.1f}, "
                    f"detail={calibration.detail_orientation:.1f}"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "onboarding_step": "personality_calibration",
                    "directness": calibration.directness,
                    "warmth": calibration.warmth,
                    "assertiveness": calibration.assertiveness,
                    "formality": calibration.formality,
                    "detail_orientation": calibration.detail_orientation,
                },
            )
            await self._episodic.store_episode(episode)
        except Exception as e:
            logger.warning("Episodic record failed during calibration: %s", e)

    async def _update_readiness(self, user_id: str) -> None:
        """Update digital_twin readiness after calibration.

        Personality calibration pushes digital_twin readiness higher
        (writing analysis brings it to ~40, calibration adds up to ~60).

        Args:
            user_id: The user whose readiness to update.
        """
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(user_id, {"digital_twin": 60.0})
        except Exception as e:
            logger.warning("Readiness update failed during calibration: %s", e)

    async def get_calibration(
        self,
        user_id: str,
    ) -> PersonalityCalibration | None:
        """Retrieve stored calibration for use in features.

        Args:
            user_id: The user whose calibration to retrieve.

        Returns:
            PersonalityCalibration if stored, None otherwise.
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                prefs: dict[str, Any] = row.get("preferences", {}) or {}
                dt = prefs.get("digital_twin", {})
                cal_data = dt.get("personality_calibration")
                if cal_data:
                    return PersonalityCalibration(**cal_data)
        except Exception as e:
            logger.warning("Failed to get personality calibration: %s", e)
        return None
