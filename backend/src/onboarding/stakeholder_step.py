"""Stakeholder mapping service for onboarding.

This service handles the stakeholder relationship mapping step during onboarding.
Users can map key stakeholders at their target accounts to help ARIA understand
their relationship landscape.

Stakeholders are stored in onboarding step_data and flowed into downstream systems
per the Integration Checklist pattern.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import DatabaseError
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
from src.memory.episodic import Episode, EpisodicMemory

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


class RelationshipType(str, Enum):
    """Classification of stakeholder relationship types."""

    CHAMPION = "champion"
    DECISION_MAKER = "decision_maker"
    INFLUENCER = "influencer"
    END_USER = "end_user"
    BLOCKER = "blocker"
    OTHER = "other"


@dataclass
class OnboardingStakeholder:
    """A stakeholder mapped during onboarding.

    Attributes:
        id: Unique identifier for this stakeholder.
        name: Contact name.
        title: Optional job title.
        company: Optional company name.
        email: Optional email address.
        relationship_type: Type of relationship (prospect, champion, etc.).
        notes: Optional additional notes.
    """

    id: str
    name: str
    title: str | None = None
    company: str | None = None
    email: str | None = None
    relationship_type: RelationshipType = RelationshipType.OTHER
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize stakeholder to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "email": self.email,
            "relationship_type": self.relationship_type.value if self.relationship_type else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnboardingStakeholder:
        """Create an OnboardingStakeholder from a dictionary."""
        relationship_type = None
        if data.get("relationship_type"):
            role_raw = data["relationship_type"]
            relationship_type = (
                RelationshipType(role_raw) if isinstance(role_raw, str) else role_raw
            )

        return cls(
            id=data["id"],
            name=data["name"],
            title=data.get("title"),
            company=data.get("company"),
            email=data.get("email"),
            relationship_type=relationship_type or RelationshipType.OTHER,
            notes=data.get("notes"),
        )


class StakeholderStepService:
    """Service for managing stakeholder mapping during onboarding.

    Stakeholders entered during onboarding help seed the relationship graph
    and provide ARIA with immediate context about key contacts.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the stakeholder step service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client
        self.episodic = EpisodicMemory()

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance."""
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def save_stakeholders(
        self,
        user_id: str,
        stakeholders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Save stakeholders from onboarding step.

        Stores stakeholders in onboarding step_data and records episodic memory.
        Updates readiness score for relationship_graph.

        Args:
            user_id: The user mapping stakeholders.
            stakeholders: List of stakeholder dictionaries.

        Returns:
            Dictionary with count and created stakeholder IDs.

        Raises:
            DatabaseError: If storage fails.
        """
        try:
            client = self._get_supabase_client()

            # Generate IDs for new stakeholders and convert to domain models
            stakeholder_models = []
            stakeholder_ids = []
            for s in stakeholders:
                stakeholder_id = str(uuid.uuid4())
                stakeholder_ids.append(stakeholder_id)

                # Parse relationship type
                relationship_type = RelationshipType.OTHER
                if s.get("relationship_type"):
                    with contextlib.suppress(ValueError):
                        relationship_type = RelationshipType(s["relationship_type"])

                model = OnboardingStakeholder(
                    id=stakeholder_id,
                    name=s["name"],
                    title=s.get("title"),
                    company=s.get("company"),
                    email=s.get("email"),
                    relationship_type=relationship_type,
                    notes=s.get("notes"),
                )
                stakeholder_models.append(model)

            # Store in onboarding step_data
            # First get current state
            state_response = (
                client.table("onboarding_state")
                .select("*")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if not state_response.data:
                logger.warning(
                    f"No onboarding state found for user {user_id}, skipping step_data update"
                )
            else:
                # Update step_data with stakeholders
                current_step_data: dict[str, Any] = state_response.data.get("step_data", {}) or {}
                current_step_data["stakeholders"] = [
                    model.to_dict() for model in stakeholder_models
                ]

                # Calculate relationship_graph readiness boost
                # Base: 10 points per stakeholder, max 50 points from this step
                readiness_boost = min(len(stakeholders) * 10, 50)

                # Update readiness scores
                current_readiness: dict[str, Any] = (
                    state_response.data.get("readiness_scores", {}) or {}
                )
                current_graph_score = current_readiness.get("relationship_graph", 0)
                if isinstance(current_graph_score, (int, float)):
                    current_readiness["relationship_graph"] = min(
                        current_graph_score + readiness_boost, 100
                    )

                # Update the state
                (
                    client.table("onboarding_state")
                    .update(
                        {
                            "step_data": current_step_data,
                            "readiness_scores": current_readiness,
                        }
                    )
                    .eq("user_id", user_id)
                    .execute()
                )

            # Store stakeholders as Semantic Memory facts for downstream consumption
            await self._store_stakeholder_facts(user_id, stakeholder_models)

            # Record episodic memory event
            await self._record_stakeholder_event(
                user_id=user_id,
                stakeholders=stakeholder_models,
            )

            # Audit log
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.SEMANTIC,  # Relationship graph is semantic memory
                memory_id=f"onboarding_stakeholders_{user_id}",
                metadata={
                    "stakeholder_count": len(stakeholder_models),
                    "stakeholder_ids": stakeholder_ids,
                },
                suppress_errors=True,
            )

            logger.info(
                "Saved onboarding stakeholders",
                extra={
                    "user_id": user_id,
                    "count": len(stakeholder_models),
                    "stakeholder_ids": stakeholder_ids,
                },
            )

            return {
                "count": len(stakeholder_models),
                "stakeholder_ids": stakeholder_ids,
            }

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to save onboarding stakeholders")
            raise DatabaseError(f"Failed to save stakeholders: {e}") from e

    async def get_stakeholders(self, user_id: str) -> list[OnboardingStakeholder]:
        """Get stakeholders for user's onboarding.

        Args:
            user_id: The user to fetch stakeholders for.

        Returns:
            List of OnboardingStakeholder instances.

        Raises:
            DatabaseError: If retrieval fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("onboarding_state")
                .select("step_data")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if not response.data:
                return []

            step_data: dict[str, Any] = response.data.get("step_data", {}) or {}
            stakeholders_data_list = step_data.get("stakeholders", [])

            stakeholders = []
            for s in stakeholders_data_list:
                if isinstance(s, dict):
                    try:
                        stakeholders.append(OnboardingStakeholder.from_dict(s))
                    except Exception as e:
                        logger.warning(f"Failed to parse stakeholder: {e}")

            return stakeholders

        except Exception as e:
            logger.exception("Failed to get onboarding stakeholders")
            raise DatabaseError(f"Failed to get stakeholders: {e}") from e

    async def _store_stakeholder_facts(
        self,
        user_id: str,
        stakeholders: list[OnboardingStakeholder],
    ) -> None:
        """Store each stakeholder as a semantic fact in memory_semantic.

        This ensures stakeholders are discoverable by the memory construction
        pipeline (memory_constructor.py) and by ARIA's relationship graph queries.
        Each stakeholder produces a fact with user_stated source (confidence 0.95).

        Args:
            user_id: The user who mapped stakeholders.
            stakeholders: List of stakeholder models to store.
        """
        if not stakeholders:
            return

        try:
            client = self._get_supabase_client()

            facts = []
            for s in stakeholders:
                # Build a descriptive fact string
                parts = [f"{s.name}"]
                if s.title:
                    parts.append(f"({s.title})")
                if s.company:
                    parts.append(f"at {s.company}")
                role_label = s.relationship_type.value.replace("_", " ")
                fact_text = f"Key stakeholder: {' '.join(parts)} — role: {role_label}"

                entities: list[dict[str, str]] = [
                    {"name": s.name, "type": "person"},
                ]
                if s.company:
                    entities.append({"name": s.company, "type": "company"})

                facts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "fact": fact_text,
                        "confidence": 0.95,
                        "source": "user_stated",
                        "category": "relationship",
                        "metadata": {
                            "onboarding_step": "stakeholder_mapping",
                            "stakeholder_id": s.id,
                            "relationship_type": s.relationship_type.value,
                            "email": s.email,
                            "entities": entities,
                        },
                    }
                )

            if facts:
                client.table("memory_semantic").insert(facts).execute()

            logger.info(
                "Stored stakeholder facts in Semantic Memory",
                extra={"user_id": user_id, "fact_count": len(facts)},
            )

        except Exception as e:
            # Non-critical — don't fail the stakeholder save
            logger.warning("Failed to store stakeholder facts in Semantic Memory: %s", e)

    async def _record_stakeholder_event(
        self,
        user_id: str,
        stakeholders: list[OnboardingStakeholder],
    ) -> None:
        """Record stakeholder mapping as episodic memory.

        Args:
            user_id: The user who mapped stakeholders.
            stakeholders: List of stakeholder models.
        """
        try:
            # Build content describing the stakeholders
            if len(stakeholders) == 0:
                content = "User completed stakeholder mapping step with no stakeholders."
            elif len(stakeholders) == 1:
                s = stakeholders[0]
                content = f"User mapped 1 stakeholder: {s.name}"
                if s.title:
                    content += f" ({s.title})"
                if s.company:
                    content += f" at {s.company}"
                if s.relationship_type != RelationshipType.OTHER:
                    content += f" - {s.relationship_type.value.replace('_', ' ')}"
            else:
                # Count by relationship type
                type_counts: dict[RelationshipType, int] = {}
                for s in stakeholders:
                    type_counts[s.relationship_type] = type_counts.get(s.relationship_type, 0) + 1

                type_summary = ", ".join(
                    f"{count} {rt.value.replace('_', ' ')}{'s' if count > 1 else ''}"
                    for rt, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
                )
                content = f"User mapped {len(stakeholders)} stakeholders: {type_summary}"

            now = datetime.now(UTC)

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="stakeholder_mapping",
                content=content,
                participants=[s.name for s in stakeholders if s.name],
                occurred_at=now,
                recorded_at=now,
                context={
                    "onboarding_step": "user_profile",
                    "stakeholder_count": len(stakeholders),
                },
            )

            await self.episodic.store_episode(episode)

        except Exception as e:
            # Don't fail the save if episodic recording fails
            logger.warning(f"Failed to record stakeholder episodic event: {e}")
