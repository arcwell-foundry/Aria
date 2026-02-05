"""Skill execution service for ARIA.

Orchestrates the full security pipeline for skill execution:
classify -> sanitize -> sandbox execute -> validate -> detokenize -> audit.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from src.security.data_classification import DataClassifier
from src.security.sanitization import DataSanitizer
from src.security.sandbox import SkillSandbox
from src.security.skill_audit import SkillAuditService
from src.security.trust_levels import SkillTrustLevel
from src.skills.index import SkillIndex
from src.skills.installer import SkillInstaller


def _hash_data(data: Any) -> str:
    """Compute SHA256 hash of data for audit purposes.

    Uses deterministic JSON serialization with sorted keys.

    Args:
        data: Any data type to hash.

    Returns:
        64-character hex SHA256 hash string.
    """
    # Convert to deterministic string representation
    if data is None:
        canonical = "null"
    else:
        canonical = json.dumps(data, sort_keys=True, default=str)

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
