"""Unit tests for tenant monthly budget governor."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.budget import BudgetGovernor, TenantBudgetStatus, get_budget_governor


class TestBudgetGovernor:
    """Tests for BudgetGovernor class."""

    @pytest.fixture
    def governor(self) -> BudgetGovernor:
        """Create a fresh BudgetGovernor for each test."""
        gov = BudgetGovernor()
        gov._cache.clear()
        return gov

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.LLM_MONTHLY_BUDGET_PER_SEAT = 250.0
        settings.LLM_BUDGET_ALERT_THRESHOLD = 0.8
        return settings

    @pytest.mark.asyncio
    async def test_check_empty_tenant_id_returns_allowed(
        self, governor: BudgetGovernor
    ) -> None:
        """Empty tenant_id should return allowed status."""
        result = await governor.check("")

        assert result.tenant_id == ""
        assert result.allowed is True
        assert result.monthly_spend_usd == 0.0
        assert result.monthly_limit_usd == 0.0
        assert result.utilization_percent == 0.0
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_check_below_budget_returns_allowed(
        self, governor: BudgetGovernor, mock_settings: MagicMock
    ) -> None:
        """Tenant below budget should be allowed."""
        with patch("src.core.budget._get_settings", return_value=mock_settings):
            with patch.object(
                governor,
                "_get_monthly_spend",
                new_callable=AsyncMock,
                return_value=50.0,
            ):
                result = await governor.check("tenant-123")

        assert result.tenant_id == "tenant-123"
        assert result.allowed is True
        assert result.monthly_spend_usd == 50.0
        assert result.monthly_limit_usd == 250.0
        assert result.utilization_percent == 20.0
        assert result.warning is None

    @pytest.mark.asyncio
    async def test_check_warning_at_80_percent(
        self, governor: BudgetGovernor, mock_settings: MagicMock
    ) -> None:
        """Warning should be set at 80% threshold."""
        with patch("src.core.budget._get_settings", return_value=mock_settings):
            with patch.object(
                governor,
                "_get_monthly_spend",
                new_callable=AsyncMock,
                return_value=200.0,  # 80% of $250
            ):
                result = await governor.check("tenant-123")

        assert result.allowed is True
        assert result.utilization_percent == 80.0
        assert result.warning is not None
        assert "Approaching limit" in result.warning

    @pytest.mark.asyncio
    async def test_check_hard_stop_at_100_percent(
        self, governor: BudgetGovernor, mock_settings: MagicMock
    ) -> None:
        """Tenant at 100% budget should be blocked."""
        with patch("src.core.budget._get_settings", return_value=mock_settings):
            with patch.object(
                governor,
                "_get_monthly_spend",
                new_callable=AsyncMock,
                return_value=250.0,  # 100% of $250
            ):
                result = await governor.check("tenant-123")

        assert result.allowed is False
        assert result.utilization_percent == 100.0
        assert result.warning is not None
        assert "Budget exceeded" in result.warning

    @pytest.mark.asyncio
    async def test_check_over_budget_blocked(
        self, governor: BudgetGovernor, mock_settings: MagicMock
    ) -> None:
        """Tenant over budget should be blocked."""
        with patch("src.core.budget._get_settings", return_value=mock_settings):
            with patch.object(
                governor,
                "_get_monthly_spend",
                new_callable=AsyncMock,
                return_value=300.0,  # 120% of $250
            ):
                result = await governor.check("tenant-123")

        assert result.allowed is False
        assert result.utilization_percent == 120.0
        assert "Budget exceeded" in result.warning

    @pytest.mark.asyncio
    async def test_cache_ttl_behavior(
        self, governor: BudgetGovernor, mock_settings: MagicMock
    ) -> None:
        """Cache should be used within TTL and refreshed after."""
        governor._cache_ttl_seconds = 1  # Short TTL for testing
        tenant_id = "tenant-123"

        # Directly manipulate cache to test TTL behavior
        now = time.time()
        governor._cache[tenant_id] = (100.0, now)

        with patch("src.core.budget._get_settings", return_value=mock_settings):
            # First call - uses cache (not expired)
            result1 = await governor.check(tenant_id)
            assert result1.monthly_spend_usd == 100.0

            # Second call - still uses cache
            result2 = await governor.check(tenant_id)
            assert result2.monthly_spend_usd == 100.0

            # Wait for TTL to expire
            time.sleep(1.1)

            # Now the cache entry is stale - the next call will need to refresh
            # But since we mock _get_monthly_spend, it should get the new value
            with patch.object(
                governor,
                "_get_monthly_spend",
                new_callable=AsyncMock,
                return_value=200.0,
            ):
                result3 = await governor.check(tenant_id)
                assert result3.monthly_spend_usd == 200.0  # New value after refresh

    @pytest.mark.asyncio
    async def test_get_monthly_spend_fail_open(self, governor: BudgetGovernor) -> None:
        """_get_monthly_spend should return 0.0 on database errors."""
        with patch("src.db.supabase.SupabaseClient") as mock_supabase_class:
            mock_supabase_class.get_client.side_effect = Exception("DB error")

            spend = await governor._get_monthly_spend("tenant-123")

            assert spend == 0.0

    @pytest.mark.asyncio
    async def test_get_monthly_spend_aggregates_costs(
        self, governor: BudgetGovernor
    ) -> None:
        """_get_monthly_spend should sum all total_cost_usd values."""
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[
                {"total_cost_usd": 10.50},
                {"total_cost_usd": 25.25},
                {"total_cost_usd": 5.0},
            ]
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            spend = await governor._get_monthly_spend("tenant-123")

        assert spend == 40.75

    @pytest.mark.asyncio
    async def test_get_monthly_spend_handles_null_costs(
        self, governor: BudgetGovernor
    ) -> None:
        """_get_monthly_spend should handle null/missing cost values."""
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[
                {"total_cost_usd": 10.0},
                {"total_cost_usd": None},
                {},  # Missing key entirely
                {"total_cost_usd": "invalid"},  # Non-numeric - should be skipped
                {"total_cost_usd": "15.5"},  # Valid numeric string
            ]
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            spend = await governor._get_monthly_spend("tenant-123")

        # Should sum 10.0 + 0 + 0 + 0 + 15.5 = 25.5
        assert spend == 25.5

    def test_clear_cache_specific_tenant(self, governor: BudgetGovernor) -> None:
        """clear_cache should remove only the specified tenant."""
        governor._cache["tenant-1"] = (100.0, time.time())
        governor._cache["tenant-2"] = (200.0, time.time())

        governor.clear_cache("tenant-1")

        assert "tenant-1" not in governor._cache
        assert "tenant-2" in governor._cache

    def test_clear_cache_all(self, governor: BudgetGovernor) -> None:
        """clear_cache with no args should clear all."""
        governor._cache["tenant-1"] = (100.0, time.time())
        governor._cache["tenant-2"] = (200.0, time.time())

        governor.clear_cache()

        assert len(governor._cache) == 0


class TestGetBudgetGovernor:
    """Tests for singleton getter."""

    def test_returns_singleton(self) -> None:
        """get_budget_governor should return the same instance."""
        # Clear any existing singleton
        import src.core.budget as budget_module

        budget_module._budget_governor = None

        gov1 = get_budget_governor()
        gov2 = get_budget_governor()

        assert gov1 is gov2

    def test_creates_new_instance_if_none(self) -> None:
        """Should create new instance if singleton is None."""
        import src.core.budget as budget_module

        budget_module._budget_governor = None

        gov = get_budget_governor()

        assert gov is not None
        assert isinstance(gov, BudgetGovernor)

        # Cleanup
        budget_module._budget_governor = None


class TestTenantBudgetStatus:
    """Tests for TenantBudgetStatus model."""

    def test_model_creation(self) -> None:
        """Should create TenantBudgetStatus with all fields."""
        status = TenantBudgetStatus(
            tenant_id="test-tenant",
            allowed=True,
            monthly_spend_usd=100.0,
            monthly_limit_usd=250.0,
            utilization_percent=40.0,
            warning="Test warning",
        )

        assert status.tenant_id == "test-tenant"
        assert status.allowed is True
        assert status.monthly_spend_usd == 100.0
        assert status.monthly_limit_usd == 250.0
        assert status.utilization_percent == 40.0
        assert status.warning == "Test warning"

    def test_warning_optional(self) -> None:
        """Warning field should be optional."""
        status = TenantBudgetStatus(
            tenant_id="test-tenant",
            allowed=True,
            monthly_spend_usd=0.0,
            monthly_limit_usd=250.0,
            utilization_percent=0.0,
        )

        assert status.warning is None
