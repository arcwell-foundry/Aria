"""Lead stakeholder tracking for contact mapping.

Stakeholders track individual contacts at a lead company including:
- Contact information (email, name, title)
- Role classification (decision maker, influencer, champion, blocker, user)
- Influence level (1-10)
- Sentiment tracking
- Last contact timestamp

Stored in Supabase with user isolation via RLS.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import Sentiment, StakeholderRole

logger = logging.getLogger(__name__)


@dataclass
class LeadStakeholder:
    """A domain model representing a stakeholder at a lead company.

    Attributes:
        id: Unique identifier for this stakeholder.
        lead_memory_id: ID of the lead memory this stakeholder belongs to.
        contact_email: Primary contact email (unique per lead).
        contact_name: Optional full name.
        title: Optional job title.
        role: Optional role classification.
        influence_level: Influence level 1-10 (default 5).
        sentiment: Current sentiment (default neutral).
        last_contacted_at: Optional timestamp of last contact.
        notes: Optional additional notes.
        created_at: When this stakeholder was created.
    """

    id: str
    lead_memory_id: str
    contact_email: str
    contact_name: str | None
    title: str | None
    role: StakeholderRole | None
    influence_level: int
    sentiment: Sentiment
    last_contacted_at: datetime | None
    notes: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize stakeholder to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "contact_email": self.contact_email,
            "contact_name": self.contact_name,
            "title": self.title,
            "role": self.role.value if self.role else None,
            "influence_level": self.influence_level,
            "sentiment": self.sentiment.value,
            "last_contacted_at": self.last_contacted_at.isoformat() if self.last_contacted_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeadStakeholder:
        """Create a LeadStakeholder from a dictionary."""
        # Parse datetime fields
        last_contacted_at = None
        if data.get("last_contacted_at"):
            raw = data["last_contacted_at"]
            last_contacted_at = (
                datetime.fromisoformat(raw) if isinstance(raw, str) else raw
            )

        created_at_raw = data["created_at"]
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )

        # Parse enums
        role = None
        if data.get("role"):
            role_raw = data["role"]
            role = (
                StakeholderRole(role_raw)
                if isinstance(role_raw, str)
                else role_raw
            )

        sentiment_raw = data["sentiment"]
        sentiment = (
            Sentiment(sentiment_raw)
            if isinstance(sentiment_raw, str)
            else sentiment_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            contact_email=cast(str, data["contact_email"]),
            contact_name=cast(str | None, data.get("contact_name")),
            title=cast(str | None, data.get("title")),
            role=role,
            influence_level=cast(int, data["influence_level"]),
            sentiment=sentiment,
            last_contacted_at=last_contacted_at,
            notes=cast(str | None, data.get("notes")),
            created_at=created_at,
        )


class LeadStakeholderService:
    """Service for managing lead stakeholder operations.

    Provides async interface for storing, retrieving, and querying
    lead stakeholders. Stored in Supabase with user isolation via RLS.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the stakeholder service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance."""
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def add_stakeholder(
        self,
        user_id: str,
        lead_memory_id: str,
        contact_email: str,
        contact_name: str | None = None,
        title: str | None = None,
        role: StakeholderRole | None = None,
        influence_level: int = 5,
        sentiment: Sentiment = Sentiment.NEUTRAL,
        notes: str | None = None,
    ) -> str:
        """Add a new stakeholder to a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            contact_email: Contact email address.
            contact_name: Optional full name.
            title: Optional job title.
            role: Optional role classification.
            influence_level: Influence level 1-10.
            sentiment: Current sentiment.
            notes: Optional additional notes.

        Returns:
            The ID of the created stakeholder.

        Raises:
            DatabaseError: If storage fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contact_email": contact_email,
                "contact_name": contact_name,
                "title": title,
                "role": role.value if role else None,
                "influence_level": influence_level,
                "sentiment": sentiment.value,
                "last_contacted_at": None,
                "notes": notes,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_stakeholders").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert stakeholder")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            stakeholder_id = cast(str, first_record.get("id"))

            if not stakeholder_id:
                raise DatabaseError("Failed to insert stakeholder")

            logger.info(
                "Added lead stakeholder",
                extra={
                    "stakeholder_id": stakeholder_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contact_email": contact_email,
                },
            )

            return stakeholder_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add lead stakeholder")
            raise DatabaseError(f"Failed to add lead stakeholder: {e}") from e

    async def list_by_lead(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[LeadStakeholder]:
        """List all stakeholders for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of LeadStakeholder instances.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_stakeholders")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .order("influence_level", desc=True)
                .execute()
            )

            stakeholders = []
            for item in response.data:
                stakeholder_dict = cast(dict[str, Any], item)
                stakeholders.append(LeadStakeholder.from_dict(stakeholder_dict))

            logger.info(
                "Listed lead stakeholders",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(stakeholders),
                },
            )

            return stakeholders

        except Exception as e:
            logger.exception("Failed to list lead stakeholders")
            raise DatabaseError(f"Failed to list lead stakeholders: {e}") from e
