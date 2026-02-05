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


class TestSandboxByTrust:
    """Tests for SANDBOX_BY_TRUST mapping."""

    def test_all_trust_levels_have_config(self) -> None:
        """Every SkillTrustLevel should have a sandbox config."""
        from src.security.sandbox import SANDBOX_BY_TRUST, SandboxConfig
        from src.security.trust_levels import SkillTrustLevel

        for level in SkillTrustLevel:
            assert level in SANDBOX_BY_TRUST
            assert isinstance(SANDBOX_BY_TRUST[level], SandboxConfig)

    def test_core_has_most_permissive_config(self) -> None:
        """CORE trust level should have the most permissive config."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        core_config = SANDBOX_BY_TRUST[SkillTrustLevel.CORE]
        assert core_config.timeout_seconds == 120
        assert core_config.memory_limit_mb == 1024
        assert core_config.cpu_limit_percent == 80
        assert core_config.network_enabled is True
        assert core_config.can_read_files is True
        assert core_config.can_write_files is True
        assert core_config.can_execute_code is True

    def test_verified_has_moderate_config(self) -> None:
        """VERIFIED trust level should have moderate permissions."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        verified_config = SANDBOX_BY_TRUST[SkillTrustLevel.VERIFIED]
        assert verified_config.timeout_seconds == 60
        assert verified_config.memory_limit_mb == 512
        assert verified_config.cpu_limit_percent == 50
        assert verified_config.network_enabled is False
        assert verified_config.can_read_files is True
        assert verified_config.can_write_files is True
        assert verified_config.can_execute_code is False

    def test_community_has_most_restrictive_config(self) -> None:
        """COMMUNITY trust level should have the most restrictive config."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        community_config = SANDBOX_BY_TRUST[SkillTrustLevel.COMMUNITY]
        assert community_config.timeout_seconds == 30
        assert community_config.memory_limit_mb == 256
        assert community_config.cpu_limit_percent == 25
        assert community_config.network_enabled is False
        assert community_config.can_read_files is False
        assert community_config.can_write_files is False
        assert community_config.can_execute_code is False

    def test_user_has_moderate_config(self) -> None:
        """USER trust level should have moderate permissions like VERIFIED."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        user_config = SANDBOX_BY_TRUST[SkillTrustLevel.USER]
        assert user_config.timeout_seconds == 60
        assert user_config.memory_limit_mb == 512
        assert user_config.cpu_limit_percent == 50
        assert user_config.network_enabled is False
        assert user_config.can_read_files is True
        assert user_config.can_write_files is True
        assert user_config.can_execute_code is False


class TestSandboxViolation:
    """Tests for SandboxViolation exception."""

    def test_sandbox_violation_is_exception(self) -> None:
        """SandboxViolation should be an Exception subclass."""
        from src.security.sandbox import SandboxViolation

        assert issubclass(SandboxViolation, Exception)

    def test_sandbox_violation_stores_details(self) -> None:
        """SandboxViolation should store violation details."""
        from src.security.sandbox import SandboxViolation

        violation = SandboxViolation(
            violation_type="timeout",
            message="Execution exceeded 30 second limit",
            details={"elapsed_seconds": 35, "limit_seconds": 30},
        )
        assert violation.violation_type == "timeout"
        assert violation.message == "Execution exceeded 30 second limit"
        assert violation.details == {"elapsed_seconds": 35, "limit_seconds": 30}
        assert str(violation) == "timeout: Execution exceeded 30 second limit"

    def test_sandbox_violation_optional_details(self) -> None:
        """SandboxViolation should work without details."""
        from src.security.sandbox import SandboxViolation

        violation = SandboxViolation(
            violation_type="network_access",
            message="Network access not permitted",
        )
        assert violation.violation_type == "network_access"
        assert violation.details is None


class TestSandboxResult:
    """Tests for SandboxResult dataclass."""

    def test_sandbox_result_success(self) -> None:
        """SandboxResult should store successful execution details."""
        from src.security.sandbox import SandboxResult

        result = SandboxResult(
            output={"analysis": "complete"},
            execution_time_ms=150,
            memory_used_mb=45.5,
            violations=[],
            success=True,
        )
        assert result.output == {"analysis": "complete"}
        assert result.execution_time_ms == 150
        assert result.memory_used_mb == 45.5
        assert result.violations == []
        assert result.success is True

    def test_sandbox_result_with_violations(self) -> None:
        """SandboxResult should store violations when execution fails."""
        from src.security.sandbox import SandboxResult, SandboxViolation

        violation = SandboxViolation("network_access", "Attempted to access blocked domain")
        result = SandboxResult(
            output=None,
            execution_time_ms=50,
            memory_used_mb=12.3,
            violations=[violation],
            success=False,
        )
        assert result.output is None
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "network_access"
        assert result.success is False

    def test_sandbox_result_any_output_type(self) -> None:
        """SandboxResult output should accept any type."""
        from src.security.sandbox import SandboxResult

        # String output
        result_str = SandboxResult(
            output="text output",
            execution_time_ms=10,
            memory_used_mb=1.0,
            violations=[],
            success=True,
        )
        assert result_str.output == "text output"

        # List output
        result_list = SandboxResult(
            output=["item1", "item2"],
            execution_time_ms=20,
            memory_used_mb=2.0,
            violations=[],
            success=True,
        )
        assert result_list.output == ["item1", "item2"]
