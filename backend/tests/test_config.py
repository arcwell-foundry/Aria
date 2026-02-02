"""Tests for configuration settings."""

import pytest

from src.core.config import Settings


def test_settings_has_openai_api_key() -> None:
    """Test that Settings includes OPENAI_API_KEY field."""
    settings = Settings()
    assert hasattr(settings, "OPENAI_API_KEY")


def test_confidence_settings_defaults() -> None:
    """Test confidence configuration has correct default values."""
    settings = Settings()

    # Decay: 5% per month = 0.05/30 per day
    assert pytest.approx(0.05 / 30) == settings.CONFIDENCE_DECAY_RATE_PER_DAY
    # Boost per corroboration
    assert settings.CONFIDENCE_CORROBORATION_BOOST == 0.10
    # Maximum confidence
    assert settings.CONFIDENCE_MAX == 0.99
    # Minimum threshold for including facts in responses
    assert settings.CONFIDENCE_MIN_THRESHOLD == 0.3
    # Refresh window (days) - facts confirmed within this period don't decay
    assert settings.CONFIDENCE_REFRESH_WINDOW_DAYS == 7
