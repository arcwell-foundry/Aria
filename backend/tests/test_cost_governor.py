"""Tests for CostGovernor — budget enforcement and cost tracking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.cost_governor import BudgetStatus, CostGovernor, LLMUsage


# ---------------------------------------------------------------------------
# LLMUsage unit tests
# ---------------------------------------------------------------------------


class TestLLMUsage:
    """Tests for the LLMUsage dataclass."""

    def test_total_tokens_sums_correctly(self) -> None:
        usage = LLMUsage(input_tokens=100, output_tokens=200, thinking_tokens=300)
        assert usage.total_tokens == 600

    def test_total_tokens_defaults_to_zero(self) -> None:
        usage = LLMUsage()
        assert usage.total_tokens == 0

    @patch("src.core.cost_governor._get_settings")
    def test_estimated_cost_usd_uses_configured_rates(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_INPUT_TOKEN_COST_PER_M=3.0,
            COST_GOVERNOR_OUTPUT_TOKEN_COST_PER_M=15.0,
            COST_GOVERNOR_THINKING_TOKEN_COST_PER_M=15.0,
        )
        usage = LLMUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            thinking_tokens=1_000_000,
        )
        # $3 + $15 + $15 = $33
        assert usage.estimated_cost_usd == pytest.approx(33.0)

    def test_from_anthropic_response_normal(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=150,
                output_tokens=200,
                cache_read_input_tokens=50,
                cache_creation_input_tokens=10,
            ),
            content=[SimpleNamespace(type="text", text="Hello")],
        )
        usage = LLMUsage.from_anthropic_response(response)
        assert usage.input_tokens == 150
        assert usage.output_tokens == 200
        assert usage.cache_read_tokens == 50
        assert usage.cache_creation_tokens == 10

    def test_from_anthropic_response_with_thinking_tokens_field(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=200,
                thinking_tokens=500,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            content=[],
        )
        usage = LLMUsage.from_anthropic_response(response)
        assert usage.thinking_tokens == 500

    def test_from_anthropic_response_thinking_from_content_blocks(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=200,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            content=[
                SimpleNamespace(type="thinking", thinking="x" * 400),  # ~100 tokens
                SimpleNamespace(type="text", text="Hello"),
            ],
        )
        usage = LLMUsage.from_anthropic_response(response)
        assert usage.thinking_tokens == 100  # 400 chars / 4

    def test_from_anthropic_response_missing_usage(self) -> None:
        response = SimpleNamespace()  # no usage attr
        usage = LLMUsage.from_anthropic_response(response)
        assert usage.total_tokens == 0


# ---------------------------------------------------------------------------
# BudgetStatus unit tests
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    """Tests for the BudgetStatus model."""

    def test_defaults(self) -> None:
        status = BudgetStatus(can_proceed=True)
        assert status.can_proceed is True
        assert status.should_reduce_effort is False
        assert status.tokens_used_today == 0
        assert status.utilization_percent == 0.0


# ---------------------------------------------------------------------------
# CostGovernor unit tests
# ---------------------------------------------------------------------------


class TestCostGovernor:
    """Tests for the CostGovernor class."""

    @pytest.mark.asyncio
    @patch("src.core.cost_governor._get_settings")
    async def test_check_budget_disabled_always_can_proceed(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=False,
            COST_GOVERNOR_DAILY_TOKEN_BUDGET=2_000_000,
            COST_GOVERNOR_DAILY_THINKING_BUDGET=500_000,
        )
        governor = CostGovernor()
        result = await governor.check_budget("user-123")
        assert result.can_proceed is True

    @pytest.mark.asyncio
    @patch("src.core.cost_governor.SupabaseClient", create=True)
    @patch("src.core.cost_governor._get_settings")
    async def test_check_budget_within_limits(
        self, mock_settings: MagicMock, _mock_sb: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=True,
            COST_GOVERNOR_DAILY_TOKEN_BUDGET=2_000_000,
            COST_GOVERNOR_DAILY_THINKING_BUDGET=500_000,
            COST_GOVERNOR_SOFT_LIMIT_PERCENT=0.80,
        )
        governor = CostGovernor()
        governor._get_today_usage = AsyncMock(return_value={  # type: ignore[method-assign]
            "input_tokens": 100_000,
            "output_tokens": 50_000,
            "extended_thinking_tokens": 10_000,
            "estimated_cost_cents": 50.0,  # 0.50 USD = 50 cents
            "request_count": 5,
        })

        result = await governor.check_budget("user-123")
        assert result.can_proceed is True
        assert result.should_reduce_effort is False
        assert result.tokens_used_today == 160_000

    @pytest.mark.asyncio
    @patch("src.core.cost_governor._get_settings")
    async def test_check_budget_at_soft_limit(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=True,
            COST_GOVERNOR_DAILY_TOKEN_BUDGET=2_000_000,
            COST_GOVERNOR_DAILY_THINKING_BUDGET=500_000,
            COST_GOVERNOR_SOFT_LIMIT_PERCENT=0.80,
        )
        governor = CostGovernor()
        # 80% of 2M = 1.6M total
        governor._get_today_usage = AsyncMock(return_value={  # type: ignore[method-assign]
            "input_tokens": 800_000,
            "output_tokens": 600_000,
            "extended_thinking_tokens": 200_000,
            "estimated_cost_cents": 1000.0,  # 10.0 USD = 1000 cents
            "request_count": 50,
        })

        result = await governor.check_budget("user-123")
        assert result.can_proceed is True
        assert result.should_reduce_effort is True
        assert result.utilization_percent == 80.0

    @pytest.mark.asyncio
    @patch("src.core.cost_governor._get_settings")
    async def test_check_budget_exceeded(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=True,
            COST_GOVERNOR_DAILY_TOKEN_BUDGET=2_000_000,
            COST_GOVERNOR_DAILY_THINKING_BUDGET=500_000,
            COST_GOVERNOR_SOFT_LIMIT_PERCENT=0.80,
        )
        governor = CostGovernor()
        governor._get_today_usage = AsyncMock(return_value={  # type: ignore[method-assign]
            "input_tokens": 1_000_000,
            "output_tokens": 800_000,
            "extended_thinking_tokens": 300_000,
            "estimated_cost_cents": 2000.0,  # 20.0 USD = 2000 cents
            "request_count": 100,
        })

        result = await governor.check_budget("user-123")
        assert result.can_proceed is False

    @pytest.mark.asyncio
    @patch("src.core.cost_governor._get_settings")
    async def test_record_usage_calls_rpc(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=True,
            COST_GOVERNOR_INPUT_TOKEN_COST_PER_M=3.0,
            COST_GOVERNOR_OUTPUT_TOKEN_COST_PER_M=15.0,
            COST_GOVERNOR_THINKING_TOKEN_COST_PER_M=15.0,
        )
        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.return_value = None

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            governor = CostGovernor()
            usage = LLMUsage(input_tokens=100, output_tokens=200)
            await governor.record_usage("user-123", usage)

            mock_client.rpc.assert_called_once()
            call_args = mock_client.rpc.call_args
            assert call_args[0][0] == "increment_usage_tracking"
            params = call_args[0][1]
            assert params["p_user_id"] == "user-123"
            assert params["p_input_tokens"] == 100
            assert params["p_output_tokens"] == 200

    @pytest.mark.asyncio
    @patch("src.core.cost_governor._get_settings")
    async def test_record_usage_swallows_exceptions(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_ENABLED=True,
            COST_GOVERNOR_INPUT_TOKEN_COST_PER_M=3.0,
            COST_GOVERNOR_OUTPUT_TOKEN_COST_PER_M=15.0,
            COST_GOVERNOR_THINKING_TOKEN_COST_PER_M=15.0,
        )
        with patch("src.db.supabase.SupabaseClient.get_client", side_effect=RuntimeError("DB down")):
            governor = CostGovernor()
            usage = LLMUsage(input_tokens=100)
            # Should NOT raise
            await governor.record_usage("user-123", usage)

    @patch("src.core.cost_governor._get_settings")
    def test_check_retry_budget_allows_within_limit(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_MAX_RETRIES_PER_GOAL=3,
        )
        governor = CostGovernor()
        assert governor.check_retry_budget("goal-1") is True

    @patch("src.core.cost_governor._get_settings")
    def test_check_retry_budget_blocks_after_max(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value = SimpleNamespace(
            COST_GOVERNOR_MAX_RETRIES_PER_GOAL=3,
        )
        governor = CostGovernor()
        governor._retry_counts["goal-1"] = 3
        assert governor.check_retry_budget("goal-1") is False

    def test_record_retry_increments(self) -> None:
        governor = CostGovernor()
        assert governor.record_retry("goal-1") == 1
        assert governor.record_retry("goal-1") == 2
        assert governor.record_retry("goal-1") == 3

    def test_clear_retry_count_resets(self) -> None:
        governor = CostGovernor()
        governor.record_retry("goal-1")
        governor.clear_retry_count("goal-1")
        assert governor._retry_counts.get("goal-1") is None

    def test_get_thinking_budget_no_downgrade_below_soft_limit(self) -> None:
        governor = CostGovernor()
        budget = BudgetStatus(
            can_proceed=True,
            should_reduce_effort=False,
            utilization_percent=50.0,
        )
        assert governor.get_thinking_budget(budget, "critical") == "critical"
        assert governor.get_thinking_budget(budget, "complex") == "complex"
        assert governor.get_thinking_budget(budget, "routine") == "routine"

    def test_get_thinking_budget_downgrades_at_soft_limit(self) -> None:
        governor = CostGovernor()
        budget = BudgetStatus(
            can_proceed=True,
            should_reduce_effort=True,
            utilization_percent=85.0,
        )
        assert governor.get_thinking_budget(budget, "critical") == "complex"
        assert governor.get_thinking_budget(budget, "complex") == "routine"
        assert governor.get_thinking_budget(budget, "routine") == "routine"


# ---------------------------------------------------------------------------
# LLM integration tests (mocked)
# ---------------------------------------------------------------------------


class TestLLMClientGovernance:
    """Tests for CostGovernor integration with LLMClient."""

    @pytest.mark.asyncio
    async def test_generate_without_user_id_skips_governance(self) -> None:
        """When user_id is None, no budget check or usage recording occurs."""
        from src.core.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client._model = "test"
        client._client = MagicMock()

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="Hello", type="text")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )
        client._client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
            mock_cb.call = AsyncMock(return_value=mock_response)
            result = await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_generate_with_user_id_checks_budget(self) -> None:
        """When user_id is provided, budget is checked before the call."""
        from src.core.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client._model = "test"
        client._client = MagicMock()

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="Hello", type="text")],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=20,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

        mock_governor = MagicMock()
        mock_governor.check_budget = AsyncMock(
            return_value=BudgetStatus(can_proceed=True, daily_budget=2_000_000)
        )
        mock_governor.record_usage = AsyncMock()

        with (
            patch("src.core.llm._llm_circuit_breaker") as mock_cb,
            patch("src.core.llm.get_cost_governor", return_value=mock_governor),
        ):
            mock_cb.call = AsyncMock(return_value=mock_response)
            result = await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                user_id="user-123",
            )

        assert result == "Hello"
        mock_governor.check_budget.assert_awaited_once_with("user-123")
        mock_governor.record_usage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_raises_budget_exceeded(self) -> None:
        """When budget is exhausted, BudgetExceededError is raised."""
        from src.core.exceptions import BudgetExceededError
        from src.core.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client._model = "test"
        client._client = MagicMock()

        mock_governor = MagicMock()
        mock_governor.check_budget = AsyncMock(
            return_value=BudgetStatus(
                can_proceed=False,
                tokens_used_today=2_000_000,
                daily_budget=2_000_000,
            )
        )

        with patch("src.core.llm.get_cost_governor", return_value=mock_governor):
            with pytest.raises(BudgetExceededError):
                await client.generate_response(
                    messages=[{"role": "user", "content": "Hi"}],
                    user_id="user-123",
                )

    @pytest.mark.asyncio
    async def test_usage_tracking_failure_does_not_block_response(self) -> None:
        """If recording usage fails, the response is still returned."""
        from src.core.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client._model = "test"
        client._client = MagicMock()

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="Hello", type="text")],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=20,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

        mock_governor = MagicMock()
        mock_governor.check_budget = AsyncMock(
            return_value=BudgetStatus(can_proceed=True, daily_budget=2_000_000)
        )
        mock_governor.record_usage = AsyncMock(side_effect=RuntimeError("DB down"))

        with (
            patch("src.core.llm._llm_circuit_breaker") as mock_cb,
            patch("src.core.llm.get_cost_governor", return_value=mock_governor),
        ):
            mock_cb.call = AsyncMock(return_value=mock_response)
            result = await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                user_id="user-123",
            )

        # Response still returned despite recording failure
        assert result == "Hello"
