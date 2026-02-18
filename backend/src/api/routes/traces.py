"""Delegation trace API routes.

Provides read-only endpoints for viewing the delegation audit trail:
- GET /traces/{goal_id}/tree — full delegation tree for a goal
- GET /traces/recent — recent traces for the current user's activity feed
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.api.deps import CurrentUser
from src.core.delegation_trace import DelegationTraceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces", tags=["traces"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TraceSummary(BaseModel):
    """Aggregated summary computed from a goal's delegation traces."""

    agent_count: int
    unique_agents: list[str]
    total_cost_usd: float
    total_duration_ms: int
    verification_passes: int
    verification_failures: int
    retries: int


class TraceTreeResponse(BaseModel):
    """Response shape for GET /traces/{goal_id}/tree."""

    traces: list[dict[str, Any]]
    summary: TraceSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_summary(trace_dicts: list[dict[str, Any]]) -> TraceSummary:
    """Derive an aggregated summary from a list of serialized traces."""
    agents: list[str] = []
    total_cost = 0.0
    total_duration = 0
    v_passes = 0
    v_failures = 0
    retries = 0

    for t in trace_dicts:
        delegatee = t.get("delegatee", "")
        if delegatee and delegatee not in agents:
            agents.append(delegatee)

        total_cost += float(t.get("cost_usd", 0))
        total_duration += int(t.get("duration_ms", 0) or 0)

        vr = t.get("verification_result")
        if isinstance(vr, dict):
            if vr.get("passed"):
                v_passes += 1
            else:
                v_failures += 1

        if t.get("status") == "re_delegated":
            retries += 1

    return TraceSummary(
        agent_count=len(agents),
        unique_agents=agents,
        total_cost_usd=round(total_cost, 4),
        total_duration_ms=total_duration,
        verification_passes=v_passes,
        verification_failures=v_failures,
        retries=retries,
    )


def _get_service() -> DelegationTraceService:
    return DelegationTraceService()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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


@router.get("/{goal_id}/tree", response_model=TraceTreeResponse)
async def get_trace_tree(
    goal_id: str,
    current_user: CurrentUser,  # noqa: ARG001 — required for auth
) -> TraceTreeResponse:
    """Get the full delegation tree for a goal ("show your work")."""
    service = _get_service()
    traces = await service.get_trace_tree(goal_id=goal_id)
    trace_dicts = [t.to_dict() for t in traces]
    summary = _compute_summary(trace_dicts)
    return TraceTreeResponse(traces=trace_dicts, summary=summary)
