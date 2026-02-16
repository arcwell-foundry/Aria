"""Pydantic models for Time Horizon Analysis.

This module defines the data structures for categorizing implications
by when they'll materialize, enabling prioritized action planning.

Key components:
- TimeHorizon: Enum for categorizing temporal urgency
- ActionTiming: Optimal timing recommendations for actions
- TimelineView: Response model for timeline endpoint
- TimelineRequest: Request parameters for timeline queries
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class TimeHorizon(str, Enum):
    """Time horizon categories for implication urgency.

    Categories are based on when an implication will materialize,
    using life sciences-appropriate time scales.
    """

    IMMEDIATE = "immediate"  # Days (1-7 days)
    SHORT_TERM = "short_term"  # Weeks (1-4 weeks)
    MEDIUM_TERM = "medium_term"  # Months (1-6 months)
    LONG_TERM = "long_term"  # Quarters+ (6+ months)


class ActionTiming(BaseModel):
    """Optimal timing for acting on an implication.

    Combines time horizon analysis with user context to recommend
    when to take action for maximum effectiveness.
    """

    optimal_action_date: date = Field(
        ...,
        description="Recommended date to take action",
    )
    window_opens: date = Field(
        ...,
        description="Earliest date when action becomes viable",
    )
    window_closes: date = Field(
        ...,
        description="Latest date when action should be taken",
    )
    reason: str = Field(
        ...,
        description="Explanation of why this timing is recommended",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the timing recommendation (0-1)",
    )


class ImplicationWithTiming(BaseModel):
    """An implication with time horizon and timing information.

    Extends the base Implication with temporal categorization.
    """

    id: UUID | None = Field(None, description="Unique identifier")
    trigger_event: str = Field(..., description="Original event that triggered analysis")
    content: str = Field(..., description="Natural language explanation")
    classification: str = Field(..., description="opportunity, threat, or neutral")
    impact_score: float = Field(..., ge=0.0, le=1.0, description="Impact on goals (0-1)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence (0-1)")
    urgency: float = Field(..., ge=0.0, le=1.0, description="Urgency (0-1)")
    combined_score: float = Field(..., ge=0.0, le=1.0, description="Combined priority score")
    time_horizon: TimeHorizon = Field(..., description="Temporal categorization")
    time_to_impact: str | None = Field(None, description="Estimated time until impact")
    affected_goals: list[str] = Field(default_factory=list, description="Affected goal IDs")
    recommended_actions: list[str] = Field(default_factory=list, description="Recommended actions")
    action_timing: ActionTiming | None = Field(None, description="Optimal timing for action")
    is_closing_window: bool = Field(
        default=False,
        description="Whether this has a time-sensitive action window",
    )
    created_at: datetime | None = Field(None, description="When this was created")


class TimelineRequest(BaseModel):
    """Request parameters for timeline endpoint.

    Allows filtering and limiting timeline results.
    """

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum implications per horizon",
    )
    horizon_filter: TimeHorizon | None = Field(
        default=None,
        description="Filter to specific time horizon",
    )
    include_closing_windows: bool = Field(
        default=True,
        description="Include implications with closing action windows",
    )
    classification: str | None = Field(
        default=None,
        description="Filter by classification (opportunity, threat, neutral)",
    )
    min_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum combined score threshold",
    )


class TimelineView(BaseModel):
    """Response model for timeline endpoint.

    Organizes implications by time horizon for prioritized planning.
    """

    immediate: list[ImplicationWithTiming] = Field(
        default_factory=list,
        description="Implications materializing in days (1-7 days)",
    )
    short_term: list[ImplicationWithTiming] = Field(
        default_factory=list,
        description="Implications materializing in weeks (1-4 weeks)",
    )
    medium_term: list[ImplicationWithTiming] = Field(
        default_factory=list,
        description="Implications materializing in months (1-6 months)",
    )
    long_term: list[ImplicationWithTiming] = Field(
        default_factory=list,
        description="Implications materializing in quarters+ (6+ months)",
    )
    closing_windows: list[ImplicationWithTiming] = Field(
        default_factory=list,
        description="Implications with time-sensitive action windows",
    )
    total_count: int = Field(
        ...,
        ge=0,
        description="Total number of implications across all horizons",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to process the request in milliseconds",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this timeline was generated",
    )


class TimeHorizonCategorization(BaseModel):
    """LLM response for categorizing an implication's time horizon.

    Used to parse structured LLM output for temporal analysis.
    """

    time_horizon: TimeHorizon = Field(
        ...,
        description="Categorized time horizon",
    )
    time_to_impact: str = Field(
        ...,
        description="Natural language time estimate (e.g., '2-3 weeks')",
    )
    is_closing_window: bool = Field(
        default=False,
        description="Whether action window is closing",
    )
    closing_window_reason: str | None = Field(
        default=None,
        description="Why the window is time-sensitive",
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in categorization",
    )


# Life Sciences Domain Knowledge Constants
FDA_TIMELINES = {
    "bla_review": "6-12 months",
    "bla_submission": "6-12 months",
    "510k_clearance": "3-6 months",
    "pdufa_date": "6-12 months",
    "nda_review": "10-12 months",
    "fda_response": "1-2 months",
}

CLINICAL_TRIAL_PHASES = {
    "phase_1": "1-2 years",
    "phase_2": "2-3 years",
    "phase_3": "3-4 years",
    "phase_4": "1-2 years",
    "post_market": "ongoing",
}

BUSINESS_CYCLES = {
    "budget_planning": "Q3 for next year",
    "fiscal_year": "12 months",
    "quarterly_review": "3 months",
    "contract_renewal": "annually",
}

CONFERENCE_SCHEDULES = {
    "asco": "June (abstract deadline Feb)",
    "jpm_healthcare": "January",
    "bio_international": "June",
    "ahip": "June",
}
