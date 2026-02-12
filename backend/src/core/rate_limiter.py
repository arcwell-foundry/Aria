"""Rate limiting middleware for ARIA API (US-930).

This module provides in-memory rate limiting using a sliding window algorithm.
It supports per-endpoint configuration and tracks requests by user_id or IP address.
"""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from fastapi import Request

from src.core.config import get_settings
from src.core.exceptions import RateLimitError


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests: Maximum number of requests allowed in the time window.
        window_seconds: Time window in seconds.
    """

    requests: int = 100
    window_seconds: int = 60


class RateLimitTracker:
    """Tracks rate limits using an in-memory sliding window.

    This implementation is simple and fast but not distributed.
    For production deployments with multiple workers, consider using Redis.
    """

    def __init__(self) -> None:
        """Initialize the rate limit tracker."""
        # Maps user_id/IP to list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
    ) -> bool:
        """Check if a request is allowed under the rate limit.

        Args:
            identifier: Unique identifier (user_id or IP address).
            config: Rate limit configuration.

        Returns:
            True if request is allowed, False if rate limit exceeded.
        """
        current_time = time.time()
        window_start = current_time - config.window_seconds

        # Get existing requests for this identifier
        request_timestamps = self._requests[identifier]

        # Remove old requests outside the time window
        # Filter in-place to maintain memory efficiency
        self._requests[identifier] = [ts for ts in request_timestamps if ts > window_start]

        # Check if under limit
        if len(self._requests[identifier]) < config.requests:
            # Add current request
            self._requests[identifier].append(current_time)
            return True

        return False

    def get_retry_after(
        self,
        identifier: str,
        config: RateLimitConfig,
    ) -> int:
        """Get seconds until the next request will be allowed.

        Args:
            identifier: Unique identifier (user_id or IP address).
            config: Rate limit configuration.

        Returns:
            Number of seconds until retry is allowed.
        """
        if not self._requests[identifier]:
            return 0

        # Get the oldest request timestamp
        oldest_timestamp = min(self._requests[identifier])
        window_expiry = oldest_timestamp + config.window_seconds
        retry_after = int(window_expiry - time.time())

        return max(0, retry_after)

    def reset_for_user(self, identifier: str) -> None:
        """Reset rate limit for a specific user.

        Args:
            identifier: Unique identifier (user_id or IP address).
        """
        self._requests.pop(identifier, None)

    def reset_all(self) -> None:
        """Reset all rate limits.

        Useful for testing or manual intervention.
        """
        self._requests.clear()


# Global rate limit tracker instance
_global_tracker = RateLimitTracker()


def get_rate_limit_config(path: str) -> RateLimitConfig:
    """Get rate limit configuration for a given API path.

    Different endpoints have different rate limits based on their cost:
    - Chat/generation endpoints: Stricter limits (expensive LLM calls)
    - Auth endpoints: Very strict limits (security sensitive)
    - Webhook endpoints: No limits (external services need reliability)
    - Default: Moderate limits

    Args:
        path: The API path being requested.

    Returns:
        Rate limit configuration for this path.
    """
    settings = get_settings()
    base_rpm = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

    # Chat and generation endpoints (expensive LLM operations)
    if path.startswith("/api/chat") or path.startswith("/api/generation"):
        return RateLimitConfig(
            requests=max(1, base_rpm // 10),  # 10% of base limit
            window_seconds=60,
        )

    # Document generation endpoints
    if path.startswith("/api/generate"):
        return RateLimitConfig(
            requests=max(1, base_rpm // 5),  # 20% of base limit
            window_seconds=60,
        )

    # Auth endpoints (security sensitive)
    if path.startswith("/api/auth"):
        return RateLimitConfig(
            requests=min(10, base_rpm // 10),  # Max 10 requests/minute
            window_seconds=60,
        )

    # Webhook endpoints (no limits - external services)
    if path.startswith("/api/webhooks"):
        return RateLimitConfig(
            requests=10_000,  # Effectively unlimited
            window_seconds=60,
        )

    # Admin endpoints (stricter limits)
    if path.startswith("/api/admin"):
        return RateLimitConfig(
            requests=max(1, base_rpm // 2),  # 50% of base limit
            window_seconds=60,
        )

    # Default configuration
    return RateLimitConfig(
        requests=base_rpm,
        window_seconds=60,
    )


def rate_limit(
    config: RateLimitConfig,
    tracker: RateLimitTracker | None = None,
) -> Callable[
    [Callable[..., Any]],
    Callable[..., Any],
]:
    """Decorator to apply rate limiting to an endpoint.

    Args:
        config: Rate limit configuration.
        tracker: Optional custom tracker (defaults to global tracker).

    Returns:
        Decorator function.

    Example:
        @rate_limit(RateLimitConfig(requests=10, window_seconds=60))
        async def my_endpoint(request: Request) -> JSONResponse:
            return JSONResponse(content={"message": "success"})
    """

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request from args (first argument for route handlers)
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request is None:
                # No request found, just call the function
                return await func(*args, **kwargs)

            # Check if rate limiting is enabled
            settings = get_settings()
            if not settings.RATE_LIMIT_ENABLED:
                return await func(*args, **kwargs)

            # Use provided tracker or global tracker
            active_tracker = tracker or _global_tracker

            # Get identifier: user_id from state or fall back to IP
            identifier: str
            if hasattr(request.state, "user_id"):
                identifier = str(request.state.user_id)
            else:
                # Fall back to client IP
                client = request.client
                identifier = client[0] if client else "unknown"

            # Check rate limit
            if not active_tracker.check_rate_limit(identifier, config):
                # Get retry_after value
                retry_after = active_tracker.get_retry_after(identifier, config)

                # Create limit string for error message
                limit_str = f"{config.requests}/{config.window_seconds} seconds"

                raise RateLimitError(
                    retry_after=retry_after,
                    limit=limit_str,
                )

            # Request allowed, proceed with endpoint
            return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "RateLimitConfig",
    "RateLimitTracker",
    "get_rate_limit_config",
    "rate_limit",
    "_global_tracker",
]
