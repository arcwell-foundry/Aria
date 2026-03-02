"""Tests for Thesys C1 configuration."""
import os
from unittest.mock import patch


# Suppress env file loading by clearing THESYS_ vars from the environment
# during test. Pydantic-settings merges env file + env vars + explicit kwargs,
# so we patch the env to isolate each test.

_CLEAN_ENV = {
    k: v for k, v in os.environ.items()
    if not k.startswith("THESYS_")
}


class TestThesysConfig:
    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_thesys_disabled_by_default(self) -> None:
        from src.core.config import Settings

        s = Settings(
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="sk",
            ANTHROPIC_API_KEY="ak",
            APP_SECRET_KEY="a" * 32,
            _env_file=None,
        )
        assert s.THESYS_ENABLED is False

    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_thesys_configured_false_when_disabled(self) -> None:
        from src.core.config import Settings

        s = Settings(
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="sk",
            ANTHROPIC_API_KEY="ak",
            APP_SECRET_KEY="a" * 32,
            THESYS_API_KEY="some-key",
            _env_file=None,
        )
        assert s.thesys_configured is False

    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_thesys_configured_true_when_enabled_and_keyed(self) -> None:
        from src.core.config import Settings

        s = Settings(
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="sk",
            ANTHROPIC_API_KEY="ak",
            APP_SECRET_KEY="a" * 32,
            THESYS_ENABLED=True,
            THESYS_API_KEY="thesys-key-123",
            _env_file=None,
        )
        assert s.thesys_configured is True

    @patch.dict(os.environ, _CLEAN_ENV, clear=True)
    def test_thesys_configured_false_when_key_empty(self) -> None:
        from src.core.config import Settings

        s = Settings(
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="sk",
            ANTHROPIC_API_KEY="ak",
            APP_SECRET_KEY="a" * 32,
            THESYS_ENABLED=True,
            THESYS_API_KEY="",
            _env_file=None,
        )
        assert s.thesys_configured is False
