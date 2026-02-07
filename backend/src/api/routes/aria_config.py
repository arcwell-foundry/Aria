"""ARIA role configuration and persona API routes (US-935)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser, get_current_user  # noqa: F401
from src.models.aria_config import ARIAConfigResponse, ARIAConfigUpdate, PreviewResponse
from src.services.aria_config_service import ARIAConfigService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aria-config", tags=["aria-config"])


def _get_service() -> ARIAConfigService:
    """Get ARIA config service instance.

    Returns:
        ARIAConfigService instance.
    """
    return ARIAConfigService()


@router.get("", response_model=ARIAConfigResponse)
async def get_aria_config(current_user: CurrentUser) -> dict[str, Any]:
    """Get current user's ARIA configuration."""
    service = _get_service()
    try:
        config = await service.get_config(current_user.id)
        logger.info("ARIA config retrieved", extra={"user_id": current_user.id})
        return config
    except Exception as e:
        logger.exception("Error fetching ARIA config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ARIA configuration",
        ) from e


@router.put("", response_model=ARIAConfigResponse)
async def update_aria_config(
    data: ARIAConfigUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's ARIA configuration."""
    service = _get_service()
    try:
        config = await service.update_config(current_user.id, data)
        logger.info(
            "ARIA config updated via API",
            extra={"user_id": current_user.id, "role": data.role.value},
        )
        return config
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error updating ARIA config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ARIA configuration",
        ) from e


@router.post("/reset-personality", response_model=ARIAConfigResponse)
async def reset_personality(current_user: CurrentUser) -> dict[str, Any]:
    """Reset personality sliders to calibrated defaults."""
    service = _get_service()
    try:
        config = await service.reset_personality(current_user.id)
        logger.info("ARIA personality reset", extra={"user_id": current_user.id})
        return config
    except Exception as e:
        logger.exception("Error resetting personality")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset personality",
        ) from e


@router.post("/preview", response_model=PreviewResponse)
async def generate_preview(
    data: ARIAConfigUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate a preview message showing how ARIA would respond with given config."""
    service = _get_service()
    try:
        preview = await service.generate_preview(current_user.id, data)
        return preview
    except Exception as e:
        logger.exception("Error generating preview")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate preview",
        ) from e
