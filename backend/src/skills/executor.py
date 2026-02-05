"""Skill execution service for ARIA.

Orchestrates the full security pipeline for skill execution:
classify -> sanitize -> sandbox execute -> validate -> detokenize -> audit.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from src.security.data_classification import DataClassifier
from src.security.sandbox import SANDBOX_BY_TRUST, SandboxViolation, SkillSandbox
from src.security.sanitization import DataSanitizer
from src.security.skill_audit import SkillAuditEntry, SkillAuditService
from src.security.trust_levels import SkillTrustLevel
from src.skills.index import SkillIndex
from src.skills.installer import SkillInstaller

logger = logging.getLogger(__name__)


def _hash_data(data: Any) -> str:
    """Compute SHA256 hash of data for audit purposes.

    Uses deterministic JSON serialization with sorted keys.

    Args:
        data: Any data type to hash.

    Returns:
        64-character hex SHA256 hash string.
    """
    # Convert to deterministic string representation
    canonical = "null" if data is None else json.dumps(data, sort_keys=True, default=str)

    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class SkillExecution:
    """Result of a skill execution through the security pipeline.

    Captures all metadata about the execution including sanitization,
    timing, and results for audit purposes.

    Attributes:
        skill_id: Unique identifier for the skill.
        skill_path: Path/identifier of the skill (e.g., "anthropics/skills/pdf").
        trust_level: Trust level of the skill at execution time.
        input_hash: SHA256 hash of input data for audit verification.
        output_hash: SHA256 hash of output data (None if execution failed).
        sanitized: Whether input data was sanitized before execution.
        tokens_used: List of tokens that replaced sensitive data.
        execution_time_ms: Execution duration in milliseconds.
        success: Whether the execution completed successfully.
        result: The skill's output (any type), or None if failed.
        error: Error message if execution failed, None otherwise.
    """

    skill_id: str
    skill_path: str
    trust_level: SkillTrustLevel
    input_hash: str
    output_hash: str | None
    sanitized: bool
    tokens_used: list[str]
    execution_time_ms: int
    success: bool
    result: Any
    error: str | None


class SkillExecutionError(Exception):
    """Exception raised when skill execution fails.

    Attributes:
        message: Human-readable error description.
        skill_id: Optional ID of the skill that failed.
        stage: Optional pipeline stage where failure occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        skill_id: str | None = None,
        stage: str | None = None,
    ) -> None:
        """Initialize SkillExecutionError.

        Args:
            message: Human-readable error description.
            skill_id: Optional ID of the skill that failed.
            stage: Optional pipeline stage (classify, sanitize, execute, validate).
        """
        self.skill_id = skill_id
        self.stage = stage
        super().__init__(message)


class SkillExecutor:
    """Executes skills through the complete security pipeline.

    Orchestrates: classify -> sanitize -> sandbox execute -> validate -> detokenize -> audit.

    All skill executions go through this service to ensure proper
    data protection and audit logging.
    """

    def __init__(
        self,
        classifier: DataClassifier,
        sanitizer: DataSanitizer,
        sandbox: SkillSandbox,
        index: SkillIndex,
        installer: SkillInstaller,
        audit_service: SkillAuditService,
    ) -> None:
        """Initialize SkillExecutor with all required dependencies.

        Args:
            classifier: DataClassifier for input data classification.
            sanitizer: DataSanitizer for tokenization/redaction.
            sandbox: SkillSandbox for isolated execution.
            index: SkillIndex for skill lookup.
            installer: SkillInstaller for checking installation status.
            audit_service: SkillAuditService for audit logging.
        """
        self._classifier = classifier
        self._sanitizer = sanitizer
        self._sandbox = sandbox
        self._index = index
        self._installer = installer
        self._audit = audit_service

    async def execute(
        self,
        user_id: str,
        skill_id: str,
        input_data: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        trigger_reason: str = "user_request",
    ) -> SkillExecution:
        """Execute a skill through the security pipeline.

        Pipeline: lookup → classify → sanitize → sandbox execute → validate → detokenize → audit

        Args:
            user_id: ID of the user requesting execution.
            skill_id: ID of the skill to execute.
            input_data: Input data to pass to the skill.
            context: Optional context for data classification.
            task_id: Optional task ID for audit trail.
            agent_id: Optional agent ID for audit trail.
            trigger_reason: Reason for execution (for audit).

        Returns:
            SkillExecution with results and metadata.

        Raises:
            SkillExecutionError: If skill not found, not installed, or execution fails.
        """
        if context is None:
            context = {}

        # Phase 1: Skill lookup
        skill_entry = await self._index.get_skill(skill_id)
        if skill_entry is None:
            raise SkillExecutionError(
                f"Skill '{skill_id}' not found in index",
                skill_id=skill_id,
                stage="lookup",
            )

        # Check if installed for user
        is_installed = await self._installer.is_installed(user_id, skill_id)
        if not is_installed:
            raise SkillExecutionError(
                f"Skill '{skill_id}' is not installed for user '{user_id}'",
                skill_id=skill_id,
                stage="lookup",
            )

        trust_level = skill_entry.trust_level
        input_hash = _hash_data(input_data)

        # Initialize variables for audit
        output_hash: str | None = None
        sanitized = False
        tokens_used: list[str] = []
        execution_time_ms = 0
        success = False
        result: Any = None
        error_msg: str | None = None
        security_flags: list[str] = []

        try:
            # Phase 2: Sanitize input
            sanitized_data, token_map = await self._sanitizer.sanitize(
                input_data, trust_level, context
            )
            sanitized = len(token_map.tokens) > 0
            tokens_used = list(token_map.tokens.keys())

            # Phase 3: Execute in sandbox
            sandbox_config = SANDBOX_BY_TRUST[trust_level]
            sandbox_result = await self._sandbox.execute(
                skill_content=skill_entry.full_content or "",
                input_data=sanitized_data,
                config=sandbox_config,
            )

            execution_time_ms = sandbox_result.execution_time_ms
            raw_output = sandbox_result.output
            success = sandbox_result.success

            # Phase 4: Validate output for leakage (log but don't fail)
            leakage_report = self._sanitizer.validate_output(raw_output, token_map)
            if leakage_report.leaked:
                logger.warning(
                    "Data leakage detected in skill output",
                    extra={
                        "skill_id": skill_id,
                        "user_id": user_id,
                        "leaked_count": len(leakage_report.leaked_values),
                        "severity": leakage_report.severity,
                    },
                )
                security_flags.append(f"leakage:{leakage_report.severity}")

            # Phase 5: Detokenize output
            result = self._sanitizer.detokenize(raw_output, token_map)
            output_hash = _hash_data(result)

        except SandboxViolation as e:
            error_msg = str(e)
            success = False
            security_flags.append(f"violation:{e.violation_type}")
            logger.warning(
                "Sandbox violation during skill execution",
                extra={
                    "skill_id": skill_id,
                    "user_id": user_id,
                    "violation_type": e.violation_type,
                },
            )

        except Exception as e:
            error_msg = str(e)
            success = False
            logger.exception(
                "Error during skill execution",
                extra={"skill_id": skill_id, "user_id": user_id},
            )

        # Phase 6: Log audit entry (always, even on failure)
        previous_hash = await self._audit.get_latest_hash(user_id)
        audit_entry_data = {
            "user_id": user_id,
            "skill_id": skill_id,
            "skill_path": skill_entry.skill_path,
            "skill_trust_level": trust_level.value,
            "trigger_reason": trigger_reason,
            "data_classes_requested": [],  # Could be enhanced to track actual classes
            "data_classes_granted": [],
            "input_hash": input_hash,
            "output_hash": output_hash,
            "execution_time_ms": execution_time_ms,
            "success": success,
            "error": error_msg,
            "data_redacted": sanitized,
            "tokens_used": tokens_used,
            "task_id": task_id,
            "agent_id": agent_id,
            "security_flags": security_flags,
        }
        entry_hash = self._audit._compute_hash(audit_entry_data, previous_hash)

        audit_entry = SkillAuditEntry(
            user_id=user_id,
            skill_id=skill_id,
            skill_path=skill_entry.skill_path,
            skill_trust_level=trust_level.value,
            trigger_reason=trigger_reason,
            data_classes_requested=[],
            data_classes_granted=[],
            input_hash=input_hash,
            output_hash=output_hash,
            execution_time_ms=execution_time_ms,
            success=success,
            error=error_msg,
            data_redacted=sanitized,
            tokens_used=tokens_used,
            task_id=task_id,
            agent_id=agent_id,
            security_flags=security_flags,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )

        await self._audit.log_execution(audit_entry)

        # Record usage on success
        if success:
            await self._installer.record_usage(user_id, skill_id, success=True)
        else:
            await self._installer.record_usage(user_id, skill_id, success=False)

        return SkillExecution(
            skill_id=skill_id,
            skill_path=skill_entry.skill_path,
            trust_level=trust_level,
            input_hash=input_hash,
            output_hash=output_hash,
            sanitized=sanitized,
            tokens_used=tokens_used,
            execution_time_ms=execution_time_ms,
            success=success,
            result=result,
            error=error_msg,
        )
