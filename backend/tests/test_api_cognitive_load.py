"""Tests for cognitive load API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app
from src.models.cognitive_load import CognitiveLoadState, LoadLevel


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


def test_get_cognitive_load_requires_auth() -> None:
    """GET /api/v1/user/cognitive-load should require authentication."""
    client = TestClient(app)
    response = client.get("/api/v1/user/cognitive-load")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_cognitive_load_history_requires_auth() -> None:
    """GET /api/v1/user/cognitive-load/history should require authentication."""
    client = TestClient(app)
    response = client.get("/api/v1/user/cognitive-load/history")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_cognitive_load_returns_state(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load should return current load state."""
    mock_state = CognitiveLoadState(
        level=LoadLevel.MEDIUM,
        score=0.45,
        factors={
            "message_brevity": 0.5,
            "typo_rate": 0.2,
            "message_velocity": 0.3,
            "calendar_density": 0.6,
            "time_of_day": 0.4,
        },
        recommendation="balanced",
    )

    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_current_load = AsyncMock(return_value=mock_state)
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["level"] == "medium"
    assert data["score"] == 0.45
    assert data["recommendation"] == "balanced"
    assert "factors" in data


def test_get_cognitive_load_returns_default_when_no_data(
    test_client: TestClient,
) -> None:
    """GET /api/v1/user/cognitive-load should return default state when no data exists."""
    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_current_load = AsyncMock(return_value=None)
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["level"] == "low"
    assert data["score"] == 0.0
    assert data["recommendation"] == "detailed"


def test_get_cognitive_load_history_returns_snapshots(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load/history should return snapshots."""
    mock_history = [
        {
            "id": "snap-1",
            "user_id": "test-user-123",
            "load_level": "high",
            "load_score": 0.65,
            "factors": {"message_brevity": 0.8},
            "session_id": None,
            "measured_at": "2026-02-03T12:00:00Z",
        },
        {
            "id": "snap-2",
            "user_id": "test-user-123",
            "load_level": "medium",
            "load_score": 0.45,
            "factors": {"message_brevity": 0.5},
            "session_id": None,
            "measured_at": "2026-02-03T11:00:00Z",
        },
    ]

    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_load_history = AsyncMock(return_value=mock_history)
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load/history")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["snapshots"]) == 2
    assert data["snapshots"][0]["load_level"] == "high"
    assert data["average_score"] is not None


def test_get_cognitive_load_history_with_limit(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load/history should respect limit parameter."""
    mock_history = [
        {
            "id": "snap-1",
            "user_id": "test-user-123",
            "load_level": "medium",
            "load_score": 0.45,
            "factors": {},
            "session_id": None,
            "measured_at": "2026-02-03T12:00:00Z",
        },
    ]

    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_load_history = AsyncMock(return_value=mock_history)
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load/history?limit=5")

    assert response.status_code == status.HTTP_200_OK
    # Verify the monitor was called with correct limit
    mock_monitor.get_load_history.assert_called_once_with(
        user_id="test-user-123", limit=5
    )


def test_get_cognitive_load_history_empty(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load/history should handle empty history."""
    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_load_history = AsyncMock(return_value=[])
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load/history")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["snapshots"] == []
    assert data["average_score"] is None
    assert data["trend"] is None


def test_get_cognitive_load_history_trend_calculation(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load/history should calculate trend correctly."""
    # Create history with improving trend (recent scores lower than older)
    mock_history = [
        {
            "id": "1",
            "user_id": "u",
            "load_level": "low",
            "load_score": 0.2,
            "factors": {},
            "session_id": None,
            "measured_at": "2026-02-03T12:00:00Z",
        },
        {
            "id": "2",
            "user_id": "u",
            "load_level": "low",
            "load_score": 0.3,
            "factors": {},
            "session_id": None,
            "measured_at": "2026-02-03T11:00:00Z",
        },
        {
            "id": "3",
            "user_id": "u",
            "load_level": "medium",
            "load_score": 0.5,
            "factors": {},
            "session_id": None,
            "measured_at": "2026-02-03T10:00:00Z",
        },
        {
            "id": "4",
            "user_id": "u",
            "load_level": "high",
            "load_score": 0.6,
            "factors": {},
            "session_id": None,
            "measured_at": "2026-02-03T09:00:00Z",
        },
    ]

    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_load_history = AsyncMock(return_value=mock_history)
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load/history")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["trend"] == "improving"


def test_get_cognitive_load_service_error(test_client: TestClient) -> None:
    """GET /api/v1/user/cognitive-load should handle service errors gracefully."""
    with (
        patch("src.api.routes.cognitive_load.get_supabase_client") as mock_get_db,
        patch(
            "src.api.routes.cognitive_load.CognitiveLoadMonitor"
        ) as mock_monitor_class,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_monitor = MagicMock()
        mock_monitor.get_current_load = AsyncMock(side_effect=Exception("DB error"))
        mock_monitor_class.return_value = mock_monitor

        response = test_client.get("/api/v1/user/cognitive-load")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert "temporarily unavailable" in data["detail"]
