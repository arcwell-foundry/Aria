"""Tests for market signal API routes."""

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


def test_get_signals_returns_all_signals(test_client: TestClient) -> None:
    """Test GET /signals returns all signals."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "signal-1",
                    "user_id": "test-user-123",
                    "company_name": "Acme Corp",
                    "signal_type": "funding",
                    "headline": "Acme raises $50M",
                    "summary": None,
                    "source_url": None,
                    "source_name": None,
                    "relevance_score": 0.85,
                    "detected_at": "2026-02-02T10:00:00Z",
                    "read_at": None,
                    "linked_lead_id": None,
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/signals/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["company_name"] == "Acme Corp"


def test_get_signals_filters_unread_only(test_client: TestClient) -> None:
    """Test GET /signals with unread_only=true filters unread signals."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_is = MagicMock()
        mock_is.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-1", "read_at": None}]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.is_ = mock_is
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/signals/?unread_only=true")

    assert response.status_code == status.HTTP_200_OK


def test_get_unread_count_returns_count(test_client: TestClient) -> None:
    """Test GET /signals/unread/count returns unread count."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=5
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/signals/unread/count")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 5


def test_mark_signal_read_updates_read_at(test_client: TestClient) -> None:
    """Test POST /signals/{id}/read marks signal as read."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-123", "read_at": "2026-02-02T10:00:00Z"}]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.post("/api/v1/signals/signal-123/read")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["read_at"] is not None


def test_mark_all_read_updates_all_unread_signals(test_client: TestClient) -> None:
    """Test POST /signals/read-all marks all signals as read."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-1"}, {"id": "signal-2"}, {"id": "signal-3"}]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.post("/api/v1/signals/read-all")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["marked_read"] == 3


def test_dismiss_signal_sets_dismissed_at(test_client: TestClient) -> None:
    """Test POST /signals/{id}/dismiss dismisses a signal."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-123", "dismissed_at": "2026-02-02T10:00:00Z"}]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.post("/api/v1/signals/signal-123/dismiss")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["dismissed_at"] is not None


# Monitored Entities API Tests


def test_get_monitored_entities_returns_entities(test_client: TestClient) -> None:
    """Test GET /signals/monitored returns monitored entities."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "entity-1",
                    "user_id": "test-user-123",
                    "entity_type": "company",
                    "entity_name": "Acme Corp",
                    "monitoring_config": {},
                    "is_active": True,
                    "last_checked_at": None,
                    "created_at": "2026-02-01T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/signals/monitored")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["entity_name"] == "Acme Corp"


def test_add_monitored_entity_creates_entity(test_client: TestClient) -> None:
    """Test POST /signals/monitored creates a monitored entity."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "entity-123",
                    "user_id": "test-user-123",
                    "entity_type": "company",
                    "entity_name": "Acme Corp",
                    "monitoring_config": {"frequency": "daily"},
                    "is_active": True,
                    "last_checked_at": None,
                    "created_at": "2026-02-01T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.post(
            "/api/v1/signals/monitored",
            json={
                "entity_type": "company",
                "entity_name": "Acme Corp",
                "monitoring_config": {"frequency": "daily"},
            },
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["entity_name"] == "Acme Corp"
    assert data["monitoring_config"]["frequency"] == "daily"


def test_remove_monitored_entity_deactivates_entity(test_client: TestClient) -> None:
    """Test DELETE /signals/monitored/{id} deactivates an entity."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "entity-123", "is_active": False}]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.delete("/api/v1/signals/monitored/entity-123")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "removed"


def test_signals_endpoints_require_authentication() -> None:
    """Test all signal endpoints require authentication."""
    client = TestClient(app)

    response = client.get("/api/v1/signals/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/signals/unread/count")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/v1/signals/signal-123/read")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/v1/signals/read-all")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/v1/signals/signal-123/dismiss")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/signals/monitored")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/v1/signals/monitored")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.delete("/api/v1/signals/monitored/entity-123")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
