"""Account planning API routes for US-941.

Endpoints:
- GET  /accounts              — List accounts (territory view)
- GET  /accounts/{id}/plan    — Get or generate account plan
- PUT  /accounts/{id}/plan    — Update account plan strategy
- GET  /accounts/territory    — Territory overview (alias with stats)
- GET  /accounts/forecast     — Pipeline forecast
- GET  /accounts/quota        — Get quota records
- POST /accounts/quota        — Set/update quota
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.account_planning import AccountPlanUpdate, QuotaSet
from src.services.account_planning_service import AccountPlanningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_service() -> AccountPlanningService:
    """Get account planning service instance."""
    return AccountPlanningService()


# --- Static routes MUST come before parametric routes ---


@router.get("/territory")
async def get_territory(
    current_user: CurrentUser,
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    sort_by: str = Query("last_activity_at", description="Sort column"),
    limit: int = Query(50, ge=1, le=200, description="Max accounts"),
) -> dict[str, Any]:
    """Get territory overview with account list and summary stats.

    Returns accounts plus aggregate stats for the territory dashboard header.
    """
    service = _get_service()
    accounts = await service.list_accounts(current_user.id, stage, sort_by, limit)

    total_value = sum(float(a.get("expected_value") or 0) for a in accounts)
    avg_health = (
        round(sum(a.get("health_score", 0) for a in accounts) / len(accounts)) if accounts else 0
    )
    stage_counts: dict[str, int] = {}
    for a in accounts:
        s = a.get("lifecycle_stage", "lead")
        stage_counts[s] = stage_counts.get(s, 0) + 1

    logger.info(
        "Territory overview retrieved",
        extra={"user_id": current_user.id, "account_count": len(accounts)},
    )

    return {
        "accounts": accounts,
        "stats": {
            "total_accounts": len(accounts),
            "total_value": total_value,
            "avg_health": avg_health,
            "stage_counts": stage_counts,
        },
    }


@router.get("/forecast")
async def get_forecast(current_user: CurrentUser) -> dict[str, Any]:
    """Get pipeline forecast based on lead health scores and expected values."""
    service = _get_service()
    return await service.get_forecast(current_user.id)


@router.get("/quota")
async def get_quota(
    current_user: CurrentUser,
    period: str | None = Query(None, description="Filter by period"),
) -> list[dict[str, Any]]:
    """Get quota tracking records."""
    service = _get_service()
    return await service.get_quota(current_user.id, period)


@router.post("/quota")
async def set_quota(
    data: QuotaSet,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Set or update a quota target for a period."""
    service = _get_service()
    quota = await service.set_quota(current_user.id, data.period, data.target_value)
    logger.info(
        "Quota set via API",
        extra={"user_id": current_user.id, "period": data.period},
    )
    return quota


# --- Parametric routes ---


@router.get("")
async def list_accounts(
    current_user: CurrentUser,
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    sort_by: str = Query("last_activity_at", description="Sort column"),
    limit: int = Query(50, ge=1, le=200, description="Max accounts"),
) -> list[dict[str, Any]]:
    """List accounts from Lead Memory."""
    service = _get_service()
    return await service.list_accounts(current_user.id, stage, sort_by, limit)


@router.get("/{lead_id}/plan")
async def get_account_plan(
    lead_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get or auto-generate an account plan for a lead."""
    service = _get_service()
    plan = await service.get_or_generate_plan(current_user.id, lead_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return plan


@router.put("/{lead_id}/plan")
async def update_account_plan(
    lead_id: str,
    data: AccountPlanUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update account plan strategy text (user edits)."""
    service = _get_service()
    plan = await service.update_plan(current_user.id, lead_id, data.strategy)
    if plan is None:
        raise HTTPException(status_code=404, detail="Account plan not found")
    logger.info(
        "Account plan updated via API",
        extra={"user_id": current_user.id, "lead_id": lead_id},
    )
    return plan
