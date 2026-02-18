"""ARIA API - Main FastAPI Application."""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from src.api.routes import (
    account,
    accounts,
    action_queue,
    activity,
    admin,
    ambient_onboarding,
    analytics,
    aria_config,
    auth,
    autonomy,
    battle_cards,
    billing,
    briefings,
    chat,
    cognitive_load,
    communication,
    companion,  # Phase 8: Companion personality routes
    compliance,
    debriefs,
    deep_sync,  # US-942: Deep sync API routes
    drafts,
    email,  # Real-time email urgency detection
    email_preferences,
    feedback,
    goals,
    health,
    insights,
    integrations,
    intelligence,  # Phase 7: Causal intelligence routes
    leads,
    meetings,
    memory,
    notifications,
    onboarding,
    perception,
    persona,
    predictions,
    preferences,
    profile,
    search,
    signals,
    skill_replay,
    skills,
    social,
    usage,  # Wave 0: Cost Governor usage tracking
    video,
    webhooks,  # Tavus webhook handler
    websets,  # Phase 3: Websets integration
    workflows,
)
from src.api.routes import (
    websocket as ws_route,
)
from src.api.routes.companion import (
    emotional_router as companion_emotional_router,  # US-804: Emotional Intelligence
)
from src.api.routes.companion import (
    reflection_router as companion_reflection_router,  # US-806: Self-Reflection
)
from src.api.routes.companion import (
    strategy_router as companion_strategy_router,  # US-805: Strategic Planning
)
from src.api.routes.companion import (
    improvement_router as companion_improvement_router,  # US-809: Self-Improvement
)
from src.api.routes.companion import (
    narrative_router as companion_narrative_router,  # US-807: Narrative Identity
)
from src.api.routes.companion import user_router as companion_user_router  # US-802: Theory of Mind
from src.core.error_tracker import ErrorTracker
from src.core.exceptions import ARIAException, RateLimitError
from src.core.security import setup_security
from src.middleware.performance import RequestIDMiddleware, RequestTimingMiddleware

# Configure logging — JSON for production (Render captures stdout), text for dev
def _configure_logging() -> None:
    """Set up logging based on LOG_FORMAT env var.

    json: Structured JSON via python-json-logger (for Render/production).
    text: Human-readable format (for local development).
    """
    import os

    log_format = os.environ.get("LOG_FORMAT", "text").lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()

    handler = logging.StreamHandler()

    if log_format == "json":
        from pythonjsonlogger.json import JsonFormatter

        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "service",
            },
            static_fields={"app": "aria-api"},
        )
        handler.setFormatter(formatter)
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root_logger.addHandler(handler)


_configure_logging()
logger = logging.getLogger(__name__)


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment or use defaults.

    Returns:
        List of allowed CORS origins.
    """
    try:
        from src.core.config import settings

        return settings.cors_origins_list
    except Exception:
        # Fallback to defaults if config not available
        return [
            "http://localhost:3000",
            "http://localhost:5173",
        ]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    """Application lifespan handler for startup and shutdown events."""
    from src.core.config import settings
    from src.db.graphiti import GraphitiClient
    from src.integrations.sync_scheduler import get_sync_scheduler  # US-942: Sync scheduler

    # Startup
    logger.info("Starting ARIA API...")

    # Log EXA API key status for enrichment diagnostics
    if settings.exa_configured:
        # Check if Exa has available credits
        has_credits, message = await settings.check_exa_credits()
        if has_credits:
            logger.info("EXA_API_KEY configured - web enrichment enabled")
        else:
            logger.warning("EXA_API_KEY configured but %s", message)
    else:
        logger.warning("EXA_API_KEY not configured - web enrichment DISABLED")
    # US-942: Start the sync scheduler
    scheduler = get_sync_scheduler()
    await scheduler.start()
    # P2-36: Start ambient gap filler scheduler
    from src.services.scheduler import start_scheduler as start_ambient_scheduler

    await start_ambient_scheduler()
    # Generate any missing daily briefings on startup
    try:
        import asyncio

        from src.jobs.daily_briefing_job import run_startup_briefing_check

        asyncio.create_task(run_startup_briefing_check())
        logger.info("Daily briefing startup check scheduled")
    except Exception:
        logger.exception("Failed to schedule daily briefing startup check")
    yield
    # Shutdown
    logger.info("Shutting down ARIA API...")
    # US-942: Stop the sync scheduler
    await scheduler.stop()
    # P2-36: Stop ambient gap filler scheduler
    from src.services.scheduler import stop_scheduler as stop_ambient_scheduler

    await stop_ambient_scheduler()
    if GraphitiClient.is_initialized():
        await GraphitiClient.close()
        logger.info("Graphiti connection closed")


app = FastAPI(
    title="ARIA API",
    description="Autonomous Reasoning & Intelligence Agent - AI-powered Department Director",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS origins — read from CORS_ORIGINS env var via config, with local fallbacks
CORS_ORIGINS = get_cors_origins()
logger.info("CORS allowed origins: %s", CORS_ORIGINS)

# Performance middleware — timing wraps request-ID so ID is available when timing logs.
# In Starlette, last-added = outermost, so add timing first, then ID.
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Security headers middleware (US-932) — added first so it's innermost
setup_security(app)

# CORS Configuration — added last so it's outermost (handles preflight first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(account.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(action_queue.router, prefix="/api/v1")
app.include_router(activity.router, prefix="/api/v1")
app.include_router(autonomy.router, prefix="/api/v1")
app.include_router(ambient_onboarding.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(aria_config.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(battle_cards.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(briefings.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(cognitive_load.router, prefix="/api/v1")
app.include_router(communication.router, prefix="/api/v1")
app.include_router(companion.router, prefix="/api/v1")  # Phase 8: Companion personality
app.include_router(companion_user_router, prefix="/api/v1")  # US-802: Theory of Mind
app.include_router(companion_emotional_router, prefix="/api/v1")  # US-804: Emotional Intelligence
app.include_router(companion_strategy_router, prefix="/api/v1")  # US-805: Strategic Planning
app.include_router(companion_reflection_router, prefix="/api/v1")  # US-806: Self-Reflection
app.include_router(companion_narrative_router, prefix="/api/v1")  # US-807: Narrative Identity
app.include_router(companion_improvement_router, prefix="/api/v1")  # US-809: Self-Improvement
app.include_router(compliance.router, prefix="/api/v1")
app.include_router(debriefs.router, prefix="/api/v1")
app.include_router(drafts.router, prefix="/api/v1")
app.include_router(email.router, prefix="/api/v1")
app.include_router(email_preferences.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(goals.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")  # Phase 7: Causal intelligence
app.include_router(leads.router, prefix="/api/v1")
app.include_router(meetings.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(perception.router, prefix="/api/v1")
app.include_router(persona.router, prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(skill_replay.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(social.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")  # Wave 0: Cost Governor
app.include_router(video.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(websets.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")

# US-942: Deep sync routes
app.include_router(deep_sync.router, prefix="/api/v1")

# WebSocket endpoint (no /api/v1 prefix — connects at /ws/{user_id})
app.include_router(ws_route.router)


@app.get("/health", tags=["system"])
async def root_health_check() -> dict[str, str]:
    """Root health check endpoint (used by Render healthCheckPath).

    Lightweight check — returns 200 if the process is running.
    For dependency-aware checks, use /api/v1/health.
    """
    return {"status": "healthy"}


@app.get("/health/neo4j", tags=["system"])
async def health_check_neo4j() -> dict[str, str]:
    """Health check endpoint for Neo4j/Graphiti connection.

    Returns:
        Health status of the Neo4j connection.
    """
    from src.db.graphiti import GraphitiClient

    is_healthy = await GraphitiClient.health_check()
    return {"status": "healthy" if is_healthy else "unhealthy"}


@app.get("/health/tavus", tags=["system"])
async def health_check_tavus() -> dict[str, str]:
    """Health check endpoint for Tavus API connectivity.

    Returns:
        Health status of the Tavus API connection.
    """
    from src.integrations.tavus import get_tavus_client

    client = get_tavus_client()
    is_healthy = await client.health_check()
    return {"service": "tavus", "status": "healthy" if is_healthy else "unhealthy"}


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Root endpoint with API information.

    Returns:
        Basic API information.
    """
    return {
        "name": "ARIA API",
        "version": "1.0.0",
        "description": "Autonomous Reasoning & Intelligence Agent",
    }


# Custom ARIA exception handler
@app.exception_handler(ARIAException)
async def aria_exception_handler(request: Request, exc: ARIAException) -> JSONResponse:
    """Handle ARIA-specific exceptions.

    Args:
        request: The incoming request.
        exc: The ARIA exception.

    Returns:
        JSON error response with consistent format.
    """
    request_id = str(uuid.uuid4())
    logger.warning(
        "ARIA exception occurred",
        extra={
            "code": exc.code,
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
        },
    )
    ErrorTracker.get_instance().record_error(
        service="api",
        error_type=exc.code,
        message=f"{request.method} {request.url.path}: {exc.message}",
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "request_id": request_id,
        },
    )


# Pydantic validation error handler
@app.exception_handler(PydanticValidationError)
async def pydantic_validation_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors.

    Args:
        request: The incoming request.
        exc: The validation exception.

    Returns:
        JSON error response with validation details.
    """
    import json

    request_id = str(uuid.uuid4())
    # DEBUG: Log full validation error details
    logger.error(
        "PYDANTIC VALIDATION ERROR",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_count": exc.error_count(),
            "errors": json.dumps(exc.errors(), default=str),
        },
    )
    # Also print to stdout for immediate visibility
    print(f"\n{'='*60}")
    print(f"PYDANTIC VALIDATION ERROR on {request.method} {request.url.path}")
    print(f"Errors: {json.dumps(exc.errors(), indent=2, default=str)}")
    print(f"{'='*60}\n")

    return JSONResponse(
        status_code=400,
        content={
            "detail": "Validation error",
            "code": "VALIDATION_ERROR",
            "request_id": request_id,
            "errors": exc.errors(),
        },
    )


# FastAPI Request validation error handler (catches body parsing errors)
@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI request validation errors.

    This catches errors during request body parsing and validation.

    Args:
        request: The incoming request.
        exc: The validation exception.

    Returns:
        JSON error response with validation details.
    """
    import json

    request_id = str(uuid.uuid4())
    # DEBUG: Log full validation error details
    logger.error(
        "REQUEST VALIDATION ERROR",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "errors": json.dumps(exc.errors(), default=str),
        },
    )
    # Also print to stdout for immediate visibility
    print(f"\n{'='*60}")
    print(f"REQUEST VALIDATION ERROR on {request.method} {request.url.path}")
    print(f"Errors: {json.dumps(exc.errors(), indent=2, default=str)}")
    print(f"{'='*60}\n")

    return JSONResponse(
        status_code=400,
        content={
            "detail": "Request validation error",
            "code": "REQUEST_VALIDATION_ERROR",
            "request_id": request_id,
            "errors": exc.errors(),
        },
    )


# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions globally.

    Returns a JSON response with CORS headers so the browser doesn't
    mask the real error as a CORS failure.
    """
    import traceback

    traceback.print_exc()

    request_id = str(uuid.uuid4())
    logger.exception(
        "Unhandled exception occurred",
        exc_info=exc,
        extra={
            "request_id": request_id,
            "path": request.url.path,
        },
    )
    ErrorTracker.get_instance().record_error(
        service="api",
        error_type=type(exc).__name__,
        message=f"{request.method} {request.url.path}: {exc}",
    )

    # Build response with explicit CORS headers so the browser
    # can read the error instead of reporting a CORS failure.
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred",
            "code": "INTERNAL_ERROR",
            "request_id": request_id,
        },
    )
    if origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


# Rate limit exception handler
@app.exception_handler(RateLimitError)
async def rate_limit_exception_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    """Handle rate limit exceeded errors.

    Args:
        request: The incoming request.
        exc: The rate limit exception.

    Returns:
        JSON error response with retry information.
    """
    request_id = str(uuid.uuid4())
    logger.warning(
        "Rate limit exceeded",
        extra={
            "code": exc.code,
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "details": exc.details,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "request_id": request_id,
            "retry_after": exc.details.get("retry_after"),
            "limit": exc.details.get("limit"),
        },
    )
