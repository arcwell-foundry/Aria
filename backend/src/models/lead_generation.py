"""Lead generation workflow models (US-939).

Pydantic models for ICP definition, discovered leads,
score breakdowns, pipeline views, and outreach.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SAVED = "saved"


class PipelineStage(str, Enum):
    PROSPECT = "prospect"
    QUALIFIED = "qualified"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"


# ICP Models
class ICPDefinition(BaseModel):
    industry: list[str] = Field(default_factory=list)
    company_size: dict[str, int] = Field(default_factory=lambda: {"min": 0, "max": 0})
    modalities: list[str] = Field(default_factory=list)
    therapeutic_areas: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ICPResponse(BaseModel):
    id: str
    user_id: str
    icp_data: ICPDefinition
    version: int
    created_at: datetime
    updated_at: datetime


# Score Breakdown
class ScoreFactor(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    explanation: str


class LeadScoreBreakdown(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    factors: list[ScoreFactor]


# Discovered Lead Models
class DiscoveredLeadResponse(BaseModel):
    id: str
    user_id: str
    icp_id: str | None
    company_name: str
    company_data: dict[str, object]
    contacts: list[dict[str, object]]
    fit_score: int
    score_breakdown: LeadScoreBreakdown | None
    signals: list[str]
    review_status: ReviewStatus
    reviewed_at: datetime | None
    source: str
    lead_memory_id: str | None
    created_at: datetime
    updated_at: datetime


class LeadReviewRequest(BaseModel):
    action: ReviewStatus = Field(..., description="Review action: approved, rejected, or saved")


# Pipeline Models
class PipelineStageSummary(BaseModel):
    stage: PipelineStage
    count: int
    total_value: float


class PipelineSummary(BaseModel):
    stages: list[PipelineStageSummary]
    total_leads: int
    total_pipeline_value: float


# Outreach Models
class OutreachRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    tone: str = Field(default="professional")


class OutreachResponse(BaseModel):
    id: str
    lead_id: str
    draft_subject: str
    draft_body: str
    status: str
    created_at: datetime


# Discovery trigger
class DiscoverLeadsRequest(BaseModel):
    target_count: int = Field(default=10, ge=1, le=50)
