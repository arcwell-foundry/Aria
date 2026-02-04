"""Tests for pattern matching in proactive memory."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPatternMatching:
    """Tests for topic pattern matching."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Mock DB client."""
        mock = MagicMock()
        # Cooldown check returns empty (no recent surfacing)
        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[]
        )
        return mock

    @pytest.mark.asyncio
    async def test_pattern_matching_returns_empty_when_graphiti_not_initialized(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should return empty list when Graphiti not initialized."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Mock GraphitiClient at the source module level
        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = False

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Let's talk about the budget proposal",
                conversation_messages=[],
            )

            assert isinstance(insights, list)
            assert len(insights) == 0

    @pytest.mark.asyncio
    async def test_pattern_matching_returns_empty_when_graphiti_unavailable(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should return empty list when Graphiti client is None."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Mock GraphitiClient.is_initialized and get_instance
        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=None)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Let's discuss the Johnson deal",
                conversation_messages=[],
            )

            assert isinstance(insights, list)
            assert len(insights) == 0

    @pytest.mark.asyncio
    async def test_pattern_matching_returns_insights_from_graphiti(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should return insights from Graphiti search results."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType

        service = ProactiveMemoryService(db_client=mock_db)

        # Create mock search result
        mock_result = MagicMock()
        mock_result.fact = "Previously discussed budget proposal with VP of Finance"
        mock_result.score = 0.85
        mock_result.uuid = "edge-123"

        # Mock GraphitiClient
        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(return_value=[mock_result])

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Let's talk about the budget proposal",
                conversation_messages=[],
            )

            assert len(insights) == 1
            assert insights[0].insight_type == InsightType.PATTERN_MATCH
            assert "budget proposal" in insights[0].content
            assert insights[0].relevance_score == 0.85
            assert insights[0].source_memory_id == "edge-123"
            assert insights[0].source_memory_type == "episodic"

    @pytest.mark.asyncio
    async def test_pattern_matching_filters_low_relevance_results(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should filter out results with score below 0.5."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Create mock search results with varying scores
        high_score_result = MagicMock()
        high_score_result.fact = "Relevant discussion about budget"
        high_score_result.score = 0.8
        high_score_result.uuid = "edge-1"

        low_score_result = MagicMock()
        low_score_result.fact = "Barely related topic"
        low_score_result.score = 0.3
        low_score_result.uuid = "edge-2"

        # Mock GraphitiClient
        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(
            return_value=[high_score_result, low_score_result]
        )

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Budget discussion",
                conversation_messages=[],
            )

            # Should only include the high-score result
            assert len(insights) == 1
            assert insights[0].source_memory_id == "edge-1"

    @pytest.mark.asyncio
    async def test_pattern_matching_handles_graphiti_exception(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should return empty list when Graphiti raises exception."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Mock GraphitiClient to raise exception
        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(side_effect=Exception("Connection failed"))

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Test message",
                conversation_messages=[],
            )

            assert isinstance(insights, list)
            assert len(insights) == 0

    @pytest.mark.asyncio
    async def test_pattern_matching_handles_import_error(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should return empty list when GraphitiClient import fails."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Remove the module from sys.modules to simulate ImportError
        with patch.dict("sys.modules", {"src.db.graphiti": None}):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Test message",
                conversation_messages=[],
            )

            assert isinstance(insights, list)
            assert len(insights) == 0

    @pytest.mark.asyncio
    async def test_pattern_matching_truncates_long_content(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should truncate content longer than 500 characters."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Create mock result with very long content
        long_content = "A" * 1000
        mock_result = MagicMock()
        mock_result.fact = long_content
        mock_result.score = 0.9
        mock_result.uuid = "edge-long"

        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(return_value=[mock_result])

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Test",
                conversation_messages=[],
            )

            assert len(insights) == 1
            assert len(insights[0].content) == 500

    @pytest.mark.asyncio
    async def test_pattern_matching_caps_relevance_score_at_one(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should cap relevance score at 1.0."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Create mock result with score > 1
        mock_result = MagicMock()
        mock_result.fact = "Test content"
        mock_result.score = 1.5  # Invalid score above 1
        mock_result.uuid = "edge-high"

        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(return_value=[mock_result])

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Test",
                conversation_messages=[],
            )

            assert len(insights) == 1
            assert insights[0].relevance_score == 1.0

    @pytest.mark.asyncio
    async def test_pattern_matching_uses_fallback_for_missing_attributes(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should handle results with missing attributes."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        # Create mock result without fact or score attributes
        mock_result = MagicMock(spec=[])  # Empty spec
        # Override __str__ to return meaningful content
        type(mock_result).__str__ = lambda self: "String representation of result"
        # Set score high enough to pass filter (default is 0.7 if no score attribute)

        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(return_value=[mock_result])

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            insights = await service._find_pattern_matches(
                user_id="user-123",
                current_message="Test",
                conversation_messages=[],
            )

            # Should create insight using str() fallback and default score
            assert isinstance(insights, list)
            # With no score attribute, hasattr returns False, so no filtering happens
            # Default relevance is 0.7, which is above threshold
            assert len(insights) == 1
            assert "String representation" in insights[0].content

    @pytest.mark.asyncio
    async def test_pattern_matching_calls_graphiti_search_with_correct_params(
        self, mock_db: MagicMock
    ) -> None:
        """Pattern matching should call Graphiti search with correct parameters."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        mock_graphiti_instance = MagicMock()
        mock_graphiti_instance.search = AsyncMock(return_value=[])

        mock_graphiti_class = MagicMock()
        mock_graphiti_class.is_initialized.return_value = True
        mock_graphiti_class.get_instance = AsyncMock(return_value=mock_graphiti_instance)

        with patch.dict(
            "sys.modules",
            {"src.db.graphiti": MagicMock(GraphitiClient=mock_graphiti_class)},
        ):
            await service._find_pattern_matches(
                user_id="user-123",
                current_message="Budget proposal discussion",
                conversation_messages=[],
            )

            # Verify search was called with correct parameters
            mock_graphiti_instance.search.assert_called_once_with(
                query="Budget proposal discussion",
                num_results=5,
                group_ids=["user-123"],
            )
