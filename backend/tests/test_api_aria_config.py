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
        "personality": {
            "proactiveness": 0.7,
            "verbosity": 0.5,
            "formality": 0.5,
            "assertiveness": 0.6,
        },
        "domain_focus": {"therapeutic_areas": [], "modalities": [], "geographies": []},
        "competitor_watchlist": [],
        "communication": {
            "preferred_channels": ["in_app"],
            "notification_frequency": "balanced",
            "response_depth": "moderate",
            "briefing_time": "08:00",
        },
        "personality_defaults": {
            "proactiveness": 0.7,
            "verbosity": 0.5,
            "formality": 0.5,
            "assertiveness": 0.6,
        },
        "updated_at": None,
    }


@pytest.mark.asyncio
async def test_get_aria_config(mock_user: MagicMock, default_config: dict) -> None:
    """GET /aria-config returns config for authenticated user."""
    mock_service = MagicMock()
    mock_service.get_config = AsyncMock(return_value=default_config)

    with (
        patch(
            "src.api.routes.aria_config.get_aria_config_service",
            return_value=mock_service,
        ),
        patch("src.api.routes.aria_config.get_current_user", return_value=mock_user),
    ):
        from src.api.routes.aria_config import get_aria_config

        result = await get_aria_config(mock_user)
        assert result["role"] == "sales_ops"
        mock_service.get_config.assert_awaited_once_with("user-test-123")


@pytest.mark.asyncio
async def test_update_aria_config(mock_user: MagicMock, default_config: dict) -> None:
    """PUT /aria-config saves and returns updated config."""
    updated = dict(default_config)
    updated["role"] = "bd_sales"
    mock_service = MagicMock()
    mock_service.update_config = AsyncMock(return_value=updated)

    with patch(
        "src.api.routes.aria_config.get_aria_config_service",
        return_value=mock_service,
    ):
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
    mock_service = MagicMock()
    mock_service.reset_personality = AsyncMock(return_value=default_config)

    with patch(
        "src.api.routes.aria_config.get_aria_config_service",
        return_value=mock_service,
    ):
        from src.api.routes.aria_config import reset_personality

        await reset_personality(mock_user)
        mock_service.reset_personality.assert_awaited_once_with("user-test-123")


@pytest.mark.asyncio
async def test_generate_preview(mock_user: MagicMock) -> None:
    """POST /aria-config/preview generates preview message."""
    mock_service = MagicMock()
    mock_service.generate_preview = AsyncMock(
        return_value={"preview_message": "Good morning.", "role_label": "BD/Sales"}
    )

    with patch(
        "src.api.routes.aria_config.get_aria_config_service",
        return_value=mock_service,
    ):
        from src.api.routes.aria_config import generate_preview
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
        result = await generate_preview(data, mock_user)
        assert result["preview_message"] == "Good morning."
        assert result["role_label"] == "BD/Sales"
