"""Tests for salience configuration settings."""

from src.core.config import Settings


def test_salience_settings_have_defaults() -> None:
    """Test that salience settings have sensible defaults."""
    settings = Settings()

    assert settings.SALIENCE_HALF_LIFE_DAYS == 30
    assert settings.SALIENCE_ACCESS_BOOST == 0.1
    assert settings.SALIENCE_MIN == 0.01


def test_salience_settings_can_be_overridden() -> None:
    """Test that salience settings can be customized via env vars."""
    settings = Settings(
        SALIENCE_HALF_LIFE_DAYS=60,
        SALIENCE_ACCESS_BOOST=0.2,
        SALIENCE_MIN=0.05,
    )

    assert settings.SALIENCE_HALF_LIFE_DAYS == 60
    assert settings.SALIENCE_ACCESS_BOOST == 0.2
    assert settings.SALIENCE_MIN == 0.05
