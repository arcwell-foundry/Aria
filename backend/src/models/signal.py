"""Market signal Pydantic models for ARIA.

This module contains all models related to market signals and monitored entities.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Type of market signal."""

    FUNDING = "funding"
    HIRING = "hiring"
    LEADERSHIP = "leadership"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    REGULATORY = "regulatory"
    EARNINGS = "earnings"
    CLINICAL_TRIAL = "clinical_trial"
    FDA_APPROVAL = "fda_approval"
    PATENT = "patent"


class EntityType(str, Enum):
    """Type of entity being monitored."""

    COMPANY = "company"
    PERSON = "person"
    TOPIC = "topic"


class SignalCreate(BaseModel):
    """Request model for creating a new market signal."""

    company_name: str = Field(..., description="Name of the company the signal is about")
    signal_type: SignalType = Field(..., description="Type of signal detected")
    headline: str = Field(..., description="Headline of the signal")
    summary: str | None = Field(None, description="Detailed summary of the signal")
    source_url: str | None = Field(None, description="URL to the source article")
    source_name: str | None = Field(None, description="Name of the source (e.g., TechCrunch)")
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Relevance score 0-1")
    linked_lead_id: str | None = Field(None, description="Optional link to a lead memory")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SignalResponse(BaseModel):
    """Response model for signal data."""

    id: str = Field(..., description="Signal ID")
    user_id: str = Field(..., description="User ID who owns the signal")
    company_name: str = Field(..., description="Name of the company")
    signal_type: SignalType = Field(..., description="Type of signal")
    headline: str = Field(..., description="Signal headline")
    summary: str | None = Field(None, description="Signal summary")
    source_url: str | None = Field(None, description="Source URL")
    source_name: str | None = Field(None, description="Source name")
    relevance_score: float = Field(..., description="Relevance score 0-1")
    detected_at: datetime = Field(..., description="When the signal was detected")
    read_at: datetime | None = Field(None, description="When the signal was read")
    linked_lead_id: str | None = Field(None, description="Linked lead ID")


class MonitoredEntityCreate(BaseModel):
    """Request model for creating a monitored entity."""

    entity_type: EntityType = Field(..., description="Type of entity to monitor")
    entity_name: str = Field(..., description="Name of the entity to monitor")
    monitoring_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration for monitoring (frequency, signal_types, etc.)",
    )


class MonitoredEntityResponse(BaseModel):
    """Response model for monitored entity data."""

    id: str = Field(..., description="Entity ID")
    user_id: str = Field(..., description="User ID who owns the entity")
    entity_type: EntityType = Field(..., description="Type of entity")
    entity_name: str = Field(..., description="Name of the entity")
    monitoring_config: dict[str, Any] = Field(..., description="Monitoring configuration")
    is_active: bool = Field(..., description="Whether monitoring is active")
    last_checked_at: datetime | None = Field(None, description="Last time entity was checked")
    created_at: datetime = Field(..., description="When entity was added")
