"""Tests for configuration settings."""

import os
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


def test_validate_startup_with_all_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup passes when all required secrets are set."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")

    settings = Settings()
    # Should not raise
    settings.validate_startup()


def test_validate_startup_with_missing_supabase_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup fails when SUPABASE_URL is missing."""
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")

    settings = Settings()
    with pytest.raises(ValueError, match="Required secrets are missing or empty.*SUPABASE_URL"):
        settings.validate_startup()


def test_validate_startup_with_missing_service_role_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup fails when SUPABASE_SERVICE_ROLE_KEY is missing."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")

    settings = Settings()
    with pytest.raises(ValueError, match="Required secrets are missing or empty.*SUPABASE_SERVICE_ROLE_KEY"):
        settings.validate_startup()


def test_validate_startup_with_missing_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup fails when ANTHROPIC_API_KEY is missing."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")

    settings = Settings()
    with pytest.raises(ValueError, match="Required secrets are missing or empty.*ANTHROPIC_API_KEY"):
        settings.validate_startup()


def test_validate_startup_with_missing_app_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup fails when APP_SECRET_KEY is missing."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("APP_SECRET_KEY", "")

    settings = Settings()
    with pytest.raises(ValueError, match="Required secrets are missing or empty.*APP_SECRET_KEY"):
        settings.validate_startup()


def test_validate_startup_with_multiple_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_startup fails when multiple secrets are missing."""
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("APP_SECRET_KEY", "")

    settings = Settings()
    with pytest.raises(ValueError, match="Required secrets are missing or empty"):
        settings.validate_startup()
