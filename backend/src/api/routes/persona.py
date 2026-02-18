"""Persona settings API routes.

Provides endpoints for viewing ARIA's persona description and
submitting persona feedback (tone adjustments, anti-patterns).
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.deps import CurrentUser, get_current_user  # noqa: F401
from src.core.persona import get_persona_builder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persona", tags=["persona"])


class PersonaFeedbackRequest(BaseModel):
    """Request body for persona feedback."""

    feedback_type: str  # "tone_adjustment" or "anti_pattern"
    feedback_data: dict[str, Any]  # e.g. {"adjustment": "be more concise"}


class PersonaFeedbackResponse(BaseModel):
    """Response for persona feedback."""

    status: str
    message: str


@router.get("", response_model=dict[str, str])
async def get_persona_description(current_user: CurrentUser) -> dict[str, str]:
    """Get human-readable persona description for Settings UI.

    Returns a summary of ARIA's identity, traits, and user-specific adaptations.
    """
    builder = get_persona_builder()
    try:
        return await builder.get_persona_description(current_user.id)
    except Exception as e:
        logger.exception("Error fetching persona description")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch persona description",
        ) from e


@router.post("/feedback", response_model=PersonaFeedbackResponse)
async def submit_persona_feedback(
    data: PersonaFeedbackRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Submit persona feedback to adjust ARIA's communication style.

    Supports feedback_type:
    - "tone_adjustment": e.g. {"adjustment": "be more concise"}
    - "anti_pattern": e.g. {"pattern": "never use bullet points"}
    """
    if data.feedback_type not in ("tone_adjustment", "anti_pattern"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feedback_type must be 'tone_adjustment' or 'anti_pattern'",
        )

    builder = get_persona_builder()
    try:
        await builder.update_persona_from_feedback(
            user_id=current_user.id,
            feedback_type=data.feedback_type,
            feedback_data=data.feedback_data,
        )
        return {
            "status": "ok",
            "message": f"Persona {data.feedback_type} stored successfully",
        }
    except Exception as e:
        logger.exception("Error storing persona feedback")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store persona feedback",
        ) from e
