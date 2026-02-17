"""Tests for Analytics API routes.

These tests follow the established pattern using dependency_overrides
and TestClient for mocking authentication.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes import analytics


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(analytics.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_overview_metrics() -> dict:
    """Sample overview metrics response."""
    return {
        "leads_created": 10,
        "meetings_booked": 5,
        "emails_sent": 20,
        "debriefs_completed": 3,
        "goals_completed": 2,
        "avg_health_score": 75.5,
        "time_saved_minutes": 120,
    }


@pytest.fixture
def mock_conversion_funnel() -> dict:
    """Sample conversion funnel response."""
    return {
        "stages": {"lead": 8, "opportunity": 4, "account": 2},
        "conversion_rates": {"lead_to_opportunity": 0.5, "opportunity_to_account": 0.5},
        "avg_days_in_stage": {"lead": 5.0, "opportunity": 10.0, "account": 15.0},
    }


@pytest.fixture
def mock_activity_trends() -> dict:
    """Sample activity trends response."""
    return {
        "granularity": "day",
        "series": {
            "emails_sent": {"2026-02-01": 5, "2026-02-02": 3},
            "meetings": {"2026-02-01": 2},
            "aria_actions": {"2026-02-01": 10, "2026-02-02": 8},
            "leads_created": {"2026-02-01": 1},
        },
    }


@pytest.fixture
def mock_response_times() -> dict:
    """Sample response time metrics."""
    return {
        "avg_response_minutes": 45.0,
        "by_lead": {"lead-1": 30.0, "lead-2": 60.0},
        "trend": [
            {"date": "2026-02-01", "avg_response_minutes": 40.0},
            {"date": "2026-02-02", "avg_response_minutes": 50.0},
        ],
    }


@pytest.fixture
def mock_aria_impact() -> dict:
    """Sample ARIA impact summary."""
    return {
        "total_actions": 25,
        "by_action_type": {"email_draft": 15, "meeting_prep": 5, "research_report": 5},
        "estimated_time_saved_minutes": 300,
        "pipeline_impact": {
            "lead_discovered": {"count": 3, "estimated_value": 150000.0},
        },
    }


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


class TestOverviewEndpoint:
    """Tests for GET /api/v1/analytics/overview."""

    def test_returns_overview_metrics(
        self, test_client: TestClient, mock_overview_metrics: dict
    ) -> None:
        """Returns overview metrics for valid request."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_overview_metrics = AsyncMock(return_value=mock_overview_metrics)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/overview")

        assert response.status_code == 200
        data = response.json()
        assert data["leads_created"] == 10
        assert data["meetings_booked"] == 5
        assert data["emails_sent"] == 20
        assert data["time_saved_minutes"] == 120

    def test_accepts_period_parameter(
        self, test_client: TestClient, mock_overview_metrics: dict
    ) -> None:
        """Accepts different period parameters."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_overview_metrics = AsyncMock(return_value=mock_overview_metrics)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/overview?period=7d")

        assert response.status_code == 200

    def test_rejects_invalid_period(self, test_client: TestClient) -> None:
        """Rejects invalid period parameter."""
        response = test_client.get("/api/v1/analytics/overview?period=invalid")
        assert response.status_code == 422

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/overview")
        assert response.status_code == 401


class TestFunnelEndpoint:
    """Tests for GET /api/v1/analytics/funnel."""

    def test_returns_conversion_funnel(
        self, test_client: TestClient, mock_conversion_funnel: dict
    ) -> None:
        """Returns conversion funnel metrics."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_conversion_funnel = AsyncMock(return_value=mock_conversion_funnel)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/funnel")

        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert "conversion_rates" in data
        assert "avg_days_in_stage" in data

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/funnel")
        assert response.status_code == 401


class TestTrendsEndpoint:
    """Tests for GET /api/v1/analytics/trends."""

    def test_returns_activity_trends(
        self, test_client: TestClient, mock_activity_trends: dict
    ) -> None:
        """Returns activity trends time series."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_activity_trends = AsyncMock(return_value=mock_activity_trends)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/trends")

        assert response.status_code == 200
        data = response.json()
        assert "granularity" in data
        assert "series" in data
        assert "emails_sent" in data["series"]

    def test_accepts_granularity_parameter(
        self, test_client: TestClient, mock_activity_trends: dict
    ) -> None:
        """Accepts granularity parameter."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_activity_trends = AsyncMock(
                return_value={**mock_activity_trends, "granularity": "week"}
            )
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/trends?granularity=week")

        assert response.status_code == 200
        assert response.json()["granularity"] == "week"

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/trends")
        assert response.status_code == 401


class TestResponseTimesEndpoint:
    """Tests for GET /api/v1/analytics/response-times."""

    def test_returns_response_times(
        self, test_client: TestClient, mock_response_times: dict
    ) -> None:
        """Returns response time metrics."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_response_time_metrics = AsyncMock(return_value=mock_response_times)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/response-times")

        assert response.status_code == 200
        data = response.json()
        assert "avg_response_minutes" in data
        assert "by_lead" in data
        assert "trend" in data

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/response-times")
        assert response.status_code == 401


class TestAriaImpactEndpoint:
    """Tests for GET /api/v1/analytics/aria-impact."""

    def test_returns_aria_impact(self, test_client: TestClient, mock_aria_impact: dict) -> None:
        """Returns ARIA impact summary."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_aria_impact_summary = AsyncMock(return_value=mock_aria_impact)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/aria-impact")

        assert response.status_code == 200
        data = response.json()
        assert "total_actions" in data
        assert "by_action_type" in data
        assert "estimated_time_saved_minutes" in data
        assert "pipeline_impact" in data

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/aria-impact")
        assert response.status_code == 401


class TestCompareEndpoint:
    """Tests for GET /api/v1/analytics/compare."""

    def test_returns_period_comparison(
        self, test_client: TestClient, mock_overview_metrics: dict
    ) -> None:
        """Returns period comparison with deltas."""
        comparison_data = {
            "current": mock_overview_metrics,
            "previous": {
                "leads_created": 8,
                "meetings_booked": 4,
                "emails_sent": 15,
                "debriefs_completed": 2,
                "goals_completed": 1,
                "avg_health_score": 70.0,
                "time_saved_minutes": 90,
            },
            "delta_pct": {
                "leads_created": 25.0,
                "meetings_booked": 25.0,
                "emails_sent": 33.3,
                "debriefs_completed": 50.0,
                "goals_completed": 100.0,
                "avg_health_score": 5.5,
                "time_saved_minutes": 33.3,
            },
        }

        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.compare_periods = AsyncMock(return_value=comparison_data)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/compare?current=30d&previous=30d")

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "previous" in data
        assert "delta_pct" in data

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/compare")
        assert response.status_code == 401


class TestExportEndpoint:
    """Tests for GET /api/v1/analytics/export."""

    def test_exports_csv_by_default(
        self,
        test_client: TestClient,
        mock_overview_metrics: dict,
        mock_conversion_funnel: dict,
        mock_activity_trends: dict,
        mock_response_times: dict,
        mock_aria_impact: dict,
    ) -> None:
        """Exports analytics as CSV by default."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_overview_metrics = AsyncMock(return_value=mock_overview_metrics)
            mock_service.get_conversion_funnel = AsyncMock(return_value=mock_conversion_funnel)
            mock_service.get_activity_trends = AsyncMock(return_value=mock_activity_trends)
            mock_service.get_response_time_metrics = AsyncMock(return_value=mock_response_times)
            mock_service.get_aria_impact_summary = AsyncMock(return_value=mock_aria_impact)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/export")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

    def test_exports_json_when_requested(
        self,
        test_client: TestClient,
        mock_overview_metrics: dict,
        mock_conversion_funnel: dict,
        mock_activity_trends: dict,
        mock_response_times: dict,
        mock_aria_impact: dict,
    ) -> None:
        """Exports analytics as JSON when format=json."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_overview_metrics = AsyncMock(return_value=mock_overview_metrics)
            mock_service.get_conversion_funnel = AsyncMock(return_value=mock_conversion_funnel)
            mock_service.get_activity_trends = AsyncMock(return_value=mock_activity_trends)
            mock_service.get_response_time_metrics = AsyncMock(return_value=mock_response_times)
            mock_service.get_aria_impact_summary = AsyncMock(return_value=mock_aria_impact)
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/export?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert "overview" in data
        assert "conversion_funnel" in data

    def test_unauthenticated(self) -> None:
        """Returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/analytics/export")
        assert response.status_code == 401


class TestErrorHandling:
    """Tests for error handling across endpoints."""

    def test_overview_server_error(self, test_client: TestClient) -> None:
        """Returns 500 on service error."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_overview_metrics = AsyncMock(side_effect=Exception("Database error"))
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/overview")

        assert response.status_code == 500

    def test_funnel_server_error(self, test_client: TestClient) -> None:
        """Returns 500 on service error."""
        with patch("src.api.routes.analytics._get_analytics_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.get_conversion_funnel = AsyncMock(side_effect=Exception("Database error"))
            mock_service_factory.return_value = mock_service

            response = test_client.get("/api/v1/analytics/funnel")

        assert response.status_code == 500
