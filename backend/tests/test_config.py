"""Tests for configuration settings."""

from src.core.config import Settings


def test_settings_has_openai_api_key() -> None:
    """Test that Settings includes OPENAI_API_KEY field."""
    settings = Settings()
    assert hasattr(settings, "OPENAI_API_KEY")
