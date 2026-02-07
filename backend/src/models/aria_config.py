"""Pydantic models for ARIA role configuration and persona settings."""

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class ARIARole(str, Enum):
    """ARIA's focus area / role configuration."""

    SALES_OPS = "sales_ops"
    BD_SALES = "bd_sales"
    MARKETING = "marketing"
    EXECUTIVE_SUPPORT = "executive_support"
    CUSTOM = "custom"


class NotificationFrequency(str, Enum):
    """Notification frequency options."""

    MINIMAL = "minimal"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class ResponseDepth(str, Enum):
    """Response depth options."""

    BRIEF = "brief"
    MODERATE = "moderate"
    DETAILED = "detailed"


class PersonalityTraits(BaseModel):
    """User-configurable personality sliders.

    Each trait is 0.0-1.0. Defaults come from auto-calibration;
    user overrides are stored here.
    """

    proactiveness: float = Field(
        default=0.7, ge=0.0, le=1.0, description="0=reactive, 1=very proactive"
    )
    verbosity: float = Field(default=0.5, ge=0.0, le=1.0, description="0=terse, 1=detailed")
    formality: float = Field(default=0.5, ge=0.0, le=1.0, description="0=casual, 1=formal")
    assertiveness: float = Field(
        default=0.6, ge=0.0, le=1.0, description="0=suggestive, 1=directive"
    )


class DomainFocus(BaseModel):
    """Domain focus areas for ARIA to prioritize."""

    therapeutic_areas: list[str] = Field(
        default_factory=list, description="e.g. oncology, immunology"
    )
    modalities: list[str] = Field(default_factory=list, description="e.g. biologics, cell therapy")
    geographies: list[str] = Field(default_factory=list, description="e.g. North America, EU")


class CommunicationPrefs(BaseModel):
    """Communication channel and style preferences."""

    preferred_channels: list[str] = Field(
        default_factory=lambda: ["in_app"],
        description="in_app, email, slack",
    )
    notification_frequency: NotificationFrequency = Field(
        default=NotificationFrequency.BALANCED,
        description="How often ARIA sends notifications",
    )
    response_depth: ResponseDepth = Field(
        default=ResponseDepth.MODERATE,
        description="How detailed ARIA's responses are",
    )
    briefing_time: str = Field(default="08:00", description="Daily briefing time HH:MM")

    @field_validator("briefing_time")
    @classmethod
    def validate_briefing_time(cls, v: str) -> str:
        """Validate briefing_time is in HH:MM format."""
        pattern = r"^([01]\d|2[0-3]):([0-5]\d)$"
        if not re.match(pattern, v):
            raise ValueError("briefing_time must be in HH:MM format (00:00-23:59)")
        return v


class ARIAConfigUpdate(BaseModel):
    """Request model for creating/updating ARIA configuration."""

    role: ARIARole = Field(..., description="ARIA's focus area")
    custom_role_description: str | None = Field(None, description="Required when role is 'custom'")
    personality: PersonalityTraits = Field(default_factory=PersonalityTraits)
    domain_focus: DomainFocus = Field(default_factory=DomainFocus)
    competitor_watchlist: list[str] = Field(
        default_factory=list, description="Company names to monitor"
    )
    communication: CommunicationPrefs = Field(default_factory=CommunicationPrefs)

    @model_validator(mode="after")
    def validate_custom_role(self) -> "ARIAConfigUpdate":
        """Require custom_role_description when role is CUSTOM."""
        if self.role == ARIARole.CUSTOM and not self.custom_role_description:
            raise ValueError("custom_role_description is required when role is 'custom'")
        return self


class ARIAConfigResponse(BaseModel):
    """Response model for ARIA configuration."""

    role: ARIARole
    custom_role_description: str | None
    personality: PersonalityTraits
    domain_focus: DomainFocus
    competitor_watchlist: list[str]
    communication: CommunicationPrefs
    personality_defaults: PersonalityTraits
    updated_at: str | None


class PreviewResponse(BaseModel):
    """Response for the preview endpoint."""

    preview_message: str = Field(..., description="Sample ARIA message with given config")
    role_label: str = Field(..., description="Human-readable role name")
