"""Tenant-level monthly budget governor for SaaS billing.

Enforces per-tenant monthly dollar budgets for enterprise contracts.
Distinct from cost_governor.py which handles per-user daily token quotas.

Use cases:
- cost_governor.py: Individual user quotas (prevent abuse, fair usage)
- budget.py: Company billing limits (enterprise contracts, overage alerts)
"""

import logging
import time
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _get_settings() -> Any:
    """Lazy import to avoid circular dependency at module level."""
    from src.core.config import get_settings

    return get_settings()


class TenantBudgetStatus(BaseModel):
    """Monthly budget state for a tenant/company."""

    tenant_id: str
    allowed: bool
    monthly_spend_usd: float
    monthly_limit_usd: float
    utilization_percent: float
    warning: Optional[str] = None


class BudgetGovernor:
    """Per-tenant monthly budget enforcement for SaaS billing.

    Queries the llm_usage table to aggregate month-to-date spend per tenant.
    Uses in-memory caching with TTL to reduce database load.

    Attributes:
        _cache: Dict mapping tenant_id to (spend, timestamp) tuples.
        _cache_ttl_seconds: Cache time-to-live in seconds.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, float]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    async def check(self, tenant_id: str) -> TenantBudgetStatus:
        """Check if tenant can make LLM calls based on monthly budget.

        Args:
            tenant_id: The tenant/company UUID. Empty string returns
                a default "allowed" status (for users without tenants).

        Returns:
            TenantBudgetStatus with allowed flag, spend, limit, and warning.
        """
        if not tenant_id:
            return TenantBudgetStatus(
                tenant_id="",
                allowed=True,
                monthly_spend_usd=0.0,
                monthly_limit_usd=0.0,
                utilization_percent=0.0,
            )

        spend = await self._get_monthly_spend(tenant_id)
        s = _get_settings()
        limit = s.LLM_MONTHLY_BUDGET_PER_SEAT
        utilization = (spend / limit) if limit > 0 else 0.0

        warning = None
        if utilization >= 1.0:
            warning = f"Budget exceeded: ${spend:.2f}/${limit:.2f}"
            logger.warning(
                "Tenant %s exceeded monthly budget: $%.2f / $%.2f",
                tenant_id,
                spend,
                limit,
            )
        elif utilization >= s.LLM_BUDGET_ALERT_THRESHOLD:
            warning = f"Approaching limit: ${spend:.2f}/${limit:.2f} ({utilization * 100:.0f}%)"
            logger.info(
                "Tenant %s approaching budget threshold: $%.2f / $%.2f (%.0f%%)",
                tenant_id,
                spend,
                limit,
                utilization * 100,
            )

        return TenantBudgetStatus(
            tenant_id=tenant_id,
            allowed=utilization < 1.0,  # Hard stop at 100%
            monthly_spend_usd=round(spend, 2),
            monthly_limit_usd=limit,
            utilization_percent=round(utilization * 100, 1),
            warning=warning,
        )

    async def _get_monthly_spend(self, tenant_id: str) -> float:
        """Get month-to-date spend from llm_usage table.

        Uses caching to reduce database queries. Fail-open on errors.

        Args:
            tenant_id: The tenant to query.

        Returns:
            Total USD spend for the current month, or 0.0 on error.
        """
        # Check cache
        now = time.time()
        cached = self._cache.get(tenant_id)
        if cached and (now - cached[1]) < self._cache_ttl_seconds:
            return cached[0]

        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            month_start = datetime.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

            response = (
                client.table("llm_usage")
                .select("total_cost_usd")
                .eq("tenant_id", tenant_id)
                .gte("created_at", month_start.isoformat())
                .execute()
            )

            spend = 0.0
            for r in response.data or []:
                try:
                    val = r.get("total_cost_usd", 0) or 0
                    # Handle both numeric and string values
                    if isinstance(val, (int, float)):
                        spend += float(val)
                    elif isinstance(val, str):
                        try:
                            spend += float(val)
                        except ValueError:
                            pass  # Skip invalid strings
                except (TypeError, ValueError):
                    pass  # Skip any malformed entries
            self._cache[tenant_id] = (spend, now)
            return spend
        except Exception:
            # Fail-open: never block a tenant because tracking failed
            logger.exception("Failed to get monthly spend for tenant %s", tenant_id)
            return 0.0

    def clear_cache(self, tenant_id: Optional[str] = None) -> None:
        """Clear the budget cache.

        Args:
            tenant_id: Specific tenant to clear, or None to clear all.
        """
        if tenant_id:
            self._cache.pop(tenant_id, None)
        else:
            self._cache.clear()


# Singleton pattern (matches cost_governor pattern)
_budget_governor: Optional[BudgetGovernor] = None


def get_budget_governor() -> BudgetGovernor:
    """Get the singleton BudgetGovernor instance.

    Returns:
        The global BudgetGovernor instance, creating it if needed.
    """
    global _budget_governor
    if _budget_governor is None:
        _budget_governor = BudgetGovernor()
    return _budget_governor
