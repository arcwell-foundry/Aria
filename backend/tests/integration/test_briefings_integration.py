"""Integration tests for briefings API endpoints.

Tests the full briefing flow including:
- Generating briefings when none exists
- Returning existing briefings
- Regenerating briefings with fresh data
- Listing recent briefings
- Getting briefings by date
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "integration-test-user-123"
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


@pytest.fixture
def mock_briefing_content() -> dict[str, Any]:
    """Create mock briefing content."""
    return {
        "summary": "Good morning! You have 3 meetings today with high-priority leads.",
        "calendar": {
            "meeting_count": 3,
            "key_meetings": [
                {"title": "Discovery Call - Acme Corp", "time": "10:00 AM"},
                {"title": "Demo - BigCorp Inc", "time": "2:00 PM"},
            ],
        },
        "leads": {
            "hot_leads": [
                {"name": "Acme Corp", "stage": "negotiation", "value": 150000}
            ],
            "needs_attention": [],
            "recently_active": [],
        },
        "signals": {
            "company_news": [
                {"company": "Acme Corp", "headline": "Raises $50M Series C"}
            ],
            "market_trends": [],
            "competitive_intel": [],
        },
        "tasks": {
            "overdue": [],
            "due_today": [
                {"title": "Follow up with John at Acme Corp"}
            ],
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create mock database client."""
    return MagicMock()


@pytest.mark.integration
class TestBriefingsIntegration:
    """Integration tests for the briefings API flow."""

    def test_get_today_briefing_returns_not_generated_when_missing(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test that GET /briefings/today returns not_generated status if none exists."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()
            # No existing briefing
            # get_briefing uses .eq().eq().order().limit().execute()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            mock_db_class.get_client.return_value = mock_db

            response = test_client.get("/api/v1/briefings/today")

            assert response.status_code == 200
            data = response.json()

            # Verify not_generated status when no briefing exists
            assert data["status"] == "not_generated"
            assert data["briefing"] is None

    def test_get_today_briefing_returns_existing(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test that GET /briefings/today returns existing briefing without regenerating."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()

            # Existing briefing in DB
            existing_briefing = {
                "id": "briefing-existing",
                "user_id": "integration-test-user-123",
                "briefing_date": datetime.now(UTC).date().isoformat(),
                "content": mock_briefing_content,
            }
            # get_briefing uses .eq().eq().order().limit().execute() and returns list
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[existing_briefing]
            )
            mock_db_class.get_client.return_value = mock_db

            # LLM should NOT be called when returning existing briefing
            mock_llm_class.return_value.generate_response = AsyncMock(
                return_value="Should not be called"
            )

            response = test_client.get("/api/v1/briefings/today")

            assert response.status_code == 200
            data = response.json()

            # Verify the existing briefing content is returned
            assert data["status"] == "ready"
            assert data["briefing"]["summary"] == mock_briefing_content["summary"]
            assert data["briefing"]["generated_at"] == mock_briefing_content["generated_at"]

    def test_regenerate_briefing_creates_fresh_content(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test that regenerate=true creates a fresh briefing."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
                data=[{"id": "briefing-regenerated"}]
            )
            mock_db_class.get_client.return_value = mock_db

            # Setup LLM mock with different summary
            mock_llm_class.return_value.generate_response = AsyncMock(
                return_value="Regenerated briefing with fresh data"
            )

            response = test_client.get("/api/v1/briefings/today?regenerate=true")

            assert response.status_code == 200
            data = response.json()

            # Verify briefing was generated (LLM was called)
            assert mock_llm_class.return_value.generate_response.called
            assert data["status"] == "ready"
            assert "summary" in data["briefing"]

    def test_list_briefings_returns_recent(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test listing recent briefings."""
        with patch("src.services.briefing.SupabaseClient") as mock_db_class:
            mock_db = MagicMock()

            expected_briefings = [
                {
                    "id": "briefing-1",
                    "briefing_date": "2026-02-03",
                    "content": mock_briefing_content,
                },
                {
                    "id": "briefing-2",
                    "briefing_date": "2026-02-02",
                    "content": {**mock_briefing_content, "summary": "Yesterday's briefing"},
                },
                {
                    "id": "briefing-3",
                    "briefing_date": "2026-02-01",
                    "content": {**mock_briefing_content, "summary": "Older briefing"},
                },
            ]
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=expected_briefings
            )
            mock_db_class.get_client.return_value = mock_db

            response = test_client.get("/api/v1/briefings")

            assert response.status_code == 200
            data = response.json()

            assert isinstance(data, list)
            assert len(data) == 3
            assert data[0]["briefing_date"] == "2026-02-03"
            assert data[1]["briefing_date"] == "2026-02-02"

    def test_list_briefings_respects_limit(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test that list briefings respects the limit parameter."""
        with patch("src.services.briefing.SupabaseClient") as mock_db_class:
            mock_db = MagicMock()

            # Return limited number of briefings
            limited_briefings = [
                {
                    "id": "briefing-1",
                    "briefing_date": "2026-02-03",
                    "content": mock_briefing_content,
                },
            ]
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=limited_briefings
            )
            mock_db_class.get_client.return_value = mock_db

            response = test_client.get("/api/v1/briefings?limit=1")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1

    def test_get_briefing_by_date_returns_briefing(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test getting a briefing by specific date."""
        with patch("src.services.briefing.SupabaseClient") as mock_db_class:
            mock_db = MagicMock()

            expected_briefing = {
                "id": "briefing-specific-date",
                "user_id": "integration-test-user-123",
                "briefing_date": "2026-02-01",
                "content": mock_briefing_content,
            }
            # get_briefing uses .eq().eq().order().limit().execute() and returns list
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[expected_briefing]
            )
            mock_db_class.get_client.return_value = mock_db

            response = test_client.get("/api/v1/briefings/2026-02-01")

            assert response.status_code == 200
            data = response.json()
            assert data["briefing_date"] == "2026-02-01"
            assert data["id"] == "briefing-specific-date"

    def test_get_briefing_by_date_not_found(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that getting a non-existent date returns 404."""
        with patch("src.services.briefing.SupabaseClient") as mock_db_class:
            mock_db = MagicMock()

            # No briefing found
            # get_briefing uses .eq().eq().order().limit().execute()
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            mock_db_class.get_client.return_value = mock_db

            response = test_client.get("/api/v1/briefings/2020-01-01")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_post_generate_briefing_creates_new(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test POST /briefings/generate creates a new briefing."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
                data=[{"id": "briefing-generated"}]
            )
            mock_db_class.get_client.return_value = mock_db

            # Setup LLM mock
            mock_llm_class.return_value.generate_response = AsyncMock(
                return_value="Newly generated briefing content"
            )

            response = test_client.post("/api/v1/briefings/generate")

            assert response.status_code == 200
            data = response.json()
            assert "summary" in data
            assert "generated_at" in data

    def test_post_regenerate_briefing_forces_new_generation(
        self,
        test_client: TestClient,
    ) -> None:
        """Test POST /briefings/regenerate forces new briefing generation."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()
            mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
                data=[{"id": "briefing-regenerated"}]
            )
            mock_db_class.get_client.return_value = mock_db

            # Setup LLM mock
            mock_llm_class.return_value.generate_response = AsyncMock(
                return_value="Regenerated briefing content"
            )

            response = test_client.post("/api/v1/briefings/regenerate")

            assert response.status_code == 200
            # Verify LLM was called (forced regeneration)
            assert mock_llm_class.return_value.generate_response.called

    def test_briefings_endpoints_require_authentication(self) -> None:
        """Test all briefing endpoints require authentication."""
        # Create client without auth override
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/v1/briefings/today"),
            ("GET", "/api/v1/briefings"),
            ("GET", "/api/v1/briefings/2026-02-01"),
            ("POST", "/api/v1/briefings/generate"),
            ("POST", "/api/v1/briefings/regenerate"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)

            assert response.status_code == 401, f"{method} {endpoint} should require auth"


@pytest.mark.integration
class TestBriefingFullFlow:
    """Test complete end-to-end briefing flows."""

    def test_full_briefing_lifecycle(
        self,
        test_client: TestClient,
        mock_briefing_content: dict[str, Any],
    ) -> None:
        """Test full briefing lifecycle: generate -> retrieve -> list -> regenerate."""
        with (
            patch("src.services.briefing.SupabaseClient") as mock_db_class,
            patch("src.services.briefing.LLMClient") as mock_llm_class,
        ):
            mock_db = MagicMock()
            mock_db_class.get_client.return_value = mock_db

            # Track stored briefings
            stored_briefings: list[dict[str, Any]] = []
            today = datetime.now(UTC).date().isoformat()

            # Initial check - no briefing exists
            # get_briefing uses .eq().eq().order().limit().execute() and returns list
            def mock_select_execute() -> MagicMock:
                matching = [b for b in stored_briefings if b["briefing_date"] == today]
                return MagicMock(data=matching if matching else [])

            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_select_execute

            # Upsert stores the briefing
            def mock_upsert(data: dict[str, Any]) -> MagicMock:
                briefing = {
                    "id": f"briefing-{len(stored_briefings) + 1}",
                    "user_id": "integration-test-user-123",
                    "briefing_date": today,
                    "content": mock_briefing_content,
                }
                # Replace existing or add new
                stored_briefings[:] = [b for b in stored_briefings if b["briefing_date"] != today]
                stored_briefings.append(briefing)
                mock_chain = MagicMock()
                mock_chain.execute.return_value = MagicMock(data=[briefing])
                return mock_chain

            mock_db.table.return_value.upsert = mock_upsert

            # List returns all stored briefings
            def mock_list_execute() -> MagicMock:
                return MagicMock(data=stored_briefings)

            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_list_execute

            # Setup LLM mock
            mock_llm_class.return_value.generate_response = AsyncMock(
                return_value=mock_briefing_content["summary"]
            )

            # Step 1: Check — no briefing exists yet
            response1 = test_client.get("/api/v1/briefings/today")
            assert response1.status_code == 200
            initial_data = response1.json()
            assert initial_data["status"] == "not_generated"
            assert initial_data["briefing"] is None

            # Step 2: Generate initial briefing via regenerate flag
            response2 = test_client.get("/api/v1/briefings/today?regenerate=true")
            assert response2.status_code == 200
            generated_data = response2.json()
            assert generated_data["status"] == "ready"
            assert "summary" in generated_data["briefing"]

            # Step 3: Retrieve (should return existing)
            response3 = test_client.get("/api/v1/briefings/today")
            assert response3.status_code == 200
            existing_data = response3.json()
            assert existing_data["status"] == "ready"

            # Step 4: List briefings
            response4 = test_client.get("/api/v1/briefings")
            assert response4.status_code == 200
            list_data = response4.json()
            assert len(list_data) >= 1

            # Step 5: Regenerate
            response5 = test_client.get("/api/v1/briefings/today?regenerate=true")
            assert response5.status_code == 200
            regenerated_data = response5.json()
            assert regenerated_data["status"] == "ready"
            assert "summary" in regenerated_data["briefing"]

            # Verify LLM was called for both generations
            assert mock_llm_class.return_value.generate_response.call_count >= 2
