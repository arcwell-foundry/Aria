"""Pydantic models for user preferences."""

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DefaultTone(str, Enum):
    """Default tone options for communications."""

    FORMAL = "formal"
    FRIENDLY = "friendly"
    URGENT = "urgent"


class MeetingBriefLeadHours(int, Enum):
    """Options for meeting brief lead time in hours."""

    TWO_HOURS = 2
    SIX_HOURS = 6
    TWELVE_HOURS = 12
    TWENTY_FOUR_HOURS = 24


class PreferenceCreate(BaseModel):
    """Request model for creating user preferences."""

    user_id: str = Field(..., description="User ID")
    briefing_time: str = Field("08:00", description="Daily briefing time in HH:MM format")
    meeting_brief_lead_hours: int = Field(24, description="Hours before meeting to generate brief")
    notification_email: bool = Field(True, description="Enable email notifications")
    notification_in_app: bool = Field(True, description="Enable in-app notifications")
    default_tone: DefaultTone = Field(
        DefaultTone.FRIENDLY, description="Default communication tone"
    )
    tracked_competitors: list[str] = Field(
        default_factory=list, description="List of tracked competitor names"
    )
    timezone: str = Field("UTC", description="User timezone")


class PreferenceUpdate(BaseModel):
    """Request model for updating user preferences (partial updates supported)."""

    briefing_time: str | None = Field(
        None, description="Daily briefing time in HH:MM format (00:00-23:59)"
    )
    meeting_brief_lead_hours: MeetingBriefLeadHours | None = Field(
        None, description="Hours before meeting to generate brief"
    )
    notification_email: bool | None = Field(None, description="Enable email notifications")
    notification_in_app: bool | None = Field(None, description="Enable in-app notifications")
    default_tone: DefaultTone | None = Field(None, description="Default communication tone")
    tracked_competitors: list[str] | None = Field(
        None, description="List of tracked competitor names"
    )
    timezone: str | None = Field(None, description="User timezone")

    @field_validator("briefing_time")
    @classmethod
    def validate_briefing_time(cls, v: str | None) -> str | None:
        """Validate briefing_time is in HH:MM format (00:00-23:59)."""
        if v is None:
            return v

        # Must match HH:MM format with leading zeros
        pattern = r"^([01]\d|2[0-3]):([0-5]\d)$"
        if not re.match(pattern, v):
            raise ValueError(
                "briefing_time must be in HH:MM format with valid hours (00-23) and minutes (00-59)"
            )
        return v


class PreferenceResponse(BaseModel):
    """Response model for user preferences."""

    id: str = Field(..., description="Preference record ID")
    user_id: str = Field(..., description="User ID")
    briefing_time: str = Field(..., description="Daily briefing time in HH:MM format")
    meeting_brief_lead_hours: int = Field(..., description="Hours before meeting to generate brief")
    notification_email: bool = Field(..., description="Email notifications enabled")
    notification_in_app: bool = Field(..., description="In-app notifications enabled")
    default_tone: str = Field(..., description="Default communication tone")
    tracked_competitors: list[str] = Field(..., description="List of tracked competitor names")
    timezone: str = Field(..., description="User timezone")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
