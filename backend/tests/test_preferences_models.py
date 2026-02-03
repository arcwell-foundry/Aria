"""Tests for user preferences Pydantic models."""

import pytest
from pydantic import ValidationError


def test_default_tone_enum_values() -> None:
    """DefaultTone should have formal, friendly, urgent values."""
    from src.models.preferences import DefaultTone

    assert DefaultTone.FORMAL.value == "formal"
    assert DefaultTone.FRIENDLY.value == "friendly"
    assert DefaultTone.URGENT.value == "urgent"


def test_meeting_brief_lead_hours_enum_values() -> None:
    """MeetingBriefLeadHours should have 2, 6, 12, 24 hour options."""
    from src.models.preferences import MeetingBriefLeadHours

    assert MeetingBriefLeadHours.TWO_HOURS.value == 2
    assert MeetingBriefLeadHours.SIX_HOURS.value == 6
    assert MeetingBriefLeadHours.TWELVE_HOURS.value == 12
    assert MeetingBriefLeadHours.TWENTY_FOUR_HOURS.value == 24


def test_preference_update_all_fields_optional() -> None:
    """PreferenceUpdate should allow empty initialization (all fields optional)."""
    from src.models.preferences import PreferenceUpdate

    update = PreferenceUpdate()

    assert update.briefing_time is None
    assert update.meeting_brief_lead_hours is None
    assert update.notification_email is None
    assert update.notification_in_app is None
    assert update.default_tone is None
    assert update.tracked_competitors is None
    assert update.timezone is None


def test_preference_update_partial_updates() -> None:
    """PreferenceUpdate should allow partial field updates."""
    from src.models.preferences import DefaultTone, MeetingBriefLeadHours, PreferenceUpdate

    # Update only briefing_time
    update1 = PreferenceUpdate(briefing_time="09:30")
    assert update1.briefing_time == "09:30"
    assert update1.notification_email is None

    # Update only notification settings
    update2 = PreferenceUpdate(notification_email=False, notification_in_app=True)
    assert update2.notification_email is False
    assert update2.notification_in_app is True
    assert update2.briefing_time is None

    # Update tone and lead hours
    update3 = PreferenceUpdate(
        default_tone=DefaultTone.FORMAL,
        meeting_brief_lead_hours=MeetingBriefLeadHours.SIX_HOURS,
    )
    assert update3.default_tone == DefaultTone.FORMAL
    assert update3.meeting_brief_lead_hours == MeetingBriefLeadHours.SIX_HOURS


def test_preference_update_valid_briefing_time_formats() -> None:
    """PreferenceUpdate should accept valid HH:MM time formats."""
    from src.models.preferences import PreferenceUpdate

    # Standard times
    assert PreferenceUpdate(briefing_time="08:00").briefing_time == "08:00"
    assert PreferenceUpdate(briefing_time="00:00").briefing_time == "00:00"
    assert PreferenceUpdate(briefing_time="23:59").briefing_time == "23:59"
    assert PreferenceUpdate(briefing_time="12:30").briefing_time == "12:30"
    assert PreferenceUpdate(briefing_time="09:05").briefing_time == "09:05"


def test_preference_update_invalid_briefing_time_rejected() -> None:
    """PreferenceUpdate should reject invalid time formats."""
    from src.models.preferences import PreferenceUpdate

    # Invalid hour (25:00)
    with pytest.raises(ValidationError):
        PreferenceUpdate(briefing_time="25:00")

    # Invalid minute (24:60)
    with pytest.raises(ValidationError):
        PreferenceUpdate(briefing_time="24:00")

    # Invalid format (no colon)
    with pytest.raises(ValidationError):
        PreferenceUpdate(briefing_time="0800")

    # Invalid format (single digit hour without padding)
    with pytest.raises(ValidationError):
        PreferenceUpdate(briefing_time="8:00")


def test_preference_update_tracked_competitors_list() -> None:
    """PreferenceUpdate should accept a list of tracked competitors."""
    from src.models.preferences import PreferenceUpdate

    update = PreferenceUpdate(
        tracked_competitors=["Competitor A", "Competitor B", "Competitor C"]
    )

    assert update.tracked_competitors == ["Competitor A", "Competitor B", "Competitor C"]
    assert len(update.tracked_competitors) == 3


def test_preference_response_full_response() -> None:
    """PreferenceResponse should contain all expected fields."""
    from src.models.preferences import PreferenceResponse

    response = PreferenceResponse(
        id="pref-123",
        user_id="user-456",
        briefing_time="08:00",
        meeting_brief_lead_hours=24,
        notification_email=True,
        notification_in_app=True,
        default_tone="friendly",
        tracked_competitors=["Competitor X", "Competitor Y"],
        timezone="America/New_York",
        created_at="2026-01-15T10:00:00Z",
        updated_at="2026-01-20T15:30:00Z",
    )

    assert response.id == "pref-123"
    assert response.user_id == "user-456"
    assert response.briefing_time == "08:00"
    assert response.meeting_brief_lead_hours == 24
    assert response.notification_email is True
    assert response.notification_in_app is True
    assert response.default_tone == "friendly"
    assert response.tracked_competitors == ["Competitor X", "Competitor Y"]
    assert response.timezone == "America/New_York"
    assert response.created_at == "2026-01-15T10:00:00Z"
    assert response.updated_at == "2026-01-20T15:30:00Z"


def test_preference_create_with_defaults() -> None:
    """PreferenceCreate should have sensible defaults."""
    from src.models.preferences import DefaultTone, PreferenceCreate

    pref = PreferenceCreate(user_id="user-123")

    assert pref.user_id == "user-123"
    assert pref.briefing_time == "08:00"
    assert pref.meeting_brief_lead_hours == 24
    assert pref.notification_email is True
    assert pref.notification_in_app is True
    assert pref.default_tone == DefaultTone.FRIENDLY
    assert pref.tracked_competitors == []
    assert pref.timezone == "UTC"


def test_preference_create_with_custom_values() -> None:
    """PreferenceCreate should accept custom values."""
    from src.models.preferences import DefaultTone, PreferenceCreate

    pref = PreferenceCreate(
        user_id="user-456",
        briefing_time="09:00",
        meeting_brief_lead_hours=12,
        notification_email=False,
        notification_in_app=False,
        default_tone=DefaultTone.FORMAL,
        tracked_competitors=["Acme Corp"],
        timezone="Europe/London",
    )

    assert pref.user_id == "user-456"
    assert pref.briefing_time == "09:00"
    assert pref.meeting_brief_lead_hours == 12
    assert pref.notification_email is False
    assert pref.notification_in_app is False
    assert pref.default_tone == DefaultTone.FORMAL
    assert pref.tracked_competitors == ["Acme Corp"]
    assert pref.timezone == "Europe/London"
