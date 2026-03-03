"""Health check API routes.

Provides:
- GET /health — overall health with per-service dependency checks (public)
- GET /health/detailed — circuit breaker states, error summary, memory (admin only)
- GET /health/ping — lightweight 200 for external uptime monitors
- POST /health/test-push — send test WebSocket notification (authenticated)
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from src.api.deps import AdminUser, CurrentUser
from src.core.cache import cached
from src.core.error_tracker import ErrorTracker
from src.core.resilience import get_all_circuit_breakers
from src.core.ws import ws_manager

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


@router.post("/circuit-breakers/{service_name}/reset", status_code=status.HTTP_200_OK)
async def reset_circuit_breaker(
    service_name: str,
    current_user: AdminUser,
) -> dict[str, Any]:
    """Reset a specific circuit breaker to CLOSED state (admin only).

    Use this to recover from transient outages without waiting for the
    recovery timeout to expire.
    """
    breakers = get_all_circuit_breakers()
    cb = breakers.get(service_name)
    if cb is None:
        return {
            "error": f"Unknown circuit breaker: {service_name}",
            "available": list(breakers.keys()),
        }
    previous_state = cb.state.value
    cb.reset()
    logger.info(
        "Circuit breaker %s reset by admin %s (was %s)",
        service_name,
        current_user.id,
        previous_state,
    )
    return {
        "service": service_name,
        "previous_state": previous_state,
        "current_state": cb.state.value,
    }


# ---------------------------------------------------------------------------
# WebSocket Push Test Endpoint
# ---------------------------------------------------------------------------


class TestPushRequest(BaseModel):
    """Request body for test push notification."""

    message: str = "WebSocket is alive"
    signal_type: str = "test"


class TestPushResponse(BaseModel):
    """Response for test push notification."""

    success: bool
    user_id: str
    connected: bool
    message: str
    timestamp: str


@router.post("/test-push", response_model=TestPushResponse)
async def test_push_notification(
    current_user: CurrentUser,
    request: TestPushRequest | None = None,
) -> TestPushResponse:
    """Send a test WebSocket notification to the authenticated user.

    This endpoint tests the real-time push pipeline by sending a signal
    event through the WebSocket connection. Use this to verify:
    - Backend WebSocket manager is functional
    - Frontend receives and displays the notification

    Args:
        current_user: The authenticated user (from JWT token).
        request: Optional custom message and signal type.

    Returns:
        Status of the push attempt including whether user is connected.
    """
    user_id = str(current_user.id)
    message = request.message if request else "WebSocket is alive"
    signal_type = request.signal_type if request else "test"
    timestamp = datetime.now(timezone.utc).isoformat()

    # Check if user has active WebSocket connection
    is_connected = ws_manager.is_connected(user_id)

    # Send signal event (will be queued if not connected)
    await ws_manager.send_signal(
        user_id=user_id,
        signal_type=signal_type,
        title="Test Notification",
        severity="medium",
        data={
            "message": message,
            "timestamp": timestamp,
            "test": True,
        },
    )

    return TestPushResponse(
        success=True,
        user_id=user_id,
        connected=is_connected,
        message=message,
        timestamp=timestamp,
    )


@router.post("/test-event")
async def test_event_trigger(
    request: Request,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Test the full event trigger pipeline with a synthetic email event."""
    from uuid import uuid4
    from src.services.event_trigger import (
        EventTriggerService,
        EventEnvelope,
        EventType,
        EventSource,
    )

    event_service: EventTriggerService = request.app.state.event_trigger_service
    user_id = str(current_user.id)

    envelope = EventEnvelope(
        event_type=EventType.EMAIL_RECEIVED,
        source=EventSource.INTERNAL,
        user_id=user_id,
        source_id=f"test-{uuid4()}",
        payload={
            "sender": "sarah@lonza.com",
            "subject": "Re: PFA Vessel Pricing Discussion",
            "snippet": "Hi, thanks for the follow-up. I've reviewed the pricing and have a few questions about volume discounts...",
            "messageId": f"test-msg-{uuid4()}",
            "threadId": "test-thread-001",
        },
    )

    result = await event_service.ingest(envelope)
    return {"test": "event_trigger_pipeline", "result": result}
