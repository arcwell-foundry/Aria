"""Tests for notification API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import notifications


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(notifications.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    # Make it behave like a dict for ['id'] access
    user.__getitem__ = lambda self, key: {"id": "test-user-123", "email": "test@example.com"}.get(key)
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    def override_get_current_user():
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestNotificationsListEndpoint:
    """Tests for GET /api/v1/notifications endpoint."""

    def test_list_notifications_requires_auth(self) -> None:
        """Test GET /api/v1/notifications requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/notifications")
        assert response.status_code == 401

    def test_list_notifications_returns_empty_list(self, test_client: TestClient) -> None:
        """Test GET /api/v1/notifications returns empty list when no notifications exist."""
        mock_response = MagicMock(notifications=[], total=0, unread_count=0)

        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.get_notifications = AsyncMock(return_value=mock_response)
            mock_service.get_notifications = instance.get_notifications

            response = test_client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["notifications"] == []
        assert data["total"] == 0
        assert data["unread_count"] == 0

    def test_list_notifications_with_data(self, test_client: TestClient) -> None:
        """Test GET /api/v1/notifications returns notifications when data exists."""
        mock_notif = MagicMock(
            id="notif-1",
            user_id="test-user-123",
            type="signal_detected",
            title="Test Signal",
            message="Test message",
            link="/leads/test",
            metadata={},
            read_at=None,
            created_at="2026-02-03T10:00:00Z",
        )

        mock_response = MagicMock(notifications=[mock_notif], total=1, unread_count=1)

        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.get_notifications = AsyncMock(return_value=mock_response)
            mock_service.get_notifications = instance.get_notifications

            response = test_client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["title"] == "Test Signal"


class TestUnreadCountEndpoint:
    """Tests for GET /api/v1/notifications/unread/count endpoint."""

    def test_get_unread_count_requires_auth(self) -> None:
        """Test GET /api/v1/notifications/unread/count requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/notifications/unread/count")
        assert response.status_code == 401

    def test_get_unread_count(self, test_client: TestClient) -> None:
        """Test GET /api/v1/notifications/unread/count returns count."""
        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.get_unread_count = AsyncMock(return_value=MagicMock(count=5))
            mock_service.get_unread_count = instance.get_unread_count

            response = test_client.get("/api/v1/notifications/unread/count")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)


class TestMarkAsReadEndpoint:
    """Tests for PUT /api/v1/notifications/{id}/read endpoint."""

    def test_mark_notification_read_requires_auth(self) -> None:
        """Test PUT /api/v1/notifications/{id}/read requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.put("/api/v1/notifications/notif-1/read")
        assert response.status_code == 401

    def test_mark_notification_read(self, test_client: TestClient) -> None:
        """Test PUT /api/v1/notifications/{id}/read marks notification as read."""
        mock_notif = MagicMock(
            id="notif-1",
            user_id="test-user-123",
            type="signal_detected",
            title="Test Signal",
            message="Test message",
            link="/leads/test",
            metadata={},
            read_at="2026-02-03T10:00:00Z",
            created_at="2026-02-03T09:00:00Z",
        )

        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.mark_as_read = AsyncMock(return_value=mock_notif)
            mock_service.mark_as_read = instance.mark_as_read

            response = test_client.put("/api/v1/notifications/notif-1/read")

        assert response.status_code == 200
        data = response.json()
        assert data["read_at"] is not None


class TestMarkAllReadEndpoint:
    """Tests for PUT /api/v1/notifications/read-all endpoint."""

    def test_mark_all_read_requires_auth(self) -> None:
        """Test PUT /api/v1/notifications/read-all requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.put("/api/v1/notifications/read-all")
        assert response.status_code == 401

    def test_mark_all_read(self, test_client: TestClient) -> None:
        """Test PUT /api/v1/notifications/read-all marks all as read."""
        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.mark_all_as_read = AsyncMock(return_value=3)
            mock_service.mark_all_as_read = instance.mark_all_as_read

            response = test_client.put("/api/v1/notifications/read-all")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 3


class TestDeleteNotificationEndpoint:
    """Tests for DELETE /api/v1/notifications/{id} endpoint."""

    def test_delete_notification_requires_auth(self) -> None:
        """Test DELETE /api/v1/notifications/{id} requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.delete("/api/v1/notifications/notif-1")
        assert response.status_code == 401

    def test_delete_notification(self, test_client: TestClient) -> None:
        """Test DELETE /api/v1/notifications/{id} deletes notification."""
        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.delete_notification = AsyncMock(return_value=None)
            mock_service.delete_notification = instance.delete_notification

            response = test_client.delete("/api/v1/notifications/notif-1")

        assert response.status_code == 204


class TestPagination:
    """Tests for pagination functionality."""

    def test_pagination_works(self, test_client: TestClient) -> None:
        """Test pagination parameters are passed through correctly."""
        mock_response = MagicMock(notifications=[], total=10, unread_count=5)

        with patch("src.api.routes.notifications.NotificationService") as mock_service:
            instance = MagicMock()
            instance.get_notifications = AsyncMock(return_value=mock_response)
            mock_service.get_notifications = instance.get_notifications

            response = test_client.get("/api/v1/notifications?limit=2&offset=4")

        assert response.status_code == 200
        # Verify the service was called with correct pagination params
        instance.get_notifications.assert_called_once_with(
            user_id="test-user-123",
            limit=2,
            offset=4,
            unread_only=False,
        )
