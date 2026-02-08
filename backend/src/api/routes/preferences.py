"""User preferences API routes for ARIA."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.core.exceptions import sanitize_error
from src.models.preferences import PreferenceResponse, PreferenceUpdate
from src.services.preference_service import PreferenceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/preferences", tags=["settings"])


def _get_service() -> PreferenceService:
    """Get preference service instance."""
    return PreferenceService()


@router.get("", response_model=PreferenceResponse)
async def get_preferences(current_user: CurrentUser) -> dict[str, Any]:
    """Get current user's preferences. Returns defaults if none exist."""
    service = _get_service()
    try:
        preferences = await service.get_preferences(current_user.id)
        logger.info("Preferences retrieved via API", extra={"user_id": current_user.id})
        return preferences
    except Exception as e:
        logger.exception("Error fetching preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch preferences",
        ) from e


@router.put("", response_model=PreferenceResponse)
async def update_preferences(
    data: PreferenceUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's preferences. Accepts partial updates."""
    service = _get_service()
    try:
        preferences = await service.update_preferences(current_user.id, data)
        logger.info("Preferences updated via API", extra={"user_id": current_user.id})
        return preferences
    except ValueError as e:
        logger.warning(
            "Preferences update failed",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=sanitize_error(e)) from e
    except Exception as e:
        logger.exception("Error updating preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        ) from e
