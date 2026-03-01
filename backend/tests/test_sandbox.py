"""Unit tests for skill execution sandbox."""

import asyncio

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


class TestSkillSandbox:
    """Tests for SkillSandbox class."""

    @pytest.mark.asyncio
    async def test_execute_returns_sandbox_result(self) -> None:
        """execute() should return a SandboxResult."""
        from src.security.sandbox import SandboxConfig, SandboxResult, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(timeout_seconds=5)

        # Mock _execute_skill to avoid LLM dependency
        async def mock_execution(skill_content: str, input_data: dict) -> dict:
            return {"result": "executed", "input_received": bool(input_data)}

        sandbox._execute_skill = mock_execution  # type: ignore

        result = await sandbox.execute(
            skill_content="Test skill content",
            input_data={"query": "test"},
            config=config,
        )

        assert isinstance(result, SandboxResult)
        assert result.success is True
        assert result.execution_time_ms >= 0
        assert result.memory_used_mb >= 0

    @pytest.mark.asyncio
    async def test_execute_enforces_timeout(self) -> None:
        """execute() should raise SandboxViolation on timeout."""
        from src.security.sandbox import SandboxConfig, SandboxViolation, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(timeout_seconds=1)

        # Create a skill execution that takes too long
        async def slow_execution(skill_content: str, input_data: dict) -> dict:
            await asyncio.sleep(5)  # Sleep longer than timeout
            return {"result": "done"}

        sandbox._execute_skill = slow_execution  # type: ignore

        with pytest.raises(SandboxViolation) as exc_info:
            await sandbox.execute(
                skill_content="Slow skill",
                input_data={},
                config=config,
            )

        assert exc_info.value.violation_type == "timeout"
        assert "1" in exc_info.value.message  # Should mention the timeout duration

    @pytest.mark.asyncio
    async def test_execute_tracks_execution_time(self) -> None:
        """execute() should track execution time in milliseconds."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(timeout_seconds=5)

        # Create a skill execution with known duration
        async def timed_execution(skill_content: str, input_data: dict) -> dict:
            await asyncio.sleep(0.1)  # 100ms
            return {"result": "done"}

        sandbox._execute_skill = timed_execution  # type: ignore

        result = await sandbox.execute(
            skill_content="Timed skill",
            input_data={},
            config=config,
        )

        # Should be at least 100ms, with some tolerance
        assert result.execution_time_ms >= 90
        assert result.execution_time_ms < 500  # Shouldn't be too long

    @pytest.mark.asyncio
    async def test_execute_returns_output(self) -> None:
        """execute() should return skill output in result."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(timeout_seconds=5)

        expected_output = {"analysis": "complete", "score": 95}

        async def output_execution(skill_content: str, input_data: dict) -> dict:
            return expected_output

        sandbox._execute_skill = output_execution  # type: ignore

        result = await sandbox.execute(
            skill_content="Output skill",
            input_data={},
            config=config,
        )

        assert result.output == expected_output

    @pytest.mark.asyncio
    async def test_check_network_access_allowed(self) -> None:
        """check_network_access should pass when network is enabled."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(network_enabled=True, allowed_domains=["api.example.com"])

        # Should not raise
        sandbox.check_network_access(config, "api.example.com")

    @pytest.mark.asyncio
    async def test_check_network_access_denied_when_disabled(self) -> None:
        """check_network_access should raise when network is disabled."""
        from src.security.sandbox import SandboxConfig, SandboxViolation, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(network_enabled=False)

        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.check_network_access(config, "api.example.com")

        assert exc_info.value.violation_type == "network_access"

    @pytest.mark.asyncio
    async def test_check_network_access_denied_for_unlisted_domain(self) -> None:
        """check_network_access should raise for domains not in whitelist."""
        from src.security.sandbox import SandboxConfig, SandboxViolation, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(
            network_enabled=True,
            allowed_domains=["api.example.com", "data.example.com"],
        )

        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.check_network_access(config, "evil.attacker.com")

        assert exc_info.value.violation_type == "network_access"
        assert "evil.attacker.com" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_check_network_access_empty_whitelist_allows_all(self) -> None:
        """Empty allowed_domains with network_enabled should allow all domains."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(network_enabled=True, allowed_domains=[])

        # Should not raise - empty whitelist means all allowed
        sandbox.check_network_access(config, "any-domain.com")

    def test_check_file_access_read_allowed(self) -> None:
        """check_file_access should pass for read when can_read_files is True."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(can_read_files=True)

        # Should not raise
        sandbox.check_file_access(config, "/path/to/file.txt", "read")

    def test_check_file_access_read_denied(self) -> None:
        """check_file_access should raise for read when can_read_files is False."""
        from src.security.sandbox import SandboxConfig, SandboxViolation, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(can_read_files=False)

        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.check_file_access(config, "/path/to/file.txt", "read")

        assert exc_info.value.violation_type == "file_access"

    def test_check_file_access_write_allowed(self) -> None:
        """check_file_access should pass for write when can_write_files is True."""
        from src.security.sandbox import SandboxConfig, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(can_write_files=True)

        # Should not raise
        sandbox.check_file_access(config, "/path/to/output.txt", "write")

    def test_check_file_access_write_denied(self) -> None:
        """check_file_access should raise for write when can_write_files is False."""
        from src.security.sandbox import SandboxConfig, SandboxViolation, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(can_write_files=False)

        with pytest.raises(SandboxViolation) as exc_info:
            sandbox.check_file_access(config, "/path/to/output.txt", "write")

        assert exc_info.value.violation_type == "file_access"
        assert "write" in exc_info.value.message.lower()


class TestModuleExports:
    """Tests for security module exports."""

    def test_sandbox_exports_from_security_module(self) -> None:
        """All sandbox types should be importable from src.security."""
        from src.security import (
            SANDBOX_BY_TRUST,
            SandboxConfig,
            SandboxResult,
            SandboxViolation,
            SkillSandbox,
        )

        assert SandboxConfig is not None
        assert SandboxViolation is not None
        assert SandboxResult is not None
        assert SkillSandbox is not None
        assert SANDBOX_BY_TRUST is not None
