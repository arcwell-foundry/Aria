"""Pydantic models for US-940 Activity Feed."""

from pydantic import BaseModel, Field


class ActivityCreate(BaseModel):
    """Request body for recording an activity."""

    agent: str | None = Field(None, description="Which agent performed this")
    activity_type: str = Field(..., min_length=1, description="Activity type key")
    title: str = Field(..., min_length=1, description="Short title")
    description: str = Field("", description="Longer description")
    reasoning: str = Field("", description="ARIA reasoning chain")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence 0-1")
    related_entity_type: str | None = Field(None, description="lead, goal, contact, company")
    related_entity_id: str | None = Field(None, description="UUID of related entity")
    metadata: dict = Field(default_factory=dict, description="Extra metadata")


class ActivityFilter(BaseModel):
    """Query parameters for filtering the activity feed."""

    agent: str | None = None
    activity_type: str | None = None
    date_start: str | None = Field(None, description="ISO date start")
    date_end: str | None = Field(None, description="ISO date end")
    search: str | None = Field(None, description="Text search in title/description")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ActivityItem(BaseModel):
    """Response model for a single activity."""

    id: str
    user_id: str
    agent: str | None = None
    activity_type: str
    title: str
    description: str = ""
    reasoning: str = ""
    confidence: float = 0.5
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
