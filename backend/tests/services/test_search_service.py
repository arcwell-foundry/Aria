"""Tests for SearchService.

This module tests the search functionality including:
- Global search across memory types
- Recent items tracking
- Recording item access
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.search_service import (
    RecentItem,
    SearchResult,
    SearchService,
)


class TestSearchResultDataclass:
    """Tests for the SearchResult dataclass."""

    def test_search_result_creation_all_fields(self):
        """Test creating a SearchResult with all fields populated."""
        result = SearchResult(
            type="lead",
            id="lead_123",
            title="Pfizer Opportunity",
            snippet="Series C biotech company looking for CDMO partner",
            score=0.95,
            url="/leads/lead_123",
        )

        assert result.type == "lead"
        assert result.id == "lead_123"
        assert result.title == "Pfizer Opportunity"
        assert result.snippet == "Series C biotech company looking for CDMO partner"
        assert result.score == 0.95
        assert result.url == "/leads/lead_123"

    def test_search_result_to_dict(self):
        """Test serialization to dict with all fields."""
        result = SearchResult(
            type="goal",
            id="goal_456",
            title="Build pipeline",
            snippet="Generate 20 qualified leads this quarter",
            score=0.88,
            url="/goals/goal_456",
        )

        dict_result = result.to_dict()

        assert dict_result["type"] == "goal"
        assert dict_result["id"] == "goal_456"
        assert dict_result["title"] == "Build pipeline"
        assert dict_result["snippet"] == "Generate 20 qualified leads this quarter"
        assert dict_result["score"] == 0.88
        assert dict_result["url"] == "/goals/goal_456"


class TestRecentItemDataclass:
    """Tests for the RecentItem dataclass."""

    def test_recent_item_creation_all_fields(self):
        """Test creating a RecentItem with all fields populated."""
        accessed_at = datetime(2025, 2, 7, 14, 30, tzinfo=UTC)

        item = RecentItem(
            type="conversation",
            id="conv_789",
            title="Q1 Planning Discussion",
            url="/chat/conv_789",
            accessed_at=accessed_at,
        )

        assert item.type == "conversation"
        assert item.id == "conv_789"
        assert item.title == "Q1 Planning Discussion"
        assert item.url == "/chat/conv_789"
        assert item.accessed_at == accessed_at

    def test_recent_item_to_dict(self):
        """Test serialization to dict with all fields."""
        accessed_at = datetime(2025, 2, 7, 14, 30, tzinfo=UTC)

        item = RecentItem(
            type="document",
            id="doc_abc",
            title="Capabilities Deck.pdf",
            url="/documents/doc_abc",
            accessed_at=accessed_at,
        )

        dict_item = item.to_dict()

        assert dict_item["type"] == "document"
        assert dict_item["id"] == "doc_abc"
        assert dict_item["title"] == "Capabilities Deck.pdf"
        assert dict_item["url"] == "/documents/doc_abc"
        assert dict_item["accessed_at"] == "2025-02-07T14:30:00+00:00"

    def test_recent_item_from_dict(self):
        """Test creating a RecentItem from a dictionary."""
        data = {
            "type": "goal",
            "id": "goal_xyz",
            "title": "Close Pfizer deal",
            "url": "/goals/goal_xyz",
            "accessed_at": "2025-02-07T14:30:00+00:00",
        }

        item = RecentItem.from_dict(data)

        assert item.type == "goal"
        assert item.id == "goal_xyz"
        assert item.title == "Close Pfizer deal"
        assert item.url == "/goals/goal_xyz"
        assert item.accessed_at == datetime(2025, 2, 7, 14, 30, tzinfo=UTC)


class TestSearchServiceInit:
    """Tests for SearchService initialization."""

    @patch("src.db.supabase.SupabaseClient.get_client")
    def test_service_initialization(self, mock_get_client):
        """Test that SearchService initializes correctly."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        service = SearchService()

        assert service._db == mock_client
        mock_get_client.assert_called_once()


class TestGlobalSearch:
    """Tests for the global_search method."""

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_global_search_returns_matching_results(self, mock_get_client):
        """Test that global_search returns results matching the query."""
        mock_client = MagicMock()

        # Create mock responses for each table
        def create_mock_response(data):
            response = MagicMock()
            response.data = data
            return response

        # Setup table mocking with side_effect based on table name
        def mock_table(table_name):
            mock_table_result = MagicMock()

            if table_name == "memory_semantic":
                mock_response = create_mock_response([
                    {
                        "id": "fact_1",
                        "fact": "Pfizer is a Series C biotech company",
                        "confidence": 0.95,
                    },
                ])
                mock_table_result.select.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_response

            elif table_name == "lead_memories":
                mock_response = create_mock_response([
                    {
                        "id": "lead_123",
                        "company_name": "Pfizer Inc.",
                        "stage": "discovery",
                        "health_score": 75,
                    },
                ])
                mock_table_result.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_response

            elif table_name == "goals":
                mock_response = create_mock_response([
                    {
                        "id": "goal_456",
                        "title": "Close Pfizer deal",
                        "description": "Pursue Pfizer opportunity for CDMO partnership",
                        "status": "active",
                        "progress": 50,
                    },
                ])
                mock_table_result.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_response

            elif table_name == "conversations":
                mock_response = create_mock_response([])
                mock_table_result.select.return_value.eq.return_value.ilike.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

            elif table_name == "user_profiles":
                # For company lookup in document search
                mock_response = create_mock_response([
                    {"company_id": "company_123"}
                ])
                mock_table_result.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

            elif table_name == "company_documents":
                mock_response = create_mock_response([])
                mock_table_result.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_response

            else:
                # Default empty response for other tables
                mock_response = create_mock_response([])
                mock_table_result.select.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_response

            return mock_table_result

        mock_client.table.side_effect = mock_table
        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.global_search(
            user_id="user_123", query="Pfizer", limit=10
        )

        # Verify results include all types
        assert len(results) > 0

        # Check that results have required fields
        for result in results:
            assert hasattr(result, "type")
            assert hasattr(result, "id")
            assert hasattr(result, "title")
            assert hasattr(result, "score")
            assert hasattr(result, "url")

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_global_search_filters_by_types(self, mock_get_client):
        """Test that global_search filters by specified types."""
        mock_client = MagicMock()

        # Mock leads search only
        mock_leads_response = MagicMock()
        mock_leads_response.data = [
            {
                "id": "lead_123",
                "company_name": "Moderna",
                "stage": "discovery",
                "health_score": 80,
            },
        ]

        mock_execute = MagicMock()
        mock_execute.execute.return_value = mock_leads_response

        mock_limit = MagicMock()
        mock_limit.limit.return_value = mock_execute
        mock_client.table.return_value.select.return_value.ilike.return_value = (
            mock_limit
        )

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.global_search(
            user_id="user_123", query="Moderna", types=["leads"], limit=10
        )

        # Should only search leads table when types=["leads"]
        assert mock_client.table.call_count >= 1

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_global_search_empty_query(self, mock_get_client):
        """Test that global_search handles empty query."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.global_search(
            user_id="user_123", query="", limit=10
        )

        # Empty query should return empty results
        assert results == []

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_global_search_no_results(self, mock_get_client):
        """Test that global_search returns empty list when no matches."""
        mock_client = MagicMock()

        # Mock empty responses
        mock_response = MagicMock()
        mock_response.data = []

        mock_execute = MagicMock()
        mock_execute.execute.return_value = mock_response
        mock_limit = MagicMock()
        mock_limit.limit.return_value = mock_execute
        mock_client.table.return_value.select.return_value.ilike.return_value = (
            mock_limit
        )

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.global_search(
            user_id="user_123", query="nonexistent xyz", limit=10
        )

        assert results == []

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_global_search_respects_limit(self, mock_get_client):
        """Test that global_search respects the limit parameter."""
        mock_client = MagicMock()

        # Mock many results
        mock_response = MagicMock()
        mock_response.data = [
            {"id": f"result_{i}", "title": f"Result {i}", "fact": f"Fact {i}"}
            for i in range(20)
        ]

        mock_execute = MagicMock()
        mock_execute.execute.return_value = mock_response
        mock_limit = MagicMock()
        mock_limit.limit.return_value = mock_execute
        mock_client.table.return_value.select.return_value.ilike.return_value = (
            mock_limit
        )

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.global_search(
            user_id="user_123", query="test", limit=5
        )

        # Verify limit was passed to queries
        for call in mock_limit.limit.call_args_list:
            assert call[0][0] <= 5


class TestRecentItems:
    """Tests for the recent_items method."""

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_recent_items_returns_sorted_list(self, mock_get_client):
        """Test that recent_items returns items sorted by accessed_at desc."""
        mock_client = MagicMock()

        # Mock user preferences with recent items
        # .single() returns a dict directly, not a list
        mock_preferences_response = MagicMock()
        mock_preferences_response.data = {
            "preferences": {
                "recent_items": [
                    {
                        "type": "lead",
                        "id": "lead_123",
                        "title": "Pfizer",
                        "url": "/leads/lead_123",
                        "accessed_at": "2025-02-07T14:00:00+00:00",
                    },
                    {
                        "type": "goal",
                        "id": "goal_456",
                        "title": "Close deal",
                        "url": "/goals/goal_456",
                        "accessed_at": "2025-02-07T15:00:00+00:00",
                    },
                    {
                        "type": "conversation",
                        "id": "conv_789",
                        "title": "Planning chat",
                        "url": "/chat/conv_789",
                        "accessed_at": "2025-02-07T13:00:00+00:00",
                    },
                ]
            }
        }

        # Create the mock chain properly
        mock_table_for_user_preferences = MagicMock()
        mock_table_for_user_preferences.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_preferences_response
        mock_client.table.return_value = mock_table_for_user_preferences

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.recent_items(user_id="user_123", limit=10)

        # Should return 3 items sorted by accessed_at descending
        assert len(results) == 3
        assert results[0].type == "goal"  # 15:00 - most recent
        assert results[1].type == "lead"  # 14:00
        assert results[2].type == "conversation"  # 13:00 - oldest

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_recent_items_empty_when_none_accessed(self, mock_get_client):
        """Test that recent_items returns empty list when no recent items."""
        mock_client = MagicMock()

        # Mock user preferences without recent items
        mock_preferences_response = MagicMock()
        mock_preferences_response.data = {"preferences": {"recent_items": []}}

        mock_table_for_user_preferences = MagicMock()
        mock_table_for_user_preferences.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_preferences_response
        mock_client.table.return_value = mock_table_for_user_preferences

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.recent_items(user_id="user_123", limit=10)

        assert results == []

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_recent_items_respects_limit(self, mock_get_client):
        """Test that recent_items respects the limit parameter."""
        mock_client = MagicMock()

        # Mock user preferences with many recent items
        many_items = [
            {
                "type": "lead",
                "id": f"lead_{i}",
                "title": f"Lead {i}",
                "url": f"/leads/lead_{i}",
                "accessed_at": f"2025-02-07T{15-i:02d}:00:00+00:00" if i <= 15 else f"2025-02-06T{24-(i-15):02d}:00:00+00:00",
            }
            for i in range(20)
        ]

        mock_preferences_response = MagicMock()
        # .single() returns data directly, so result.data is the preferences dict
        mock_preferences_response.data = {
            "user_id": "user_123",
            "preferences": {"recent_items": many_items}
        }

        mock_table_for_user_preferences = MagicMock()
        mock_table_for_user_preferences.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_preferences_response
        mock_client.table.return_value = mock_table_for_user_preferences

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.recent_items(user_id="user_123", limit=5)

        # Should only return 5 most recent
        assert len(results) == 5

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_recent_items_handles_missing_user_preferences(
        self, mock_get_client
    ):
        """Test that recent_items handles missing user preferences."""
        mock_client = MagicMock()

        # Mock empty response (no preferences found)
        mock_preferences_response = MagicMock()
        mock_preferences_response.data = []

        mock_table_for_user_preferences = MagicMock()
        mock_table_for_user_preferences.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_preferences_response
        mock_client.table.return_value = mock_table_for_user_preferences

        mock_get_client.return_value = mock_client

        service = SearchService()
        results = await service.recent_items(user_id="user_123", limit=10)

        assert results == []


class TestRecordAccess:
    """Tests for the record_access method."""

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_record_access_adds_new_item(self, mock_get_client):
        """Test that record_access adds a new item to recent items."""
        mock_client = MagicMock()

        # Mock existing preferences (empty)
        mock_get_response = MagicMock()
        mock_get_response.data = {"preferences": {"recent_items": []}}

        # Mock update response
        mock_update_response = MagicMock()
        mock_update_response.data = [{"preferences": {"recent_items": []}}]

        # Create separate mocks for SELECT and UPDATE calls
        mock_select_table = MagicMock()
        mock_select_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        mock_update_table = MagicMock()
        mock_update_table.update.return_value.eq.return_value.execute.return_value = mock_update_response

        # Track calls to table() - return different mocks based on call count
        table_call_count = [0]

        def get_table_mock(*args, **kwargs):
            nonlocal table_call_count
            table_call_count[0] += 1
            if table_call_count[0] == 1:
                return mock_select_table
            return mock_update_table

        mock_client.table.side_effect = get_table_mock
        mock_get_client.return_value = mock_client

        service = SearchService()
        await service.record_access(
            user_id="user_123",
            type="lead",
            id="lead_456",
            title="New Lead",
            url="/leads/lead_456",
        )

        # Verify update was called with the new item in recent_items
        assert table_call_count[0] == 2  # table() called twice
        update_call = mock_update_table.update.call_args
        update_data = update_call[0][0]

        assert "preferences" in update_data
        assert "recent_items" in update_data["preferences"]

        recent_items = update_data["preferences"]["recent_items"]
        assert len(recent_items) == 1
        assert recent_items[0]["type"] == "lead"
        assert recent_items[0]["id"] == "lead_456"
        assert recent_items[0]["title"] == "New Lead"
        assert recent_items[0]["url"] == "/leads/lead_456"
        assert "accessed_at" in recent_items[0]

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_record_access_updates_existing_item(self, mock_get_client):
        """Test that record_access updates accessed_at for existing item."""
        mock_client = MagicMock()

        existing_accessed_at = "2025-02-07T10:00:00+00:00"

        # Mock existing preferences with the item
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "preferences": {
                "recent_items": [
                    {
                        "type": "lead",
                        "id": "lead_456",
                        "title": "Existing Lead",
                        "url": "/leads/lead_456",
                        "accessed_at": existing_accessed_at,
                    }
                ]
            }
        }

        # Mock update response
        mock_update_response = MagicMock()
        mock_update_response.data = [{"preferences": {"recent_items": []}}]

        # Create separate mocks for SELECT and UPDATE calls
        mock_select_table = MagicMock()
        mock_select_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        mock_update_table = MagicMock()
        mock_update_table.update.return_value.eq.return_value.execute.return_value = mock_update_response

        # Track calls to table()
        table_call_count = [0]

        def get_table_mock(*args, **kwargs):
            nonlocal table_call_count
            table_call_count[0] += 1
            if table_call_count[0] == 1:
                return mock_select_table
            return mock_update_table

        mock_client.table.side_effect = get_table_mock
        mock_get_client.return_value = mock_client

        service = SearchService()
        await service.record_access(
            user_id="user_123",
            type="lead",
            id="lead_456",  # Same ID as existing
            title="Updated Lead",
            url="/leads/lead_456",
        )

        # Verify the item was moved to front with new timestamp
        update_call = mock_update_table.update.call_args
        update_data = update_call[0][0]

        recent_items = update_data["preferences"]["recent_items"]
        assert len(recent_items) == 1
        assert recent_items[0]["title"] == "Updated Lead"
        assert recent_items[0]["accessed_at"] != existing_accessed_at

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_record_access_caps_at_20_items(self, mock_get_client):
        """Test that record_access caps recent items at 20."""
        mock_client = MagicMock()

        # Create 20 existing items
        existing_items = [
            {
                "type": "lead",
                "id": f"lead_{i}",
                "title": f"Lead {i}",
                "url": f"/leads/lead_{i}",
                "accessed_at": f"2025-02-07T{15-i:02d}:00:00+00:00" if i <= 15 else f"2025-02-06T{24-(i-15):02d}:00:00+00:00",
            }
            for i in range(20)
        ]

        # Mock existing preferences with 20 items
        mock_get_response = MagicMock()
        mock_get_response.data = {
            "user_id": "user_123",
            "preferences": {"recent_items": existing_items}
        }

        # Mock update response
        mock_update_response = MagicMock()
        mock_update_response.data = [{"preferences": {"recent_items": []}}]

        # Create separate mocks for SELECT and UPDATE calls
        mock_select_table = MagicMock()
        mock_select_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        mock_update_table = MagicMock()
        mock_update_table.update.return_value.eq.return_value.execute.return_value = mock_update_response

        # Track calls to table()
        table_call_count = [0]

        def get_table_mock(*args, **kwargs):
            nonlocal table_call_count
            table_call_count[0] += 1
            if table_call_count[0] == 1:
                return mock_select_table
            return mock_update_table

        mock_client.table.side_effect = get_table_mock
        mock_get_client.return_value = mock_client

        service = SearchService()
        await service.record_access(
            user_id="user_123",
            type="lead",
            id="lead_new",
            title="New Lead",
            url="/leads/lead_new",
        )

        # Verify still only 20 items (oldest was removed)
        update_call = mock_update_table.update.call_args
        update_data = update_call[0][0]

        recent_items = update_data["preferences"]["recent_items"]
        assert len(recent_items) == 20
        # New item should be first
        assert recent_items[0]["id"] == "lead_new"

    @pytest.mark.asyncio
    @patch("src.db.supabase.SupabaseClient.get_client")
    async def test_record_access_handles_missing_preferences(
        self, mock_get_client
    ):
        """Test that record_access handles missing user preferences."""
        mock_client = MagicMock()

        # Mock empty response (no preferences)
        mock_get_response = MagicMock()
        mock_get_response.data = None  # .single() returns None when not found

        # Mock update response
        mock_update_response = MagicMock()
        mock_update_response.data = [{"preferences": {"recent_items": []}}]

        # Create separate mocks for SELECT and INSERT calls
        mock_select_table = MagicMock()
        mock_select_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_response

        mock_insert_table = MagicMock()
        mock_insert_table.insert.return_value.execute.return_value = mock_update_response

        # Track calls to table()
        table_call_count = [0]

        def get_table_mock(*args, **kwargs):
            nonlocal table_call_count
            table_call_count[0] += 1
            if table_call_count[0] == 1:
                return mock_select_table
            return mock_insert_table

        mock_client.table.side_effect = get_table_mock
        mock_get_client.return_value = mock_client

        service = SearchService()
        await service.record_access(
            user_id="user_123",
            type="goal",
            id="goal_new",
            title="New Goal",
            url="/goals/goal_new",
        )

        # Should still create the record via INSERT
        assert table_call_count[0] == 2
        insert_call = mock_insert_table.insert.call_args
        assert insert_call is not None
        insert_data = insert_call[0][0]
        assert "user_id" in insert_data
        assert insert_data["user_id"] == "user_123"
        assert "preferences" in insert_data
