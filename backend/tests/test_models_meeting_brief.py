"""Tests for meeting brief Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def test_attendee_profile_response_valid() -> None:
    """Test AttendeeProfileResponse accepts valid data."""
    from src.models.meeting_brief import AttendeeProfileResponse

    profile = AttendeeProfileResponse(
        email="john@example.com",
        name="John Smith",
        title="VP Sales",
        company="Acme Corp",
        linkedin_url="https://linkedin.com/in/johnsmith",
        background="15 years in enterprise sales",
        recent_activity=["Published article on B2B sales"],
        talking_points=["Ask about Q3 budget cycle"],
    )

    assert profile.email == "john@example.com"
    assert profile.name == "John Smith"
    assert len(profile.talking_points) == 1


def test_company_research_response_valid() -> None:
    """Test CompanyResearchResponse accepts valid data."""
    from src.models.meeting_brief import CompanyResearchResponse

    company = CompanyResearchResponse(
        name="Acme Corp",
        industry="Life Sciences",
        size="500-1000",
        recent_news=["Raised $50M Series B"],
        our_history="First contacted 3 months ago",
    )

    assert company.name == "Acme Corp"
    assert len(company.recent_news) == 1


def test_meeting_brief_content_valid() -> None:
    """Test MeetingBriefContent accepts valid data."""
    from src.models.meeting_brief import (
        AttendeeProfileResponse,
        CompanyResearchResponse,
        MeetingBriefContent,
    )

    brief = MeetingBriefContent(
        summary="Quarterly business review with key stakeholder",
        attendees=[
            AttendeeProfileResponse(
                email="john@example.com",
                name="John Smith",
            )
        ],
        company=CompanyResearchResponse(
            name="Acme Corp",
            industry="Life Sciences",
        ),
        suggested_agenda=["Review Q4 results", "Discuss expansion"],
        risks_opportunities=["Risk: Budget constraints", "Opportunity: New division"],
    )

    assert "Quarterly" in brief.summary
    assert len(brief.attendees) == 1


def test_meeting_brief_response_valid() -> None:
    """Test MeetingBriefResponse accepts valid data."""
    from src.models.meeting_brief import MeetingBriefResponse

    brief = MeetingBriefResponse(
        id="brief-123",
        calendar_event_id="evt-456",
        meeting_title="Q4 Review",
        meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
        status="completed",
        brief_content={
            "summary": "Meeting summary",
            "attendees": [],
            "suggested_agenda": [],
            "risks_opportunities": [],
        },
    )

    assert brief.id == "brief-123"
    assert brief.status == "completed"


def test_generate_brief_request_valid() -> None:
    """Test GenerateBriefRequest accepts valid data."""
    from src.models.meeting_brief import GenerateBriefRequest

    request = GenerateBriefRequest(
        calendar_event_id="evt-123",
        meeting_title="Discovery Call",
        meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
        attendee_emails=["john@example.com", "jane@example.com"],
    )

    assert request.calendar_event_id == "evt-123"
    assert len(request.attendee_emails) == 2


def test_generate_brief_request_requires_event_id() -> None:
    """Test GenerateBriefRequest requires calendar_event_id."""
    from src.models.meeting_brief import GenerateBriefRequest

    with pytest.raises(ValidationError):
        GenerateBriefRequest(
            meeting_title="Discovery Call",
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
        )


def test_upcoming_meeting_response_valid() -> None:
    """Test UpcomingMeetingResponse accepts valid data."""
    from src.models.meeting_brief import UpcomingMeetingResponse

    meeting = UpcomingMeetingResponse(
        calendar_event_id="evt-123",
        meeting_title="Q4 Review",
        meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=UTC),
        attendees=["john@example.com"],
        brief_status="completed",
        brief_id="brief-456",
    )

    assert meeting.calendar_event_id == "evt-123"
    assert meeting.brief_status == "completed"
