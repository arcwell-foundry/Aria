from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LifecycleStage(str, Enum):
    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    ACCOUNT = "account"


class LeadStatus(str, Enum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    DORMANT = "dormant"


class EventType(str, Enum):
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    MEETING = "meeting"
    CALL = "call"
    NOTE = "note"
    SIGNAL = "signal"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class StakeholderRole(str, Enum):
    DECISION_MAKER = "decision_maker"
    INFLUENCER = "influencer"
    CHAMPION = "champion"
    BLOCKER = "blocker"
    USER = "user"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class InsightType(str, Enum):
    OBJECTION = "objection"
    BUYING_SIGNAL = "buying_signal"
    COMMITMENT = "commitment"
    RISK = "risk"
    OPPORTUNITY = "opportunity"


class ContributionType(str, Enum):
    EVENT = "event"
    NOTE = "note"
    INSIGHT = "insight"


class ContributionStatus(str, Enum):
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


# Lead Memory Models
class LeadMemoryCreate(BaseModel):
    company_name: str
    company_id: str | None = None
    lifecycle_stage: LifecycleStage = LifecycleStage.LEAD
    expected_close_date: date | None = None
    expected_value: float | None = None
    tags: list[str] = []
    metadata: dict[str, object] = {}


class LeadMemoryUpdate(BaseModel):
    company_name: str | None = None
    lifecycle_stage: LifecycleStage | None = None
    status: LeadStatus | None = None
    health_score: int | None = Field(None, ge=0, le=100)
    expected_close_date: date | None = None
    expected_value: float | None = None
    tags: list[str] | None = None


class ConversionScoreSummary(BaseModel):
    """Summary of conversion score for lead response."""

    probability: float = Field(..., ge=0, le=100, description="Conversion probability 0-100%")
    confidence: float = Field(..., ge=0, le=1, description="Data completeness score 0-1")
    calculated_at: datetime | None = Field(None, description="When score was calculated")


class LeadMemoryResponse(BaseModel):
    id: str
    user_id: str
    company_name: str
    company_id: str | None
    lifecycle_stage: LifecycleStage
    status: LeadStatus
    health_score: int
    crm_id: str | None
    crm_provider: str | None
    first_touch_at: datetime | None
    last_activity_at: datetime | None
    expected_close_date: date | None
    expected_value: float | None
    tags: list[str]
    conversion_score: ConversionScoreSummary | None = Field(
        None, description="Conversion probability score from ML model"
    )
    created_at: datetime
    updated_at: datetime


# Event Models
class LeadEventCreate(BaseModel):
    event_type: EventType
    direction: Direction | None = None
    subject: str | None = None
    content: str | None = None
    participants: list[str] = []
    occurred_at: datetime
    source: str | None = None
    source_id: str | None = None


class LeadEventResponse(BaseModel):
    id: str
    lead_memory_id: str
    event_type: EventType
    direction: Direction | None
    subject: str | None
    content: str | None
    participants: list[str]
    occurred_at: datetime
    source: str | None
    created_at: datetime


# Stakeholder Models
class StakeholderCreate(BaseModel):
    contact_email: str
    contact_name: str | None = None
    title: str | None = None
    role: StakeholderRole | None = None
    influence_level: int = Field(5, ge=1, le=10)
    sentiment: Sentiment = Sentiment.NEUTRAL
    notes: str | None = None


class StakeholderUpdate(BaseModel):
    contact_name: str | None = None
    title: str | None = None
    role: StakeholderRole | None = None
    influence_level: int | None = Field(None, ge=1, le=10)
    sentiment: Sentiment | None = None
    notes: str | None = None


class StakeholderResponse(BaseModel):
    id: str
    lead_memory_id: str
    contact_email: str
    contact_name: str | None
    title: str | None
    role: StakeholderRole | None
    influence_level: int
    sentiment: Sentiment
    last_contacted_at: datetime | None
    notes: str | None
    created_at: datetime


# Insight Models
class InsightCreate(BaseModel):
    insight_type: InsightType
    content: str
    confidence: float = Field(0.7, ge=0, le=1)
    source_event_id: str | None = None


class InsightResponse(BaseModel):
    id: str
    lead_memory_id: str
    insight_type: InsightType
    content: str
    confidence: float
    source_event_id: str | None
    detected_at: datetime
    addressed_at: datetime | None


# Transition Request
class StageTransitionRequest(BaseModel):
    stage: LifecycleStage = Field(..., description="Target lifecycle stage")


# Contributor Models
class ContributorCreate(BaseModel):
    contributor_id: str = Field(..., description="User ID to add as contributor")
    contributor_name: str = Field(..., description="Full name of contributor")
    contributor_email: EmailStr = Field(..., description="Email of contributor")


class ContributorResponse(BaseModel):
    id: str
    lead_memory_id: str
    name: str
    email: EmailStr
    added_at: datetime
    contribution_count: int


# Contribution Models
class ContributionCreate(BaseModel):
    contribution_type: ContributionType = Field(..., description="Type of contribution")
    contribution_id: str | None = Field(
        None, description="ID of the event/note/insight being contributed"
    )
    content: str | None = Field(None, description="Content for note/insight contributions")


class ContributionResponse(BaseModel):
    id: str
    lead_memory_id: str
    contributor_id: str
    contributor_name: str
    contribution_type: ContributionType
    contribution_id: str | None
    content: str | None
    status: ContributionStatus
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by: str | None


class ContributionReviewRequest(BaseModel):
    action: Literal["merge", "reject"] = Field(..., description="Action: 'merge' or 'reject'")


# Conversion Scoring Models
class FeatureDriverResponse(BaseModel):
    """A feature that influences the conversion score."""

    name: str
    value: float
    contribution: float
    description: str


class ScoreExplanationResponse(BaseModel):
    """Full explanation of conversion score."""

    lead_memory_id: str
    conversion_probability: float
    confidence: float
    summary: str
    key_drivers: list[FeatureDriverResponse]
    key_risks: list[FeatureDriverResponse]
    recommendation: str


class BatchScoreResponse(BaseModel):
    """Result of batch scoring all leads."""

    scored: int
    errors: list[dict[str, str]]
    duration_seconds: float


class ConversionRankingItem(BaseModel):
    """A lead in the conversion rankings list."""

    id: str
    company_name: str
    lifecycle_stage: LifecycleStage
    conversion_probability: float
    confidence: float
    health_score: int
    expected_value: float | None


class ConversionRankingsResponse(BaseModel):
    """Ranked list of leads by conversion probability."""

    rankings: list[ConversionRankingItem]
    total_count: int
    scored_at: datetime
