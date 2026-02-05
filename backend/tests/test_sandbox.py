"""Unit tests for skill execution sandbox."""

import pytest


class TestSandboxConfig:
    """Tests for SandboxConfig dataclass."""

    def test_sandbox_config_default_values(self) -> None:
        """SandboxConfig should have sensible defaults."""
        from src.security.sandbox import SandboxConfig

        config = SandboxConfig()
        assert config.timeout_seconds == 30
        assert config.memory_limit_mb == 256
        assert config.cpu_limit_percent == 25
        assert config.network_enabled is False
        assert config.allowed_domains == []
        assert config.can_read_files is False
        assert config.can_write_files is False
        assert config.can_execute_code is False

    def test_sandbox_config_custom_values(self) -> None:
        """SandboxConfig should accept custom values."""
        from src.security.sandbox import SandboxConfig

        config = SandboxConfig(
            timeout_seconds=120,
            memory_limit_mb=1024,
            cpu_limit_percent=80,
            network_enabled=True,
            allowed_domains=["api.example.com"],
            can_read_files=True,
            can_write_files=True,
            can_execute_code=True,
        )
        assert config.timeout_seconds == 120
        assert config.memory_limit_mb == 1024
        assert config.cpu_limit_percent == 80
        assert config.network_enabled is True
        assert config.allowed_domains == ["api.example.com"]
        assert config.can_read_files is True
        assert config.can_write_files is True
        assert config.can_execute_code is True
