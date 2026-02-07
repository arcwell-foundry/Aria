"""ARIA API - Main FastAPI Application."""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from src.api.routes import (
    account,
    admin,
    analytics,
    aria_config,
    auth,
    battle_cards,
    billing,
    briefings,
    chat,
    cognitive_load,
    compliance,
    debriefs,
    drafts,
    email_preferences,
    feedback,
    goals,
    insights,
    integrations,
    leads,
    meetings,
    memory,
    notifications,
    onboarding,
    predictions,
    preferences,
    profile,
    search,
    signals,
    skills,
)
from src.core.exceptions import ARIAException, RateLimitError
from src.core.security import setup_security

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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
    from src.db.graphiti import GraphitiClient

    # Startup
    logger.info("Starting ARIA API...")
    yield
    # Shutdown
    logger.info("Shutting down ARIA API...")
    if GraphitiClient.is_initialized():
        await GraphitiClient.close()
        logger.info("Graphiti connection closed")


app = FastAPI(
    title="ARIA API",
    description="Autonomous Reasoning & Intelligence Agent - AI-powered Department Director",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware (US-932)
setup_security(app)

# Include API routers
app.include_router(account.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(aria_config.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(battle_cards.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(briefings.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(compliance.router, prefix="/api/v1")
app.include_router(debriefs.router, prefix="/api/v1")
app.include_router(drafts.router, prefix="/api/v1")
app.include_router(email_preferences.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(goals.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(meetings.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(cognitive_load.router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status of the API.
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
    request_id = str(uuid.uuid4())
    logger.warning(
        "Validation error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "errors": exc.error_count(),
        },
    )
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Validation error",
            "code": "VALIDATION_ERROR",
            "request_id": request_id,
            "errors": exc.errors(),
        },
    )


# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions globally.

    Args:
        request: The incoming request.
        exc: The unhandled exception.

    Returns:
        JSON error response.
    """
    request_id = str(uuid.uuid4())
    logger.exception(
        "Unhandled exception occurred",
        exc_info=exc,
        extra={
            "request_id": request_id,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred",
            "code": "INTERNAL_ERROR",
            "request_id": request_id,
        },
    )


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
