"""Test calendar pull sync functionality (US-942 Task 4).

These tests verify:
1. Calendar sync creates research tasks for external meetings
2. Internal meetings don't create research tasks
3. Google Calendar event parsing works correctly
4. Outlook event parsing works correctly
5. External attendee detection works correctly
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

# Import directly to avoid circular import issues through __init__.py
import src.integrations.deep_sync
from src.integrations.deep_sync_domain import CalendarEvent
from src.integrations.domain import IntegrationType
from src.memory.prospective import TaskPriority, TaskStatus, TriggerType


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mocked Supabase client for testing."""
    mock_client = MagicMock()

    # Mock table responses
    def mock_table(table_name: str) -> MagicMock:
        mock_table = MagicMock()

        # Mock select chain for user_integrations
        if table_name == "user_integrations":
            mock_select = MagicMock()
            mock_eq = MagicMock(return_value=mock_select)
            mock_select.eq = mock_eq
            mock_maybe_single = MagicMock()
            mock_select.maybe_single = mock_maybe_single
            mock_maybe_single.execute = MagicMock(return_value=MagicMock(
                data={
                    "id": "integration-123",
                    "user_id": "user-123",
                    "integration_type": "google_calendar",
                    "composio_connection_id": "conn-123",
                    "status": "active",
                }
            ))
            mock_table.select = MagicMock(return_value=mock_select)

        return mock_table

    mock_client.table = mock_table
    return mock_client


@pytest.fixture
def mock_oauth_client() -> MagicMock:
    """Create a mocked OAuth client for testing."""
    mock_client = MagicMock()
    mock_client.execute_action = AsyncMock()
    return mock_client


@pytest.fixture
def mock_prospective_memory() -> MagicMock:
    """Create a mocked ProspectiveMemory for testing."""
    mock_memory = MagicMock()
    mock_memory.create_task = AsyncMock(return_value="task-123")
    return mock_memory


@pytest.fixture
def deep_sync_service(
    mock_supabase_client: MagicMock,
    mock_oauth_client: MagicMock,
    mock_prospective_memory: MagicMock,
) -> src.integrations.deep_sync.DeepSyncService:
    """Create a DeepSyncService instance with mocked dependencies."""
    # Patch ProspectiveMemory before importing DeepSyncService
    with patch("src.memory.prospective.ProspectiveMemory", return_value=mock_prospective_memory):
        service = src.integrations.deep_sync.DeepSyncService()

        # Replace with mocks
        service.supabase = mock_supabase_client
        service.integration_service = mock_oauth_client

        yield service


class TestCalendarPullSync:
    """Test calendar pull sync functionality."""

    @pytest.mark.asyncio
    async def test_sync_calendar_creates_research_tasks(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Calendar sync should create research tasks for external meetings."""
        # Mock calendar API response with external meeting
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        mock_oauth_client.execute_action.return_value = {
            "data": [
                {
                    "id": "event-1",
                    "summary": "Sales Call with Acme Corp",
                    "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
                    "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
                    "attendees": [
                        {"email": "user@company.com"},
                        {"email": "john@acmecorp.com"},
                        {"email": "jane@acmecorp.com"},
                    ],
                    "description": "Quarterly review meeting",
                    "location": "Conference Room A",
                }
            ]
        }

        # Execute sync
        result = await deep_sync_service.sync_calendar(
            user_id="user-123",
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        # Verify result
        assert result.records_processed == 1
        assert result.records_succeeded == 1
        assert result.records_failed == 0
        assert result.memory_entries_created == 1

        # Verify research task was created
        mock_prospective_memory.create_task.assert_called_once()
        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]

        assert "Prepare meeting brief" in task.task
        assert "Acme Corp" in task.description
        assert task.priority == TaskPriority.MEDIUM  # External meeting

    @pytest.mark.asyncio
    async def test_sync_calendar_internal_meeting(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Internal meetings should not create research tasks."""
        # Mock calendar API response with internal meeting
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        mock_oauth_client.execute_action.return_value = {
            "data": [
                {
                    "id": "event-2",
                    "summary": "Team Standup",
                    "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
                    "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
                    "attendees": [
                        {"email": "user@company.com"},
                        {"email": "colleague@company.com"},
                        {"email": "manager@company.com"},
                    ],
                }
            ]
        }

        # Execute sync
        result = await deep_sync_service.sync_calendar(
            user_id="user-123",
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        # Verify result
        assert result.records_processed == 1
        assert result.records_succeeded == 1
        assert result.records_failed == 0
        assert result.memory_entries_created == 0  # No research task for internal meeting

        # Verify no research task was created
        mock_prospective_memory.create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_calendar_handles_mixed_events(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_oauth_client: MagicMock,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Calendar sync should handle mix of internal and external events."""
        # Mock calendar API response with mixed events
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)
        day_after = now + timedelta(days=2)

        mock_oauth_client.execute_action.return_value = {
            "data": [
                {
                    "id": "event-1",
                    "summary": "External Sales Call",
                    "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
                    "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
                    "attendees": [{"email": "user@company.com"}, {"email": "client@external.com"}],
                },
                {
                    "id": "event-2",
                    "summary": "Internal Standup",
                    "start": {"dateTime": day_after.isoformat().replace("+00:00", "Z")},
                    "end": {"dateTime": (day_after + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
                    "attendees": [{"email": "user@company.com"}, {"email": "colleague@company.com"}],
                },
                {
                    "id": "event-3",
                    "summary": "Partner Meeting",
                    "start": {"dateTime": day_after.isoformat().replace("+00:00", "Z")},
                    "end": {"dateTime": (day_after + timedelta(hours=2)).isoformat().replace("+00:00", "Z")},
                    "attendees": [{"email": "user@company.com"}, {"email": "partner@partner.com"}],
                },
            ]
        }

        # Execute sync
        result = await deep_sync_service.sync_calendar(
            user_id="user-123",
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        # Verify result
        assert result.records_processed == 3
        assert result.records_succeeded == 3
        assert result.records_failed == 0
        assert result.memory_entries_created == 2  # Only external events

        # Verify 2 research tasks were created (not for internal meeting)
        assert mock_prospective_memory.create_task.call_count == 2


class TestParseCalendarEvent:
    """Test calendar event parsing."""

    def test_parse_calendar_event_google_format(self) -> None:
        """Should parse Google Calendar event format correctly."""
        service = src.integrations.deep_sync.DeepSyncService()

        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event_data = {
            "id": "google-event-123",
            "summary": "Quarterly Business Review",
            "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
            "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
            "attendees": [
                {"email": "user@company.com"},
                {"email": "client@acmecorp.com"},
            ],
            "description": "Review Q4 performance",
            "location": "Conference Room B",
        }

        event = service._parse_calendar_event(
            event_data=event_data,
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        assert event.external_id == "google-event-123"
        assert event.title == "Quarterly Business Review"
        assert event.description == "Review Q4 performance"
        assert event.location == "Conference Room B"
        assert len(event.attendees) == 2
        assert "user@company.com" in event.attendees
        assert "client@acmecorp.com" in event.attendees

    def test_parse_calendar_event_outlook_format(self) -> None:
        """Should parse Outlook event format correctly."""
        service = src.integrations.deep_sync.DeepSyncService()

        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event_data = {
            "id": "outlook-event-123",
            "subject": "Product Demo",
            "start": {"dateTime": tomorrow.isoformat()},
            "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat()},
            "attendees": [
                {
                    "emailAddress": {
                        "address": "user@company.com",
                        "name": "User Name",
                    }
                },
                {
                    "emailAddress": {
                        "address": "prospect@clientco.com",
                        "name": "Prospect Name",
                    }
                },
            ],
            "bodyPreview": "Demo of new features",
            "location": {"displayName": "Main Office"},
        }

        event = service._parse_calendar_event(
            event_data=event_data,
            integration_type=IntegrationType.OUTLOOK,
        )

        assert event.external_id == "outlook-event-123"
        assert event.title == "Product Demo"
        assert event.description == "Demo of new features"
        assert event.location == "Main Office"
        assert len(event.attendees) == 2
        assert "user@company.com" in event.attendees
        assert "prospect@clientco.com" in event.attendees

    def test_parse_calendar_event_is_external_detection(self) -> None:
        """Should correctly detect external meetings based on attendees."""
        service = src.integrations.deep_sync.DeepSyncService()

        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        # External meeting - has non-company attendees
        external_event_data = {
            "id": "event-external",
            "summary": "Client Meeting",
            "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
            "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
            "attendees": [
                {"email": "user@company.com"},
                {"email": "client@external.com"},
            ],
        }

        external_event = service._parse_calendar_event(
            event_data=external_event_data,
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )
        assert external_event.is_external is True

        # Internal meeting - all attendees from company
        internal_event_data = {
            "id": "event-internal",
            "summary": "Team Meeting",
            "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
            "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
            "attendees": [
                {"email": "user@company.com"},
                {"email": "colleague@company.com"},
            ],
        }

        internal_event = service._parse_calendar_event(
            event_data=internal_event_data,
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )
        assert internal_event.is_external is False

    def test_parse_calendar_event_with_date_only(self) -> None:
        """Should handle all-day events with date-only format."""
        service = src.integrations.deep_sync.DeepSyncService()

        tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()

        event_data = {
            "id": "event-allday",
            "summary": "All Day Event",
            "start": {"date": tomorrow.isoformat()},
            "end": {"date": tomorrow.isoformat()},
            "attendees": [{"email": "user@company.com"}],
        }

        event = service._parse_calendar_event(
            event_data=event_data,
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        # Should successfully parse with datetime fallback
        assert event.external_id == "event-allday"
        assert event.title == "All Day Event"
        assert event.start_time is not None
        assert event.end_time is not None

    def test_parse_calendar_event_no_attendees(self) -> None:
        """Should handle events with no attendees."""
        service = src.integrations.deep_sync.DeepSyncService()

        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event_data = {
            "id": "event-no-attendees",
            "summary": "Personal Event",
            "start": {"dateTime": tomorrow.isoformat().replace("+00:00", "Z")},
            "end": {"dateTime": (tomorrow + timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
        }

        event = service._parse_calendar_event(
            event_data=event_data,
            integration_type=IntegrationType.GOOGLE_CALENDAR,
        )

        assert event.external_id == "event-no-attendees"
        assert len(event.attendees) == 0
        assert event.is_external is False  # No attendees means internal

    def test_parse_datetime_string_with_z_suffix(self) -> None:
        """Should parse datetime strings with Z suffix."""
        service = src.integrations.deep_sync.DeepSyncService()

        # Test with Z suffix
        dt_str = "2026-02-08T14:30:00Z"
        result = service._parse_datetime_string(dt_str)

        assert result is not None
        assert result.tzinfo == UTC
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 8
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_datetime_string_with_timezone_offset(self) -> None:
        """Should parse datetime strings with timezone offset."""
        service = src.integrations.deep_sync.DeepSyncService()

        # Test with +00:00 offset
        dt_str = "2026-02-08T14:30:00+00:00"
        result = service._parse_datetime_string(dt_str)

        assert result is not None
        assert result.tzinfo == UTC
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 8

    def test_parse_datetime_string_invalid_fallback(self) -> None:
        """Should return current time for invalid datetime strings."""
        service = src.integrations.deep_sync.DeepSyncService()

        # Test with invalid string
        result = service._parse_datetime_string("invalid-date")

        # Should fallback to current time
        assert result is not None
        assert result.tzinfo == UTC


class TestCreateMeetingResearchTask:
    """Test meeting research task creation."""

    @pytest.mark.asyncio
    async def test_create_meeting_research_task_external(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Should create research task for external meeting with medium priority."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event = CalendarEvent(
            external_id="event-123",
            title="Sales Call with Acme Corp",
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=1),
            attendees=["user@company.com", "john@acmecorp.com"],
            description="Quarterly review",
            location="Conference Room A",
            is_external=True,
        )

        task_id = await deep_sync_service._create_meeting_research_task(
            user_id="user-123",
            event=event,
        )

        assert task_id == "task-123"
        mock_prospective_memory.create_task.assert_called_once()

        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]

        assert "Prepare meeting brief" in task.task
        assert "Acme Corp" in task.description
        assert "john@acmecorp.com" in task.description
        assert task.priority == TaskPriority.MEDIUM

        # Verify trigger is 24 hours before event
        trigger_at = datetime.fromisoformat(task.trigger_config["due_at"])
        expected_trigger = tomorrow - timedelta(hours=24)
        assert abs((trigger_at - expected_trigger).total_seconds()) < 60  # Within 1 minute

    @pytest.mark.asyncio
    async def test_create_meeting_research_task_internal(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Should create research task for internal meeting with low priority."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event = CalendarEvent(
            external_id="event-456",
            title="Team Standup",
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=1),
            attendees=["user@company.com", "colleague@company.com"],
            is_external=False,
        )

        task_id = await deep_sync_service._create_meeting_research_task(
            user_id="user-123",
            event=event,
        )

        assert task_id == "task-123"
        mock_prospective_memory.create_task.assert_called_once()

        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]

        assert task.priority == TaskPriority.LOW  # Internal meeting

    @pytest.mark.asyncio
    async def test_create_meeting_research_task_handles_many_attendees(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Should limit attendees display to 5 in task description."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        # Create event with 10 attendees
        attendees = [f"person{i}@external.com" for i in range(10)]
        event = CalendarEvent(
            external_id="event-789",
            title="Large Meeting",
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=1),
            attendees=attendees,
            is_external=True,
        )

        task_id = await deep_sync_service._create_meeting_research_task(
            user_id="user-123",
            event=event,
        )

        assert task_id == "task-123"
        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]

        # Should show first 5 attendees and "and X others"
        assert "person0@external.com" in task.description
        assert "person4@external.com" in task.description
        assert "and 5 others" in task.description

    @pytest.mark.asyncio
    async def test_create_meeting_research_task_with_location_and_description(
        self,
        deep_sync_service: src.integrations.deep_sync.DeepSyncService,
        mock_prospective_memory: MagicMock,
    ) -> None:
        """Should include location and description in task."""
        now = datetime.now(UTC)
        tomorrow = now + timedelta(days=1)

        event = CalendarEvent(
            external_id="event-999",
            title="Onsite Demo",
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=2),
            attendees=["client@external.com"],
            description="Demonstrate new product features to executive team. Focus on ROI and automation capabilities.",
            location="Client HQ, 123 Main St",
            is_external=True,
        )

        task_id = await deep_sync_service._create_meeting_research_task(
            user_id="user-123",
            event=event,
        )

        assert task_id == "task-123"
        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]

        assert "Client HQ" in task.description
        assert "Demonstrate new product" in task.description
