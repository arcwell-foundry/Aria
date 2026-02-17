"""Autonomy API routes for ARIA.

Provides endpoints for querying and adjusting ARIA's autonomy level.
The autonomy level determines which action risk levels ARIA can auto-execute
without user approval.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.api.deps import CurrentUser
from src.services.action_queue_service import ActionQueueService
from src.services.autonomy_calibration import get_autonomy_calibration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autonomy", tags=["autonomy"])

# Tier <-> backend level mapping
TIER_TO_LEVEL: dict[str, int] = {
    "guided": 1,
    "assisted": 3,
    "autonomous": 4,
}

LEVEL_TO_TIER: dict[int, str] = {
    1: "guided",
    2: "guided",
    3: "assisted",
    4: "autonomous",
    5: "autonomous",
}

TIER_DESCRIPTIONS: dict[str, str] = {
    "guided": "ARIA suggests actions, you approve everything",
    "assisted": "ARIA auto-executes low-risk actions, asks for medium and above",
    "autonomous": "ARIA auto-executes low and medium-risk, asks for high and above",
}


class SetTierRequest(BaseModel):
    """Request body for setting the autonomy tier."""

    tier: str

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in TIER_TO_LEVEL:
            raise ValueError(f"Invalid tier. Must be one of: {list(TIER_TO_LEVEL.keys())}")
        return v


@router.get("/status")
async def get_autonomy_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get the current autonomy status for the user.

    Returns the current tier, recommended tier, selectable tiers,
    action statistics, and recent actions.
    """
    calibration = get_autonomy_calibration_service()
    action_service = ActionQueueService()

    # Get current and recommended levels
    recommended = await calibration.calculate_autonomy_level(current_user.id)
    recommended_level = recommended["level"]
    recommended_tier = LEVEL_TO_TIER.get(recommended_level, "guided")

    # Get current stored level
    current_level = await calibration._get_autonomy_level(current_user.id)
    current_tier = LEVEL_TO_TIER.get(current_level, "guided")

    # Determine selectable tiers (lower or equal to recommended)
    recommended_backend_level = TIER_TO_LEVEL.get(recommended_tier, 1)
    can_select = [
        tier for tier, level in TIER_TO_LEVEL.items()
        if level <= recommended_backend_level
    ]

    # Get action stats
    stats = await calibration._get_action_stats(current_user.id)
    total_actions = stats["total"]
    approval_rate = (
        stats["completed"] / total_actions if total_actions > 0 else 0.0
    )

    # Get recent actions
    recent_actions = await action_service.get_queue(current_user.id, limit=10)

    logger.info(
        "Autonomy status retrieved",
        extra={
            "user_id": current_user.id,
            "current_tier": current_tier,
            "recommended_tier": recommended_tier,
        },
    )

    return {
        "current_level": current_level,
        "current_tier": current_tier,
        "recommended_level": recommended_level,
        "recommended_tier": recommended_tier,
        "can_select_tiers": can_select,
        "stats": {
            "total_actions": total_actions,
            "approval_rate": round(approval_rate, 2),
            "auto_executed": stats["completed"],
            "rejected": stats["rejected"],
        },
        "recent_actions": [
            {
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "action_type": a.get("action_type", ""),
                "risk_level": a.get("risk_level", ""),
                "status": a.get("status", ""),
                "agent": a.get("agent", ""),
                "created_at": a.get("created_at", ""),
            }
            for a in recent_actions
        ],
    }


@router.post("/level")
async def set_autonomy_level(
    data: SetTierRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Set the user's autonomy tier.

    Validates that the requested tier does not exceed the recommended level.
    """
    calibration = get_autonomy_calibration_service()

    # Get recommended level to enforce lower-only constraint
    recommended = await calibration.calculate_autonomy_level(current_user.id)
    recommended_level = recommended["level"]
    recommended_tier = LEVEL_TO_TIER.get(recommended_level, "guided")
    recommended_backend_level = TIER_TO_LEVEL.get(recommended_tier, 1)

    requested_level = TIER_TO_LEVEL[data.tier]
    if requested_level > recommended_backend_level:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot set tier above recommended level. Maximum: {recommended_tier}",
        )

    # Write to user_settings
    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()

    try:
        # Try to update existing settings
        result = (
            db.table("user_settings")
            .select("preferences")
            .eq("user_id", current_user.id)
            .maybe_single()
            .execute()
        )

        if result and result.data:
            preferences = result.data.get("preferences", {})
            preferences["autonomy_level"] = requested_level
            db.table("user_settings").update(
                {"preferences": preferences}
            ).eq("user_id", current_user.id).execute()
        else:
            db.table("user_settings").insert({
                "user_id": current_user.id,
                "preferences": {"autonomy_level": requested_level},
            }).execute()
    except Exception:
        logger.exception(
            "Failed to save autonomy level",
            extra={"user_id": current_user.id, "tier": data.tier},
        )
        raise HTTPException(status_code=500, detail="Failed to save autonomy level") from None

    logger.info(
        "Autonomy level updated",
        extra={
            "user_id": current_user.id,
            "tier": data.tier,
            "level": requested_level,
        },
    )

    # Return updated status
    return await get_autonomy_status(current_user)
