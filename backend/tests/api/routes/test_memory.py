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


from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


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


from fastapi.testclient import TestClient


class TestQueryMemoryEndpoint:
    """Tests for GET /api/v1/memory/query endpoint."""

    def test_query_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/api/v1/memory/query", params={"q": "test"})

        assert response.status_code == 401

    def test_query_requires_query_param(self) -> None:
        """Test that q parameter is required."""
        from src.main import app

        client = TestClient(app)

        # Even with mock auth, missing q should fail validation
        response = client.get(
            "/api/v1/memory/query",
            headers={"Authorization": "Bearer test-token"},
        )
        # Should fail validation - missing required q param
        assert response.status_code in [401, 422]  # 401 if auth fails first, 422 if validation


class TestQueryMemoryIntegration:
    """Integration tests for memory query endpoint."""

    @pytest.fixture
    def mock_auth(self) -> Any:
        """Fixture to mock authentication."""
        with patch("src.api.deps.get_current_user", new_callable=AsyncMock) as mock:
            user = MagicMock()
            user.id = "test-user-123"
            mock.return_value = user
            yield mock

    @pytest.fixture
    def mock_graphiti(self) -> Any:
        """Fixture to mock Graphiti client."""
        with patch("src.db.graphiti.GraphitiClient.get_instance", new_callable=AsyncMock) as mock:
            client = MagicMock()
            client.search = AsyncMock(return_value=[])
            mock.return_value = client
            yield mock

    @pytest.fixture
    def mock_supabase(self) -> Any:
        """Fixture to mock Supabase client."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock:
            client = MagicMock()
            # Mock table queries to return empty results
            table_mock = MagicMock()
            table_mock.select.return_value = table_mock
            table_mock.eq.return_value = table_mock
            table_mock.or_.return_value = table_mock
            table_mock.order.return_value = table_mock
            table_mock.limit.return_value = table_mock
            table_mock.execute.return_value = MagicMock(data=[])
            client.table.return_value = table_mock
            mock.return_value = client
            yield mock

    def test_query_returns_paginated_response(
        self, mock_auth: Any, mock_graphiti: Any, mock_supabase: Any
    ) -> None:
        """Test that query returns properly paginated response."""
        from src.main import app

        client = TestClient(app)

        response = client.get(
            "/api/v1/memory/query",
            params={"q": "test query", "page": 1, "page_size": 10},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_more" in data
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_query_filters_by_memory_type(
        self, mock_auth: Any, mock_graphiti: Any, mock_supabase: Any
    ) -> None:
        """Test that query respects memory type filter."""
        from src.main import app

        client = TestClient(app)

        response = client.get(
            "/api/v1/memory/query",
            params={"q": "test", "types": ["procedural"]},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200

    def test_query_with_date_range(
        self, mock_auth: Any, mock_graphiti: Any, mock_supabase: Any
    ) -> None:
        """Test that query accepts date range parameters."""
        from src.main import app

        client = TestClient(app)

        response = client.get(
            "/api/v1/memory/query",
            params={
                "q": "meeting",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200

    def test_query_invalid_page_size(
        self, mock_auth: Any, mock_graphiti: Any, mock_supabase: Any
    ) -> None:
        """Test that invalid page_size returns validation error."""
        from src.main import app

        client = TestClient(app)

        response = client.get(
            "/api/v1/memory/query",
            params={"q": "test", "page_size": 500},  # Max is 100
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422


class TestCreateEpisodeRequestModel:
    """Tests for CreateEpisodeRequest Pydantic model."""

    def test_create_episode_request_valid(self) -> None:
        """Test creating a valid episode request."""
        from src.api.routes.memory import CreateEpisodeRequest

        request = CreateEpisodeRequest(
            event_type="meeting",
            content="Discussed Q3 budget with finance team",
            participants=["John Smith", "Jane Doe"],
            occurred_at=datetime(2024, 6, 15, 14, 0, 0, tzinfo=UTC),
            context={"location": "Conference Room A"},
        )

        assert request.event_type == "meeting"
        assert request.content == "Discussed Q3 budget with finance team"
        assert len(request.participants) == 2
        assert request.context["location"] == "Conference Room A"

    def test_create_episode_request_minimal(self) -> None:
        """Test creating episode with only required fields."""
        from src.api.routes.memory import CreateEpisodeRequest

        request = CreateEpisodeRequest(
            event_type="note",
            content="Quick note about project status",
        )

        assert request.event_type == "note"
        assert request.content == "Quick note about project status"
        assert request.participants == []
        assert request.occurred_at is None
        assert request.context == {}

    def test_create_episode_request_empty_content_fails(self) -> None:
        """Test that empty content raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateEpisodeRequest

        with pytest.raises(ValidationError):
            CreateEpisodeRequest(
                event_type="meeting",
                content="",
            )

    def test_create_episode_request_empty_event_type_fails(self) -> None:
        """Test that empty event_type raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateEpisodeRequest

        with pytest.raises(ValidationError):
            CreateEpisodeRequest(
                event_type="",
                content="Some content",
            )


class TestCreateEpisodeResponseModel:
    """Tests for CreateEpisodeResponse Pydantic model."""

    def test_create_episode_response_valid(self) -> None:
        """Test creating a valid episode response."""
        from src.api.routes.memory import CreateEpisodeResponse

        response = CreateEpisodeResponse(
            id="episode-123",
        )

        assert response.id == "episode-123"
        assert response.message == "Episode created successfully"

    def test_create_episode_response_custom_message(self) -> None:
        """Test creating episode response with custom message."""
        from src.api.routes.memory import CreateEpisodeResponse

        response = CreateEpisodeResponse(
            id="episode-456",
            message="Custom success message",
        )

        assert response.id == "episode-456"
        assert response.message == "Custom success message"


class TestStoreEpisodeEndpoint:
    """Tests for POST /api/v1/memory/episode endpoint."""

    def test_store_episode_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                "content": "Test meeting content",
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_user(self) -> Any:
        """Create a mock user object."""
        user = MagicMock()
        user.id = "test-user-123"
        return user

    @pytest.fixture
    def app_with_mocked_auth(self, mock_user: Any) -> Any:
        """Fixture to create app with mocked authentication."""
        from src.api.deps import get_current_user
        from src.main import app

        async def mock_get_current_user() -> Any:
            return mock_user

        app.dependency_overrides[get_current_user] = mock_get_current_user
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def mock_episodic_memory(self) -> Any:
        """Fixture to mock EpisodicMemory."""
        with patch("src.api.routes.memory.EpisodicMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.store_episode = AsyncMock(return_value="episode-id-123")
            mock_class.return_value = mock_instance
            yield mock_instance

    def test_store_episode_success(
        self, app_with_mocked_auth: Any, mock_episodic_memory: Any
    ) -> None:
        """Test successful episode creation."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                "content": "Discussed Q3 budget with finance team",
                "participants": ["John Smith"],
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Episode created successfully"

    def test_store_episode_with_all_fields(
        self, app_with_mocked_auth: Any, mock_episodic_memory: Any
    ) -> None:
        """Test episode creation with all optional fields."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "call",
                "content": "Sales call with prospect",
                "participants": ["Alice", "Bob"],
                "occurred_at": "2024-06-15T14:00:00Z",
                "context": {"duration_minutes": 30, "call_type": "video"},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    def test_store_episode_validation_error_empty_content(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that empty content returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                "content": "",  # Empty string should fail
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_episode_validation_error_empty_event_type(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that empty event_type returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "",  # Empty string should fail
                "content": "Some content",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_episode_missing_required_fields(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that missing required fields returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                # Missing content
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_episode_storage_failure_returns_503(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that storage failure returns 503 Service Unavailable."""
        from src.core.exceptions import EpisodicMemoryError

        with patch("src.api.routes.memory.EpisodicMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.store_episode = AsyncMock(
                side_effect=EpisodicMemoryError("Graphiti connection failed")
            )
            mock_class.return_value = mock_instance

            client = TestClient(app_with_mocked_auth)

            response = client.post(
                "/api/v1/memory/episode",
                json={
                    "event_type": "meeting",
                    "content": "Test meeting content",
                },
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["detail"] == "Memory storage unavailable"


class TestCreateFactRequestModel:
    """Tests for CreateFactRequest Pydantic model."""

    def test_create_fact_request_valid(self) -> None:
        """Test creating a valid fact request."""
        from src.api.routes.memory import CreateFactRequest

        request = CreateFactRequest(
            subject="Acme Corp",
            predicate="has_budget_cycle",
            object="Q3",
            source="user_stated",
            confidence=0.95,
        )

        assert request.subject == "Acme Corp"
        assert request.predicate == "has_budget_cycle"
        assert request.object == "Q3"
        assert request.source == "user_stated"
        assert request.confidence == 0.95

    def test_create_fact_request_minimal(self) -> None:
        """Test creating fact with only required fields."""
        from src.api.routes.memory import CreateFactRequest

        request = CreateFactRequest(
            subject="John",
            predicate="works_at",
            object="TechCorp",
        )

        assert request.subject == "John"
        assert request.source is None
        assert request.confidence is None

    def test_create_fact_request_invalid_source(self) -> None:
        """Test that invalid source raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="John",
                predicate="works_at",
                object="TechCorp",
                source="invalid_source",
            )

    def test_create_fact_request_confidence_bounds(self) -> None:
        """Test that confidence must be between 0 and 1."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="John",
                predicate="works_at",
                object="TechCorp",
                confidence=1.5,
            )

    def test_create_fact_request_confidence_negative(self) -> None:
        """Test that negative confidence raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="John",
                predicate="works_at",
                object="TechCorp",
                confidence=-0.1,
            )

    def test_create_fact_request_empty_subject_fails(self) -> None:
        """Test that empty subject raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="",
                predicate="works_at",
                object="TechCorp",
            )

    def test_create_fact_request_with_validity_dates(self) -> None:
        """Test creating fact with validity date range."""
        from src.api.routes.memory import CreateFactRequest

        request = CreateFactRequest(
            subject="Acme Corp",
            predicate="has_ceo",
            object="John Smith",
            valid_from=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            valid_to=datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC),
        )

        assert request.valid_from is not None
        assert request.valid_to is not None
        assert request.valid_from.year == 2024


class TestCreateFactResponseModel:
    """Tests for CreateFactResponse Pydantic model."""

    def test_create_fact_response_valid(self) -> None:
        """Test creating a valid fact response."""
        from src.api.routes.memory import CreateFactResponse

        response = CreateFactResponse(
            id="fact-123",
        )

        assert response.id == "fact-123"
        assert response.message == "Fact created successfully"

    def test_create_fact_response_custom_message(self) -> None:
        """Test creating fact response with custom message."""
        from src.api.routes.memory import CreateFactResponse

        response = CreateFactResponse(
            id="fact-456",
            message="Custom success message",
        )

        assert response.id == "fact-456"
        assert response.message == "Custom success message"


class TestStoreFactEndpoint:
    """Tests for POST /api/v1/memory/fact endpoint."""

    def test_store_fact_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "Acme Corp",
                "predicate": "has_budget_cycle",
                "object": "Q3",
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_user(self) -> Any:
        """Create a mock user object."""
        user = MagicMock()
        user.id = "test-user-123"
        return user

    @pytest.fixture
    def app_with_mocked_auth(self, mock_user: Any) -> Any:
        """Fixture to create app with mocked authentication."""
        from src.api.deps import get_current_user
        from src.main import app

        async def mock_get_current_user() -> Any:
            return mock_user

        app.dependency_overrides[get_current_user] = mock_get_current_user
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def mock_semantic_memory(self) -> Any:
        """Fixture to mock SemanticMemory."""
        with patch("src.api.routes.memory.SemanticMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.add_fact = AsyncMock(return_value="fact-id-123")
            mock_class.return_value = mock_instance
            yield mock_instance

    def test_store_fact_success(
        self, app_with_mocked_auth: Any, mock_semantic_memory: Any
    ) -> None:
        """Test successful fact creation."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "Acme Corp",
                "predicate": "has_budget_cycle",
                "object": "Q3",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Fact created successfully"

    def test_store_fact_with_all_fields(
        self, app_with_mocked_auth: Any, mock_semantic_memory: Any
    ) -> None:
        """Test fact creation with all optional fields."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "John Smith",
                "predicate": "works_at",
                "object": "Acme Corp",
                "source": "crm_import",
                "confidence": 0.9,
                "valid_from": "2024-01-01T00:00:00Z",
                "valid_to": "2024-12-31T23:59:59Z",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    def test_store_fact_validation_error_empty_subject(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that empty subject returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "",
                "predicate": "works_at",
                "object": "TechCorp",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_fact_validation_error_invalid_source(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that invalid source returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "John",
                "predicate": "works_at",
                "object": "TechCorp",
                "source": "invalid_source",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_fact_validation_error_confidence_out_of_bounds(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that confidence > 1.0 returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "John",
                "predicate": "works_at",
                "object": "TechCorp",
                "confidence": 1.5,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_fact_missing_required_fields(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that missing required fields returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "John",
                "predicate": "works_at",
                # Missing object
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_fact_storage_failure_returns_503(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that storage failure returns 503 Service Unavailable."""
        from src.core.exceptions import SemanticMemoryError

        with patch("src.api.routes.memory.SemanticMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.add_fact = AsyncMock(
                side_effect=SemanticMemoryError("Graphiti connection failed")
            )
            mock_class.return_value = mock_instance

            client = TestClient(app_with_mocked_auth)

            response = client.post(
                "/api/v1/memory/fact",
                json={
                    "subject": "Acme Corp",
                    "predicate": "has_budget_cycle",
                    "object": "Q3",
                },
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["detail"] == "Memory storage unavailable"

    def test_store_fact_uses_default_confidence_from_source(
        self, app_with_mocked_auth: Any, mock_semantic_memory: Any
    ) -> None:
        """Test that default confidence is set based on source when not provided."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "Acme Corp",
                "predicate": "has_budget_cycle",
                "object": "Q3",
                "source": "extracted",
                # No confidence provided - should use SOURCE_CONFIDENCE[EXTRACTED] = 0.75
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        # Verify add_fact was called with the correct confidence
        mock_semantic_memory.add_fact.assert_called_once()
        call_args = mock_semantic_memory.add_fact.call_args
        fact = call_args[0][0]
        assert fact.confidence == 0.75  # SOURCE_CONFIDENCE[EXTRACTED]


class TestCreateTaskRequestModel:
    """Tests for CreateTaskRequest Pydantic model."""

    def test_create_task_request_valid(self) -> None:
        """Test creating a valid task request."""
        from src.api.routes.memory import CreateTaskRequest

        request = CreateTaskRequest(
            task="Follow up with client",
            description="Send proposal review request",
            trigger_type="time",
            trigger_config={"due_at": "2024-07-01T10:00:00Z"},
            priority="high",
        )

        assert request.task == "Follow up with client"
        assert request.description == "Send proposal review request"
        assert request.trigger_type == "time"
        assert request.priority == "high"

    def test_create_task_request_minimal(self) -> None:
        """Test creating task with only required fields."""
        from src.api.routes.memory import CreateTaskRequest

        request = CreateTaskRequest(
            task="Call John",
            trigger_type="time",
            trigger_config={"due_at": "2024-07-01T10:00:00Z"},
        )

        assert request.task == "Call John"
        assert request.description is None
        assert request.priority == "medium"  # default

    def test_create_task_request_invalid_trigger_type(self) -> None:
        """Test that invalid trigger_type raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateTaskRequest

        with pytest.raises(ValidationError):
            CreateTaskRequest(
                task="Call John",
                trigger_type="invalid",
                trigger_config={},
            )

    def test_create_task_request_invalid_priority(self) -> None:
        """Test that invalid priority raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateTaskRequest

        with pytest.raises(ValidationError):
            CreateTaskRequest(
                task="Call John",
                trigger_type="time",
                trigger_config={"due_at": "2024-07-01T10:00:00Z"},
                priority="invalid",
            )

    def test_create_task_request_empty_task_fails(self) -> None:
        """Test that empty task raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateTaskRequest

        with pytest.raises(ValidationError):
            CreateTaskRequest(
                task="",
                trigger_type="time",
                trigger_config={"due_at": "2024-07-01T10:00:00Z"},
            )

    def test_create_task_request_with_related_ids(self) -> None:
        """Test creating task with related goal and lead IDs."""
        from src.api.routes.memory import CreateTaskRequest

        request = CreateTaskRequest(
            task="Review proposal",
            trigger_type="event",
            trigger_config={"event_name": "contract_signed"},
            related_goal_id="goal-123",
            related_lead_id="lead-456",
        )

        assert request.related_goal_id == "goal-123"
        assert request.related_lead_id == "lead-456"


class TestCreateTaskResponseModel:
    """Tests for CreateTaskResponse Pydantic model."""

    def test_create_task_response_valid(self) -> None:
        """Test creating a valid task response."""
        from src.api.routes.memory import CreateTaskResponse

        response = CreateTaskResponse(
            id="task-123",
        )

        assert response.id == "task-123"
        assert response.message == "Task created successfully"

    def test_create_task_response_custom_message(self) -> None:
        """Test creating task response with custom message."""
        from src.api.routes.memory import CreateTaskResponse

        response = CreateTaskResponse(
            id="task-456",
            message="Custom success message",
        )

        assert response.id == "task-456"
        assert response.message == "Custom success message"


class TestStoreTaskEndpoint:
    """Tests for POST /api/v1/memory/task endpoint."""

    def test_store_task_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Follow up with client",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_user(self) -> Any:
        """Create a mock user object."""
        user = MagicMock()
        user.id = "test-user-123"
        return user

    @pytest.fixture
    def app_with_mocked_auth(self, mock_user: Any) -> Any:
        """Fixture to create app with mocked authentication."""
        from src.api.deps import get_current_user
        from src.main import app

        async def mock_get_current_user() -> Any:
            return mock_user

        app.dependency_overrides[get_current_user] = mock_get_current_user
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    def mock_prospective_memory(self) -> Any:
        """Fixture to mock ProspectiveMemory."""
        with patch("src.api.routes.memory.ProspectiveMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.create_task = AsyncMock(return_value="task-id-123")
            mock_class.return_value = mock_instance
            yield mock_instance

    def test_store_task_success(
        self, app_with_mocked_auth: Any, mock_prospective_memory: Any
    ) -> None:
        """Test successful task creation."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Follow up with client",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Task created successfully"

    def test_store_task_with_all_fields(
        self, app_with_mocked_auth: Any, mock_prospective_memory: Any
    ) -> None:
        """Test task creation with all optional fields."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Review contract",
                "description": "Review and provide feedback on partnership contract",
                "trigger_type": "event",
                "trigger_config": {"event_name": "document_received"},
                "priority": "urgent",
                "related_goal_id": "goal-123",
                "related_lead_id": "lead-456",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    def test_store_task_with_related_ids(
        self, app_with_mocked_auth: Any, mock_prospective_memory: Any
    ) -> None:
        """Test task creation with related goal_id and lead_id."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Schedule demo",
                "trigger_type": "condition",
                "trigger_config": {"condition": "lead_qualified"},
                "related_goal_id": "goal-abc",
                "related_lead_id": "lead-xyz",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        # Verify create_task was called with related IDs
        mock_prospective_memory.create_task.assert_called_once()
        call_args = mock_prospective_memory.create_task.call_args
        task = call_args[0][0]
        assert task.related_goal_id == "goal-abc"
        assert task.related_lead_id == "lead-xyz"

    def test_store_task_validation_error_empty_task(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that empty task returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_task_validation_error_invalid_trigger_type(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that invalid trigger_type returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Call John",
                "trigger_type": "invalid",
                "trigger_config": {},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_task_validation_error_invalid_priority(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that invalid priority returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Call John",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
                "priority": "invalid",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_task_missing_required_fields(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that missing required fields returns 422."""
        client = TestClient(app_with_mocked_auth)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Call John",
                # Missing trigger_type and trigger_config
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422

    def test_store_task_storage_failure_returns_503(
        self, app_with_mocked_auth: Any
    ) -> None:
        """Test that storage failure returns 503 Service Unavailable."""
        from src.core.exceptions import ProspectiveMemoryError

        with patch("src.api.routes.memory.ProspectiveMemory") as mock_class:
            mock_instance = MagicMock()
            mock_instance.create_task = AsyncMock(
                side_effect=ProspectiveMemoryError("Supabase connection failed")
            )
            mock_class.return_value = mock_instance

            client = TestClient(app_with_mocked_auth)

            response = client.post(
                "/api/v1/memory/task",
                json={
                    "task": "Follow up with client",
                    "trigger_type": "time",
                    "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
                },
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 503
            data = response.json()
            assert data["detail"] == "Memory storage unavailable"
