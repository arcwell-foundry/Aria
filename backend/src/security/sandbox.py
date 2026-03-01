"""Skill execution sandbox for ARIA security.

Provides isolated execution environment for skills with configurable
resource limits based on trust levels. Ensures untrusted skills cannot
access system resources or data beyond their permissions.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Final

from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)


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
        except TimeoutError:
            raise SandboxViolation(
                violation_type="timeout",
                message=f"Skill execution timed out after {config.timeout_seconds} seconds",
                details={"timeout_seconds": config.timeout_seconds},
            ) from None

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
        """Execute the skill via LLM with skill instructions as system prompt.

        Builds a prompt from skill_content (markdown/YAML instructions) and
        the sanitized input_data, calls the LLM, and returns parsed output.

        Args:
            skill_content: The skill's instruction content (markdown/text).
            input_data: The sanitized input data.

        Returns:
            Parsed JSON output from the LLM, or a dict with the raw text.
        """
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        llm = LLMClient()

        # Build system prompt from skill content
        system_prompt = (
            "You are executing a skill within ARIA, an AI assistant for "
            "life sciences commercial teams.\n\n"
            "SKILL INSTRUCTIONS:\n"
            f"{skill_content}\n\n"
            "IMPORTANT: Respond with valid JSON only. Your output will be "
            "parsed programmatically."
        )

        # Build user message from input data
        user_message = "Execute this skill with the following input:\n\n"
        for key, value in input_data.items():
            if isinstance(value, (dict, list)):
                user_message += f"## {key}\n```json\n{json.dumps(value, indent=2, default=str)}\n```\n\n"
            else:
                user_message += f"## {key}\n{value}\n\n"

        if not input_data:
            user_message += "(No specific input provided — use skill defaults.)\n"

        raw_response = await llm.generate_response(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=4096,
            task=TaskType.SKILL_EXECUTE,
            agent_id="skill_sandbox",
        )

        # Parse JSON response
        try:
            text = raw_response.strip()
            if text.startswith("```"):
                first_newline = text.index("\n")
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.debug("Skill output is not JSON, returning as text result")
            return {"result": raw_response, "format": "text"}

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
