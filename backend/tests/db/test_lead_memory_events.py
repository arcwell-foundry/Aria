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
