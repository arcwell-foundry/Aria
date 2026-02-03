"""Tests for drafts API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create a mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create a test client with authentication override."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_draft() -> dict:
    """Create a sample draft for testing."""
    return {
        "id": "draft-123",
        "user_id": "test-user-123",
        "recipient_email": "test@example.com",
        "recipient_name": "Test User",
        "subject": "Hello",
        "body": "Hi there!",
        "purpose": "intro",
        "tone": "friendly",
        "context": {},
        "lead_memory_id": None,
        "style_match_score": 0.85,
        "status": "draft",
        "sent_at": None,
        "error_message": None,
        "created_at": "2026-02-03T10:00:00Z",
        "updated_at": "2026-02-03T10:00:00Z",
    }


def test_create_draft_success(test_client: TestClient, sample_draft: dict) -> None:
    """Test successful draft creation."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.create_draft = AsyncMock(return_value=sample_draft)
        mock_service_getter.return_value = mock_service

        response = test_client.post(
            "/api/v1/drafts/email",
            json={"recipient_email": "test@example.com", "purpose": "intro"},
        )

    assert response.status_code == 201
    assert response.json()["id"] == "draft-123"


def test_create_draft_with_all_fields(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test draft creation with all optional fields."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.create_draft = AsyncMock(return_value=sample_draft)
        mock_service_getter.return_value = mock_service

        response = test_client.post(
            "/api/v1/drafts/email",
            json={
                "recipient_email": "test@example.com",
                "recipient_name": "Test User",
                "subject_hint": "Introduction",
                "purpose": "intro",
                "context": "Met at conference",
                "tone": "formal",
                "lead_memory_id": "lead-456",
            },
        )

    assert response.status_code == 201
    mock_service.create_draft.assert_called_once()
    call_kwargs = mock_service.create_draft.call_args.kwargs
    assert call_kwargs["recipient_email"] == "test@example.com"
    assert call_kwargs["recipient_name"] == "Test User"


def test_list_drafts_returns_drafts(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test listing drafts."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.list_drafts = AsyncMock(return_value=[sample_draft])
        mock_service_getter.return_value = mock_service

        response = test_client.get("/api/v1/drafts")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_drafts_with_limit(test_client: TestClient, sample_draft: dict) -> None:
    """Test listing drafts with limit parameter."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.list_drafts = AsyncMock(return_value=[sample_draft])
        mock_service_getter.return_value = mock_service

        response = test_client.get("/api/v1/drafts?limit=10")

    assert response.status_code == 200
    mock_service.list_drafts.assert_called_once_with("test-user-123", 10, None)


def test_list_drafts_with_status_filter(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test listing drafts with status filter."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.list_drafts = AsyncMock(return_value=[sample_draft])
        mock_service_getter.return_value = mock_service

        response = test_client.get("/api/v1/drafts?status=draft")

    assert response.status_code == 200
    mock_service.list_drafts.assert_called_once_with("test-user-123", 50, "draft")


def test_get_draft_returns_draft(test_client: TestClient, sample_draft: dict) -> None:
    """Test getting a specific draft."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.get_draft = AsyncMock(return_value=sample_draft)
        mock_service_getter.return_value = mock_service

        response = test_client.get("/api/v1/drafts/draft-123")

    assert response.status_code == 200
    assert response.json()["id"] == "draft-123"


def test_get_draft_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test getting a non-existent draft returns 404."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.get_draft = AsyncMock(return_value=None)
        mock_service_getter.return_value = mock_service

        response = test_client.get("/api/v1/drafts/nonexistent")

    assert response.status_code == 404


def test_update_draft_updates_fields(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test updating a draft."""
    updated = sample_draft.copy()
    updated["subject"] = "Updated Subject"

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.update_draft = AsyncMock(return_value=updated)
        mock_service_getter.return_value = mock_service

        response = test_client.put(
            "/api/v1/drafts/draft-123", json={"subject": "Updated Subject"}
        )

    assert response.status_code == 200
    assert response.json()["subject"] == "Updated Subject"


def test_update_draft_with_multiple_fields(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test updating multiple fields at once."""
    updated = sample_draft.copy()
    updated["subject"] = "New Subject"
    updated["body"] = "New body content"

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.update_draft = AsyncMock(return_value=updated)
        mock_service_getter.return_value = mock_service

        response = test_client.put(
            "/api/v1/drafts/draft-123",
            json={"subject": "New Subject", "body": "New body content"},
        )

    assert response.status_code == 200


def test_delete_draft_removes_draft(test_client: TestClient) -> None:
    """Test deleting a draft."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.delete_draft = AsyncMock(return_value=True)
        mock_service_getter.return_value = mock_service

        response = test_client.delete("/api/v1/drafts/draft-123")

    assert response.status_code == 200
    assert response.json()["message"] == "Draft deleted successfully"


def test_delete_draft_returns_500_on_failure(test_client: TestClient) -> None:
    """Test delete failure returns 500."""
    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.delete_draft = AsyncMock(return_value=False)
        mock_service_getter.return_value = mock_service

        response = test_client.delete("/api/v1/drafts/draft-123")

    assert response.status_code == 500


def test_regenerate_draft_regenerates(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test regenerating a draft."""
    regenerated = sample_draft.copy()
    regenerated["body"] = "Regenerated body"

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.regenerate_draft = AsyncMock(return_value=regenerated)
        mock_service_getter.return_value = mock_service

        response = test_client.post("/api/v1/drafts/draft-123/regenerate")

    assert response.status_code == 200


def test_regenerate_draft_with_new_tone(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test regenerating with a new tone."""
    regenerated = sample_draft.copy()
    regenerated["tone"] = "formal"

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.regenerate_draft = AsyncMock(return_value=regenerated)
        mock_service_getter.return_value = mock_service

        response = test_client.post(
            "/api/v1/drafts/draft-123/regenerate", json={"tone": "formal"}
        )

    assert response.status_code == 200
    mock_service.regenerate_draft.assert_called_once()


def test_regenerate_draft_with_additional_context(
    test_client: TestClient, sample_draft: dict
) -> None:
    """Test regenerating with additional context."""
    regenerated = sample_draft.copy()

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.regenerate_draft = AsyncMock(return_value=regenerated)
        mock_service_getter.return_value = mock_service

        response = test_client.post(
            "/api/v1/drafts/draft-123/regenerate",
            json={"additional_context": "Make it more persuasive"},
        )

    assert response.status_code == 200


def test_send_draft_sends_email(test_client: TestClient, sample_draft: dict) -> None:
    """Test sending a draft."""
    sent = sample_draft.copy()
    sent["status"] = "sent"
    sent["sent_at"] = "2026-02-03T11:00:00Z"

    with patch("src.api.routes.drafts.get_draft_service") as mock_service_getter:
        mock_service = AsyncMock()
        mock_service.send_draft = AsyncMock(return_value=sent)
        mock_service_getter.return_value = mock_service

        response = test_client.post("/api/v1/drafts/draft-123/send")

    assert response.status_code == 200
    assert response.json()["status"] == "sent"


def test_drafts_endpoints_require_authentication() -> None:
    """Test all endpoints require authentication."""
    client = TestClient(app)

    # Clear any overrides
    app.dependency_overrides.clear()

    # Test create endpoint
    assert (
        client.post(
            "/api/v1/drafts/email",
            json={"recipient_email": "t@t.com", "purpose": "intro"},
        ).status_code
        == 401
    )

    # Test list endpoint
    assert client.get("/api/v1/drafts").status_code == 401

    # Test get endpoint
    assert client.get("/api/v1/drafts/draft-123").status_code == 401

    # Test update endpoint
    assert (
        client.put("/api/v1/drafts/draft-123", json={"subject": "New"}).status_code
        == 401
    )

    # Test delete endpoint
    assert client.delete("/api/v1/drafts/draft-123").status_code == 401

    # Test regenerate endpoint
    assert client.post("/api/v1/drafts/draft-123/regenerate").status_code == 401

    # Test send endpoint
    assert client.post("/api/v1/drafts/draft-123/send").status_code == 401
