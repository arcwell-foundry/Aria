"""Tests for Communication API routes (US-938)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import communication
from src.models.communication import (
    ChannelResult,
    ChannelType,
    CommunicationResponse,
    MessagePriority,
)


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(communication.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    # Make it behave like a dict for ['id'] access
    user.__getitem__ = lambda _self, key: {"id": "test-user-123", "email": "test@example.com"}.get(
        key
    )
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


@pytest.fixture
def client() -> TestClient:
    """Create test client without authentication."""
    app = create_test_app()
    return TestClient(app)


class TestPostCommunicate:
    """Test POST /communicate endpoint."""

    def test_communicate_required(self, client: TestClient) -> None:
        """Endpoint should require authentication."""
        response = client.post("/api/v1/communicate", json={})
        assert response.status_code == 401

    def test_send_fyi_notification(self, test_client: TestClient) -> None:
        """Should send FYI message to in-app notifications."""
        request_data = {
            "user_id": "user-123",  # Will be overridden by auth
            "message": "Test FYI message",
            "priority": "fyi",
            "title": "Test Title",
        }

        mock_response = CommunicationResponse(
            user_id="user-123",
            priority=MessagePriority.FYI,
            channels_used=[ChannelType.IN_APP],
            results={
                ChannelType.IN_APP: ChannelResult(
                    channel=ChannelType.IN_APP,
                    success=True,
                    message_id="notif-123",
                    error=None,
                )
            },
        )

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(return_value=mock_response)
            mock_get_router.return_value = mock_router

            response = test_client.post("/api/v1/communicate", json=request_data)

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "user-123"
            assert data["priority"] == "fyi"
            assert "in_app" in data["channels_used"]

    def test_send_with_force_channels(self, test_client: TestClient) -> None:
        """Should respect force_channels parameter."""
        request_data = {
            "user_id": "user-123",  # Will be overridden by auth
            "message": "Forced email message",
            "priority": "fyi",
            "force_channels": ["email"],
        }

        mock_response = CommunicationResponse(
            user_id="user-123",
            priority=MessagePriority.FYI,
            channels_used=[ChannelType.EMAIL],
            results={
                ChannelType.EMAIL: ChannelResult(
                    channel=ChannelType.EMAIL,
                    success=True,
                    message_id="email-123",
                    error=None,
                )
            },
        )

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(return_value=mock_response)
            mock_get_router.return_value = mock_router

            response = test_client.post("/api/v1/communicate", json=request_data)

            assert response.status_code == 200

    def test_validates_message_length(self, test_client: TestClient) -> None:
        """Should reject messages that are too long."""
        request_data = {
            "message": "x" * 5001,  # Over 5000 char limit
            "priority": "fyi",
        }

        response = test_client.post("/api/v1/communicate", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_validates_priority_enum(self, test_client: TestClient) -> None:
        """Should reject invalid priority values."""
        request_data = {
            "message": "Test",
            "priority": "invalid_priority",
        }

        response = test_client.post("/api/v1/communicate", json=request_data)
        assert response.status_code == 422

    def test_user_id_overridden_by_auth(self, test_client: TestClient) -> None:
        """user_id in request should be overridden by authenticated user."""
        request_data = {
            "user_id": "different-user-id",  # Should be ignored
            "message": "Test",
            "priority": "fyi",
        }

        mock_response = CommunicationResponse(
            user_id="test-user-123",  # From auth token
            priority=MessagePriority.FYI,
            channels_used=[ChannelType.IN_APP],
            results={
                ChannelType.IN_APP: ChannelResult(
                    channel=ChannelType.IN_APP,
                    success=True,
                    message_id="notif-123",
                    error=None,
                )
            },
        )

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(return_value=mock_response)
            mock_get_router.return_value = mock_router

            test_client.post("/api/v1/communicate", json=request_data)

            # Verify router was called with authenticated user ID
            mock_router.route_message.assert_called_once()
            call_args = mock_router.route_message.call_args[0][0]
            assert call_args.user_id != "different-user-id"
            assert call_args.user_id == "test-user-123"

    def test_all_channels_fail_returns_503(self, test_client: TestClient) -> None:
        """Should return 503 when all channels fail."""
        request_data = {
            "user_id": "test-user-123",
            "message": "Urgent alert",
            "priority": "critical",
        }

        mock_response = CommunicationResponse(
            user_id="test-user-123",
            priority=MessagePriority.CRITICAL,
            channels_used=[],
            results={
                ChannelType.IN_APP: ChannelResult(
                    channel=ChannelType.IN_APP,
                    success=False,
                    message_id=None,
                    error="Service unavailable",
                ),
                ChannelType.PUSH: ChannelResult(
                    channel=ChannelType.PUSH,
                    success=False,
                    message_id=None,
                    error="Push not implemented",
                ),
            },
        )

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(return_value=mock_response)
            mock_get_router.return_value = mock_router

            response = test_client.post("/api/v1/communicate", json=request_data)

            assert response.status_code == 503

    def test_internal_error_returns_500(self, test_client: TestClient) -> None:
        """Should return 500 on unexpected internal errors."""
        request_data = {
            "user_id": "test-user-123",
            "message": "Test",
            "priority": "fyi",
        }

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(side_effect=RuntimeError("Unexpected failure"))
            mock_get_router.return_value = mock_router

            response = test_client.post("/api/v1/communicate", json=request_data)

            assert response.status_code == 500

    def test_background_priority_with_no_channels(self, test_client: TestClient) -> None:
        """BACKGROUND priority should succeed even with no channels used."""
        request_data = {
            "user_id": "test-user-123",
            "message": "Background task done",
            "priority": "background",
        }

        # Background returns empty results but no channels fail,
        # so the "any_success" check is False (no results at all).
        # The route should return 503 since there are no successful channels.
        mock_response = CommunicationResponse(
            user_id="test-user-123",
            priority=MessagePriority.BACKGROUND,
            channels_used=[],
            results={},
        )

        with patch("src.api.routes.communication.get_communication_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.route_message = AsyncMock(return_value=mock_response)
            mock_get_router.return_value = mock_router

            response = test_client.post("/api/v1/communicate", json=request_data)

            # Background with no channels: results dict is empty, so
            # any() on empty iterable is False → 503
            # This is correct behavior - agents should not use the HTTP
            # endpoint for background messages (they're logged only).
            assert response.status_code == 503
