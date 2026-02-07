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
