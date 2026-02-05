"""Tests for skill executor service."""

from src.skills.executor import SkillExecutionError


class TestSkillExecutionError:
    """Tests for SkillExecutionError exception class."""

    def test_skill_execution_error_is_exception(self) -> None:
        """Test SkillExecutionError inherits from Exception."""
        error = SkillExecutionError("test error")
        assert isinstance(error, Exception)

    def test_skill_execution_error_stores_message(self) -> None:
        """Test SkillExecutionError stores error message."""
        error = SkillExecutionError("Skill failed to execute")
        assert str(error) == "Skill failed to execute"

    def test_skill_execution_error_stores_skill_id(self) -> None:
        """Test SkillExecutionError can store skill_id."""
        error = SkillExecutionError("Failed", skill_id="skill-123")
        assert error.skill_id == "skill-123"

    def test_skill_execution_error_stores_stage(self) -> None:
        """Test SkillExecutionError can store pipeline stage."""
        error = SkillExecutionError("Failed", stage="sanitization")
        assert error.stage == "sanitization"
