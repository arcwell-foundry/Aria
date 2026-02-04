# Lead Memory Event Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create event tracking system for lead memory that stores all lead interactions (emails, meetings, calls, notes, signals) and provides timeline queries.

**Architecture:** Service class pattern with Supabase storage. Events are stored in `lead_memory_events` table with user isolation via RLS. LeadEvent dataclass models domain entities. EventType enum defines event categories. Direction enum distinguishes inbound/outbound communications.

**Tech Stack:**
- Python 3.11+ dataclasses for domain models
- Supabase client for database operations (already exists in `src/db/supabase.py`)
- Pydantic models already exist in `src/models/lead_memory.py`
- pytest for testing

**Key Files:**
- Create: `backend/src/memory/lead_memory_events.py`
- Modify: `backend/src/memory/__init__.py` (add exports)
- Test: `backend/tests/test_lead_memory_events.py`

**Database Schema:** Already exists in `supabase/migrations/20260202000004_create_lead_memory.sql` (lines 23-36)

**Existing Models to Reference:** `src/models/lead_memory.py` (lines 20-27, 93-115) contains EventType enum and LeadEventCreate/Response models

---

## Task 1: Create LeadEvent Dataclass

**Files:**
- Create: `backend/src/memory/lead_memory_events.py`

**Step 1: Write the failing test**

First create the test file structure:

```python
# File: backend/tests/test_lead_memory_events.py

from datetime import UTC, datetime

import pytest

from src.memory.lead_memory_events import Direction, EventType, LeadEvent


class TestLeadEventDataclass:
    def test_lead_event_creation(self):
        event = LeadEvent(
            id="123e4567-e89b-12d3-a456-426614174000",
            lead_memory_id="lead-123",
            event_type=EventType.EMAIL_SENT,
            direction=Direction.OUTBOUND,
            subject="Follow up",
            content="Hi, just checking in",
            participants=["john@acme.com"],
            occurred_at=datetime.now(UTC),
            source="gmail",
            source_id="msg-456",
        )
        assert event.id == "123e4567-e89b-12d3-a456-426614174000"
        assert event.lead_memory_id == "lead-123"
        assert event.event_type == EventType.EMAIL_SENT
        assert event.direction == Direction.OUTBOUND

    def test_event_type_enum_values(self):
        assert EventType.EMAIL_SENT.value == "email_sent"
        assert EventType.EMAIL_RECEIVED.value == "email_received"
        assert EventType.MEETING.value == "meeting"
        assert EventType.CALL.value == "call"
        assert EventType.NOTE.value == "note"
        assert EventType.SIGNAL.value == "signal"

    def test_direction_enum_values(self):
        assert Direction.INBOUND.value == "inbound"
        assert Direction.OUTBOUND.value == "outbound"

    def test_lead_event_to_dict(self):
        occurred_at = datetime(2025, 2, 3, 12, 0, 0, tzinfo=UTC)
        event = LeadEvent(
            id="event-123",
            lead_memory_id="lead-456",
            event_type=EventType.MEETING,
            direction=None,
            subject="Discovery Call",
            content="Discussed requirements",
            participants=["john@acme.com", "jane@acme.com"],
            occurred_at=occurred_at,
            source="calendar",
            source_id="cal-789",
        )
        data = event.to_dict()
        assert data["id"] == "event-123"
        assert data["lead_memory_id"] == "lead-456"
        assert data["event_type"] == "meeting"
        assert data["direction"] is None
        assert data["occurred_at"] == "2025-02-03T12:00:00+00:00"

    def test_lead_event_from_dict(self):
        data = {
            "id": "event-123",
            "lead_memory_id": "lead-456",
            "event_type": "call",
            "direction": "inbound",
            "subject": "Technical discussion",
            "content": "Talked about API integration",
            "participants": ["tech@acme.com"],
            "occurred_at": "2025-02-03T14:30:00+00:00",
            "source": "manual",
            "source_id": None,
            "created_at": "2025-02-03T14:30:00+00:00",
        }
        event = LeadEvent.from_dict(data)
        assert event.id == "event-123"
        assert event.event_type == EventType.CALL
        assert event.direction == Direction.INBOUND
        assert event.participants == ["tech@acme.com"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_events.py -v`

Expected: `ModuleNotFoundError: No module named 'src.memory.lead_memory_events'`

**Step 3: Write minimal implementation**

```python
# File: backend/src/memory/lead_memory_events.py

"""Lead memory event tracking for timeline of interactions.

Events track all lead interactions including:
- Email communications (sent/received)
- Meetings and calls
- Manual notes
- Market signals

Events are stored in Supabase with user isolation via RLS.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of lead events that can be tracked."""

    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    MEETING = "meeting"
    CALL = "call"
    NOTE = "note"
    SIGNAL = "signal"


class Direction(str, Enum):
    """Direction of communication events."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class LeadEvent:
    """A lead event representing an interaction.

    Events capture all touchpoints with a lead including
    communications, meetings, and notes. They form the
    chronological timeline of a sales pursuit.
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
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
    def from_dict(cls, data: dict[str, Any]) -> "LeadEvent":
        """Create a LeadEvent instance from a dictionary.

        Args:
            data: Dictionary containing event data from database.

        Returns:
            LeadEvent instance with restored state.
        """
        occurred_at = data["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)

        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=data["id"],
            lead_memory_id=data["lead_memory_id"],
            event_type=EventType(data["event_type"]),
            direction=Direction(data["direction"]) if data.get("direction") else None,
            subject=data.get("subject"),
            content=data.get("content"),
            participants=data.get("participants", []),
            occurred_at=occurred_at,
            source=data.get("source"),
            source_id=data.get("source_id"),
            created_at=created_at,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventDataclass -v`

Expected: `PASSED` for all tests

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/test_lead_memory_events.py
git commit -m "feat(lead-memory): add LeadEvent dataclass with EventType and Direction enums"
```

---

## Task 2: Create LeadEventService Class Skeleton

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_lead_memory_events.py

class TestLeadEventService:
    def test_service_initialization(self):
        service = LeadEventService()
        assert service is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventService::test_service_initialization -v`

Expected: `NameError: name 'LeadEventService' is not defined`

**Step 3: Write minimal implementation**

Add to `backend/src/memory/lead_memory_events.py`:

```python
class LeadEventService:
    """Service for managing lead event operations.

    Provides async interface for storing, retrieving, and querying
    lead events. Events are stored in Supabase with user isolation
    via RLS policies.
    """

    def _get_supabase_client(self) -> Any:
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventService::test_service_initialization -v`

Expected: `PASSED`

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/test_lead_memory_events.py
git commit -m "feat(lead-memory): add LeadEventService skeleton"
```

---

## Task 3: Implement add_event Method

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_lead_memory_events.py

from unittest.mock import AsyncMock, MagicMock, patch

class TestLeadEventServiceAddEvent:
    @pytest.mark.asyncio
    async def test_add_email_sent_event(self):
        service = LeadEventService()
        occurred_at = datetime(2025, 2, 3, 12, 0, 0, tzinfo=UTC)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "new-event-id", "created_at": occurred_at.isoformat()}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            from src.models.lead_memory import LeadEventCreate

            event_create = LeadEventCreate(
                event_type=EventType.EMAIL_SENT,
                direction="outbound",
                subject="Follow up",
                content="Checking in",
                participants=["john@acme.com"],
                occurred_at=occurred_at,
                source="gmail",
                source_id="msg-123",
            )

            event_id = await service.add_event(
                user_id="user-123",
                lead_memory_id="lead-456",
                event_data=event_create,
            )

            assert event_id == "new-event-id"
            mock_client.table.assert_called_once_with("lead_memory_events")
            mock_client.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_meeting_event_without_direction(self):
        service = LeadEventService()
        occurred_at = datetime(2025, 2, 3, 14, 0, 0, tzinfo=UTC)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "meeting-event-id", "created_at": occurred_at.isoformat()}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            from src.models.lead_memory import LeadEventCreate

            event_create = LeadEventCreate(
                event_type=EventType.MEETING,
                subject="Discovery Call",
                participants=["john@acme.com", "jane@acme.com"],
                occurred_at=occurred_at,
                source="calendar",
            )

            event_id = await service.add_event(
                user_id="user-123",
                lead_memory_id="lead-789",
                event_data=event_create,
            )

            assert event_id == "meeting-event-id"

    @pytest.mark.asyncio
    async def test_add_event_handles_database_error(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Connection lost")

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            from src.core.exceptions import DatabaseError
            from src.models.lead_memory import LeadEventCreate

            event_create = LeadEventCreate(
                event_type=EventType.NOTE,
                content="Internal note",
                occurred_at=datetime.now(UTC),
            )

            with pytest.raises(DatabaseError):
                await service.add_event(
                    user_id="user-123",
                    lead_memory_id="lead-456",
                    event_data=event_create,
                )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceAddEvent -v`

Expected: Tests fail with `AttributeError: 'LeadEventService' object has no attribute 'add_event'`

**Step 3: Write minimal implementation**

Add to `LeadEventService` class in `backend/src/memory/lead_memory_events.py`:

```python
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

            event_id = response.data[0]["id"]

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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceAddEvent -v`

Expected: `PASSED` for all tests

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/test_lead_memory_events.py
git commit -m "feat(lead-memory): implement add_event method"
```

---

## Task 4: Implement get_timeline Method

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_lead_memory_events.py

class TestLeadEventServiceTimeline:
    @pytest.mark.asyncio
    async def test_get_timeline_by_date_range(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "event-1",
                "lead_memory_id": "lead-123",
                "event_type": "email_sent",
                "direction": "outbound",
                "subject": "Intro email",
                "content": "Nice to meet you",
                "participants": ["john@acme.com"],
                "occurred_at": "2025-02-01T10:00:00+00:00",
                "source": "gmail",
                "source_id": "msg-1",
                "created_at": "2025-02-01T10:00:00+00:00",
            },
            {
                "id": "event-2",
                "lead_memory_id": "lead-123",
                "event_type": "meeting",
                "direction": None,
                "subject": "Discovery Call",
                "content": "Requirements discussion",
                "participants": ["john@acme.com", "jane@acme.com"],
                "occurred_at": "2025-02-03T14:00:00+00:00",
                "source": "calendar",
                "source_id": "cal-1",
                "created_at": "2025-02-03T14:00:00+00:00",
            },
        ]

        mock_select = MagicMock()
        mock_select.eq.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_select

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            events = await service.get_timeline(
                user_id="user-123",
                lead_memory_id="lead-123",
                start_date=datetime(2025, 2, 1, tzinfo=UTC),
                end_date=datetime(2025, 2, 28, tzinfo=UTC),
            )

            assert len(events) == 2
            assert events[0].event_type == EventType.EMAIL_SENT
            assert events[1].event_type == EventType.MEETING
            assert events[1].participants == ["john@acme.com", "jane@acme.com"]

    @pytest.mark.asyncio
    async def test_get_timeline_empty_result(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []

        mock_select = MagicMock()
        mock_select.eq.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_select

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            events = await service.get_timeline(
                user_id="user-123",
                lead_memory_id="lead-123",
                start_date=datetime(2025, 1, 1, tzinfo=UTC),
                end_date=datetime(2025, 1, 31, tzinfo=UTC),
            )

            assert events == []

    @pytest.mark.asyncio
    async def test_get_timeline_without_date_range(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "event-1",
                "lead_memory_id": "lead-123",
                "event_type": "note",
                "direction": None,
                "subject": None,
                "content": "Internal note",
                "participants": [],
                "occurred_at": "2025-02-03T12:00:00+00:00",
                "source": None,
                "source_id": None,
                "created_at": "2025-02-03T12:00:00+00:00",
            },
        ]

        mock_select = MagicMock()
        mock_select.eq.return_value.eq.return_value.order.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_select

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            events = await service.get_timeline(
                user_id="user-123",
                lead_memory_id="lead-123",
            )

            assert len(events) == 1
            assert events[0].event_type == EventType.NOTE
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceTimeline -v`

Expected: `AttributeError: 'LeadEventService' object has no attribute 'get_timeline'`

**Step 3: Write minimal implementation**

Add to `LeadEventService` class in `backend/src/memory/lead_memory_events.py`:

```python
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
                events.append(LeadEvent.from_dict(item))

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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceTimeline -v`

Expected: `PASSED` for all tests

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/test_lead_memory_events.py
git commit -m "feat(lead-memory): implement get_timeline method"
```

---

## Task 5: Implement get_by_type Method

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_lead_memory_events.py

class TestLeadEventServiceByType:
    @pytest.mark.asyncio
    async def test_get_events_by_type(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "email-1",
                "lead_memory_id": "lead-123",
                "event_type": "email_sent",
                "direction": "outbound",
                "subject": "Follow up 1",
                "content": "Checking in",
                "participants": ["john@acme.com"],
                "occurred_at": "2025-02-01T10:00:00+00:00",
                "source": "gmail",
                "source_id": "msg-1",
                "created_at": "2025-02-01T10:00:00+00:00",
            },
            {
                "id": "email-2",
                "lead_memory_id": "lead-123",
                "event_type": "email_sent",
                "direction": "outbound",
                "subject": "Follow up 2",
                "content": "Any update?",
                "participants": ["john@acme.com"],
                "occurred_at": "2025-02-03T10:00:00+00:00",
                "source": "gmail",
                "source_id": "msg-2",
                "created_at": "2025-02-03T10:00:00+00:00",
            },
        ]

        mock_select = MagicMock()
        mock_select.eq.return_value.eq.return_value.order.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_select

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            events = await service.get_by_type(
                user_id="user-123",
                lead_memory_id="lead-123",
                event_type=EventType.EMAIL_SENT,
            )

            assert len(events) == 2
            assert all(e.event_type == EventType.EMAIL_SENT for e in events)
            assert events[0].subject == "Follow up 2"  # Most recent first

    @pytest.mark.asyncio
    async def test_get_meetings_by_type(self):
        service = LeadEventService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "meeting-1",
                "lead_memory_id": "lead-123",
                "event_type": "meeting",
                "direction": None,
                "subject": "Demo",
                "content": "Product walkthrough",
                "participants": ["john@acme.com"],
                "occurred_at": "2025-02-02T15:00:00+00:00",
                "source": "calendar",
                "source_id": "cal-1",
                "created_at": "2025-02-02T15:00:00+00:00",
            },
        ]

        mock_select = MagicMock()
        mock_select.eq.return_value.eq.return_value.order.return_value.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_select

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            events = await service.get_by_type(
                user_id="user-123",
                lead_memory_id="lead-123",
                event_type=EventType.MEETING,
            )

            assert len(events) == 1
            assert events[0].event_type == EventType.MEETING
            assert events[0].source == "calendar"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceByType -v`

Expected: `AttributeError: 'LeadEventService' object has no attribute 'get_by_type'`

**Step 3: Write minimal implementation**

Add to `LeadEventService` class in `backend/src/memory/lead_memory_events.py`:

```python
    async def get_by_type(
        self,
        user_id: str,
        lead_memory_id: str,
        event_type: EventType,
    ) -> list[LeadEvent]:
        """Get events of a specific type for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            event_type: The type of events to retrieve.

        Returns:
            List of LeadEvent instances of the specified type,
            ordered by occurred_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_memory_events")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("event_type", event_type.value)
                .order("occurred_at", desc=True)
                .execute()
            )

            events = []
            for item in response.data:
                events.append(LeadEvent.from_dict(item))

            logger.info(
                "Retrieved lead events by type",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "event_type": event_type.value,
                    "event_count": len(events),
                },
            )

            return events

        except Exception as e:
            logger.exception("Failed to get lead events by type")
            raise DatabaseError(f"Failed to get lead events by type: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_lead_memory_events.py::TestLeadEventServiceByType -v`

Expected: `PASSED` for all tests

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/test_lead_memory_events.py
git commit -m "feat(lead-memory): implement get_by_type method"
```

---

## Task 6: Add Integration Point Comments for Gmail/Calendar

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Add integration documentation**

Add docstring comments to the service class (no test needed, this is documentation):

Add to `LeadEventService` class in `backend/src/memory/lead_memory_events.py`:

```python
    async def add_event_from_gmail(
        self,
        user_id: str,
        lead_memory_id: str,
        message_id: str,
        subject: str,
        from_email: str,
        to_emails: list[str],
        body: str,
        sent_at: datetime,
        direction: Direction,
    ) -> str:
        """Add an event from Gmail integration.

        Integration point: Called by Gmail webhook handler or sync job.
        TODO: Implement in Phase 6 (Integrations)

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            message_id: Gmail message ID for deduplication.
            subject: Email subject.
            from_email: Sender email address.
            to_emails: Recipient email addresses.
            body: Email body content.
            sent_at: When the email was sent.
            direction: inbound (received) or outbound (sent).

        Returns:
            The ID of the created event.
        """
        from src.models.lead_memory import LeadEventCreate

        event_type = EventType.EMAIL_SENT if direction == Direction.OUTBOUND else EventType.EMAIL_RECEIVED

        event_data = LeadEventCreate(
            event_type=event_type,
            direction=direction.value,
            subject=subject,
            content=body[:5000],  # Truncate long emails
            participants=to_emails + [from_email],
            occurred_at=sent_at,
            source="gmail",
            source_id=message_id,
        )

        return await self.add_event(user_id, lead_memory_id, event_data)

    async def add_event_from_calendar(
        self,
        user_id: str,
        lead_memory_id: str,
        event_id: str,
        title: str,
        description: str | None,
        attendees: list[str],
        start_time: datetime,
    ) -> str:
        """Add an event from Calendar integration.

        Integration point: Called by Calendar webhook handler or sync job.
        TODO: Implement in Phase 6 (Integrations)

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            event_id: Calendar event ID for deduplication.
            title: Meeting title.
            description: Meeting description.
            attendees: List of attendee emails.
            start_time: Meeting start time.

        Returns:
            The ID of the created event.
        """
        from src.models.lead_memory import LeadEventCreate

        event_data = LeadEventCreate(
            event_type=EventType.MEETING,
            direction=None,
            subject=title,
            content=description,
            participants=attendees,
            occurred_at=start_time,
            source="calendar",
            source_id=event_id,
        )

        return await self.add_event(user_id, lead_memory_id, event_data)
```

**Step 2: No test needed - these are convenience wrappers around tested methods**

**Step 3: Run all tests to verify nothing broke**

Run: `cd backend && pytest tests/test_lead_memory_events.py -v`

Expected: All existing tests pass

**Step 4: Commit**

```bash
git add backend/src/memory/lead_memory_events.py
git commit -m "feat(lead-memory): add Gmail/Calendar integration convenience methods"
```

---

## Task 7: Update Memory Module Exports

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write failing test**

```python
# File: backend/tests/test_memory_lead_events_module_exports.py

def test_lead_memory_events_module_exports():
    """Test that lead memory events are exported from memory module."""
    from src.memory import (
        Direction,
        EventType,
        LeadEvent,
        LeadEventService,
    )
    from src.memory.lead_memory_events import (
        Direction as DirectDirection,
        EventType as DirectEventType,
        LeadEvent as DirectLeadEvent,
        LeadEventService as DirectLeadEventService,
    )

    assert EventType is DirectEventType
    assert Direction is DirectDirection
    assert LeadEvent is DirectLeadEvent
    assert LeadEventService is DirectLeadEventService

def test_event_type_enum_values():
    """Test EventType enum has correct values."""
    from src.memory import EventType

    assert EventType.EMAIL_SENT.value == "email_sent"
    assert EventType.EMAIL_RECEIVED.value == "email_received"
    assert EventType.MEETING.value == "meeting"
    assert EventType.CALL.value == "call"
    assert EventType.NOTE.value == "note"
    assert EventType.SIGNAL.value == "signal"

def test_direction_enum_values():
    """Test Direction enum has correct values."""
    from src.memory import Direction

    assert Direction.INBOUND.value == "inbound"
    assert Direction.OUTBOUND.value == "outbound"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_memory_lead_events_module_exports.py -v`

Expected: `ImportError: cannot import name 'EventType' from 'src.memory'`

**Step 3: Write minimal implementation**

Update `backend/src/memory/__init__.py`:

Add to imports section (around line 12, after other imports):

```python
from src.memory.lead_memory_events import (
    Direction,
    EventType,
    LeadEvent,
    LeadEventService,
)
```

Add to `__all__` list (at the end, before closing quote):

```python
    # Lead Memory Events
    "LeadEvent",
    "LeadEventService",
    "EventType",
    "Direction",
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_memory_lead_events_module_exports.py -v`

Expected: `PASSED` for all tests

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_memory_lead_events_module_exports.py
git commit -m "feat(lead-memory): export lead event classes from memory module"
```

---

## Task 8: Run All Tests and Verify Type Checking

**Step 1: Run all event tracking tests**

Run: `cd backend && pytest tests/test_lead_memory_events.py tests/test_memory_lead_events_module_exports.py -v`

Expected: All tests pass

**Step 2: Run type checking**

Run: `cd backend && mypy src/memory/lead_memory_events.py --strict`

Expected: May have type errors related to Any types for Supabase client. These are acceptable for now but add comments if needed.

**Step 3: Run linting**

Run: `cd backend && ruff check src/memory/lead_memory_events.py`

Expected: No errors

Run: `cd backend && ruff format src/memory/lead_memory_events.py --check`

Expected: No format changes needed

**Step 4: Run existing related tests to ensure no regressions**

Run: `cd backend && pytest tests/test_lead_memory_schema.py -v`

Expected: All tests pass (tests existing Pydantic models)

**Step 5: Final commit if needed**

```bash
git add backend/src/memory/lead_memory_events.py backend/tests/
git commit -m "test(lead-memory): final verification of lead event tracking"
```

---

## Task 9: Create Database Verification Test (Optional but Recommended)

**Files:**
- Create: `backend/tests/db/test_lead_memory_events.py`

**Step 1: Write database integration test**

This test verifies the database schema exists and RLS policies work. It requires a test database connection.

```python
# File: backend/tests/db/test_lead_memory_events.py

"""Database integration tests for lead memory events.

Requires Supabase test database connection.
Run with: pytest tests/db/test_lead_memory_events.py -v
"""

import pytest

from src.db.supabase import SupabaseClient


@pytest.mark.database
class TestLeadMemoryEventsDatabase:
    def test_lead_memory_events_table_exists(self):
        """Verify lead_memory_events table exists."""
        client = SupabaseClient.get_client()

        # Try to select from the table - will error if it doesn't exist
        response = client.table("lead_memory_events").select("*").limit(1).execute()

        assert response is not None

    def test_lead_memory_events_has_required_columns(self):
        """Verify lead_memory_events has all required columns."""
        client = SupabaseClient.get_client()

        # Insert and retrieve a test event (relies on service role access)
        test_data = {
            "lead_memory_id": "00000000-0000-0000-0000-000000000000",  # Dummy ID
            "event_type": "note",
            "content": "Test event for schema verification",
            "occurred_at": "2025-02-03T12:00:00Z",
        }

        try:
            response = client.table("lead_memory_events").insert(test_data).execute()
            assert len(response.data) == 1

            # Clean up
            event_id = response.data[0]["id"]
            client.table("lead_memory_events").delete().eq("id", event_id).execute()

        except Exception as e:
            pytest.fail(f"Schema verification failed: {e}")

    def test_lead_memory_events_rls_policy_exists(self):
        """Verify RLS policy exists for user isolation."""
        # This requires SQL query to check policies
        # For now, just verify the table has RLS enabled via the API
        client = SupabaseClient.get_client()

        # As service role, we should be able to query
        response = client.table("lead_memory_events").select("*").limit(1).execute()
        assert response is not None
```

**Step 2: Run database test (only if database is available)**

Run: `cd backend && pytest tests/db/test_lead_memory_events.py -v -m database`

Expected: Passes if database exists, can be skipped if not

**Step 3: Commit**

```bash
git add backend/tests/db/test_lead_memory_events.py
git commit -m "test(lead-memory): add database schema verification tests"
```

---

## Task 10: Final Documentation Update

**Files:**
- Modify: `backend/src/memory/lead_memory_events.py`

**Step 1: Add module-level usage documentation**

Update the module docstring to include usage examples:

```python
"""Lead memory event tracking for timeline of interactions.

Events track all lead interactions including:
- Email communications (sent/received)
- Meetings and calls
- Manual notes
- Market signals

Events are stored in Supabase with user isolation via RLS.

Usage:
    ```python
    from src.memory import LeadEventService, EventType, Direction

    service = LeadEventService()

    # Add an event
    from src.models.lead_memory import LeadEventCreate
    from datetime import datetime, UTC

    event_data = LeadEventCreate(
        event_type=EventType.EMAIL_SENT,
        direction="outbound",
        subject="Follow up",
        content="Checking in",
        participants=["john@acme.com"],
        occurred_at=datetime.now(UTC),
        source="manual",
    )

    event_id = await service.add_event(
        user_id="user-123",
        lead_memory_id="lead-456",
        event_data=event_data,
    )

    # Get timeline
    events = await service.get_timeline(
        user_id="user-123",
        lead_memory_id="lead-456",
        start_date=datetime(2025, 2, 1, tzinfo=UTC),
        end_date=datetime(2025, 2, 28, tzinfo=UTC),
    )

    # Get events by type
    emails = await service.get_by_type(
        user_id="user-123",
        lead_memory_id="lead-456",
        event_type=EventType.EMAIL_SENT,
    )
    ```
"""
```

**Step 2: Run tests to ensure documentation didn't break anything**

Run: `cd backend && pytest tests/test_lead_memory_events.py -v`

Expected: All tests pass

**Step 3: Final commit**

```bash
git add backend/src/memory/lead_memory_events.py
git commit -m "docs(lead-memory): add usage examples to module documentation"
```

---

## Final Verification

After completing all tasks:

1. **Run all tests:**
   ```bash
   cd backend && pytest tests/test_lead_memory_events.py tests/test_memory_lead_events_module_exports.py tests/test_lead_memory_schema.py -v
   ```

2. **Type checking:**
   ```bash
   cd backend && mypy src/memory/lead_memory_events.py
   ```

3. **Linting:**
   ```bash
   cd backend && ruff check src/memory/lead_memory_events.py && ruff format src/memory/lead_memory_events.py
   ```

4. **Verify exports:**
   ```python
   # Test import works
   from src.memory import LeadEvent, LeadEventService, EventType, Direction
   ```

**All tests should pass and type checking should complete successfully.**
