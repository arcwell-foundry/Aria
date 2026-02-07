"""Tests for search API routes.

This module tests the search endpoints:
- GET /api/v1/search?q=query&types=leads,goals&limit=10
- GET /api/v1/search/recent?limit=10
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.services.search_service import (
    RecentItem,
    SearchResult,
)


class TestSearchRoutes:
    """Tests for the search endpoints."""

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_search_endpoint_returns_results(self, mock_search_service_class):
        """Test that GET /search returns search results."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.global_search.return_value = [
            SearchResult(
                type="lead",
                id="lead_456",
                title="Pfizer Inc.",
                snippet="Stage: discovery | Health: 75/100",
                score=0.95,
                url="/leads/lead_456",
            ),
            SearchResult(
                type="goal",
                id="goal_789",
                title="Close Pfizer deal",
                snippet="Pursue Pfizer opportunity for CDMO partnership",
                score=0.88,
                url="/goals/goal_789",
            ),
        ]
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import global_search

        results = await global_search(
            mock_user,
            query="Pfizer",
            types=["leads", "goals"],
            limit=10,
        )

        assert len(results) == 2
        assert results[0]["type"] == "lead"
        assert results[0]["id"] == "lead_456"
        assert results[0]["title"] == "Pfizer Inc."

        # Verify search service was called correctly
        mock_search_service.global_search.assert_called_once_with(
            user_id="user_123", query="Pfizer", types=["leads", "goals"], limit=10
        )

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_search_empty_query(self, mock_search_service_class):
        """Test that empty query returns empty results."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.global_search.return_value = []
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import global_search

        results = await global_search(
            mock_user,
            query="",
            limit=10,
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_search_no_types_filter(self, mock_search_service_class):
        """Test search with no types filter searches all types."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.global_search.return_value = []
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import global_search

        await global_search(
            mock_user,
            query="test",
            limit=10,
        )

        # Verify search service was called
        mock_search_service.global_search.assert_called_once()
        # The types parameter should be None when not provided (or handled by the service)

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_search_custom_limit(self, mock_search_service_class):
        """Test that custom limit is passed to search service."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.global_search.return_value = []
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import global_search

        await global_search(
            mock_user,
            query="test",
            limit=20,
        )

        # Verify limit was passed correctly
        mock_search_service.global_search.assert_called_once()
        call_kwargs = mock_search_service.global_search.call_args[1]
        assert call_kwargs["limit"] == 20

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_recent_items_endpoint(self, mock_search_service_class):
        """Test that GET /search/recent returns recent items."""
        # Mock search service
        mock_search_service = AsyncMock()
        test_time = datetime(2025, 2, 7, 14, 0, tzinfo=UTC)
        mock_search_service.recent_items.return_value = [
            RecentItem(
                type="lead",
                id="lead_456",
                title="Pfizer",
                url="/leads/lead_456",
                accessed_at=test_time,
            ),
            RecentItem(
                type="goal",
                id="goal_789",
                title="Close deal",
                url="/goals/goal_789",
                accessed_at=test_time,
            ),
        ]
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import get_recent_items

        results = await get_recent_items(
            mock_user,
            limit=10,
        )

        assert len(results) == 2
        assert results[0]["type"] == "lead"
        assert results[0]["id"] == "lead_456"
        assert results[0]["title"] == "Pfizer"

        # Verify search service was called correctly
        mock_search_service.recent_items.assert_called_once_with(
            user_id="user_123", limit=10
        )

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_recent_items_custom_limit(self, mock_search_service_class):
        """Test that custom limit is passed to recent_items."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.recent_items.return_value = []
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import get_recent_items

        await get_recent_items(
            mock_user,
            limit=5,
        )

        # Verify limit was passed correctly
        mock_search_service.recent_items.assert_called_once_with(
            user_id="user_123", limit=5
        )

    @pytest.mark.asyncio
    @patch("src.api.routes.search.SearchService")
    async def test_recent_items_empty(self, mock_search_service_class):
        """Test that empty recent items returns empty array."""
        # Mock search service
        mock_search_service = AsyncMock()
        mock_search_service.recent_items.return_value = []
        mock_search_service_class.return_value = mock_search_service

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_123"

        from src.api.routes.search import get_recent_items

        results = await get_recent_items(
            mock_user,
            limit=10,
        )

        assert len(results) == 0
