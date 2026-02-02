"""Tests for battle cards API routes.

These tests follow TDD principles - tests were written first, then implementation.
"""

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
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_user_profile() -> dict:
    """Create mock user profile with company_id."""
    return {
        "id": "test-user-123",
        "company_id": "company-abc",
        "role": "user",
    }


@pytest.fixture
def test_client(mock_current_user: MagicMock, mock_user_profile: dict) -> TestClient:
    """Create test client with mocked authentication."""
    from src.services.battle_card_service import BattleCardService

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    async def override_get_user_company_id() -> str:
        return mock_user_profile["company_id"]

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock get_user_company_id
    with patch("src.api.routes.battle_cards._get_user_company_id", return_value=mock_user_profile["company_id"]):
        client = TestClient(app)
        yield client

    app.dependency_overrides.clear()


class TestBattleCardsListEndpoint:
    """Tests for GET /api/v1/battlecards endpoint."""

    def test_list_battle_cards_requires_auth(self) -> None:
        """Test GET /api/v1/battlecards requires authentication."""
        client = TestClient(app)
        response = client.get("/api/v1/battlecards")

        assert response.status_code == 401

    def test_list_battle_cards_returns_empty_list(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards returns empty list when no cards exist."""
        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.list_battle_cards = AsyncMock(return_value=[])

            response = test_client.get("/api/v1/battlecards")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_battle_cards_returns_cards(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards returns list of cards."""
        mock_cards = [
            {
                "id": "card-1",
                "competitor_name": "Competitor A",
                "overview": "Test overview",
            },
            {
                "id": "card-2",
                "competitor_name": "Competitor B",
                "overview": "Another overview",
            },
        ]

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.list_battle_cards = AsyncMock(return_value=mock_cards)

            response = test_client.get("/api/v1/battlecards")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["competitor_name"] == "Competitor A"

    def test_list_battle_cards_with_search(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards?search=query filters results."""
        mock_cards = [
            {
                "id": "card-1",
                "competitor_name": "TechCorp",
            },
        ]

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.list_battle_cards = AsyncMock(return_value=mock_cards)

            response = test_client.get("/api/v1/battlecards?search=Tech")

        assert response.status_code == 200
        assert len(response.json()) == 1
        mock_service.list_battle_cards.assert_called_once()


class TestBattleCardsGetByCompetitor:
    """Tests for GET /api/v1/battlecards/{competitor_name} endpoint."""

    def test_get_battle_card_by_competitor_requires_auth(self) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} requires authentication."""
        client = TestClient(app)
        response = client.get("/api/v1/battlecards/Test%20Competitor")

        assert response.status_code == 401

    def test_get_battle_card_by_competitor_found(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} returns card when found."""
        mock_card = {
            "id": "card-1",
            "competitor_name": "Test Competitor",
            "overview": "Test overview",
            "strengths": ["Strong brand"],
        }

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.get_battle_card = AsyncMock(return_value=mock_card)

            response = test_client.get("/api/v1/battlecards/Test%20Competitor")

        assert response.status_code == 200
        data = response.json()
        assert data["competitor_name"] == "Test Competitor"

    def test_get_battle_card_by_competitor_not_found(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} returns 404 when not found."""
        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.get_battle_card = AsyncMock(return_value=None)

            response = test_client.get("/api/v1/battlecards/Unknown")

        assert response.status_code == 404


class TestBattleCardsCreate:
    """Tests for POST /api/v1/battlecards endpoint."""

    def test_create_battle_card_requires_auth(self) -> None:
        """Test POST /api/v1/battlecards requires authentication."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/battlecards",
            json={"competitor_name": "New Competitor"}
        )

        assert response.status_code == 401

    def test_create_battle_card_success(self, test_client: TestClient) -> None:
        """Test POST /api/v1/battlecards creates a new battle card."""
        mock_card = {
            "id": "card-new",
            "competitor_name": "New Competitor",
            "overview": None,
            "strengths": [],
            "weaknesses": [],
        }

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.create_battle_card = AsyncMock(return_value=mock_card)

            response = test_client.post(
                "/api/v1/battlecards",
                json={"competitor_name": "New Competitor"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "card-new"
        assert data["competitor_name"] == "New Competitor"

    def test_create_battle_card_with_all_fields(self, test_client: TestClient) -> None:
        """Test POST /api/v1/battlecards with all fields."""
        mock_card = {
            "id": "card-full",
            "competitor_name": "Full Competitor",
            "competitor_domain": "competitor.com",
            "overview": "A competitor",
            "strengths": ["Strong"],
            "weaknesses": ["Weak"],
            "pricing": {"starting_at": "$10k"},
            "differentiation": [],
            "objection_handlers": [],
        }

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.create_battle_card = AsyncMock(return_value=mock_card)

            response = test_client.post(
                "/api/v1/battlecards",
                json={
                    "competitor_name": "Full Competitor",
                    "competitor_domain": "competitor.com",
                    "overview": "A competitor",
                    "strengths": ["Strong"],
                    "weaknesses": ["Weak"],
                    "pricing": {"starting_at": "$10k"},
                }
            )

        assert response.status_code == 200


class TestBattleCardsUpdate:
    """Tests for PATCH /api/v1/battlecards/{card_id} endpoint."""

    def test_update_battle_card_requires_auth(self) -> None:
        """Test PATCH /api/v1/battlecards/{card_id} requires authentication."""
        client = TestClient(app)
        response = client.patch(
            "/api/v1/battlecards/card-123",
            json={"overview": "Updated"}
        )

        assert response.status_code == 401

    def test_update_battle_card_success(self, test_client: TestClient) -> None:
        """Test PATCH /api/v1/battlecards/{card_id} updates a battle card."""
        mock_card = {
            "id": "card-123",
            "competitor_name": "Test Competitor",
            "overview": "Updated overview",
        }

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.update_battle_card = AsyncMock(return_value=mock_card)

            response = test_client.patch(
                "/api/v1/battlecards/card-123",
                json={"overview": "Updated overview"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["overview"] == "Updated overview"


class TestBattleCardsDelete:
    """Tests for DELETE /api/v1/battlecards/{card_id} endpoint."""

    def test_delete_battle_card_requires_auth(self) -> None:
        """Test DELETE /api/v1/battlecards/{card_id} requires authentication."""
        client = TestClient(app)
        response = client.delete("/api/v1/battlecards/card-123")

        assert response.status_code == 401

    def test_delete_battle_card_success(self, test_client: TestClient) -> None:
        """Test DELETE /api/v1/battlecards/{card_id} deletes a battle card."""
        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.delete_battle_card = AsyncMock(return_value=True)

            response = test_client.delete("/api/v1/battlecards/card-123")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestBattleCardsHistory:
    """Tests for GET /api/v1/battlecards/{card_id}/history endpoint."""

    def test_get_battle_card_history_requires_auth(self) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history requires authentication."""
        client = TestClient(app)
        response = client.get("/api/v1/battlecards/card-123/history")

        assert response.status_code == 401

    def test_get_battle_card_history_success(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history returns change history."""
        mock_history = [
            {
                "id": "change-1",
                "change_type": "overview_updated",
                "detected_at": "2024-01-01T00:00:00Z",
            }
        ]

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.get_card_history = AsyncMock(return_value=mock_history)

            response = test_client.get("/api/v1/battlecards/card-123/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["change_type"] == "overview_updated"

    def test_get_battle_card_history_with_limit(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history?limit=10 applies limit."""
        mock_history = []

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.get_card_history = AsyncMock(return_value=mock_history)

            response = test_client.get("/api/v1/battlecards/card-123/history?limit=10")

        assert response.status_code == 200
        mock_service.get_card_history.assert_called_with("card-123", 10)


class TestBattleCardsObjectionHandler:
    """Tests for POST /api/v1/battlecards/{card_id}/objections endpoint."""

    def test_add_objection_handler_requires_auth(self) -> None:
        """Test POST /api/v1/battlecards/{card_id}/objections requires authentication."""
        client = TestClient(app)
        response = test_client.post(
            "/api/v1/battlecards/card-123/objections",
            json={"objection": "Too expensive", "response": "We offer value"}
        )

        assert response.status_code == 401

    def test_add_objection_handler_success(self, test_client: TestClient) -> None:
        """Test POST /api/v1/battlecards/{card_id}/objections adds objection handler."""
        mock_card = {
            "id": "card-123",
            "objection_handlers": [
                {"objection": "Old", "response": "Old response"},
                {"objection": "Too expensive", "response": "We offer value"},
            ],
        }

        with patch("src.api.routes.battle_cards.service") as mock_service:
            mock_service.add_objection_handler = AsyncMock(return_value=mock_card)

            response = test_client.post(
                "/api/v1/battlecards/card-123/objections",
                json={"objection": "Too expensive", "response": "We offer value"}
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["objection_handlers"]) == 2
