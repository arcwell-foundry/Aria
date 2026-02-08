"""Tests for US-941 Account Planning & Strategic Workflows."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.models.account_planning import (
    AccountListItem,
    AccountPlanUpdate,
    ForecastStage,
    QuotaSet,
)

# ------------------------------------------------------------------ #
# Model tests                                                         #
# ------------------------------------------------------------------ #


class TestModels:
    """Test Pydantic model validation."""

    def test_quota_set_valid(self) -> None:
        q = QuotaSet(period="2026-Q1", target_value=500000)
        assert q.period == "2026-Q1"
        assert q.target_value == 500000

    def test_quota_set_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            QuotaSet(period="2026-Q1", target_value=-100)

    def test_quota_set_rejects_empty_period(self) -> None:
        with pytest.raises(ValueError):
            QuotaSet(period="", target_value=1000)

    def test_account_plan_update_valid(self) -> None:
        u = AccountPlanUpdate(strategy="## New Strategy\n\nDetails here.")
        assert u.strategy.startswith("## New Strategy")

    def test_account_plan_update_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            AccountPlanUpdate(strategy="")

    def test_forecast_stage_model(self) -> None:
        fs = ForecastStage(stage="opportunity", count=5, total_value=100000, weighted_value=40000)
        assert fs.weighted_value == 40000

    def test_account_list_item_optional_fields(self) -> None:
        item = AccountListItem(
            id="abc",
            company_name="Acme",
            lifecycle_stage="lead",
            status="active",
            health_score=75,
            expected_value=None,
            last_activity_at=None,
            next_action=None,
        )
        assert item.expected_value is None


# ------------------------------------------------------------------ #
# Service tests                                                       #
# ------------------------------------------------------------------ #


def _mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


def _chain(mock: MagicMock, data: list[dict[str, Any]]) -> MagicMock:
    """Make a fluent mock chain return data on .execute()."""
    execute_result = MagicMock()
    execute_result.data = data
    mock.execute.return_value = execute_result
    for method in (
        "select",
        "eq",
        "in_",
        "order",
        "limit",
        "insert",
        "update",
        "upsert",
        "maybe_single",
        "single",
    ):
        getattr(mock, method, lambda *a, **kw: mock).return_value = mock  # noqa: ARG005
    mock.execute.return_value = execute_result
    return mock


class TestListAccounts:
    """Test AccountPlanningService.list_accounts."""

    @pytest.mark.asyncio
    async def test_list_accounts_returns_data(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        leads_mock = MagicMock()
        plans_mock = MagicMock()

        lead_data = [
            {
                "id": "lead-1",
                "company_name": "Acme Bio",
                "lifecycle_stage": "opportunity",
                "status": "active",
                "health_score": 80,
                "expected_value": 50000,
                "last_activity_at": "2026-01-15T00:00:00Z",
                "tags": [],
            }
        ]
        plan_data = [
            {
                "lead_memory_id": "lead-1",
                "next_actions": [{"action": "Send proposal", "priority": "high"}],
            }
        ]

        _chain(leads_mock, lead_data)
        _chain(plans_mock, plan_data)

        def table_dispatch(name: str) -> MagicMock:
            if name == "lead_memories":
                return leads_mock
            return plans_mock

        db.table = table_dispatch

        with patch("src.services.account_planning_service.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = db
            service = AccountPlanningService()
            service._db = db

            result = await service.list_accounts("user-1")

        assert len(result) == 1
        assert result[0]["company_name"] == "Acme Bio"
        assert result[0]["next_action"] == "Send proposal"

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        leads_mock = MagicMock()
        _chain(leads_mock, [])

        db.table = lambda _: leads_mock

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.list_accounts("user-1")

        assert result == []


class TestForecast:
    """Test AccountPlanningService.get_forecast."""

    @pytest.mark.asyncio
    async def test_forecast_calculation(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        lead_data = [
            {
                "lifecycle_stage": "lead",
                "status": "active",
                "health_score": 100,
                "expected_value": 10000,
            },
            {
                "lifecycle_stage": "opportunity",
                "status": "active",
                "health_score": 80,
                "expected_value": 50000,
            },
            {
                "lifecycle_stage": "account",
                "status": "active",
                "health_score": 90,
                "expected_value": 100000,
            },
        ]
        _chain(mock_table, lead_data)
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_forecast("user-1")

        assert result["total_pipeline"] == 160000
        assert result["weighted_pipeline"] == 89000.0
        assert len(result["stages"]) == 3

    @pytest.mark.asyncio
    async def test_forecast_empty_pipeline(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_forecast("user-1")

        assert result["total_pipeline"] == 0
        assert result["weighted_pipeline"] == 0
        assert result["stages"] == []


class TestQuota:
    """Test AccountPlanningService quota methods."""

    @pytest.mark.asyncio
    async def test_set_quota(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(
            mock_table,
            [
                {
                    "id": "q-1",
                    "user_id": "user-1",
                    "period": "2026-Q1",
                    "target_value": 500000,
                    "actual_value": 0,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
        )
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.set_quota("user-1", "2026-Q1", 500000)

        assert result["period"] == "2026-Q1"
        assert result["target_value"] == 500000

    @pytest.mark.asyncio
    async def test_get_quota(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(
            mock_table,
            [
                {
                    "id": "q-1",
                    "period": "2026-Q1",
                    "target_value": 500000,
                    "actual_value": 125000,
                },
            ],
        )
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_quota("user-1")

        assert len(result) == 1
        assert result[0]["actual_value"] == 125000


class TestAccountPlan:
    """Test AccountPlanningService plan generation."""

    @pytest.mark.asyncio
    async def test_get_existing_plan(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        lead_mock = MagicMock()
        plan_mock = MagicMock()

        lead_exec = MagicMock()
        lead_exec.data = {"id": "lead-1", "company_name": "Test"}
        lead_mock.select.return_value = lead_mock
        lead_mock.eq.return_value = lead_mock
        lead_mock.maybe_single.return_value = lead_mock
        lead_mock.execute.return_value = lead_exec

        plan_exec = MagicMock()
        plan_exec.data = {
            "id": "plan-1",
            "strategy": "Existing strategy",
            "next_actions": [],
            "stakeholder_summary": {},
        }
        plan_mock.select.return_value = plan_mock
        plan_mock.eq.return_value = plan_mock
        plan_mock.maybe_single.return_value = plan_mock
        plan_mock.execute.return_value = plan_exec

        def table_dispatch(name: str) -> MagicMock:
            if name == "lead_memories":
                return lead_mock
            return plan_mock

        db.table = table_dispatch

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.get_or_generate_plan("user-1", "lead-1")

        assert result is not None
        assert result["strategy"] == "Existing strategy"

    @pytest.mark.asyncio
    async def test_update_plan(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(
            mock_table,
            [
                {
                    "id": "plan-1",
                    "strategy": "Updated",
                    "updated_at": "2026-02-08T00:00:00Z",
                },
            ],
        )
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.update_plan("user-1", "lead-1", "Updated")

        assert result is not None
        assert result["strategy"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_plan_not_found(self) -> None:
        from src.services.account_planning_service import AccountPlanningService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        with patch("src.services.account_planning_service.SupabaseClient"):
            service = AccountPlanningService()
            service._db = db
            result = await service.update_plan("user-1", "lead-1", "New text")

        assert result is None
