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

        assert result["personality_defaults"]["formality"] == 0.9
        assert result["personality_defaults"]["assertiveness"] == 0.7
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
            "domain_focus": {
                "therapeutic_areas": ["oncology"],
                "modalities": [],
                "geographies": [],
            },
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
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"preferences": {}}
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"preferences": {}}])
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
        await service.update_config("user-789", update)

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
            "personality": {
                "proactiveness": 0.1,
                "verbosity": 0.1,
                "formality": 0.1,
                "assertiveness": 0.1,
            },
            "personality_defaults": {
                "proactiveness": 0.7,
                "verbosity": 0.6,
                "formality": 0.9,
                "assertiveness": 0.7,
            },
            "domain_focus": {
                "therapeutic_areas": [],
                "modalities": [],
                "geographies": [],
            },
            "competitor_watchlist": [],
            "communication": {
                "preferred_channels": ["in_app"],
                "notification_frequency": "balanced",
                "response_depth": "moderate",
                "briefing_time": "08:00",
            },
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
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"preferences": {}}])
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.aria_config_service import ARIAConfigService

        service = ARIAConfigService()
        await service.reset_personality("user-123")

        call_args = mock_db.table.return_value.update.call_args[0][0]
        updated_personality = call_args["preferences"]["aria_config"]["personality"]
        assert updated_personality["formality"] == 0.9
        assert updated_personality["assertiveness"] == 0.7
