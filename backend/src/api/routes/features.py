"""Feature flags API route.

Serves feature flag state to the frontend.
"""

import logging

from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/features")
async def get_features(current_user: CurrentUser) -> dict:
    """Return current feature flag values."""
    return {
        "thesys_enabled": settings.thesys_configured,
    }
