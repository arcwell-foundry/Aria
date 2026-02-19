"""Admin Dashboard API Routes.

Provides endpoints for the developer/admin dashboard monitoring system.
All endpoints require admin role access.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from src.api.deps import AdminUser
from src.services.admin_dashboard_service import AdminDashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])
service = AdminDashboardService()


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class DashboardOverviewResponse(BaseModel):
    """Top-level KPIs for the admin dashboard."""

    active_users: int = 0
    cost_today: float = 0.0
    active_ooda: int = 0
    pass_rate: float = 0.0
    avg_trust: float = 0.0
    cost_alert: bool = False


class ActiveOODACycle(BaseModel):
    """Summary of an active OODA cycle."""

    cycle_id: str
    goal_id: str
    user_id: str = ""
    current_phase: str = ""
    iteration: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
    phases_completed: int = 0
    agents_dispatched: list[str] = Field(default_factory=list)
    started_at: str = ""


class AgentExecution(BaseModel):
    """Single agent execution record for waterfall view."""

    trace_id: str
    delegatee: str = ""
    status: str = ""
    cost_usd: float = 0.0
    created_at: str = ""
    task_description: str = ""
    input_size: int = 0
    output_size: int = 0
    verification_passed: bool | None = None


class UserUsageSummary(BaseModel):
    """Per-user usage aggregation."""

    user_id: str
    total_cost: float = 0.0
    total_tokens: int = 0
    total_thinking_tokens: int = 0
    total_calls: int = 0
    days_active: int = 0


class DailyTotal(BaseModel):
    """Daily usage total."""

    date: str
    cost: float = 0.0
    tokens: int = 0
    thinking_tokens: int = 0


class UsageAlert(BaseModel):
    """Cost alert for a user exceeding threshold."""

    user_id: str
    date: str
    cost: float = 0.0
    message: str = ""


class TeamUsageResponse(BaseModel):
    """Team-wide usage data."""

    users: list[UserUsageSummary] = Field(default_factory=list)
    daily_totals: list[DailyTotal] = Field(default_factory=list)
    alerts: list[UsageAlert] = Field(default_factory=list)


class TrustCategory(BaseModel):
    """Trust score for a single action category."""

    action_category: str
    trust_score: float = 0.0
    successful_actions: int = 0
    failed_actions: int = 0
    override_count: int = 0


class UserTrustSummary(BaseModel):
    """Per-user trust overview."""

    user_id: str
    avg_trust: float = 0.0
    categories: list[TrustCategory] = Field(default_factory=list)
    is_stuck: bool = False
    total_actions: int = 0


class TrustEvolutionPoint(BaseModel):
    """Single point in the trust time series."""

    user_id: str
    action_category: str = ""
    trust_score: float = 0.0
    change_type: str = ""
    recorded_at: str = ""


class AgentVerificationStats(BaseModel):
    """Verification stats for a single agent."""

    agent: str
    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_rate: float = 0.0


class TaskTypeVerificationStats(BaseModel):
    """Verification stats for a single task type."""

    task_type: str
    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_rate: float = 0.0


class VerificationStatsResponse(BaseModel):
    """Verification pass/fail breakdown."""

    overall_pass_rate: float = 0.0
    total_verified: int = 0
    total_passed: int = 0
    worst_agent: str = ""
    by_agent: list[AgentVerificationStats] = Field(default_factory=list)
    by_task_type: list[TaskTypeVerificationStats] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    status_code=status.HTTP_200_OK,
)
async def get_overview(
    _current_user: AdminUser,
) -> dict[str, Any]:
    """Dashboard overview with top-level KPIs.

    Args:
        _current_user: Authenticated admin user.

    Returns:
        Overview metrics.
    """
    return await service.get_dashboard_overview()


@router.get(
    "/ooda/active",
    response_model=list[ActiveOODACycle],
    status_code=status.HTTP_200_OK,
)
async def get_active_ooda_cycles(
    _current_user: AdminUser,
    limit: int = Query(50, ge=1, le=200, description="Max cycles to return"),
) -> list[dict[str, Any]]:
    """Active OODA cycles for real-time monitoring.

    Args:
        _current_user: Authenticated admin user.
        limit: Maximum number of cycles.

    Returns:
        List of active OODA cycle summaries.
    """
    return await service.get_active_ooda_cycles(limit=limit)


@router.get(
    "/agents/waterfall",
    response_model=list[AgentExecution],
    status_code=status.HTTP_200_OK,
)
async def get_agent_waterfall(
    _current_user: AdminUser,
    hours: int = Query(24, ge=1, le=168, description="Hours of history"),
    limit: int = Query(200, ge=1, le=1000, description="Max executions"),
) -> list[dict[str, Any]]:
    """Agent execution timeline for waterfall visualization.

    Args:
        _current_user: Authenticated admin user.
        hours: How far back to look.
        limit: Maximum executions to return.

    Returns:
        List of agent execution records.
    """
    return await service.get_agent_waterfall(hours=hours, limit=limit)


@router.get(
    "/usage",
    response_model=TeamUsageResponse,
    status_code=status.HTTP_200_OK,
)
async def get_team_usage(
    _current_user: AdminUser,
    days: int = Query(30, ge=1, le=90, description="Days of history"),
    granularity: str = Query("day", description="Aggregation level (day/week)"),
) -> dict[str, Any]:
    """Team token usage over time with cost alerts.

    Args:
        _current_user: Authenticated admin user.
        days: How far back to look.
        granularity: Aggregation level.

    Returns:
        Team usage data with per-user breakdown and alerts.
    """
    return await service.get_team_usage(days=days, granularity=granularity)


@router.get(
    "/trust/summaries",
    response_model=list[UserTrustSummary],
    status_code=status.HTTP_200_OK,
)
async def get_trust_summaries(
    _current_user: AdminUser,
) -> list[dict[str, Any]]:
    """Per-user trust overview with stuck user detection.

    Args:
        _current_user: Authenticated admin user.

    Returns:
        List of user trust summaries.
    """
    return await service.get_trust_summaries()


@router.get(
    "/trust/evolution",
    response_model=list[TrustEvolutionPoint],
    status_code=status.HTTP_200_OK,
)
async def get_trust_evolution(
    _current_user: AdminUser,
    user_id: str | None = Query(None, description="Filter by user ID"),
    days: int = Query(30, ge=1, le=365, description="Days of history"),
) -> list[dict[str, Any]]:
    """Trust score time series with change events.

    Args:
        _current_user: Authenticated admin user.
        user_id: Optional user filter.
        days: How far back to look.

    Returns:
        List of trust evolution data points.
    """
    return await service.get_trust_evolution(user_id=user_id, days=days)


@router.get(
    "/verification",
    response_model=VerificationStatsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_verification_stats(
    _current_user: AdminUser,
    days: int = Query(30, ge=1, le=365, description="Days of history"),
) -> dict[str, Any]:
    """Verification pass/fail rates by agent and task type.

    Args:
        _current_user: Authenticated admin user.
        days: How far back to look.

    Returns:
        Verification statistics with breakdowns.
    """
    return await service.get_verification_stats(days=days)
