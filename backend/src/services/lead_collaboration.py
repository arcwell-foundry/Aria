"""Lead collaboration service for multi-user contributions.

This service enables team members to contribute to shared leads with
an owner approval workflow. Contributions are flagged for review and
can be merged or rejected by the lead owner.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import ContributionStatus as ModelContributionStatus
from src.models.lead_memory import ContributionType as ModelContributionType

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
            "reviewed_at": self.reviewed_at.isoformat()
            if self.reviewed_at
            else None,
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
