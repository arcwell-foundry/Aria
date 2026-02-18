"""Trust Dashboard API routes.

Provides endpoints for viewing per-category trust profiles,
trust score history, and setting manual autonomy overrides.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from src.api.deps import CurrentUser
from src.core.trust import (
    TrustCalibrationService,
    get_trust_calibration_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trust", tags=["trust"])

VALID_OVERRIDE_MODES = {"always_approve", "plan_approval", "notify_only", "full_auto", "aria_decides"}

APPROVAL_LEVEL_LABELS = {
    "AUTO_EXECUTE": "Full Autonomy",
    "EXECUTE_AND_NOTIFY": "Notify After Execution",
    "APPROVE_PLAN": "Requires Plan Approval",
    "APPROVE_EACH": "Requires Step Approval",
}


class SetOverrideRequest(BaseModel):
    """Request body for setting a trust override mode."""

    mode: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in VALID_OVERRIDE_MODES:
            raise ValueError(f"Invalid mode. Must be one of: {sorted(VALID_OVERRIDE_MODES)}")
        return v


def _get_overrides(user_id: str) -> dict[str, str]:
    """Read trust_overrides from user_settings.preferences JSONB."""
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        result = (
            client.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data.get("preferences", {}).get("trust_overrides", {})
    except Exception:
        logger.exception("Failed to read trust overrides for user %s", user_id)
    return {}


def _save_overrides(user_id: str, overrides: dict[str, str]) -> None:
    """Write trust_overrides into user_settings.preferences JSONB."""
    from src.db.supabase import SupabaseClient

    client = SupabaseClient.get_client()
    result = (
        client.table("user_settings")
        .select("preferences")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        preferences = result.data.get("preferences", {})
        preferences["trust_overrides"] = overrides
        client.table("user_settings").update(
            {"preferences": preferences}
        ).eq("user_id", user_id).execute()
    else:
        client.table("user_settings").insert({
            "user_id": user_id,
            "preferences": {"trust_overrides": overrides},
        }).execute()


@router.get("/me")
async def get_trust_profiles(current_user: CurrentUser) -> list[dict[str, Any]]:
    """Get all per-category trust profiles for the current user."""
    service = get_trust_calibration_service()
    profiles = await service.get_all_profiles(current_user.id)
    overrides = _get_overrides(current_user.id)

    result = []
    for p in profiles:
        approval_level = TrustCalibrationService._compute_approval_level(p.trust_score, 0.3)
        can_upgrade = await service.can_request_autonomy_upgrade(current_user.id, p.action_category)
        result.append({
            "action_category": p.action_category,
            "trust_score": round(p.trust_score, 4),
            "successful_actions": p.successful_actions,
            "failed_actions": p.failed_actions,
            "override_count": p.override_count,
            "approval_level": approval_level,
            "approval_level_label": APPROVAL_LEVEL_LABELS.get(approval_level, approval_level),
            "can_request_upgrade": can_upgrade,
            "override_mode": overrides.get(p.action_category),
        })

    return result


@router.get("/me/history")
async def get_trust_history(
    current_user: CurrentUser,
    category: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    """Get trust score history for the current user."""
    service = get_trust_calibration_service()
    return await service.get_trust_history(current_user.id, category=category, days=days)


@router.put("/me/{category}/override")
async def set_trust_override(
    category: str,
    data: SetOverrideRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Set or remove a manual autonomy override for a category."""
    service = get_trust_calibration_service()
    profile = await service.get_trust_profile(current_user.id, category)

    overrides = _get_overrides(current_user.id)
    if data.mode == "aria_decides":
        overrides.pop(category, None)
    else:
        overrides[category] = data.mode

    try:
        _save_overrides(current_user.id, overrides)
    except Exception:
        logger.exception("Failed to save trust override for user %s", current_user.id)
        raise HTTPException(status_code=500, detail="Failed to save override") from None

    approval_level = TrustCalibrationService._compute_approval_level(profile.trust_score, 0.3)
    can_upgrade = await service.can_request_autonomy_upgrade(current_user.id, category)

    return {
        "action_category": profile.action_category,
        "trust_score": round(profile.trust_score, 4),
        "successful_actions": profile.successful_actions,
        "failed_actions": profile.failed_actions,
        "override_count": profile.override_count,
        "approval_level": approval_level,
        "approval_level_label": APPROVAL_LEVEL_LABELS.get(approval_level, approval_level),
        "can_request_upgrade": can_upgrade,
        "override_mode": overrides.get(category),
    }
