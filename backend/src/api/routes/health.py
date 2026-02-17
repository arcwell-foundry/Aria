"""Health check API routes.

Provides:
- GET /health — overall health with per-service dependency checks (public)
- GET /health/detailed — circuit breaker states, error summary, memory (admin only)
- GET /health/ping — lightweight 200 for external uptime monitors
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Response, status

from src.api.deps import AdminUser
from src.core.cache import cached
from src.core.error_tracker import ErrorTracker
from src.core.resilience import get_all_circuit_breakers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.monotonic()
_VERSION = "1.0.0"


@cached(ttl=30, key_func=lambda: "health_check")
async def _get_cached_health_check() -> dict[str, Any]:
    """Cached health check that tests actual dependencies.

    Separated from endpoint to allow caching without affecting route signature.
    """
    from src.core.monitoring import OverallStatus, run_health_checks

    result = await run_health_checks()
    result["uptime_seconds"] = round(time.monotonic() - _start_time, 1)
    result["version"] = _VERSION

    # Include circuit breaker states for extra context
    breakers = get_all_circuit_breakers()
    result["circuit_breakers"] = {
        name: cb.state.value for name, cb in breakers.items()
    }

    # Tag with overall status enum for callers that need it
    result["_overall"] = OverallStatus(result["status"])
    return result


@router.get("", status_code=status.HTTP_200_OK)
async def health_check(response: Response) -> dict[str, Any]:
    """Overall health check with dependency probes.

    Returns status, per-service health, uptime, and version.
    No authentication required.

    Render uses this to determine instance health:
    - 200 → healthy or degraded (keep running)
    - 503 → unhealthy / DB down (auto-restart)
    """
    from src.core.monitoring import OverallStatus

    result = await _get_cached_health_check()

    if result.get("_overall") == OverallStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Don't leak internal enum to response
    data = {k: v for k, v in result.items() if not k.startswith("_")}
    return data


@router.get("/ping", status_code=status.HTTP_200_OK)
async def ping() -> dict[str, str]:
    """Lightweight ping for external uptime monitors (e.g. UptimeRobot).

    No dependency checks, no auth. Returns 200 with current timestamp.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/detailed", status_code=status.HTTP_200_OK)
async def health_check_detailed(
    current_user: AdminUser,
) -> dict[str, Any]:
    """Detailed health check (admin only).

    Returns circuit breaker states, error summary, and memory usage.
    """
    from src.core.monitoring import run_health_checks

    breakers = get_all_circuit_breakers()
    circuit_breaker_data = {name: cb.to_dict() for name, cb in breakers.items()}

    tracker = ErrorTracker.get_instance()
    error_summary = tracker.get_error_summary(period_seconds=3600)

    # Run full dependency checks
    dep_checks = await run_health_checks()

    # Process memory info
    try:
        import resource

        rusage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = round(rusage.ru_maxrss / (1024 * 1024), 1)  # macOS reports bytes
    except Exception:
        rss_mb = 0.0

    return {
        "dependencies": dep_checks,
        "circuit_breakers": circuit_breaker_data,
        "errors": error_summary,
        "memory": {
            "rss_mb": rss_mb,
            "pid": os.getpid(),
        },
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "version": _VERSION,
    }
