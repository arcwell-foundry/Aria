"""Companion personality and theory of mind API routes.

Provides endpoints for:
- Getting user's personality profile
- Forming opinions on topics
- Recording pushback outcomes
- Getting mental state inference
- Getting behavioral patterns
- Generating emotional responses
- Strategic planning (US-805)
- Self-reflection and self-correction (US-806)
- Narrative identity (US-807)
- Digital twin writing style (US-808)
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
from src.companion.narrative import (
    MilestoneType,
    NarrativeIdentityEngine,
    NarrativeState,
    RelationshipMilestone,
)
from src.companion.personality import PersonalityService
from src.companion.self_improvement import (
    ImprovementCycleResponse,
    SelfImprovementLoop,
    WeeklyReportResponse,
)
from src.companion.self_reflection import (
    AcknowledgeMistakeRequest,
    AcknowledgeMistakeResponse,
    DailyReflectionResponse,
    ImprovementPlanResponse,
    ReflectRequest,
    SelfAssessmentResponse,
    SelfReflectionService,
)
from src.companion.strategic import (
    PlanType,
    StrategicPlanningService,
)
from src.companion.theory_of_mind import TheoryOfMindModule
from src.memory.digital_twin import DigitalTwin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personality", tags=["companion"])
user_router = APIRouter(prefix="/user", tags=["companion"])
emotional_router = APIRouter(prefix="/emotional", tags=["companion"])
improvement_router = APIRouter(prefix="/improvement", tags=["companion"])


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


# Digital Twin Response Models (US-808)


class WritingStyleResponse(BaseModel):
    """Response model for writing style profile."""

    average_sentence_length: float = Field(..., description="Average words per sentence")
    vocabulary_level: str = Field(
        ..., description="Vocabulary level: simple, moderate, or advanced"
    )
    formality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Formality score (0.0 informal to 1.0 formal)"
    )
    common_phrases: list[str] = Field(
        default_factory=list, description="Common phrases used by the user"
    )
    greeting_style: str = Field(
        default="", description="Typical greeting style (e.g., 'Hi', 'Dear')"
    )
    sign_off_style: str = Field(
        default="", description="Typical sign-off style (e.g., 'Best', 'Regards')"
    )
    emoji_usage: bool = Field(..., description="Whether user typically uses emojis")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence level of the fingerprint"
    )
    samples_analyzed: int = Field(..., ge=0, description="Number of text samples analyzed")
    style_guidelines: str = Field(
        ..., description="Prompt-ready style instructions for content generation"
    )
    created_at: datetime | None = Field(None, description="When the fingerprint was created")
    updated_at: datetime | None = Field(None, description="When the fingerprint was last updated")


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


# ── Digital Twin Endpoints (US-808) ─────────────────────────────────────────────


@user_router.get("/writing-style", response_model=WritingStyleResponse | None)
async def get_writing_style(
    current_user: CurrentUser,
) -> WritingStyleResponse | None:
    """Get the user's writing style profile from Digital Twin.

    Returns the user's writing style fingerprint if available, including
    vocabulary level, formality score, common phrases, and style guidelines
    that can be used for generating style-matched content.

    Args:
        current_user: The authenticated user.

    Returns:
        WritingStyleResponse with the user's style profile, or None if no
        fingerprint exists yet.

    Raises:
        HTTPException: If retrieval fails unexpectedly.
    """
    twin = DigitalTwin()

    try:
        fingerprint = await twin.get_fingerprint(current_user.id)

        if not fingerprint:
            return None

        guidelines = await twin.get_style_guidelines(current_user.id)

        return WritingStyleResponse(
            average_sentence_length=fingerprint.average_sentence_length,
            vocabulary_level=fingerprint.vocabulary_level,
            formality_score=fingerprint.formality_score,
            common_phrases=fingerprint.common_phrases,
            greeting_style=fingerprint.greeting_style,
            sign_off_style=fingerprint.sign_off_style,
            emoji_usage=fingerprint.emoji_usage,
            confidence=fingerprint.confidence,
            samples_analyzed=fingerprint.samples_analyzed,
            style_guidelines=guidelines,
            created_at=fingerprint.created_at,
            updated_at=fingerprint.updated_at,
        )

    except Exception as e:
        logger.exception(
            "Failed to get writing style",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve writing style profile",
        ) from e


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
        ) from None


def _plan_to_response(plan: Any) -> PlanResponse:
    """Convert StrategicPlan to response model."""
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
        logger.warning(
            "Invalid strategic plan request",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid plan parameters. Please check and try again.",
        ) from e
    except Exception as e:
        logger.exception(
            "Failed to create strategic plan",
            extra={"user_id": current_user.id, "title": request.title},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create strategic plan. Please try again.",
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


# ── Self-Reflection Endpoints (US-806) ─────────────────────────────────────────

reflection_router = APIRouter(prefix="/reflection", tags=["companion"])


@reflection_router.post("/reflect", response_model=DailyReflectionResponse)
async def trigger_reflection(
    current_user: CurrentUser,
    _request: ReflectRequest,
) -> DailyReflectionResponse:
    """Trigger a manual reflection on ARIA's recent performance.

    Analyzes today's interactions, feedback, and actions to generate
    a reflection with positive/negative outcomes and improvement opportunities.

    Args:
        current_user: The authenticated user.
        request: The reflection request with period.

    Returns:
        DailyReflectionResponse with reflection data.

    Raises:
        HTTPException: If reflection generation fails.
    """
    service = SelfReflectionService()

    try:
        reflection = await service.run_daily_reflection(current_user.id)

        return DailyReflectionResponse(
            id=reflection["id"],
            reflection_date=reflection["reflection_date"],
            total_interactions=reflection["total_interactions"],
            positive_outcomes=reflection["positive_outcomes"],
            negative_outcomes=reflection["negative_outcomes"],
            patterns_detected=reflection["patterns_detected"],
            improvement_opportunities=reflection["improvement_opportunities"],
        )

    except Exception as e:
        logger.exception(
            "Failed to generate reflection",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate reflection",
        ) from e


@reflection_router.get("/self-assessment", response_model=SelfAssessmentResponse)
async def get_self_assessment(
    current_user: CurrentUser,
) -> SelfAssessmentResponse:
    """Get the latest self-assessment for ARIA's capabilities.

    Generates or retrieves a weekly assessment including score,
    strengths, weaknesses, and trend analysis.

    Args:
        current_user: The authenticated user.

    Returns:
        SelfAssessmentResponse with assessment data.

    Raises:
        HTTPException: If assessment generation fails.
    """
    service = SelfReflectionService()

    try:
        assessment = await service.generate_self_assessment(
            user_id=current_user.id,
            period="weekly",
        )

        return SelfAssessmentResponse(
            id=assessment["id"],
            assessment_period=assessment["assessment_period"],
            overall_score=assessment["overall_score"],
            strengths=assessment["strengths"],
            weaknesses=assessment["weaknesses"],
            mistakes_acknowledged=assessment["mistakes_acknowledged"],
            improvement_plan=assessment["improvement_plan"],
            trend=assessment["trend"],
        )

    except Exception as e:
        logger.exception(
            "Failed to generate self-assessment",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate self-assessment",
        ) from e


@reflection_router.get(
    "/improvement-plan",
    response_model=ImprovementPlanResponse,
)
async def get_improvement_plan(
    current_user: CurrentUser,
) -> ImprovementPlanResponse:
    """Get the current improvement plan with prioritized actions.

    Returns areas for improvement sorted by priority, along with
    progress indicators from the latest assessment.

    Args:
        current_user: The authenticated user.

    Returns:
        ImprovementPlanResponse with improvement areas and progress.

    Raises:
        HTTPException: If plan retrieval fails.
    """
    service = SelfReflectionService()

    try:
        plan = await service.get_improvement_plan(current_user.id)

        return ImprovementPlanResponse(
            areas=plan["areas"],
            last_updated=plan["last_updated"],
            progress_indicators=plan["progress_indicators"],
        )

    except Exception as e:
        logger.exception(
            "Failed to get improvement plan",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to get improvement plan",
        ) from e


@reflection_router.post(
    "/acknowledge-mistake",
    response_model=AcknowledgeMistakeResponse,
)
async def acknowledge_mistake(
    current_user: CurrentUser,
    request: AcknowledgeMistakeRequest,
) -> AcknowledgeMistakeResponse:
    """Generate an honest acknowledgment of a mistake.

    Creates an acknowledgment that takes full responsibility without
    excuses, using "I" statements and committing to improvement.

    Args:
        current_user: The authenticated user.
        request: The acknowledgment request with mistake description.

    Returns:
        AcknowledgeMistakeResponse with the acknowledgment text.

    Raises:
        HTTPException: If acknowledgment generation fails.
    """
    service = SelfReflectionService()

    try:
        acknowledgment = await service.acknowledge_mistake(
            user_id=current_user.id,
            mistake_description=request.mistake_description,
        )

        return AcknowledgeMistakeResponse(
            acknowledgment=acknowledgment,
            recorded=True,
        )

    except Exception as e:
        logger.exception(
            "Failed to acknowledge mistake",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to acknowledge mistake",
        ) from e


# ── Narrative Identity Endpoints (US-807) ───────────────────────────────────────

narrative_router = APIRouter(prefix="/narrative", tags=["companion"])


class MilestoneResponse(BaseModel):
    """Response model for a relationship milestone."""

    id: str
    type: str
    date: datetime
    description: str
    significance: float
    related_entity_type: str | None
    related_entity_id: str | None
    created_at: datetime


class NarrativeStateResponse(BaseModel):
    """Response model for narrative state."""

    relationship_start: datetime
    total_interactions: int
    trust_score: float
    shared_victories: list[dict[str, Any]]
    shared_challenges: list[dict[str, Any]]
    inside_references: list[str]
    updated_at: datetime


class RecordMilestoneRequest(BaseModel):
    """Request model for recording a milestone."""

    milestone_type: str = Field(
        ...,
        description="Type of milestone: first_interaction, first_deal, first_challenge, deal_closed, first_goal_completed, first_pushback_accepted",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of the milestone",
    )
    related_entity_type: str | None = Field(
        None,
        description="Optional type of related entity (e.g., deal, goal)",
    )
    related_entity_id: str | None = Field(
        None,
        description="Optional ID of related entity",
    )
    significance: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Importance of milestone (0.0-1.0)",
    )


class ContextualReferencesRequest(BaseModel):
    """Request model for contextual references."""

    current_topic: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Current conversation topic",
    )


class ContextualReferencesResponse(BaseModel):
    """Response model for contextual references."""

    references: list[str] = Field(
        default_factory=list,
        description="Relevant references from shared history (max 2)",
    )


class AnniversaryResponse(BaseModel):
    """Response model for anniversary detection."""

    anniversaries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of detected anniversaries",
    )


def _milestone_to_response(milestone: RelationshipMilestone) -> MilestoneResponse:
    """Convert RelationshipMilestone to response model."""
    return MilestoneResponse(
        id=milestone.id,
        type=milestone.type,
        date=milestone.date,
        description=milestone.description,
        significance=milestone.significance,
        related_entity_type=milestone.related_entity_type,
        related_entity_id=milestone.related_entity_id,
        created_at=milestone.created_at,
    )


def _state_to_response(state: NarrativeState) -> NarrativeStateResponse:
    """Convert NarrativeState to response model."""
    return NarrativeStateResponse(
        relationship_start=state.relationship_start,
        total_interactions=state.total_interactions,
        trust_score=state.trust_score,
        shared_victories=state.shared_victories,
        shared_challenges=state.shared_challenges,
        inside_references=state.inside_references,
        updated_at=state.updated_at,
    )


@narrative_router.get("/relationship", response_model=NarrativeStateResponse)
async def get_relationship_narrative(
    current_user: CurrentUser,
) -> NarrativeStateResponse:
    """Get the narrative state of the user-ARIA relationship.

    Returns the current state including trust score, interaction count,
    shared victories/challenges, and inside references.

    Args:
        current_user: The authenticated user.

    Returns:
        NarrativeStateResponse with relationship details.
    """
    engine = NarrativeIdentityEngine()
    state = await engine.get_narrative_state(current_user.id)
    return _state_to_response(state)


@narrative_router.get("/milestones", response_model=list[MilestoneResponse])
async def list_milestones(
    current_user: CurrentUser,
) -> list[MilestoneResponse]:
    """List relationship milestones for the user.

    Args:
        current_user: The authenticated user.

    Returns:
        List of MilestoneResponse objects.
    """
    engine = NarrativeIdentityEngine()
    milestones = await engine._get_recent_milestones(current_user.id, limit=50)
    return [_milestone_to_response(m) for m in milestones]


@narrative_router.post("/milestone", response_model=MilestoneResponse)
async def record_milestone(
    current_user: CurrentUser,
    request: RecordMilestoneRequest,
) -> MilestoneResponse:
    """Manually record a relationship milestone.

    Records a milestone in the user-ARIA relationship history.
    Milestones with high significance (>= 0.7) are added to inside references.

    Args:
        current_user: The authenticated user.
        request: The milestone recording request.

    Returns:
        MilestoneResponse with the created milestone.

    Raises:
        HTTPException: If milestone recording fails.
    """
    engine = NarrativeIdentityEngine()

    # Validate milestone type
    valid_types = [e.value for e in MilestoneType]
    if request.milestone_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid milestone_type. Must be one of: {valid_types}",
        )

    try:
        milestone = await engine.record_milestone(
            user_id=current_user.id,
            milestone_type=request.milestone_type,
            description=request.description,
            related_entity_type=request.related_entity_type,
            related_entity_id=request.related_entity_id,
            significance=request.significance,
        )
        return _milestone_to_response(milestone)

    except Exception as e:
        logger.exception(
            "Failed to record milestone",
            extra={"user_id": current_user.id, "milestone_type": request.milestone_type},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to record milestone",
        ) from e


@narrative_router.post("/references", response_model=ContextualReferencesResponse)
async def get_contextual_references(
    current_user: CurrentUser,
    request: ContextualReferencesRequest,
) -> ContextualReferencesResponse:
    """Get contextual references from shared history.

    Uses LLM to find relevant shared experiences for the current topic.
    Returns at most 2 references to avoid overwhelming the response.

    Args:
        current_user: The authenticated user.
        request: The request with current topic.

    Returns:
        ContextualReferencesResponse with relevant references.
    """
    engine = NarrativeIdentityEngine()
    references = await engine.get_contextual_references(
        user_id=current_user.id,
        current_topic=request.current_topic,
    )
    return ContextualReferencesResponse(references=references)


@narrative_router.get("/anniversaries", response_model=AnniversaryResponse)
async def check_anniversaries(
    current_user: CurrentUser,
) -> AnniversaryResponse:
    """Check for upcoming or current anniversaries.

    Detects work anniversaries and deal/goal anniversaries based on
    the relationship history and milestone dates.

    Args:
        current_user: The authenticated user.

    Returns:
        AnniversaryResponse with detected anniversaries.
    """
    engine = NarrativeIdentityEngine()
    anniversaries = await engine.check_anniversaries(current_user.id)
    return AnniversaryResponse(anniversaries=anniversaries)


# ── Self-Improvement Endpoints (US-809) ──────────────────────────────────────


@improvement_router.get("/cycle", response_model=ImprovementCycleResponse)
async def run_improvement_cycle(
    current_user: CurrentUser,
) -> ImprovementCycleResponse:
    """Run an improvement cycle analyzing recent performance.

    Queries recent daily reflections, identifies capability gaps,
    and generates an actionable improvement plan.

    Args:
        current_user: The authenticated user.

    Returns:
        ImprovementCycleResponse with areas, action_plan, and trend.

    Raises:
        HTTPException: If cycle generation fails.
    """
    service = SelfImprovementLoop()

    try:
        result = await service.run_improvement_cycle(current_user.id)

        return ImprovementCycleResponse(
            areas=result["top_improvement_areas"],
            action_plan=result["action_plan"],
            performance_trend=result["performance_trend"],
        )

    except Exception as e:
        logger.exception(
            "Failed to run improvement cycle",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to run improvement cycle",
        ) from e


@improvement_router.get("/weekly-report", response_model=WeeklyReportResponse)
async def get_weekly_report(
    current_user: CurrentUser,
) -> WeeklyReportResponse:
    """Generate a weekly improvement report with trend analysis.

    Compares this week's performance with the previous week and
    generates a summary with wins and areas to work on.

    Args:
        current_user: The authenticated user.

    Returns:
        WeeklyReportResponse with summary, metrics, and comparison.

    Raises:
        HTTPException: If report generation fails.
    """
    service = SelfImprovementLoop()

    try:
        result = await service.generate_weekly_report(current_user.id)

        return WeeklyReportResponse(
            summary=result["summary"],
            interaction_count=result["interaction_count"],
            improvement_metrics=result["improvement_metrics"],
            wins=result["wins"],
            areas_to_work_on=result["areas_to_work_on"],
            week_over_week=result["week_over_week"],
        )

    except Exception as e:
        logger.exception(
            "Failed to generate weekly report",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate weekly report",
        ) from e
