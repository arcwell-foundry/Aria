"""Personality system for ARIA companion.

This module implements ARIA's consistent character with opinions,
pushback capability, and personality traits that adapt to user preferences.

Key features:
- TraitLevel enum for personality trait levels (LOW=1, MODERATE=2, HIGH=3)
- PersonalityProfile with 5 core traits: directness, warmth, assertiveness, humor, formality
- OpinionResult for structured opinion formation
- PersonalityService for managing personality and forming opinions
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.memory.episodic import EpisodicMemory
from src.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


class TraitLevel(IntEnum):
    """Personality trait levels on a 1-3 scale."""

    LOW = 1
    MODERATE = 2
    HIGH = 3


@dataclass
class PersonalityProfile:
    """ARIA's personality profile with 5 core traits.

    Each trait is on a 1-3 scale (TraitLevel):
    - 1 (LOW): More reserved/indirect
    - 2 (MODERATE): Balanced
    - 3 (HIGH): More pronounced/direct
    """

    directness: int = 3  # HIGH - Direct but not rude
    warmth: int = 2  # MODERATE - Professional warmth
    assertiveness: int = 2  # MODERATE - Willing to push back
    humor: int = 2  # MODERATE - Occasional appropriate humor
    formality: int = 1  # LOW - Conversational, not stiff
    adapted_for_user: bool = False
    adaptation_notes: str = ""

    def __post_init__(self) -> None:
        """Validate trait values are within valid range."""
        for trait_name in ["directness", "warmth", "assertiveness", "humor", "formality"]:
            value = getattr(self, trait_name)
            if not 1 <= value <= 3:
                msg = f"{trait_name} must be between 1 and 3, got {value}"
                raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "directness": self.directness,
            "warmth": self.warmth,
            "assertiveness": self.assertiveness,
            "humor": self.humor,
            "formality": self.formality,
            "adapted_for_user": self.adapted_for_user,
            "adaptation_notes": self.adaptation_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityProfile":
        """Create a PersonalityProfile from a dictionary.

        Args:
            data: Dictionary containing profile data.

        Returns:
            PersonalityProfile instance.
        """
        return cls(
            directness=data.get("directness", 3),
            warmth=data.get("warmth", 2),
            assertiveness=data.get("assertiveness", 2),
            humor=data.get("humor", 2),
            formality=data.get("formality", 1),
            adapted_for_user=data.get("adapted_for_user", False),
            adaptation_notes=data.get("adaptation_notes", ""),
        )


@dataclass
class OpinionResult:
    """Result of opinion formation on a topic.

    Contains the formed opinion, confidence level, supporting evidence,
    and whether ARIA should push back on the user's approach.
    """

    has_opinion: bool
    opinion: str = ""
    confidence: float = 0.0
    supporting_evidence: list[str] = field(default_factory=list)
    should_push_back: bool = False
    pushback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize opinion to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "has_opinion": self.has_opinion,
            "opinion": self.opinion,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "should_push_back": self.should_push_back,
            "pushback_reason": self.pushback_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpinionResult":
        """Create an OpinionResult from a dictionary.

        Args:
            data: Dictionary containing opinion data.

        Returns:
            OpinionResult instance.
        """
        return cls(
            has_opinion=data.get("has_opinion", False),
            opinion=data.get("opinion", ""),
            confidence=data.get("confidence", 0.0),
            supporting_evidence=data.get("supporting_evidence", []),
            should_push_back=data.get("should_push_back", False),
            pushback_reason=data.get("pushback_reason", ""),
        )


class PersonalityService:
    """Service for managing ARIA's personality and forming opinions.

    This service handles:
    - Loading and storing user-specific personality adaptations
    - Forming opinions based on semantic memory facts
    - Generating pushback when warranted
    - Recording and tracking opinion outcomes
    - Adapting personality based on interaction patterns
    """

    def __init__(self) -> None:
        """Initialize the personality service."""
        self._supabase = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._semantic_memory = SemanticMemory()
        self._episodic_memory = EpisodicMemory()

    async def get_profile(self, user_id: str) -> PersonalityProfile:
        """Get the personality profile for a user.

        Returns the user's adapted profile if it exists, otherwise
        returns the default ARIA personality.

        Args:
            user_id: The user's ID.

        Returns:
            PersonalityProfile for the user.
        """
        try:
            response = (
                self._supabase.table("companion_personality_profiles")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            if response.data:
                row = response.data[0]
                if isinstance(row, dict):
                    return PersonalityProfile(
                        directness=int(row.get("directness", 3)),
                        warmth=int(row.get("warmth", 2)),
                        assertiveness=int(row.get("assertiveness", 2)),
                        humor=int(row.get("humor", 2)),
                        formality=int(row.get("formality", 1)),
                        adapted_for_user=bool(row.get("adapted_for_user", False)),
                        adaptation_notes=str(row.get("adaptation_notes", "")),
                    )
        except Exception as e:
            logger.warning(
                "Failed to load personality profile, using defaults",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Return default profile
        return PersonalityProfile()

    async def form_opinion(
        self,
        user_id: str,
        topic: str,
        context: dict[str, Any] | None = None,
    ) -> OpinionResult | None:
        """Form an opinion on a topic based on semantic memory.

        Queries semantic memory for relevant facts and uses the LLM
        to synthesize an opinion. Returns None if there's insufficient
        basis for forming an opinion.

        Args:
            user_id: The user's ID.
            topic: The topic to form an opinion on.
            context: Optional additional context for opinion formation.

        Returns:
            OpinionResult if an opinion can be formed, None otherwise.
        """
        try:
            # Search for relevant facts in semantic memory
            facts = await self._semantic_memory.search_facts(
                user_id=user_id,
                query=topic,
                min_confidence=0.5,
                limit=10,
            )

            if not facts:
                logger.debug(
                    "No facts found for opinion formation",
                    extra={"user_id": user_id, "topic": topic},
                )
                return None

            # Format facts for the LLM
            formatted_facts = "\n".join(
                f"- {fact.subject} {fact.predicate} {fact.object} (confidence: {fact.confidence:.2f})"
                for fact in facts[:5]  # Limit to top 5 most relevant
            )

            # Get user's personality profile for tone calibration
            profile = await self.get_profile(user_id)

            # Build the prompt
            context_str = ""
            if context:
                context_items = [f"{k}: {v}" for k, v in context.items()]
                context_str = "\n\nAdditional context:\n" + "\n".join(f"- {item}" for item in context_items)

            prompt = f"""Based on this information, form an opinion on: {topic}

Relevant facts from memory:
{formatted_facts}
{context_str}

Form a clear, direct opinion. Be willing to push back if the evidence suggests a mistake or better alternative.

Personality traits to calibrate tone:
- Directness: {profile.directness}/3 (higher = more straightforward)
- Assertiveness: {profile.assertiveness}/3 (higher = more willing to challenge)

Output ONLY valid JSON with this structure:
{{
    "has_opinion": true or false,
    "opinion": "your direct opinion on this topic",
    "confidence": 0.0 to 1.0,
    "supporting_evidence": ["list of key facts that support this"],
    "should_push_back": true or false,
    "pushback_reason": "reason to push back, if applicable"
}}"""

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                task=TaskType.ONBOARD_PERSONALITY,
            )

            # Parse JSON response
            # Handle potential markdown code blocks
            response_text = response.strip()
            if response_text.startswith("```"):
                # Remove markdown code block markers
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()

            opinion_data = json.loads(response_text)
            return OpinionResult.from_dict(opinion_data)

        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse opinion response as JSON",
                extra={"user_id": user_id, "topic": topic, "error": str(e)},
            )
            return None
        except Exception:
            logger.exception(
                "Failed to form opinion",
                extra={"user_id": user_id, "topic": topic},
            )
            return None

    async def generate_pushback(
        self,
        user_id: str,
        user_statement: str,
        opinion: OpinionResult,
    ) -> str | None:
        """Generate pushback on a user's statement.

        Only generates pushback if the opinion indicates it's warranted.
        Uses episodic memory to reference relevant shared history for
        more natural and contextual pushback.

        Args:
            user_id: The user's ID.
            user_statement: The user's statement to push back on.
            opinion: The formed opinion with pushback reasoning.

        Returns:
            Pushback message if warranted, None otherwise.
        """
        if not opinion.should_push_back:
            return None

        try:
            # Search for relevant shared history in episodic memory
            episodes = await self._episodic_memory.semantic_search(
                user_id=user_id,
                query=f"decisions outcomes {opinion.pushback_reason}",
                limit=3,
            )

            # Format shared history reference
            history_reference = ""
            if episodes:
                # Use the most relevant episode as a reference point
                episode = episodes[0]
                history_reference = f"\n\nRelevant history: {episode.content[:200]}..."

            # Get personality profile for tone
            profile = await self.get_profile(user_id)

            prompt = f"""Generate pushback on this user statement: "{user_statement}"

Reason for pushback: {opinion.pushback_reason}

Your opinion: {opinion.opinion}

Supporting evidence:
{chr(10).join(f"- {e}" for e in opinion.supporting_evidence[:3])}
{history_reference}

Personality traits:
- Directness: {profile.directness}/3
- Assertiveness: {profile.assertiveness}/3
- Warmth: {profile.warmth}/3

Generate a natural pushback message. Start with "Honestly?" or "I'd push back on that..." and explain why, referencing shared history if available. Be direct but not rude. Keep it concise (2-3 sentences max).

Output ONLY the pushback message, no JSON or formatting."""

            pushback = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=200,
                task=TaskType.GENERAL,
            )

            return pushback.strip()

        except Exception:
            logger.exception(
                "Failed to generate pushback",
                extra={"user_id": user_id},
            )
            return None

    async def record_opinion(
        self,
        user_id: str,
        topic: str,
        opinion: OpinionResult,
        pushback_generated: str | None = None,
    ) -> str:
        """Record an opinion in the database.

        Stores the formed opinion for later reference and outcome tracking.

        Args:
            user_id: The user's ID.
            topic: The topic the opinion is about.
            opinion: The formed opinion result.
            pushback_generated: Optional pushback message that was generated.

        Returns:
            The ID of the recorded opinion.
        """
        opinion_id = str(uuid.uuid4())

        try:
            self._supabase.table("companion_opinions").insert({
                "id": opinion_id,
                "user_id": user_id,
                "topic": topic,
                "opinion": opinion.opinion,
                "confidence": opinion.confidence,
                "supporting_evidence": json.dumps(opinion.supporting_evidence),
                "should_push_back": opinion.should_push_back,
                "pushback_reason": opinion.pushback_reason,
                "pushback_generated": pushback_generated,
                "created_at": datetime.now(UTC).isoformat(),
            }).execute()

            logger.info(
                "Recorded opinion",
                extra={
                    "opinion_id": opinion_id,
                    "user_id": user_id,
                    "topic": topic,
                    "should_push_back": opinion.should_push_back,
                },
            )

            return opinion_id

        except Exception:
            logger.exception(
                "Failed to record opinion",
                extra={"user_id": user_id, "topic": topic},
            )
            raise

    async def update_pushback_outcome(
        self,
        opinion_id: str,
        user_accepted: bool,
    ) -> None:
        """Update the outcome of a pushback interaction.

        Tracks whether the user accepted ARIA's pushback advice,
        which informs future personality adaptation.

        Args:
            opinion_id: The ID of the opinion.
            user_accepted: Whether the user accepted the pushback.
        """
        try:
            self._supabase.table("companion_opinions").update({
                "user_accepted_pushback": user_accepted,
            }).eq("id", opinion_id).execute()

            logger.info(
                "Updated pushback outcome",
                extra={
                    "opinion_id": opinion_id,
                    "user_accepted": user_accepted,
                },
            )

        except Exception:
            logger.exception(
                "Failed to update pushback outcome",
                extra={"opinion_id": opinion_id},
            )
            raise

    async def adapt_personality(self, user_id: str) -> PersonalityProfile:
        """Adapt personality based on interaction patterns.

        Analyzes past opinion outcomes and interactions to adjust
        personality traits for better user alignment.

        Args:
            user_id: The user's ID.

        Returns:
            Updated PersonalityProfile after adaptation.
        """
        try:
            # Get recent opinion outcomes
            response = (
                self._supabase.table("companion_opinions")
                .select("*")
                .eq("user_id", user_id)
                .not_.is_("user_accepted_pushback", "null")
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )

            if not response.data or len(response.data) < 5:
                # Not enough data for adaptation
                return await self.get_profile(user_id)

            # Calculate acceptance rate
            accepted_count = sum(
                1 for row in response.data
                if isinstance(row, dict) and bool(row.get("user_accepted_pushback"))
            )
            acceptance_rate = accepted_count / len(response.data)

            # Get current profile
            current_profile = await self.get_profile(user_id)

            # Adapt based on acceptance patterns
            adaptation_notes = []

            # If user frequently rejects pushback, reduce assertiveness
            if acceptance_rate < 0.3 and current_profile.assertiveness > 1:
                current_profile.assertiveness = max(1, current_profile.assertiveness - 1)
                adaptation_notes.append("Reduced assertiveness due to low pushback acceptance")

            # If user frequently accepts pushback, may increase directness
            elif acceptance_rate > 0.7 and current_profile.directness < 3:
                current_profile.directness = min(3, current_profile.directness + 1)
                adaptation_notes.append("Increased directness due to high pushback acceptance")

            # Update profile in database
            current_profile.adapted_for_user = True
            current_profile.adaptation_notes = "; ".join(adaptation_notes)

            self._supabase.table("companion_personality_profiles").upsert({
                "user_id": user_id,
                "directness": current_profile.directness,
                "warmth": current_profile.warmth,
                "assertiveness": current_profile.assertiveness,
                "humor": current_profile.humor,
                "formality": current_profile.formality,
                "adapted_for_user": current_profile.adapted_for_user,
                "adaptation_notes": current_profile.adaptation_notes,
                "updated_at": datetime.now(UTC).isoformat(),
            }).execute()

            logger.info(
                "Adapted personality profile",
                extra={
                    "user_id": user_id,
                    "acceptance_rate": acceptance_rate,
                    "adaptations": adaptation_notes,
                },
            )

            return current_profile

        except Exception:
            logger.exception(
                "Failed to adapt personality",
                extra={"user_id": user_id},
            )
            # Return current profile on error
            return await self.get_profile(user_id)
