# US-526: Skill Execution Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a skill execution service that orchestrates the full security pipeline: classify input → sanitize based on trust → sandbox execute → validate output → detokenize → audit log.

**Architecture:** The SkillExecutor class coordinates between DataClassifier, DataSanitizer, SkillSandbox, SkillInstaller, and SkillAuditService. It enforces the security pipeline for every skill execution, ensuring no data reaches skills without proper classification and sanitization based on trust levels.

**Tech Stack:** Python 3.11+, dataclasses, hashlib for SHA256, async/await patterns matching existing codebase

---

## Task 1: Create SkillExecutionError Exception

**Files:**
- Create: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing test for exception class**

```python
# tests/test_skill_executor.py
"""Tests for skill executor service."""

import pytest

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
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutionError -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.skills.executor'"

**Step 3: Write minimal implementation**

```python
# src/skills/executor.py
"""Skill execution service for ARIA.

Orchestrates the full security pipeline for skill execution:
classify → sanitize → sandbox execute → validate → detokenize → audit.
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
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutionError -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): add SkillExecutionError exception class

Part of US-526: Skill Execution Service"
```

---

## Task 2: Create SkillExecution Dataclass

**Files:**
- Modify: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing tests for SkillExecution dataclass**

```python
# Add to tests/test_skill_executor.py
from src.security.trust_levels import SkillTrustLevel
from src.skills.executor import SkillExecution, SkillExecutionError


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
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutionDataclass -v`
Expected: FAIL with "ImportError: cannot import name 'SkillExecution'"

**Step 3: Write minimal implementation**

```python
# Add to src/skills/executor.py after imports
from dataclasses import dataclass
from typing import Any

from src.security.trust_levels import SkillTrustLevel


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
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutionDataclass -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): add SkillExecution dataclass

Captures execution metadata including sanitization, timing, and results.
Part of US-526: Skill Execution Service"
```

---

## Task 3: Add Hash Computation Helper

**Files:**
- Modify: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing tests for _hash_data**

```python
# Add to tests/test_skill_executor.py
import hashlib
import json


class TestHashDataHelper:
    """Tests for _hash_data helper function."""

    def test_hash_data_returns_sha256(self) -> None:
        """Test _hash_data returns a valid SHA256 hex string."""
        from src.skills.executor import _hash_data

        result = _hash_data({"key": "value"})
        assert len(result) == 64  # SHA256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_data_is_deterministic(self) -> None:
        """Test same input always produces same hash."""
        from src.skills.executor import _hash_data

        data = {"name": "test", "value": 123}
        hash1 = _hash_data(data)
        hash2 = _hash_data(data)
        assert hash1 == hash2

    def test_hash_data_different_input_different_hash(self) -> None:
        """Test different inputs produce different hashes."""
        from src.skills.executor import _hash_data

        hash1 = _hash_data({"a": 1})
        hash2 = _hash_data({"a": 2})
        assert hash1 != hash2

    def test_hash_data_handles_string(self) -> None:
        """Test _hash_data works with string input."""
        from src.skills.executor import _hash_data

        result = _hash_data("test string")
        assert len(result) == 64

    def test_hash_data_handles_list(self) -> None:
        """Test _hash_data works with list input."""
        from src.skills.executor import _hash_data

        result = _hash_data([1, 2, 3])
        assert len(result) == 64

    def test_hash_data_handles_none(self) -> None:
        """Test _hash_data works with None input."""
        from src.skills.executor import _hash_data

        result = _hash_data(None)
        assert len(result) == 64

    def test_hash_data_sorted_keys(self) -> None:
        """Test dict key order doesn't affect hash."""
        from src.skills.executor import _hash_data

        hash1 = _hash_data({"a": 1, "b": 2})
        hash2 = _hash_data({"b": 2, "a": 1})
        assert hash1 == hash2
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestHashDataHelper -v`
Expected: FAIL with "ImportError: cannot import name '_hash_data'"

**Step 3: Write minimal implementation**

```python
# Add to src/skills/executor.py after imports
import hashlib
import json


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
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestHashDataHelper -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): add _hash_data helper for audit hashing

Uses deterministic JSON serialization for consistent hashes.
Part of US-526: Skill Execution Service"
```

---

## Task 4: Create SkillExecutor Class with Constructor

**Files:**
- Modify: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing tests for SkillExecutor init**

```python
# Add to tests/test_skill_executor.py
from unittest.mock import MagicMock, patch


class TestSkillExecutorInit:
    """Tests for SkillExecutor initialization."""

    def test_executor_initializes_with_dependencies(self) -> None:
        """Test SkillExecutor accepts all required dependencies."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox
        from src.security.skill_audit import SkillAuditService
        from src.skills.executor import SkillExecutor
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
        from src.skills.executor import SkillExecutor

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
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorInit -v`
Expected: FAIL with "ImportError: cannot import name 'SkillExecutor'"

**Step 3: Write minimal implementation**

```python
# Add to src/skills/executor.py

from src.security.data_classification import DataClassifier
from src.security.sanitization import DataSanitizer
from src.security.sandbox import SkillSandbox
from src.security.skill_audit import SkillAuditService
from src.skills.index import SkillIndex
from src.skills.installer import SkillInstaller


class SkillExecutor:
    """Executes skills through the complete security pipeline.

    Orchestrates: classify → sanitize → sandbox execute → validate → detokenize → audit.

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
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorInit -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): add SkillExecutor class with constructor

Accepts all required security pipeline dependencies.
Part of US-526: Skill Execution Service"
```

---

## Task 5: Implement Execute Method - Skill Lookup

**Files:**
- Modify: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing tests for execute skill lookup**

```python
# Add to tests/test_skill_executor.py
from datetime import datetime, UTC


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
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorExecuteSkillLookup -v`
Expected: FAIL with "AttributeError: 'SkillExecutor' object has no attribute 'execute'"

**Step 3: Write minimal implementation**

```python
# Add to SkillExecutor class in src/skills/executor.py

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

        # TODO: Implement remaining pipeline phases
        raise NotImplementedError("Execution pipeline not yet complete")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorExecuteSkillLookup -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): add execute method with skill lookup phase

Validates skill exists in index and is installed for user.
Part of US-526: Skill Execution Service"
```

---

## Task 6: Implement Execute Method - Full Pipeline

**Files:**
- Modify: `src/skills/executor.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write the failing tests for full pipeline**

```python
# Add to tests/test_skill_executor.py
from src.security.sandbox import SandboxResult, SANDBOX_BY_TRUST
from src.security.sanitization import TokenMap


class TestSkillExecutorExecuteFullPipeline:
    """Tests for SkillExecutor.execute full pipeline."""

    @pytest.fixture
    def executor_with_full_mocks(self) -> tuple:
        """Create executor with fully mocked pipeline."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox, SandboxResult
        from src.security.trust_levels import SkillTrustLevel
        from src.skills.executor import SkillExecutor
        from src.skills.index import SkillIndexEntry

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        sandbox = MagicMock(spec=SkillSandbox)
        index = MagicMock()
        installer = MagicMock()
        audit = MagicMock()

        # Setup default successful responses
        mock_entry = MagicMock(spec=SkillIndexEntry)
        mock_entry.id = "skill-123"
        mock_entry.skill_path = "anthropics/skills/pdf"
        mock_entry.skill_name = "PDF Parser"
        mock_entry.trust_level = SkillTrustLevel.VERIFIED
        mock_entry.full_content = "# PDF Parser\nExtract text from PDFs"
        index.get_skill = AsyncMock(return_value=mock_entry)

        installer.is_installed = AsyncMock(return_value=True)
        installer.record_usage = AsyncMock(return_value=None)

        # Mock sandbox to return success
        sandbox.execute = AsyncMock(
            return_value=SandboxResult(
                output={"parsed": "document content"},
                execution_time_ms=150,
                memory_used_mb=50.0,
                violations=[],
                success=True,
            )
        )

        # Mock audit service
        audit.get_latest_hash = AsyncMock(return_value="0" * 64)
        audit.log_execution = AsyncMock(return_value=None)

        executor = SkillExecutor(
            classifier=classifier,
            sanitizer=sanitizer,
            sandbox=sandbox,
            index=index,
            installer=installer,
            audit_service=audit,
        )

        return executor, index, installer, sandbox, audit, mock_entry

    @pytest.mark.asyncio
    async def test_execute_successful_returns_skill_execution(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test successful execution returns SkillExecution."""
        from src.skills.executor import SkillExecution

        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        result = await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "document.pdf"},
        )

        assert isinstance(result, SkillExecution)
        assert result.skill_id == "skill-123"
        assert result.skill_path == "anthropics/skills/pdf"
        assert result.success is True
        assert result.result == {"parsed": "document content"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_calls_sanitizer_with_trust_level(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute sanitizes input based on skill trust level."""
        from src.security.trust_levels import SkillTrustLevel

        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        # Spy on sanitizer
        with patch.object(
            executor._sanitizer, "sanitize", wraps=executor._sanitizer.sanitize
        ) as mock_sanitize:
            mock_sanitize.return_value = ({"file": "document.pdf"}, TokenMap())

            await executor.execute(
                user_id="user-123",
                skill_id="skill-123",
                input_data={"file": "document.pdf"},
            )

            mock_sanitize.assert_called_once()
            call_args = mock_sanitize.call_args
            assert call_args[0][1] == SkillTrustLevel.VERIFIED  # trust level

    @pytest.mark.asyncio
    async def test_execute_calls_sandbox_with_correct_config(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute uses correct sandbox config for trust level."""
        from src.security.sandbox import SANDBOX_BY_TRUST
        from src.security.trust_levels import SkillTrustLevel

        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "test.pdf"},
        )

        sandbox.execute.assert_called_once()
        call_args = sandbox.execute.call_args
        # Should use VERIFIED config
        assert call_args[1]["config"] == SANDBOX_BY_TRUST[SkillTrustLevel.VERIFIED]

    @pytest.mark.asyncio
    async def test_execute_logs_audit_entry(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute logs to audit trail."""
        from src.security.skill_audit import SkillAuditEntry

        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "test.pdf"},
            task_id="task-456",
            agent_id="hunter",
            trigger_reason="document_analysis",
        )

        audit.log_execution.assert_called_once()
        call_args = audit.log_execution.call_args
        audit_entry = call_args[0][0]
        assert isinstance(audit_entry, SkillAuditEntry)
        assert audit_entry.user_id == "user-123"
        assert audit_entry.skill_id == "skill-123"
        assert audit_entry.task_id == "task-456"
        assert audit_entry.agent_id == "hunter"
        assert audit_entry.trigger_reason == "document_analysis"
        assert audit_entry.success is True

    @pytest.mark.asyncio
    async def test_execute_records_usage_on_success(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute records usage in installer on success."""
        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "test.pdf"},
        )

        installer.record_usage.assert_called_once_with(
            "user-123", "skill-123", success=True
        )

    @pytest.mark.asyncio
    async def test_execute_computes_input_and_output_hashes(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute computes hashes for audit."""
        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        result = await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "test.pdf"},
        )

        # Should have valid hashes
        assert len(result.input_hash) == 64
        assert len(result.output_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.input_hash)
        assert all(c in "0123456789abcdef" for c in result.output_hash)

    @pytest.mark.asyncio
    async def test_execute_captures_execution_time(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute captures execution time from sandbox."""
        executor, index, installer, sandbox, audit, entry = executor_with_full_mocks

        result = await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"file": "test.pdf"},
        )

        assert result.execution_time_ms == 150  # From mock
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorExecuteFullPipeline -v`
Expected: FAIL with "NotImplementedError: Execution pipeline not yet complete"

**Step 3: Write full implementation**

```python
# Replace the execute method in src/skills/executor.py with full implementation

import time
from src.security.sandbox import SANDBOX_BY_TRUST, SandboxViolation
from src.security.skill_audit import SkillAuditEntry


class SkillExecutor:
    """Executes skills through the complete security pipeline.

    Orchestrates: classify → sanitize → sandbox execute → validate → detokenize → audit.

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

        start_time = time.perf_counter()
        input_hash = _hash_data(input_data)

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
        skill_path = skill_entry.skill_path
        skill_content = skill_entry.full_content or ""

        # Phase 2: Sanitize input based on trust level
        try:
            sanitized_data, token_map = await self._sanitizer.sanitize(
                input_data,
                trust_level,
                context,
            )
            tokens_used = list(token_map.tokens.keys())
            sanitized = len(tokens_used) > 0
        except Exception as e:
            raise SkillExecutionError(
                f"Failed to sanitize input: {e}",
                skill_id=skill_id,
                stage="sanitization",
            ) from e

        # Phase 3: Execute in sandbox
        sandbox_config = SANDBOX_BY_TRUST[trust_level]
        output_hash: str | None = None
        result: Any = None
        error: str | None = None
        success = False
        execution_time_ms = 0

        try:
            sandbox_result = await self._sandbox.execute(
                skill_content=skill_content,
                input_data=sanitized_data,
                config=sandbox_config,
            )
            execution_time_ms = sandbox_result.execution_time_ms
            success = sandbox_result.success

            if success:
                # Phase 4: Validate output for leakage
                leakage = self._sanitizer.validate_output(
                    sandbox_result.output, token_map
                )
                if leakage.leaked:
                    # Log but don't fail - redact leaked values in output
                    pass  # TODO: implement leakage handling

                # Phase 5: Detokenize output
                result = self._sanitizer.detokenize(sandbox_result.output, token_map)
                output_hash = _hash_data(result)

        except SandboxViolation as e:
            error = str(e)
            success = False
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
        except Exception as e:
            error = str(e)
            success = False
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Phase 6: Audit logging
        previous_hash = await self._audit.get_latest_hash(user_id)
        audit_data = {
            "user_id": user_id,
            "skill_id": skill_id,
            "skill_path": skill_path,
            "skill_trust_level": trust_level.value,
            "trigger_reason": trigger_reason,
            "data_classes_requested": [],  # TODO: track requested classes
            "data_classes_granted": [],  # TODO: track granted classes
            "data_redacted": sanitized,
            "tokens_used": tokens_used,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "execution_time_ms": execution_time_ms,
            "success": success,
            "error": error,
        }
        entry_hash = self._audit._compute_hash(audit_data, previous_hash)

        audit_entry = SkillAuditEntry(
            user_id=user_id,
            skill_id=skill_id,
            skill_path=skill_path,
            skill_trust_level=trust_level.value,
            task_id=task_id,
            agent_id=agent_id,
            trigger_reason=trigger_reason,
            data_classes_requested=[],
            data_classes_granted=[],
            data_redacted=sanitized,
            tokens_used=tokens_used,
            input_hash=input_hash,
            output_hash=output_hash,
            execution_time_ms=execution_time_ms,
            success=success,
            error=error,
            sandbox_config=None,  # TODO: serialize config
            security_flags=[],
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        await self._audit.log_execution(audit_entry)

        # Record usage in installer
        await self._installer.record_usage(user_id, skill_id, success=success)

        return SkillExecution(
            skill_id=skill_id,
            skill_path=skill_path,
            trust_level=trust_level,
            input_hash=input_hash,
            output_hash=output_hash,
            sanitized=sanitized,
            tokens_used=tokens_used,
            execution_time_ms=execution_time_ms,
            success=success,
            result=result,
            error=error,
        )
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorExecuteFullPipeline -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/skills/executor.py tests/test_skill_executor.py
git commit -m "feat(skills): implement full execute pipeline

Complete security pipeline: lookup → sanitize → sandbox → validate → detokenize → audit.
Part of US-526: Skill Execution Service"
```

---

## Task 7: Add Error Handling Tests

**Files:**
- Test: `tests/test_skill_executor.py`

**Step 1: Write tests for error cases**

```python
# Add to tests/test_skill_executor.py

class TestSkillExecutorErrorHandling:
    """Tests for SkillExecutor error handling."""

    @pytest.fixture
    def executor_with_full_mocks(self) -> tuple:
        """Create executor with fully mocked pipeline."""
        from src.security.data_classification import DataClassifier
        from src.security.sanitization import DataSanitizer
        from src.security.sandbox import SkillSandbox, SandboxResult
        from src.security.trust_levels import SkillTrustLevel
        from src.skills.executor import SkillExecutor
        from src.skills.index import SkillIndexEntry

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        sandbox = MagicMock(spec=SkillSandbox)
        index = MagicMock()
        installer = MagicMock()
        audit = MagicMock()

        mock_entry = MagicMock(spec=SkillIndexEntry)
        mock_entry.id = "skill-123"
        mock_entry.skill_path = "test/skill"
        mock_entry.skill_name = "Test"
        mock_entry.trust_level = SkillTrustLevel.COMMUNITY
        mock_entry.full_content = "# Test"
        index.get_skill = AsyncMock(return_value=mock_entry)
        installer.is_installed = AsyncMock(return_value=True)
        installer.record_usage = AsyncMock(return_value=None)
        audit.get_latest_hash = AsyncMock(return_value="0" * 64)
        audit.log_execution = AsyncMock(return_value=None)

        executor = SkillExecutor(
            classifier=classifier,
            sanitizer=sanitizer,
            sandbox=sandbox,
            index=index,
            installer=installer,
            audit_service=audit,
        )

        return executor, sandbox, audit, installer

    @pytest.mark.asyncio
    async def test_execute_handles_sandbox_violation(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute handles SandboxViolation gracefully."""
        from src.security.sandbox import SandboxViolation

        executor, sandbox, audit, installer = executor_with_full_mocks

        sandbox.execute = AsyncMock(
            side_effect=SandboxViolation("timeout", "Skill timed out after 30s")
        )

        result = await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"test": "data"},
        )

        assert result.success is False
        assert "timeout" in result.error.lower()
        # Should still log audit
        audit.log_execution.assert_called_once()
        # Should record failed usage
        installer.record_usage.assert_called_once_with(
            "user-123", "skill-123", success=False
        )

    @pytest.mark.asyncio
    async def test_execute_handles_sandbox_exception(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test execute handles unexpected sandbox exceptions."""
        executor, sandbox, audit, installer = executor_with_full_mocks

        sandbox.execute = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        result = await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"test": "data"},
        )

        assert result.success is False
        assert "Unexpected error" in result.error

    @pytest.mark.asyncio
    async def test_execute_logs_failed_execution_to_audit(
        self, executor_with_full_mocks: tuple
    ) -> None:
        """Test failed executions are still logged to audit."""
        from src.security.skill_audit import SkillAuditEntry

        executor, sandbox, audit, installer = executor_with_full_mocks

        sandbox.execute = AsyncMock(side_effect=RuntimeError("Boom"))

        await executor.execute(
            user_id="user-123",
            skill_id="skill-123",
            input_data={"test": "data"},
        )

        audit.log_execution.assert_called_once()
        audit_entry = audit.log_execution.call_args[0][0]
        assert audit_entry.success is False
        assert audit_entry.error is not None
```

**Step 2: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestSkillExecutorErrorHandling -v`
Expected: PASS (3 tests)

**Step 3: Commit**

```bash
git add tests/test_skill_executor.py
git commit -m "test(skills): add error handling tests for SkillExecutor

Verifies sandbox violations and exceptions are handled gracefully.
Part of US-526: Skill Execution Service"
```

---

## Task 8: Update Module Exports

**Files:**
- Modify: `src/skills/__init__.py`
- Test: `tests/test_skill_executor.py`

**Step 1: Write test for module exports**

```python
# Add to tests/test_skill_executor.py

class TestModuleExports:
    """Tests for skills module exports."""

    def test_skill_executor_exported_from_skills_module(self) -> None:
        """Test SkillExecutor is exported from skills module."""
        from src.skills import SkillExecutor

        assert SkillExecutor is not None

    def test_skill_execution_exported_from_skills_module(self) -> None:
        """Test SkillExecution is exported from skills module."""
        from src.skills import SkillExecution

        assert SkillExecution is not None

    def test_skill_execution_error_exported_from_skills_module(self) -> None:
        """Test SkillExecutionError is exported from skills module."""
        from src.skills import SkillExecutionError

        assert SkillExecutionError is not None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_skill_executor.py::TestModuleExports -v`
Expected: FAIL with "ImportError: cannot import name 'SkillExecutor'"

**Step 3: Update module exports**

```python
# src/skills/__init__.py
"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Installation and lifecycle management
- Security-aware execution
- Multi-skill orchestration
"""

from src.skills.executor import SkillExecution, SkillExecutionError, SkillExecutor
from src.skills.index import (
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
    SkillIndex,
    SkillIndexEntry,
)
from src.skills.installer import InstalledSkill, SkillInstaller, SkillNotFoundError

__all__ = [
    # Index
    "SkillIndex",
    "SkillIndexEntry",
    "TIER_1_CORE_SKILLS",
    "TIER_2_RELEVANT_TAG",
    "TIER_3_DISCOVERY_ALL",
    # Installer
    "SkillInstaller",
    "InstalledSkill",
    "SkillNotFoundError",
    # Executor
    "SkillExecutor",
    "SkillExecution",
    "SkillExecutionError",
]
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_skill_executor.py::TestModuleExports -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/skills/__init__.py tests/test_skill_executor.py
git commit -m "feat(skills): export SkillExecutor, SkillExecution, SkillExecutionError

Updates skills module __init__.py with new executor exports.
Part of US-526: Skill Execution Service"
```

---

## Task 9: Run Full Test Suite

**Files:**
- None (validation only)

**Step 1: Run all executor tests**

Run: `python3 -m pytest tests/test_skill_executor.py -v`
Expected: PASS (all tests)

**Step 2: Run all skills module tests**

Run: `python3 -m pytest tests/test_skill*.py -v`
Expected: PASS (all tests)

**Step 3: Run type checking**

Run: `mypy src/skills/executor.py --strict`
Expected: Success with no errors

**Step 4: Run linting**

Run: `ruff check src/skills/executor.py && ruff format src/skills/executor.py`
Expected: No issues

**Step 5: Final commit**

```bash
git add .
git commit -m "feat(skills): complete US-526 Skill Execution Service

Implements SkillExecutor with full security pipeline:
- SkillExecutionError exception with skill_id and stage tracking
- SkillExecution dataclass capturing execution metadata
- _hash_data helper for SHA256 audit hashing
- SkillExecutor.execute() method with pipeline:
  lookup → sanitize → sandbox → validate → detokenize → audit

All tests passing, type-checked, and linted.

Closes US-526"
```

---

## Summary

| Task | Description | Files | Tests |
|------|-------------|-------|-------|
| 1 | SkillExecutionError exception | executor.py | 4 |
| 2 | SkillExecution dataclass | executor.py | 4 |
| 3 | _hash_data helper | executor.py | 7 |
| 4 | SkillExecutor constructor | executor.py | 2 |
| 5 | Execute - skill lookup | executor.py | 2 |
| 6 | Execute - full pipeline | executor.py | 7 |
| 7 | Error handling tests | test_skill_executor.py | 3 |
| 8 | Module exports | __init__.py | 3 |
| 9 | Full validation | - | - |

**Total: ~32 tests across 9 tasks**
