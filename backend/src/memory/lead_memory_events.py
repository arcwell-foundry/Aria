"""Lead memory event tracking domain models.

This module provides the core domain model for tracking lead events,
including interactions like emails, meetings, calls, notes, and signals.
Events represent the timeline of activity for each lead in the system.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import Direction, EventType

logger = logging.getLogger(__name__)


@dataclass
class LeadEvent:
    """A domain model representing a single lead event.

    LeadEvents capture all interactions and activities related to a lead,
    forming the timeline of the sales pursuit. Each event has a type,
    direction (where applicable), and rich metadata for context.

    Attributes:
        id: Unique identifier for this event.
        lead_memory_id: ID of the lead memory this event belongs to.
        event_type: The type of event (email, meeting, call, etc.).
        direction: Whether the event was inbound or outbound (None for notes/signals).
        subject: Optional subject line or title.
        content: The main content/body of the event.
        participants: List of participant email addresses.
        occurred_at: When the event actually happened.
        source: The source system (e.g., "gmail", "zoom", "salesforce").
        source_id: The ID of this event in the source system.
        created_at: When this event record was created in ARIA.
    """

    id: str
    lead_memory_id: str
    event_type: EventType
    direction: Direction | None
    subject: str | None
    content: str | None
    participants: list[str]
    occurred_at: datetime
    source: str | None
    source_id: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        """Serialize the event to a dictionary.

        Converts the event to a dictionary suitable for JSON serialization,
        with datetime fields converted to ISO format strings.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "event_type": self.event_type.value,
            "direction": self.direction.value if self.direction else None,
            "subject": self.subject,
            "content": self.content,
            "participants": self.participants,
            "occurred_at": self.occurred_at.isoformat(),
            "source": self.source,
            "source_id": self.source_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeadEvent:
        """Create a LeadEvent from a dictionary.

        Deserializes a dictionary back into a LeadEvent instance,
        handling both ISO format strings and datetime objects.

        Args:
            data: Dictionary containing event data.

        Returns:
            A LeadEvent instance with restored state.
        """
        # Parse occurred_at - handle both string and datetime
        occurred_at_raw = data["occurred_at"]
        if isinstance(occurred_at_raw, str):
            occurred_at = datetime.fromisoformat(occurred_at_raw)
        else:
            occurred_at = cast(datetime, occurred_at_raw)

        # Parse created_at - handle both string and datetime
        created_at_raw = data["created_at"]
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw)
        else:
            created_at = cast(datetime, created_at_raw)

        # Parse direction - handle both string and Direction enum
        direction_raw = data.get("direction")
        direction: Direction | None
        if isinstance(direction_raw, str):
            direction = Direction(direction_raw)
        else:
            direction = cast(Direction | None, direction_raw)

        # Parse event_type - handle both string and EventType enum
        event_type_raw = data["event_type"]
        if isinstance(event_type_raw, str):
            event_type = EventType(event_type_raw)
        else:
            event_type = EventType(cast(str, event_type_raw))

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            event_type=event_type,
            direction=direction,
            subject=cast(str | None, data.get("subject")),
            content=cast(str | None, data.get("content")),
            participants=cast(list[str], data.get("participants", [])),
            occurred_at=occurred_at,
            source=cast(str | None, data.get("source")),
            source_id=cast(str | None, data.get("source_id")),
            created_at=created_at,
        )


class LeadEventService:
    """Service for managing lead event operations.

    Provides async interface for storing, retrieving, and querying
    lead events. Events are stored in Supabase with user isolation
    via RLS policies.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the lead event service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            DatabaseError: If client initialization fails.
        """
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def add_event(
        self,
        user_id: str,
        lead_memory_id: str,
        event_data: Any,  # LeadEventCreate from src.models.lead_memory
    ) -> str:
        """Add a new event to a lead's timeline.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            event_data: Event data from LeadEventCreate model.

        Returns:
            The ID of the created event.

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
                "event_type": event_data.event_type.value,
                "direction": event_data.direction,
                "subject": event_data.subject,
                "content": event_data.content,
                "participants": event_data.participants,
                "occurred_at": event_data.occurred_at.isoformat(),
                "source": event_data.source,
                "source_id": event_data.source_id,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_memory_events").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert event")

            # Cast the response data to dict for type safety
            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            event_id = cast(str, first_record.get("id"))

            if not event_id:
                raise DatabaseError("Failed to insert event")

            logger.info(
                "Added lead event",
                extra={
                    "event_id": event_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "event_type": event_data.event_type.value,
                },
            )

            return event_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add lead event")
            raise DatabaseError(f"Failed to add lead event: {e}") from e

    async def get_timeline(
        self,
        user_id: str,
        lead_memory_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[LeadEvent]:
        """Get timeline of events for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            start_date: Optional start date for filtering.
            end_date: Optional end date for filtering.

        Returns:
            List of LeadEvent instances ordered by occurred_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            query = client.table("lead_memory_events").select("*").eq("lead_memory_id", lead_memory_id)

            if start_date:
                query = query.gte("occurred_at", start_date.isoformat())
            if end_date:
                query = query.lte("occurred_at", end_date.isoformat())

            query = query.order("occurred_at", desc=True)

            response = query.execute()

            events = []
            for item in response.data:
                event_dict = cast(dict[str, Any], item)
                events.append(LeadEvent.from_dict(event_dict))

            logger.info(
                "Retrieved lead event timeline",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "event_count": len(events),
                },
            )

            return events

        except Exception as e:
            logger.exception("Failed to get lead event timeline")
            raise DatabaseError(f"Failed to get lead event timeline: {e}") from e
