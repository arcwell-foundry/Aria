"""Tests for meeting debrief API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


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

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_debrief_creates_debrief(test_client: TestClient) -> None:
    """Test POST /debriefs creates a new debrief."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = [
            {
                "id": "debrief-123",
                "user_id": "test-user-123",
                "meeting_id": "meeting-abc",
                "meeting_title": "Sales Demo",
                "summary": "Great meeting",
                "outcome": "positive",
                "action_items": [],
                "commitments_ours": [],
                "commitments_theirs": [],
                "insights": [],
                "follow_up_needed": True,
                "follow_up_draft": "Draft email",
                "linked_lead_id": None,
                "created_at": "2026-02-02T15:00:00Z",
            }
        ]
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        response = test_client.post(
            "/api/v1/debriefs",
            json={
                "meeting_id": "meeting-abc",
                "notes": "Great meeting, they want to move forward",
                "meeting_context": {
                    "title": "Sales Demo",
                    "start_time": "2026-02-02T14:00:00Z",
                    "attendees": ["prospect@example.com"],
                },
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-123"
    assert data["meeting_id"] == "meeting-abc"
    assert data["outcome"] == "positive"


def test_list_debriefs_returns_debriefs(test_client: TestClient) -> None:
    """Test GET /debriefs returns list of debriefs."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = [
            {"id": "debrief-1", "meeting_id": "meeting-1", "summary": "Summary 1"},
            {"id": "debrief-2", "meeting_id": "meeting-2", "summary": "Summary 2"},
        ]
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/debriefs?limit=10")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2


def test_get_debrief_returns_debrief_when_found(test_client: TestClient) -> None:
    """Test GET /debriefs/{id} returns debrief when found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = {
            "id": "debrief-123",
            "user_id": "test-user-123",
            "meeting_id": "meeting-abc",
            "summary": "Great meeting",
        }
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/debriefs/debrief-123")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-123"
    assert data["summary"] == "Great meeting"


def test_get_debrief_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /debriefs/{id} returns 404 when debrief not found."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = None
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/debriefs/debrief-999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_debriefs_for_meeting_returns_debriefs(test_client: TestClient) -> None:
    """Test GET /debriefs/meeting/{meeting_id} returns debriefs for meeting."""
    with patch("src.services.debrief_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        result_mock = MagicMock()
        result_mock.data = [
            {"id": "debrief-1", "meeting_id": "meeting-abc", "summary": "First debrief"},
            {"id": "debrief-2", "meeting_id": "meeting-abc", "summary": "Second debrief"},
        ]
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = result_mock
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/debriefs/meeting/meeting-abc")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2


def test_debriefs_endpoints_require_authentication() -> None:
    """Test all debrief endpoints require authentication."""
    client = TestClient(app)

    response = client.post("/api/v1/debriefs", json={"meeting_id": "abc", "notes": "Notes"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/debriefs")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/debriefs/debrief-123")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/debriefs/meeting/meeting-abc")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
