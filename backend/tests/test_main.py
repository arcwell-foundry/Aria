"""Tests for main API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the API."""
    return TestClient(app, raise_server_exceptions=False)


def test_health_check(client: TestClient) -> None:
    """Test that health check endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_root_endpoint(client: TestClient) -> None:
    """Test that root endpoint returns API information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ARIA API"
    assert data["version"] == "1.0.0"
    assert "description" in data


def test_cors_headers(client: TestClient) -> None:
    """Test that CORS headers are set correctly for allowed origins."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_headers_different_origin(client: TestClient) -> None:
    """Test CORS headers for another allowed origin."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_auth_me_requires_authentication(client: TestClient) -> None:
    """Test that /api/v1/auth/me requires authentication."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_login_validation_error(client: TestClient) -> None:
    """Test that login validates email format."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "invalid-email", "password": "password123"},
    )
    assert response.status_code == 422  # Validation error


def test_signup_validation_error(client: TestClient) -> None:
    """Test that signup validates required fields."""
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "test@example.com", "password": "short"},  # Password too short
    )
    assert response.status_code == 422  # Validation error


def test_health_check_neo4j_not_configured(client: TestClient) -> None:
    """Test that Neo4j health endpoint returns status when not configured."""
    response = client.get("/health/neo4j")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    # When not initialized, should return unhealthy
    assert data["status"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
async def test_lifespan_closes_graphiti_on_shutdown() -> None:
    """Test that lifespan handler closes Graphiti on shutdown."""
    from unittest.mock import AsyncMock, patch

    with patch("src.db.graphiti.GraphitiClient") as mock_client_class:
        mock_client_class.close = AsyncMock()
        mock_client_class.is_initialized.return_value = True

        from src.main import app, lifespan

        async with lifespan(app):
            pass  # Simulate app running

        mock_client_class.close.assert_called_once()


def test_security_middleware_is_registered() -> None:
    """Test that security middleware is registered on app startup (US-932)."""
    from fastapi.middleware.trustedhost import TrustedHostMiddleware

    from src.core.security import SecurityHeadersMiddleware

    # Check that middleware is registered
    middleware_classes = [m.cls for m in app.user_middleware]

    assert SecurityHeadersMiddleware in middleware_classes
    assert TrustedHostMiddleware in middleware_classes
