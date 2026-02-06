"""API routes for onboarding state machine."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser
from src.onboarding.models import (
    OnboardingStateResponse,
    OnboardingStep,
    StepCompletionRequest,
    StepSkipRequest,
)
from src.onboarding.orchestrator import OnboardingOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _get_orchestrator() -> OnboardingOrchestrator:
    return OnboardingOrchestrator()


@router.get("/state", response_model=OnboardingStateResponse)
async def get_onboarding_state(
    current_user: CurrentUser,
) -> OnboardingStateResponse:
    """Get current onboarding state for authenticated user."""
    orchestrator = _get_orchestrator()
    return await orchestrator.get_or_create_state(current_user.id)


@router.post("/steps/{step}/complete", response_model=OnboardingStateResponse)
async def complete_step(
    step: OnboardingStep,
    body: StepCompletionRequest,
    current_user: CurrentUser,
) -> OnboardingStateResponse:
    """Complete a step and advance to the next."""
    orchestrator = _get_orchestrator()
    try:
        return await orchestrator.complete_step(current_user.id, step, body.step_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/steps/{step}/skip", response_model=OnboardingStateResponse)
async def skip_step(
    step: OnboardingStep,
    current_user: CurrentUser,
    body: StepSkipRequest = StepSkipRequest(),
) -> OnboardingStateResponse:
    """Skip a non-critical step."""
    orchestrator = _get_orchestrator()
    try:
        return await orchestrator.skip_step(current_user.id, step, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/routing")
async def get_routing(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Determine post-auth routing for user."""
    orchestrator = _get_orchestrator()
    destination = await orchestrator.get_routing_decision(current_user.id)
    return {"route": destination}
