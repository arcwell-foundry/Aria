"""Usage Tracker — wraps external API calls with per-user tracking and rate limiting.

Every Exa search, Composio action, PubMed query, and other external API call
should go through track_and_execute() to enforce per-user daily limits and
record usage for billing/analytics.

Usage:
    from src.services.usage_tracker import track_and_execute

    result = await track_and_execute(
        user_id=user_id,
        api_type="exa",
        func=exa_client.search,
        query="competitive landscape",
    )
"""

import logging
import time
from datetime import date
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default daily call limits per API type per user
_DEFAULT_DAILY_LIMITS: dict[str, int] = {
    "exa": 500,
    "composio": 200,
    "pubmed": 300,
    "fda": 200,
    "chembl": 200,
    "clinicaltrials": 200,
    "resend": 100,
    "stripe": 50,
}

# Estimated cost per call in cents
_ESTIMATED_COST_CENTS: dict[str, float] = {
    "exa": 1.0,          # ~$0.01/call
    "composio": 0.5,     # ~$0.005/call
    "pubmed": 0.0,       # Free
    "fda": 0.0,          # Free
    "chembl": 0.0,       # Free
    "clinicaltrials": 0.0,  # Free
    "resend": 0.1,       # ~$0.001/email
    "stripe": 0.0,       # No per-call cost
}


class RateLimitExceeded(Exception):
    """Raised when a user exceeds their daily API call limit."""

    def __init__(self, api_type: str, limit: int) -> None:
        self.api_type = api_type
        self.limit = limit
        super().__init__(
            f"Daily limit of {limit} calls reached for {api_type}. "
            f"Usage resets at midnight UTC."
        )


async def check_rate_limit(user_id: str, api_type: str) -> bool:
    """Check if a user is within their daily rate limit for an API type.

    Args:
        user_id: The user's ID.
        api_type: The API type to check.

    Returns:
        True if within limits, False if exceeded.
    """
    limit = _DEFAULT_DAILY_LIMITS.get(api_type, 1000)

    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("api_usage_tracking")
            .select("call_count")
            .eq("user_id", user_id)
            .eq("date", date.today().isoformat())
            .eq("api_type", api_type)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            current_count = result.data.get("call_count", 0)
            return current_count < limit
        return True  # No usage row yet, within limits
    except Exception:
        # Fail-open: if we can't check, allow the call
        logger.debug("Rate limit check failed, allowing call", exc_info=True)
        return True


async def record_api_usage(
    user_id: str,
    api_type: str,
    success: bool = True,
    cost_cents: float | None = None,
) -> None:
    """Record an API call in the usage tracking table.

    Args:
        user_id: The user's ID.
        api_type: The API type (exa, composio, etc.).
        success: Whether the call succeeded.
        cost_cents: Override cost in cents (uses default estimate if None).
    """
    estimated_cost = cost_cents if cost_cents is not None else _ESTIMATED_COST_CENTS.get(api_type, 0)

    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        db.rpc(
            "increment_api_usage",
            {
                "p_user_id": user_id,
                "p_date": date.today().isoformat(),
                "p_api_type": api_type,
                "p_calls": 1,
                "p_errors": 0 if success else 1,
                "p_cost_cents": estimated_cost,
            },
        ).execute()
    except Exception:
        # Fail-open: never block work because tracking failed
        logger.debug("Failed to record API usage", exc_info=True)


async def track_and_execute(
    user_id: str,
    api_type: str,
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute an async function with rate limiting and usage tracking.

    Checks the user's daily rate limit, executes the function, and records
    the usage. If the rate limit is exceeded, raises RateLimitExceeded.

    Args:
        user_id: The user's ID.
        api_type: The API type (exa, composio, pubmed, etc.).
        func: The async function to execute.
        *args: Positional arguments for func.
        **kwargs: Keyword arguments for func.

    Returns:
        The result of func(*args, **kwargs).

    Raises:
        RateLimitExceeded: If the user has exceeded their daily limit.
    """
    if not await check_rate_limit(user_id, api_type):
        limit = _DEFAULT_DAILY_LIMITS.get(api_type, 1000)
        raise RateLimitExceeded(api_type, limit)

    start = time.monotonic()
    success = True
    try:
        result = await func(*args, **kwargs)
        return result
    except RateLimitExceeded:
        raise
    except Exception:
        success = False
        raise
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        await record_api_usage(user_id, api_type, success=success)
        logger.debug(
            "API call tracked",
            extra={
                "user_id": user_id,
                "api_type": api_type,
                "success": success,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )


async def get_user_api_usage(user_id: str, target_date: date | None = None) -> list[dict[str, Any]]:
    """Get a user's API usage summary for a given date.

    Args:
        user_id: The user's ID.
        target_date: Date to query (defaults to today).

    Returns:
        List of usage rows with api_type, call_count, error_count, cost_cents.
    """
    query_date = (target_date or date.today()).isoformat()

    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("api_usage_tracking")
            .select("api_type, call_count, error_count, cost_cents")
            .eq("user_id", user_id)
            .eq("date", query_date)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.debug("Failed to get API usage", exc_info=True)
        return []
