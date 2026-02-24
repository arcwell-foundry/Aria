"""Tests for integrations API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from src.api.routes import integrations
from src.api.deps import get_current_user
from src.integrations.domain import (
    Integration,
    IntegrationStatus,
    IntegrationType,
    SyncStatus,
)


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(integrations.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


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


class TestListIntegrations:
    """Tests for GET /integrations endpoint."""

    def test_list_integrations_empty(self, test_client: TestClient) -> None:
        """Test listing integrations when none connected."""
        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = MagicMock()
            service.get_user_integrations = AsyncMock(return_value=[])
            m.return_value = service

            response = test_client.get("/api/v1/integrations")

            assert response.status_code == 200
            assert response.json() == []

    def test_list_integrations_with_connections(self, test_client: TestClient) -> None:
        """Test listing integrations with connected integrations."""
        mock_integration = {
            "id": "integration-123",
            "user_id": "test-user-123",
            "integration_type": "google_calendar",
            "composio_connection_id": "conn-123",
            "composio_account_id": "acct-123",
            "display_name": "My Calendar",
            "status": "active",
            "last_sync_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
            "sync_status": "success",
            "error_message": None,
            "created_at": datetime(2024, 1, 10, 9, 0, 0, tzinfo=UTC).isoformat(),
            "updated_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
        }

        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = MagicMock()
            service.get_user_integrations = AsyncMock(return_value=[mock_integration])
            m.return_value = service

            response = test_client.get("/api/v1/integrations")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "integration-123"
            assert data[0]["integration_type"] == "google_calendar"
            assert data[0]["status"] == "active"

    def test_list_integrations_unauthorized(self) -> None:
        """Test listing integrations without authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/integrations")

        assert response.status_code == 401


class TestListAvailableIntegrations:
    """Tests for GET /integrations/available endpoint."""

    def test_list_available_integrations(self, test_client: TestClient) -> None:
        """Test listing all available integrations with their connection status."""
        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = MagicMock()
            service.get_available_integrations = AsyncMock(return_value=[
                {
                    "integration_type": "google_calendar",
                    "display_name": "Google Calendar",
                    "description": "Sync your calendar for meeting briefs and scheduling",
                    "icon": "calendar",
                    "is_connected": True,
                    "status": "active",
                },
                {
                    "integration_type": "gmail",
                    "display_name": "Gmail",
                    "description": "Connect Gmail for email drafting and analysis",
                    "icon": "mail",
                    "is_connected": False,
                    "status": None,
                },
            ])
            m.return_value = service

            response = test_client.get("/api/v1/integrations/available")

            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 2
            assert any(i["integration_type"] == "google_calendar" for i in data)
            assert any(i["integration_type"] == "gmail" for i in data)


class TestGetAuthUrl:
    """Tests for POST /integrations/{integration_type}/auth-url endpoint."""

    def test_get_auth_url_success(self, test_client: TestClient) -> None:
        """Test generating OAuth authorization URL."""
        with patch("src.api.routes.integrations.get_oauth_client") as m:
            oauth_client = MagicMock()
            oauth_client.generate_auth_url = AsyncMock(
                return_value="https://auth.composio.dev/authorize?code=test123"
            )
            m.return_value = oauth_client

            response = test_client.post(
                "/api/v1/integrations/google_calendar/auth-url",
                json={"redirect_uri": "http://localhost:5173/integrations/callback"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "authorization_url" in data
            assert data["authorization_url"] == "https://auth.composio.dev/authorize?code=test123"

    def test_get_auth_url_invalid_integration(self, test_client: TestClient) -> None:
        """Test generating auth URL for invalid integration type."""
        response = test_client.post(
            "/api/v1/integrations/invalid_integration/auth-url",
            json={"redirect_uri": "http://localhost:5173/integrations/callback"},
        )

        assert response.status_code == 400  # Bad request for invalid integration type


class TestConnectIntegration:
    """Tests for POST /integrations/{integration_type}/connect endpoint."""

    def test_connect_integration_success(self, test_client: TestClient) -> None:
        """Test completing OAuth connection."""
        mock_integration = {
            "id": "integration-123",
            "user_id": "test-user-123",
            "integration_type": "google_calendar",
            "composio_connection_id": "conn-123",
            "composio_account_id": "acct-123",
            "display_name": "user@example.com",
            "status": "active",
            "sync_status": "success",
            "last_sync_at": None,
            "error_message": None,
            "created_at": None,
            "updated_at": None,
        }

        with patch("src.api.routes.integrations.get_oauth_client") as m_oauth:
            oauth_client = MagicMock()
            oauth_client.exchange_code_for_connection = AsyncMock(
                return_value={
                    "connection_id": "conn-123",
                    "account_id": "acct-123",
                    "account_email": "user@example.com",
                }
            )
            m_oauth.return_value = oauth_client

            with patch("src.api.routes.integrations.get_integration_service") as m_service:
                service = MagicMock()
                service.create_integration = AsyncMock(return_value=mock_integration)
                m_service.return_value = service

                response = test_client.post(
                    "/api/v1/integrations/google_calendar/connect",
                    json={"code": "auth-code-123"},
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == "integration-123"
                assert data["integration_type"] == "google_calendar"
                assert data["status"] == "active"


class TestDisconnectIntegration:
    """Tests for POST /integrations/{integration_type}/disconnect endpoint."""

    def test_disconnect_integration_success(self, test_client: TestClient) -> None:
        """Test disconnecting an integration."""
        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = MagicMock()
            service.disconnect_integration = AsyncMock(return_value=None)
            m.return_value = service

            response = test_client.post("/api/v1/integrations/google_calendar/disconnect")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data


class TestSyncIntegration:
    """Tests for POST /integrations/{integration_id}/sync endpoint."""

    def test_sync_integration_success(self, test_client: TestClient) -> None:
        """Test triggering manual sync."""
        mock_integration = {
            "id": "integration-123",
            "user_id": "test-user-123",
            "integration_type": "google_calendar",
            "composio_connection_id": "conn-123",
            "status": "active",
            "sync_status": "success",
        }

        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = MagicMock()
            service.trigger_sync = AsyncMock(return_value=mock_integration)
            m.return_value = service

            response = test_client.post("/api/v1/integrations/integration-123/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "integration-123"
            assert data["sync_status"] == "success"
