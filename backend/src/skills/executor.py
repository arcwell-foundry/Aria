"""Skill execution service for ARIA.

Orchestrates the full security pipeline for skill execution:
classify -> sanitize -> sandbox execute -> validate -> detokenize -> audit.
"""


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
