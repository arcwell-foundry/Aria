"""Websets data models for Exa bulk lead generation.

Websets API provides asynchronous bulk entity discovery.
When a user approves a pipeline goal (e.g., "Build CDMO pipeline in Northeast"),
Hunter creates a Webset, adds enrichment for contact info, and results
flow into the Pipeline page as they arrive.

Phase 3: Websets Integration for Bulk Lead Generation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WebsetStatus(str, Enum):
    """Status of a Webset job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityType(str, Enum):
    """Type of entity to discover via Webset."""

    COMPANY = "company"
    PERSON = "person"


class EnrichmentFormat(str, Enum):
    """Format for enrichment field values."""

    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    DATE = "date"
    NUMBER = "number"
    OPTIONS = "options"


# ── Request Models ───────────────────────────────────────────────────────


class WebsetSearchConfig(BaseModel):
    """Configuration for Webset search."""

    query: str = Field(..., description="Search query for entity discovery")
    entity_type: EntityType = Field(
        default=EntityType.COMPANY,
        description="Type of entity to discover",
    )


class EnrichmentRequest(BaseModel):
    """Request to add enrichment task to a Webset."""

    description: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Natural language description of enrichment task (1-5000 chars)",
    )
    format: EnrichmentFormat = Field(
        default=EnrichmentFormat.TEXT,
        description="Expected format of enrichment result",
    )


class WebsetCreateRequest(BaseModel):
    """Request to create a new Webset."""

    search: WebsetSearchConfig = Field(
        ...,
        description="Search configuration for entity discovery",
    )
    external_id: str | None = Field(
        default=None,
        description="External ID to link to goal_id or other reference",
    )


class WebhookRegisterRequest(BaseModel):
    """Request to register a webhook for Webset events."""

    webhook_url: str = Field(..., description="URL to receive webhook events")
    events: list[str] = Field(
        default=["webset.items.completed"],
        description="List of event types to subscribe to",
    )


# ── Response Models ───────────────────────────────────────────────────────


class WebsetResponse(BaseModel):
    """Response from Webset API."""

    id: str = Field(..., description="Exa Webset ID")
    status: WebsetStatus = Field(..., description="Current Webset status")
    items_count: int = Field(default=0, description="Total items in Webset")
    created_at: datetime = Field(..., description="Webset creation timestamp")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")


class WebsetItemContact(BaseModel):
    """Contact information extracted from a Webset item."""

    name: str | None = Field(default=None, description="Contact name")
    title: str | None = Field(default=None, description="Job title")
    email: str | None = Field(default=None, description="Email address")
    phone: str | None = Field(default=None, description="Phone number")
    linkedin_url: str | None = Field(default=None, description="LinkedIn profile URL")


class WebsetItem(BaseModel):
    """A single item from a Webset."""

    id: str = Field(..., description="Item ID")
    name: str = Field(..., description="Company or person name")
    url: str | None = Field(default=None, description="Website URL")
    description: str | None = Field(default=None, description="Entity description")
    domain: str | None = Field(default=None, description="Website domain")

    # Enriched fields
    founded_year: int | None = Field(default=None, description="Year founded")
    employee_count: int | None = Field(default=None, description="Employee count")
    headquarters: str | None = Field(default=None, description="Headquarters location")
    industry: str | None = Field(default=None, description="Industry classification")
    revenue: str | None = Field(default=None, description="Revenue range")
    funding_stage: str | None = Field(default=None, description="Latest funding stage")

    # Contacts (enriched)
    contacts: list[WebsetItemContact] = Field(
        default_factory=list,
        description="Enriched contacts",
    )

    # Raw data from Exa
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw data from Exa API",
    )

    # Metadata
    score: float = Field(default=0.0, description="Relevance score")
    enriched_at: datetime | None = Field(
        default=None,
        description="When enrichment was completed",
    )


class WebsetItemsResponse(BaseModel):
    """Paginated response of Webset items."""

    items: list[WebsetItem] = Field(default_factory=list, description="Webset items")
    next_cursor: str | None = Field(
        default=None,
        description="Cursor for next page of results",
    )
    has_more: bool = Field(default=False, description="Whether more items exist")


class EnrichmentResponse(BaseModel):
    """Response from enrichment creation."""

    id: str = Field(..., description="Enrichment task ID")
    webset_id: str = Field(..., description="Parent Webset ID")
    status: str = Field(..., description="Enrichment status")
    description: str = Field(..., description="Enrichment task description")
    created_at: datetime = Field(..., description="Creation timestamp")


class WebhookResponse(BaseModel):
    """Response from webhook registration."""

    id: str = Field(..., description="Webhook ID")
    url: str = Field(..., description="Webhook URL")
    events: list[str] = Field(..., description="Subscribed events")
    secret: str | None = Field(default=None, description="Webhook secret for verification")
    created_at: datetime = Field(..., description="Registration timestamp")


# ── Webhook Event Models ───────────────────────────────────────────────────


class WebsetItemCompletedEvent(BaseModel):
    """Event payload for webset.items.completed webhook."""

    webset_id: str = Field(..., description="Webset ID")
    item_id: str = Field(..., description="Completed item ID")
    event_type: str = Field(default="webset.items.completed")
    timestamp: datetime = Field(..., description="Event timestamp")
    data: dict[str, Any] = Field(default_factory=dict, description="Item data")


class WebsetCompletedEvent(BaseModel):
    """Event payload for webset.completed webhook."""

    webset_id: str = Field(..., description="Webset ID")
    event_type: str = Field(default="webset.completed")
    timestamp: datetime = Field(..., description="Event timestamp")
    items_count: int = Field(..., description="Total items processed")


# ── Database Models ────────────────────────────────────────────────────────


class WebsetJobCreate(BaseModel):
    """Data for creating a Webset job record."""

    webset_id: str = Field(..., description="Exa Webset ID")
    user_id: str = Field(..., description="User who initiated the job")
    goal_id: str | None = Field(default=None, description="Associated goal ID")
    entity_type: EntityType = Field(..., description="Type of entity")
    search_query: str = Field(..., description="Original search query")


class WebsetJobResponse(BaseModel):
    """Response for a Webset job record."""

    id: str = Field(..., description="Job UUID")
    webset_id: str = Field(..., description="Exa Webset ID")
    user_id: str = Field(..., description="User who initiated the job")
    goal_id: str | None = Field(default=None, description="Associated goal ID")
    status: WebsetStatus = Field(..., description="Job status")
    entity_type: EntityType = Field(..., description="Type of entity")
    search_query: str = Field(..., description="Original search query")
    items_imported: int = Field(default=0, description="Number of items imported")
    error_message: str | None = Field(default=None, description="Error if failed")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
