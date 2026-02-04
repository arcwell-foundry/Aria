"""Proactive insights API routes for ARIA.

This module provides endpoints for:
- Getting proactive insights based on current context
- Recording user engagement with surfaced insights
- Retrieving surfaced insights history
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.intelligence.proactive_memory import ProactiveMemoryService
from src.models.proactive_insight import ProactiveInsight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


class ProactiveInsightResponse(BaseModel):
    """Response model for a single proactive insight."""

    insight_type: str
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    source_memory_id: str
    source_memory_type: str
    explanation: str
    surfaced_record_id: str | None = None


class ProactiveInsightsResponse(BaseModel):
    """Response model for proactive insights endpoint."""

    insights: list[ProactiveInsightResponse]


class SurfacedInsightHistoryItem(BaseModel):
    """Response model for a surfaced insight history item."""

    id: str
    user_id: str
    memory_type: str
    memory_id: str
    insight_type: str
    context: str | None
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str | None
    surfaced_at: str
    engaged: bool
    engaged_at: str | None
    dismissed: bool
    dismissed_at: str | None


class SurfacedInsightsHistoryResponse(BaseModel):
    """Response model for surfaced insights history endpoint."""

    items: list[SurfacedInsightHistoryItem]


def _insight_to_response(
    insight: ProactiveInsight, surfaced_record_id: str | None = None
) -> ProactiveInsightResponse:
    """Convert a ProactiveInsight to a response model."""
    return ProactiveInsightResponse(
        insight_type=insight.insight_type.value,
        content=insight.content,
        relevance_score=insight.relevance_score,
        source_memory_id=insight.source_memory_id,
        source_memory_type=insight.source_memory_type,
        explanation=insight.explanation,
        surfaced_record_id=surfaced_record_id,
    )


@router.get("/proactive", response_model=ProactiveInsightsResponse)
async def get_proactive_insights(
    current_user: CurrentUser,
    context: str = Query(..., description="Current conversation context"),
    conversation_history: str = Query(
        default="", description="JSON-encoded conversation history (optional)"
    ),
) -> ProactiveInsightsResponse:
    """Get proactive insights based on current context.

    Returns insights that ARIA should volunteer to the user based on:
    - Pattern matches with past conversations
    - Temporal triggers (upcoming deadlines, follow-ups)
    - Goal relevance (relates to active user goals)

    Args:
        current_user: Authenticated user
        context: Current conversation context (e.g., topic being discussed)
        conversation_history: Optional JSON-encoded list of recent messages

    Returns:
        List of proactive insights to surface to the user
    """
    db = get_supabase_client()
    service = ProactiveMemoryService(db_client=db)

    try:
        # Parse conversation history if provided
        conversation_messages: list[dict[str, Any]] = []
        if conversation_history:
            try:
                conversation_messages = json.loads(conversation_history)
            except json.JSONDecodeError:
                logger.warning("Failed to parse conversation_history, using empty list")

        # Find insights worth surfacing
        insights = await service.find_volunteerable_context(
            user_id=current_user.id,
            current_message=context,
            conversation_messages=conversation_messages,
        )

        # Record surfaced insights and build response
        response_insights: list[ProactiveInsightResponse] = []
        for insight in insights:
            record_id = await service.record_surfaced(
                user_id=current_user.id,
                insight=insight,
                context=context,
            )
            response_insights.append(_insight_to_response(insight, record_id))

        logger.info(
            "Proactive insights retrieved",
            extra={
                "user_id": current_user.id,
                "insight_count": len(response_insights),
            },
        )

        return ProactiveInsightsResponse(insights=response_insights)

    except Exception:
        logger.exception("Failed to get proactive insights", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=503,
            detail="Proactive insights service temporarily unavailable",
        ) from None


@router.post("/{insight_id}/engage", status_code=204)
async def engage_insight(
    insight_id: str,
    current_user: CurrentUser,
) -> Response:
    """Mark an insight as engaged by the user.

    Records that the user found this insight valuable and interacted with it.
    This feedback helps improve future insight relevance scoring.

    Args:
        insight_id: ID of the surfaced_insights record
        current_user: Authenticated user

    Returns:
        204 No Content on success
    """
    db = get_supabase_client()
    service = ProactiveMemoryService(db_client=db)

    try:
        await service.record_engagement(
            insight_id=insight_id,
            engaged=True,
        )

        logger.info(
            "Insight engagement recorded",
            extra={
                "user_id": current_user.id,
                "insight_id": insight_id,
                "action": "engaged",
            },
        )

        return Response(status_code=204)

    except Exception:
        logger.exception(
            "Failed to record insight engagement",
            extra={"user_id": current_user.id, "insight_id": insight_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to record engagement",
        ) from None


@router.post("/{insight_id}/dismiss", status_code=204)
async def dismiss_insight(
    insight_id: str,
    current_user: CurrentUser,
) -> Response:
    """Mark an insight as dismissed by the user.

    Records that the user did not find this insight valuable.
    This feedback helps improve future insight relevance scoring.

    Args:
        insight_id: ID of the surfaced_insights record
        current_user: Authenticated user

    Returns:
        204 No Content on success
    """
    db = get_supabase_client()
    service = ProactiveMemoryService(db_client=db)

    try:
        await service.record_engagement(
            insight_id=insight_id,
            engaged=False,
        )

        logger.info(
            "Insight dismissal recorded",
            extra={
                "user_id": current_user.id,
                "insight_id": insight_id,
                "action": "dismissed",
            },
        )

        return Response(status_code=204)

    except Exception:
        logger.exception(
            "Failed to record insight dismissal",
            extra={"user_id": current_user.id, "insight_id": insight_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to record dismissal",
        ) from None


@router.get("/history", response_model=SurfacedInsightsHistoryResponse)
async def get_insights_history(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
    engaged_only: bool = Query(False, description="Only return insights user engaged with"),
) -> SurfacedInsightsHistoryResponse:
    """Get history of surfaced insights for the user.

    Returns historical record of insights that were surfaced to this user,
    useful for analytics and understanding what insights resonate.

    Args:
        current_user: Authenticated user
        limit: Maximum number of records to return (default 20, max 100)
        engaged_only: If True, only return insights user engaged with

    Returns:
        List of surfaced insight history items ordered by most recent
    """
    db = get_supabase_client()
    service = ProactiveMemoryService(db_client=db)

    try:
        history = await service.get_surfaced_history(
            user_id=current_user.id,
            limit=limit,
            engaged_only=engaged_only,
        )

        items = [
            SurfacedInsightHistoryItem(
                id=item["id"],
                user_id=item["user_id"],
                memory_type=item["memory_type"],
                memory_id=item["memory_id"],
                insight_type=item["insight_type"],
                context=item.get("context"),
                relevance_score=item["relevance_score"],
                explanation=item.get("explanation"),
                surfaced_at=item["surfaced_at"],
                engaged=item["engaged"],
                engaged_at=item.get("engaged_at"),
                dismissed=item["dismissed"],
                dismissed_at=item.get("dismissed_at"),
            )
            for item in history
        ]

        logger.info(
            "Insights history retrieved",
            extra={
                "user_id": current_user.id,
                "item_count": len(items),
                "engaged_only": engaged_only,
            },
        )

        return SurfacedInsightsHistoryResponse(items=items)

    except Exception:
        logger.exception("Failed to get insights history", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=503,
            detail="Insights history service temporarily unavailable",
        ) from None
