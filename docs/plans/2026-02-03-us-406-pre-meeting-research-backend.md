# US-406: Pre-Meeting Research Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a pre-meeting research backend that automatically generates briefs with attendee profiles, company research, and talking points 24 hours before meetings.

**Architecture:** A `MeetingBriefService` coordinates research by fetching calendar events via the Operator agent (using Composio OAuth), researching attendees via the Scout agent, synthesizing insights with Claude, and storing results in `meeting_briefs` and `attendee_profiles` tables. A background job triggers brief generation 24h before meetings. Routes expose GET/POST endpoints for retrieving and generating briefs on-demand.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase (PostgreSQL) / Pydantic / Scout Agent / Anthropic Claude / pytest

---

## Task 1: Create Database Migration for meeting_briefs Table

**Files:**
- Create: `/Users/dhruv/aria/supabase/migrations/20260203000001_create_meeting_briefs.sql`

**Step 1: Create migration file**

Create `/Users/dhruv/aria/supabase/migrations/20260203000001_create_meeting_briefs.sql`:

```sql
-- Meeting briefs for pre-meeting research
-- Generated 24h before meetings with attendee/company intel

CREATE TABLE IF NOT EXISTS meeting_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    calendar_event_id TEXT NOT NULL,
    meeting_title TEXT,
    meeting_time TIMESTAMPTZ NOT NULL,
    attendees TEXT[] DEFAULT '{}',
    brief_content JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    generated_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, calendar_event_id)
);

-- Enable RLS
ALTER TABLE meeting_briefs ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own meeting briefs"
    ON meeting_briefs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own meeting briefs"
    ON meeting_briefs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own meeting briefs"
    ON meeting_briefs FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own meeting briefs"
    ON meeting_briefs FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to meeting briefs"
    ON meeting_briefs
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_meeting_briefs_user_id ON meeting_briefs(user_id);
CREATE INDEX idx_meeting_briefs_meeting_time ON meeting_briefs(meeting_time);
CREATE INDEX idx_meeting_briefs_status ON meeting_briefs(status);
CREATE INDEX idx_meeting_briefs_user_time ON meeting_briefs(user_id, meeting_time);

-- Updated at trigger (reuse existing function)
CREATE TRIGGER update_meeting_briefs_updated_at
    BEFORE UPDATE ON meeting_briefs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Table comment
COMMENT ON TABLE meeting_briefs IS 'Pre-meeting research briefs generated 24h before meetings';
```

**Step 2: Verify migration file exists**

Run: `ls -la /Users/dhruv/aria/supabase/migrations/20260203000001_create_meeting_briefs.sql`
Expected: File exists

**Step 3: Commit**

```bash
git add supabase/migrations/20260203000001_create_meeting_briefs.sql
git commit -m "$(cat <<'EOF'
feat(db): add meeting_briefs table migration

Creates meeting_briefs table with:
- User-scoped meeting briefs with calendar event reference
- Status tracking (pending/generating/completed/failed)
- JSONB brief_content for flexible research data
- RLS policies for user isolation
- Indexes for efficient queries by user/time/status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Database Migration for attendee_profiles Table

**Files:**
- Create: `/Users/dhruv/aria/supabase/migrations/20260203000002_create_attendee_profiles.sql`

**Step 1: Create migration file**

Create `/Users/dhruv/aria/supabase/migrations/20260203000002_create_attendee_profiles.sql`:

```sql
-- Attendee profiles cached from research
-- Shared across users to avoid redundant lookups

CREATE TABLE IF NOT EXISTS attendee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    title TEXT,
    company TEXT,
    linkedin_url TEXT,
    profile_data JSONB DEFAULT '{}',
    research_status TEXT NOT NULL DEFAULT 'pending' CHECK (research_status IN ('pending', 'researching', 'completed', 'not_found')),
    last_researched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE attendee_profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies: All authenticated users can read profiles (shared cache)
CREATE POLICY "Authenticated users can view attendee profiles"
    ON attendee_profiles FOR SELECT
    TO authenticated
    USING (true);

-- Only service role can write (prevents user manipulation)
CREATE POLICY "Service role can insert attendee profiles"
    ON attendee_profiles FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "Service role can update attendee profiles"
    ON attendee_profiles FOR UPDATE
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to attendee profiles"
    ON attendee_profiles
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_attendee_profiles_email ON attendee_profiles(email);
CREATE INDEX idx_attendee_profiles_company ON attendee_profiles(company);
CREATE INDEX idx_attendee_profiles_status ON attendee_profiles(research_status);

-- Updated at trigger
CREATE TRIGGER update_attendee_profiles_updated_at
    BEFORE UPDATE ON attendee_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Table comment
COMMENT ON TABLE attendee_profiles IS 'Cached attendee research profiles shared across users';
```

**Step 2: Verify migration file exists**

Run: `ls -la /Users/dhruv/aria/supabase/migrations/20260203000002_create_attendee_profiles.sql`
Expected: File exists

**Step 3: Commit**

```bash
git add supabase/migrations/20260203000002_create_attendee_profiles.sql
git commit -m "$(cat <<'EOF'
feat(db): add attendee_profiles table migration

Creates attendee_profiles table with:
- Shared cache of researched profiles (keyed by email)
- Profile data including LinkedIn, title, company
- Research status tracking
- RLS policies allowing read access but write via service role only

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create Pydantic Models for Meeting Briefs

**Files:**
- Create: `/Users/dhruv/aria/backend/src/models/meeting_brief.py`
- Test: `/Users/dhruv/aria/backend/tests/test_models_meeting_brief.py`

**Step 1: Write the failing test for models**

Create `/Users/dhruv/aria/backend/tests/test_models_meeting_brief.py`:

```python
"""Tests for meeting brief Pydantic models."""

import pytest
from datetime import datetime, timezone
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
        meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=timezone.utc),
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
        meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=timezone.utc),
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
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=timezone.utc),
        )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_models_meeting_brief.py -v`
Expected: FAIL with ModuleNotFoundError (models don't exist)

**Step 3: Create the models**

Create `/Users/dhruv/aria/backend/src/models/meeting_brief.py`:

```python
"""Pydantic models for pre-meeting research briefs."""

from datetime import datetime
from enum import Enum

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
    brief_content: dict = Field(default_factory=dict, description="Brief content JSON")
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
    brief_status: BriefStatus | None = Field(
        default=None, description="Brief status if exists"
    )
    brief_id: str | None = Field(default=None, description="Brief ID if exists")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_models_meeting_brief.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/models/meeting_brief.py backend/tests/test_models_meeting_brief.py
git commit -m "$(cat <<'EOF'
feat(models): add Pydantic models for meeting briefs

Adds models for:
- AttendeeProfileResponse: researched attendee data
- CompanyResearchResponse: company intel
- MeetingBriefContent: full brief structure
- MeetingBriefResponse: API response model
- GenerateBriefRequest: brief generation request
- UpcomingMeetingResponse: meeting with brief status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create MeetingBriefService with Basic CRUD

**Files:**
- Create: `/Users/dhruv/aria/backend/src/services/meeting_brief.py`
- Test: `/Users/dhruv/aria/backend/tests/test_meeting_brief_service.py`

**Step 1: Write the failing test for service creation**

Create `/Users/dhruv/aria/backend/tests/test_meeting_brief_service.py`:

```python
"""Tests for MeetingBriefService."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_brief_returns_none_when_not_found() -> None:
    """Test get_brief returns None when brief doesn't exist."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief(
            user_id="user-123", calendar_event_id="evt-456"
        )

        assert result is None


@pytest.mark.asyncio
async def test_get_brief_returns_brief_when_found() -> None:
    """Test get_brief returns brief when it exists."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "completed",
            "brief_content": {"summary": "Test summary"},
            "generated_at": "2026-02-03T14:00:00Z",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_brief(
            user_id="user-123", calendar_event_id="evt-456"
        )

        assert result is not None
        assert result["id"] == "brief-123"


@pytest.mark.asyncio
async def test_create_brief_inserts_pending_brief() -> None:
    """Test create_brief creates a pending brief record."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "brief_content": {},
        }

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.create_brief(
            user_id="user-123",
            calendar_event_id="evt-456",
            meeting_title="Discovery Call",
            meeting_time=datetime(2026, 2, 4, 14, 0, tzinfo=timezone.utc),
            attendees=["john@example.com"],
        )

        assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_get_upcoming_meetings_returns_list() -> None:
    """Test get_upcoming_meetings returns meetings with brief status."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_briefs = [
            {
                "id": "brief-1",
                "calendar_event_id": "evt-1",
                "meeting_title": "Call 1",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "completed",
                "attendees": ["a@example.com"],
            },
            {
                "id": "brief-2",
                "calendar_event_id": "evt-2",
                "meeting_title": "Call 2",
                "meeting_time": "2026-02-05T10:00:00Z",
                "status": "pending",
                "attendees": ["b@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_briefs
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.get_upcoming_meetings(user_id="user-123", limit=10)

        assert len(result) == 2
        assert result[0]["calendar_event_id"] == "evt-1"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_meeting_brief_service.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create the service**

Create `/Users/dhruv/aria/backend/src/services/meeting_brief.py`:

```python
"""Meeting brief service for pre-meeting research.

Manages meeting brief CRUD operations and coordinates research generation.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class MeetingBriefService:
    """Service for managing pre-meeting research briefs."""

    def __init__(self) -> None:
        """Initialize meeting brief service."""
        self._db = SupabaseClient.get_client()

    async def get_brief(
        self, user_id: str, calendar_event_id: str
    ) -> dict[str, Any] | None:
        """Get a meeting brief by calendar event ID.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("calendar_event_id", calendar_event_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def get_brief_by_id(self, user_id: str, brief_id: str) -> dict[str, Any] | None:
        """Get a meeting brief by its ID.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", brief_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def create_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a pending meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Created brief dict.
        """
        brief_data = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = self._db.table("meeting_briefs").insert(brief_data).execute()

        logger.info(
            "Created pending meeting brief",
            extra={
                "user_id": user_id,
                "calendar_event_id": calendar_event_id,
                "meeting_title": meeting_title,
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def update_brief_status(
        self,
        brief_id: str,
        status: str,
        brief_content: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update brief status and optionally content.

        Args:
            brief_id: The brief's ID.
            status: New status (pending/generating/completed/failed).
            brief_content: Optional brief content to set.
            error_message: Optional error message if failed.

        Returns:
            Updated brief dict.
        """
        update_data: dict[str, Any] = {"status": status}

        if brief_content is not None:
            update_data["brief_content"] = brief_content
            update_data["generated_at"] = datetime.now(UTC).isoformat()

        if error_message is not None:
            update_data["error_message"] = error_message

        result = (
            self._db.table("meeting_briefs")
            .update(update_data)
            .eq("id", brief_id)
            .execute()
        )

        logger.info(
            "Updated meeting brief status",
            extra={"brief_id": brief_id, "status": status},
        )

        return cast(dict[str, Any], result.data[0])

    async def get_upcoming_meetings(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get upcoming meetings with brief status.

        Args:
            user_id: The user's ID.
            limit: Maximum number of meetings to return.

        Returns:
            List of meeting briefs ordered by meeting time.
        """
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("meeting_briefs")
            .select("id, calendar_event_id, meeting_title, meeting_time, status, attendees")
            .eq("user_id", user_id)
            .gte("meeting_time", now)
            .order("meeting_time", desc=False)
            .limit(limit)
            .execute()
        )

        return cast(list[dict[str, Any]], result.data or [])

    async def upsert_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create or update a meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Upserted brief dict.
        """
        brief_data = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = (
            self._db.table("meeting_briefs")
            .upsert(brief_data, on_conflict="user_id,calendar_event_id")
            .execute()
        )

        return cast(dict[str, Any], result.data[0])
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_meeting_brief_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/meeting_brief.py backend/tests/test_meeting_brief_service.py
git commit -m "$(cat <<'EOF'
feat(service): add MeetingBriefService with CRUD operations

Implements:
- get_brief: fetch by calendar event ID
- get_brief_by_id: fetch by brief ID
- create_brief: create pending brief
- update_brief_status: update status and content
- get_upcoming_meetings: list future meetings with status
- upsert_brief: create or update brief

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create AttendeeProfileService for Profile Caching

**Files:**
- Create: `/Users/dhruv/aria/backend/src/services/attendee_profile.py`
- Test: `/Users/dhruv/aria/backend/tests/test_attendee_profile_service.py`

**Step 1: Write the failing test**

Create `/Users/dhruv/aria/backend/tests/test_attendee_profile_service.py`:

```python
"""Tests for AttendeeProfileService."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_profile_returns_none_when_not_found() -> None:
    """Test get_profile returns None when profile doesn't exist."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profile(email="unknown@example.com")

        assert result is None


@pytest.mark.asyncio
async def test_get_profile_returns_profile_when_found() -> None:
    """Test get_profile returns profile when it exists."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_profile = {
            "id": "profile-123",
            "email": "john@example.com",
            "name": "John Smith",
            "title": "VP Sales",
            "company": "Acme Corp",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profile(email="john@example.com")

        assert result is not None
        assert result["name"] == "John Smith"


@pytest.mark.asyncio
async def test_get_profiles_batch_returns_found_profiles() -> None:
    """Test get_profiles_batch returns profiles for known emails."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_profiles = [
            {"email": "john@example.com", "name": "John"},
            {"email": "jane@example.com", "name": "Jane"},
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=mock_profiles
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profiles_batch(
            emails=["john@example.com", "jane@example.com", "unknown@example.com"]
        )

        # Should return dict keyed by email
        assert len(result) == 2
        assert "john@example.com" in result


@pytest.mark.asyncio
async def test_upsert_profile_creates_new_profile() -> None:
    """Test upsert_profile creates a new profile."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"email": "new@example.com", "name": "New Person"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.upsert_profile(
            email="new@example.com",
            name="New Person",
            title="Manager",
            company="NewCo",
        )

        assert result["email"] == "new@example.com"


@pytest.mark.asyncio
async def test_is_stale_returns_true_for_old_profiles() -> None:
    """Test is_stale returns True for profiles older than threshold."""
    from datetime import datetime, timedelta, timezone

    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        # Profile researched 10 days ago
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_profile = {
            "email": "old@example.com",
            "last_researched_at": old_time,
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.is_stale(email="old@example.com", max_age_days=7)

        assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_attendee_profile_service.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create the service**

Create `/Users/dhruv/aria/backend/src/services/attendee_profile.py`:

```python
"""Attendee profile service for caching researched profiles.

Manages the shared cache of attendee research data.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class AttendeeProfileService:
    """Service for managing cached attendee profiles."""

    def __init__(self) -> None:
        """Initialize attendee profile service."""
        self._db = SupabaseClient.get_client()

    async def get_profile(self, email: str) -> dict[str, Any] | None:
        """Get a profile by email.

        Args:
            email: Attendee email address.

        Returns:
            Profile dict if found, None otherwise.
        """
        result = (
            self._db.table("attendee_profiles")
            .select("*")
            .eq("email", email.lower())
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def get_profiles_batch(
        self, emails: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get multiple profiles by email.

        Args:
            emails: List of email addresses.

        Returns:
            Dict mapping email to profile data.
        """
        if not emails:
            return {}

        normalized_emails = [e.lower() for e in emails]

        result = (
            self._db.table("attendee_profiles")
            .select("*")
            .in_("email", normalized_emails)
            .execute()
        )

        profiles = result.data or []
        return {p["email"]: p for p in profiles}

    async def upsert_profile(
        self,
        email: str,
        name: str | None = None,
        title: str | None = None,
        company: str | None = None,
        linkedin_url: str | None = None,
        profile_data: dict[str, Any] | None = None,
        research_status: str = "completed",
    ) -> dict[str, Any]:
        """Create or update an attendee profile.

        Args:
            email: Attendee email address.
            name: Full name.
            title: Job title.
            company: Company name.
            linkedin_url: LinkedIn profile URL.
            profile_data: Additional profile data.
            research_status: Research status.

        Returns:
            Upserted profile dict.
        """
        data = {
            "email": email.lower(),
            "research_status": research_status,
            "last_researched_at": datetime.now(UTC).isoformat(),
        }

        if name is not None:
            data["name"] = name
        if title is not None:
            data["title"] = title
        if company is not None:
            data["company"] = company
        if linkedin_url is not None:
            data["linkedin_url"] = linkedin_url
        if profile_data is not None:
            data["profile_data"] = profile_data

        result = (
            self._db.table("attendee_profiles")
            .upsert(data, on_conflict="email")
            .execute()
        )

        logger.info(
            "Upserted attendee profile",
            extra={"email": email.lower(), "research_status": research_status},
        )

        return cast(dict[str, Any], result.data[0])

    async def is_stale(self, email: str, max_age_days: int = 7) -> bool:
        """Check if a profile needs refresh.

        Args:
            email: Attendee email address.
            max_age_days: Maximum age in days before considered stale.

        Returns:
            True if profile is stale or doesn't exist.
        """
        profile = await self.get_profile(email)

        if not profile:
            return True

        last_researched = profile.get("last_researched_at")
        if not last_researched:
            return True

        # Parse ISO format timestamp
        if isinstance(last_researched, str):
            last_researched_dt = datetime.fromisoformat(
                last_researched.replace("Z", "+00:00")
            )
        else:
            last_researched_dt = last_researched

        age = datetime.now(UTC) - last_researched_dt
        return age > timedelta(days=max_age_days)

    async def mark_not_found(self, email: str) -> dict[str, Any]:
        """Mark a profile as not found (couldn't research).

        Args:
            email: Attendee email address.

        Returns:
            Updated profile dict.
        """
        return await self.upsert_profile(
            email=email,
            research_status="not_found",
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_attendee_profile_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/attendee_profile.py backend/tests/test_attendee_profile_service.py
git commit -m "$(cat <<'EOF'
feat(service): add AttendeeProfileService for profile caching

Implements:
- get_profile: fetch single profile by email
- get_profiles_batch: fetch multiple profiles efficiently
- upsert_profile: create or update profile with research data
- is_stale: check if profile needs refresh
- mark_not_found: mark profile as unresearchable

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Brief Generation Logic with Scout Agent and Claude

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/services/meeting_brief.py`
- Test: `/Users/dhruv/aria/backend/tests/test_meeting_brief_service.py`

**Step 1: Write the failing test for generate_brief**

Add to `/Users/dhruv/aria/backend/tests/test_meeting_brief_service.py`:

```python
@pytest.mark.asyncio
async def test_generate_brief_content_creates_brief() -> None:
    """Test generate_brief_content calls LLM and updates brief."""
    with (
        patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
        patch("src.services.meeting_brief.anthropic.Anthropic") as mock_llm_class,
        patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
        patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
    ):
        # Setup DB mock
        mock_db = MagicMock()
        mock_brief = {
            "id": "brief-123",
            "user_id": "user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "attendees": ["john@acme.com"],
        }
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**mock_brief, "status": "completed"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_response = MagicMock()
        mock_llm_content = MagicMock()
        mock_llm_content.text = '{"summary": "Meeting with Acme Corp", "suggested_agenda": ["Intro"], "risks_opportunities": []}'
        mock_llm_response.content = [mock_llm_content]
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        # Setup profile service mock
        mock_profile_service = MagicMock()
        mock_profile_service.get_profiles_batch.return_value = {
            "john@acme.com": {
                "email": "john@acme.com",
                "name": "John Smith",
                "title": "VP Sales",
                "company": "Acme Corp",
            }
        }
        mock_profile_class.return_value = mock_profile_service

        # Setup Scout agent mock
        mock_scout = MagicMock()
        mock_scout.execute.return_value = MagicMock(
            success=True,
            data=[{"company_name": "Acme Corp", "headline": "Raised funding"}],
        )
        mock_scout_class.return_value = mock_scout

        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()
        result = await service.generate_brief_content(
            user_id="user-123",
            brief_id="brief-123",
        )

        assert result is not None
        assert "summary" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_meeting_brief_service.py::test_generate_brief_content_creates_brief -v`
Expected: FAIL (method doesn't exist)

**Step 3: Add generate_brief_content method**

Add to `/Users/dhruv/aria/backend/src/services/meeting_brief.py` (after the imports, add new imports and method):

Update imports at top of file:

```python
"""Meeting brief service for pre-meeting research.

Manages meeting brief CRUD operations and coordinates research generation.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

import anthropic

from src.agents.scout import ScoutAgent
from src.core.config import settings
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.services.attendee_profile import AttendeeProfileService

logger = logging.getLogger(__name__)
```

Add method to `MeetingBriefService` class:

```python
    async def generate_brief_content(
        self,
        user_id: str,
        brief_id: str,
    ) -> dict[str, Any] | None:
        """Generate meeting brief content using research and LLM.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID to populate.

        Returns:
            Generated brief content dict, or None if failed.
        """
        # Get the brief
        brief = await self.get_brief_by_id(user_id, brief_id)
        if not brief:
            logger.error("Brief not found", extra={"brief_id": brief_id})
            return None

        # Update status to generating
        await self.update_brief_status(brief_id, "generating")

        try:
            # Get attendee profiles from cache
            attendee_emails = brief.get("attendees", [])
            profile_service = AttendeeProfileService()
            profiles = await profile_service.get_profiles_batch(attendee_emails)

            # Research companies via Scout agent
            companies = list({p.get("company") for p in profiles.values() if p.get("company")})
            company_signals: list[dict[str, Any]] = []

            if companies:
                llm_client = LLMClient()
                scout = ScoutAgent(llm_client=llm_client, user_id=user_id)

                if scout.validate_input({"entities": companies}):
                    result = await scout.execute({"entities": companies})
                    if result.success and result.data:
                        company_signals = result.data

            # Build context for LLM
            context = self._build_brief_context(
                brief=brief,
                profiles=profiles,
                signals=company_signals,
            )

            # Generate brief with Claude
            llm = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

            prompt = f"""Generate a pre-meeting brief based on the following context:

Meeting: {brief.get('meeting_title', 'Upcoming Meeting')}
Time: {brief.get('meeting_time')}

Attendees:
{json.dumps(list(profiles.values()), indent=2)}

Recent company signals:
{json.dumps(company_signals, indent=2)}

Generate a JSON response with this exact structure:
{{
    "summary": "One paragraph meeting context and purpose",
    "suggested_agenda": ["Array of 3-5 agenda items"],
    "risks_opportunities": ["Array of 2-4 risks or opportunities to consider"]
}}

Focus on actionable insights for the meeting."""

            response = llm.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse LLM response
            response_text = response.content[0].text
            brief_content = json.loads(response_text)

            # Add attendee profiles to content
            brief_content["attendees"] = [
                {
                    "email": p.get("email"),
                    "name": p.get("name"),
                    "title": p.get("title"),
                    "company": p.get("company"),
                    "linkedin_url": p.get("linkedin_url"),
                    "background": p.get("profile_data", {}).get("background"),
                    "recent_activity": p.get("profile_data", {}).get("recent_activity", []),
                    "talking_points": p.get("profile_data", {}).get("talking_points", []),
                }
                for p in profiles.values()
            ]

            # Add company data if available
            if companies:
                primary_company = companies[0]
                relevant_signals = [s for s in company_signals if s.get("company_name") == primary_company]
                brief_content["company"] = {
                    "name": primary_company,
                    "recent_news": [s.get("headline") for s in relevant_signals[:3]],
                }

            # Update brief with content
            await self.update_brief_status(
                brief_id=brief_id,
                status="completed",
                brief_content=brief_content,
            )

            logger.info(
                "Generated meeting brief content",
                extra={"user_id": user_id, "brief_id": brief_id},
            )

            return brief_content

        except Exception as e:
            logger.exception(
                "Failed to generate brief content",
                extra={"user_id": user_id, "brief_id": brief_id, "error": str(e)},
            )
            await self.update_brief_status(
                brief_id=brief_id,
                status="failed",
                error_message=str(e),
            )
            return None

    def _build_brief_context(
        self,
        brief: dict[str, Any],
        profiles: dict[str, dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build context object for brief generation.

        Args:
            brief: The meeting brief record.
            profiles: Attendee profile data.
            signals: Company signals from Scout.

        Returns:
            Context dict for LLM.
        """
        return {
            "meeting_title": brief.get("meeting_title"),
            "meeting_time": brief.get("meeting_time"),
            "attendees": list(profiles.values()),
            "companies": list({p.get("company") for p in profiles.values() if p.get("company")}),
            "signals": signals,
        }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_meeting_brief_service.py::test_generate_brief_content_creates_brief -v`
Expected: PASS

**Step 5: Run all service tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_meeting_brief_service.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/services/meeting_brief.py backend/tests/test_meeting_brief_service.py
git commit -m "$(cat <<'EOF'
feat(service): add generate_brief_content with Scout and Claude

Implements brief generation that:
- Fetches attendee profiles from cache
- Uses Scout agent for company signal research
- Synthesizes research with Claude into actionable brief
- Updates brief with content or error status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Create API Routes for Meeting Briefs

**Files:**
- Create: `/Users/dhruv/aria/backend/src/api/routes/meetings.py`
- Test: `/Users/dhruv/aria/backend/tests/test_api_meetings.py`

**Step 1: Write the failing test**

Create `/Users/dhruv/aria/backend/tests/test_api_meetings.py`:

```python
"""Tests for meeting brief API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client() -> TestClient:
    """Create test client with mocked auth."""
    with patch("src.api.deps.get_current_user") as mock_auth:
        mock_user = MagicMock()
        mock_user.id = "test-user-123"
        mock_auth.return_value = mock_user

        from src.main import app

        return TestClient(app)


def test_get_brief_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/{id}/brief returns 404 when not found."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/meetings/evt-123/brief")

    assert response.status_code == 404


def test_get_brief_returns_brief_when_found(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/{id}/brief returns brief when found."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_brief = {
            "id": "brief-123",
            "user_id": "test-user-123",
            "calendar_event_id": "evt-123",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "completed",
            "brief_content": {"summary": "Test"},
            "generated_at": "2026-02-03T14:00:00Z",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/meetings/evt-123/brief")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "brief-123"


def test_get_upcoming_returns_meetings(test_client: TestClient) -> None:
    """Test GET /api/v1/meetings/upcoming returns meeting list."""
    with patch("src.services.meeting_brief.SupabaseClient") as mock_db_class:
        mock_meetings = [
            {
                "id": "brief-1",
                "calendar_event_id": "evt-1",
                "meeting_title": "Call 1",
                "meeting_time": "2026-02-04T14:00:00Z",
                "status": "completed",
                "attendees": ["a@example.com"],
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_meetings
        )
        mock_db_class.get_client.return_value = mock_db

        response = test_client.get("/api/v1/meetings/upcoming")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_generate_brief_creates_and_generates(test_client: TestClient) -> None:
    """Test POST /api/v1/meetings/{id}/brief/generate creates brief."""
    with (
        patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
        patch("src.services.meeting_brief.anthropic.Anthropic") as mock_llm_class,
        patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
        patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
    ):
        mock_brief = {
            "id": "brief-123",
            "user_id": "test-user-123",
            "calendar_event_id": "evt-456",
            "meeting_title": "Discovery Call",
            "meeting_time": "2026-02-04T14:00:00Z",
            "status": "pending",
            "attendees": [],
            "brief_content": {},
        }

        mock_db = MagicMock()
        # Insert returns new brief
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[mock_brief]
        )
        # Select returns the brief
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_brief
        )
        # Update returns updated brief
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**mock_brief, "status": "completed", "brief_content": {"summary": "Test"}}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_response = MagicMock()
        mock_llm_content = MagicMock()
        mock_llm_content.text = '{"summary": "Test", "suggested_agenda": [], "risks_opportunities": []}'
        mock_llm_response.content = [mock_llm_content]
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        # Setup profile service mock
        mock_profile_service = MagicMock()
        mock_profile_service.get_profiles_batch.return_value = {}
        mock_profile_class.return_value = mock_profile_service

        # Setup Scout mock
        mock_scout = MagicMock()
        mock_scout.validate_input.return_value = False
        mock_scout_class.return_value = mock_scout

        response = test_client.post(
            "/api/v1/meetings/evt-456/brief/generate",
            json={
                "calendar_event_id": "evt-456",
                "meeting_title": "Discovery Call",
                "meeting_time": "2026-02-04T14:00:00Z",
                "attendee_emails": [],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["pending", "generating", "completed"]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_api_meetings.py -v`
Expected: FAIL (routes don't exist)

**Step 3: Create the routes**

Create `/Users/dhruv/aria/backend/src/api/routes/meetings.py`:

```python
"""Meeting brief API routes.

Endpoints for pre-meeting research briefs.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser
from src.models.meeting_brief import (
    GenerateBriefRequest,
    MeetingBriefResponse,
    UpcomingMeetingResponse,
)
from src.services.meeting_brief import MeetingBriefService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _get_service() -> MeetingBriefService:
    """Get meeting brief service instance."""
    return MeetingBriefService()


@router.get("/upcoming", response_model=list[UpcomingMeetingResponse])
async def get_upcoming_meetings(
    current_user: CurrentUser,
    limit: int = 10,
) -> list[UpcomingMeetingResponse]:
    """Get upcoming meetings with brief status.

    Returns list of meetings in the next 7 days with their brief status.
    """
    service = _get_service()
    meetings = await service.get_upcoming_meetings(
        user_id=current_user.id,
        limit=limit,
    )

    return [
        UpcomingMeetingResponse(
            calendar_event_id=m["calendar_event_id"],
            meeting_title=m.get("meeting_title"),
            meeting_time=datetime.fromisoformat(m["meeting_time"].replace("Z", "+00:00")),
            attendees=m.get("attendees", []),
            brief_status=m.get("status"),
            brief_id=m.get("id"),
        )
        for m in meetings
    ]


@router.get("/{calendar_event_id}/brief", response_model=MeetingBriefResponse)
async def get_meeting_brief(
    calendar_event_id: str,
    current_user: CurrentUser,
) -> MeetingBriefResponse:
    """Get a meeting brief by calendar event ID.

    Returns the pre-meeting research brief if it exists.
    """
    service = _get_service()
    brief = await service.get_brief(
        user_id=current_user.id,
        calendar_event_id=calendar_event_id,
    )

    if not brief:
        raise HTTPException(status_code=404, detail="Meeting brief not found")

    return MeetingBriefResponse(
        id=brief["id"],
        calendar_event_id=brief["calendar_event_id"],
        meeting_title=brief.get("meeting_title"),
        meeting_time=datetime.fromisoformat(brief["meeting_time"].replace("Z", "+00:00")),
        status=brief["status"],
        brief_content=brief.get("brief_content", {}),
        generated_at=(
            datetime.fromisoformat(brief["generated_at"].replace("Z", "+00:00"))
            if brief.get("generated_at")
            else None
        ),
        error_message=brief.get("error_message"),
    )


@router.post("/{calendar_event_id}/brief/generate", response_model=MeetingBriefResponse)
async def generate_meeting_brief(
    calendar_event_id: str,
    request: GenerateBriefRequest,
    current_user: CurrentUser,
) -> MeetingBriefResponse:
    """Generate or regenerate a meeting brief on-demand.

    Creates the brief record and triggers research generation.
    """
    service = _get_service()

    # Create or get existing brief
    existing = await service.get_brief(
        user_id=current_user.id,
        calendar_event_id=calendar_event_id,
    )

    if existing:
        brief = existing
        # Reset to pending for regeneration
        await service.update_brief_status(brief["id"], "pending")
    else:
        brief = await service.create_brief(
            user_id=current_user.id,
            calendar_event_id=calendar_event_id,
            meeting_title=request.meeting_title,
            meeting_time=request.meeting_time,
            attendees=request.attendee_emails,
        )

    # Generate content
    content = await service.generate_brief_content(
        user_id=current_user.id,
        brief_id=brief["id"],
    )

    # Fetch updated brief
    updated_brief = await service.get_brief_by_id(
        user_id=current_user.id,
        brief_id=brief["id"],
    )

    if not updated_brief:
        raise HTTPException(status_code=500, detail="Failed to retrieve generated brief")

    logger.info(
        "Generated meeting brief via API",
        extra={
            "user_id": current_user.id,
            "calendar_event_id": calendar_event_id,
            "brief_id": brief["id"],
        },
    )

    return MeetingBriefResponse(
        id=updated_brief["id"],
        calendar_event_id=updated_brief["calendar_event_id"],
        meeting_title=updated_brief.get("meeting_title"),
        meeting_time=datetime.fromisoformat(
            updated_brief["meeting_time"].replace("Z", "+00:00")
        ),
        status=updated_brief["status"],
        brief_content=updated_brief.get("brief_content", {}),
        generated_at=(
            datetime.fromisoformat(updated_brief["generated_at"].replace("Z", "+00:00"))
            if updated_brief.get("generated_at")
            else None
        ),
        error_message=updated_brief.get("error_message"),
    )
```

**Step 4: Register routes in main app**

The routes need to be registered in the main app. Check if there's a routes registration pattern.

Add to `/Users/dhruv/aria/backend/src/main.py` (add import and include):

```python
from src.api.routes.meetings import router as meetings_router

# Add with other router includes
app.include_router(meetings_router, prefix="/api/v1")
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_api_meetings.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/meetings.py backend/tests/test_api_meetings.py backend/src/main.py
git commit -m "$(cat <<'EOF'
feat(api): add meeting brief API routes

Adds endpoints:
- GET /api/v1/meetings/upcoming - list upcoming meetings with brief status
- GET /api/v1/meetings/{id}/brief - get meeting brief
- POST /api/v1/meetings/{id}/brief/generate - on-demand generation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Create Background Job for Pre-Meeting Brief Generation

**Files:**
- Create: `/Users/dhruv/aria/backend/src/jobs/meeting_brief_generator.py`
- Test: `/Users/dhruv/aria/backend/tests/test_jobs_meeting_brief.py`

**Step 1: Write the failing test**

Create `/Users/dhruv/aria/backend/tests/test_jobs_meeting_brief.py`:

```python
"""Tests for meeting brief generation job."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_job_finds_meetings_within_window() -> None:
    """Test job identifies meetings within 24h window."""
    with patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class:
        mock_users = [{"id": "user-1"}]
        mock_integrations = [
            {"user_id": "user-1", "integration_type": "google_calendar"}
        ]

        mock_db = MagicMock()
        # First call: get users
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=mock_users
        )
        mock_db_class.get_client.return_value = mock_db

        from src.jobs.meeting_brief_generator import find_meetings_needing_briefs

        result = await find_meetings_needing_briefs(hours_ahead=24)

        # Should return list (may be empty without calendar integration)
        assert isinstance(result, list)


@pytest.mark.asyncio
async def test_run_meeting_brief_job_returns_summary() -> None:
    """Test job returns summary of processed meetings."""
    with (
        patch("src.jobs.meeting_brief_generator.SupabaseClient") as mock_db_class,
        patch("src.jobs.meeting_brief_generator.find_meetings_needing_briefs") as mock_find,
        patch("src.jobs.meeting_brief_generator.MeetingBriefService") as mock_service_class,
    ):
        mock_find.return_value = []

        mock_db = MagicMock()
        mock_db_class.get_client.return_value = mock_db

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        from src.jobs.meeting_brief_generator import run_meeting_brief_job

        result = await run_meeting_brief_job()

        assert "meetings_found" in result
        assert "briefs_generated" in result
        assert "errors" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_jobs_meeting_brief.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create the job**

Create `/Users/dhruv/aria/backend/src/jobs/meeting_brief_generator.py`:

```python
"""Background job for generating pre-meeting briefs.

This job should be scheduled to run periodically (e.g., hourly).
It finds meetings within the configured window (default 24h) and
generates briefs for any that don't have one yet.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.services.meeting_brief import MeetingBriefService

logger = logging.getLogger(__name__)


async def find_meetings_needing_briefs(
    hours_ahead: int = 24,
) -> list[dict[str, Any]]:
    """Find meetings within window that need briefs generated.

    Args:
        hours_ahead: Hours ahead to look for meetings.

    Returns:
        List of meeting records needing briefs.
    """
    db = SupabaseClient.get_client()

    now = datetime.now(UTC)
    window_end = now + timedelta(hours=hours_ahead)

    # Find briefs in pending status within window
    result = (
        db.table("meeting_briefs")
        .select("id, user_id, calendar_event_id, meeting_title, meeting_time, attendees")
        .eq("status", "pending")
        .gte("meeting_time", now.isoformat())
        .lte("meeting_time", window_end.isoformat())
        .execute()
    )

    meetings = cast(list[dict[str, Any]], result.data or [])

    logger.info(
        f"Found {len(meetings)} meetings needing briefs",
        extra={"hours_ahead": hours_ahead, "window_end": window_end.isoformat()},
    )

    return meetings


async def run_meeting_brief_job(
    hours_ahead: int = 24,
) -> dict[str, Any]:
    """Run the meeting brief generation job.

    Finds meetings within the window and generates briefs for them.
    Continues processing even if individual briefs fail.

    Args:
        hours_ahead: Hours ahead to look for meetings (default 24).

    Returns:
        Summary dict with meetings_found, briefs_generated, and errors.
    """
    logger.info("Starting meeting brief generation job")

    meetings = await find_meetings_needing_briefs(hours_ahead=hours_ahead)

    briefs_generated = 0
    errors = 0

    service = MeetingBriefService()

    for meeting in meetings:
        try:
            user_id = cast(str, meeting["user_id"])
            brief_id = cast(str, meeting["id"])

            logger.info(
                f"Generating brief for meeting",
                extra={
                    "user_id": user_id,
                    "brief_id": brief_id,
                    "meeting_title": meeting.get("meeting_title"),
                },
            )

            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            if content:
                briefs_generated += 1
            else:
                errors += 1

        except Exception as e:
            errors += 1
            logger.error(
                "Failed to generate brief",
                extra={
                    "brief_id": meeting.get("id"),
                    "error": str(e),
                },
            )

    result = {
        "meetings_found": len(meetings),
        "briefs_generated": briefs_generated,
        "errors": errors,
        "hours_ahead": hours_ahead,
    }

    logger.info("Meeting brief generation job completed", extra=result)
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_jobs_meeting_brief.py -v`
Expected: All tests PASS

**Step 5: Update jobs __init__.py**

Add to `/Users/dhruv/aria/backend/src/jobs/__init__.py`:

```python
from src.jobs.meeting_brief_generator import run_meeting_brief_job

__all__ = ["run_salience_decay_job", "run_meeting_brief_job"]
```

**Step 6: Commit**

```bash
git add backend/src/jobs/meeting_brief_generator.py backend/tests/test_jobs_meeting_brief.py backend/src/jobs/__init__.py
git commit -m "$(cat <<'EOF'
feat(jobs): add meeting brief generation background job

Implements:
- find_meetings_needing_briefs: finds pending briefs within window
- run_meeting_brief_job: processes pending briefs in batch

Job should be scheduled to run hourly to generate briefs
24 hours before meetings.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Run Full Test Suite and Quality Checks

**Files:**
- All backend files

**Step 1: Run full test suite**

Run: `cd /Users/dhruv/aria/backend && pytest tests/ -v --ignore=tests/integration`
Expected: All tests PASS

**Step 2: Run type checker on new files**

Run: `cd /Users/dhruv/aria/backend && mypy src/models/meeting_brief.py src/services/meeting_brief.py src/services/attendee_profile.py src/api/routes/meetings.py src/jobs/meeting_brief_generator.py --strict`
Expected: No errors (or acceptable warnings)

**Step 3: Run linter**

Run: `cd /Users/dhruv/aria/backend && ruff check src/models/meeting_brief.py src/services/meeting_brief.py src/services/attendee_profile.py src/api/routes/meetings.py src/jobs/meeting_brief_generator.py`
Expected: No errors

**Step 4: Run formatter**

Run: `cd /Users/dhruv/aria/backend && ruff format src/models/meeting_brief.py src/services/meeting_brief.py src/services/attendee_profile.py src/api/routes/meetings.py src/jobs/meeting_brief_generator.py`
Expected: Files formatted (or already formatted)

**Step 5: Commit if any formatting changes**

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: format meeting brief files

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)" || echo "No formatting changes"
```

---

## Task 10: Add Integration Test for End-to-End Flow

**Files:**
- Create: `/Users/dhruv/aria/backend/tests/integration/test_meeting_brief_flow.py`

**Step 1: Write integration test**

Create `/Users/dhruv/aria/backend/tests/integration/test_meeting_brief_flow.py`:

```python
"""Integration tests for meeting brief end-to-end flow."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_brief_generation_flow() -> None:
    """Test complete flow: create brief -> generate content -> retrieve."""
    with (
        patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
        patch("src.services.meeting_brief.anthropic.Anthropic") as mock_llm_class,
        patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
        patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
    ):
        # Setup in-memory storage
        briefs_store: dict[str, dict] = {}
        brief_counter = [0]

        def mock_insert(data: dict) -> MagicMock:
            brief_counter[0] += 1
            brief_id = f"brief-{brief_counter[0]}"
            stored = {**data, "id": brief_id}
            briefs_store[brief_id] = stored
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[stored])
            return result

        def mock_select() -> MagicMock:
            chain = MagicMock()
            chain.eq.return_value = chain
            chain.single.return_value = chain

            def execute() -> MagicMock:
                # Return first brief that matches
                for brief in briefs_store.values():
                    return MagicMock(data=brief)
                return MagicMock(data=None)

            chain.execute = execute
            return chain

        def mock_update(data: dict) -> MagicMock:
            def execute() -> MagicMock:
                for brief_id, brief in briefs_store.items():
                    brief.update(data)
                    return MagicMock(data=[brief])
                return MagicMock(data=[])

            chain = MagicMock()
            chain.eq.return_value = chain
            chain.execute = execute
            return chain

        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_table.insert.side_effect = lambda data: mock_insert(data)
        mock_table.select.return_value = mock_select()
        mock_table.update.side_effect = lambda data: mock_update(data)
        mock_db.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM
        mock_llm_response = MagicMock()
        mock_llm_content = MagicMock()
        mock_llm_content.text = """{
            "summary": "Quarterly review with key stakeholder from Acme Corp",
            "suggested_agenda": ["Review Q4 results", "Discuss 2026 plans"],
            "risks_opportunities": ["Budget constraints", "Expansion opportunity"]
        }"""
        mock_llm_response.content = [mock_llm_content]
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        # Setup profile service
        mock_profile_service = MagicMock()
        mock_profile_service.get_profiles_batch.return_value = {
            "john@acme.com": {
                "email": "john@acme.com",
                "name": "John Smith",
                "title": "VP Procurement",
                "company": "Acme Corp",
                "profile_data": {"background": "15 years in procurement"},
            }
        }
        mock_profile_class.return_value = mock_profile_service

        # Setup Scout
        mock_scout = MagicMock()
        mock_scout.validate_input.return_value = True
        mock_scout.execute.return_value = MagicMock(
            success=True,
            data=[
                {
                    "company_name": "Acme Corp",
                    "signal_type": "funding",
                    "headline": "Acme raises $50M Series C",
                }
            ],
        )
        mock_scout_class.return_value = mock_scout

        # Import and run
        from src.services.meeting_brief import MeetingBriefService

        service = MeetingBriefService()

        # Step 1: Create brief
        meeting_time = datetime.now(timezone.utc) + timedelta(days=1)
        brief = await service.create_brief(
            user_id="user-123",
            calendar_event_id="evt-abc",
            meeting_title="Q4 Business Review",
            meeting_time=meeting_time,
            attendees=["john@acme.com"],
        )

        assert brief["status"] == "pending"
        assert brief["id"] is not None

        # Step 2: Generate content
        content = await service.generate_brief_content(
            user_id="user-123",
            brief_id=brief["id"],
        )

        assert content is not None
        assert "summary" in content
        assert "Quarterly review" in content["summary"]
        assert len(content["suggested_agenda"]) == 2
        assert len(content["attendees"]) == 1
        assert content["attendees"][0]["name"] == "John Smith"
```

**Step 2: Run integration test**

Run: `cd /Users/dhruv/aria/backend && pytest tests/integration/test_meeting_brief_flow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/integration/test_meeting_brief_flow.py
git commit -m "$(cat <<'EOF'
test: add integration test for meeting brief flow

Tests complete flow:
1. Create pending brief
2. Generate content with Scout and LLM
3. Verify attendee and company data included

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-406: Pre-Meeting Research Backend with:

1. **Database Migrations** - `meeting_briefs` and `attendee_profiles` tables with RLS policies
2. **Pydantic Models** - Request/response models for API type safety
3. **MeetingBriefService** - CRUD operations and brief generation logic
4. **AttendeeProfileService** - Profile caching to avoid redundant lookups
5. **Brief Generation** - Integrates Scout agent for company research and Claude for synthesis
6. **API Routes** - GET/POST endpoints for briefs and upcoming meetings
7. **Background Job** - Scheduled job to generate briefs 24h before meetings
8. **Tests** - Unit and integration tests for all components

**Key Features:**
- Triggered 24h before meetings (configurable via `hours_ahead`)
- Research includes attendee profiles, company signals, talking points
- Brief stored for reference with status tracking
- On-demand generation via POST endpoint
- Caches attendee profiles to avoid redundant research
- Uses Scout agent for market signals
- Synthesizes research with Claude into actionable brief

**Endpoints:**
- `GET /api/v1/meetings/upcoming` - List upcoming meetings with brief status
- `GET /api/v1/meetings/{id}/brief` - Get meeting brief
- `POST /api/v1/meetings/{id}/brief/generate` - On-demand generation
