"""Tests for battle card service.

These tests follow TDD principles - tests were written first, then implementation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBattleCardCreate:
    """Tests for BattleCardCreate model."""

    def test_battle_card_create_with_required_fields(self) -> None:
        """Test creating BattleCardCreate with only required fields."""
        from src.services.battle_card_service import BattleCardCreate

        data = BattleCardCreate(competitor_name="Competitor Inc")

        assert data.competitor_name == "Competitor Inc"
        assert data.competitor_domain is None
        assert data.overview is None
        assert data.strengths == []
        assert data.weaknesses == []
        assert data.pricing == {}
        assert data.differentiation == []
        assert data.objection_handlers == []

    def test_battle_card_create_with_all_fields(self) -> None:
        """Test creating BattleCardCreate with all fields."""
        from src.services.battle_card_service import BattleCardCreate

        data = BattleCardCreate(
            competitor_name="Competitor Inc",
            competitor_domain="competitor.com",
            overview="A major competitor in the space",
            strengths=["Strong brand", "Large sales team"],
            weaknesses=["High pricing", "Slow innovation"],
            pricing={"starting_at": "$50k", "model": "subscription"},
            differentiation=[{"feature": "AI", "our_advantage": "More accurate"}],
            objection_handlers=[{"objection": "They're cheaper", "response": "We offer better value"}],
        )

        assert data.competitor_name == "Competitor Inc"
        assert data.competitor_domain == "competitor.com"
        assert data.overview == "A major competitor in the space"
        assert len(data.strengths) == 2
        assert len(data.weaknesses) == 2
        assert data.pricing["starting_at"] == "$50k"
        assert len(data.differentiation) == 1
        assert len(data.objection_handlers) == 1


class TestBattleCardUpdate:
    """Tests for BattleCardUpdate model."""

    def test_battle_card_update_empty(self) -> None:
        """Test creating BattleCardUpdate with no fields."""
        from src.services.battle_card_service import BattleCardUpdate

        data = BattleCardUpdate()

        assert data.overview is None
        assert data.strengths is None
        assert data.weaknesses is None
        assert data.pricing is None
        assert data.differentiation is None
        assert data.objection_handlers is None

    def test_battle_card_update_partial(self) -> None:
        """Test creating BattleCardUpdate with some fields."""
        from src.services.battle_card_service import BattleCardUpdate

        data = BattleCardUpdate(
            overview="Updated overview",
            strengths=["New strength"]
        )

        assert data.overview == "Updated overview"
        assert data.strengths == ["New strength"]
        assert data.weaknesses is None
        assert data.pricing is None


def test_battle_card_service_has_create_method() -> None:
    """Test BattleCardService has create_battle_card method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "create_battle_card")


def test_battle_card_service_has_get_method() -> None:
    """Test BattleCardService has get methods."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "get_battle_card")
    assert hasattr(BattleCardService, "get_battle_card_by_id")


def test_battle_card_service_has_list_method() -> None:
    """Test BattleCardService has list method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "list_battle_cards")


def test_battle_card_service_has_update_method() -> None:
    """Test BattleCardService has update method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "update_battle_card")


def test_battle_card_service_has_delete_method() -> None:
    """Test BattleCardService has delete method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "delete_battle_card")


def test_battle_card_service_has_history_method() -> None:
    """Test BattleCardService has history method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "get_card_history")


def test_battle_card_service_has_objection_handler_method() -> None:
    """Test BattleCardService has add_objection_handler method."""
    from src.services.battle_card_service import BattleCardService

    assert hasattr(BattleCardService, "add_objection_handler")
