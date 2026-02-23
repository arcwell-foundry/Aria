"""Usage tracking API routes for Cost Governor.

Provides user-facing endpoints to check budget status and usage history,
including both LLM token usage and external API usage.
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Query, status

from src.api.deps import CurrentUser
from src.core.cost_governor import BudgetStatus, CostGovernor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

_governor: CostGovernor | None = None


def _get_governor() -> CostGovernor:
    """Get or create the module-level CostGovernor instance."""
    global _governor
    if _governor is None:
        _governor = CostGovernor()
    return _governor


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_my_usage(
    current_user: CurrentUser,
    days: int = Query(30, ge=1, le=90, description="Number of days of history"),
) -> dict[str, Any]:
    """Get current user's budget status and usage history.

    Args:
        current_user: The authenticated user.
        days: Number of days of history to return.

    Returns:
        Budget status and daily usage history.
    """
    governor = _get_governor()
    budget = await governor.check_budget(current_user.id)
    history = await governor.get_usage_summary(current_user.id, days=days)

    return {
        "budget": budget.model_dump(),
        "history": history,
    }


@router.get("/me/budget", response_model=BudgetStatus, status_code=status.HTTP_200_OK)
async def get_my_budget(
    current_user: CurrentUser,
) -> BudgetStatus:
    """Get current user's budget status (lightweight, for UI polling).

    Args:
        current_user: The authenticated user.

    Returns:
        Current BudgetStatus.
    """
    governor = _get_governor()
    return await governor.check_budget(current_user.id)


@router.get("/me/api", status_code=status.HTTP_200_OK)
async def get_my_api_usage(
    current_user: CurrentUser,
    target_date: str | None = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
) -> dict[str, Any]:
    """Get current user's external API usage (Exa, Composio, etc.).

    Args:
        current_user: The authenticated user.
        target_date: Optional date to query.

    Returns:
        List of API usage records by type for the given date.
    """
    from src.services.usage_tracker import get_user_api_usage

    query_date = date.fromisoformat(target_date) if target_date else None
    usage = await get_user_api_usage(current_user.id, target_date=query_date)
    return {
        "date": (query_date or date.today()).isoformat(),
        "api_usage": usage,
    }
