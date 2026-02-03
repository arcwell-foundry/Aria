"""Integration tests for battle cards API endpoints.

Tests cover the full flow of battle card operations:
- Creating battle cards
- Listing battle cards
- Getting by competitor name
- Updating cards with change tracking
- Getting change history
- Deleting cards
- Adding objection handlers
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestBattleCardsIntegration:
    """Integration tests for the battle cards flow."""

    @pytest.fixture
    def mock_db_client(self) -> MagicMock:
        """Create mock database client."""
        return MagicMock()

    @pytest.fixture
    def company_id(self) -> str:
        """Test company ID."""
        return "company-integration-123"

    @pytest.fixture
    def user_id(self) -> str:
        """Test user ID."""
        return "user-integration-456"

    @pytest.mark.asyncio
    async def test_create_battle_card(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test creating a battle card."""
        from src.services.battle_card_service import BattleCardCreate, BattleCardService

        now = datetime.now(UTC)
        card_id = "card-new-123"

        created_card = {
            "id": card_id,
            "company_id": company_id,
            "competitor_name": "TestCompetitor",
            "competitor_domain": "testcompetitor.com",
            "overview": "A test competitor in the market",
            "strengths": ["Strong brand", "Good support"],
            "weaknesses": ["High prices", "Limited features"],
            "pricing": {"base": "$100/month"},
            "differentiation": [],
            "objection_handlers": [],
            "update_source": "manual",
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
        }

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock insert
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[created_card])
            )

            service = BattleCardService()
            result = await service.create_battle_card(
                company_id=company_id,
                data=BattleCardCreate(
                    competitor_name="TestCompetitor",
                    competitor_domain="testcompetitor.com",
                    overview="A test competitor in the market",
                    strengths=["Strong brand", "Good support"],
                    weaknesses=["High prices", "Limited features"],
                    pricing={"base": "$100/month"},
                ),
            )

            assert result["id"] == card_id
            assert result["competitor_name"] == "TestCompetitor"
            assert result["overview"] == "A test competitor in the market"
            assert "Strong brand" in result["strengths"]
            assert result["company_id"] == company_id

    @pytest.mark.asyncio
    async def test_list_battle_cards(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test listing battle cards."""
        from src.services.battle_card_service import BattleCardService

        now = datetime.now(UTC)
        cards_data = [
            {
                "id": "card-1",
                "company_id": company_id,
                "competitor_name": "Alpha Corp",
                "overview": "Alpha competitor",
                "created_at": now.isoformat(),
            },
            {
                "id": "card-2",
                "company_id": company_id,
                "competitor_name": "Beta Inc",
                "overview": "Beta competitor",
                "created_at": now.isoformat(),
            },
            {
                "id": "card-3",
                "company_id": company_id,
                "competitor_name": "Gamma LLC",
                "overview": "Gamma competitor",
                "created_at": now.isoformat(),
            },
        ]

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock list query
            mock_db_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=cards_data
            )

            service = BattleCardService()
            result = await service.list_battle_cards(company_id=company_id)

            assert isinstance(result, list)
            assert len(result) == 3
            assert result[0]["competitor_name"] == "Alpha Corp"

    @pytest.mark.asyncio
    async def test_list_battle_cards_with_search(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test listing battle cards with search filter."""
        from src.services.battle_card_service import BattleCardService

        filtered_cards = [
            {
                "id": "card-1",
                "company_id": company_id,
                "competitor_name": "Alpha Corp",
                "overview": "Alpha competitor",
            },
        ]

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock filtered query
            mock_db_client.table.return_value.select.return_value.eq.return_value.ilike.return_value.order.return_value.execute.return_value = MagicMock(
                data=filtered_cards
            )

            service = BattleCardService()
            result = await service.list_battle_cards(company_id=company_id, search="Alpha")

            assert len(result) == 1
            assert result[0]["competitor_name"] == "Alpha Corp"

    @pytest.mark.asyncio
    async def test_get_battle_card_by_name(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test getting a battle card by competitor name."""
        from src.services.battle_card_service import BattleCardService

        card_data = {
            "id": "card-get-123",
            "company_id": company_id,
            "competitor_name": "GetTestCompetitor",
            "overview": "A specific competitor",
            "strengths": ["Strong tech"],
            "weaknesses": ["Weak sales"],
        }

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock single query
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=card_data
            )

            service = BattleCardService()
            result = await service.get_battle_card(
                company_id=company_id,
                competitor_name="GetTestCompetitor",
            )

            assert result is not None
            assert result["competitor_name"] == "GetTestCompetitor"
            assert result["overview"] == "A specific competitor"

    @pytest.mark.asyncio
    async def test_get_battle_card_not_found(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test getting a battle card that doesn't exist."""
        from src.services.battle_card_service import BattleCardService

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock empty response
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )

            service = BattleCardService()
            result = await service.get_battle_card(
                company_id=company_id,
                competitor_name="NonExistentCompetitor",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_update_battle_card(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test updating a battle card."""
        from src.services.battle_card_service import BattleCardService, BattleCardUpdate

        card_id = "card-update-123"
        now = datetime.now(UTC)

        current_card = {
            "id": card_id,
            "company_id": "company-123",
            "competitor_name": "UpdateTestCompetitor",
            "overview": "Original overview",
            "strengths": ["Old strength"],
            "weaknesses": [],
            "pricing": {},
            "differentiation": [],
            "objection_handlers": [],
        }

        updated_card = {
            **current_card,
            "overview": "Updated overview",
            "strengths": ["New strength", "Another strength"],
            "last_updated": now.isoformat(),
        }

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock get current card
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=current_card
            )

            # Mock update
            mock_db_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_card]
            )

            # Mock insert changes
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            service = BattleCardService()
            result = await service.update_battle_card(
                card_id=card_id,
                data=BattleCardUpdate(
                    overview="Updated overview",
                    strengths=["New strength", "Another strength"],
                ),
            )

            assert result["overview"] == "Updated overview"
            assert "New strength" in result["strengths"]

    @pytest.mark.asyncio
    async def test_update_battle_card_tracks_changes(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test that updating a battle card creates change history."""
        from src.services.battle_card_service import BattleCardService, BattleCardUpdate

        card_id = "card-history-123"
        now = datetime.now(UTC)

        current_card = {
            "id": card_id,
            "company_id": "company-123",
            "competitor_name": "HistoryTestCompetitor",
            "overview": "Original overview",
            "strengths": [],
            "weaknesses": [],
            "pricing": {},
            "differentiation": [],
            "objection_handlers": [],
        }

        updated_card = {**current_card, "overview": "Changed overview"}

        # Track what gets inserted into changes table
        captured_changes: list[dict[str, Any]] = []

        def capture_insert(data: Any) -> MagicMock:
            if isinstance(data, list):
                captured_changes.extend(data)
            mock_chain = MagicMock()
            mock_chain.execute.return_value = MagicMock(data=[])
            return mock_chain

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock get current card
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=current_card
            )

            # Mock update
            mock_db_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_card]
            )

            # Capture changes insertion
            mock_db_client.table.return_value.insert = capture_insert

            service = BattleCardService()
            await service.update_battle_card(
                card_id=card_id,
                data=BattleCardUpdate(overview="Changed overview"),
            )

            # Verify changes were recorded
            assert len(captured_changes) >= 1
            change = captured_changes[0]
            assert change["battle_card_id"] == card_id
            assert change["change_type"] == "overview_updated"
            assert change["old_value"] == "Original overview"
            assert change["new_value"] == "Changed overview"

    @pytest.mark.asyncio
    async def test_get_card_history(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test getting change history for a battle card."""
        from src.services.battle_card_service import BattleCardService

        card_id = "card-history-view-123"
        now = datetime.now(UTC)

        history_data = [
            {
                "id": "change-1",
                "battle_card_id": card_id,
                "change_type": "overview_updated",
                "field_name": "overview",
                "old_value": "Old overview",
                "new_value": "New overview",
                "detected_at": now.isoformat(),
            },
            {
                "id": "change-2",
                "battle_card_id": card_id,
                "change_type": "strengths_updated",
                "field_name": "strengths",
                "old_value": [],
                "new_value": ["New strength"],
                "detected_at": now.isoformat(),
            },
        ]

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock history query
            mock_db_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=history_data
            )

            service = BattleCardService()
            result = await service.get_card_history(card_id=card_id, limit=20)

            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["change_type"] == "overview_updated"
            assert result[1]["change_type"] == "strengths_updated"

    @pytest.mark.asyncio
    async def test_delete_battle_card(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test deleting a battle card."""
        from src.services.battle_card_service import BattleCardService

        card_id = "card-delete-123"

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock delete
            mock_db_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

            service = BattleCardService()
            result = await service.delete_battle_card(card_id=card_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_add_objection_handler(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test adding an objection handler to a battle card."""
        from src.services.battle_card_service import BattleCardService

        card_id = "card-objection-123"
        now = datetime.now(UTC)

        current_card = {
            "id": card_id,
            "company_id": "company-123",
            "competitor_name": "ObjectionTestCompetitor",
            "overview": "Test competitor",
            "strengths": [],
            "weaknesses": [],
            "pricing": {},
            "differentiation": [],
            "objection_handlers": [
                {"objection": "Old objection", "response": "Old response"},
            ],
        }

        updated_card = {
            **current_card,
            "objection_handlers": [
                {"objection": "Old objection", "response": "Old response"},
                {"objection": "Too expensive", "response": "We offer better value"},
            ],
            "last_updated": now.isoformat(),
        }

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock get current card (called twice - once in add_objection_handler, once in update)
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=current_card
            )

            # Mock update
            mock_db_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_card]
            )

            # Mock insert changes
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            service = BattleCardService()
            result = await service.add_objection_handler(
                card_id=card_id,
                objection="Too expensive",
                response="We offer better value",
            )

            assert len(result["objection_handlers"]) == 2
            assert result["objection_handlers"][1]["objection"] == "Too expensive"
            assert result["objection_handlers"][1]["response"] == "We offer better value"

    @pytest.mark.asyncio
    async def test_full_battle_card_lifecycle(
        self,
        mock_db_client: MagicMock,
        company_id: str,
    ) -> None:
        """Test complete lifecycle: create -> update -> add objection -> get history -> delete."""
        from src.services.battle_card_service import (
            BattleCardCreate,
            BattleCardService,
            BattleCardUpdate,
        )

        card_id = "lifecycle-card-123"
        now = datetime.now(UTC)

        # Stage 1: Created card
        created_card: dict[str, Any] = {
            "id": card_id,
            "company_id": company_id,
            "competitor_name": "Lifecycle Competitor",
            "competitor_domain": "lifecycle.com",
            "overview": "Initial overview",
            "strengths": [],
            "weaknesses": [],
            "pricing": {},
            "differentiation": [],
            "objection_handlers": [],
            "update_source": "manual",
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
        }

        # Track operations for verification
        operations: list[str] = []

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            service = BattleCardService()

            # === STEP 1: CREATE ===
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[created_card])
            )

            result = await service.create_battle_card(
                company_id=company_id,
                data=BattleCardCreate(
                    competitor_name="Lifecycle Competitor",
                    competitor_domain="lifecycle.com",
                    overview="Initial overview",
                ),
            )
            operations.append("create")

            assert result["id"] == card_id
            assert result["competitor_name"] == "Lifecycle Competitor"

            # === STEP 2: UPDATE ===
            # Mock get for update
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=created_card
            )

            updated_card = {
                **created_card,
                "overview": "Updated overview",
                "strengths": ["New strength"],
            }
            mock_db_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_card]
            )
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            result = await service.update_battle_card(
                card_id=card_id,
                data=BattleCardUpdate(
                    overview="Updated overview",
                    strengths=["New strength"],
                ),
            )
            operations.append("update")

            assert result["overview"] == "Updated overview"

            # === STEP 3: ADD OBJECTION HANDLER ===
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=updated_card
            )

            with_objection = {
                **updated_card,
                "objection_handlers": [
                    {"objection": "Price concern", "response": "Value proposition"},
                ],
            }
            mock_db_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[with_objection]
            )

            result = await service.add_objection_handler(
                card_id=card_id,
                objection="Price concern",
                response="Value proposition",
            )
            operations.append("add_objection")

            assert len(result["objection_handlers"]) == 1

            # === STEP 4: GET HISTORY ===
            history_data = [
                {
                    "id": "change-1",
                    "battle_card_id": card_id,
                    "change_type": "overview_updated",
                    "detected_at": now.isoformat(),
                },
            ]
            mock_db_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=history_data
            )

            history = await service.get_card_history(card_id=card_id)
            operations.append("get_history")

            assert len(history) >= 1

            # === STEP 5: DELETE ===
            mock_db_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

            deleted = await service.delete_battle_card(card_id=card_id)
            operations.append("delete")

            assert deleted is True

            # Verify all operations completed
            assert operations == [
                "create",
                "update",
                "add_objection",
                "get_history",
                "delete",
            ]

    @pytest.mark.asyncio
    async def test_update_battle_card_not_found(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test updating a battle card that doesn't exist raises error."""
        from src.services.battle_card_service import BattleCardService, BattleCardUpdate

        card_id = "nonexistent-card"

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock empty response for get
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )

            service = BattleCardService()

            with pytest.raises(ValueError, match="Battle card not found"):
                await service.update_battle_card(
                    card_id=card_id,
                    data=BattleCardUpdate(overview="New overview"),
                )

    @pytest.mark.asyncio
    async def test_add_objection_handler_card_not_found(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test adding objection handler to nonexistent card raises error."""
        from src.services.battle_card_service import BattleCardService

        card_id = "nonexistent-card"

        with patch("src.services.battle_card_service.SupabaseClient") as mock_db_class:
            mock_db_class.get_client.return_value = mock_db_client

            # Mock empty response for get
            mock_db_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )

            service = BattleCardService()

            with pytest.raises(ValueError, match="Battle card not found"):
                await service.add_objection_handler(
                    card_id=card_id,
                    objection="Test objection",
                    response="Test response",
                )
