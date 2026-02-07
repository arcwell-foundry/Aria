"""Tests for feedback API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app
from src.models.feedback import FeedbackResponse


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_submit_response_feedback_success(test_client: TestClient) -> None:
    """Test POST /api/v1/feedback/response returns 201 with feedback_id."""
    mock_feedback_response = FeedbackResponse(
        id="feedback-123",
        user_id="test-user-123",
        type="response",
        rating="up",
        message_id="msg-456",
        comment="Great response!",
        page=None,
        created_at=datetime.now(UTC),
    )

    with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{
            "id": "feedback-123",
            "user_id": "test-user-123",
            "type": "response",
            "rating": "up",
            "message_id": "msg-456",
            "comment": "Great response!",
            "page": None,
            "created_at": datetime.now(UTC).isoformat(),
        }]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        response = test_client.post(
            "/api/v1/feedback/response",
            json={
                "message_id": "msg-456",
                "rating": "up",
                "comment": "Great response!",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Thank you for your feedback!"
    assert data["feedback_id"] == "feedback-123"


def test_submit_response_feedback_invalid_rating(test_client: TestClient) -> None:
    """Test POST /api/v1/feedback/response with invalid rating returns 422."""
    response = test_client.post(
        "/api/v1/feedback/response",
        json={
            "message_id": "msg-456",
            "rating": "invalid",
            "comment": "This should fail",
        },
    )

    assert response.status_code == 422


def test_submit_general_feedback_success(test_client: TestClient) -> None:
    """Test POST /api/v1/feedback/general returns 201 with feedback_id."""
    mock_feedback_response = FeedbackResponse(
        id="feedback-789",
        user_id="test-user-123",
        type="bug",
        rating=None,
        message_id=None,
        comment=None,
        page="/dashboard",
        created_at=datetime.now(UTC),
    )

    with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{
            "id": "feedback-789",
            "user_id": "test-user-123",
            "type": "bug",
            "rating": None,
            "message_id": None,
            "comment": None,
            "page": "/dashboard",
            "created_at": datetime.now(UTC).isoformat(),
        }]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        response = test_client.post(
            "/api/v1/feedback/general",
            json={
                "type": "bug",
                "message": "Found a bug on the dashboard",
                "page": "/dashboard",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Thank you for your feedback!"
    assert data["feedback_id"] == "feedback-789"


def test_submit_general_feedback_missing_message(test_client: TestClient) -> None:
    """Test POST /api/v1/feedback/general without message returns 422."""
    response = test_client.post(
        "/api/v1/feedback/general",
        json={
            "type": "bug",
            "page": "/dashboard",
        },
    )

    assert response.status_code == 422


def test_submit_response_feedback_unauthorized() -> None:
    """Test POST /api/v1/feedback/response without auth returns 401."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/feedback/response",
        json={
            "message_id": "msg-456",
            "rating": "up",
        },
    )

    assert response.status_code == 401
