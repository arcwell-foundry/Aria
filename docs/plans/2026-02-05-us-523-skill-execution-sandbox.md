# US-523: Skill Execution Sandbox Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a secure sandbox system that isolates skill execution with configurable resource limits based on trust levels.

**Architecture:** SandboxConfig dataclass defines resource constraints (timeout, memory, CPU, network, file access). SANDBOX_BY_TRUST maps SkillTrustLevel to appropriate configs. SkillSandbox executes skills with timeout enforcement and tracks resource usage, returning SandboxResult with execution metrics.

**Tech Stack:** Python 3.11+, asyncio for timeout enforcement, dataclasses for config/result types

---

### Task 1: Create SandboxConfig dataclass

**Files:**
- Create: `backend/src/security/sandbox.py`
- Test: `backend/tests/test_sandbox.py`

**Step 1: Write the failing test for SandboxConfig**

Create `backend/tests/test_sandbox.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxConfig -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.security.sandbox'"

**Step 3: Write minimal implementation**

Create `backend/src/security/sandbox.py`:

```python
"""Skill execution sandbox for ARIA security.

Provides isolated execution environment for skills with configurable
resource limits based on trust levels. Ensures untrusted skills cannot
access system resources or data beyond their permissions.
"""

from dataclasses import dataclass, field


@dataclass
class SandboxConfig:
    """Configuration for skill execution sandbox.

    Defines resource limits and access permissions for skill execution.
    Different trust levels get different configs via SANDBOX_BY_TRUST.

    Attributes:
        timeout_seconds: Maximum execution time before termination.
        memory_limit_mb: Maximum memory usage in megabytes.
        cpu_limit_percent: Maximum CPU usage percentage (0-100).
        network_enabled: Whether network access is allowed.
        allowed_domains: Whitelist of domains if network is enabled.
        can_read_files: Whether skill can read files.
        can_write_files: Whether skill can write files.
        can_execute_code: Whether skill can execute arbitrary code.
    """

    timeout_seconds: int = 30
    memory_limit_mb: int = 256
    cpu_limit_percent: int = 25
    network_enabled: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    can_read_files: bool = False
    can_write_files: bool = False
    can_execute_code: bool = False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxConfig -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add SandboxConfig dataclass for skill isolation

US-523: Defines resource limits and access permissions for skill execution.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Create SANDBOX_BY_TRUST mapping

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing tests for SANDBOX_BY_TRUST**

Add to `backend/tests/test_sandbox.py`:

```python
class TestSandboxByTrust:
    """Tests for SANDBOX_BY_TRUST mapping."""

    def test_all_trust_levels_have_config(self) -> None:
        """Every SkillTrustLevel should have a sandbox config."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        for level in SkillTrustLevel:
            assert level in SANDBOX_BY_TRUST
            assert isinstance(SANDBOX_BY_TRUST[level], SandboxConfig)

    def test_core_has_most_permissive_config(self) -> None:
        """CORE trust level should have the most permissive config."""
        from src.security.sandbox import SANDBOX_BY_TRUST, SandboxConfig
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
        from src.security.sandbox import SANDBOX_BY_TRUST, SandboxConfig
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
        from src.security.sandbox import SANDBOX_BY_TRUST, SandboxConfig
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
        from src.security.sandbox import SANDBOX_BY_TRUST, SandboxConfig
        from src.security.trust_levels import SkillTrustLevel

        user_config = SANDBOX_BY_TRUST[SkillTrustLevel.USER]
        assert user_config.timeout_seconds == 60
        assert user_config.memory_limit_mb == 512
        assert user_config.cpu_limit_percent == 50
        assert user_config.network_enabled is False
        assert user_config.can_read_files is True
        assert user_config.can_write_files is True
        assert user_config.can_execute_code is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxByTrust -v`
Expected: FAIL with "cannot import name 'SANDBOX_BY_TRUST'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/sandbox.py` after SandboxConfig:

```python
from typing import Final

from src.security.trust_levels import SkillTrustLevel


# Sandbox configs by trust level - more trusted = more permissions
SANDBOX_BY_TRUST: Final[dict[SkillTrustLevel, SandboxConfig]] = {
    SkillTrustLevel.CORE: SandboxConfig(
        timeout_seconds=120,
        memory_limit_mb=1024,
        cpu_limit_percent=80,
        network_enabled=True,
        allowed_domains=[],  # Empty means all domains allowed for CORE
        can_read_files=True,
        can_write_files=True,
        can_execute_code=True,
    ),
    SkillTrustLevel.VERIFIED: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        cpu_limit_percent=50,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=True,
        can_write_files=True,
        can_execute_code=False,
    ),
    SkillTrustLevel.COMMUNITY: SandboxConfig(
        timeout_seconds=30,
        memory_limit_mb=256,
        cpu_limit_percent=25,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=False,
        can_write_files=False,
        can_execute_code=False,
    ),
    SkillTrustLevel.USER: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        cpu_limit_percent=50,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=True,
        can_write_files=True,
        can_execute_code=False,
    ),
}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxByTrust -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add SANDBOX_BY_TRUST mapping for trust-based limits

US-523: Maps each SkillTrustLevel to appropriate SandboxConfig.
CORE gets full access, COMMUNITY is most restricted.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Create SandboxViolation exception

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing test for SandboxViolation**

Add to `backend/tests/test_sandbox.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxViolation -v`
Expected: FAIL with "cannot import name 'SandboxViolation'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/sandbox.py`:

```python
from typing import Any


class SandboxViolation(Exception):
    """Exception raised when a skill violates sandbox constraints.

    Raised when a skill attempts to exceed resource limits or access
    restricted capabilities (network, files, code execution).

    Attributes:
        violation_type: Category of violation (timeout, memory, network, file, code).
        message: Human-readable description of the violation.
        details: Optional dict with additional violation details.
    """

    def __init__(
        self,
        violation_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize SandboxViolation.

        Args:
            violation_type: Category of violation.
            message: Human-readable description.
            details: Optional additional details.
        """
        self.violation_type = violation_type
        self.message = message
        self.details = details
        super().__init__(f"{violation_type}: {message}")
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxViolation -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add SandboxViolation exception for constraint breaches

US-523: Exception with type, message, and optional details for
tracking timeout, memory, network, and file access violations.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Create SandboxResult dataclass

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing test for SandboxResult**

Add to `backend/tests/test_sandbox.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxResult -v`
Expected: FAIL with "cannot import name 'SandboxResult'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/sandbox.py`:

```python
@dataclass
class SandboxResult:
    """Result of sandboxed skill execution.

    Contains the execution output along with resource usage metrics
    and any violations that occurred during execution.

    Attributes:
        output: The skill's output (any type).
        execution_time_ms: Time taken to execute in milliseconds.
        memory_used_mb: Peak memory usage during execution in megabytes.
        violations: List of SandboxViolation instances if any occurred.
        success: Whether execution completed without critical violations.
    """

    output: Any
    execution_time_ms: int
    memory_used_mb: float
    violations: list[SandboxViolation]
    success: bool
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSandboxResult -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add SandboxResult dataclass for execution metrics

US-523: Captures output, timing, memory usage, violations, and
success status from sandboxed skill execution.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Create SkillSandbox class with timeout enforcement

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing tests for SkillSandbox**

Add to `backend/tests/test_sandbox.py`:

```python
import asyncio


class TestSkillSandbox:
    """Tests for SkillSandbox class."""

    @pytest.mark.asyncio
    async def test_execute_returns_sandbox_result(self) -> None:
        """execute() should return a SandboxResult."""
        from src.security.sandbox import SandboxConfig, SandboxResult, SkillSandbox

        sandbox = SkillSandbox()
        config = SandboxConfig(timeout_seconds=5)

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox -v`
Expected: FAIL with "cannot import name 'SkillSandbox'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/sandbox.py`:

```python
import asyncio
import time


class SkillSandbox:
    """Executes skills in isolated sandbox with resource limits.

    Provides timeout enforcement, resource tracking, and access control
    for skill execution based on SandboxConfig settings.
    """

    async def execute(
        self,
        skill_content: str,
        input_data: dict[str, Any],
        config: SandboxConfig,
    ) -> SandboxResult:
        """Execute skill instructions in sandbox.

        Enforces timeout and tracks resource usage. Returns SandboxResult
        with output and metrics, or raises SandboxViolation on timeout.

        Args:
            skill_content: The skill's markdown/instruction content.
            input_data: Sanitized input data for the skill.
            config: SandboxConfig defining resource limits.

        Returns:
            SandboxResult with output, timing, and resource metrics.

        Raises:
            SandboxViolation: If execution exceeds timeout.
        """
        start_time = time.perf_counter()

        try:
            output = await asyncio.wait_for(
                self._execute_skill(skill_content, input_data),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise SandboxViolation(
                violation_type="timeout",
                message=f"Skill execution timed out after {config.timeout_seconds} seconds",
                details={"timeout_seconds": config.timeout_seconds},
            )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return SandboxResult(
            output=output,
            execution_time_ms=execution_time_ms,
            memory_used_mb=0.0,  # TODO: Implement memory tracking
            violations=[],
            success=True,
        )

    async def _execute_skill(
        self,
        skill_content: str,
        input_data: dict[str, Any],
    ) -> Any:
        """Execute the skill (placeholder for actual LLM-based execution).

        For LLM-based skills, this builds a prompt with skill instructions
        and sanitized input, then calls the LLM.

        Args:
            skill_content: The skill's instruction content.
            input_data: The sanitized input data.

        Returns:
            The skill's output.
        """
        # Placeholder implementation - actual execution would call LLM
        return {"status": "executed", "input_received": bool(input_data)}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add SkillSandbox with timeout enforcement

US-523: Executes skills with asyncio.wait_for timeout, tracks
execution time, returns SandboxResult with metrics.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add network access check to SkillSandbox

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing tests for network access check**

Add to `backend/tests/test_sandbox.py` in TestSkillSandbox class:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox::test_check_network_access_allowed -v`
Expected: FAIL with "AttributeError: 'SkillSandbox' object has no attribute 'check_network_access'"

**Step 3: Write minimal implementation**

Add to SkillSandbox class in `backend/src/security/sandbox.py`:

```python
    def check_network_access(self, config: SandboxConfig, domain: str) -> None:
        """Check if network access to a domain is permitted.

        Args:
            config: The sandbox configuration.
            domain: The domain being accessed.

        Raises:
            SandboxViolation: If network access is not permitted.
        """
        if not config.network_enabled:
            raise SandboxViolation(
                violation_type="network_access",
                message="Network access is not permitted for this skill",
                details={"requested_domain": domain},
            )

        # Empty whitelist means all domains allowed (for CORE skills)
        if config.allowed_domains and domain not in config.allowed_domains:
            raise SandboxViolation(
                violation_type="network_access",
                message=f"Domain '{domain}' is not in the allowed domains whitelist",
                details={
                    "requested_domain": domain,
                    "allowed_domains": config.allowed_domains,
                },
            )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox::test_check_network -v`
Expected: PASS (4 tests matching pattern)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add network access check to SkillSandbox

US-523: Validates network access against config.network_enabled
and config.allowed_domains whitelist before execution.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add file access check to SkillSandbox

**Files:**
- Modify: `backend/src/security/sandbox.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing tests for file access check**

Add to `backend/tests/test_sandbox.py` in TestSkillSandbox class:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox::test_check_file_access -v`
Expected: FAIL with "AttributeError: 'SkillSandbox' object has no attribute 'check_file_access'"

**Step 3: Write minimal implementation**

Add to SkillSandbox class in `backend/src/security/sandbox.py`:

```python
    def check_file_access(
        self,
        config: SandboxConfig,
        file_path: str,
        operation: str,
    ) -> None:
        """Check if file access is permitted.

        Args:
            config: The sandbox configuration.
            file_path: Path to the file being accessed.
            operation: Type of operation - "read" or "write".

        Raises:
            SandboxViolation: If file access is not permitted.
        """
        if operation == "read" and not config.can_read_files:
            raise SandboxViolation(
                violation_type="file_access",
                message="File read access is not permitted for this skill",
                details={"file_path": file_path, "operation": operation},
            )

        if operation == "write" and not config.can_write_files:
            raise SandboxViolation(
                violation_type="file_access",
                message="File write access is not permitted for this skill",
                details={"file_path": file_path, "operation": operation},
            )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestSkillSandbox::test_check_file_access -v`
Expected: PASS (4 tests matching pattern)

**Step 5: Commit**

```bash
git add backend/src/security/sandbox.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): add file access check to SkillSandbox

US-523: Validates read/write file operations against
config.can_read_files and config.can_write_files.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Update security module exports

**Files:**
- Modify: `backend/src/security/__init__.py`
- Modify: `backend/tests/test_sandbox.py`

**Step 1: Write the failing test for module exports**

Add to `backend/tests/test_sandbox.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestModuleExports -v`
Expected: FAIL with "cannot import name 'SandboxConfig' from 'src.security'"

**Step 3: Write minimal implementation**

Update `backend/src/security/__init__.py`:

```python
"""Security module for ARIA.

Provides data classification, trust levels, sanitization, sandboxing, and audit
capabilities for the skills integration system.
"""

from src.security.data_classification import (
    ClassifiedData,
    DataClass,
    DataClassifier,
)
from src.security.sandbox import (
    SANDBOX_BY_TRUST,
    SandboxConfig,
    SandboxResult,
    SandboxViolation,
    SkillSandbox,
)
from src.security.sanitization import (
    DataSanitizer,
    LeakageReport,
    TokenMap,
)
from src.security.trust_levels import (
    TRUST_DATA_ACCESS,
    TRUSTED_SKILL_SOURCES,
    SkillTrustLevel,
    can_access_data,
    determine_trust_level,
)

__all__ = [
    # Data classification
    "ClassifiedData",
    "DataClass",
    "DataClassifier",
    # Trust levels
    "SkillTrustLevel",
    "TRUST_DATA_ACCESS",
    "TRUSTED_SKILL_SOURCES",
    "determine_trust_level",
    "can_access_data",
    # Sanitization
    "TokenMap",
    "LeakageReport",
    "DataSanitizer",
    # Sandbox
    "SandboxConfig",
    "SandboxViolation",
    "SandboxResult",
    "SkillSandbox",
    "SANDBOX_BY_TRUST",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sandbox.py::TestModuleExports -v`
Expected: PASS (1 test)

**Step 5: Commit**

```bash
git add backend/src/security/__init__.py backend/tests/test_sandbox.py
git commit -m "$(cat <<'EOF'
feat(security): export sandbox types from security module

US-523: Adds SandboxConfig, SandboxViolation, SandboxResult,
SkillSandbox, and SANDBOX_BY_TRUST to public exports.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Run full test suite and verify

**Files:**
- None (verification only)

**Step 1: Run all sandbox tests**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: All tests pass (approximately 22 tests)

**Step 2: Run mypy type check**

Run: `cd backend && python -m mypy src/security/sandbox.py --strict`
Expected: Success with no errors

**Step 3: Run ruff linting**

Run: `cd backend && python -m ruff check src/security/sandbox.py`
Expected: No issues found

**Step 4: Run ruff formatting**

Run: `cd backend && python -m ruff format src/security/sandbox.py --check`
Expected: File formatted correctly (or format if needed)

**Step 5: Commit final verification**

If any formatting was needed:
```bash
cd backend && python -m ruff format src/security/sandbox.py
git add backend/src/security/sandbox.py
git commit -m "$(cat <<'EOF'
style(security): format sandbox module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Final File: backend/src/security/sandbox.py

After all tasks, the complete file should look like:

```python
"""Skill execution sandbox for ARIA security.

Provides isolated execution environment for skills with configurable
resource limits based on trust levels. Ensures untrusted skills cannot
access system resources or data beyond their permissions.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Final

from src.security.trust_levels import SkillTrustLevel


@dataclass
class SandboxConfig:
    """Configuration for skill execution sandbox.

    Defines resource limits and access permissions for skill execution.
    Different trust levels get different configs via SANDBOX_BY_TRUST.

    Attributes:
        timeout_seconds: Maximum execution time before termination.
        memory_limit_mb: Maximum memory usage in megabytes.
        cpu_limit_percent: Maximum CPU usage percentage (0-100).
        network_enabled: Whether network access is allowed.
        allowed_domains: Whitelist of domains if network is enabled.
        can_read_files: Whether skill can read files.
        can_write_files: Whether skill can write files.
        can_execute_code: Whether skill can execute arbitrary code.
    """

    timeout_seconds: int = 30
    memory_limit_mb: int = 256
    cpu_limit_percent: int = 25
    network_enabled: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    can_read_files: bool = False
    can_write_files: bool = False
    can_execute_code: bool = False


# Sandbox configs by trust level - more trusted = more permissions
SANDBOX_BY_TRUST: Final[dict[SkillTrustLevel, SandboxConfig]] = {
    SkillTrustLevel.CORE: SandboxConfig(
        timeout_seconds=120,
        memory_limit_mb=1024,
        cpu_limit_percent=80,
        network_enabled=True,
        allowed_domains=[],  # Empty means all domains allowed for CORE
        can_read_files=True,
        can_write_files=True,
        can_execute_code=True,
    ),
    SkillTrustLevel.VERIFIED: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        cpu_limit_percent=50,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=True,
        can_write_files=True,
        can_execute_code=False,
    ),
    SkillTrustLevel.COMMUNITY: SandboxConfig(
        timeout_seconds=30,
        memory_limit_mb=256,
        cpu_limit_percent=25,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=False,
        can_write_files=False,
        can_execute_code=False,
    ),
    SkillTrustLevel.USER: SandboxConfig(
        timeout_seconds=60,
        memory_limit_mb=512,
        cpu_limit_percent=50,
        network_enabled=False,
        allowed_domains=[],
        can_read_files=True,
        can_write_files=True,
        can_execute_code=False,
    ),
}


class SandboxViolation(Exception):
    """Exception raised when a skill violates sandbox constraints.

    Raised when a skill attempts to exceed resource limits or access
    restricted capabilities (network, files, code execution).

    Attributes:
        violation_type: Category of violation (timeout, memory, network, file, code).
        message: Human-readable description of the violation.
        details: Optional dict with additional violation details.
    """

    def __init__(
        self,
        violation_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize SandboxViolation.

        Args:
            violation_type: Category of violation.
            message: Human-readable description.
            details: Optional additional details.
        """
        self.violation_type = violation_type
        self.message = message
        self.details = details
        super().__init__(f"{violation_type}: {message}")


@dataclass
class SandboxResult:
    """Result of sandboxed skill execution.

    Contains the execution output along with resource usage metrics
    and any violations that occurred during execution.

    Attributes:
        output: The skill's output (any type).
        execution_time_ms: Time taken to execute in milliseconds.
        memory_used_mb: Peak memory usage during execution in megabytes.
        violations: List of SandboxViolation instances if any occurred.
        success: Whether execution completed without critical violations.
    """

    output: Any
    execution_time_ms: int
    memory_used_mb: float
    violations: list[SandboxViolation]
    success: bool


class SkillSandbox:
    """Executes skills in isolated sandbox with resource limits.

    Provides timeout enforcement, resource tracking, and access control
    for skill execution based on SandboxConfig settings.
    """

    async def execute(
        self,
        skill_content: str,
        input_data: dict[str, Any],
        config: SandboxConfig,
    ) -> SandboxResult:
        """Execute skill instructions in sandbox.

        Enforces timeout and tracks resource usage. Returns SandboxResult
        with output and metrics, or raises SandboxViolation on timeout.

        Args:
            skill_content: The skill's markdown/instruction content.
            input_data: Sanitized input data for the skill.
            config: SandboxConfig defining resource limits.

        Returns:
            SandboxResult with output, timing, and resource metrics.

        Raises:
            SandboxViolation: If execution exceeds timeout.
        """
        start_time = time.perf_counter()

        try:
            output = await asyncio.wait_for(
                self._execute_skill(skill_content, input_data),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise SandboxViolation(
                violation_type="timeout",
                message=f"Skill execution timed out after {config.timeout_seconds} seconds",
                details={"timeout_seconds": config.timeout_seconds},
            )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return SandboxResult(
            output=output,
            execution_time_ms=execution_time_ms,
            memory_used_mb=0.0,  # TODO: Implement memory tracking
            violations=[],
            success=True,
        )

    async def _execute_skill(
        self,
        skill_content: str,
        input_data: dict[str, Any],
    ) -> Any:
        """Execute the skill (placeholder for actual LLM-based execution).

        For LLM-based skills, this builds a prompt with skill instructions
        and sanitized input, then calls the LLM.

        Args:
            skill_content: The skill's instruction content.
            input_data: The sanitized input data.

        Returns:
            The skill's output.
        """
        # Placeholder implementation - actual execution would call LLM
        return {"status": "executed", "input_received": bool(input_data)}

    def check_network_access(self, config: SandboxConfig, domain: str) -> None:
        """Check if network access to a domain is permitted.

        Args:
            config: The sandbox configuration.
            domain: The domain being accessed.

        Raises:
            SandboxViolation: If network access is not permitted.
        """
        if not config.network_enabled:
            raise SandboxViolation(
                violation_type="network_access",
                message="Network access is not permitted for this skill",
                details={"requested_domain": domain},
            )

        # Empty whitelist means all domains allowed (for CORE skills)
        if config.allowed_domains and domain not in config.allowed_domains:
            raise SandboxViolation(
                violation_type="network_access",
                message=f"Domain '{domain}' is not in the allowed domains whitelist",
                details={
                    "requested_domain": domain,
                    "allowed_domains": config.allowed_domains,
                },
            )

    def check_file_access(
        self,
        config: SandboxConfig,
        file_path: str,
        operation: str,
    ) -> None:
        """Check if file access is permitted.

        Args:
            config: The sandbox configuration.
            file_path: Path to the file being accessed.
            operation: Type of operation - "read" or "write".

        Raises:
            SandboxViolation: If file access is not permitted.
        """
        if operation == "read" and not config.can_read_files:
            raise SandboxViolation(
                violation_type="file_access",
                message="File read access is not permitted for this skill",
                details={"file_path": file_path, "operation": operation},
            )

        if operation == "write" and not config.can_write_files:
            raise SandboxViolation(
                violation_type="file_access",
                message="File write access is not permitted for this skill",
                details={"file_path": file_path, "operation": operation},
            )
```

---

Plan complete and saved to `docs/plans/2026-02-05-us-523-skill-execution-sandbox.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
