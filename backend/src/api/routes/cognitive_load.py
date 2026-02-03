"""Cognitive load API routes for ARIA.

This module provides endpoints for:
- Getting current cognitive load state
- Retrieving cognitive load history
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.models.cognitive_load import (
    CognitiveLoadHistoryResponse,
    CognitiveLoadSnapshotResponse,
    CognitiveLoadState,
    LoadLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/cognitive-load", response_model=CognitiveLoadState)
async def get_cognitive_load(
    current_user: CurrentUser,
) -> CognitiveLoadState:
    """Get current cognitive load state for the authenticated user.

    Returns the most recent cognitive load assessment including:
    - Load level (low, medium, high, critical)
    - Numeric score (0.0 to 1.0)
    - Individual factor scores
    - Response style recommendation
    """
    db = get_supabase_client()
    monitor = CognitiveLoadMonitor(db_client=db)

    try:
        state = await monitor.get_current_load(user_id=current_user.id)

        if state is None:
            # Return default low-load state when no data exists
            return CognitiveLoadState(
                level=LoadLevel.LOW,
                score=0.0,
                factors={},
                recommendation="detailed",
            )

        logger.info(
            "Cognitive load retrieved",
            extra={"user_id": current_user.id, "load_level": state.level.value},
        )

        return state

    except Exception:
        logger.exception(
            "Failed to get cognitive load", extra={"user_id": current_user.id}
        )
        raise HTTPException(
            status_code=503,
            detail="Cognitive load service temporarily unavailable",
        ) from None


@router.get("/cognitive-load/history", response_model=CognitiveLoadHistoryResponse)
async def get_cognitive_load_history(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum snapshots to return"),
) -> CognitiveLoadHistoryResponse:
    """Get cognitive load history for the authenticated user.

    Returns historical cognitive load snapshots with:
    - List of snapshots ordered by most recent first
    - Average score across the period
    - Trend indicator (improving, stable, worsening)
    """
    db = get_supabase_client()
    monitor = CognitiveLoadMonitor(db_client=db)

    try:
        history = await monitor.get_load_history(user_id=current_user.id, limit=limit)

        snapshots = [
            CognitiveLoadSnapshotResponse(
                id=snap["id"],
                user_id=snap["user_id"],
                load_level=snap["load_level"],
                load_score=snap["load_score"],
                factors=snap["factors"],
                session_id=snap.get("session_id"),
                measured_at=snap["measured_at"],
            )
            for snap in history
        ]

        # Calculate average score
        average_score: float | None = None
        if snapshots:
            average_score = sum(s.load_score for s in snapshots) / len(snapshots)

        # Determine trend (compare first half to second half)
        trend: str | None = None
        if len(snapshots) >= 4:
            mid = len(snapshots) // 2
            recent_avg = sum(s.load_score for s in snapshots[:mid]) / mid
            older_avg = sum(s.load_score for s in snapshots[mid:]) / (
                len(snapshots) - mid
            )
            if recent_avg < older_avg - 0.1:
                trend = "improving"
            elif recent_avg > older_avg + 0.1:
                trend = "worsening"
            else:
                trend = "stable"

        logger.info(
            "Cognitive load history retrieved",
            extra={
                "user_id": current_user.id,
                "snapshot_count": len(snapshots),
                "trend": trend,
            },
        )

        return CognitiveLoadHistoryResponse(
            snapshots=snapshots,
            average_score=average_score,
            trend=trend,
        )

    except Exception:
        logger.exception(
            "Failed to get cognitive load history", extra={"user_id": current_user.id}
        )
        raise HTTPException(
            status_code=503,
            detail="Cognitive load service temporarily unavailable",
        ) from None
