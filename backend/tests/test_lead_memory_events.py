"""Tests for LeadEvent dataclass and related enums.

This module tests the domain model for lead memory events, including:
- EventType enum for categorizing event types
- Direction enum for tracking inbound/outbound events
- LeadEvent dataclass for event representation and serialization
"""

from datetime import UTC, datetime

from src.memory.lead_memory_events import (
    Direction,
    EventType,
    LeadEvent,
    LeadEventService,
)


class TestEventTypeEnum:
    """Tests for the EventType enum."""

    def test_event_type_enum_values(self):
        """Test EventType enum has correct string values."""
        assert EventType.EMAIL_SENT.value == "email_sent"
        assert EventType.EMAIL_RECEIVED.value == "email_received"
        assert EventType.MEETING.value == "meeting"
        assert EventType.CALL.value == "call"
        assert EventType.NOTE.value == "note"
        assert EventType.SIGNAL.value == "signal"

    def test_event_type_enum_count(self):
        """Test EventType enum has exactly 6 values."""
        assert len(EventType) == 6

    def test_event_type_iteration(self):
        """Test EventType enum can be iterated."""
        event_types = list(EventType)
        assert EventType.EMAIL_SENT in event_types
        assert EventType.MEETING in event_types


class TestDirectionEnum:
    """Tests for the Direction enum."""

    def test_direction_enum_values(self):
        """Test Direction enum has correct string values."""
        assert Direction.INBOUND.value == "inbound"
        assert Direction.OUTBOUND.value == "outbound"

    def test_direction_enum_count(self):
        """Test Direction enum has exactly 2 values."""
        assert len(Direction) == 2


class TestLeadEventDataclass:
    """Tests for the LeadEvent dataclass."""

    def test_lead_event_creation_all_fields(self):
        """Test creating a LeadEvent with all fields populated."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 35, tzinfo=UTC)

        event = LeadEvent(
            id="evt_123",
            lead_memory_id="lead_456",
            event_type=EventType.EMAIL_SENT,
            direction=Direction.OUTBOUND,
            subject="Follow up on proposal",
            content="Hi John, checking in on our proposal...",
            participants=["john@acme.com", "sarah@aria.ai"],
            occurred_at=occurred_at,
            source="gmail",
            source_id="msg_abc123",
            created_at=created_at,
        )

        assert event.id == "evt_123"
        assert event.lead_memory_id == "lead_456"
        assert event.event_type == EventType.EMAIL_SENT
        assert event.direction == Direction.OUTBOUND
        assert event.subject == "Follow up on proposal"
        assert event.content == "Hi John, checking in on our proposal..."
        assert event.participants == ["john@acme.com", "sarah@aria.ai"]
        assert event.occurred_at == occurred_at
        assert event.source == "gmail"
        assert event.source_id == "msg_abc123"
        assert event.created_at == created_at

    def test_lead_event_creation_minimal_fields(self):
        """Test creating a LeadEvent with only required fields."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        event = LeadEvent(
            id="evt_123",
            lead_memory_id="lead_456",
            event_type=EventType.NOTE,
            direction=None,
            subject=None,
            content="Internal note about this lead",
            participants=[],
            occurred_at=occurred_at,
            source=None,
            source_id=None,
            created_at=created_at,
        )

        assert event.id == "evt_123"
        assert event.direction is None
        assert event.subject is None
        assert event.participants == []
        assert event.source is None
        assert event.source_id is None

    def test_lead_event_to_dict(self):
        """Test serialization to dict with all fields."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 35, tzinfo=UTC)

        event = LeadEvent(
            id="evt_123",
            lead_memory_id="lead_456",
            event_type=EventType.MEETING,
            direction=Direction.INBOUND,
            subject="Discovery call",
            content="Discussed pain points and budget",
            participants=["john@acme.com", "jane@acme.com"],
            occurred_at=occurred_at,
            source="zoom",
            source_id="meet_xyz789",
            created_at=created_at,
        )

        result = event.to_dict()

        assert result["id"] == "evt_123"
        assert result["lead_memory_id"] == "lead_456"
        assert result["event_type"] == "meeting"
        assert result["direction"] == "inbound"
        assert result["subject"] == "Discovery call"
        assert result["content"] == "Discussed pain points and budget"
        assert result["participants"] == ["john@acme.com", "jane@acme.com"]
        assert result["occurred_at"] == "2025-02-03T14:30:00+00:00"
        assert result["source"] == "zoom"
        assert result["source_id"] == "meet_xyz789"
        assert result["created_at"] == "2025-02-03T14:35:00+00:00"

    def test_lead_event_to_dict_with_none_values(self):
        """Test serialization to dict with None values."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        event = LeadEvent(
            id="evt_123",
            lead_memory_id="lead_456",
            event_type=EventType.SIGNAL,
            direction=None,
            subject=None,
            content="Company just raised Series B",
            participants=[],
            occurred_at=occurred_at,
            source=None,
            source_id=None,
            created_at=created_at,
        )

        result = event.to_dict()

        assert result["direction"] is None
        assert result["subject"] is None
        assert result["source"] is None
        assert result["source_id"] is None

    def test_lead_event_from_dict(self):
        """Test deserialization from dict with all fields."""
        data = {
            "id": "evt_123",
            "lead_memory_id": "lead_456",
            "event_type": "call",
            "direction": "outbound",
            "subject": "Follow up call",
            "content": "Discussed the contract terms",
            "participants": ["john@acme.com"],
            "occurred_at": "2025-02-03T14:30:00+00:00",
            "source": "phone",
            "source_id": "call_abc123",
            "created_at": "2025-02-03T14:35:00+00:00",
        }

        event = LeadEvent.from_dict(data)

        assert event.id == "evt_123"
        assert event.lead_memory_id == "lead_456"
        assert event.event_type == EventType.CALL
        assert event.direction == Direction.OUTBOUND
        assert event.subject == "Follow up call"
        assert event.content == "Discussed the contract terms"
        assert event.participants == ["john@acme.com"]
        assert event.occurred_at == datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        assert event.source == "phone"
        assert event.source_id == "call_abc123"
        assert event.created_at == datetime(2025, 2, 3, 14, 35, tzinfo=UTC)

    def test_lead_event_from_dict_with_none_values(self):
        """Test deserialization from dict with None values."""
        data = {
            "id": "evt_123",
            "lead_memory_id": "lead_456",
            "event_type": "note",
            "direction": None,
            "subject": None,
            "content": "Internal note",
            "participants": [],
            "occurred_at": "2025-02-03T14:30:00+00:00",
            "source": None,
            "source_id": None,
            "created_at": "2025-02-03T14:30:00+00:00",
        }

        event = LeadEvent.from_dict(data)

        assert event.direction is None
        assert event.subject is None
        assert event.source is None
        assert event.source_id is None

    def test_lead_event_from_dict_with_datetime_objects(self):
        """Test deserialization when datetime fields are already datetime objects."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 35, tzinfo=UTC)

        data = {
            "id": "evt_123",
            "lead_memory_id": "lead_456",
            "event_type": "email_sent",
            "direction": "outbound",
            "subject": "Test",
            "content": "Test content",
            "participants": [],
            "occurred_at": occurred_at,
            "source": "test",
            "source_id": "test_id",
            "created_at": created_at,
        }

        event = LeadEvent.from_dict(data)

        assert event.occurred_at == occurred_at
        assert event.created_at == created_at

    def test_round_trip_serialization(self):
        """Test that to_dict and from_dict preserve all data."""
        occurred_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        created_at = datetime(2025, 2, 3, 14, 35, tzinfo=UTC)

        original = LeadEvent(
            id="evt_123",
            lead_memory_id="lead_456",
            event_type=EventType.EMAIL_RECEIVED,
            direction=Direction.INBOUND,
            subject="Re: Proposal",
            content="Thanks for sending the proposal",
            participants=["john@acme.com"],
            occurred_at=occurred_at,
            source="gmail",
            source_id="msg_xyz",
            created_at=created_at,
        )

        # Serialize and deserialize
        dict_data = original.to_dict()
        restored = LeadEvent.from_dict(dict_data)

        # Check all fields match
        assert restored.id == original.id
        assert restored.lead_memory_id == original.lead_memory_id
        assert restored.event_type == original.event_type
        assert restored.direction == original.direction
        assert restored.subject == original.subject
        assert restored.content == original.content
        assert restored.participants == original.participants
        assert restored.occurred_at == original.occurred_at
        assert restored.source == original.source
        assert restored.source_id == original.source_id
        assert restored.created_at == original.created_at


class TestLeadEventService:
    """Tests for the LeadEventService class."""

    def test_service_initialization(self):
        """Test that LeadEventService can be instantiated."""
        service = LeadEventService()
        assert service is not None
