"""Ambient Onboarding API routes (US-925).

Endpoints for the chat service to retrieve pending ambient gap-fill
prompts and record user engagement outcomes.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.onboarding.ambient_gap_filler import AmbientGapFiller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ambient-onboarding", tags=["ambient-onboarding"])


class AmbientPromptResponse(BaseModel):
    """Response model for an ambient prompt."""

    id: str = Field(..., description="Prompt UUID")
    domain: str = Field(..., description="Readiness domain")
    prompt: str = Field(..., description="Natural language prompt text")
    score: float = Field(..., description="Readiness score when generated")
    status: str = Field(..., description="Prompt status")


class OutcomeRequest(BaseModel):
    """Request model for recording prompt outcome."""

    outcome: str = Field(
        ...,
        pattern="^(engaged|dismissed|deferred)$",
        description="User engagement outcome",
    )


@router.get(
    "/ambient-prompt",
    response_model=AmbientPromptResponse | None,
    status_code=status.HTTP_200_OK,
)
async def get_ambient_prompt(
    current_user: CurrentUser,
) -> AmbientPromptResponse | None:
    """Get pending ambient prompt for the current conversation.

    Called by the chat service before generating ARIA's response.
    Returns the oldest pending prompt, marking it as delivered.

    Args:
        current_user: The authenticated user (auto-injected).

    Returns:
        AmbientPromptResponse if a prompt exists, None (204) otherwise.
    """
    try:
        filler = AmbientGapFiller()
        prompt = await filler.get_pending_prompt(current_user.id)

        if prompt is None:
            return None

        return AmbientPromptResponse(
            id=prompt.get("id", ""),
            domain=prompt.get("domain", ""),
            prompt=prompt.get("prompt", ""),
            score=float(prompt.get("score", 0.0)),
            status=prompt.get("status", "delivered"),
        )
    except Exception as e:
        logger.exception("Error fetching ambient prompt")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ambient prompt",
        ) from e


@router.post(
    "/ambient-prompt/{prompt_id}/outcome",
    status_code=status.HTTP_200_OK,
)
async def record_prompt_outcome(
    prompt_id: str,
    request: OutcomeRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Record user engagement outcome for an ambient prompt.

    Tracks whether user engaged (provided data), dismissed (ignored),
    or deferred (acknowledged but not now). Engaged outcomes feed
    procedural memory for future prompt optimization.

    Args:
        prompt_id: The ambient prompt UUID.
        request: The outcome to record.
        current_user: The authenticated user (auto-injected).

    Returns:
        Confirmation message.
    """
    try:
        filler = AmbientGapFiller()
        await filler.record_outcome(current_user.id, prompt_id, request.outcome)
        return {"status": "recorded", "outcome": request.outcome}
    except Exception as e:
        logger.exception("Error recording prompt outcome")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record outcome",
        ) from e
