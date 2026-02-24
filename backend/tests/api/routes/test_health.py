"""Tests for health check API routes.

Tests cover:
- GET /api/v1/health — overall health with service statuses (no auth required)
- GET /api/v1/health/detailed — detailed health (admin only)
- Non-admin users get 403 on /detailed
- Service status reflects circuit breaker state
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes import health
from src.core.error_tracker import ErrorTracker
from src.core.monitoring import OverallStatus
from src.core.resilience import CircuitBreaker, CircuitState


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(health.router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _reset_error_tracker() -> None:
    """Reset ErrorTracker singleton between tests."""
    ErrorTracker._instance = None


@pytest.fixture
def mock_current_user() -> MagicMock:
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def mock_admin_user() -> MagicMock:
    user = MagicMock()
    user.id = "admin-user-123"
    return user


@pytest.fixture
def public_client() -> TestClient:
    """Client without auth — health endpoint should work without auth."""
    app = create_test_app()
    client = TestClient(app)
    yield client


@pytest.fixture
def admin_client(mock_admin_user: MagicMock) -> TestClient:
    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_admin_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(mock_current_user: MagicMock) -> TestClient:
    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_cached_health(
    status: str = "healthy",
    services: dict | None = None,
    circuit_breakers: dict | None = None,
) -> dict:
    """Build a dict matching _get_cached_health_check() return shape."""
    overall = OverallStatus(status)
    return {
        "status": status,
        "services": services or {},
        "uptime_seconds": 42.0,
        "version": "1.0.0",
        "circuit_breakers": circuit_breakers or {},
        "_overall": overall,
    }


# ------------------------------------------------------------------ #
# GET /api/v1/health                                                  #
# ------------------------------------------------------------------ #


class TestHealthCheck:
    """Tests for GET /api/v1/health."""

    def test_returns_healthy_status(self, public_client: TestClient) -> None:
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(),
        ):
            response = public_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "services" in data
        assert "uptime_seconds" in data
        assert "version" in data

    def test_includes_service_statuses(self, public_client: TestClient) -> None:
        services = {
            "tavus": {"status": "up", "latency_ms": 10.0},
            "exa": {"status": "up", "latency_ms": 15.0},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert "tavus" in data["services"]
        assert "exa" in data["services"]
        assert data["services"]["tavus"]["status"] == "up"
        assert data["services"]["exa"]["status"] == "up"

    def test_service_down_when_circuit_open(self, public_client: TestClient) -> None:
        services = {
            "tavus": {"status": "down", "latency_ms": 0.0},
            "exa": {"status": "up", "latency_ms": 15.0},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(status="degraded", services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["services"]["tavus"]["status"] == "down"
        assert data["services"]["exa"]["status"] == "up"

    def test_degraded_when_some_services_down(self, public_client: TestClient) -> None:
        services = {
            "tavus": {"status": "down", "latency_ms": 0.0},
            "exa": {"status": "up", "latency_ms": 15.0},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(status="degraded", services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["status"] == "degraded"

    def test_unhealthy_when_critical_service_down(self, public_client: TestClient) -> None:
        services = {
            "supabase": {"status": "down", "latency_ms": 0.0, "message": "Connection refused"},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(status="unhealthy", services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["status"] == "unhealthy"
        assert response.status_code == 503

    def test_healthy_when_all_services_up(self, public_client: TestClient) -> None:
        services = {
            "tavus": {"status": "up", "latency_ms": 10.0},
            "exa": {"status": "up", "latency_ms": 15.0},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["status"] == "healthy"

    def test_healthy_when_no_circuit_breakers(self, public_client: TestClient) -> None:
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["status"] == "healthy"

    def test_degraded_status(self, public_client: TestClient) -> None:
        services = {
            "tavus": {"status": "down", "latency_ms": 0.0},
        }
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(status="degraded", services=services),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["status"] == "degraded"

    def test_no_auth_required(self, public_client: TestClient) -> None:
        """Health check should work without authentication."""
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(),
        ):
            response = public_client.get("/api/v1/health")

        assert response.status_code == 200

    def test_uptime_is_non_negative(self, public_client: TestClient) -> None:
        with patch(
            "src.api.routes.health._get_cached_health_check",
            new_callable=AsyncMock,
            return_value=_make_cached_health(),
        ):
            response = public_client.get("/api/v1/health")

        data = response.json()
        assert data["uptime_seconds"] >= 0


# ------------------------------------------------------------------ #
# GET /api/v1/health/detailed                                         #
# ------------------------------------------------------------------ #


class TestDetailedHealthCheck:
    """Tests for GET /api/v1/health/detailed (admin only)."""

    def test_returns_circuit_breaker_states(self, admin_client: TestClient) -> None:
        tavus_cb = MagicMock(spec=CircuitBreaker)
        tavus_cb.to_dict.return_value = {
            "service": "tavus",
            "state": "closed",
            "failure_count": 0,
            "failure_threshold": 5,
            "recovery_timeout": 60.0,
            "success_threshold": 3,
        }

        with patch(
            "src.api.routes.health.get_all_circuit_breakers",
            return_value={"tavus": tavus_cb},
        ), patch(
            "src.db.supabase.SupabaseClient.get_user_by_id",
            new=AsyncMock(return_value={"role": "admin"}),
        ):
            response = admin_client.get("/api/v1/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert "circuit_breakers" in data
        assert data["circuit_breakers"]["tavus"]["state"] == "closed"

    def test_returns_error_summary(self, admin_client: TestClient) -> None:
        tracker = ErrorTracker.get_instance()
        tracker.record_error("tavus", "ConnectionError", "test")
        tracker.record_error("exa", "TimeoutError", "test")

        with patch(
            "src.api.routes.health.get_all_circuit_breakers",
            return_value={},
        ), patch(
            "src.db.supabase.SupabaseClient.get_user_by_id",
            new=AsyncMock(return_value={"role": "admin"}),
        ):
            response = admin_client.get("/api/v1/health/detailed")

        data = response.json()
        assert "errors" in data
        assert data["errors"]["total"] == 2
        assert data["errors"]["by_service"]["tavus"] == 1
        assert data["errors"]["by_service"]["exa"] == 1

    def test_returns_memory_usage(self, admin_client: TestClient) -> None:
        with patch(
            "src.api.routes.health.get_all_circuit_breakers",
            return_value={},
        ), patch(
            "src.db.supabase.SupabaseClient.get_user_by_id",
            new=AsyncMock(return_value={"role": "admin"}),
        ):
            response = admin_client.get("/api/v1/health/detailed")

        data = response.json()
        assert "memory" in data
        assert "rss_mb" in data["memory"]
        assert isinstance(data["memory"]["rss_mb"], (int, float))

    def test_non_admin_gets_403(self, user_client: TestClient) -> None:
        with patch(
            "src.db.supabase.SupabaseClient.get_user_by_id",
            new=AsyncMock(return_value={"role": "user"}),
        ):
            response = user_client.get("/api/v1/health/detailed")

        assert response.status_code == 403

    def test_unauthenticated_gets_401(self, public_client: TestClient) -> None:
        response = public_client.get("/api/v1/health/detailed")
        assert response.status_code == 401
