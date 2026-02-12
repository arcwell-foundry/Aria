"""Pydantic models for ROI (Return on Investment) metrics."""

from pydantic import BaseModel, Field, field_validator


class TimeSavedBreakdown(BaseModel):
    """Detailed breakdown of time saved across activities."""

    email_drafts: dict[str, int | float] = Field(
        default_factory=dict,
        description="Email drafts time savings: {count, estimated_hours}",
    )
    meeting_prep: dict[str, int | float] = Field(
        default_factory=dict,
        description="Meeting prep time savings: {count, estimated_hours}",
    )
    research_reports: dict[str, int | float] = Field(
        default_factory=dict,
        description="Research reports time savings: {count, estimated_hours}",
    )
    crm_updates: dict[str, int | float] = Field(
        default_factory=dict,
        description="CRM updates time savings: {count, estimated_hours}",
    )


class TimeSavedMetrics(BaseModel):
    """Time saved metrics for ROI calculation."""

    hours: float = Field(
        ...,
        ge=0.0,
        description="Total hours saved in the period",
    )
    breakdown: TimeSavedBreakdown = Field(
        default_factory=TimeSavedBreakdown,
        description="Detailed breakdown of time savings by activity",
    )


class IntelligenceDeliveredMetrics(BaseModel):
    """Intelligence delivered metrics showing ARIA's knowledge contributions."""

    facts_discovered: int = Field(
        ...,
        ge=0,
        description="Number of facts discovered and stored in semantic memory",
    )
    signals_detected: int = Field(
        ...,
        ge=0,
        description="Number of market signals detected from communications",
    )
    gaps_filled: int = Field(
        ...,
        ge=0,
        description="Number of knowledge gaps filled proactively",
    )
    briefings_generated: int = Field(
        ...,
        ge=0,
        description="Number of meeting briefings generated",
    )


class ActionsTakenMetrics(BaseModel):
    """Actions taken metrics showing ARIA's autonomous and assisted actions."""

    total: int = Field(
        ...,
        ge=0,
        description="Total actions taken by ARIA",
    )
    auto_approved: int = Field(
        ...,
        ge=0,
        description="Actions taken automatically without user review",
    )
    user_approved: int = Field(
        ...,
        ge=0,
        description="Actions taken after user review and approval",
    )
    rejected: int = Field(
        ...,
        ge=0,
        description="Actions suggested but rejected by user",
    )


class PipelineImpactMetrics(BaseModel):
    """Pipeline impact metrics showing ARIA's contribution to sales pipeline."""

    leads_discovered: int = Field(
        ...,
        ge=0,
        description="Number of new leads discovered by ARIA",
    )
    meetings_prepped: int = Field(
        ...,
        ge=0,
        description="Number of meetings prepared with briefings",
    )
    follow_ups_sent: int = Field(
        ...,
        ge=0,
        description="Number of follow-up actions completed",
    )


class WeeklyTrendPoint(BaseModel):
    """A single data point in the weekly time-saved trend."""

    week_start: str = Field(
        ...,
        description="ISO date string for the start of the week (YYYY-MM-DD)",
    )
    hours_saved: float = Field(
        ...,
        ge=0.0,
        description="Total hours saved during this week",
    )


class PeriodValidation(BaseModel):
    """Validated time period for ROI metrics queries."""

    period: str = Field(
        ...,
        pattern="^(7d|30d|90d|all)$",
        description="Time period: 7d, 30d, 90d, or all",
    )

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        """Validate period is one of the allowed values."""
        allowed = {"7d", "30d", "90d", "all"}
        if v not in allowed:
            raise ValueError(f"Period must be one of {allowed}")
        return v


class ROIMetricsResponse(BaseModel):
    """Complete ROI metrics response for the dashboard."""

    # Core metrics
    time_saved: TimeSavedMetrics = Field(
        ...,
        description="Time saved metrics and breakdown",
    )
    intelligence_delivered: IntelligenceDeliveredMetrics = Field(
        ...,
        description="Intelligence discovery and delivery metrics",
    )
    actions_taken: ActionsTakenMetrics = Field(
        ...,
        description="Autonomous and assisted action metrics",
    )
    pipeline_impact: PipelineImpactMetrics = Field(
        ...,
        description="Sales pipeline impact metrics",
    )

    # Trend data
    weekly_trend: list[WeeklyTrendPoint] = Field(
        default_factory=list,
        description="Weekly time-saved trend for the period",
    )

    # Metadata
    period: str = Field(
        ...,
        description="Time period covered by these metrics (7d, 30d, 90d, all)",
    )
    calculated_at: str = Field(
        ...,
        description="ISO timestamp when metrics were calculated",
    )

    # Optional derived metrics
    time_saved_per_week: float | None = Field(
        None,
        ge=0.0,
        description="Average hours saved per week in the period",
    )
    action_approval_rate: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Rate of user-approved actions (auto + user) / total",
    )
