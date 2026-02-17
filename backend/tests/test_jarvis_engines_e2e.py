"""Phase 7 Jarvis Intelligence Engine end-to-end tests.

Tests the four core intelligence engines through their API routes:
1. Daily Briefing generation (BriefingService via /api/v1/briefings/generate)
2. Pre-meeting research (MeetingBriefService via /api/v1/meetings/{id}/brief)
3. Email draft with style matching (DraftService via /api/v1/drafts/email)
4. Market signals retrieval (SignalService via /api/v1/signals)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "test-user-jarvis-001"
    user.email = "jarvis-test@luminone.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create a test client with authentication overridden."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 1: Daily Briefing Generation
# ---------------------------------------------------------------------------


def test_daily_briefing_generation(test_client: TestClient) -> None:
    """POST /api/v1/briefings/generate returns briefing with all required sections.

    The BriefingService.generate_briefing() gathers calendar, leads, signals,
    and tasks data, then uses an LLM to produce an executive summary.
    The response must conform to the BriefingContent model with six fields:
    summary, calendar, leads, signals, tasks, and generated_at.
    """
    briefing_content = {
        "summary": (
            "Good morning. You have 3 meetings today including a strategic "
            "review with Lonza. Two hot leads need attention, and there is a "
            "new FDA approval signal for Catalent."
        ),
        "calendar": {
            "meeting_count": 3,
            "key_meetings": [
                {"title": "Lonza Strategic Review", "time": "10:00 AM"},
                {"title": "Team Standup", "time": "09:00 AM"},
                {"title": "Pipeline Review", "time": "02:00 PM"},
            ],
        },
        "leads": {
            "hot_leads": ["Lonza - Phase 3 expansion"],
            "needs_attention": ["Catalent - follow-up overdue"],
            "recently_active": [],
        },
        "signals": {
            "company_news": ["Catalent receives FDA approval for new facility"],
            "market_trends": [],
            "competitive_intel": [],
        },
        "tasks": {
            "overdue": [],
            "due_today": ["Send Lonza proposal revision"],
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }

    with patch("src.api.routes.briefings.BriefingService") as MockBriefingService:
        mock_service = MagicMock()
        mock_service.generate_briefing = AsyncMock(return_value=briefing_content)
        MockBriefingService.return_value = mock_service

        response = test_client.post("/api/v1/briefings/generate")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Verify all BriefingContent fields are present
    assert "summary" in data
    assert "calendar" in data
    assert "leads" in data
    assert "signals" in data
    assert "tasks" in data
    assert "generated_at" in data

    # Verify content quality
    assert len(data["summary"]) > 0
    assert data["calendar"]["meeting_count"] == 3
    assert len(data["leads"]["hot_leads"]) == 1
    assert len(data["signals"]["company_news"]) == 1

    # Verify the service was called with the correct user ID
    mock_service.generate_briefing.assert_called_once_with(
        "test-user-jarvis-001", None
    )


# ---------------------------------------------------------------------------
# Test 2: Pre-Meeting Research Brief
# ---------------------------------------------------------------------------


def test_pre_meeting_research(test_client: TestClient) -> None:
    """GET /api/v1/meetings/{calendar_event_id}/brief returns meeting research.

    The MeetingBriefService.get_brief() retrieves a pre-generated brief
    containing attendee profiles, company research, suggested agenda, and
    risks/opportunities. The response must match MeetingBriefResponse.
    """
    meeting_brief_data = {
        "id": "brief-abc-123",
        "calendar_event_id": "cal-evt-456",
        "meeting_title": "Lonza Q2 Strategy Session",
        "meeting_time": "2026-02-16T14:00:00Z",
        "status": "completed",
        "brief_content": {
            "summary": (
                "Strategic alignment meeting with Lonza biologics division. "
                "Key decision-makers attending. Previous engagement was positive."
            ),
            "attendees": [
                {
                    "email": "m.fischer@lonza.com",
                    "name": "Marc Fischer",
                    "title": "VP Biologics",
                    "company": "Lonza",
                    "talking_points": [
                        "Recent capacity expansion plans",
                        "mRNA manufacturing partnership opportunity",
                    ],
                }
            ],
            "company": {
                "name": "Lonza",
                "industry": "Life Sciences / CDMO",
                "recent_news": ["Lonza announces $500M Basel expansion"],
            },
            "suggested_agenda": [
                "Review Q1 collaboration milestones",
                "Discuss expanded mRNA capacity needs",
            ],
            "risks_opportunities": [
                "RISK: Lonza evaluating competitor bids for Phase 3 slot",
                "OPPORTUNITY: New Basel facility creates partnership opening",
            ],
        },
        "generated_at": "2026-02-16T12:30:00Z",
        "error_message": None,
    }

    with patch("src.api.routes.meetings.MeetingBriefService") as MockMeetingBriefService:
        mock_service = MagicMock()
        mock_service.get_brief = AsyncMock(return_value=meeting_brief_data)
        MockMeetingBriefService.return_value = mock_service

        response = test_client.get("/api/v1/meetings/cal-evt-456/brief")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Verify MeetingBriefResponse structure
    assert data["id"] == "brief-abc-123"
    assert data["calendar_event_id"] == "cal-evt-456"
    assert data["meeting_title"] == "Lonza Q2 Strategy Session"
    assert data["status"] == "completed"

    # Verify brief content contains research
    brief_content = data["brief_content"]
    assert "summary" in brief_content
    assert "attendees" in brief_content
    assert "company" in brief_content
    assert "suggested_agenda" in brief_content
    assert "risks_opportunities" in brief_content

    # Verify attendee research depth
    assert len(brief_content["attendees"]) == 1
    attendee = brief_content["attendees"][0]
    assert attendee["name"] == "Marc Fischer"
    assert len(attendee["talking_points"]) >= 1

    # Verify company research
    assert brief_content["company"]["name"] == "Lonza"
    assert len(brief_content["company"]["recent_news"]) >= 1

    # Verify the service was called correctly
    mock_service.get_brief.assert_called_once_with(
        "test-user-jarvis-001", "cal-evt-456"
    )


# ---------------------------------------------------------------------------
# Test 3: Email Draft with Style Matching
# ---------------------------------------------------------------------------


def test_email_draft_with_style(test_client: TestClient) -> None:
    """POST /api/v1/drafts/email creates a style-matched email draft.

    The DraftService.create_draft() generates a draft that matches the user's
    writing style (measured by style_match_score). The response must conform
    to EmailDraftResponse with subject, body, purpose, tone, and style score.
    """
    draft_response = {
        "id": "draft-jarvis-789",
        "user_id": "test-user-jarvis-001",
        "recipient_email": "m.fischer@lonza.com",
        "recipient_name": "Marc Fischer",
        "subject": "Following up on our Biologics Partnership Discussion",
        "body": (
            "Hi Marc,\n\n"
            "Great connecting at the strategy session yesterday. I wanted to "
            "follow up on the mRNA capacity discussion and share a few ideas "
            "that could accelerate our timeline.\n\n"
            "Would Thursday work for a 30-minute deep dive?\n\n"
            "Best,\nAlex"
        ),
        "purpose": "follow_up",
        "tone": "friendly",
        "context": {"meeting_ref": "Lonza Q2 Strategy Session"},
        "lead_memory_id": "lead-lonza-001",
        "style_match_score": 0.91,
        "status": "draft",
        "sent_at": None,
        "error_message": None,
        "created_at": "2026-02-16T15:00:00Z",
        "updated_at": "2026-02-16T15:00:00Z",
    }

    with patch("src.api.routes.drafts.get_draft_service") as mock_get_service:
        mock_service = AsyncMock()
        mock_service.create_draft = AsyncMock(return_value=draft_response)
        mock_get_service.return_value = mock_service

        response = test_client.post(
            "/api/v1/drafts/email",
            json={
                "recipient_email": "m.fischer@lonza.com",
                "recipient_name": "Marc Fischer",
                "purpose": "follow_up",
                "tone": "friendly",
                "context": "Met at Lonza Q2 Strategy Session, discussed mRNA capacity",
                "lead_memory_id": "lead-lonza-001",
            },
        )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    # Verify EmailDraftResponse structure
    assert data["id"] == "draft-jarvis-789"
    assert data["recipient_email"] == "m.fischer@lonza.com"
    assert data["recipient_name"] == "Marc Fischer"
    assert data["purpose"] == "follow_up"
    assert data["tone"] == "friendly"
    assert data["status"] == "draft"

    # Verify draft content quality
    assert len(data["subject"]) > 10, "Subject should be descriptive"
    assert len(data["body"]) > 50, "Body should be a substantive draft"
    assert "Marc" in data["body"], "Body should address recipient by name"

    # Verify style matching
    assert data["style_match_score"] is not None
    assert data["style_match_score"] >= 0.8, (
        "Style match score should be high for a well-matched draft"
    )

    # Verify the service received all parameters
    mock_service.create_draft.assert_called_once()
    call_kwargs = mock_service.create_draft.call_args.kwargs
    assert call_kwargs["user_id"] == "test-user-jarvis-001"
    assert call_kwargs["recipient_email"] == "m.fischer@lonza.com"
    assert call_kwargs["purpose"] == "follow_up"
    assert call_kwargs["tone"] == "friendly"
    assert call_kwargs["lead_memory_id"] == "lead-lonza-001"


# ---------------------------------------------------------------------------
# Test 4: Market Signals Structure
# ---------------------------------------------------------------------------


def test_market_signals_structure(test_client: TestClient) -> None:
    """GET /api/v1/signals returns market signals with correct structure.

    The SignalService.get_signals() retrieves monitored market signals
    including funding rounds, leadership changes, FDA approvals, and more.
    Each signal must include type, headline, relevance_score, and source.
    """
    signals_data = [
        {
            "id": "signal-001",
            "user_id": "test-user-jarvis-001",
            "company_name": "Catalent",
            "signal_type": "fda_approval",
            "headline": "Catalent receives FDA approval for new biologics facility",
            "summary": (
                "The FDA has approved Catalent's new 200,000 sq ft biologics "
                "manufacturing facility in Indiana, enabling expanded capacity "
                "for cell and gene therapy production."
            ),
            "source_url": "https://www.fiercepharma.com/catalent-fda-approval",
            "source_name": "FiercePharma",
            "relevance_score": 0.92,
            "detected_at": "2026-02-16T08:30:00Z",
            "read_at": None,
            "linked_lead_id": "lead-catalent-002",
        },
        {
            "id": "signal-002",
            "user_id": "test-user-jarvis-001",
            "company_name": "Lonza",
            "signal_type": "funding",
            "headline": "Lonza invests $500M in Basel biologics expansion",
            "summary": None,
            "source_url": "https://www.reuters.com/lonza-expansion",
            "source_name": "Reuters",
            "relevance_score": 0.87,
            "detected_at": "2026-02-15T14:00:00Z",
            "read_at": None,
            "linked_lead_id": None,
        },
        {
            "id": "signal-003",
            "user_id": "test-user-jarvis-001",
            "company_name": "Samsung Biologics",
            "signal_type": "leadership",
            "headline": "Samsung Biologics appoints new Chief Commercial Officer",
            "summary": None,
            "source_url": None,
            "source_name": "BioPharma Dive",
            "relevance_score": 0.65,
            "detected_at": "2026-02-14T09:00:00Z",
            "read_at": "2026-02-15T10:00:00Z",
            "linked_lead_id": None,
        },
    ]

    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=signals_data
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/signals")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Verify we got all signals
    assert len(data) == 3

    # Verify each signal has required fields
    required_fields = {
        "id", "company_name", "signal_type", "headline",
        "relevance_score", "detected_at",
    }
    for signal in data:
        for field in required_fields:
            assert field in signal, f"Signal missing required field: {field}"

    # Verify signal type diversity (multiple engine types)
    signal_types = {s["signal_type"] for s in data}
    assert "fda_approval" in signal_types
    assert "funding" in signal_types
    assert "leadership" in signal_types

    # Verify relevance scoring is present and in range
    for signal in data:
        assert 0.0 <= signal["relevance_score"] <= 1.0

    # Verify the highest relevance signal is the FDA approval
    sorted_signals = sorted(data, key=lambda s: s["relevance_score"], reverse=True)
    assert sorted_signals[0]["signal_type"] == "fda_approval"
    assert sorted_signals[0]["company_name"] == "Catalent"

    # Verify read/unread state tracking
    unread = [s for s in data if s["read_at"] is None]
    assert len(unread) == 2, "Two signals should be unread"

    # Verify linked lead association
    linked = [s for s in data if s["linked_lead_id"] is not None]
    assert len(linked) == 1, "One signal should be linked to a lead"
    assert linked[0]["linked_lead_id"] == "lead-catalent-002"
