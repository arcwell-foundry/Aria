"""Tests for preferences API routes.

These tests follow TDD principles - tests were written first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import preferences


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(preferences.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_preferences() -> dict:
    """Create mock preferences response."""
    return {
        "id": "pref-uuid-123",
        "user_id": "test-user-123",
        "briefing_time": "08:00",
        "meeting_brief_lead_hours": 24,
        "notification_email": True,
        "notification_in_app": True,
        "default_tone": "friendly",
        "tracked_competitors": [],
        "timezone": "UTC",
        "created_at": "2026-02-03T10:00:00+00:00",
        "updated_at": "2026-02-03T10:00:00+00:00",
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


class TestGetPreferences:
    """Tests for GET /api/v1/settings/preferences endpoint."""

    def test_get_preferences_success(
        self, test_client: TestClient, mock_preferences: dict
    ) -> None:
        """Test GET /api/v1/settings/preferences returns preferences successfully."""
        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_preferences = AsyncMock(return_value=mock_preferences)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/settings/preferences")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-123"
        assert data["briefing_time"] == "08:00"
        assert data["meeting_brief_lead_hours"] == 24
        assert data["notification_email"] is True
        assert data["notification_in_app"] is True
        assert data["default_tone"] == "friendly"
        assert data["tracked_competitors"] == []
        assert data["timezone"] == "UTC"

    def test_get_preferences_unauthenticated(self) -> None:
        """Test GET /api/v1/settings/preferences returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/settings/preferences")
        assert response.status_code == 401

    def test_get_preferences_server_error(self, test_client: TestClient) -> None:
        """Test GET /api/v1/settings/preferences returns 500 on service error."""
        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_preferences = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/settings/preferences")

        assert response.status_code == 500
        assert response.json()["detail"]  # Sanitized error message


class TestUpdatePreferences:
    """Tests for PUT /api/v1/settings/preferences endpoint."""

    def test_update_preferences_success(
        self, test_client: TestClient, mock_preferences: dict
    ) -> None:
        """Test PUT /api/v1/settings/preferences updates preferences successfully."""
        updated_prefs = {**mock_preferences, "briefing_time": "09:00"}

        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_preferences = AsyncMock(return_value=updated_prefs)
            mock_get_service.return_value = mock_service

            response = test_client.put(
                "/api/v1/settings/preferences",
                json={"briefing_time": "09:00"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["briefing_time"] == "09:00"

    def test_update_preferences_unauthenticated(self) -> None:
        """Test PUT /api/v1/settings/preferences returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.put(
            "/api/v1/settings/preferences", json={"briefing_time": "09:00"}
        )
        assert response.status_code == 401

    def test_update_preferences_invalid_tone(self, test_client: TestClient) -> None:
        """Test PUT /api/v1/settings/preferences returns 422 for invalid tone."""
        response = test_client.put(
            "/api/v1/settings/preferences",
            json={"default_tone": "aggressive"},  # Invalid tone value
        )
        assert response.status_code == 422

    def test_update_preferences_invalid_time(self, test_client: TestClient) -> None:
        """Test PUT /api/v1/settings/preferences returns 422 for invalid time format."""
        response = test_client.put(
            "/api/v1/settings/preferences",
            json={"briefing_time": "25:00"},  # Invalid time
        )
        assert response.status_code == 422

    def test_update_preferences_invalid_lead_hours(
        self, test_client: TestClient
    ) -> None:
        """Test PUT /api/v1/settings/preferences returns 422 for invalid lead hours."""
        response = test_client.put(
            "/api/v1/settings/preferences",
            json={"meeting_brief_lead_hours": 5},  # Not in allowed enum (2, 6, 12, 24)
        )
        assert response.status_code == 422

    def test_update_preferences_partial_update(
        self, test_client: TestClient, mock_preferences: dict
    ) -> None:
        """Test PUT /api/v1/settings/preferences accepts partial updates."""
        updated_prefs = {**mock_preferences, "notification_email": False}

        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_preferences = AsyncMock(return_value=updated_prefs)
            mock_get_service.return_value = mock_service

            response = test_client.put(
                "/api/v1/settings/preferences",
                json={"notification_email": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["notification_email"] is False
        # Other fields should remain unchanged
        assert data["briefing_time"] == "08:00"

    def test_update_preferences_value_error(
        self, test_client: TestClient
    ) -> None:
        """Test PUT /api/v1/settings/preferences returns 400 on ValueError from service."""
        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_preferences = AsyncMock(
                side_effect=ValueError("Invalid competitor name")
            )
            mock_get_service.return_value = mock_service

            response = test_client.put(
                "/api/v1/settings/preferences",
                json={"tracked_competitors": ["Invalid"]},
            )

        assert response.status_code == 400
        assert response.json()["detail"]  # Sanitized error message

    def test_update_preferences_server_error(
        self, test_client: TestClient
    ) -> None:
        """Test PUT /api/v1/settings/preferences returns 500 on service error."""
        with patch("src.api.routes.preferences._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_preferences = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_get_service.return_value = mock_service

            response = test_client.put(
                "/api/v1/settings/preferences",
                json={"briefing_time": "09:00"},
            )

        assert response.status_code == 500
        assert response.json()["detail"]  # Sanitized error message
