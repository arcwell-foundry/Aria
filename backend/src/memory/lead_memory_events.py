"""Lead memory event tracking domain models.

This module provides the core domain model for tracking lead events,
including interactions like emails, meetings, calls, notes, and signals.
Events represent the timeline of activity for each lead in the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client


class EventType(str, Enum):
    """Types of events that can occur on a lead."""

    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    MEETING = "meeting"
    CALL = "call"
    NOTE = "note"
    SIGNAL = "signal"


class Direction(str, Enum):
    """Direction of communication for bidirectional events."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


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
