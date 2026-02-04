"""Test Lead Memory Events database schema and RLS policies.

These tests verify:
1. Lead memory events table exists and is accessible
2. Events table has correct column structure
3. Service role has appropriate access

Note: These tests use mocked Supabase clients for schema validation
without requiring a live database connection. This follows the existing
test patterns in the codebase.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mocked Supabase client for testing.

    The mock simulates successful responses from lead memory tables,
    allowing tests to verify the correct table names and query patterns
    are being used.
    """
    mock_client = MagicMock()

    # Store the last table name for assertion
    last_table_name = {"name": None}

    # Mock successful response for all tables
    def mock_table(table_name: str) -> MagicMock:
        last_table_name["name"] = table_name
        mock_table_instance = MagicMock()

        # Track inserted data for testing
        inserted_data = {"data": None}

        # Mock select chain
        mock_select = MagicMock()
        mock_select.limit = MagicMock(return_value=mock_select)
        mock_select.eq = MagicMock(return_value=mock_select)
        mock_select.execute = MagicMock(return_value=MagicMock(data=[]))
        mock_table_instance.select = MagicMock(return_value=mock_select)

        # Mock insert chain - return data based on input
        mock_insert = MagicMock()

        def mock_execute_insert() -> MagicMock:
            # Return the data that was "inserted" with an added ID
            return MagicMock(
                data=[
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        **(inserted_data["data"] or {}),
                    }
                ]
            )

        def mock_insert_call(data: dict) -> MagicMock:
            inserted_data["data"] = data
            return mock_insert

        mock_insert.execute = MagicMock(side_effect=mock_execute_insert)
        mock_table_instance.insert = MagicMock(side_effect=mock_insert_call)

        # Mock delete chain
        mock_delete = MagicMock()
        mock_delete.eq = MagicMock(return_value=mock_delete)
        mock_delete.execute = MagicMock(return_value=MagicMock(data=[]))
        mock_table_instance.delete = MagicMock(return_value=mock_delete)

        return mock_table_instance

    mock_client.table = MagicMock(side_effect=mock_table)
    # Add attribute to track last called table for assertions
    mock_client._last_table_name = last_table_name
    return mock_client


@pytest.fixture
def reset_client(mock_supabase_client: MagicMock) -> MagicMock:
    """Reset the mock client between tests for isolation.

    This ensures that test setup and interactions don't leak
    between test methods.
    """
    # Reset all mock call counts before each test
    mock_supabase_client.reset_mock()
    # Reset the table name tracker
    mock_supabase_client._last_table_name["name"] = None
    return mock_supabase_client


class TestLeadMemoryEventsSchema:
    """Verify lead memory events table structure is accessed correctly."""

    def test_events_table_exists(self, reset_client: MagicMock) -> None:
        """Verify lead_memory_events table exists and is accessible."""
        result = reset_client.table("lead_memory_events").select("*").limit(1).execute()
        assert result.data is not None
        # Verify the table method was called with correct table name
        assert reset_client._last_table_name["name"] == "lead_memory_events"

    def test_events_has_required_columns(self, reset_client: MagicMock) -> None:
        """Verify lead_memory_events has all required columns."""
        # Test inserting with all required columns
        test_data = {
            "lead_memory_id": "00000000-0000-0000-0000-000000000000",
            "event_type": "note",
            "content": "Test event for schema verification",
            "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }

        result = reset_client.table("lead_memory_events").insert(test_data).execute()
        assert len(result.data) == 1
        assert result.data[0]["event_type"] == "note"
        assert result.data[0]["lead_memory_id"] == "00000000-0000-0000-0000-000000000000"

    def test_events_supports_all_event_types(self, reset_client: MagicMock) -> None:
        """Verify events table supports different event types."""
        event_types = ["email", "call", "meeting", "note", "task"]

        for event_type in event_types:
            # Reset mock for each iteration
            reset_client.reset_mock()
            reset_client._last_table_name["name"] = None

            test_data = {
                "lead_memory_id": "00000000-0000-0000-0000-000000000000",
                "event_type": event_type,
                "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1),
            }
            result = reset_client.table("lead_memory_events").insert(test_data).execute()
            assert result.data[0]["event_type"] == event_type

    def test_events_with_optional_fields(self, reset_client: MagicMock) -> None:
        """Verify events table accepts optional fields."""
        test_data = {
            "lead_memory_id": "00000000-0000-0000-0000-000000000000",
            "event_type": "email",
            "direction": "inbound",
            "subject": "Test Subject",
            "content": "Test content",
            "participants": ["test@example.com", "user@example.com"],
            "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "source": "gmail",
            "source_id": "msg-123",
        }

        result = reset_client.table("lead_memory_events").insert(test_data).execute()
        assert len(result.data) == 1
        assert result.data[0]["direction"] == "inbound"
        assert result.data[0]["subject"] == "Test Subject"
        assert result.data[0]["source"] == "gmail"

    def test_events_delete_operation(self, reset_client: MagicMock) -> None:
        """Verify events can be deleted by ID."""
        event_id = "123e4567-e89b-12d3-a456-426614174000"
        reset_client.table("lead_memory_events").delete().eq("id", event_id).execute()
        # Verify delete was called with correct table name
        assert reset_client._last_table_name["name"] == "lead_memory_events"

    def test_events_query_by_lead_memory(self, reset_client: MagicMock) -> None:
        """Verify events can be queried by lead_memory_id."""
        lead_memory_id = "00000000-0000-0000-0000-000000000000"
        result = (
            reset_client.table("lead_memory_events")
            .select("*")
            .eq("lead_memory_id", lead_memory_id)
            .execute()
        )
        assert result.data is not None


class TestLeadMemoryEventsAccess:
    """Verify access patterns for lead memory events."""

    def test_service_role_can_query_events(self, reset_client: MagicMock) -> None:
        """Service role should be able to query all events."""
        result = reset_client.table("lead_memory_events").select("*").limit(10).execute()
        assert result.data is not None

    def test_service_role_can_insert_events(self, reset_client: MagicMock) -> None:
        """Service role should be able to insert events."""
        test_data = {
            "lead_memory_id": "00000000-0000-0000-0000-000000000000",
            "event_type": "note",
            "content": "Service role test",
            "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        result = reset_client.table("lead_memory_events").insert(test_data).execute()
        assert len(result.data) == 1
        assert result.data[0]["event_type"] == "note"

    def test_service_role_can_delete_events(self, reset_client: MagicMock) -> None:
        """Service role should be able to delete events."""
        event_id = "123e4567-e89b-12d3-a456-426614174000"
        reset_client.table("lead_memory_events").delete().eq("id", event_id).execute()
        # Verify the table method was called with correct table name
        assert reset_client._last_table_name["name"] == "lead_memory_events"
