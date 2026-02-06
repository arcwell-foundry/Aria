"""Pydantic models for the onboarding state machine."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OnboardingStep(str, Enum):
    """Steps in the onboarding state machine."""

    COMPANY_DISCOVERY = "company_discovery"
    DOCUMENT_UPLOAD = "document_upload"
    USER_PROFILE = "user_profile"
    WRITING_SAMPLES = "writing_samples"
    EMAIL_INTEGRATION = "email_integration"
    INTEGRATION_WIZARD = "integration_wizard"
    FIRST_GOAL = "first_goal"
    ACTIVATION = "activation"


# Ordered step sequence — drives progression logic
STEP_ORDER: list[OnboardingStep] = [
    OnboardingStep.COMPANY_DISCOVERY,
    OnboardingStep.DOCUMENT_UPLOAD,
    OnboardingStep.USER_PROFILE,
    OnboardingStep.WRITING_SAMPLES,
    OnboardingStep.EMAIL_INTEGRATION,
    OnboardingStep.INTEGRATION_WIZARD,
    OnboardingStep.FIRST_GOAL,
    OnboardingStep.ACTIVATION,
]

# Steps that can be skipped (non-critical)
SKIPPABLE_STEPS: set[OnboardingStep] = {
    OnboardingStep.DOCUMENT_UPLOAD,
    OnboardingStep.WRITING_SAMPLES,
    OnboardingStep.EMAIL_INTEGRATION,
}


class ReadinessScores(BaseModel):
    """Readiness sub-scores across five domains (0-100 each)."""

    corporate_memory: float = 0.0
    digital_twin: float = 0.0
    relationship_graph: float = 0.0
    integrations: float = 0.0
    goal_clarity: float = 0.0


class OnboardingState(BaseModel):
    """Persisted onboarding state for a user."""

    id: str
    user_id: str
    current_step: OnboardingStep
    step_data: dict[str, Any] = Field(default_factory=dict)
    completed_steps: list[str] = Field(default_factory=list)
    skipped_steps: list[str] = Field(default_factory=list)
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    readiness_scores: ReadinessScores = Field(default_factory=ReadinessScores)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OnboardingStateResponse(BaseModel):
    """Response wrapper with progress metadata."""

    state: OnboardingState
    progress_percentage: float
    total_steps: int
    completed_count: int
    current_step_index: int
    is_complete: bool


class StepCompletionRequest(BaseModel):
    """Request body for completing a step."""

    step_data: dict[str, Any] = Field(default_factory=dict)


class StepSkipRequest(BaseModel):
    """Request body for skipping a step."""

    reason: str | None = None
