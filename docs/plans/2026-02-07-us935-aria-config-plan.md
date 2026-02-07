# US-935: ARIA Role Configuration & Persona UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a settings page where users configure ARIA's role, personality traits, domain focus, competitor watchlist, and communication preferences — stored in `user_settings.preferences.aria_config` and feeding into agent decisions + personality system.

**Architecture:** Backend Pydantic models + FastAPI route + service layer storing config in existing `user_settings.preferences` JSONB. Frontend React page at `/settings/aria-config` (light surface) with role cards, personality sliders, tag inputs, and a hybrid preview panel. Personality sliders default from auto-calibration with manual override and reset.

**Tech Stack:** Python/FastAPI/Pydantic (backend), React/TypeScript/Tailwind/Framer Motion (frontend), Supabase (storage), React Query (data fetching)

---

### Task 1: Backend Pydantic Models

**Files:**
- Create: `backend/src/models/aria_config.py`
- Test: `backend/tests/test_aria_config_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_aria_config_models.py
"""Tests for ARIA config Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models.aria_config import (
    ARIAConfigResponse,
    ARIAConfigUpdate,
    ARIARole,
    CommunicationPrefs,
    DomainFocus,
    NotificationFrequency,
    PersonalityTraits,
    PreviewResponse,
    ResponseDepth,
)


class TestARIARole:
    """Tests for ARIARole enum."""

    def test_valid_roles(self) -> None:
        assert ARIARole.SALES_OPS == "sales_ops"
        assert ARIARole.BD_SALES == "bd_sales"
        assert ARIARole.MARKETING == "marketing"
        assert ARIARole.EXECUTIVE_SUPPORT == "executive_support"
        assert ARIARole.CUSTOM == "custom"


class TestPersonalityTraits:
    """Tests for PersonalityTraits model."""

    def test_defaults(self) -> None:
        traits = PersonalityTraits()
        assert traits.proactiveness == 0.7
        assert traits.verbosity == 0.5
        assert traits.formality == 0.5
        assert traits.assertiveness == 0.6

    def test_valid_range(self) -> None:
        traits = PersonalityTraits(
            proactiveness=0.0, verbosity=1.0, formality=0.5, assertiveness=0.0
        )
        assert traits.proactiveness == 0.0
        assert traits.verbosity == 1.0

    def test_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            PersonalityTraits(proactiveness=-0.1)

    def test_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PersonalityTraits(verbosity=1.1)


class TestCommunicationPrefs:
    """Tests for CommunicationPrefs model."""

    def test_defaults(self) -> None:
        prefs = CommunicationPrefs()
        assert prefs.preferred_channels == ["in_app"]
        assert prefs.notification_frequency == NotificationFrequency.BALANCED
        assert prefs.response_depth == ResponseDepth.MODERATE
        assert prefs.briefing_time == "08:00"

    def test_valid_briefing_time(self) -> None:
        prefs = CommunicationPrefs(briefing_time="14:30")
        assert prefs.briefing_time == "14:30"

    def test_rejects_invalid_briefing_time(self) -> None:
        with pytest.raises(ValidationError):
            CommunicationPrefs(briefing_time="25:00")

    def test_rejects_bad_format_briefing_time(self) -> None:
        with pytest.raises(ValidationError):
            CommunicationPrefs(briefing_time="8am")

    def test_rejects_invalid_frequency(self) -> None:
        with pytest.raises(ValidationError):
            CommunicationPrefs(notification_frequency="always")

    def test_rejects_invalid_depth(self) -> None:
        with pytest.raises(ValidationError):
            CommunicationPrefs(response_depth="everything")


class TestDomainFocus:
    """Tests for DomainFocus model."""

    def test_defaults(self) -> None:
        focus = DomainFocus()
        assert focus.therapeutic_areas == []
        assert focus.modalities == []
        assert focus.geographies == []

    def test_with_values(self) -> None:
        focus = DomainFocus(
            therapeutic_areas=["oncology", "immunology"],
            modalities=["biologics"],
            geographies=["North America"],
        )
        assert len(focus.therapeutic_areas) == 2


class TestARIAConfigUpdate:
    """Tests for ARIAConfigUpdate model."""

    def test_requires_custom_description_for_custom_role(self) -> None:
        with pytest.raises(ValidationError):
            ARIAConfigUpdate(
                role=ARIARole.CUSTOM,
                custom_role_description=None,
                personality=PersonalityTraits(),
                domain_focus=DomainFocus(),
                competitor_watchlist=[],
                communication=CommunicationPrefs(),
            )

    def test_custom_role_with_description(self) -> None:
        config = ARIAConfigUpdate(
            role=ARIARole.CUSTOM,
            custom_role_description="Focus on partnership development",
            personality=PersonalityTraits(),
            domain_focus=DomainFocus(),
            competitor_watchlist=[],
            communication=CommunicationPrefs(),
        )
        assert config.custom_role_description == "Focus on partnership development"

    def test_non_custom_role_no_description_required(self) -> None:
        config = ARIAConfigUpdate(
            role=ARIARole.SALES_OPS,
            personality=PersonalityTraits(),
            domain_focus=DomainFocus(),
            competitor_watchlist=[],
            communication=CommunicationPrefs(),
        )
        assert config.custom_role_description is None


class TestARIAConfigResponse:
    """Tests for ARIAConfigResponse model."""

    def test_includes_personality_defaults(self) -> None:
        resp = ARIAConfigResponse(
            role=ARIARole.SALES_OPS,
            custom_role_description=None,
            personality=PersonalityTraits(),
            domain_focus=DomainFocus(),
            competitor_watchlist=[],
            communication=CommunicationPrefs(),
            personality_defaults=PersonalityTraits(
                proactiveness=0.6, verbosity=0.4, formality=0.7, assertiveness=0.5
            ),
            updated_at=None,
        )
        assert resp.personality_defaults.proactiveness == 0.6


class TestPreviewResponse:
    """Tests for PreviewResponse model."""

    def test_preview_response(self) -> None:
        resp = PreviewResponse(
            preview_message="Here's how I'd respond with these settings...",
            role_label="Sales Operations",
        )
        assert "respond" in resp.preview_message
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_aria_config_models.py -v`
Expected: FAIL with ModuleNotFoundError (models don't exist yet)

**Step 3: Write minimal implementation**

```python
# backend/src/models/aria_config.py
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

    proactiveness: float = Field(0.7, ge=0.0, le=1.0, description="0=reactive, 1=very proactive")
    verbosity: float = Field(0.5, ge=0.0, le=1.0, description="0=terse, 1=detailed")
    formality: float = Field(0.5, ge=0.0, le=1.0, description="0=casual, 1=formal")
    assertiveness: float = Field(0.6, ge=0.0, le=1.0, description="0=suggestive, 1=directive")


class DomainFocus(BaseModel):
    """Domain focus areas for ARIA to prioritize."""

    therapeutic_areas: list[str] = Field(default_factory=list, description="e.g. oncology, immunology")
    modalities: list[str] = Field(default_factory=list, description="e.g. biologics, cell therapy")
    geographies: list[str] = Field(default_factory=list, description="e.g. North America, EU")


class CommunicationPrefs(BaseModel):
    """Communication channel and style preferences."""

    preferred_channels: list[str] = Field(
        default_factory=lambda: ["in_app"],
        description="in_app, email, slack",
    )
    notification_frequency: NotificationFrequency = Field(
        NotificationFrequency.BALANCED,
        description="How often ARIA sends notifications",
    )
    response_depth: ResponseDepth = Field(
        ResponseDepth.MODERATE,
        description="How detailed ARIA's responses are",
    )
    briefing_time: str = Field("08:00", description="Daily briefing time HH:MM")

    @field_validator("briefing_time")
    @classmethod
    def validate_briefing_time(cls, v: str) -> str:
        """Validate briefing_time is in HH:MM format."""
        pattern = r"^([01]\d|2[0-3]):([0-5]\d)$"
        if not re.match(pattern, v):
            raise ValueError(
                "briefing_time must be in HH:MM format (00:00-23:59)"
            )
        return v


class ARIAConfigUpdate(BaseModel):
    """Request model for creating/updating ARIA configuration."""

    role: ARIARole = Field(..., description="ARIA's focus area")
    custom_role_description: str | None = Field(
        None, description="Required when role is 'custom'"
    )
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_aria_config_models.py -v`
Expected: All tests PASS

**Step 5: Run type checker**

Run: `cd /Users/dhruv/aria && python -m mypy backend/src/models/aria_config.py --strict`
Expected: Success: no issues found

**Step 6: Commit**

```bash
git add backend/src/models/aria_config.py backend/tests/test_aria_config_models.py
git commit -m "feat(US-935): add ARIA config Pydantic models with validation"
```

---

### Task 2: Backend Service Layer

**Files:**
- Create: `backend/src/services/aria_config_service.py`
- Test: `backend/tests/test_aria_config_service.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_aria_config_service.py
"""Tests for ARIAConfigService."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.aria_config import (
    ARIAConfigUpdate,
    ARIARole,
    CommunicationPrefs,
    DomainFocus,
    PersonalityTraits,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    return MagicMock()


@pytest.mark.asyncio
async def test_get_config_returns_defaults_for_new_user(mock_db: MagicMock) -> None:
    """First-time user gets default config with calibrated personality."""
    with patch("src.services.aria_config_service.SupabaseClient") as mock_db_class:
        # No existing aria_config, but has calibration
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={
                "preferences": {
                    "digital_twin": {
                        "personality_calibration": {
                            "directness": 0.8,
                            "warmth": 0.3,
                            "assertiveness": 0.7,
                            "detail_orientation": 0.6,
                            "formality": 0.9,
                        }
                    }
                }
            }
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.aria_config_service import ARIAConfigService

        service = ARIAConfigService()
        result = await service.get_config("user-123")

        # Should map calibration to personality defaults
        assert result["personality_defaults"]["formality"] == 0.9
        assert result["personality_defaults"]["assertiveness"] == 0.7
        # Personality should equal defaults for new user
        assert result["personality"]["formality"] == 0.9
        assert result["role"] == "sales_ops"


@pytest.mark.asyncio
async def test_get_config_returns_stored_config(mock_db: MagicMock) -> None:
    """Returning user gets their saved config."""
    with patch("src.services.aria_config_service.SupabaseClient") as mock_db_class:
        stored_config = {
            "role": "marketing",
            "custom_role_description": None,
            "personality": {
                "proactiveness": 0.9,
                "verbosity": 0.3,
                "formality": 0.8,
                "assertiveness": 0.4,
            },
            "domain_focus": {"therapeutic_areas": ["oncology"], "modalities": [], "geographies": []},
            "competitor_watchlist": ["Pfizer"],
            "communication": {
                "preferred_channels": ["in_app", "email"],
                "notification_frequency": "aggressive",
                "response_depth": "detailed",
                "briefing_time": "07:00",
            },
            "personality_defaults": {
                "proactiveness": 0.7,
                "verbosity": 0.5,
                "formality": 0.5,
                "assertiveness": 0.6,
            },
            "updated_at": "2026-02-07T10:00:00Z",
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"preferences": {"aria_config": stored_config}}
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.aria_config_service import ARIAConfigService

        service = ARIAConfigService()
        result = await service.get_config("user-456")

        assert result["role"] == "marketing"
        assert result["personality"]["proactiveness"] == 0.9
        assert result["competitor_watchlist"] == ["Pfizer"]


@pytest.mark.asyncio
async def test_update_config_persists(mock_db: MagicMock) -> None:
    """Update saves to user_settings.preferences.aria_config."""
    with patch("src.services.aria_config_service.SupabaseClient") as mock_db_class:
        # Current preferences
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"preferences": {}}
        )
        # Update response
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"preferences": {}}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.aria_config_service import ARIAConfigService

        service = ARIAConfigService()
        update = ARIAConfigUpdate(
            role=ARIARole.BD_SALES,
            personality=PersonalityTraits(proactiveness=0.9),
            domain_focus=DomainFocus(therapeutic_areas=["oncology"]),
            competitor_watchlist=["Moderna"],
            communication=CommunicationPrefs(),
        )
        result = await service.update_config("user-789", update)

        # Verify update was called
        mock_db.table.return_value.update.assert_called_once()
        call_args = mock_db.table.return_value.update.call_args[0][0]
        aria_config = call_args["preferences"]["aria_config"]
        assert aria_config["role"] == "bd_sales"
        assert aria_config["competitor_watchlist"] == ["Moderna"]


@pytest.mark.asyncio
async def test_reset_personality_restores_calibrated_defaults(mock_db: MagicMock) -> None:
    """Reset copies calibrated values back into personality."""
    with patch("src.services.aria_config_service.SupabaseClient") as mock_db_class:
        calibrated = {
            "directness": 0.8,
            "warmth": 0.3,
            "assertiveness": 0.7,
            "detail_orientation": 0.6,
            "formality": 0.9,
        }
        stored_config = {
            "role": "sales_ops",
            "personality": {"proactiveness": 0.1, "verbosity": 0.1, "formality": 0.1, "assertiveness": 0.1},
            "personality_defaults": {"proactiveness": 0.7, "verbosity": 0.6, "formality": 0.9, "assertiveness": 0.7},
            "domain_focus": {"therapeutic_areas": [], "modalities": [], "geographies": []},
            "competitor_watchlist": [],
            "communication": {"preferred_channels": ["in_app"], "notification_frequency": "balanced", "response_depth": "moderate", "briefing_time": "08:00"},
            "custom_role_description": None,
            "updated_at": None,
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={
                "preferences": {
                    "aria_config": stored_config,
                    "digital_twin": {"personality_calibration": calibrated},
                }
            }
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"preferences": {}}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.aria_config_service import ARIAConfigService

        service = ARIAConfigService()
        result = await service.reset_personality("user-123")

        # Verify personality was reset to defaults
        call_args = mock_db.table.return_value.update.call_args[0][0]
        updated_personality = call_args["preferences"]["aria_config"]["personality"]
        assert updated_personality["formality"] == 0.9
        assert updated_personality["assertiveness"] == 0.7
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_aria_config_service.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# backend/src/services/aria_config_service.py
"""ARIA configuration service.

Manages ARIA role, personality, domain focus, competitor watchlist,
and communication preferences. Config stored in
user_settings.preferences.aria_config JSONB.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.aria_config import ARIAConfigUpdate, ARIARole, PersonalityTraits

logger = logging.getLogger(__name__)

# Default personality mapped from auto-calibration
_DEFAULT_PERSONALITY = PersonalityTraits().model_dump()

# Map from calibration trait names to config trait names
_CALIBRATION_MAPPING: dict[str, str] = {
    "assertiveness": "assertiveness",
    "formality": "formality",
    "detail_orientation": "verbosity",
}


def _calibration_to_personality(calibration: dict[str, Any]) -> dict[str, Any]:
    """Map PersonalityCalibration values to PersonalityTraits.

    Calibration has: directness, warmth, assertiveness, detail_orientation, formality
    Config has: proactiveness, verbosity, formality, assertiveness

    Mapping:
    - assertiveness -> assertiveness (direct)
    - formality -> formality (direct)
    - detail_orientation -> verbosity (high detail = high verbosity)
    - proactiveness has no calibration source, keep default 0.7
    """
    result = dict(_DEFAULT_PERSONALITY)
    if "assertiveness" in calibration:
        result["assertiveness"] = calibration["assertiveness"]
    if "formality" in calibration:
        result["formality"] = calibration["formality"]
    if "detail_orientation" in calibration:
        result["verbosity"] = calibration["detail_orientation"]
    return result


class ARIAConfigService:
    """Service for managing ARIA configuration."""

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_config(self, user_id: str) -> dict[str, Any]:
        """Get ARIA config, building defaults from calibration for new users.

        Args:
            user_id: The user's ID.

        Returns:
            ARIA config dict matching ARIAConfigResponse schema.
        """
        prefs = await self._get_preferences(user_id)
        aria_config = prefs.get("aria_config")

        if aria_config:
            return cast(dict[str, Any], aria_config)

        # Build defaults from calibration
        calibration = self._extract_calibration(prefs)
        personality = _calibration_to_personality(calibration)

        default_config: dict[str, Any] = {
            "role": ARIARole.SALES_OPS.value,
            "custom_role_description": None,
            "personality": personality,
            "domain_focus": {"therapeutic_areas": [], "modalities": [], "geographies": []},
            "competitor_watchlist": [],
            "communication": {
                "preferred_channels": ["in_app"],
                "notification_frequency": "balanced",
                "response_depth": "moderate",
                "briefing_time": "08:00",
            },
            "personality_defaults": personality,
            "updated_at": None,
        }
        return default_config

    async def update_config(
        self, user_id: str, data: ARIAConfigUpdate
    ) -> dict[str, Any]:
        """Update ARIA configuration.

        Args:
            user_id: The user's ID.
            data: Config update data.

        Returns:
            Updated config dict.
        """
        prefs = await self._get_preferences(user_id)

        # Preserve personality_defaults from existing config or build from calibration
        existing_config = prefs.get("aria_config", {})
        personality_defaults = existing_config.get("personality_defaults")
        if not personality_defaults:
            calibration = self._extract_calibration(prefs)
            personality_defaults = _calibration_to_personality(calibration)

        config_data = data.model_dump(mode="json")
        config_data["personality_defaults"] = personality_defaults
        config_data["updated_at"] = datetime.now(UTC).isoformat()

        prefs["aria_config"] = config_data
        self._db.table("user_settings").update(
            {"preferences": prefs}
        ).eq("user_id", user_id).execute()

        logger.info("ARIA config updated", extra={"user_id": user_id, "role": data.role.value})
        return cast(dict[str, Any], config_data)

    async def reset_personality(self, user_id: str) -> dict[str, Any]:
        """Reset personality sliders to calibrated defaults.

        Args:
            user_id: The user's ID.

        Returns:
            Updated config dict with reset personality.
        """
        prefs = await self._get_preferences(user_id)
        aria_config = prefs.get("aria_config", {})

        # Get defaults from stored config or recalculate from calibration
        personality_defaults = aria_config.get("personality_defaults")
        if not personality_defaults:
            calibration = self._extract_calibration(prefs)
            personality_defaults = _calibration_to_personality(calibration)

        aria_config["personality"] = dict(personality_defaults)
        aria_config["personality_defaults"] = personality_defaults
        aria_config["updated_at"] = datetime.now(UTC).isoformat()
        prefs["aria_config"] = aria_config

        self._db.table("user_settings").update(
            {"preferences": prefs}
        ).eq("user_id", user_id).execute()

        logger.info("ARIA personality reset to defaults", extra={"user_id": user_id})
        return cast(dict[str, Any], aria_config)

    async def _get_preferences(self, user_id: str) -> dict[str, Any]:
        """Read user_settings.preferences for a user."""
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                return cast(dict[str, Any], row.get("preferences", {}) or {})
        except Exception as e:
            logger.warning("Failed to read preferences: %s", e)
        return {}

    def _extract_calibration(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """Extract personality calibration from Digital Twin data."""
        dt = prefs.get("digital_twin", {})
        calibration: dict[str, Any] = dt.get("personality_calibration", {})
        return calibration


# Singleton
_service: ARIAConfigService | None = None


def get_aria_config_service() -> ARIAConfigService:
    """Get or create service singleton."""
    global _service
    if _service is None:
        _service = ARIAConfigService()
    return _service
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_aria_config_service.py -v`
Expected: All tests PASS

**Step 5: Run type checker**

Run: `cd /Users/dhruv/aria && python -m mypy backend/src/services/aria_config_service.py --strict`
Expected: Success

**Step 6: Commit**

```bash
git add backend/src/services/aria_config_service.py backend/tests/test_aria_config_service.py
git commit -m "feat(US-935): add ARIA config service with calibration defaults"
```

---

### Task 3: Backend API Routes

**Files:**
- Create: `backend/src/api/routes/aria_config.py`
- Modify: `backend/src/main.py` (add router import and registration)
- Test: `backend/tests/test_api_aria_config.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_api_aria_config.py
"""Tests for ARIA config API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.aria_config import ARIARole, PersonalityTraits


@pytest.fixture
def mock_user() -> MagicMock:
    """Create mock authenticated user."""
    user = MagicMock()
    user.id = "user-test-123"
    return user


@pytest.fixture
def default_config() -> dict:
    """Default ARIA config response."""
    return {
        "role": "sales_ops",
        "custom_role_description": None,
        "personality": {"proactiveness": 0.7, "verbosity": 0.5, "formality": 0.5, "assertiveness": 0.6},
        "domain_focus": {"therapeutic_areas": [], "modalities": [], "geographies": []},
        "competitor_watchlist": [],
        "communication": {
            "preferred_channels": ["in_app"],
            "notification_frequency": "balanced",
            "response_depth": "moderate",
            "briefing_time": "08:00",
        },
        "personality_defaults": {"proactiveness": 0.7, "verbosity": 0.5, "formality": 0.5, "assertiveness": 0.6},
        "updated_at": None,
    }


@pytest.mark.asyncio
async def test_get_aria_config(mock_user: MagicMock, default_config: dict) -> None:
    """GET /aria-config returns config for authenticated user."""
    with (
        patch("src.api.routes.aria_config.ARIAConfigService") as mock_service_class,
        patch("src.api.routes.aria_config.get_current_user", return_value=mock_user),
    ):
        mock_service = MagicMock()
        mock_service.get_config = AsyncMock(return_value=default_config)
        mock_service_class.return_value = mock_service

        from src.api.routes.aria_config import get_aria_config

        result = await get_aria_config(mock_user)
        assert result["role"] == "sales_ops"
        mock_service.get_config.assert_awaited_once_with("user-test-123")


@pytest.mark.asyncio
async def test_update_aria_config(mock_user: MagicMock, default_config: dict) -> None:
    """PUT /aria-config saves and returns updated config."""
    with patch("src.api.routes.aria_config.ARIAConfigService") as mock_service_class:
        updated = dict(default_config)
        updated["role"] = "bd_sales"
        mock_service = MagicMock()
        mock_service.update_config = AsyncMock(return_value=updated)
        mock_service_class.return_value = mock_service

        from src.api.routes.aria_config import update_aria_config
        from src.models.aria_config import (
            ARIAConfigUpdate,
            CommunicationPrefs,
            DomainFocus,
        )

        data = ARIAConfigUpdate(
            role=ARIARole.BD_SALES,
            personality=PersonalityTraits(),
            domain_focus=DomainFocus(),
            competitor_watchlist=[],
            communication=CommunicationPrefs(),
        )
        result = await update_aria_config(data, mock_user)
        assert result["role"] == "bd_sales"


@pytest.mark.asyncio
async def test_reset_personality(mock_user: MagicMock, default_config: dict) -> None:
    """POST /aria-config/reset-personality resets personality sliders."""
    with patch("src.api.routes.aria_config.ARIAConfigService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.reset_personality = AsyncMock(return_value=default_config)
        mock_service_class.return_value = mock_service

        from src.api.routes.aria_config import reset_personality

        result = await reset_personality(mock_user)
        mock_service.reset_personality.assert_awaited_once_with("user-test-123")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_api_aria_config.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# backend/src/api/routes/aria_config.py
"""ARIA role configuration and persona API routes (US-935)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.models.aria_config import ARIAConfigResponse, ARIAConfigUpdate, PreviewResponse
from src.services.aria_config_service import ARIAConfigService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aria-config", tags=["aria-config"])


def _get_service() -> ARIAConfigService:
    """Get ARIA config service instance."""
    return ARIAConfigService()


@router.get("", response_model=ARIAConfigResponse)
async def get_aria_config(current_user: CurrentUser) -> dict[str, Any]:
    """Get current user's ARIA configuration."""
    service = _get_service()
    try:
        config = await service.get_config(current_user.id)
        logger.info("ARIA config retrieved", extra={"user_id": current_user.id})
        return config
    except Exception as e:
        logger.exception("Error fetching ARIA config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ARIA configuration",
        ) from e


@router.put("", response_model=ARIAConfigResponse)
async def update_aria_config(
    data: ARIAConfigUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's ARIA configuration."""
    service = _get_service()
    try:
        config = await service.update_config(current_user.id, data)
        logger.info(
            "ARIA config updated via API",
            extra={"user_id": current_user.id, "role": data.role.value},
        )
        return config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        logger.exception("Error updating ARIA config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ARIA configuration",
        ) from e


@router.post("/reset-personality", response_model=ARIAConfigResponse)
async def reset_personality(current_user: CurrentUser) -> dict[str, Any]:
    """Reset personality sliders to calibrated defaults."""
    service = _get_service()
    try:
        config = await service.reset_personality(current_user.id)
        logger.info("ARIA personality reset", extra={"user_id": current_user.id})
        return config
    except Exception as e:
        logger.exception("Error resetting personality")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset personality",
        ) from e


@router.post("/preview", response_model=PreviewResponse)
async def generate_preview(
    data: ARIAConfigUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate a preview message showing how ARIA would respond with given config."""
    service = _get_service()
    try:
        preview = await service.generate_preview(current_user.id, data)
        return preview
    except Exception as e:
        logger.exception("Error generating preview")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate preview",
        ) from e
```

**Step 4: Register router in main.py**

Add to imports in `backend/src/main.py`:
```python
from src.api.routes import (
    ...
    aria_config,
    ...
)
```

Add router registration (alphabetically after `analytics`):
```python
app.include_router(aria_config.router, prefix="/api/v1")
```

**Step 5: Add generate_preview stub to service**

Add to `ARIAConfigService` in `backend/src/services/aria_config_service.py`:

```python
    async def generate_preview(
        self, user_id: str, data: ARIAConfigUpdate
    ) -> dict[str, Any]:
        """Generate a sample ARIA message with given configuration.

        Args:
            user_id: The user's ID.
            data: Config to preview.

        Returns:
            Preview response dict.
        """
        role_labels = {
            ARIARole.SALES_OPS: "Sales Operations",
            ARIARole.BD_SALES: "BD/Sales",
            ARIARole.MARKETING: "Marketing",
            ARIARole.EXECUTIVE_SUPPORT: "Executive Support",
            ARIARole.CUSTOM: "Custom",
        }
        role_label = role_labels.get(data.role, "Sales Operations")

        # Build personality description for prompt
        p = data.personality
        tone_parts: list[str] = []
        if p.formality > 0.7:
            tone_parts.append("formal")
        elif p.formality < 0.3:
            tone_parts.append("casual")
        if p.assertiveness > 0.7:
            tone_parts.append("direct")
        elif p.assertiveness < 0.3:
            tone_parts.append("suggestive")
        if p.verbosity > 0.7:
            tone_parts.append("detailed")
        elif p.verbosity < 0.3:
            tone_parts.append("concise")
        if p.proactiveness > 0.7:
            tone_parts.append("proactive")
        elif p.proactiveness < 0.3:
            tone_parts.append("reactive")

        tone_desc = ", ".join(tone_parts) if tone_parts else "balanced"

        # For now, return a static template. LLM integration can be added later.
        preview = (
            f"Good morning. I've reviewed overnight developments relevant to your "
            f"{role_label.lower()} priorities. "
        )
        if data.domain_focus.therapeutic_areas:
            areas = ", ".join(data.domain_focus.therapeutic_areas[:2])
            preview += f"In {areas}, "
        if data.competitor_watchlist:
            competitor = data.competitor_watchlist[0]
            preview += f"{competitor} announced a new partnership yesterday — "
            preview += "I've prepared a competitive analysis. "
        else:
            preview += "there are three signals worth your attention. "

        if p.verbosity > 0.7:
            preview += "I've compiled detailed briefings for each item with supporting data."
        elif p.verbosity < 0.3:
            preview += "Summary attached."
        else:
            preview += "Shall I walk you through the highlights?"

        return {"preview_message": preview, "role_label": role_label}
```

**Step 6: Run all tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_api_aria_config.py backend/tests/test_aria_config_service.py backend/tests/test_aria_config_models.py -v`
Expected: All PASS

**Step 7: Run type checker on route**

Run: `cd /Users/dhruv/aria && python -m mypy backend/src/api/routes/aria_config.py --strict`
Expected: Success

**Step 8: Commit**

```bash
git add backend/src/api/routes/aria_config.py backend/src/main.py backend/src/services/aria_config_service.py backend/tests/test_api_aria_config.py
git commit -m "feat(US-935): add ARIA config API routes and preview endpoint"
```

---

### Task 4: Frontend API Client & Hook

**Files:**
- Create: `frontend/src/api/ariaConfig.ts`
- Create: `frontend/src/hooks/useAriaConfig.ts`

**Step 1: Create API client**

```typescript
// frontend/src/api/ariaConfig.ts
import { apiClient } from "./client";

// Enums matching backend
export type ARIARole = "sales_ops" | "bd_sales" | "marketing" | "executive_support" | "custom";
export type NotificationFrequency = "minimal" | "balanced" | "aggressive";
export type ResponseDepth = "brief" | "moderate" | "detailed";

export interface PersonalityTraits {
  proactiveness: number;
  verbosity: number;
  formality: number;
  assertiveness: number;
}

export interface DomainFocus {
  therapeutic_areas: string[];
  modalities: string[];
  geographies: string[];
}

export interface CommunicationPrefs {
  preferred_channels: string[];
  notification_frequency: NotificationFrequency;
  response_depth: ResponseDepth;
  briefing_time: string;
}

export interface ARIAConfig {
  role: ARIARole;
  custom_role_description: string | null;
  personality: PersonalityTraits;
  domain_focus: DomainFocus;
  competitor_watchlist: string[];
  communication: CommunicationPrefs;
  personality_defaults: PersonalityTraits;
  updated_at: string | null;
}

export interface ARIAConfigUpdateRequest {
  role: ARIARole;
  custom_role_description?: string | null;
  personality: PersonalityTraits;
  domain_focus: DomainFocus;
  competitor_watchlist: string[];
  communication: CommunicationPrefs;
}

export interface PreviewResponse {
  preview_message: string;
  role_label: string;
}

export async function getAriaConfig(): Promise<ARIAConfig> {
  const response = await apiClient.get<ARIAConfig>("/aria-config");
  return response.data;
}

export async function updateAriaConfig(
  data: ARIAConfigUpdateRequest
): Promise<ARIAConfig> {
  const response = await apiClient.put<ARIAConfig>("/aria-config", data);
  return response.data;
}

export async function resetPersonality(): Promise<ARIAConfig> {
  const response = await apiClient.post<ARIAConfig>("/aria-config/reset-personality");
  return response.data;
}

export async function generatePreview(
  data: ARIAConfigUpdateRequest
): Promise<PreviewResponse> {
  const response = await apiClient.post<PreviewResponse>("/aria-config/preview", data);
  return response.data;
}
```

**Step 2: Create React Query hook**

```typescript
// frontend/src/hooks/useAriaConfig.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAriaConfig,
  updateAriaConfig,
  resetPersonality,
  generatePreview,
  type ARIAConfig,
  type ARIAConfigUpdateRequest,
  type PreviewResponse,
} from "@/api/ariaConfig";

export const ariaConfigKeys = {
  all: ["ariaConfig"] as const,
  detail: () => [...ariaConfigKeys.all, "detail"] as const,
};

export function useAriaConfig() {
  return useQuery({
    queryKey: ariaConfigKeys.detail(),
    queryFn: () => getAriaConfig(),
  });
}

export function useUpdateAriaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ARIAConfigUpdateRequest) => updateAriaConfig(data),
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: ariaConfigKeys.detail() });

      const previous = queryClient.getQueryData<ARIAConfig>(
        ariaConfigKeys.detail()
      );

      if (previous) {
        queryClient.setQueryData<ARIAConfig>(ariaConfigKeys.detail(), {
          ...previous,
          ...newData,
          updated_at: new Date().toISOString(),
        });
      }

      return { previous };
    },
    onError: (_err, _newData, context) => {
      if (context?.previous) {
        queryClient.setQueryData(ariaConfigKeys.detail(), context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ariaConfigKeys.detail() });
    },
  });
}

export function useResetPersonality() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => resetPersonality(),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ariaConfigKeys.detail() });
    },
  });
}

export function useGeneratePreview() {
  return useMutation({
    mutationFn: (data: ARIAConfigUpdateRequest) => generatePreview(data),
  });
}
```

**Step 3: Run type check**

Run: `cd /Users/dhruv/aria && npm run typecheck --prefix frontend`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/api/ariaConfig.ts frontend/src/hooks/useAriaConfig.ts
git commit -m "feat(US-935): add frontend API client and React Query hooks"
```

---

### Task 5: Frontend Page — ARIAConfigPage.tsx

**Files:**
- Create: `frontend/src/pages/ARIAConfigPage.tsx`
- Modify: `frontend/src/pages/index.ts` (add export)
- Modify: `frontend/src/App.tsx` (add route)

**Reference:** Follow `PreferencesSettings.tsx` pattern for state management and auto-save. Use ARIA Design System light surface colors. See design doc `docs/plans/2026-02-07-us935-aria-config-design.md` for exact specs.

**Step 1: Create the page component**

Create `frontend/src/pages/ARIAConfigPage.tsx` — full implementation with:
- `DashboardLayout` wrapper
- Loading skeleton (light surface: `bg-[#F5F5F0]` placeholder blocks on `bg-[#FAFAF9]`)
- Error banner with retry
- Success toast
- Local state synced from `useAriaConfig()` via `useEffect`
- Auto-save via `useUpdateAriaConfig()` with debounce for sliders
- Seven sections per design doc:
  1. Header — "Configure ARIA" in Instrument Serif
  2. Role selector — 5 cards grid, custom textarea reveal
  3. Personality sliders — 4 range inputs with reset button
  4. Domain focus — 3 tag inputs with suggestion dropdown
  5. Competitor watchlist — tag input
  6. Communication prefs — toggles, segmented controls, time picker
  7. Preview panel — static template + "Generate preview" button

Light surface colors throughout: `bg-[#FAFAF9]` page, `bg-white` cards with `border-[#E2E0DC]`, `text-[#1A1D27]` primary text, `text-[#6B7280]` secondary, `[#5B6E8A]` interactive.

Lucide icons: `Briefcase`, `Handshake`, `Megaphone`, `Crown`, `Wrench` for role cards. `Sliders`, `Target`, `Eye`, `MessageSquare` for section icons.

**Step 2: Add page export**

Add to `frontend/src/pages/index.ts`:
```typescript
export { ARIAConfigPage } from "./ARIAConfigPage";
```

**Step 3: Add route in App.tsx**

Add import `ARIAConfigPage` to the imports from `@/pages`. Add route block between `/settings/preferences` and `/settings/profile`:

```tsx
<Route
  path="/settings/aria-config"
  element={
    <ProtectedRoute>
      <ARIAConfigPage />
    </ProtectedRoute>
  }
/>
```

**Step 4: Run type check and lint**

Run: `cd /Users/dhruv/aria && npm run typecheck --prefix frontend && npm run lint --prefix frontend`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/pages/ARIAConfigPage.tsx frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(US-935): add ARIA Config settings page with light surface design"
```

---

### Task 6: Quality Gates & Final Verification

**Files:** All files from Tasks 1-5

**Step 1: Run all backend tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_aria_config_models.py backend/tests/test_aria_config_service.py backend/tests/test_api_aria_config.py -v`
Expected: All PASS

**Step 2: Run backend type checker on all new files**

Run: `cd /Users/dhruv/aria && python -m mypy backend/src/models/aria_config.py backend/src/services/aria_config_service.py backend/src/api/routes/aria_config.py --strict`
Expected: Success

**Step 3: Run backend linting**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/models/aria_config.py backend/src/services/aria_config_service.py backend/src/api/routes/aria_config.py && python -m ruff format --check backend/src/models/aria_config.py backend/src/services/aria_config_service.py backend/src/api/routes/aria_config.py`
Expected: All passed

**Step 4: Run frontend type check**

Run: `cd /Users/dhruv/aria && npm run typecheck --prefix frontend`
Expected: No errors

**Step 5: Run frontend lint**

Run: `cd /Users/dhruv/aria && npm run lint --prefix frontend`
Expected: No errors

**Step 6: Fix any issues found in steps 1-5, then commit fixes if needed**
