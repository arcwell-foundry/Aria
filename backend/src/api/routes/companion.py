"""Companion personality and theory of mind API routes.

Provides endpoints for:
- Getting user's personality profile
- Forming opinions on topics
- Recording pushback outcomes
- Getting mental state inference
- Getting behavioral patterns
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.companion.personality import PersonalityService
from src.companion.theory_of_mind import TheoryOfMindModule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personality", tags=["companion"])
user_router = APIRouter(prefix="/user", tags=["companion"])


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
