"""Tests for email preferences API routes.

These tests follow TDD principles - tests were written first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import email_preferences


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(email_preferences.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_email_preferences() -> dict:
    """Create mock email preferences response."""
    return {
        "user_id": "test-user-123",
        "weekly_summary": True,
        "feature_announcements": True,
        "security_alerts": True,
    }


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


class TestGetEmailPreferences:
    """Tests for GET /api/v1/settings/email-preferences endpoint."""

    def test_get_email_preferences_authenticated(
        self, test_client: TestClient, mock_email_preferences: dict
    ) -> None:
        """Test GET /api/v1/settings/email-preferences returns preferences successfully."""
        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_email_preferences = AsyncMock(return_value=mock_email_preferences)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/settings/email-preferences")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-123"
        assert data["weekly_summary"] is True
        assert data["feature_announcements"] is True
        assert data["security_alerts"] is True  # Always true, cannot be disabled

    def test_get_email_preferences_unauthenticated(self) -> None:
        """Test GET /api/v1/settings/email-preferences returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/settings/email-preferences")
        assert response.status_code == 401

    def test_get_email_preferences_server_error(self, test_client: TestClient) -> None:
        """Test GET /api/v1/settings/email-preferences returns 500 on service error."""
        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_email_preferences = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/settings/email-preferences")

        assert response.status_code == 500
        assert response.json()["detail"]  # Sanitized error message


class TestUpdateEmailPreferences:
    """Tests for PATCH /api/v1/settings/email-preferences endpoint."""

    def test_update_email_preferences_single_field(
        self, test_client: TestClient, mock_email_preferences: dict
    ) -> None:
        """Test PATCH /api/v1/settings/email-preferences updates single field successfully."""
        updated_prefs = {**mock_email_preferences, "weekly_summary": False}

        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_email_preferences = AsyncMock(return_value=updated_prefs)
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/settings/email-preferences",
                json={"weekly_summary": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["weekly_summary"] is False
        # Other fields should remain unchanged
        assert data["feature_announcements"] is True
        assert data["security_alerts"] is True

    def test_update_email_preferences_unauthenticated(self) -> None:
        """Test PATCH /api/v1/settings/email-preferences returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.patch(
            "/api/v1/settings/email-preferences",
            json={"weekly_summary": False},
        )
        assert response.status_code == 401

    def test_security_alerts_cannot_be_disabled(self, test_client: TestClient) -> None:
        """Test PATCH /api/v1/settings/email-preferences returns 400 when trying to disable security_alerts."""
        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_email_preferences = AsyncMock(
                side_effect=ValueError("Security alerts cannot be disabled")
            )
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/settings/email-preferences",
                json={"security_alerts": False},
            )

        assert response.status_code == 400
        assert response.json()["detail"]  # Sanitized error message

    def test_update_multiple_preferences(
        self, test_client: TestClient, mock_email_preferences: dict
    ) -> None:
        """Test PATCH /api/v1/settings/email-preferences updates multiple fields successfully."""
        updated_prefs = {
            **mock_email_preferences,
            "weekly_summary": False,
            "feature_announcements": False,
        }

        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_email_preferences = AsyncMock(return_value=updated_prefs)
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/settings/email-preferences",
                json={
                    "weekly_summary": False,
                    "feature_announcements": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["weekly_summary"] is False
        assert data["feature_announcements"] is False
        assert data["security_alerts"] is True

    def test_update_email_preferences_value_error(
        self, test_client: TestClient
    ) -> None:
        """Test PATCH /api/v1/settings/email-preferences returns 400 on ValueError from service."""
        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_email_preferences = AsyncMock(
                side_effect=ValueError("Invalid preference value")
            )
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/settings/email-preferences",
                json={"weekly_summary": False},  # Valid type, but service raises ValueError
            )

        assert response.status_code == 400
        assert response.json()["detail"]  # Sanitized error message

    def test_update_email_preferences_server_error(
        self, test_client: TestClient
    ) -> None:
        """Test PATCH /api/v1/settings/email-preferences returns 500 on service error."""
        with patch("src.api.routes.email_preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_email_preferences = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/settings/email-preferences",
                json={"weekly_summary": False},
            )

        assert response.status_code == 500
        assert response.json()["detail"]  # Sanitized error message
