"""Tests for skill executor service."""

from src.security.trust_levels import SkillTrustLevel
from src.skills.executor import SkillExecution, SkillExecutionError


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


class TestSkillExecutionDataclass:
    """Tests for SkillExecution dataclass."""

    def test_create_skill_execution_with_required_fields(self) -> None:
        """Test creating SkillExecution with all required fields."""
        execution = SkillExecution(
            skill_id="skill-123",
            skill_path="anthropics/skills/pdf",
            trust_level=SkillTrustLevel.VERIFIED,
            input_hash="abc123",
            output_hash="def456",
            sanitized=True,
            tokens_used=["[CONTACT_001]"],
            execution_time_ms=150,
            success=True,
            result={"output": "processed"},
            error=None,
        )
        assert execution.skill_id == "skill-123"
        assert execution.trust_level == SkillTrustLevel.VERIFIED
        assert execution.success is True

    def test_skill_execution_failed_state(self) -> None:
        """Test SkillExecution captures failed execution."""
        execution = SkillExecution(
            skill_id="skill-456",
            skill_path="community/broken-skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            input_hash="abc123",
            output_hash=None,
            sanitized=True,
            tokens_used=[],
            execution_time_ms=50,
            success=False,
            result=None,
            error="Skill timed out",
        )
        assert execution.success is False
        assert execution.error == "Skill timed out"
        assert execution.output_hash is None
        assert execution.result is None

    def test_skill_execution_tokens_used_list(self) -> None:
        """Test tokens_used captures all tokens from sanitization."""
        execution = SkillExecution(
            skill_id="skill-789",
            skill_path="aria:document-parser",
            trust_level=SkillTrustLevel.CORE,
            input_hash="hash1",
            output_hash="hash2",
            sanitized=True,
            tokens_used=["[FINANCIAL_001]", "[CONTACT_001]", "[CONTACT_002]"],
            execution_time_ms=200,
            success=True,
            result={"parsed": True},
            error=None,
        )
        assert len(execution.tokens_used) == 3
        assert "[FINANCIAL_001]" in execution.tokens_used

    def test_skill_execution_result_any_type(self) -> None:
        """Test result can be any type."""
        for result_value in [
            {"key": "value"},
            ["item1", "item2"],
            "string result",
            42,
            None,
        ]:
            execution = SkillExecution(
                skill_id="skill-test",
                skill_path="test/skill",
                trust_level=SkillTrustLevel.USER,
                input_hash="hash",
                output_hash="hash2" if result_value else None,
                sanitized=False,
                tokens_used=[],
                execution_time_ms=10,
                success=result_value is not None,
                result=result_value,
                error=None if result_value else "No result",
            )
            assert execution.result == result_value
