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
    """Test GET /api/v1/briefings/today returns existing briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.LLMClient"
    ) as mock_llm_class:
        # Setup DB mock — return an existing briefing
        mock_db = MagicMock()
        existing_briefing = {
            "id": "briefing-123",
            "user_id": "test-user-123",
            "briefing_date": date.today().isoformat(),
            "content": {
                "summary": "Good morning! You have 3 meetings today.",
                "calendar": {"meeting_count": 0, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-12T10:00:00+00:00",
            },
        }
        # get_briefing uses .eq().eq().order().limit().execute() chain
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[existing_briefing]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/briefings/today")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["briefing"]["summary"] == "Good morning! You have 3 meetings today."
    assert data["briefing"]["calendar"]["meeting_count"] == 0


def test_get_today_briefing_regenerates_when_flag_true(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/today?regenerate=true regenerates briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.LLMClient"
    ) as mock_llm_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.generate_response = AsyncMock(
            return_value="Regenerated briefing"
        )

        response = test_client.get("/api/v1/briefings/today?regenerate=true")

    assert response.status_code == 200


def test_list_briefings_returns_recent_briefings(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings returns list of briefings."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        expected_briefings = [
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
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=expected_briefings
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/briefings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_briefings_respects_limit_parameter(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings?limit=5 respects limit."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/briefings?limit=5")

    assert response.status_code == 200


def test_get_briefing_by_date_returns_briefing(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/2026-02-01 returns specific briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        expected_briefing = {
            "id": "briefing-123",
            "user_id": "test-user-123",
            "briefing_date": "2026-02-01",
            "content": {
                "summary": "Briefing for Feb 1",
                "calendar": {"meeting_count": 0, "key_meetings": []},
                "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
                "signals": {
                    "company_news": [],
                    "market_trends": [],
                    "competitive_intel": [],
                },
                "tasks": {"overdue": [], "due_today": []},
                "generated_at": "2026-02-01T10:00:00",
            },
        }
        # Setup DB mock — get_briefing uses .eq().eq().order().limit().execute()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[expected_briefing]
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/briefings/2026-02-01")

    assert response.status_code == 200
    data = response.json()
    assert data["briefing_date"] == "2026-02-01"


def test_get_briefing_by_date_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /api/v1/briefings/2026-01-01 returns 404 when not found."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/briefings/2026-01-01")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_briefing_creates_new_briefing(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/generate creates new briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.LLMClient"
    ) as mock_llm_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.generate_response = AsyncMock(
            return_value="Newly generated briefing"
        )

        response = test_client.post("/api/v1/briefings/generate")

    assert response.status_code == 200


def test_generate_briefing_with_custom_date(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/generate with briefing_date creates briefing for that date."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.LLMClient"
    ) as mock_llm_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.generate_response = AsyncMock(
            return_value="Briefing for custom date"
        )

        response = test_client.post(
            "/api/v1/briefings/generate", json={"briefing_date": "2026-02-15"}
        )

    assert response.status_code == 200


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

    response = client.post("/api/v1/briefings/regenerate")
    assert response.status_code == 401


def test_regenerate_briefing_creates_new_briefing(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/regenerate creates new briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.LLMClient"
    ) as mock_llm_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_class.return_value.generate_response = AsyncMock(
            return_value="Regenerated briefing"
        )

        response = test_client.post("/api/v1/briefings/regenerate")

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
