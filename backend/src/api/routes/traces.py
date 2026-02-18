"""Delegation trace API routes.

Provides read-only endpoints for viewing the delegation audit trail:
- GET /traces/{goal_id}/tree — full delegation tree for a goal
- GET /traces/recent — recent traces for the current user's activity feed
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from src.api.deps import CurrentUser
from src.core.delegation_trace import DelegationTraceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces", tags=["traces"])


def _get_service() -> DelegationTraceService:
    return DelegationTraceService()


@router.get("/recent")
async def get_recent_traces(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Get recent delegation traces for the activity feed."""
    service = _get_service()
    traces = await service.get_user_traces(
        user_id=current_user.id,
        limit=limit,
    )
    return [t.to_dict() for t in traces]


@router.get("/{goal_id}/tree")
async def get_trace_tree(
    goal_id: str,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get the full delegation tree for a goal ("show your work")."""
    service = _get_service()
    traces = await service.get_trace_tree(goal_id=goal_id)
    return [t.to_dict() for t in traces]
