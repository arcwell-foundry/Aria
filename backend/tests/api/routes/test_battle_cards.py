"""Tests for battle cards API routes.

These tests follow TDD principles - tests were written first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from src.api.routes import battle_cards


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(battle_cards.router, prefix="/api/v1")
    return app


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
    from src.api.deps import get_current_user

    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

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
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/battlecards")
        assert response.status_code == 401

    def test_list_battle_cards_returns_empty_list(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards returns empty list when no cards exist."""
        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_battle_cards = AsyncMock(return_value=[])
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_battle_cards_returns_cards(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards returns list of cards."""
        mock_cards = [
            {"id": "card-1", "competitor_name": "Competitor A"},
            {"id": "card-2", "competitor_name": "Competitor B"},
        ]

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_battle_cards = AsyncMock(return_value=mock_cards)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_battle_cards_with_search(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards?search=query filters results."""
        mock_cards = [{"id": "card-1", "competitor_name": "TechCorp"}]

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_battle_cards = AsyncMock(return_value=mock_cards)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards?search=Tech")

        assert response.status_code == 200
        assert len(response.json()) == 1


class TestBattleCardsGetByCompetitor:
    """Tests for GET /api/v1/battlecards/{competitor_name} endpoint."""

    def test_get_battle_card_by_competitor_requires_auth(self) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/battlecards/Test%20Competitor")
        assert response.status_code == 401

    def test_get_battle_card_by_competitor_found(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} returns card when found."""
        mock_card = {"id": "card-1", "competitor_name": "Test Competitor"}

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_battle_card = AsyncMock(return_value=mock_card)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards/Test%20Competitor")

        assert response.status_code == 200
        assert response.json()["competitor_name"] == "Test Competitor"

    def test_get_battle_card_by_competitor_not_found(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{competitor_name} returns 404 when not found."""
        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_battle_card = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards/Unknown")

        assert response.status_code == 404


class TestBattleCardsCreate:
    """Tests for POST /api/v1/battlecards endpoint."""

    def test_create_battle_card_requires_auth(self) -> None:
        """Test POST /api/v1/battlecards requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post("/api/v1/battlecards", json={"competitor_name": "New"})
        assert response.status_code == 401

    def test_create_battle_card_success(self, test_client: TestClient) -> None:
        """Test POST /api/v1/battlecards creates a new battle card."""
        mock_card = {"id": "card-new", "competitor_name": "New Competitor"}

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_battle_card = AsyncMock(return_value=mock_card)
            mock_get_service.return_value = mock_service

            response = test_client.post(
                "/api/v1/battlecards",
                json={"competitor_name": "New Competitor"}
            )

        assert response.status_code == 200
        assert response.json()["id"] == "card-new"


class TestBattleCardsUpdate:
    """Tests for PATCH /api/v1/battlecards/{card_id} endpoint."""

    def test_update_battle_card_requires_auth(self) -> None:
        """Test PATCH /api/v1/battlecards/{card_id} requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.patch("/api/v1/battlecards/card-123", json={"overview": "Updated"})
        assert response.status_code == 401

    def test_update_battle_card_success(self, test_client: TestClient) -> None:
        """Test PATCH /api/v1/battlecards/{card_id} updates a battle card."""
        mock_card = {"id": "card-123", "overview": "Updated overview"}

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update_battle_card = AsyncMock(return_value=mock_card)
            mock_get_service.return_value = mock_service

            response = test_client.patch(
                "/api/v1/battlecards/card-123",
                json={"overview": "Updated overview"}
            )

        assert response.status_code == 200
        assert response.json()["overview"] == "Updated overview"


class TestBattleCardsDelete:
    """Tests for DELETE /api/v1/battlecards/{card_id} endpoint."""

    def test_delete_battle_card_requires_auth(self) -> None:
        """Test DELETE /api/v1/battlecards/{card_id} requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.delete("/api/v1/battlecards/card-123")
        assert response.status_code == 401

    def test_delete_battle_card_success(self, test_client: TestClient) -> None:
        """Test DELETE /api/v1/battlecards/{card_id} deletes a battle card."""
        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.delete_battle_card = AsyncMock(return_value=True)
            mock_get_service.return_value = mock_service

            response = test_client.delete("/api/v1/battlecards/card-123")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestBattleCardsHistory:
    """Tests for GET /api/v1/battlecards/{card_id}/history endpoint."""

    def test_get_battle_card_history_requires_auth(self) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/battlecards/card-123/history")
        assert response.status_code == 401

    def test_get_battle_card_history_success(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history returns change history."""
        mock_history = [{"id": "change-1", "change_type": "overview_updated"}]

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_card_history = AsyncMock(return_value=mock_history)
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards/card-123/history")

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_battle_card_history_with_limit(self, test_client: TestClient) -> None:
        """Test GET /api/v1/battlecards/{card_id}/history?limit=10 applies limit."""
        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_card_history = AsyncMock(return_value=[])
            mock_get_service.return_value = mock_service

            response = test_client.get("/api/v1/battlecards/card-123/history?limit=10")

        assert response.status_code == 200
        mock_service.get_card_history.assert_called_with("card-123", 10)


class TestBattleCardsObjectionHandler:
    """Tests for POST /api/v1/battlecards/{card_id}/objections endpoint."""

    def test_add_objection_handler_requires_auth(self) -> None:
        """Test POST /api/v1/battlecards/{card_id}/objections requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/battlecards/card-123/objections?objection=Too+expensive&response=We+offer+value"
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

        with patch("src.api.routes.battle_cards._get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.add_objection_handler = AsyncMock(return_value=mock_card)
            mock_get_service.return_value = mock_service

            response = test_client.post(
                "/api/v1/battlecards/card-123/objections?objection=Too+expensive&response=We+offer+value"
            )

        assert response.status_code == 200
        assert len(response.json()["objection_handlers"]) == 2
