"""Cost Governor — per-user token budget enforcement and cost tracking.

Sits transparently inside LLMClient. Checks budgets before and records
usage after every call. Soft degradation handles 95% of cases by reducing
thinking effort silently; hard stops only fire at 100% budget exhaustion.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _get_settings() -> Any:
    """Lazy import to avoid circular dependency at module level."""
    from src.core.config import get_settings

    return get_settings()


@dataclass
class LLMUsage:
    """Token usage from a single LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Sum of input, output, and thinking tokens."""
        return self.input_tokens + self.output_tokens + self.thinking_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """Estimated cost in USD based on configured per-million rates."""
        s = _get_settings()
        return (
            self.input_tokens * s.COST_GOVERNOR_INPUT_TOKEN_COST_PER_M / 1_000_000
            + self.output_tokens * s.COST_GOVERNOR_OUTPUT_TOKEN_COST_PER_M / 1_000_000
            + self.thinking_tokens * s.COST_GOVERNOR_THINKING_TOKEN_COST_PER_M / 1_000_000
        )

    @classmethod
    def from_anthropic_response(cls, response: Any) -> "LLMUsage":
        """Extract usage from an Anthropic API response.

        Args:
            response: The raw Anthropic message response object.

        Returns:
            LLMUsage populated from response.usage attributes.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return cls()

        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        # Cache tokens are reported in usage on newer SDK versions
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

        # Thinking tokens: check for dedicated field first, then estimate
        # from thinking content blocks as a fallback.
        thinking_tokens = 0
        if hasattr(usage, "thinking_tokens"):
            thinking_tokens = getattr(usage, "thinking_tokens", 0) or 0
        elif hasattr(response, "content"):
            for block in response.content:
                if getattr(block, "type", None) == "thinking":
                    text = getattr(block, "thinking", "") or ""
                    # Rough estimate: ~4 chars per token
                    thinking_tokens += len(text) // 4

        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )


class BudgetStatus(BaseModel):
    """Current budget state for a user."""

    can_proceed: bool
    should_reduce_effort: bool = False
    tokens_used_today: int = 0
    tokens_remaining: int = 0
    thinking_tokens_used_today: int = 0
    thinking_tokens_remaining: int = 0
    daily_budget: int = 0
    daily_thinking_budget: int = 0
    utilization_percent: float = 0.0
    estimated_cost_today_usd: float = 0.0
    llm_calls_today: int = 0


class CostGovernor:
    """Per-user token budget enforcement and cost tracking."""

    def __init__(self) -> None:
        self._retry_counts: dict[str, int] = {}

    async def check_budget(self, user_id: str) -> BudgetStatus:
        """Check whether a user can make another LLM call.

        Args:
            user_id: The user to check.

        Returns:
            BudgetStatus with can_proceed / should_reduce_effort flags.
        """
        s = _get_settings()

        if not s.COST_GOVERNOR_ENABLED:
            return BudgetStatus(
                can_proceed=True,
                daily_budget=s.COST_GOVERNOR_DAILY_TOKEN_BUDGET,
                daily_thinking_budget=s.COST_GOVERNOR_DAILY_THINKING_BUDGET,
                tokens_remaining=s.COST_GOVERNOR_DAILY_TOKEN_BUDGET,
                thinking_tokens_remaining=s.COST_GOVERNOR_DAILY_THINKING_BUDGET,
            )

        row = await self._get_today_usage(user_id)

        total_used = (
            row["input_tokens"]
            + row["output_tokens"]
            + row["extended_thinking_tokens"]
        )
        thinking_used = row["extended_thinking_tokens"]
        daily_budget = s.COST_GOVERNOR_DAILY_TOKEN_BUDGET
        thinking_budget = s.COST_GOVERNOR_DAILY_THINKING_BUDGET
        utilization = total_used / daily_budget if daily_budget > 0 else 0.0

        can_proceed = total_used < daily_budget
        should_reduce = utilization >= s.COST_GOVERNOR_SOFT_LIMIT_PERCENT and can_proceed

        return BudgetStatus(
            can_proceed=can_proceed,
            should_reduce_effort=should_reduce,
            tokens_used_today=total_used,
            tokens_remaining=max(0, daily_budget - total_used),
            thinking_tokens_used_today=thinking_used,
            thinking_tokens_remaining=max(0, thinking_budget - thinking_used),
            daily_budget=daily_budget,
            daily_thinking_budget=thinking_budget,
            utilization_percent=round(utilization * 100, 2),
            estimated_cost_today_usd=float(row["estimated_cost_cents"]) / 100.0,
            llm_calls_today=row["request_count"],
        )

    async def record_usage(self, user_id: str, usage: LLMUsage) -> None:
        """Record token usage for a user. Fail-open on errors.

        Args:
            user_id: The user to record usage for.
            usage: The token usage from the LLM call.
        """
        s = _get_settings()
        if not s.COST_GOVERNOR_ENABLED:
            return

        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            client.rpc(
                "increment_usage_tracking",
                {
                    "p_user_id": user_id,
                    "p_date": date.today().isoformat(),
                    "p_input_tokens": usage.input_tokens,
                    "p_output_tokens": usage.output_tokens,
                    "p_thinking_tokens": usage.thinking_tokens,
                    "p_cache_read_tokens": usage.cache_read_tokens,
                    "p_cache_creation_tokens": usage.cache_creation_tokens,
                    "p_estimated_cost": usage.estimated_cost_usd,
                },
            ).execute()
        except Exception:
            # Fail-open: never block a response because tracking failed
            logger.exception("Failed to record usage for user %s", user_id)

    def get_thinking_budget(
        self, budget_status: BudgetStatus, requested_effort: str
    ) -> str:
        """Downgrade thinking effort when approaching budget limits.

        Args:
            budget_status: Current budget status.
            requested_effort: One of "routine", "complex", "critical".

        Returns:
            Possibly downgraded effort level.
        """
        if not budget_status.should_reduce_effort:
            return requested_effort

        downgrades = {"critical": "complex", "complex": "routine"}
        downgraded = downgrades.get(requested_effort, requested_effort)
        if downgraded != requested_effort:
            logger.info(
                "Cost governor downgraded thinking effort: %s -> %s (%.1f%% utilization)",
                requested_effort,
                downgraded,
                budget_status.utilization_percent,
            )
        return downgraded

    def check_retry_budget(self, goal_id: str) -> bool:
        """Check whether a goal has retries remaining.

        Args:
            goal_id: The goal to check.

        Returns:
            True if retries are within the allowed limit.
        """
        s = _get_settings()
        current = self._retry_counts.get(goal_id, 0)
        return current < s.COST_GOVERNOR_MAX_RETRIES_PER_GOAL

    def record_retry(self, goal_id: str) -> int:
        """Record a retry attempt for a goal.

        Args:
            goal_id: The goal being retried.

        Returns:
            New retry count.
        """
        count = self._retry_counts.get(goal_id, 0) + 1
        self._retry_counts[goal_id] = count
        return count

    def clear_retry_count(self, goal_id: str) -> None:
        """Clear retry counter for a completed goal.

        Args:
            goal_id: The goal to clear.
        """
        self._retry_counts.pop(goal_id, None)

    async def _get_today_usage(self, user_id: str) -> dict[str, Any]:
        """Fetch today's usage row for a user.

        Args:
            user_id: The user to query.

        Returns:
            Dict with token counts, defaulting to zeros if no row exists.
        """
        # Column names match deployed usage_tracking table schema
        defaults: dict[str, Any] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "extended_thinking_tokens": 0,
            "estimated_cost_cents": 0.0,
            "request_count": 0,
        }

        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("usage_tracking")
                .select("*")
                .eq("user_id", user_id)
                .eq("date", date.today().isoformat())
                .maybe_single()
                .execute()
            )

            if response.data:
                return {**defaults, **response.data}
        except Exception:
            logger.exception("Failed to fetch usage for user %s", user_id)

        return defaults

    async def get_usage_summary(
        self, user_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get usage history for a user over the last N days.

        Args:
            user_id: The user to query.
            days: Number of days of history.

        Returns:
            List of daily usage rows ordered by date DESC.
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("usage_tracking")
                .select("*")
                .eq("user_id", user_id)
                .order("date", desc=True)
                .limit(days)
                .execute()
            )
            return response.data or []
        except Exception:
            logger.exception("Failed to fetch usage summary for user %s", user_id)
            return []

    async def get_all_users_usage_today(self) -> list[dict[str, Any]]:
        """Get all users' usage for today, ordered by cost DESC.

        Returns:
            List of today's usage rows for all users.
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("usage_tracking")
                .select("*")
                .eq("date", date.today().isoformat())
                .order("estimated_cost_usd", desc=True)
                .execute()
            )
            return response.data or []
        except Exception:
            logger.exception("Failed to fetch all users' usage for today")
            return []
