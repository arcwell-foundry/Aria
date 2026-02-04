# US-414: Settings - Preferences Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a premium Settings - Preferences page where users configure briefing time, meeting brief lead time, notifications, default tone, and competitors to track.

**Architecture:** Backend provides GET/PUT endpoints for user_preferences table with RLS policies. Frontend renders Apple-inspired settings UI with auto-save via React Query mutations.

**Tech Stack:** FastAPI, Pydantic, Supabase PostgreSQL, React, TypeScript, Tailwind CSS, Framer Motion, React Query

---

## Task 1: Create Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260203000003_create_user_preferences.sql`

**Step 1: Write the migration file**

```sql
-- User preferences table for US-414: Settings - Preferences
-- Stores user notification preferences, briefing settings, and tracked competitors
-- One record per user with sensible defaults

-- Main user_preferences table
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    briefing_time TIME DEFAULT '08:00' NOT NULL,
    meeting_brief_lead_hours INT DEFAULT 24 NOT NULL,
    notification_email BOOLEAN DEFAULT true NOT NULL,
    notification_in_app BOOLEAN DEFAULT true NOT NULL,
    default_tone TEXT DEFAULT 'friendly' NOT NULL,
    tracked_competitors TEXT[] DEFAULT '{}' NOT NULL,
    timezone TEXT DEFAULT 'UTC' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id),
    CONSTRAINT valid_tone CHECK (default_tone IN ('formal', 'friendly', 'urgent')),
    CONSTRAINT valid_lead_hours CHECK (meeting_brief_lead_hours IN (2, 6, 12, 24))
);

-- Add table comment
COMMENT ON TABLE user_preferences IS 'Stores user preferences for briefings, notifications, and ARIA behavior. One record per user with auto-created defaults.';

-- Create indexes for efficient querying
CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);

-- Enable Row Level Security
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation (multi-tenant)
CREATE POLICY "Users can view their own preferences" ON user_preferences
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update their own preferences" ON user_preferences
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own preferences" ON user_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own preferences" ON user_preferences
    FOR DELETE USING (auth.uid() = user_id);

-- Service role bypass policy (for backend operations)
CREATE POLICY "Service role can manage user_preferences" ON user_preferences
    FOR ALL USING (auth.role() = 'service_role');

-- Updated_at trigger (reuses existing function from 001_initial_schema.sql)
CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**Step 2: Verify the migration syntax**

Run: `cd backend && cat supabase/migrations/20260203000003_create_user_preferences.sql`
Expected: Migration file content displayed without syntax errors

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260203000003_create_user_preferences.sql
git commit -m "feat(db): add user_preferences table migration for US-414"
```

---

## Task 2: Create Backend Pydantic Models

**Files:**
- Create: `backend/src/models/preferences.py`

**Step 1: Write the failing test**

Create: `backend/tests/test_preferences_models.py`

```python
"""Tests for preferences Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models.preferences import (
    DefaultTone,
    MeetingBriefLeadHours,
    PreferenceCreate,
    PreferenceResponse,
    PreferenceUpdate,
)


class TestDefaultToneEnum:
    """Tests for DefaultTone enum."""

    def test_valid_tones(self) -> None:
        """Test that all valid tones are accepted."""
        assert DefaultTone.FORMAL.value == "formal"
        assert DefaultTone.FRIENDLY.value == "friendly"
        assert DefaultTone.URGENT.value == "urgent"


class TestMeetingBriefLeadHoursEnum:
    """Tests for MeetingBriefLeadHours enum."""

    def test_valid_lead_hours(self) -> None:
        """Test that all valid lead hours are accepted."""
        assert MeetingBriefLeadHours.TWO_HOURS.value == 2
        assert MeetingBriefLeadHours.SIX_HOURS.value == 6
        assert MeetingBriefLeadHours.TWELVE_HOURS.value == 12
        assert MeetingBriefLeadHours.TWENTY_FOUR_HOURS.value == 24


class TestPreferenceUpdate:
    """Tests for PreferenceUpdate model."""

    def test_all_fields_optional(self) -> None:
        """Test that all fields are optional for partial updates."""
        update = PreferenceUpdate()
        assert update.briefing_time is None
        assert update.meeting_brief_lead_hours is None
        assert update.notification_email is None
        assert update.notification_in_app is None
        assert update.default_tone is None
        assert update.tracked_competitors is None
        assert update.timezone is None

    def test_partial_update(self) -> None:
        """Test partial update with only some fields."""
        update = PreferenceUpdate(
            notification_email=False,
            default_tone=DefaultTone.FORMAL,
        )
        assert update.notification_email is False
        assert update.default_tone == DefaultTone.FORMAL
        assert update.briefing_time is None

    def test_valid_briefing_time_formats(self) -> None:
        """Test valid time string formats."""
        update = PreferenceUpdate(briefing_time="09:30")
        assert update.briefing_time == "09:30"

    def test_invalid_briefing_time_rejected(self) -> None:
        """Test that invalid time formats are rejected."""
        with pytest.raises(ValidationError):
            PreferenceUpdate(briefing_time="25:00")  # Invalid hour

    def test_tracked_competitors_list(self) -> None:
        """Test tracked competitors as list of strings."""
        update = PreferenceUpdate(tracked_competitors=["Competitor A", "Competitor B"])
        assert update.tracked_competitors == ["Competitor A", "Competitor B"]


class TestPreferenceResponse:
    """Tests for PreferenceResponse model."""

    def test_full_response(self) -> None:
        """Test complete response with all fields."""
        response = PreferenceResponse(
            id="550e8400-e29b-41d4-a716-446655440000",
            user_id="550e8400-e29b-41d4-a716-446655440001",
            briefing_time="08:00",
            meeting_brief_lead_hours=24,
            notification_email=True,
            notification_in_app=True,
            default_tone="friendly",
            tracked_competitors=["Acme Corp"],
            timezone="America/New_York",
            created_at="2026-02-03T12:00:00Z",
            updated_at="2026-02-03T12:00:00Z",
        )
        assert response.id == "550e8400-e29b-41d4-a716-446655440000"
        assert response.default_tone == "friendly"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_preferences_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.models.preferences'"

**Step 3: Write the model implementation**

Create: `backend/src/models/preferences.py`

```python
"""Pydantic models for user preferences.

This module defines request/response models for the preferences API endpoints.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DefaultTone(str, Enum):
    """Communication tone options."""

    FORMAL = "formal"
    FRIENDLY = "friendly"
    URGENT = "urgent"


class MeetingBriefLeadHours(int, Enum):
    """Meeting brief lead time options in hours."""

    TWO_HOURS = 2
    SIX_HOURS = 6
    TWELVE_HOURS = 12
    TWENTY_FOUR_HOURS = 24


class PreferenceCreate(BaseModel):
    """Request model for creating preferences (used internally for defaults)."""

    user_id: str = Field(..., description="User ID")
    briefing_time: str = Field(default="08:00", description="Daily briefing time (HH:MM)")
    meeting_brief_lead_hours: int = Field(
        default=24, description="Hours before meeting to generate brief"
    )
    notification_email: bool = Field(default=True, description="Enable email notifications")
    notification_in_app: bool = Field(default=True, description="Enable in-app notifications")
    default_tone: DefaultTone = Field(
        default=DefaultTone.FRIENDLY, description="Default communication tone"
    )
    tracked_competitors: list[str] = Field(
        default_factory=list, description="List of competitors to track"
    )
    timezone: str = Field(default="UTC", description="User timezone")


class PreferenceUpdate(BaseModel):
    """Request model for updating preferences.

    All fields are optional for partial updates.
    """

    briefing_time: str | None = Field(None, description="Daily briefing time (HH:MM)")
    meeting_brief_lead_hours: MeetingBriefLeadHours | None = Field(
        None, description="Hours before meeting to generate brief"
    )
    notification_email: bool | None = Field(None, description="Enable email notifications")
    notification_in_app: bool | None = Field(None, description="Enable in-app notifications")
    default_tone: DefaultTone | None = Field(None, description="Default communication tone")
    tracked_competitors: list[str] | None = Field(
        None, description="List of competitors to track"
    )
    timezone: str | None = Field(None, description="User timezone")

    @field_validator("briefing_time")
    @classmethod
    def validate_briefing_time(cls, v: str | None) -> str | None:
        """Validate briefing time is a valid HH:MM format."""
        if v is None:
            return v
        try:
            hours, minutes = v.split(":")
            h = int(hours)
            m = int(minutes)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError("Invalid time")
            return f"{h:02d}:{m:02d}"
        except (ValueError, AttributeError) as e:
            raise ValueError("Briefing time must be in HH:MM format (00:00-23:59)") from e

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "briefing_time": "09:00",
                "meeting_brief_lead_hours": 12,
                "notification_email": True,
                "notification_in_app": True,
                "default_tone": "friendly",
                "tracked_competitors": ["Competitor Inc", "Acme Corp"],
                "timezone": "America/New_York",
            }
        }


class PreferenceResponse(BaseModel):
    """Response model for preference data."""

    id: str = Field(..., description="Preference record ID")
    user_id: str = Field(..., description="User ID")
    briefing_time: str = Field(..., description="Daily briefing time (HH:MM)")
    meeting_brief_lead_hours: int = Field(
        ..., description="Hours before meeting to generate brief"
    )
    notification_email: bool = Field(..., description="Email notifications enabled")
    notification_in_app: bool = Field(..., description="In-app notifications enabled")
    default_tone: str = Field(..., description="Default communication tone")
    tracked_competitors: list[str] = Field(..., description="List of tracked competitors")
    timezone: str = Field(..., description="User timezone")
    created_at: str = Field(..., description="Record creation timestamp")
    updated_at: str = Field(..., description="Record last update timestamp")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "briefing_time": "08:00",
                "meeting_brief_lead_hours": 24,
                "notification_email": True,
                "notification_in_app": True,
                "default_tone": "friendly",
                "tracked_competitors": ["Acme Corp", "TechRival"],
                "timezone": "UTC",
                "created_at": "2026-02-03T12:00:00Z",
                "updated_at": "2026-02-03T12:00:00Z",
            }
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_preferences_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/preferences.py backend/tests/test_preferences_models.py
git commit -m "feat(models): add Pydantic models for user preferences"
```

---

## Task 3: Create Backend Preference Service

**Files:**
- Create: `backend/src/services/preference_service.py`
- Test: `backend/tests/test_preference_service.py`

**Step 1: Write the failing test**

Create: `backend/tests/test_preference_service.py`

```python
"""Tests for PreferenceService."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.preferences import DefaultTone, MeetingBriefLeadHours, PreferenceUpdate
from src.services.preference_service import PreferenceService


class TestPreferenceService:
    """Tests for PreferenceService."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = PreferenceService()
        self.test_user_id = "test-user-123"

    @patch.object(PreferenceService, "_db", new_callable=MagicMock)
    @pytest.mark.asyncio
    async def test_get_preferences_existing_user(self, mock_db: MagicMock) -> None:
        """Test getting preferences for user with existing preferences."""
        mock_response = MagicMock()
        mock_response.data = {
            "id": "pref-123",
            "user_id": self.test_user_id,
            "briefing_time": "09:00",
            "meeting_brief_lead_hours": 12,
            "notification_email": True,
            "notification_in_app": False,
            "default_tone": "formal",
            "tracked_competitors": ["Competitor A"],
            "timezone": "America/New_York",
            "created_at": "2026-02-03T12:00:00Z",
            "updated_at": "2026-02-03T12:00:00Z",
        }
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            mock_response
        )

        result = await self.service.get_preferences(self.test_user_id)

        assert result["id"] == "pref-123"
        assert result["briefing_time"] == "09:00"
        assert result["notification_in_app"] is False

    @patch.object(PreferenceService, "_db", new_callable=MagicMock)
    @pytest.mark.asyncio
    async def test_update_preferences(self, mock_db: MagicMock) -> None:
        """Test updating preferences."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "pref-123",
                "user_id": self.test_user_id,
                "briefing_time": "10:00",
                "meeting_brief_lead_hours": 6,
                "notification_email": False,
                "notification_in_app": True,
                "default_tone": "urgent",
                "tracked_competitors": [],
                "timezone": "UTC",
                "created_at": "2026-02-03T12:00:00Z",
                "updated_at": "2026-02-03T13:00:00Z",
            }
        ]
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        update_data = PreferenceUpdate(
            briefing_time="10:00",
            meeting_brief_lead_hours=MeetingBriefLeadHours.SIX_HOURS,
            notification_email=False,
            default_tone=DefaultTone.URGENT,
        )

        result = await self.service.update_preferences(self.test_user_id, update_data)

        assert result["briefing_time"] == "10:00"
        assert result["meeting_brief_lead_hours"] == 6
        assert result["notification_email"] is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_preference_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.preference_service'"

**Step 3: Write the service implementation**

Create: `backend/src/services/preference_service.py`

```python
"""Preference service for ARIA.

This module handles user preference management including getting, creating,
and updating user preferences.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.preferences import PreferenceUpdate

logger = logging.getLogger(__name__)


class PreferenceService:
    """Service for user preference management."""

    def __init__(self) -> None:
        """Initialize preference service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user preferences.

        If preferences don't exist, creates default preferences for the user.

        Args:
            user_id: The user's ID.

        Returns:
            User preferences dict.
        """
        logger.info("Fetching preferences", extra={"user_id": user_id})

        try:
            result = (
                self._db.table("user_preferences")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if result.data is None:
                logger.info(
                    "No preferences found, creating defaults",
                    extra={"user_id": user_id},
                )
                return await self._create_default_preferences(user_id)

            return cast(dict[str, Any], result.data)

        except Exception as e:
            # Check if it's a "no rows" error (PGRST116)
            if "PGRST116" in str(e):
                logger.info(
                    "No preferences found, creating defaults",
                    extra={"user_id": user_id},
                )
                return await self._create_default_preferences(user_id)
            raise

    async def update_preferences(
        self, user_id: str, data: PreferenceUpdate
    ) -> dict[str, Any]:
        """Update user preferences.

        Creates preferences with defaults if they don't exist, then applies updates.

        Args:
            user_id: The user's ID.
            data: Preference update data.

        Returns:
            Updated preferences dict.

        Raises:
            ValueError: If update fails.
        """
        logger.info("Updating preferences", extra={"user_id": user_id})

        # Ensure preferences exist first
        await self.get_preferences(user_id)

        # Build update data, excluding None values
        update_data: dict[str, Any] = {}
        for field, value in data.model_dump(exclude_none=True).items():
            if hasattr(value, "value"):
                # Handle enums
                update_data[field] = value.value
            else:
                update_data[field] = value

        if not update_data:
            logger.info("No fields to update", extra={"user_id": user_id})
            return await self.get_preferences(user_id)

        update_data["updated_at"] = datetime.now(UTC).isoformat()

        result = (
            self._db.table("user_preferences")
            .update(update_data)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            logger.warning("Preferences update failed", extra={"user_id": user_id})
            raise ValueError("Failed to update preferences")

        logger.info("Preferences updated", extra={"user_id": user_id})
        return cast(dict[str, Any], result.data[0])

    async def _create_default_preferences(self, user_id: str) -> dict[str, Any]:
        """Create default preferences for a new user.

        Args:
            user_id: The user's ID.

        Returns:
            Created preferences dict with defaults.
        """
        default_data = {
            "user_id": user_id,
            "briefing_time": "08:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
        }

        result = self._db.table("user_preferences").insert(default_data).execute()

        logger.info("Created default preferences", extra={"user_id": user_id})
        return cast(dict[str, Any], result.data[0])
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_preference_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/preference_service.py backend/tests/test_preference_service.py
git commit -m "feat(service): add PreferenceService for user preferences"
```

---

## Task 4: Create Backend API Routes

**Files:**
- Create: `backend/src/api/routes/preferences.py`
- Modify: `backend/src/main.py` (add router import and include)
- Test: `backend/tests/test_preferences_routes.py`

**Step 1: Write the failing test**

Create: `backend/tests/test_preferences_routes.py`

```python
"""Integration tests for preferences API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> MagicMock:
    """Create mock user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def mock_preferences() -> dict:
    """Create mock preferences data."""
    return {
        "id": "pref-123",
        "user_id": "test-user-123",
        "briefing_time": "08:00",
        "meeting_brief_lead_hours": 24,
        "notification_email": True,
        "notification_in_app": True,
        "default_tone": "friendly",
        "tracked_competitors": ["Acme Corp"],
        "timezone": "UTC",
        "created_at": "2026-02-03T12:00:00Z",
        "updated_at": "2026-02-03T12:00:00Z",
    }


class TestGetPreferences:
    """Tests for GET /api/v1/settings/preferences."""

    def test_get_preferences_success(
        self,
        client: TestClient,
        mock_user: MagicMock,
        mock_preferences: dict,
    ) -> None:
        """Test successful preferences retrieval."""
        with (
            patch("src.api.routes.preferences.get_current_user", return_value=mock_user),
            patch(
                "src.api.routes.preferences.PreferenceService"
            ) as mock_service_class,
        ):
            mock_service = mock_service_class.return_value
            mock_service.get_preferences = AsyncMock(return_value=mock_preferences)

            response = client.get(
                "/api/v1/settings/preferences",
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["briefing_time"] == "08:00"
            assert data["default_tone"] == "friendly"

    def test_get_preferences_unauthenticated(self, client: TestClient) -> None:
        """Test preferences retrieval without auth."""
        response = client.get("/api/v1/settings/preferences")
        assert response.status_code == 401


class TestUpdatePreferences:
    """Tests for PUT /api/v1/settings/preferences."""

    def test_update_preferences_success(
        self,
        client: TestClient,
        mock_user: MagicMock,
        mock_preferences: dict,
    ) -> None:
        """Test successful preferences update."""
        updated_prefs = {**mock_preferences, "briefing_time": "09:30", "default_tone": "formal"}

        with (
            patch("src.api.routes.preferences.get_current_user", return_value=mock_user),
            patch(
                "src.api.routes.preferences.PreferenceService"
            ) as mock_service_class,
        ):
            mock_service = mock_service_class.return_value
            mock_service.update_preferences = AsyncMock(return_value=updated_prefs)

            response = client.put(
                "/api/v1/settings/preferences",
                json={"briefing_time": "09:30", "default_tone": "formal"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["briefing_time"] == "09:30"
            assert data["default_tone"] == "formal"

    def test_update_preferences_invalid_tone(
        self,
        client: TestClient,
        mock_user: MagicMock,
    ) -> None:
        """Test preferences update with invalid tone."""
        with patch("src.api.routes.preferences.get_current_user", return_value=mock_user):
            response = client.put(
                "/api/v1/settings/preferences",
                json={"default_tone": "invalid_tone"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 422  # Validation error

    def test_update_preferences_invalid_time(
        self,
        client: TestClient,
        mock_user: MagicMock,
    ) -> None:
        """Test preferences update with invalid time."""
        with patch("src.api.routes.preferences.get_current_user", return_value=mock_user):
            response = client.put(
                "/api/v1/settings/preferences",
                json={"briefing_time": "25:00"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 422  # Validation error
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_preferences_routes.py -v`
Expected: FAIL with import errors or 404 (route not found)

**Step 3: Write the routes implementation**

Create: `backend/src/api/routes/preferences.py`

```python
"""User preferences API routes for ARIA.

This module provides endpoints for:
- Getting user preferences
- Updating user preferences
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import CurrentUser, get_current_user
from src.models.preferences import PreferenceResponse, PreferenceUpdate
from src.services.preference_service import PreferenceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/preferences", tags=["settings"])


def _get_service() -> PreferenceService:
    """Get preference service instance."""
    return PreferenceService()


@router.get("", response_model=PreferenceResponse)
async def get_preferences(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current user's preferences.

    Returns user preferences, creating defaults if none exist.
    """
    service = _get_service()

    try:
        preferences = await service.get_preferences(current_user.id)

        logger.info(
            "Preferences retrieved via API",
            extra={"user_id": current_user.id},
        )

        return preferences

    except Exception as e:
        logger.exception("Error fetching preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch preferences",
        ) from e


@router.put("", response_model=PreferenceResponse)
async def update_preferences(
    data: PreferenceUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's preferences.

    Accepts partial updates - only provided fields are modified.
    """
    service = _get_service()

    try:
        preferences = await service.update_preferences(current_user.id, data)

        logger.info(
            "Preferences updated via API",
            extra={"user_id": current_user.id},
        )

        return preferences

    except ValueError as e:
        logger.warning(
            "Preferences update failed",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except Exception as e:
        logger.exception("Error updating preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        ) from e
```

**Step 4: Register the router in main.py**

Modify: `backend/src/main.py`

Add import (after existing route imports around line 25):
```python
from src.api.routes import (
    auth,
    battle_cards,
    briefings,
    chat,
    cognitive_load,
    debriefs,
    drafts,
    goals,
    integrations,
    meetings,
    memory,
    preferences,  # Add this line
    signals,
)
```

Add router include (after existing router includes around line 99):
```python
app.include_router(preferences.router, prefix="/api/v1")
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_preferences_routes.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/preferences.py backend/src/main.py backend/tests/test_preferences_routes.py
git commit -m "feat(api): add preferences API endpoints GET/PUT /settings/preferences"
```

---

## Task 5: Create Frontend API Client

**Files:**
- Create: `frontend/src/api/preferences.ts`

**Step 1: Write the API client**

Create: `frontend/src/api/preferences.ts`

```typescript
import { apiClient } from "./client";

// Enums matching backend
export type DefaultTone = "formal" | "friendly" | "urgent";
export type MeetingBriefLeadHours = 2 | 6 | 12 | 24;

// Response type
export interface UserPreferences {
  id: string;
  user_id: string;
  briefing_time: string;
  meeting_brief_lead_hours: MeetingBriefLeadHours;
  notification_email: boolean;
  notification_in_app: boolean;
  default_tone: DefaultTone;
  tracked_competitors: string[];
  timezone: string;
  created_at: string;
  updated_at: string;
}

// Request type for updates
export interface UpdatePreferencesRequest {
  briefing_time?: string;
  meeting_brief_lead_hours?: MeetingBriefLeadHours;
  notification_email?: boolean;
  notification_in_app?: boolean;
  default_tone?: DefaultTone;
  tracked_competitors?: string[];
  timezone?: string;
}

// API functions
export async function getPreferences(): Promise<UserPreferences> {
  const response = await apiClient.get<UserPreferences>("/settings/preferences");
  return response.data;
}

export async function updatePreferences(
  data: UpdatePreferencesRequest
): Promise<UserPreferences> {
  const response = await apiClient.put<UserPreferences>("/settings/preferences", data);
  return response.data;
}

// Convenience export
export const preferencesApi = {
  getPreferences,
  updatePreferences,
};
```

**Step 2: Verify the file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors for preferences.ts

**Step 3: Commit**

```bash
git add frontend/src/api/preferences.ts
git commit -m "feat(api): add preferences API client functions"
```

---

## Task 6: Create Frontend React Query Hooks

**Files:**
- Create: `frontend/src/hooks/usePreferences.ts`

**Step 1: Write the hooks**

Create: `frontend/src/hooks/usePreferences.ts`

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPreferences,
  updatePreferences,
  type UpdatePreferencesRequest,
  type UserPreferences,
} from "@/api/preferences";

// Query keys
export const preferenceKeys = {
  all: ["preferences"] as const,
  detail: () => [...preferenceKeys.all, "detail"] as const,
};

// Get preferences query
export function usePreferences() {
  return useQuery({
    queryKey: preferenceKeys.detail(),
    queryFn: () => getPreferences(),
  });
}

// Update preferences mutation with optimistic updates
export function useUpdatePreferences() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdatePreferencesRequest) => updatePreferences(data),
    onMutate: async (newData) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: preferenceKeys.detail() });

      // Snapshot the previous value
      const previousPreferences = queryClient.getQueryData<UserPreferences>(
        preferenceKeys.detail()
      );

      // Optimistically update to the new value
      if (previousPreferences) {
        queryClient.setQueryData<UserPreferences>(preferenceKeys.detail(), {
          ...previousPreferences,
          ...newData,
          updated_at: new Date().toISOString(),
        });
      }

      // Return a context object with the snapshotted value
      return { previousPreferences };
    },
    onError: (_err, _newData, context) => {
      // Rollback to the previous value on error
      if (context?.previousPreferences) {
        queryClient.setQueryData(
          preferenceKeys.detail(),
          context.previousPreferences
        );
      }
    },
    onSettled: () => {
      // Always refetch after error or success
      queryClient.invalidateQueries({ queryKey: preferenceKeys.detail() });
    },
  });
}
```

**Step 2: Verify the file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/usePreferences.ts
git commit -m "feat(hooks): add usePreferences React Query hooks with optimistic updates"
```

---

## Task 7: Create PreferencesSettings Page Component

**Files:**
- Create: `frontend/src/pages/PreferencesSettings.tsx`

**Step 1: Write the page component**

Create: `frontend/src/pages/PreferencesSettings.tsx`

```typescript
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardLayout } from "@/components/DashboardLayout";
import { usePreferences, useUpdatePreferences } from "@/hooks/usePreferences";
import type { DefaultTone, MeetingBriefLeadHours } from "@/api/preferences";

// Lead hours options
const LEAD_HOURS_OPTIONS: { value: MeetingBriefLeadHours; label: string }[] = [
  { value: 24, label: "24 hours" },
  { value: 12, label: "12 hours" },
  { value: 6, label: "6 hours" },
  { value: 2, label: "2 hours" },
];

// Tone options
const TONE_OPTIONS: { value: DefaultTone; label: string; description: string }[] = [
  { value: "formal", label: "Formal", description: "Professional and business-like" },
  { value: "friendly", label: "Friendly", description: "Warm and approachable" },
  { value: "urgent", label: "Urgent", description: "Direct and action-oriented" },
];

// Success toast component
function SuccessToast({ show, onHide }: { show: boolean; onHide: () => void }) {
  useEffect(() => {
    if (show) {
      const timer = setTimeout(onHide, 2000);
      return () => clearTimeout(timer);
    }
  }, [show, onHide]);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 50 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className="fixed bottom-6 right-6 z-50"
        >
          <div className="flex items-center gap-2 px-4 py-3 bg-emerald-500/90 backdrop-blur-sm text-white rounded-xl shadow-lg shadow-emerald-500/25">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-sm font-medium">Preferences saved</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Loading skeleton
function PreferencesSettingsSkeleton() {
  return (
    <div className="space-y-8">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
          <div className="h-6 bg-slate-700 rounded w-1/4 mb-4 animate-pulse" />
          <div className="space-y-3">
            <div className="h-4 bg-slate-700 rounded w-2/3 animate-pulse" />
            <div className="h-10 bg-slate-700 rounded w-full animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Error banner
function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl"
    >
      <div className="flex items-start gap-3">
        <svg className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div className="flex-1">
          <p className="text-sm text-red-300">{message}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1 text-xs font-medium bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    </motion.div>
  );
}

// Section wrapper component
function SettingsSection({
  title,
  description,
  children,
  delay = 0,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-2xl p-6"
    >
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {description && <p className="text-sm text-slate-400 mt-1">{description}</p>}
      </div>
      {children}
    </motion.div>
  );
}

// Toggle switch component (Apple-style)
function ToggleSwitch({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`
        relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500
        ${enabled ? "bg-primary-600" : "bg-slate-600"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <span
        className={`
          pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-lg ring-0
          transition duration-200 ease-in-out
          ${enabled ? "translate-x-5" : "translate-x-0"}
        `}
      />
    </button>
  );
}

// Segmented control component
function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  disabled = false,
}: {
  value: T;
  options: { value: T; label: string; description?: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => !disabled && onChange(option.value)}
          disabled={disabled}
          className={`
            relative px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200
            ${
              value === option.value
                ? "bg-primary-600 text-white shadow-lg shadow-primary-600/25"
                : "bg-slate-700/50 text-slate-300 hover:bg-slate-700 hover:text-white"
            }
            ${disabled ? "opacity-50 cursor-not-allowed" : ""}
          `}
        >
          <div className="text-center">
            <div>{option.label}</div>
            {option.description && (
              <div className={`text-xs mt-0.5 ${value === option.value ? "text-white/70" : "text-slate-500"}`}>
                {option.description}
              </div>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

// Competitor chip component
function CompetitorChip({
  name,
  onRemove,
  disabled = false,
}: {
  name: string;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.span
      layout
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 border border-slate-600/50 rounded-full text-sm text-slate-200"
    >
      {name}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className={`
          p-0.5 rounded-full hover:bg-slate-600 transition-colors
          ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </motion.span>
  );
}

// Main page component
export function PreferencesSettingsPage() {
  const { data: preferences, isLoading, error, refetch } = usePreferences();
  const updateMutation = useUpdatePreferences();

  // Local state for form inputs
  const [briefingTime, setBriefingTime] = useState("08:00");
  const [leadHours, setLeadHours] = useState<MeetingBriefLeadHours>(24);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [inAppNotifications, setInAppNotifications] = useState(true);
  const [defaultTone, setDefaultTone] = useState<DefaultTone>("friendly");
  const [trackedCompetitors, setTrackedCompetitors] = useState<string[]>([]);
  const [newCompetitor, setNewCompetitor] = useState("");
  const [showSuccess, setShowSuccess] = useState(false);

  // Sync local state with fetched preferences
  useEffect(() => {
    if (preferences) {
      setBriefingTime(preferences.briefing_time);
      setLeadHours(preferences.meeting_brief_lead_hours);
      setEmailNotifications(preferences.notification_email);
      setInAppNotifications(preferences.notification_in_app);
      setDefaultTone(preferences.default_tone);
      setTrackedCompetitors(preferences.tracked_competitors);
    }
  }, [preferences]);

  // Auto-save handler
  const savePreference = useCallback(
    (field: string, value: unknown) => {
      updateMutation.mutate(
        { [field]: value },
        {
          onSuccess: () => {
            setShowSuccess(true);
          },
        }
      );
    },
    [updateMutation]
  );

  // Handle briefing time change
  const handleBriefingTimeChange = (time: string) => {
    setBriefingTime(time);
    savePreference("briefing_time", time);
  };

  // Handle lead hours change
  const handleLeadHoursChange = (hours: MeetingBriefLeadHours) => {
    setLeadHours(hours);
    savePreference("meeting_brief_lead_hours", hours);
  };

  // Handle notification toggles
  const handleEmailNotificationChange = (enabled: boolean) => {
    setEmailNotifications(enabled);
    savePreference("notification_email", enabled);
  };

  const handleInAppNotificationChange = (enabled: boolean) => {
    setInAppNotifications(enabled);
    savePreference("notification_in_app", enabled);
  };

  // Handle tone change
  const handleToneChange = (tone: DefaultTone) => {
    setDefaultTone(tone);
    savePreference("default_tone", tone);
  };

  // Handle competitor management
  const handleAddCompetitor = () => {
    const trimmed = newCompetitor.trim();
    if (trimmed && !trackedCompetitors.includes(trimmed)) {
      const updated = [...trackedCompetitors, trimmed];
      setTrackedCompetitors(updated);
      setNewCompetitor("");
      savePreference("tracked_competitors", updated);
    }
  };

  const handleRemoveCompetitor = (competitor: string) => {
    const updated = trackedCompetitors.filter((c) => c !== competitor);
    setTrackedCompetitors(updated);
    savePreference("tracked_competitors", updated);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddCompetitor();
    }
  };

  const isPending = updateMutation.isPending;

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-3xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-8"
          >
            <h1 className="text-3xl font-bold text-white mb-2">Preferences</h1>
            <p className="text-slate-400">
              Customize how ARIA works for you
            </p>
          </motion.div>

          {/* Info banner */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mb-8 p-4 bg-primary-500/10 border border-primary-500/20 rounded-xl"
          >
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-primary-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-primary-300">
                Your preferences are saved automatically as you make changes.
              </p>
            </div>
          </motion.div>

          {/* Error banner */}
          {error && (
            <ErrorBanner
              message="Failed to load preferences. Please try again."
              onRetry={() => refetch()}
            />
          )}

          {/* Loading state */}
          {isLoading ? (
            <PreferencesSettingsSkeleton />
          ) : (
            <div className="space-y-6">
              {/* Daily Briefing Section */}
              <SettingsSection
                title="Daily Briefing"
                description="When would you like to receive your daily briefing?"
                delay={0.1}
              >
                <div className="flex items-center gap-4">
                  <label htmlFor="briefing-time" className="text-sm text-slate-300">
                    Briefing Time
                  </label>
                  <input
                    id="briefing-time"
                    type="time"
                    value={briefingTime}
                    onChange={(e) => handleBriefingTimeChange(e.target.value)}
                    disabled={isPending}
                    className="
                      px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white
                      focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>
              </SettingsSection>

              {/* Meeting Brief Section */}
              <SettingsSection
                title="Meeting Briefs"
                description="How early should ARIA prepare your meeting briefs?"
                delay={0.15}
              >
                <div className="space-y-3">
                  <label className="text-sm text-slate-300">Lead Time</label>
                  <div className="grid grid-cols-4 gap-2">
                    {LEAD_HOURS_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleLeadHoursChange(option.value)}
                        disabled={isPending}
                        className={`
                          px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                          ${
                            leadHours === option.value
                              ? "bg-primary-600 text-white shadow-lg shadow-primary-600/25"
                              : "bg-slate-700/50 text-slate-300 hover:bg-slate-700 hover:text-white"
                          }
                          disabled:opacity-50
                        `}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </SettingsSection>

              {/* Notifications Section */}
              <SettingsSection
                title="Notifications"
                description="Choose how you want to be notified"
                delay={0.2}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between py-2">
                    <div>
                      <div className="text-sm font-medium text-white">Email Notifications</div>
                      <div className="text-xs text-slate-400">Receive updates via email</div>
                    </div>
                    <ToggleSwitch
                      enabled={emailNotifications}
                      onChange={handleEmailNotificationChange}
                      disabled={isPending}
                    />
                  </div>
                  <div className="border-t border-slate-700/50" />
                  <div className="flex items-center justify-between py-2">
                    <div>
                      <div className="text-sm font-medium text-white">In-App Notifications</div>
                      <div className="text-xs text-slate-400">Show notifications in the app</div>
                    </div>
                    <ToggleSwitch
                      enabled={inAppNotifications}
                      onChange={handleInAppNotificationChange}
                      disabled={isPending}
                    />
                  </div>
                </div>
              </SettingsSection>

              {/* Communication Tone Section */}
              <SettingsSection
                title="Communication Style"
                description="Set the default tone for ARIA's communications"
                delay={0.25}
              >
                <SegmentedControl
                  value={defaultTone}
                  options={TONE_OPTIONS}
                  onChange={handleToneChange}
                  disabled={isPending}
                />
              </SettingsSection>

              {/* Competitors Section */}
              <SettingsSection
                title="Tracked Competitors"
                description="Add competitors you want ARIA to monitor"
                delay={0.3}
              >
                <div className="space-y-4">
                  {/* Add competitor input */}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCompetitor}
                      onChange={(e) => setNewCompetitor(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Enter competitor name"
                      disabled={isPending}
                      className="
                        flex-1 px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white
                        placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500
                        focus:border-transparent disabled:opacity-50 transition-all
                      "
                    />
                    <button
                      type="button"
                      onClick={handleAddCompetitor}
                      disabled={isPending || !newCompetitor.trim()}
                      className="
                        px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white rounded-lg
                        font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed
                        shadow-lg shadow-primary-600/25
                      "
                    >
                      Add
                    </button>
                  </div>

                  {/* Competitor chips */}
                  <div className="flex flex-wrap gap-2">
                    <AnimatePresence>
                      {trackedCompetitors.map((competitor) => (
                        <CompetitorChip
                          key={competitor}
                          name={competitor}
                          onRemove={() => handleRemoveCompetitor(competitor)}
                          disabled={isPending}
                        />
                      ))}
                    </AnimatePresence>
                    {trackedCompetitors.length === 0 && (
                      <p className="text-sm text-slate-500">No competitors tracked yet</p>
                    )}
                  </div>
                </div>
              </SettingsSection>
            </div>
          )}
        </div>
      </div>

      {/* Success toast */}
      <SuccessToast show={showSuccess} onHide={() => setShowSuccess(false)} />
    </DashboardLayout>
  );
}
```

**Step 2: Verify the file compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/PreferencesSettings.tsx
git commit -m "feat(ui): add PreferencesSettingsPage with Apple-inspired design"
```

---

## Task 8: Register Route and Export Page

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Add export to pages barrel**

Modify: `frontend/src/pages/index.ts`

Add this line (in alphabetical order with other exports):
```typescript
export { PreferencesSettingsPage } from "./PreferencesSettings";
```

The complete file should look like:
```typescript
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { GoalsPage } from "./Goals";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { LoginPage } from "./Login";
export { MeetingBriefPage } from "./MeetingBrief";
export { PreferencesSettingsPage } from "./PreferencesSettings";
export { SignupPage } from "./Signup";
```

**Step 2: Add route to App.tsx**

Modify: `frontend/src/App.tsx`

Add `PreferencesSettingsPage` to the import statement:
```typescript
import {
  AriaChatPage,
  BattleCardsPage,
  IntegrationsCallbackPage,
  IntegrationsSettingsPage,
  LoginPage,
  MeetingBriefPage,
  PreferencesSettingsPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
} from "@/pages";
```

Add the route after the integrations callback route (around line 89):
```typescript
<Route
  path="/settings/preferences"
  element={
    <ProtectedRoute>
      <PreferencesSettingsPage />
    </ProtectedRoute>
  }
/>
```

**Step 3: Verify the app compiles**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(routing): register /settings/preferences route"
```

---

## Task 9: Run All Tests and Verify

**Step 1: Run backend tests**

Run: `cd backend && pytest tests/test_preferences*.py -v`
Expected: All tests pass

**Step 2: Run backend linting and type checking**

Run: `cd backend && ruff check src/models/preferences.py src/services/preference_service.py src/api/routes/preferences.py && mypy src/models/preferences.py src/services/preference_service.py src/api/routes/preferences.py --strict`
Expected: No errors

**Step 3: Run frontend type checking**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 4: Run frontend linting**

Run: `cd frontend && npm run lint`
Expected: No errors

**Step 5: Commit**

```bash
git add .
git commit -m "test: verify all preferences tests and linting pass"
```

---

## Summary of Files Created/Modified

**New Files:**
- `backend/supabase/migrations/20260203000003_create_user_preferences.sql`
- `backend/src/models/preferences.py`
- `backend/src/services/preference_service.py`
- `backend/src/api/routes/preferences.py`
- `backend/tests/test_preferences_models.py`
- `backend/tests/test_preference_service.py`
- `backend/tests/test_preferences_routes.py`
- `frontend/src/api/preferences.ts`
- `frontend/src/hooks/usePreferences.ts`
- `frontend/src/pages/PreferencesSettings.tsx`

**Modified Files:**
- `backend/src/main.py` (add preferences router)
- `frontend/src/pages/index.ts` (add export)
- `frontend/src/App.tsx` (add route)

---

Plan complete and saved to `docs/plans/2026-02-03-us-414-settings-preferences.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
