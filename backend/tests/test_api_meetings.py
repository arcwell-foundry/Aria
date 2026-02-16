"""Tests for meeting brief API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


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


def test_get_upcoming_meetings_returns_list(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/upcoming returns list of upcoming meetings."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_upcoming_meetings = AsyncMock(
            return_value=[
                {
                    "id": "brief-1",
                    "calendar_event_id": "event-1",
                    "meeting_title": "Sales Review",
                    "meeting_time": "2026-02-03T14:00:00+00:00",
                    "status": "completed",
                    "attendees": ["alice@example.com"],
                },
                {
                    "id": "brief-2",
                    "calendar_event_id": "event-2",
                    "meeting_title": "Product Demo",
                    "meeting_time": "2026-02-04T10:00:00+00:00",
                    "status": "pending",
                    "attendees": ["bob@example.com"],
                },
            ]
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/meetings/upcoming")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["calendar_event_id"] == "event-1"
    assert data[0]["brief_status"] == "completed"
    assert data[1]["calendar_event_id"] == "event-2"
    assert data[1]["brief_status"] == "pending"


def test_get_upcoming_meetings_respects_limit(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/upcoming?limit=5 respects limit parameter."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_upcoming_meetings = AsyncMock(return_value=[])
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/meetings/upcoming?limit=5")

    assert response.status_code == 200
    mock_service.get_upcoming_meetings.assert_called_once()
    call_args = mock_service.get_upcoming_meetings.call_args
    assert call_args.kwargs.get("limit") == 5 or call_args.args[1] == 5


def test_get_meeting_brief_returns_brief(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/{id}/brief returns meeting brief."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_brief = AsyncMock(
            return_value={
                "id": "brief-123",
                "calendar_event_id": "event-123",
                "meeting_title": "Important Meeting",
                "meeting_time": "2026-02-03T15:00:00+00:00",
                "status": "completed",
                "brief_content": {
                    "summary": "Meeting with key stakeholders",
                    "suggested_agenda": ["Introductions", "Discussion", "Next steps"],
                    "risks_opportunities": ["Risk: tight timeline"],
                },
                "generated_at": "2026-02-03T10:00:00+00:00",
                "error_message": None,
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/meetings/event-123/brief")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "brief-123"
    assert data["calendar_event_id"] == "event-123"
    assert data["status"] == "completed"
    assert "summary" in data["brief_content"]


def test_get_meeting_brief_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/{id}/brief returns 404 when brief not found."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_brief = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/meetings/nonexistent-event/brief")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_brief_creates_new_brief(test_client: TestClient) -> None:
    """Test POST /api/v1/meetings/{id}/brief/generate creates and generates brief."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        created_brief = {
            "id": "brief-new",
            "calendar_event_id": "event-new",
            "meeting_title": "New Meeting",
            "meeting_time": "2026-02-05T09:00:00+00:00",
            "status": "pending",
            "attendees": ["new@example.com"],
            "brief_content": {},
            "generated_at": None,
            "error_message": None,
        }
        # First call returns None (brief doesn't exist), second call returns the created brief
        mock_service.get_brief = AsyncMock(side_effect=[None, created_brief])
        # Create new brief
        mock_service.create_brief = AsyncMock(return_value=created_brief)
        # Update status to pending (before background generation)
        mock_service.update_brief_status = AsyncMock(
            return_value={
                "id": "brief-new",
                "status": "pending",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/meetings/event-new/brief/generate",
            json={
                "meeting_title": "New Meeting",
                "meeting_time": "2026-02-05T09:00:00+00:00",
                "attendee_emails": ["new@example.com"],
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert data["id"] == "brief-new"
    assert data["status"] == "pending"


def test_generate_brief_triggers_regeneration_for_existing(
    test_client: TestClient,
) -> None:
    """Test POST /api/v1/meetings/{id}/brief/generate triggers regeneration for existing brief."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        existing_brief = {
            "id": "brief-existing",
            "calendar_event_id": "event-existing",
            "meeting_title": "Existing Meeting",
            "meeting_time": "2026-02-05T09:00:00+00:00",
            "status": "completed",
            "brief_content": {"summary": "Old content"},
            "generated_at": "2026-02-03T10:00:00+00:00",
            "error_message": None,
        }
        updated_brief = {
            **existing_brief,
            "status": "pending",
        }
        # First call returns existing brief, second call returns the updated brief
        mock_service.get_brief = AsyncMock(side_effect=[existing_brief, updated_brief])
        # Update status to pending
        mock_service.update_brief_status = AsyncMock(
            return_value={
                "id": "brief-existing",
                "status": "pending",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/meetings/event-existing/brief/generate",
            json={
                "meeting_title": "Existing Meeting",
                "meeting_time": "2026-02-05T09:00:00+00:00",
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert data["id"] == "brief-existing"
    assert data["status"] == "pending"


def test_generate_brief_requires_meeting_time(test_client: TestClient) -> None:
    """Test POST /api/v1/meetings/{id}/brief/generate requires meeting_time."""
    with patch("src.api.routes.meetings.MeetingBriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_brief = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/meetings/event-new/brief/generate",
            json={
                "meeting_title": "Missing Time Meeting",
            },
        )

    assert response.status_code == 400  # App custom handler returns 400 for validation errors


def test_meetings_endpoints_require_authentication() -> None:
    """Test all meeting endpoints require authentication."""
    client = TestClient(app)

    response = client.get("/api/v1/meetings/upcoming")
    assert response.status_code == 401

    response = client.get("/api/v1/meetings/event-123/brief")
    assert response.status_code == 401

    response = client.post(
        "/api/v1/meetings/event-123/brief/generate",
        json={
            "meeting_time": "2026-02-05T09:00:00+00:00",
        },
    )
    assert response.status_code == 401
