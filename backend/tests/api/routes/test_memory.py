"""Tests for memory API routes."""

from datetime import UTC, datetime

import pytest


class TestMemoryQueryResultModel:
    """Tests for MemoryQueryResult Pydantic model."""

    def test_memory_query_result_valid_episodic(self) -> None:
        """Test creating a valid episodic memory query result."""
        from src.api.routes.memory import MemoryQueryResult

        result = MemoryQueryResult(
            id="test-id-123",
            memory_type="episodic",
            content="Meeting with John about project X",
            relevance_score=0.85,
            confidence=None,
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        )

        assert result.id == "test-id-123"
        assert result.memory_type == "episodic"
        assert result.content == "Meeting with John about project X"
        assert result.relevance_score == 0.85
        assert result.confidence is None
        assert result.timestamp.year == 2024

    def test_memory_query_result_valid_semantic(self) -> None:
        """Test creating a valid semantic memory query result with confidence."""
        from src.api.routes.memory import MemoryQueryResult

        result = MemoryQueryResult(
            id="fact-456",
            memory_type="semantic",
            content="Acme Corp has budget cycle in Q3",
            relevance_score=0.92,
            confidence=0.85,
            timestamp=datetime(2024, 2, 1, 14, 30, 0, tzinfo=UTC),
        )

        assert result.memory_type == "semantic"
        assert result.confidence == 0.85

    def test_memory_query_result_valid_procedural(self) -> None:
        """Test creating a valid procedural memory query result."""
        from src.api.routes.memory import MemoryQueryResult

        result = MemoryQueryResult(
            id="workflow-789",
            memory_type="procedural",
            content="Follow-up sequence for initial contact",
            relevance_score=0.78,
            confidence=None,
            timestamp=datetime(2024, 3, 10, 9, 15, 0, tzinfo=UTC),
        )

        assert result.memory_type == "procedural"
        assert result.id == "workflow-789"

    def test_memory_query_result_valid_prospective(self) -> None:
        """Test creating a valid prospective memory query result."""
        from src.api.routes.memory import MemoryQueryResult

        result = MemoryQueryResult(
            id="task-101",
            memory_type="prospective",
            content="Follow up with client next week",
            relevance_score=0.95,
            confidence=None,
            timestamp=datetime(2024, 4, 5, 16, 0, 0, tzinfo=UTC),
        )

        assert result.memory_type == "prospective"
        assert result.relevance_score == 0.95

    def test_memory_query_result_invalid_memory_type(self) -> None:
        """Test that invalid memory type raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import MemoryQueryResult

        with pytest.raises(ValidationError):
            MemoryQueryResult(
                id="test-id",
                memory_type="invalid_type",
                content="Some content",
                relevance_score=0.5,
                confidence=None,
                timestamp=datetime.now(UTC),
            )

    def test_memory_query_result_relevance_score_bounds(self) -> None:
        """Test that relevance_score must be between 0 and 1."""
        from pydantic import ValidationError

        from src.api.routes.memory import MemoryQueryResult

        # Test score too high
        with pytest.raises(ValidationError):
            MemoryQueryResult(
                id="test-id",
                memory_type="episodic",
                content="Some content",
                relevance_score=1.5,
                confidence=None,
                timestamp=datetime.now(UTC),
            )

        # Test score too low
        with pytest.raises(ValidationError):
            MemoryQueryResult(
                id="test-id",
                memory_type="episodic",
                content="Some content",
                relevance_score=-0.1,
                confidence=None,
                timestamp=datetime.now(UTC),
            )

    def test_memory_query_result_confidence_bounds(self) -> None:
        """Test that confidence must be between 0 and 1 when provided."""
        from pydantic import ValidationError

        from src.api.routes.memory import MemoryQueryResult

        # Test confidence too high
        with pytest.raises(ValidationError):
            MemoryQueryResult(
                id="test-id",
                memory_type="semantic",
                content="Some content",
                relevance_score=0.5,
                confidence=1.2,
                timestamp=datetime.now(UTC),
            )

        # Test confidence too low
        with pytest.raises(ValidationError):
            MemoryQueryResult(
                id="test-id",
                memory_type="semantic",
                content="Some content",
                relevance_score=0.5,
                confidence=-0.1,
                timestamp=datetime.now(UTC),
            )


class TestMemoryQueryResponseModel:
    """Tests for MemoryQueryResponse Pydantic model."""

    def test_memory_query_response_empty(self) -> None:
        """Test creating an empty response."""
        from src.api.routes.memory import MemoryQueryResponse

        response = MemoryQueryResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
            has_more=False,
        )

        assert response.items == []
        assert response.total == 0
        assert response.page == 1
        assert response.page_size == 20
        assert response.has_more is False

    def test_memory_query_response_with_items(self) -> None:
        """Test creating a response with multiple items."""
        from src.api.routes.memory import MemoryQueryResponse, MemoryQueryResult

        items = [
            MemoryQueryResult(
                id="id-1",
                memory_type="episodic",
                content="First memory",
                relevance_score=0.9,
                confidence=None,
                timestamp=datetime.now(UTC),
            ),
            MemoryQueryResult(
                id="id-2",
                memory_type="semantic",
                content="Second memory",
                relevance_score=0.8,
                confidence=0.75,
                timestamp=datetime.now(UTC),
            ),
        ]

        response = MemoryQueryResponse(
            items=items,
            total=50,
            page=1,
            page_size=20,
            has_more=True,
        )

        assert len(response.items) == 2
        assert response.total == 50
        assert response.has_more is True

    def test_memory_query_response_pagination(self) -> None:
        """Test pagination fields in response."""
        from src.api.routes.memory import MemoryQueryResponse

        response = MemoryQueryResponse(
            items=[],
            total=100,
            page=3,
            page_size=25,
            has_more=True,
        )

        assert response.page == 3
        assert response.page_size == 25
        assert response.has_more is True


from unittest.mock import AsyncMock, patch


class TestMemoryQueryService:
    """Tests for MemoryQueryService."""

    @pytest.mark.asyncio
    async def test_query_episodic_only(self) -> None:
        """Test querying only episodic memory."""
        from datetime import UTC, datetime

        from src.api.routes.memory import MemoryQueryService

        service = MemoryQueryService()

        with patch.object(service, "_query_episodic", new_callable=AsyncMock) as mock_episodic:
            mock_episodic.return_value = [
                {
                    "id": "ep-1",
                    "memory_type": "episodic",
                    "content": "Meeting about budget",
                    "relevance_score": 0.8,
                    "confidence": None,
                    "timestamp": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                }
            ]

            results = await service.query(
                user_id="user-123",
                query="budget meeting",
                memory_types=["episodic"],
                start_date=None,
                end_date=None,
                limit=20,
                offset=0,
            )

            assert len(results) == 1
            assert results[0]["memory_type"] == "episodic"
            mock_episodic.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_multiple_types_sorted_by_relevance(self) -> None:
        """Test querying multiple memory types returns sorted results."""
        from datetime import UTC, datetime

        from src.api.routes.memory import MemoryQueryService

        service = MemoryQueryService()

        with (
            patch.object(service, "_query_episodic", new_callable=AsyncMock) as mock_ep,
            patch.object(service, "_query_semantic", new_callable=AsyncMock) as mock_sem,
        ):
            mock_ep.return_value = [
                {
                    "id": "ep-1",
                    "memory_type": "episodic",
                    "content": "Low relevance episode",
                    "relevance_score": 0.5,
                    "confidence": None,
                    "timestamp": datetime.now(UTC),
                }
            ]
            mock_sem.return_value = [
                {
                    "id": "fact-1",
                    "memory_type": "semantic",
                    "content": "High relevance fact",
                    "relevance_score": 0.9,
                    "confidence": 0.85,
                    "timestamp": datetime.now(UTC),
                }
            ]

            results = await service.query(
                user_id="user-123",
                query="test query",
                memory_types=["episodic", "semantic"],
                start_date=None,
                end_date=None,
                limit=20,
                offset=0,
            )

            assert len(results) == 2
            # Should be sorted by relevance descending
            assert results[0]["relevance_score"] == 0.9
            assert results[1]["relevance_score"] == 0.5
