"""Tests for skill executor service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.security.trust_levels import SkillTrustLevel
from src.skills.executor import SkillExecution, SkillExecutionError, SkillExecutor, _hash_data


class TestHashDataHelper:
    """Tests for _hash_data helper function."""

    def test_hash_data_returns_sha256(self) -> None:
        """Test _hash_data returns a valid SHA256 hex string."""
        result = _hash_data({"key": "value"})
        assert len(result) == 64  # SHA256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_data_is_deterministic(self) -> None:
        """Test same input always produces same hash."""
        data = {"name": "test", "value": 123}
        hash1 = _hash_data(data)
        hash2 = _hash_data(data)
        assert hash1 == hash2

    def test_hash_data_different_input_different_hash(self) -> None:
        """Test different inputs produce different hashes."""
        hash1 = _hash_data({"a": 1})
        hash2 = _hash_data({"a": 2})
        assert hash1 != hash2

    def test_hash_data_handles_string(self) -> None:
        """Test _hash_data works with string input."""
        result = _hash_data("test string")
        assert len(result) == 64

    def test_hash_data_handles_list(self) -> None:
        """Test _hash_data works with list input."""
        result = _hash_data([1, 2, 3])
        assert len(result) == 64

    def test_hash_data_handles_none(self) -> None:
        """Test _hash_data works with None input."""
        result = _hash_data(None)
        assert len(result) == 64

    def test_hash_data_sorted_keys(self) -> None:
        """Test dict key order doesn't affect hash."""
        hash1 = _hash_data({"a": 1, "b": 2})
        hash2 = _hash_data({"b": 2, "a": 1})
        assert hash1 == hash2


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


class TestSkillExecutorInit:
    """Tests for SkillExecutor initialization."""

    def test_executor_initializes_with_dependencies(self) -> None:
        """Test SkillExecutor accepts all required dependencies."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox
        from src.security.skill_audit import SkillAuditService
        from src.skills.index import SkillIndex
        from src.skills.installer import SkillInstaller

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        sandbox = SkillSandbox()
        index = MagicMock(spec=SkillIndex)
        installer = MagicMock(spec=SkillInstaller)
        audit = MagicMock(spec=SkillAuditService)

        executor = SkillExecutor(
            classifier=classifier,
            sanitizer=sanitizer,
            sandbox=sandbox,
            index=index,
            installer=installer,
            audit_service=audit,
        )

        assert executor._classifier is classifier
        assert executor._sanitizer is sanitizer
        assert executor._sandbox is sandbox
        assert executor._index is index
        assert executor._installer is installer
        assert executor._audit is audit

    def test_executor_stores_all_components(self) -> None:
        """Test all components are accessible after init."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        sandbox = SkillSandbox()

        executor = SkillExecutor(
            classifier=classifier,
            sanitizer=sanitizer,
            sandbox=sandbox,
            index=MagicMock(),
            installer=MagicMock(),
            audit_service=MagicMock(),
        )

        # Should have all private attributes
        assert hasattr(executor, "_classifier")
        assert hasattr(executor, "_sanitizer")
        assert hasattr(executor, "_sandbox")
        assert hasattr(executor, "_index")
        assert hasattr(executor, "_installer")
        assert hasattr(executor, "_audit")


class TestSkillExecutorExecuteSkillLookup:
    """Tests for SkillExecutor.execute skill lookup phase."""

    @pytest.fixture
    def executor_with_mocks(self) -> tuple:
        """Create executor with mocked dependencies."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox
        from src.skills.executor import SkillExecutor

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        sandbox = SkillSandbox()
        index = MagicMock()
        installer = MagicMock()
        audit = MagicMock()

        executor = SkillExecutor(
            classifier=classifier,
            sanitizer=sanitizer,
            sandbox=sandbox,
            index=index,
            installer=installer,
            audit_service=audit,
        )

        return executor, index, installer, audit

    @pytest.mark.asyncio
    async def test_execute_raises_error_if_skill_not_found(
        self, executor_with_mocks: tuple
    ) -> None:
        """Test execute raises SkillExecutionError if skill not in index."""
        from src.skills.executor import SkillExecutionError

        executor, index, installer, audit = executor_with_mocks
        index.get_skill = AsyncMock(return_value=None)

        with pytest.raises(SkillExecutionError) as exc_info:
            await executor.execute(
                user_id="user-123",
                skill_id="nonexistent-skill",
                input_data={"text": "test"},
            )

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.skill_id == "nonexistent-skill"
        assert exc_info.value.stage == "lookup"

    @pytest.mark.asyncio
    async def test_execute_raises_error_if_skill_not_installed(
        self, executor_with_mocks: tuple
    ) -> None:
        """Test execute raises error if skill not installed for user."""
        from src.security.trust_levels import SkillTrustLevel
        from src.skills.executor import SkillExecutionError
        from src.skills.index import SkillIndexEntry

        executor, index, installer, audit = executor_with_mocks

        # Skill exists in index
        mock_entry = MagicMock(spec=SkillIndexEntry)
        mock_entry.id = "skill-123"
        mock_entry.skill_path = "test/skill"
        mock_entry.skill_name = "Test Skill"
        mock_entry.trust_level = SkillTrustLevel.COMMUNITY
        mock_entry.full_content = "# Test skill content"
        index.get_skill = AsyncMock(return_value=mock_entry)

        # But not installed
        installer.is_installed = AsyncMock(return_value=False)

        with pytest.raises(SkillExecutionError) as exc_info:
            await executor.execute(
                user_id="user-123",
                skill_id="skill-123",
                input_data={"text": "test"},
            )

        assert "not installed" in str(exc_info.value).lower()
        assert exc_info.value.skill_id == "skill-123"
        assert exc_info.value.stage == "lookup"
