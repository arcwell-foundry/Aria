"""Lead collaboration service for multi-user contributions.

This service enables team members to contribute to shared leads with
an owner approval workflow. Contributions are flagged for review and
can be merged or rejected by the lead owner.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from datetime import UTC
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


# Internal enums for domain model
class ContributionStatus(str, Enum):
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


class ContributionType(str, Enum):
    EVENT = "event"
    NOTE = "note"
    INSIGHT = "insight"


@dataclass
class Contribution:
    """A domain model representing a contribution to a lead.

    Attributes:
        id: Unique identifier for this contribution.
        lead_memory_id: ID of the lead memory this contribution belongs to.
        contributor_id: User ID of the contributor.
        contribution_type: Type of contribution (event, note, insight).
        contribution_id: ID of the event/note/insight being contributed.
        status: Review status (pending, merged, rejected).
        reviewed_by: User ID of the reviewer (if reviewed).
        reviewed_at: Timestamp of review (if reviewed).
        created_at: When this contribution was created.
    """

    id: str
    lead_memory_id: str
    contributor_id: str
    contribution_type: ContributionType
    contribution_id: str | None
    status: ContributionStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize contribution to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "contributor_id": self.contributor_id,
            "contribution_type": self.contribution_type.value,
            "contribution_id": self.contribution_id,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contribution:
        """Create a Contribution from a dictionary."""
        # Parse datetime fields
        reviewed_at = None
        if data.get("reviewed_at"):
            raw = data["reviewed_at"]
            reviewed_at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw

        created_at_raw = data["created_at"]
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )

        # Parse enums
        contribution_type_raw = data["contribution_type"]
        contribution_type = (
            ContributionType(contribution_type_raw)
            if isinstance(contribution_type_raw, str)
            else contribution_type_raw
        )

        status_raw = data["status"]
        status = ContributionStatus(status_raw) if isinstance(status_raw, str) else status_raw

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            contributor_id=cast(str, data["contributor_id"]),
            contribution_type=contribution_type,
            contribution_id=cast(str | None, data.get("contribution_id")),
            status=status,
            reviewed_by=cast(str | None, data.get("reviewed_by")),
            reviewed_at=reviewed_at,
            created_at=created_at,
        )


@dataclass
class Contributor:
    """A domain model representing a contributor to a lead.

    Attributes:
        id: Unique identifier for this contributor relationship.
        lead_memory_id: ID of the lead memory this contributor belongs to.
        name: Full name of the contributor.
        email: Email address of the contributor.
        added_at: When this contributor was added.
        contribution_count: Number of contributions made by this contributor.
    """

    id: str
    lead_memory_id: str
    name: str
    email: str
    added_at: datetime
    contribution_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize contributor to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "name": self.name,
            "email": self.email,
            "added_at": self.added_at.isoformat(),
            "contribution_count": self.contribution_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contributor:
        """Create a Contributor from a dictionary."""
        added_at_raw = data["added_at"]
        added_at = (
            datetime.fromisoformat(added_at_raw) if isinstance(added_at_raw, str) else added_at_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            name=cast(str, data["name"]),
            email=cast(str, data["email"]),
            added_at=added_at,
            contribution_count=cast(int, data["contribution_count"]),
        )


class LeadCollaborationService:
    """Service for managing lead collaboration operations."""

    def __init__(self, db_client: Client) -> None:
        """Initialize the collaboration service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance.

        Returns:
            The Supabase client.

        Raises:
            DatabaseError: If client retrieval fails.
        """
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def add_contributor(
        self,
        user_id: str,
        lead_memory_id: str,
        contributor_id: str,
    ) -> str:
        """Add a contributor to a lead.

        Note: Contributors are implicitly added when they make their first
        contribution. This method exists for explicit addition and validation.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            contributor_id: User ID to add as contributor.

        Returns:
            The contributor_id that was added.

        Raises:
            DatabaseError: If operation fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Check if contributor already has contributions to this lead
            response = (
                client.table("lead_memory_contributions")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("contributor_id", contributor_id)
                .execute()
            )

            # Contributors are tracked via their contributions
            # No separate table - return the contributor_id
            logger.info(
                "Contributor added to lead",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contributor_id": contributor_id,
                    "existing_contributions": len(response.data or []),
                },
            )

            return contributor_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add contributor")
            raise DatabaseError(f"Failed to add contributor: {e}") from e

    async def submit_contribution(
        self,
        user_id: str,
        lead_memory_id: str,
        contribution_type: ContributionType,
        contribution_id: str | None = None,
        content: str | None = None,
    ) -> str:
        """Submit a contribution to a lead for owner review.

        Args:
            user_id: The user submitting the contribution.
            lead_memory_id: The lead memory ID.
            contribution_type: Type of contribution (event, note, insight).
            contribution_id: Optional ID of existing event/note/insight.
            content: Optional content for note/insight contributions.

        Returns:
            The ID of the created contribution record.

        Raises:
            DatabaseError: If submission fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contributor_id": user_id,
                "contribution_type": contribution_type.value,
                "contribution_id": contribution_id,
                "status": ContributionStatus.PENDING.value,
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_memory_contributions").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert contribution")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            new_contribution_id = cast(str, first_record.get("id"))

            if not new_contribution_id:
                raise DatabaseError("Failed to insert contribution")

            logger.info(
                "Contribution submitted",
                extra={
                    "contribution_id": new_contribution_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contribution_type": contribution_type.value,
                },
            )

            return new_contribution_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to submit contribution")
            raise DatabaseError(f"Failed to submit contribution: {e}") from e
