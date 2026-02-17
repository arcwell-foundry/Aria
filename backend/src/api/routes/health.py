"""Health check API routes.

Provides:
- GET /health — overall health with per-service status (public)
- GET /health/detailed — circuit breaker states, error summary, memory (admin only)
"""

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, status

from src.api.deps import AdminUser
from src.core.error_tracker import ErrorTracker
from src.core.resilience import CircuitState, get_all_circuit_breakers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.monotonic()
_VERSION = "1.0.0"


def _service_status(state: CircuitState) -> str:
    """Map circuit breaker state to a human-readable service status."""
    if state == CircuitState.CLOSED:
        return "up"
    if state == CircuitState.HALF_OPEN:
        return "degraded"
    return "down"


def _overall_status(services: dict[str, str]) -> str:
    """Derive overall health from individual service statuses."""
    if not services:
        return "healthy"
    statuses = set(services.values())
    if statuses == {"up"}:
        return "healthy"
    if statuses == {"down"}:
        return "unhealthy"
    # Mix of up/down/degraded → degraded
    return "degraded"


@router.get("", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, Any]:
    """Overall health check.

    Returns status, per-service health, uptime, and version.
    No authentication required.
    """
    breakers = get_all_circuit_breakers()
    services = {name: _service_status(cb.state) for name, cb in breakers.items()}

    return {
        "status": _overall_status(services),
        "services": services,
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "version": _VERSION,
    }


@router.get("/detailed", status_code=status.HTTP_200_OK)
async def health_check_detailed(
    current_user: AdminUser,
) -> dict[str, Any]:
    """Detailed health check (admin only).

    Returns circuit breaker states, error summary, and memory usage.
    """
    breakers = get_all_circuit_breakers()
    circuit_breaker_data = {name: cb.to_dict() for name, cb in breakers.items()}

    tracker = ErrorTracker.get_instance()
    error_summary = tracker.get_error_summary(period_seconds=3600)

    # Process memory info
    try:
        import resource

        rusage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = round(rusage.ru_maxrss / (1024 * 1024), 1)  # macOS reports bytes
    except Exception:
        rss_mb = 0.0

    return {
        "circuit_breakers": circuit_breaker_data,
        "errors": error_summary,
        "memory": {
            "rss_mb": rss_mb,
            "pid": os.getpid(),
        },
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "version": _VERSION,
    }
