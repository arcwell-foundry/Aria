"""Skill execution sandbox for ARIA security.

Provides isolated execution environment for skills with configurable
resource limits based on trust levels. Ensures untrusted skills cannot
access system resources or data beyond their permissions.
"""

from dataclasses import dataclass, field
from typing import Any, Final

from src.security.trust_levels import SkillTrustLevel


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
