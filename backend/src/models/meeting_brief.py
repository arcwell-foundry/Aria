"""Pydantic models for pre-meeting research briefs."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BriefStatus(str, Enum):
    """Status of meeting brief generation."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AttendeeProfileResponse(BaseModel):
    """Attendee profile with research data."""

    email: str = Field(..., description="Attendee email address")
    name: str | None = Field(default=None, description="Full name")
    title: str | None = Field(default=None, description="Job title")
    company: str | None = Field(default=None, description="Company name")
    linkedin_url: str | None = Field(default=None, description="LinkedIn profile URL")
    background: str | None = Field(default=None, description="Professional background summary")
    recent_activity: list[str] = Field(
        default_factory=list, description="Recent professional activities"
    )
    talking_points: list[str] = Field(
        default_factory=list, description="Suggested conversation topics"
    )


class CompanyResearchResponse(BaseModel):
    """Company research data."""

    name: str = Field(..., description="Company name")
    industry: str | None = Field(default=None, description="Industry sector")
    size: str | None = Field(default=None, description="Company size range")
    recent_news: list[str] = Field(default_factory=list, description="Recent news items")
    our_history: str | None = Field(
        default=None, description="History of our interactions with this company"
    )


class MeetingBriefContent(BaseModel):
    """Full meeting brief content structure."""

    summary: str = Field(..., description="One paragraph meeting context summary")
    attendees: list[AttendeeProfileResponse] = Field(
        default_factory=list, description="Researched attendee profiles"
    )
    company: CompanyResearchResponse | None = Field(
        default=None, description="Primary company research"
    )
    suggested_agenda: list[str] = Field(
        default_factory=list, description="Suggested meeting agenda items"
    )
    risks_opportunities: list[str] = Field(
        default_factory=list, description="Identified risks and opportunities"
    )


class MeetingBriefResponse(BaseModel):
    """Response model for a meeting brief."""

    id: str = Field(..., description="Brief ID")
    calendar_event_id: str = Field(..., description="Calendar event reference")
    meeting_title: str | None = Field(default=None, description="Meeting title")
    meeting_time: datetime = Field(..., description="Scheduled meeting time")
    status: BriefStatus = Field(..., description="Brief generation status")
    brief_content: dict[str, Any] = Field(default_factory=dict, description="Brief content JSON")
    generated_at: datetime | None = Field(default=None, description="When brief was generated")
    error_message: str | None = Field(default=None, description="Error message if failed")


class GenerateBriefRequest(BaseModel):
    """Request to generate a meeting brief."""

    calendar_event_id: str = Field(..., description="Calendar event ID")
    meeting_title: str | None = Field(default=None, description="Meeting title")
    meeting_time: datetime = Field(..., description="Meeting start time")
    attendee_emails: list[str] = Field(
        default_factory=list, description="List of attendee email addresses"
    )


class UpcomingMeetingResponse(BaseModel):
    """Response for upcoming meeting with brief status."""

    calendar_event_id: str = Field(..., description="Calendar event ID")
    meeting_title: str | None = Field(default=None, description="Meeting title")
    meeting_time: datetime = Field(..., description="Meeting start time")
    attendees: list[str] = Field(default_factory=list, description="Attendee emails")
    brief_status: BriefStatus | None = Field(default=None, description="Brief status if exists")
    brief_id: str | None = Field(default=None, description="Brief ID if exists")
