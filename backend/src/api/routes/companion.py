"""Companion personality and theory of mind API routes.

Provides endpoints for:
- Getting user's personality profile
- Forming opinions on topics
- Recording pushback outcomes
- Getting mental state inference
- Getting behavioral patterns
- Generating emotional responses
- Strategic planning (US-805)
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.companion.emotional import (
    EmotionalIntelligenceEngine,
    EmotionalResponseRequest,
    EmotionalResponseResponse,
)
from src.companion.personality import PersonalityService
from src.companion.strategic import (
    ConcernType,
    PlanType,
    RiskSeverity,
    StrategicPlanningService,
)
from src.companion.theory_of_mind import TheoryOfMindModule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personality", tags=["companion"])
user_router = APIRouter(prefix="/user", tags=["companion"])
emotional_router = APIRouter(prefix="/emotional", tags=["companion"])


class PersonalityProfileResponse(BaseModel):
    """Response model for personality profile."""

    directness: int = Field(..., ge=1, le=3, description="Directness level (1-3)")
    warmth: int = Field(..., ge=1, le=3, description="Warmth level (1-3)")
    assertiveness: int = Field(..., ge=1, le=3, description="Assertiveness level (1-3)")
    humor: int = Field(..., ge=1, le=3, description="Humor level (1-3)")
    formality: int = Field(..., ge=1, le=3, description="Formality level (1-3)")
    adapted_for_user: bool = Field(..., description="Whether profile is adapted for user")


class OpinionRequest(BaseModel):
    """Request model for forming an opinion."""

    topic: str = Field(..., min_length=1, max_length=500, description="Topic to form opinion on")
    context: dict[str, Any] | None = Field(
        None, description="Optional additional context for opinion formation"
    )


class OpinionResponse(BaseModel):
    """Response model for opinion formation."""

    has_opinion: bool = Field(..., description="Whether an opinion was formed")
    opinion: str = Field(default="", description="The formed opinion")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence level")
    supporting_evidence: list[str] = Field(
        default_factory=list, description="Evidence supporting the opinion"
    )
    should_push_back: bool = Field(default=False, description="Whether pushback is warranted")
    pushback_reason: str = Field(default="", description="Reason for pushback if applicable")
    pushback_message: str | None = Field(
        None, description="Generated pushback message if warranted"
    )
    opinion_id: str | None = Field(None, description="ID of recorded opinion")


class PushbackOutcomeRequest(BaseModel):
    """Request model for recording pushback outcome."""

    opinion_id: str = Field(..., min_length=1, description="ID of the opinion")
    user_accepted: bool = Field(..., description="Whether user accepted the pushback")


# Theory of Mind Response Models


class MentalStateResponse(BaseModel):
    """Response model for mental state inference."""

    stress_level: str = Field(
        ..., description="Stress level: relaxed, normal, elevated, high, critical"
    )
    confidence: str = Field(
        ...,
        description="Confidence level: very_uncertain, uncertain, neutral, confident, very_confident",
    )
    current_focus: str = Field(default="", description="Current topic or focus")
    emotional_tone: str = Field(default="neutral", description="Emotional tone detected")
    needs_support: bool = Field(default=False, description="Whether user needs emotional support")
    needs_space: bool = Field(default=False, description="Whether user needs space")
    recommended_response_style: str = Field(
        default="standard",
        description="Recommended response style: concise, detailed, supportive, space, standard",
    )
    inferred_at: datetime = Field(..., description="When this state was inferred")


class StatePattern(BaseModel):
    """Response model for a behavioral pattern."""

    pattern_type: str = Field(..., description="Type of pattern")
    pattern_data: dict[str, Any] = Field(..., description="Pattern-specific data")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Pattern confidence")
    observed_count: int = Field(default=1, description="Number of times observed")
    last_observed: datetime = Field(..., description="When pattern was last observed")


class StatePatternsResponse(BaseModel):
    """Response model for behavioral patterns."""

    patterns: list[StatePattern] = Field(
        default_factory=list, description="List of detected patterns"
    )


@router.get("/profile", response_model=PersonalityProfileResponse)
async def get_personality_profile(
    current_user: CurrentUser,
) -> PersonalityProfileResponse:
    """Get the personality profile for the current user.

    Returns the user's adapted personality profile if it exists,
    otherwise returns ARIA's default personality traits.

    Args:
        current_user: The authenticated user.

    Returns:
        PersonalityProfileResponse with current trait levels.
    """
    service = PersonalityService()
    profile = await service.get_profile(current_user.id)

    return PersonalityProfileResponse(
        directness=profile.directness,
        warmth=profile.warmth,
        assertiveness=profile.assertiveness,
        humor=profile.humor,
        formality=profile.formality,
        adapted_for_user=profile.adapted_for_user,
    )


@router.post("/opinion", response_model=OpinionResponse)
async def form_opinion(
    current_user: CurrentUser,
    request: OpinionRequest,
) -> OpinionResponse:
    """Form an opinion on a topic.

    Uses semantic memory to gather relevant facts and forms an opinion
    using the LLM. May generate pushback if the evidence suggests it.

    Args:
        current_user: The authenticated user.
        request: The opinion request with topic and optional context.

    Returns:
        OpinionResponse with the formed opinion and optional pushback.

    Raises:
        HTTPException: If opinion formation fails.
    """
    service = PersonalityService()

    # Form the opinion
    opinion = await service.form_opinion(
        user_id=current_user.id,
        topic=request.topic,
        context=request.context,
    )

    if opinion is None:
        return OpinionResponse(
            has_opinion=False,
            opinion="",
            confidence=0.0,
            supporting_evidence=[],
            should_push_back=False,
            pushback_reason="",
        )

    # Generate pushback if warranted
    pushback_message = None
    if opinion.should_push_back:
        # Use the topic as the user statement for pushback generation
        pushback_message = await service.generate_pushback(
            user_id=current_user.id,
            user_statement=request.topic,
            opinion=opinion,
        )

    # Record the opinion
    opinion_id = await service.record_opinion(
        user_id=current_user.id,
        topic=request.topic,
        opinion=opinion,
        pushback_generated=pushback_message,
    )

    return OpinionResponse(
        has_opinion=opinion.has_opinion,
        opinion=opinion.opinion,
        confidence=opinion.confidence,
        supporting_evidence=opinion.supporting_evidence,
        should_push_back=opinion.should_push_back,
        pushback_reason=opinion.pushback_reason,
        pushback_message=pushback_message,
        opinion_id=opinion_id,
    )


@router.post("/pushback-outcome")
async def record_pushback_outcome(
    _current_user: CurrentUser,
    request: PushbackOutcomeRequest,
) -> dict[str, str]:
    """Record the outcome of a pushback interaction.

    Tracks whether the user accepted ARIA's pushback advice, which
    informs future personality adaptation.

    Args:
        _current_user: The authenticated user (used for auth validation).
        request: The pushback outcome request.

    Returns:
        Success status message.

    Raises:
        HTTPException: If the opinion doesn't exist or update fails.
    """
    service = PersonalityService()

    try:
        await service.update_pushback_outcome(
            opinion_id=request.opinion_id,
            user_accepted=request.user_accepted,
        )
    except Exception as e:
        logger.exception(
            "Failed to record pushback outcome",
            extra={"opinion_id": request.opinion_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to record pushback outcome",
        ) from e

    return {"status": "recorded"}


# ── Theory of Mind Endpoints ───────────────────────────────────────────────────


@user_router.get("/mental-state", response_model=MentalStateResponse)
async def get_mental_state(
    current_user: CurrentUser,
) -> MentalStateResponse:
    """Get the inferred mental state for the current user.

    Returns the most recent mental state inference if available,
    otherwise performs a new inference from recent conversation.

    Args:
        current_user: The authenticated user.

    Returns:
        MentalStateResponse with current mental state inference.
    """
    module = TheoryOfMindModule()

    # Try to get the most recent stored state
    state = await module.get_current_state(current_user.id)

    if state is None:
        # No stored state - return a default neutral state
        return MentalStateResponse(
            stress_level="normal",
            confidence="neutral",
            current_focus="",
            emotional_tone="neutral",
            needs_support=False,
            needs_space=False,
            recommended_response_style="standard",
            inferred_at=datetime.now(),
        )

    return MentalStateResponse(
        stress_level=state.stress_level.value,
        confidence=state.confidence.value,
        current_focus=state.current_focus,
        emotional_tone=state.emotional_tone,
        needs_support=state.needs_support,
        needs_space=state.needs_space,
        recommended_response_style=state.recommended_response_style,
        inferred_at=datetime.now(),  # Use current time since we don't store inferred_at in MentalState
    )


@user_router.get("/state-patterns", response_model=StatePatternsResponse)
async def get_state_patterns(
    current_user: CurrentUser,
) -> StatePatternsResponse:
    """Get detected behavioral patterns for the current user.

    Returns patterns detected from mental state history, such as
    time-based stress patterns or focus trends.

    Args:
        current_user: The authenticated user.

    Returns:
        StatePatternsResponse with list of detected patterns.
    """
    module = TheoryOfMindModule()
    patterns = await module.get_patterns(current_user.id)

    return StatePatternsResponse(
        patterns=[
            StatePattern(
                pattern_type=p.pattern_type,
                pattern_data=p.pattern_data,
                confidence=p.confidence,
                observed_count=p.observed_count,
                last_observed=p.last_observed,
            )
            for p in patterns
        ]
    )


# ── Emotional Intelligence Endpoints ───────────────────────────────────────────


@emotional_router.post("/response", response_model=EmotionalResponseResponse)
async def get_emotional_response(
    current_user: CurrentUser,
    request: EmotionalResponseRequest,
) -> EmotionalResponseResponse:
    """Generate an emotional response for a user message.

    Analyzes the emotional context of the message and generates
    an appropriate acknowledgment with guidance on how to respond.

    Args:
        current_user: The authenticated user.
        request: The emotional response request with message and optional history.

    Returns:
        EmotionalResponseResponse with context, acknowledgment, and guidance.

    Raises:
        HTTPException: If response generation fails.
    """
    engine = EmotionalIntelligenceEngine()

    try:
        response = await engine.generate_emotional_response(
            user_id=current_user.id,
            message=request.message,
            conversation_history=request.conversation_history,
        )

        return EmotionalResponseResponse(
            context=response.context.value,
            acknowledgment=response.acknowledgment,
            support_type=response.support_type.value,
            response_elements=response.response_elements,
            avoid_list=response.avoid_list,
        )

    except Exception as e:
        logger.exception(
            "Failed to generate emotional response",
            extra={"user_id": current_user.id, "message_preview": request.message[:50]},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate emotional response",
        ) from e


# ── Strategic Planning Endpoints (US-805) ────────────────────────────────────────

strategy_router = APIRouter(prefix="/strategy", tags=["companion"])


class CreatePlanRequest(BaseModel):
    """Request model for creating a strategic plan."""

    title: str = Field(..., min_length=1, max_length=200, description="Plan title")
    plan_type: str = Field(
        ...,
        description="Type of plan: quarterly, annual, campaign, territory, account",
    )
    objectives: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of strategic objectives",
    )


class UpdatePlanRequest(BaseModel):
    """Request model for updating a strategic plan."""

    title: str | None = Field(None, max_length=200, description="Updated plan title")
    objectives: list[str] | None = Field(None, max_length=10, description="Updated objectives")
    key_results: list[dict[str, Any]] | None = Field(None, description="Updated key results")
    progress_data: dict[str, float] | None = Field(
        None, description="Progress updates mapped by key result description"
    )
    status: str | None = Field(None, description="Plan status: active, completed, archived")


class ScenarioRequest(BaseModel):
    """Request model for running a scenario analysis."""

    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Description of the scenario to analyze",
    )


class KeyResultResponse(BaseModel):
    """Response model for a key result."""

    description: str
    target_value: float
    current_value: float
    unit: str
    progress_percentage: float


class RiskResponse(BaseModel):
    """Response model for a risk."""

    description: str
    severity: str
    likelihood: float
    impact: float
    mitigation: str


class ScenarioResponse(BaseModel):
    """Response model for a scenario."""

    name: str
    description: str
    probability: float
    key_factors: list[str]
    outcomes: dict[str, Any]


class PlanResponse(BaseModel):
    """Response model for a strategic plan."""

    id: str
    title: str
    plan_type: str
    status: str
    objectives: list[str]
    key_results: list[KeyResultResponse]
    risks: list[RiskResponse]
    scenarios: list[ScenarioResponse]
    progress_score: float
    aria_assessment: str
    aria_concerns: list[str]
    created_at: datetime
    updated_at: datetime


class ScenarioAnalysisResponse(BaseModel):
    """Response model for scenario analysis."""

    scenario_description: str
    affected_objectives: list[str]
    risk_changes: list[dict[str, Any]]
    recommended_adjustments: list[str]
    confidence: float
    error: str | None = None


class ChallengeResponse(BaseModel):
    """Response model for plan challenge."""

    assumptions_challenged: list[str]
    blind_spots: list[str]
    alternatives_considered: list[str]
    recommended_revisions: list[str]
    directness_level: int
    error: str | None = None


class ConcernResponse(BaseModel):
    """Response model for a strategic concern."""

    plan_id: str
    plan_title: str
    concern_type: str
    description: str
    severity: str
    recommendation: str


def _validate_plan_type(plan_type: str) -> PlanType:
    """Validate and convert plan type string to enum."""
    try:
        return PlanType(plan_type.lower())
    except ValueError:
        valid_types = [e.value for e in PlanType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan_type. Must be one of: {valid_types}",
        )


def _plan_to_response(plan: Any) -> PlanResponse:
    """Convert StrategicPlan to response model."""
    from src.companion.strategic import KeyResult, Risk, Scenario

    return PlanResponse(
        id=plan.id,
        title=plan.title,
        plan_type=plan.plan_type.value,
        status=plan.status,
        objectives=plan.objectives,
        key_results=[
            KeyResultResponse(
                description=kr.description,
                target_value=kr.target_value,
                current_value=kr.current_value,
                unit=kr.unit,
                progress_percentage=kr.progress_percentage,
            )
            for kr in plan.key_results
        ],
        risks=[
            RiskResponse(
                description=r.description,
                severity=r.severity.value,
                likelihood=r.likelihood,
                impact=r.impact,
                mitigation=r.mitigation,
            )
            for r in plan.risks
        ],
        scenarios=[
            ScenarioResponse(
                name=s.name,
                description=s.description,
                probability=s.probability,
                key_factors=s.key_factors,
                outcomes=s.outcomes,
            )
            for s in plan.scenarios
        ],
        progress_score=plan.progress_score,
        aria_assessment=plan.aria_assessment,
        aria_concerns=plan.aria_concerns,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@strategy_router.post("/plan", response_model=PlanResponse)
async def create_strategic_plan(
    current_user: CurrentUser,
    request: CreatePlanRequest,
) -> PlanResponse:
    """Create a new strategic plan.

    Creates a strategic plan with LLM-generated key results,
    risks, scenarios, and ARIA assessment.

    Args:
        current_user: The authenticated user.
        request: The plan creation request.

    Returns:
        PlanResponse with the created plan.

    Raises:
        HTTPException: If plan creation fails.
    """
    plan_type = _validate_plan_type(request.plan_type)
    service = StrategicPlanningService()

    try:
        plan = await service.create_plan(
            user_id=current_user.id,
            title=request.title,
            plan_type=plan_type,
            objectives=request.objectives,
        )
        return _plan_to_response(plan)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(
            "Failed to create strategic plan",
            extra={"user_id": current_user.id, "title": request.title},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create strategic plan",
        ) from e


@strategy_router.get("/plans", response_model=list[PlanResponse])
async def list_strategic_plans(
    current_user: CurrentUser,
) -> list[PlanResponse]:
    """List all active strategic plans for the user.

    Args:
        current_user: The authenticated user.

    Returns:
        List of PlanResponse objects for user's active plans.
    """
    service = StrategicPlanningService()
    plans = await service.get_active_plans(current_user.id)
    return [_plan_to_response(plan) for plan in plans]


@strategy_router.get("/plan/{plan_id}", response_model=PlanResponse)
async def get_strategic_plan(
    current_user: CurrentUser,
    plan_id: str,
) -> PlanResponse:
    """Get a specific strategic plan.

    Args:
        current_user: The authenticated user.
        plan_id: The plan ID.

    Returns:
        PlanResponse with the requested plan.

    Raises:
        HTTPException: If plan not found.
    """
    service = StrategicPlanningService()
    plan = await service.get_plan(plan_id, current_user.id)

    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    return _plan_to_response(plan)


@strategy_router.put("/plan/{plan_id}", response_model=PlanResponse)
async def update_strategic_plan(
    current_user: CurrentUser,
    plan_id: str,
    request: UpdatePlanRequest,
) -> PlanResponse:
    """Update a strategic plan.

    Args:
        current_user: The authenticated user.
        plan_id: The plan ID.
        request: The update request.

    Returns:
        PlanResponse with the updated plan.

    Raises:
        HTTPException: If plan not found or update fails.
    """
    service = StrategicPlanningService()

    # Handle progress updates separately
    if request.progress_data:
        plan = await service.update_progress(
            plan_id=plan_id,
            user_id=current_user.id,
            progress_data=request.progress_data,
        )
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        return _plan_to_response(plan)

    # Handle other updates
    updates: dict[str, Any] = {}
    if request.title is not None:
        updates["title"] = request.title
    if request.objectives is not None:
        updates["objectives"] = request.objectives
    if request.key_results is not None:
        updates["key_results"] = request.key_results
    if request.status is not None:
        updates["status"] = request.status

    if not updates:
        # No updates provided, just return current plan
        plan = await service.get_plan(plan_id, current_user.id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        return _plan_to_response(plan)

    plan = await service.update_plan(
        plan_id=plan_id,
        user_id=current_user.id,
        updates=updates,
    )

    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    return _plan_to_response(plan)


@strategy_router.post("/plan/{plan_id}/scenario", response_model=ScenarioAnalysisResponse)
async def run_scenario_analysis(
    current_user: CurrentUser,
    plan_id: str,
    request: ScenarioRequest,
) -> ScenarioAnalysisResponse:
    """Run a "what-if" scenario analysis on a plan.

    Args:
        current_user: The authenticated user.
        plan_id: The plan ID.
        request: The scenario request.

    Returns:
        ScenarioAnalysisResponse with impact analysis.

    Raises:
        HTTPException: If plan not found or analysis fails.
    """
    service = StrategicPlanningService()

    result = await service.run_scenario(
        plan_id=plan_id,
        user_id=current_user.id,
        scenario_description=request.description,
    )

    if "error" in result and result.get("affected_objectives") == []:
        raise HTTPException(status_code=404, detail="Plan not found")

    return ScenarioAnalysisResponse(**result)


@strategy_router.post("/plan/{plan_id}/challenge", response_model=ChallengeResponse)
async def challenge_strategic_plan(
    current_user: CurrentUser,
    plan_id: str,
) -> ChallengeResponse:
    """Have ARIA critically evaluate a plan.

    ARIA will identify weaknesses, blind spots, and unrealistic assumptions.

    Args:
        current_user: The authenticated user.
        plan_id: The plan ID.

    Returns:
        ChallengeResponse with ARIA's critique.

    Raises:
        HTTPException: If plan not found.
    """
    service = StrategicPlanningService()

    result = await service.challenge_plan(
        plan_id=plan_id,
        user_id=current_user.id,
    )

    if "error" in result and result.get("assumptions_challenged") == []:
        raise HTTPException(status_code=404, detail="Plan not found")

    return ChallengeResponse(**result)


@strategy_router.get("/concerns", response_model=list[ConcernResponse])
async def get_strategic_concerns(
    current_user: CurrentUser,
) -> list[ConcernResponse]:
    """Get prioritized strategic concerns across all active plans.

    Args:
        current_user: The authenticated user.

    Returns:
        List of ConcernResponse objects, sorted by severity.
    """
    service = StrategicPlanningService()
    concerns = await service.get_strategic_concerns(current_user.id)

    return [
        ConcernResponse(
            plan_id=c.plan_id,
            plan_title=c.plan_title,
            concern_type=c.concern_type.value,
            description=c.description,
            severity=c.severity,
            recommendation=c.recommendation,
        )
        for c in concerns
    ]
