"""Pydantic models for Analytics API responses."""

from pydantic import BaseModel, Field


class OverviewMetricsResponse(BaseModel):
    """High-level overview metrics response."""

    leads_created: int = Field(..., ge=0, description="Number of leads created in period")
    meetings_booked: int = Field(
        ..., ge=0, description="Number of meetings booked with external attendees"
    )
    emails_sent: int = Field(..., ge=0, description="Number of emails sent in period")
    debriefs_completed: int = Field(..., ge=0, description="Number of meeting debriefs completed")
    goals_completed: int = Field(..., ge=0, description="Number of goals marked complete")
    avg_health_score: float | None = Field(
        None, ge=0, le=100, description="Average health score across active leads"
    )
    time_saved_minutes: int = Field(
        ..., ge=0, description="Total estimated minutes saved from ARIA actions"
    )


class ConversionFunnelResponse(BaseModel):
    """Conversion funnel metrics response."""

    stages: dict[str, int] = Field(
        default_factory=dict,
        description="Count of leads in each lifecycle stage (lead, opportunity, account)",
    )
    conversion_rates: dict[str, float | None] = Field(
        default_factory=dict,
        description="Stage-to-stage conversion rates (e.g., lead_to_opportunity)",
    )
    avg_days_in_stage: dict[str, float | None] = Field(
        default_factory=dict,
        description="Average days spent in each stage",
    )


class ActivityTrendPoint(BaseModel):
    """Single data point in activity trend series."""

    date: str = Field(
        ..., description="Date bucket (YYYY-MM-DD, YYYY-MM-DD for week, or YYYY-MM for month)"
    )
    count: int = Field(..., ge=0, description="Count of activities in this bucket")


class ActivityTrendsResponse(BaseModel):
    """Activity trends time series response."""

    granularity: str = Field(..., description="Time grouping: 'day', 'week', or 'month'")
    series: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Time series for each metric (emails_sent, meetings, aria_actions, leads_created)",
    )


class ResponseTimeTrendPoint(BaseModel):
    """Single data point in response time trend."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    avg_response_minutes: float = Field(..., ge=0, description="Average response time in minutes")


class ResponseTimeMetricsResponse(BaseModel):
    """Response time metrics response."""

    avg_response_minutes: float | None = Field(
        None, ge=0, description="Overall average response time in minutes"
    )
    by_lead: dict[str, float] = Field(
        default_factory=dict,
        description="Average response time per lead (lead_memory_id -> minutes)",
    )
    trend: list[ResponseTimeTrendPoint] = Field(
        default_factory=list,
        description="Daily response time trend",
    )


class PipelineImpactBreakdown(BaseModel):
    """Pipeline impact breakdown for a single impact type."""

    count: int = Field(..., ge=0, description="Number of impacts of this type")
    estimated_value: float = Field(..., ge=0, description="Total estimated value in dollars")


class AriaImpactSummaryResponse(BaseModel):
    """ARIA impact summary response."""

    total_actions: int = Field(..., ge=0, description="Total ARIA actions taken")
    by_action_type: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of actions by type (email_draft, meeting_prep, etc.)",
    )
    estimated_time_saved_minutes: int = Field(
        ..., ge=0, description="Total estimated minutes saved"
    )
    pipeline_impact: dict[str, PipelineImpactBreakdown] = Field(
        default_factory=dict,
        description="Pipeline impact breakdown by type",
    )


class PeriodComparisonResponse(BaseModel):
    """Period-over-period comparison response."""

    current: OverviewMetricsResponse = Field(..., description="Metrics for current period")
    previous: OverviewMetricsResponse = Field(..., description="Metrics for previous period")
    delta_pct: dict[str, float | None] = Field(
        default_factory=dict,
        description="Percentage change for each metric (absolute for avg_health_score)",
    )
