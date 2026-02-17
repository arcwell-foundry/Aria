"""Tests for meeting debrief API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

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


# =============================================================================
# POST /debriefs - Initiate Debrief
# =============================================================================


def test_initiate_debrief_creates_pending_debrief(test_client: TestClient) -> None:
    """Test POST /debriefs initiates a pending debrief."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.initiate_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "user_id": "test-user-123",
                "meeting_id": "meeting-abc",
                "meeting_title": "Sales Demo with Lonza",
                "meeting_time": "2026-02-17T14:00:00Z",
                "linked_lead_id": "lead-456",
                "status": "pending",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/debriefs",
            json={
                "meeting_id": "meeting-abc",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-123"
    assert data["meeting_title"] == "Sales Demo with Lonza"
    assert data["meeting_time"] == "2026-02-17T14:00:00Z"
    assert data["linked_lead_id"] == "lead-456"
    assert "pre_filled_context" in data


def test_initiate_debrief_with_calendar_event_id(test_client: TestClient) -> None:
    """Test POST /debriefs with calendar_event_id UUID."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.initiate_debrief = AsyncMock(
            return_value={
                "id": "debrief-456",
                "meeting_id": "550e8400-e29b-41d4-a716-446655440000",
                "meeting_title": "Partnership Discussion",
                "meeting_time": "2026-02-18T10:00:00Z",
                "linked_lead_id": None,
                "status": "pending",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/debriefs",
            json={
                "meeting_id": "placeholder",
                "calendar_event_id": "550e8400-e29b-41d4-a716-446655440000",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-456"
    assert data["meeting_title"] == "Partnership Discussion"


def test_initiate_debrief_handles_error(test_client: TestClient) -> None:
    """Test POST /debriefs handles initiation errors."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.initiate_debrief = AsyncMock(
            side_effect=Exception("Meeting not found")
        )
        mock_service_class.return_value = mock_service

        response = test_client.post(
            "/api/v1/debriefs",
            json={"meeting_id": "invalid-meeting"},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Failed to initiate debrief" in response.json()["detail"]


# =============================================================================
# PUT /debriefs/{id} - Submit Debrief Notes
# =============================================================================


def test_submit_debrief_processes_notes(test_client: TestClient) -> None:
    """Test PUT /debriefs/{id} submits notes and triggers processing."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "user_id": "test-user-123",
                "meeting_id": "meeting-abc",
                "status": "pending",
            }
        )
        mock_service.process_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "summary": "Great meeting, they want to proceed",
                "outcome": "positive",
                "action_items": [{"task": "Send proposal", "owner": "us"}],
                "commitments_ours": ["Send pricing by Friday"],
                "commitments_theirs": ["Review with team"],
                "insights": [{"type": "buying_signal", "content": "Interested in enterprise plan"}],
                "follow_up_needed": True,
            }
        )
        mock_service.post_process_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "summary": "Great meeting, they want to proceed",
                "outcome": "positive",
                "action_items": [{"task": "Send proposal", "owner": "us"}],
                "commitments_ours": ["Send pricing by Friday"],
                "commitments_theirs": ["Review with team"],
                "insights": [{"type": "buying_signal", "content": "Interested in enterprise plan"}],
                "follow_up_needed": True,
                "follow_up_draft": "Dear John, Thank you for...",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.put(
            "/api/v1/debriefs/debrief-123",
            json={
                "raw_notes": "Great meeting. They want to move forward with enterprise plan.",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-123"
    assert data["summary"] == "Great meeting, they want to proceed"
    assert len(data["action_items"]) == 1
    assert data["follow_up_draft"] == "Dear John, Thank you for..."


def test_submit_debrief_returns_404_for_nonexistent(test_client: TestClient) -> None:
    """Test PUT /debriefs/{id} returns 404 for nonexistent debrief."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debrief = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        response = test_client.put(
            "/api/v1/debriefs/nonexistent-id",
            json={"raw_notes": "Some notes"},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_submit_debrief_handles_processing_error(test_client: TestClient) -> None:
    """Test PUT /debriefs/{id} handles processing errors."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "user_id": "test-user-123",
                "status": "pending",
            }
        )
        mock_service.process_debrief = AsyncMock(
            side_effect=ValueError("Invalid notes format")
        )
        mock_service_class.return_value = mock_service

        response = test_client.put(
            "/api/v1/debriefs/debrief-123",
            json={"raw_notes": "Test notes"},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# GET /debriefs - List Debriefs with Pagination
# =============================================================================


def test_list_debriefs_returns_paginated_list(test_client: TestClient) -> None:
    """Test GET /debriefs returns paginated list."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_debriefs_filtered = AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "debrief-1",
                        "meeting_id": "meeting-1",
                        "meeting_title": "Sales Call",
                        "meeting_time": "2026-02-17T10:00:00Z",
                        "outcome": "positive",
                        "action_items": [{"task": "Follow up"}],
                        "linked_lead_id": "lead-1",
                        "status": "completed",
                        "created_at": "2026-02-17T12:00:00Z",
                    },
                    {
                        "id": "debrief-2",
                        "meeting_id": "meeting-2",
                        "meeting_title": "Demo",
                        "meeting_time": "2026-02-16T14:00:00Z",
                        "outcome": "neutral",
                        "action_items": [],
                        "linked_lead_id": None,
                        "status": "completed",
                        "created_at": "2026-02-16T16:00:00Z",
                    },
                ],
                "total": 25,
                "has_more": True,
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs?page=1&page_size=20")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["has_more"] is True
    assert data["items"][0]["action_items_count"] == 1


def test_list_debriefs_with_date_filter(test_client: TestClient) -> None:
    """Test GET /debriefs with date range filtering."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_debriefs_filtered = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "has_more": False,
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.get(
            "/api/v1/debriefs?start_date=2026-02-01T00:00:00Z&end_date=2026-02-28T23:59:59Z"
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["items"] == []


def test_list_debriefs_with_lead_filter(test_client: TestClient) -> None:
    """Test GET /debriefs with lead ID filtering."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_debriefs_filtered = AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "debrief-1",
                        "meeting_id": "meeting-1",
                        "meeting_title": "Lonza Meeting",
                        "linked_lead_id": "lead-123",
                        "action_items": [],
                        "status": "completed",
                        "created_at": "2026-02-17T12:00:00Z",
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs?linked_lead_id=lead-123")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["linked_lead_id"] == "lead-123"


# =============================================================================
# GET /debriefs/pending - Pending Debriefs
# =============================================================================


def test_get_pending_debriefs_returns_meetings(test_client: TestClient) -> None:
    """Test GET /debriefs/pending returns meetings needing debrief."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.check_pending_debriefs = AsyncMock(
            return_value=[
                {
                    "id": "event-1",
                    "title": "Sales Demo with Pfizer",
                    "start_time": "2026-02-16T14:00:00Z",
                    "end_time": "2026-02-16T15:00:00Z",
                    "external_company": "Pfizer",
                    "attendees": ["john@pfizer.com"],
                },
                {
                    "id": "event-2",
                    "title": "Follow-up Call",
                    "start_time": "2026-02-15T10:00:00Z",
                    "end_time": "2026-02-15T10:30:00Z",
                    "external_company": None,
                    "attendees": [],
                },
            ]
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs/pending")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Sales Demo with Pfizer"
    assert data[0]["external_company"] == "Pfizer"
    assert data[1]["title"] == "Follow-up Call"


def test_get_pending_debriefs_respects_limit(test_client: TestClient) -> None:
    """Test GET /debriefs/pending respects limit parameter."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.check_pending_debriefs = AsyncMock(
            return_value=[
                {"id": f"event-{i}", "title": f"Meeting {i}", "attendees": []}
                for i in range(20)
            ]
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs/pending?limit=5")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 5


# =============================================================================
# GET /debriefs/{id} - Get Specific Debrief
# =============================================================================


def test_get_debrief_returns_full_debrief(test_client: TestClient) -> None:
    """Test GET /debriefs/{id} returns full debrief details."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debrief = AsyncMock(
            return_value={
                "id": "debrief-123",
                "user_id": "test-user-123",
                "meeting_id": "meeting-abc",
                "meeting_title": "Sales Demo",
                "meeting_time": "2026-02-17T14:00:00Z",
                "raw_notes": "Great meeting. They want to proceed.",
                "summary": "Positive outcome",
                "outcome": "positive",
                "action_items": [{"task": "Send proposal", "owner": "us", "due_date": None}],
                "commitments_ours": ["Send pricing"],
                "commitments_theirs": ["Review internally"],
                "insights": [{"type": "buying_signal", "content": "Ready to buy"}],
                "follow_up_needed": True,
                "follow_up_draft": "Dear John...",
                "linked_lead_id": "lead-456",
                "status": "completed",
                "created_at": "2026-02-17T16:00:00Z",
            }
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs/debrief-123")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "debrief-123"
    assert data["summary"] == "Positive outcome"
    assert data["raw_notes"] == "Great meeting. They want to proceed."
    assert len(data["action_items"]) == 1
    assert data["status"] == "completed"


def test_get_debrief_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /debriefs/{id} returns 404 when not found."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debrief = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs/debrief-999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# GET /debriefs/meeting/{meeting_id} - Debriefs for Meeting
# =============================================================================


def test_get_debriefs_for_meeting_returns_debriefs(test_client: TestClient) -> None:
    """Test GET /debriefs/meeting/{meeting_id} returns debriefs for meeting."""
    with patch("src.api.routes.debriefs.DebriefService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.get_debriefs_for_meeting = AsyncMock(
            return_value=[
                {
                    "id": "debrief-1",
                    "user_id": "test-user-123",
                    "meeting_id": "meeting-abc",
                    "meeting_title": "Sales Demo",
                    "meeting_time": "2026-02-17T14:00:00Z",
                    "raw_notes": "First debrief",
                    "summary": "First summary",
                    "outcome": "positive",
                    "action_items": [],
                    "commitments_ours": [],
                    "commitments_theirs": [],
                    "insights": [],
                    "follow_up_needed": False,
                    "follow_up_draft": None,
                    "linked_lead_id": None,
                    "status": "completed",
                    "created_at": "2026-02-17T16:00:00Z",
                },
                {
                    "id": "debrief-2",
                    "user_id": "test-user-123",
                    "meeting_id": "meeting-abc",
                    "meeting_title": "Sales Demo",
                    "meeting_time": "2026-02-17T14:00:00Z",
                    "raw_notes": "Updated notes",
                    "summary": "Updated summary",
                    "outcome": "positive",
                    "action_items": [],
                    "commitments_ours": [],
                    "commitments_theirs": [],
                    "insights": [],
                    "follow_up_needed": True,
                    "follow_up_draft": "Follow up email",
                    "linked_lead_id": None,
                    "status": "completed",
                    "created_at": "2026-02-17T18:00:00Z",
                },
            ]
        )
        mock_service_class.return_value = mock_service

        response = test_client.get("/api/v1/debriefs/meeting/meeting-abc")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "debrief-1"
    assert data[1]["id"] == "debrief-2"


# =============================================================================
# Authentication Tests
# =============================================================================


def test_debriefs_endpoints_require_authentication() -> None:
    """Test all debrief endpoints require authentication."""
    client = TestClient(app)

    # POST - initiate
    response = client.post("/api/v1/debriefs", json={"meeting_id": "abc"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # PUT - submit
    response = client.put(
        "/api/v1/debriefs/debrief-123", json={"raw_notes": "Notes"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # GET - list
    response = client.get("/api/v1/debriefs")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # GET - pending
    response = client.get("/api/v1/debriefs/pending")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # GET - specific
    response = client.get("/api/v1/debriefs/debrief-123")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # GET - by meeting
    response = client.get("/api/v1/debriefs/meeting/meeting-abc")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# Validation Tests
# =============================================================================


def test_initiate_debrief_validates_meeting_id(test_client: TestClient) -> None:
    """Test POST /debriefs validates meeting_id is required."""
    response = test_client.post("/api/v1/debriefs", json={})

    # App returns 400 for validation errors via custom exception handler
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_submit_debrief_validates_raw_notes(test_client: TestClient) -> None:
    """Test PUT /debriefs/{id} validates raw_notes is required."""
    response = test_client.put("/api/v1/debriefs/debrief-123", json={})

    # App returns 400 for validation errors via custom exception handler
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_submit_debrief_validates_notes_length(test_client: TestClient) -> None:
    """Test PUT /debriefs/{id} validates notes length."""
    # Test empty notes (no need to mock service since validation happens before)
    response = test_client.put(
        "/api/v1/debriefs/debrief-123", json={"raw_notes": ""}
    )
    # App returns 400 for validation errors via custom exception handler
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Test notes too long (over 10000 chars)
    response = test_client.put(
        "/api/v1/debriefs/debrief-123", json={"raw_notes": "x" * 10001}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
