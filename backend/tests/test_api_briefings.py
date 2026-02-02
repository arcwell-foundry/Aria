"""Tests for briefing API routes."""

from datetime import date
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


def test_get_today_briefing_returns_briefing(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/today returns briefing."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.get_or_generate_briefing = AsyncMock(
            return_value={
                "summary": "Good morning! You have 3 meetings today.",
                "calendar": {"meeting_count": 3, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-02T10:00:00",
            }
        )

        response = test_client.get("/api/v1/briefings/today")

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["calendar"]["meeting_count"] == 3


def test_get_today_briefing_regenerates_when_flag_true(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/today?regenerate=true regenerates briefing."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.generate_briefing = AsyncMock(
            return_value={
                "summary": "Regenerated briefing",
                "calendar": {"meeting_count": 0, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-02T11:00:00",
            }
        )

        response = test_client.get("/api/v1/briefings/today?regenerate=true")

    assert response.status_code == 200
    mock_service.generate_briefing.assert_called_once_with("test-user-123")


def test_list_briefings_returns_recent_briefings(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings returns list of briefings."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.list_briefings = AsyncMock(
            return_value=[
                {
                    "id": "briefing-1",
                    "briefing_date": "2026-02-02",
                    "content": {"summary": "Today's briefing"},
                },
                {
                    "id": "briefing-2",
                    "briefing_date": "2026-02-01",
                    "content": {"summary": "Yesterday's briefing"},
                },
            ]
        )

        response = test_client.get("/api/v1/briefings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_briefings_respects_limit_parameter(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings?limit=5 respects limit."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.list_briefings = AsyncMock(return_value=[])

        response = test_client.get("/api/v1/briefings?limit=5")

    assert response.status_code == 200
    mock_service.list_briefings.assert_called_once_with("test-user-123", 5)


def test_get_briefing_by_date_returns_briefing(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/2026-02-01 returns specific briefing."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.get_briefing = AsyncMock(
            return_value={
                "id": "briefing-123",
                "briefing_date": "2026-02-01",
                "content": {"summary": "Briefing for Feb 1"},
            }
        )

        response = test_client.get("/api/v1/briefings/2026-02-01")

    assert response.status_code == 200
    data = response.json()
    assert data["briefing_date"] == "2026-02-01"


def test_get_briefing_by_date_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/2026-01-01 returns 404 when not found."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.get_briefing = AsyncMock(return_value=None)

        response = test_client.get("/api/v1/briefings/2026-01-01")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_briefing_creates_new_briefing(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/generate creates new briefing."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.generate_briefing = AsyncMock(
            return_value={
                "summary": "Newly generated briefing",
                "calendar": {"meeting_count": 1, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-02T12:00:00",
            }
        )

        response = test_client.post("/api/v1/briefings/generate")

    assert response.status_code == 200
    mock_service.generate_briefing.assert_called_once_with("test-user-123", None)


def test_generate_briefing_with_custom_date(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/generate with briefing_date creates briefing for that date."""
    with patch("src.api.routes.briefings.briefing_service") as mock_service:
        mock_service.generate_briefing = AsyncMock(
            return_value={
                "summary": "Briefing for custom date",
                "calendar": {"meeting_count": 0, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-02T12:00:00",
            }
        )

        response = test_client.post(
            "/api/v1/briefings/generate", json={"briefing_date": "2026-02-15"}
        )

    assert response.status_code == 200
    mock_service.generate_briefing.assert_called_once()


def test_briefings_endpoints_require_authentication() -> None:
    """Test all briefing endpoints require authentication."""
    client = TestClient(app)

    response = client.get("/api/v1/briefings/today")
    assert response.status_code == 401

    response = client.get("/api/v1/briefings")
    assert response.status_code == 401

    response = client.get("/api/v1/briefings/2026-02-01")
    assert response.status_code == 401

    response = client.post("/api/v1/briefings/generate")
    assert response.status_code == 401
