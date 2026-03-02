"""Thesys C1 Generative UI API routes.

Provides on-demand visualization endpoints for converting ARIA's text
responses into rich interactive UI components via the Thesys C1 API.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
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


class EmbedRequest(BaseModel):
    """Request body for embed endpoint (full LLM proxy)."""

    messages: list[dict] = Field(
        ...,
        min_length=1,
        description="Full conversation history",
    )
    system_prompt: str | None = Field(
        None,
        description="Optional system prompt (defaults to ARIA_C1_SYSTEM_PROMPT)",
    )


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


@router.post(
    "/embed",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "SSE stream of C1-rendered content"},
        401: {"description": "Authentication required"},
        503: {"description": "Thesys service unavailable"},
    },
)
async def embed_stream(
    body: EmbedRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Streaming embed endpoint for exploratory queries.

    Uses C1's full LLM proxy (embed path) for cases where the optimal UI
    is unpredictable. C1 decides between tables, cards, charts, etc.

    This endpoint:
    - Uses base_url=https://api.thesys.dev/v1/embed
    - Accepts full conversation history (messages array)
    - Returns SSE stream with C1-rendered content
    - Includes custom actions in metadata

    Args:
        body: EmbedRequest with messages and optional system_prompt.
        current_user: JWT-authenticated user.

    Returns:
        StreamingResponse with text/event-stream content type.
    """
    if not settings.thesys_configured:
        raise HTTPException(
            status_code=503,
            detail="Thesys C1 service not configured",
        )

    from src.services.thesys_actions import get_aria_custom_actions
    from src.services.thesys_system_prompt import ARIA_C1_SYSTEM_PROMPT

    system_prompt = body.system_prompt or ARIA_C1_SYSTEM_PROMPT

    # Create client with embed base URL
    client = AsyncOpenAI(
        api_key=settings.THESYS_API_KEY.get_secret_value(),
        base_url="https://api.thesys.dev/v1/embed",
    )

    # Build messages with system prompt
    messages = [{"role": "system", "content": system_prompt}] + body.messages

    # Build metadata with custom actions
    metadata = {
        "thesys": json.dumps({
            "c1_custom_actions": get_aria_custom_actions(),
        }),
    }

    async def generate() -> AsyncIterator[str]:
        """Generate SSE chunks from C1 stream."""
        try:
            stream = await client.chat.completions.create(
                model="c1/anthropic/claude-haiku-4-5/latest",
                messages=messages,
                metadata=metadata,
                stream=True,
                timeout=settings.THESYS_TIMEOUT,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    # SSE format: data: <content>\n\n
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            # Send done marker
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Embed stream error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
