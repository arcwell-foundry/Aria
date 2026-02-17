"""Production health monitoring with dependency checks.

Provides comprehensive health checks for all ARIA dependencies:
- Supabase DB (critical — unhealthy if down)
- Tavus API (non-critical — degraded if down)
- Claude/Anthropic API (non-critical — degraded if down)
- Exa API (non-critical — degraded if down)

Used by Render's healthCheckPath to auto-restart unhealthy instances.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Health status for an individual service."""

    UP = "up"
    DOWN = "down"
    UNCONFIGURED = "unconfigured"


class OverallStatus(str, Enum):
    """Overall application health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ServiceCheck:
    """Result of a single service health check."""

    name: str
    status: ServiceStatus
    latency_ms: float = 0.0
    message: str = ""
    critical: bool = False


async def check_supabase() -> ServiceCheck:
    """Check Supabase DB connectivity via a lightweight query."""
    start = time.perf_counter()
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        # Use a simple RPC or table query to verify connectivity
        response = client.table("user_profiles").select("id").limit(1).execute()
        latency = (time.perf_counter() - start) * 1000
        # If we get here without exception, DB is reachable
        return ServiceCheck(
            name="supabase",
            status=ServiceStatus.UP,
            latency_ms=round(latency, 2),
            critical=True,
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.error("Supabase health check failed: %s", e)
        return ServiceCheck(
            name="supabase",
            status=ServiceStatus.DOWN,
            latency_ms=round(latency, 2),
            message=str(e)[:200],
            critical=True,
        )


async def check_tavus() -> ServiceCheck:
    """Check Tavus API reachability."""
    start = time.perf_counter()
    try:
        from src.core.config import settings

        if not settings.TAVUS_API_KEY:
            return ServiceCheck(
                name="tavus",
                status=ServiceStatus.UNCONFIGURED,
                message="TAVUS_API_KEY not set",
            )

        from src.integrations.tavus import get_tavus_client

        client = get_tavus_client()
        is_healthy = await client.health_check()
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheck(
            name="tavus",
            status=ServiceStatus.UP if is_healthy else ServiceStatus.DOWN,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.warning("Tavus health check failed: %s", e)
        return ServiceCheck(
            name="tavus",
            status=ServiceStatus.DOWN,
            latency_ms=round(latency, 2),
            message=str(e)[:200],
        )


async def check_claude() -> ServiceCheck:
    """Check Anthropic Claude API reachability."""
    start = time.perf_counter()
    try:
        from src.core.config import settings

        if not settings.ANTHROPIC_API_KEY.get_secret_value():
            return ServiceCheck(
                name="claude",
                status=ServiceStatus.UNCONFIGURED,
                message="ANTHROPIC_API_KEY not set",
            )

        import anthropic

        client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
        )
        # Lightweight check — list models (minimal token cost)
        await client.models.list(limit=1)
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheck(
            name="claude",
            status=ServiceStatus.UP,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.warning("Claude API health check failed: %s", e)
        return ServiceCheck(
            name="claude",
            status=ServiceStatus.DOWN,
            latency_ms=round(latency, 2),
            message=str(e)[:200],
        )


async def check_exa() -> ServiceCheck:
    """Check Exa API reachability."""
    start = time.perf_counter()
    try:
        from src.core.config import settings

        if not settings.exa_configured:
            return ServiceCheck(
                name="exa",
                status=ServiceStatus.UNCONFIGURED,
                message="EXA_API_KEY not set",
            )

        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.exa.ai/search",
                headers={"x-api-key": settings.EXA_API_KEY},
            )
            latency = (time.perf_counter() - start) * 1000
            # 405 Method Not Allowed means the API is reachable
            # (GET not allowed on search, but server responded)
            if response.status_code in (200, 405, 422):
                return ServiceCheck(
                    name="exa",
                    status=ServiceStatus.UP,
                    latency_ms=round(latency, 2),
                )
            return ServiceCheck(
                name="exa",
                status=ServiceStatus.DOWN,
                latency_ms=round(latency, 2),
                message=f"HTTP {response.status_code}",
            )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        logger.warning("Exa API health check failed: %s", e)
        return ServiceCheck(
            name="exa",
            status=ServiceStatus.DOWN,
            latency_ms=round(latency, 2),
            message=str(e)[:200],
        )


async def run_health_checks() -> dict[str, Any]:
    """Run all dependency health checks and compute overall status.

    Returns:
        Dict with overall status, per-service results, and uptime.
        Render uses the HTTP status code from the calling endpoint:
        - 200 for healthy/degraded (instance keeps running)
        - 503 for unhealthy (Render auto-restarts)
    """
    import asyncio

    checks = await asyncio.gather(
        check_supabase(),
        check_tavus(),
        check_claude(),
        check_exa(),
        return_exceptions=True,
    )

    services: dict[str, dict[str, Any]] = {}
    db_down = False

    for result in checks:
        if isinstance(result, Exception):
            # Gather returned an exception for this check
            logger.error("Health check raised exception: %s", result)
            continue
        check: ServiceCheck = result
        services[check.name] = {
            "status": check.status.value,
            "latency_ms": check.latency_ms,
        }
        if check.message:
            services[check.name]["message"] = check.message
        if check.critical and check.status == ServiceStatus.DOWN:
            db_down = True

    # Determine overall status
    if db_down:
        overall = OverallStatus.UNHEALTHY
    elif any(
        s["status"] == ServiceStatus.DOWN.value
        for s in services.values()
    ):
        overall = OverallStatus.DEGRADED
    else:
        overall = OverallStatus.HEALTHY

    return {
        "status": overall.value,
        "services": services,
    }
