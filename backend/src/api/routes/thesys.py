"""Thesys C1 Generative UI API routes.

Provides on-demand visualization endpoints for converting ARIA's text
responses into rich interactive UI components via the Thesys C1 API.
"""

import logging
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser, get_current_user
from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/thesys", tags=["thesys"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class VisualizeRequest(BaseModel):
    """Request body for visualization endpoints."""

    content: str = Field(..., min_length=1, description="Text content to visualize")
    content_type: str | None = Field(None, description="Content type hint")
    conversation_id: str | None = Field(None, description="Conversation ID for context")


class VisualizeSyncResponse(BaseModel):
    """Response from synchronous visualization."""

    rendered_content: str
    render_mode: str  # "c1" or "markdown"
    content_type: str | None = None


class HealthResponse(BaseModel):
    """Thesys service health status."""

    configured: bool
    available: bool = False
    circuit_breaker: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def thesys_health(current_user: CurrentUser) -> HealthResponse:
    """Check Thesys C1 service health and circuit breaker state."""
    if not settings.thesys_configured:
        return HealthResponse(configured=False)

    from src.core.resilience import thesys_circuit_breaker
    from src.services.thesys_service import get_thesys_service

    svc = get_thesys_service()
    return HealthResponse(
        configured=True,
        available=svc.is_available,
        circuit_breaker=thesys_circuit_breaker.to_dict(),
    )


@router.post(
    "/visualize/sync",
    response_model=VisualizeSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def visualize_sync(
    body: VisualizeRequest,
    current_user: CurrentUser,
) -> VisualizeSyncResponse:
    """Synchronous (non-streaming) visualization of content through C1.

    Returns the full rendered content in a single response. Falls back
    to raw markdown if C1 is unavailable or the content isn't eligible.
    """
    if not settings.thesys_configured:
        return VisualizeSyncResponse(
            rendered_content=body.content,
            render_mode="markdown",
            content_type=body.content_type,
        )

    from src.services.thesys_classifier import ThesysRoutingClassifier
    from src.services.thesys_service import get_thesys_service
    from src.services.thesys_system_prompt import build_system_prompt

    should, detected_type = ThesysRoutingClassifier.classify(body.content)
    content_type = body.content_type or detected_type

    if not should and not body.content_type:
        return VisualizeSyncResponse(
            rendered_content=body.content,
            render_mode="markdown",
            content_type=content_type,
        )

    svc = get_thesys_service()
    if not svc.is_available:
        return VisualizeSyncResponse(
            rendered_content=body.content,
            render_mode="markdown",
            content_type=content_type,
        )

    system_prompt = build_system_prompt(content_type)
    rendered = await svc.visualize(body.content, system_prompt)
    render_mode = "c1" if rendered != body.content else "markdown"

    return VisualizeSyncResponse(
        rendered_content=rendered,
        render_mode=render_mode,
        content_type=content_type,
    )
