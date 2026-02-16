"""
Narrative Identity Engine for ARIA.

Maintains the story of the user-ARIA relationship, tracking milestones
and building a shared narrative that deepens over time.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class MilestoneType(str, Enum):
    """Types of relationship milestones."""

    FIRST_INTERACTION = "first_interaction"
    FIRST_DEAL = "first_deal"
    FIRST_CHALLENGE = "first_challenge"
    DEAL_CLOSED = "deal_closed"
    FIRST_GOAL_COMPLETED = "first_goal_completed"
    FIRST_PUSHBACK_ACCEPTED = "first_pushback_accepted"
    RELATIONSHIP_MILESTONE = "relationship_milestone"
    WORK_ANNIVERSARY = "work_anniversary"
    DEAL_ANNIVERSARY = "deal_anniversary"


@dataclass
class RelationshipMilestone:
    """A milestone in the user-ARIA relationship."""

    id: str
    type: str  # MilestoneType value
    date: datetime
    description: str
    significance: float = 0.5
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date.isoformat(),
            "description": self.description,
            "significance": self.significance,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipMilestone:
        """Deserialize from dictionary."""
        date_val = data.get("date")
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
        elif date_val is None:
            date_val = datetime.now(UTC)

        created_at_val = data.get("created_at")
        if isinstance(created_at_val, str):
            created_at_val = datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
        elif created_at_val is None:
            created_at_val = datetime.now(UTC)

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", ""),
            date=date_val,
            description=data.get("description", ""),
            significance=float(data.get("significance", 0.5)),
            related_entity_type=data.get("related_entity_type"),
            related_entity_id=data.get("related_entity_id"),
            created_at=created_at_val,
        )


@dataclass
class NarrativeState:
    """The current state of the user-ARIA relationship narrative."""

    user_id: str
    relationship_start: datetime
    total_interactions: int = 0
    trust_score: float = 0.5
    shared_victories: list[dict[str, Any]] = field(default_factory=list)
    shared_challenges: list[dict[str, Any]] = field(default_factory=list)
    inside_references: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage/transmission."""
        return {
            "user_id": self.user_id,
            "relationship_start": self.relationship_start.isoformat(),
            "total_interactions": self.total_interactions,
            "trust_score": self.trust_score,
            "shared_victories": self.shared_victories,
            "shared_challenges": self.shared_challenges,
            "inside_references": self.inside_references,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NarrativeState:
        """Deserialize from dictionary."""
        rel_start = data.get("relationship_start")
        if isinstance(rel_start, str):
            rel_start = datetime.fromisoformat(rel_start.replace("Z", "+00:00"))
        elif rel_start is None:
            rel_start = datetime.now(UTC)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        elif updated_at is None:
            updated_at = datetime.now(UTC)

        return cls(
            user_id=data.get("user_id", ""),
            relationship_start=rel_start,
            total_interactions=int(data.get("total_interactions", 0)),
            trust_score=float(data.get("trust_score", 0.5)),
            shared_victories=data.get("shared_victories", []),
            shared_challenges=data.get("shared_challenges", []),
            inside_references=data.get("inside_references", []),
            updated_at=updated_at,
        )


class NarrativeIdentityEngine:
    """
    Engine for maintaining the narrative identity of the user-ARIA relationship.

    This engine:
    - Tracks relationship milestones (firsts, victories, challenges)
    - Builds a shared narrative over time
    - Generates contextual references to shared history
    - Maintains a trust score that evolves with the relationship
    - Detects anniversaries for meaningful moments
    """

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
        memory_service: Any = None,
    ) -> None:
        """
        Initialize the Narrative Identity Engine.

        Args:
            db_client: Supabase client for persistence (optional, will create if not provided).
            llm_client: LLM client for relevance detection (optional, will create if not provided).
            memory_service: Memory service for context retrieval (optional).
        """
        if db_client is None:
            self._db = SupabaseClient.get_client()
        else:
            self._db = db_client

        if llm_client is None:
            self._llm = LLMClient()
        else:
            self._llm = llm_client

        self._memory = memory_service

    async def get_narrative_state(self, user_id: str) -> NarrativeState:
        """
        Get the narrative state for a user.

        Creates a new narrative state if one doesn't exist.

        Args:
            user_id: The user's ID.

        Returns:
            NarrativeState for the user.
        """
        try:
            result = (
                self._db.table("user_narratives")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if result.data:
                return NarrativeState.from_dict(result.data)

        except Exception as e:
            logger.debug(
                "No existing narrative state found, creating new",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Create new narrative state
        return await self._initialize_narrative(user_id)

    async def record_milestone(
        self,
        user_id: str,
        milestone_type: str,
        description: str,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        significance: float = 0.5,
    ) -> RelationshipMilestone:
        """
        Record a relationship milestone.

        Args:
            user_id: The user's ID.
            milestone_type: Type of milestone (from MilestoneType enum).
            description: Description of the milestone.
            related_entity_type: Optional type of related entity (e.g., "deal", "goal").
            related_entity_id: Optional ID of related entity.
            significance: Importance of milestone (0.0-1.0).

        Returns:
            The created RelationshipMilestone.
        """
        now = datetime.now(UTC)
        milestone_id = str(uuid.uuid4())

        milestone = RelationshipMilestone(
            id=milestone_id,
            type=milestone_type,
            date=now,
            description=description,
            significance=min(1.0, max(0.0, significance)),
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            created_at=now,
        )

        try:
            # Store milestone
            self._db.table("relationship_milestones").insert(
                {
                    "id": milestone_id,
                    "user_id": user_id,
                    "type": milestone_type,
                    "date": now.isoformat(),
                    "description": description,
                    "significance": milestone.significance,
                    "related_entity_type": related_entity_type,
                    "related_entity_id": related_entity_id,
                    "created_at": now.isoformat(),
                }
            ).execute()

            # Update trust score based on milestone type
            await self._update_trust_for_milestone(user_id, milestone_type, significance)

            # Add to inside references if significant
            if significance >= 0.7:
                await self._add_inside_reference(user_id, description)

            logger.info(
                "Recorded milestone",
                extra={
                    "user_id": user_id,
                    "milestone_type": milestone_type,
                    "milestone_id": milestone_id,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to record milestone",
                extra={"user_id": user_id, "error": str(e)},
            )

        return milestone

    async def get_contextual_references(
        self,
        user_id: str,
        current_topic: str,
    ) -> list[str]:
        """
        Get relevant contextual references from shared history.

        Uses LLM to determine which shared experiences are relevant
        to the current conversation topic.

        Args:
            user_id: The user's ID.
            current_topic: The current topic being discussed.

        Returns:
            List of relevant references (max 2).
        """
        try:
            # Get narrative state
            state = await self.get_narrative_state(user_id)

            # Combine all shared experiences
            experiences = []

            for victory in state.shared_victories[-5:]:
                experiences.append(f"Victory: {victory.get('description', '')}")

            for challenge in state.shared_challenges[-5:]:
                experiences.append(f"Challenge: {challenge.get('description', '')}")

            # Get recent milestones
            milestones = await self._get_recent_milestones(user_id, limit=5)
            for m in milestones:
                experiences.append(f"Milestone: {m.description}")

            if not experiences:
                return []

            # Use LLM to find relevant experiences
            relevant = await self._find_relevant_experiences(
                experiences=experiences,
                current_topic=current_topic,
            )

            # Return max 2 references
            return relevant[:2]

        except Exception as e:
            logger.warning(
                "Failed to get contextual references",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def check_anniversaries(self, user_id: str) -> list[dict[str, Any]]:
        """
        Check for upcoming or recent anniversaries.

        Args:
            user_id: The user's ID.

        Returns:
            List of anniversary notifications.
        """
        anniversaries = []
        today = datetime.now(UTC).date()

        try:
            # Get relationship start
            state = await self.get_narrative_state(user_id)
            rel_start = state.relationship_start.date()

            # Check work anniversary (relationship anniversary)
            if rel_start.month == today.month and rel_start.day == today.day:
                years = today.year - rel_start.year
                if years > 0:
                    anniversaries.append(
                        {
                            "type": "work_anniversary",
                            "years": years,
                            "description": f"We've been working together for {years} year{'s' if years > 1 else ''}!",
                            "date": rel_start.isoformat(),
                        }
                    )

            # Check milestone anniversaries
            milestones_result = (
                self._db.table("relationship_milestones")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )

            if milestones_result.data:
                for m_data in milestones_result.data:
                    milestone = RelationshipMilestone.from_dict(m_data)
                    m_date = milestone.date.date()

                    # Check if today is anniversary of this milestone
                    if m_date.month == today.month and m_date.day == today.day:
                        years = today.year - m_date.year
                        if years > 0 and milestone.type in [
                            MilestoneType.FIRST_DEAL.value,
                            MilestoneType.DEAL_CLOSED.value,
                            MilestoneType.FIRST_GOAL_COMPLETED.value,
                        ]:
                            anniversaries.append(
                                {
                                    "type": "deal_anniversary",
                                    "years": years,
                                    "description": f"{years} year{'s' if years > 1 else ''} since {milestone.description}",
                                    "date": m_date.isoformat(),
                                    "milestone_type": milestone.type,
                                }
                            )

        except Exception as e:
            logger.warning(
                "Failed to check anniversaries",
                extra={"user_id": user_id, "error": str(e)},
            )

        return anniversaries

    async def update_trust_score(
        self,
        user_id: str,
        event_type: str,
    ) -> float:
        """
        Update the trust score based on an event.

        Args:
            user_id: The user's ID.
            event_type: Type of trust-affecting event.

        Returns:
            The updated trust score.
        """
        state = await self.get_narrative_state(user_id)

        # Trust adjustments based on event type
        adjustments = {
            "pushback_accepted": 0.05,
            "goal_completed": 0.03,
            "milestone_reached": 0.02,
            "positive_feedback": 0.02,
            "negative_feedback": -0.03,
            "task_failed": -0.02,
            "correction_applied": 0.01,
        }

        adjustment = adjustments.get(event_type, 0.0)
        new_score = min(1.0, max(0.0, state.trust_score + adjustment))

        try:
            self._db.table("user_narratives").update(
                {
                    "trust_score": new_score,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("user_id", user_id).execute()

            logger.debug(
                "Updated trust score",
                extra={
                    "user_id": user_id,
                    "old_score": state.trust_score,
                    "new_score": new_score,
                    "event_type": event_type,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to update trust score",
                extra={"user_id": user_id, "error": str(e)},
            )

        return new_score

    async def increment_interactions(self, user_id: str) -> int:
        """
        Increment the total interaction count.

        Args:
            user_id: The user's ID.

        Returns:
            The updated interaction count.
        """
        state = await self.get_narrative_state(user_id)
        new_count = state.total_interactions + 1

        try:
            self._db.table("user_narratives").update(
                {
                    "total_interactions": new_count,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("user_id", user_id).execute()

        except Exception as e:
            logger.error(
                "Failed to increment interactions",
                extra={"user_id": user_id, "error": str(e)},
            )

        return new_count

    # ── Private Methods ─────────────────────────────────────────────────────

    async def _initialize_narrative(self, user_id: str) -> NarrativeState:
        """Initialize a new narrative state for a user."""
        now = datetime.now(UTC)
        state = NarrativeState(
            user_id=user_id,
            relationship_start=now,
            total_interactions=0,
            trust_score=0.5,
            shared_victories=[],
            shared_challenges=[],
            inside_references=[],
            updated_at=now,
        )

        try:
            self._db.table("user_narratives").insert(
                {
                    "user_id": user_id,
                    "relationship_start": now.isoformat(),
                    "total_interactions": 0,
                    "trust_score": 0.5,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": now.isoformat(),
                }
            ).execute()

            logger.info(
                "Initialized narrative state",
                extra={"user_id": user_id},
            )

        except Exception as e:
            logger.error(
                "Failed to initialize narrative state",
                extra={"user_id": user_id, "error": str(e)},
            )

        return state

    async def _update_trust_for_milestone(
        self,
        user_id: str,
        milestone_type: str,
        _significance: float,
    ) -> None:
        """Update trust score based on milestone type."""
        # Map milestone types to trust events
        trust_events = {
            MilestoneType.FIRST_DEAL.value: "milestone_reached",
            MilestoneType.FIRST_GOAL_COMPLETED.value: "goal_completed",
            MilestoneType.DEAL_CLOSED.value: "goal_completed",
            MilestoneType.FIRST_PUSHBACK_ACCEPTED.value: "pushback_accepted",
        }

        event_type = trust_events.get(milestone_type)
        if event_type:
            await self.update_trust_score(user_id, event_type)

    async def _add_inside_reference(self, user_id: str, reference: str) -> None:
        """Add an inside reference to the narrative state."""
        try:
            # Get current state
            state = await self.get_narrative_state(user_id)

            # Add new reference (keep max 20)
            references = state.inside_references[-19:] + [reference]

            self._db.table("user_narratives").update(
                {
                    "inside_references": references,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("user_id", user_id).execute()

        except Exception as e:
            logger.warning(
                "Failed to add inside reference",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _get_recent_milestones(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[RelationshipMilestone]:
        """Get recent milestones for a user."""
        try:
            result = (
                self._db.table("relationship_milestones")
                .select("*")
                .eq("user_id", user_id)
                .order("date", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [RelationshipMilestone.from_dict(m) for m in result.data]

        except Exception as e:
            logger.warning(
                "Failed to get recent milestones",
                extra={"user_id": user_id, "error": str(e)},
            )

        return []

    async def _find_relevant_experiences(
        self,
        experiences: list[str],
        current_topic: str,
    ) -> list[str]:
        """Use LLM to find experiences relevant to current topic."""
        if not experiences:
            return []

        prompt = f"""Determine which of these shared experiences are relevant to the current topic.

Shared experiences:
{chr(10).join(f"- {exp}" for exp in experiences)}

Current topic: {current_topic}

Return JSON with the relevant experience descriptions (max 2). If none are relevant, return empty array.
Output ONLY valid JSON:
{{"relevant": ["experience description 1", "experience description 2"]}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )

            # Extract JSON
            content = response.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            result = json.loads(content)
            return result.get("relevant", [])

        except Exception as e:
            logger.debug(
                "Failed to find relevant experiences",
                extra={"error": str(e)},
            )
            return []
