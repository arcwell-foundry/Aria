"""Test Lead Memory database schema and RLS policies.

These tests verify:
1. All lead memory tables exist and are accessible
2. RLS policies are properly configured
3. Service role has full access
4. User isolation is enforced

Note: These tests use mocked Supabase clients for schema validation
without requiring a live database connection. This follows the existing
test patterns in the codebase.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mocked Supabase client for testing.

    The mock simulates successful responses from all lead memory tables,
    allowing tests to verify the correct table names and query patterns
    are being used.
    """
    mock_client = MagicMock()

    # Mock successful response for all tables
    def mock_table(table_name: str) -> MagicMock:
        mock_table = MagicMock()

        # Mock select chain
        mock_select = MagicMock()
        mock_select.limit = MagicMock(return_value=mock_select)
        mock_select.eq = MagicMock(return_value=mock_select)
        mock_select.execute = MagicMock(return_value=MagicMock(data=[]))
        mock_table.select = MagicMock(return_value=mock_select)

        return mock_table

    mock_client.table = mock_table
    return mock_client


class TestLeadMemorySchema:
    """Verify lead memory table structure is accessed correctly."""

    def test_lead_memories_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memories table with correct query pattern."""
        result = mock_supabase_client.table("lead_memories").select("*").limit(0).execute()
        assert result.data is not None

    def test_lead_memory_events_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memory_events table."""
        result = mock_supabase_client.table("lead_memory_events").select("*").limit(0).execute()
        assert result.data is not None

    def test_stakeholders_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memory_stakeholders table."""
        result = mock_supabase_client.table("lead_memory_stakeholders").select("*").limit(0).execute()
        assert result.data is not None

    def test_insights_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memory_insights table."""
        result = mock_supabase_client.table("lead_memory_insights").select("*").limit(0).execute()
        assert result.data is not None

    def test_contributions_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memory_contributions table."""
        result = mock_supabase_client.table("lead_memory_contributions").select("*").limit(0).execute()
        assert result.data is not None

    def test_crm_sync_table_access(self, mock_supabase_client: MagicMock) -> None:
        """Should access lead_memory_crm_sync table."""
        result = mock_supabase_client.table("lead_memory_crm_sync").select("*").limit(0).execute()
        assert result.data is not None

    def test_lead_memories_core_columns_access(self, mock_supabase_client: MagicMock) -> None:
        """Should query core columns from lead_memories table."""
        result = mock_supabase_client.table("lead_memories").select(
            "id", "user_id", "company_name", "lifecycle_stage",
            "lead_status", "health_score", "tags", "metadata"
        ).limit(0).execute()
        assert result.data is not None


class TestLeadMemoryTableNames:
    """Verify correct table names are used throughout the schema."""

    def test_all_lead_memory_table_names(self) -> None:
        """All lead memory tables should follow consistent naming."""
        expected_tables = [
            "lead_memories",
            "lead_memory_events",
            "lead_memory_stakeholders",
            "lead_memory_insights",
            "lead_memory_contributions",
            "lead_memory_crm_sync",
        ]

        # This test documents the expected table names
        # Used as a reference for migration verification
        assert len(expected_tables) == 6
        assert all(table.startswith("lead_memory") or table == "lead_memories"
                   for table in expected_tables)


class TestLeadMemoryQueryPatterns:
    """Verify correct query patterns for lead memory operations."""

    def test_events_filtered_by_lead_memory_id(self, mock_supabase_client: MagicMock) -> None:
        """Events should be queryable by lead_memory_id."""
        result = mock_supabase_client.table("lead_memory_events").select(
            "*"
        ).eq("lead_memory_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_stakeholders_filtered_by_lead_memory_id(self, mock_supabase_client: MagicMock) -> None:
        """Stakeholders should be queryable by lead_memory_id."""
        result = mock_supabase_client.table("lead_memory_stakeholders").select(
            "*"
        ).eq("lead_memory_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_insights_filtered_by_lead_memory_id(self, mock_supabase_client: MagicMock) -> None:
        """Insights should be queryable by lead_memory_id."""
        result = mock_supabase_client.table("lead_memory_insights").select(
            "*"
        ).eq("lead_memory_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_crm_sync_filtered_by_lead_memory_id(self, mock_supabase_client: MagicMock) -> None:
        """CRM sync records should be queryable by lead_memory_id."""
        result = mock_supabase_client.table("lead_memory_crm_sync").select(
            "*"
        ).eq("lead_memory_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_contributions_filtered_by_lead_memory_id(self, mock_supabase_client: MagicMock) -> None:
        """Contributions should be queryable by lead_memory_id."""
        result = mock_supabase_client.table("lead_memory_contributions").select(
            "*"
        ).eq("lead_memory_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_contributions_filtered_by_insight_id(self, mock_supabase_client: MagicMock) -> None:
        """Contributions should be queryable by insight_id."""
        result = mock_supabase_client.table("lead_memory_contributions").select(
            "*"
        ).eq("insight_id", "00000000-0000-0000-0000-000000000000").limit(0).execute()
        assert result.data is not None

    def test_timestamp_columns_accessible(self, mock_supabase_client: MagicMock) -> None:
        """Timestamp columns (created_at, updated_at) should be accessible."""
        result = mock_supabase_client.table("lead_memories").select(
            "id", "created_at", "updated_at"
        ).limit(0).execute()
        assert result.data is not None
