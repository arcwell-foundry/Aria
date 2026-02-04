"""Tests for proactive insights API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestGetProactiveInsights:
    """Tests for GET /api/v1/insights/proactive endpoint."""

    @pytest.fixture
    def mock_current_user(self) -> MagicMock:
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "user-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user: MagicMock) -> TestClient:
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_proactive_insights(self, client_with_mocks: TestClient) -> None:
        """Should return list of proactive insights."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.find_volunteerable_context = AsyncMock(return_value=[])
            mock_instance.record_surfaced = AsyncMock(return_value="record-123")
            MockService.return_value = mock_instance

            response = client_with_mocks.get(
                "/api/v1/insights/proactive",
                params={"context": "Discussing budget with Dr. Smith"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "insights" in data

    def test_returns_insights_with_data(self, client_with_mocks: TestClient) -> None:
        """Should return insights when service returns data."""
        from src.models.proactive_insight import InsightType, ProactiveInsight

        mock_insight = ProactiveInsight(
            insight_type=InsightType.TEMPORAL,
            content="Follow up with Dr. Smith",
            relevance_score=0.85,
            source_memory_id="memory-456",
            source_memory_type="prospective",
            explanation="Due in 2 days",
        )

        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.find_volunteerable_context = AsyncMock(
                return_value=[mock_insight]
            )
            mock_instance.record_surfaced = AsyncMock(return_value="record-123")
            MockService.return_value = mock_instance

            response = client_with_mocks.get(
                "/api/v1/insights/proactive",
                params={"context": "Discussing budget"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "insights" in data
            assert len(data["insights"]) == 1
            assert data["insights"][0]["content"] == "Follow up with Dr. Smith"
            assert data["insights"][0]["relevance_score"] == 0.85


class TestEngageInsight:
    """Tests for POST /api/v1/insights/{id}/engage endpoint."""

    @pytest.fixture
    def mock_current_user(self) -> MagicMock:
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "user-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user: MagicMock) -> TestClient:
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_marks_insight_as_engaged(self, client_with_mocks: TestClient) -> None:
        """Should mark insight as engaged."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.record_engagement = AsyncMock()
            MockService.return_value = mock_instance

            response = client_with_mocks.post("/api/v1/insights/insight-123/engage")

            assert response.status_code == 204
            mock_instance.record_engagement.assert_called_once_with(
                insight_id="insight-123",
                engaged=True,
            )


class TestDismissInsight:
    """Tests for POST /api/v1/insights/{id}/dismiss endpoint."""

    @pytest.fixture
    def mock_current_user(self) -> MagicMock:
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "user-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user: MagicMock) -> TestClient:
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_marks_insight_as_dismissed(self, client_with_mocks: TestClient) -> None:
        """Should mark insight as dismissed."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.record_engagement = AsyncMock()
            MockService.return_value = mock_instance

            response = client_with_mocks.post("/api/v1/insights/insight-123/dismiss")

            assert response.status_code == 204
            mock_instance.record_engagement.assert_called_once_with(
                insight_id="insight-123",
                engaged=False,
            )


class TestGetInsightsHistory:
    """Tests for GET /api/v1/insights/history endpoint."""

    @pytest.fixture
    def mock_current_user(self) -> MagicMock:
        """Mock authenticated user."""
        user = MagicMock()
        user.id = "user-123"
        return user

    @pytest.fixture
    def client_with_mocks(self, mock_current_user: MagicMock) -> TestClient:
        """Create test client with mocked dependencies."""
        from src.api.deps import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_history(self, client_with_mocks: TestClient) -> None:
        """Should return surfaced insights history."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.get_surfaced_history = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            response = client_with_mocks.get("/api/v1/insights/history")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data

    def test_returns_history_with_data(self, client_with_mocks: TestClient) -> None:
        """Should return history items when data exists."""
        mock_history = [
            {
                "id": "surfaced-1",
                "user_id": "user-123",
                "memory_type": "prospective",
                "memory_id": "memory-456",
                "insight_type": "temporal",
                "context": "discussing budget",
                "relevance_score": 0.85,
                "explanation": "Due in 2 days",
                "surfaced_at": "2024-01-15T10:00:00+00:00",
                "engaged": True,
                "engaged_at": "2024-01-15T10:05:00+00:00",
                "dismissed": False,
                "dismissed_at": None,
            }
        ]

        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.get_surfaced_history = AsyncMock(return_value=mock_history)
            MockService.return_value = mock_instance

            response = client_with_mocks.get("/api/v1/insights/history")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == "surfaced-1"
            assert data["items"][0]["engaged"] is True

    def test_respects_limit_parameter(self, client_with_mocks: TestClient) -> None:
        """Should pass limit parameter to service."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.get_surfaced_history = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            response = client_with_mocks.get(
                "/api/v1/insights/history",
                params={"limit": 50},
            )

            assert response.status_code == 200
            mock_instance.get_surfaced_history.assert_called_once_with(
                user_id="user-123",
                limit=50,
                engaged_only=False,
            )

    def test_respects_engaged_only_parameter(
        self, client_with_mocks: TestClient
    ) -> None:
        """Should pass engaged_only parameter to service."""
        with (
            patch("src.api.routes.insights.get_supabase_client"),
            patch("src.api.routes.insights.ProactiveMemoryService") as MockService,
        ):
            mock_instance = MagicMock()
            mock_instance.get_surfaced_history = AsyncMock(return_value=[])
            MockService.return_value = mock_instance

            response = client_with_mocks.get(
                "/api/v1/insights/history",
                params={"engaged_only": True},
            )

            assert response.status_code == 200
            mock_instance.get_surfaced_history.assert_called_once_with(
                user_id="user-123",
                limit=20,
                engaged_only=True,
            )
