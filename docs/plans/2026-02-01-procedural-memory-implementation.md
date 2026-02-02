# Procedural Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement procedural memory for storing and retrieving learned workflows with success tracking, versioning, and trigger-based matching.

**Architecture:** Procedural memory stores workflows in Supabase with JSONB for flexible step definitions and trigger conditions. Unlike episodic/semantic memory which use Graphiti, procedural memory uses Supabase for structured querying of workflow metadata and success rates. The implementation follows established memory module patterns (dataclass models, async service class, comprehensive error handling).

**Tech Stack:** Python 3.11+, Supabase (PostgreSQL), Pydantic for validation, pytest for testing, mypy strict mode

---

## Task 1: Add ProceduralMemoryError and WorkflowNotFoundError Exceptions

**Files:**
- Modify: `backend/src/core/exceptions.py:259` (append after FactNotFoundError)

**Step 1: Read the exceptions file to confirm insertion point**

Verify the current end of the file to know exact line numbers.

**Step 2: Add ProceduralMemoryError class**

Append to `backend/src/core/exceptions.py`:

```python


class ProceduralMemoryError(ARIAException):
    """Procedural memory operation error (500).

    Used for failures when storing or retrieving workflows from Supabase.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize procedural memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Procedural memory operation failed: {message}",
            code="PROCEDURAL_MEMORY_ERROR",
            status_code=500,
        )


class WorkflowNotFoundError(NotFoundError):
    """Workflow not found error (404)."""

    def __init__(self, workflow_id: str) -> None:
        """Initialize workflow not found error.

        Args:
            workflow_id: The ID of the workflow that was not found.
        """
        super().__init__(resource="Workflow", resource_id=workflow_id)
```

**Step 3: Run quality gates to verify**

Run: `cd backend && mypy src/core/exceptions.py --strict && ruff check src/core/exceptions.py && ruff format src/core/exceptions.py --check`
Expected: All pass

**Step 4: Commit**

```bash
cd backend && git add src/core/exceptions.py && git commit -m "$(cat <<'EOF'
feat(memory): add procedural memory exceptions

Add ProceduralMemoryError and WorkflowNotFoundError for procedural
memory error handling, following the pattern from episodic/semantic.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Workflow Dataclass with Serialization

**Files:**
- Create: `backend/src/memory/procedural.py`
- Test: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for Workflow dataclass**

Create `backend/tests/test_procedural_memory.py`:

```python
"""Tests for procedural memory module."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest


def test_workflow_initialization() -> None:
    """Test Workflow initializes with required fields."""
    from src.memory.procedural import Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-123",
        user_id="user-456",
        workflow_name="follow_up_sequence",
        description="Standard follow-up after initial meeting",
        trigger_conditions={"event": "meeting_completed", "lead_stage": "qualified"},
        steps=[
            {"action": "wait", "duration_hours": 24},
            {"action": "send_email", "template": "follow_up_1"},
            {"action": "wait", "duration_hours": 72},
            {"action": "send_email", "template": "follow_up_2"},
        ],
        success_count=15,
        failure_count=3,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    assert workflow.id == "wf-123"
    assert workflow.user_id == "user-456"
    assert workflow.workflow_name == "follow_up_sequence"
    assert workflow.description == "Standard follow-up after initial meeting"
    assert workflow.trigger_conditions["event"] == "meeting_completed"
    assert len(workflow.steps) == 4
    assert workflow.success_count == 15
    assert workflow.failure_count == 3
    assert workflow.is_shared is False
    assert workflow.version == 1


def test_workflow_success_rate_calculation() -> None:
    """Test Workflow.success_rate property calculates correctly."""
    from src.memory.procedural import Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-123",
        user_id="user-456",
        workflow_name="test_workflow",
        description="Test",
        trigger_conditions={},
        steps=[],
        success_count=75,
        failure_count=25,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    assert workflow.success_rate == 0.75


def test_workflow_success_rate_zero_executions() -> None:
    """Test Workflow.success_rate returns 0.0 when no executions."""
    from src.memory.procedural import Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-123",
        user_id="user-456",
        workflow_name="test_workflow",
        description="Test",
        trigger_conditions={},
        steps=[],
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    assert workflow.success_rate == 0.0


def test_workflow_to_dict_serializes_correctly() -> None:
    """Test Workflow.to_dict returns a serializable dictionary."""
    from src.memory.procedural import Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-123",
        user_id="user-456",
        workflow_name="follow_up_sequence",
        description="Standard follow-up",
        trigger_conditions={"event": "meeting_completed"},
        steps=[{"action": "send_email", "template": "follow_up_1"}],
        success_count=10,
        failure_count=2,
        is_shared=True,
        version=2,
        created_at=now,
        updated_at=now,
    )

    data = workflow.to_dict()

    assert data["id"] == "wf-123"
    assert data["user_id"] == "user-456"
    assert data["workflow_name"] == "follow_up_sequence"
    assert data["description"] == "Standard follow-up"
    assert data["trigger_conditions"] == {"event": "meeting_completed"}
    assert data["steps"] == [{"action": "send_email", "template": "follow_up_1"}]
    assert data["success_count"] == 10
    assert data["failure_count"] == 2
    assert data["is_shared"] is True
    assert data["version"] == 2
    assert data["created_at"] == now.isoformat()
    assert data["updated_at"] == now.isoformat()

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_workflow_from_dict_deserializes_correctly() -> None:
    """Test Workflow.from_dict creates Workflow from dictionary."""
    from src.memory.procedural import Workflow

    now = datetime.now(UTC)
    data: dict[str, Any] = {
        "id": "wf-123",
        "user_id": "user-456",
        "workflow_name": "outreach_sequence",
        "description": "Cold outreach workflow",
        "trigger_conditions": {"lead_source": "conference"},
        "steps": [{"action": "research", "duration_minutes": 15}],
        "success_count": 5,
        "failure_count": 1,
        "is_shared": False,
        "version": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    workflow = Workflow.from_dict(data)

    assert workflow.id == "wf-123"
    assert workflow.user_id == "user-456"
    assert workflow.workflow_name == "outreach_sequence"
    assert workflow.description == "Cold outreach workflow"
    assert workflow.trigger_conditions == {"lead_source": "conference"}
    assert workflow.steps == [{"action": "research", "duration_minutes": 15}]
    assert workflow.success_count == 5
    assert workflow.failure_count == 1
    assert workflow.is_shared is False
    assert workflow.version == 1
    assert workflow.created_at == now
    assert workflow.updated_at == now
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.procedural'"

**Step 3: Write minimal Workflow implementation**

Create `backend/src/memory/procedural.py`:

```python
"""Procedural memory module for storing learned workflows.

Procedural memory stores successful workflow patterns with:
- Ordered step sequences for task execution
- Trigger conditions for workflow matching
- Success/failure tracking for learning
- Version history for workflow evolution
- User-specific and shared workflows

Workflows are stored in Supabase for structured querying and
easy integration with the rest of the application state.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Workflow:
    """A procedural memory record representing a learned workflow.

    Stores repeatable patterns of actions with success tracking
    for continuous improvement of task execution.
    """

    id: str
    user_id: str
    workflow_name: str
    description: str
    trigger_conditions: dict[str, Any]  # When to use this workflow
    steps: list[dict[str, Any]]  # Ordered list of actions
    success_count: int
    failure_count: int
    is_shared: bool  # Available to other users in same company
    version: int
    created_at: datetime
    updated_at: datetime

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of this workflow.

        Returns:
            Success rate between 0.0 and 1.0, or 0.0 if no executions.
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        """Serialize workflow to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workflow_name": self.workflow_name,
            "description": self.description,
            "trigger_conditions": self.trigger_conditions,
            "steps": self.steps,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "is_shared": self.is_shared,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create a Workflow instance from a dictionary.

        Args:
            data: Dictionary containing workflow data.

        Returns:
            Workflow instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            workflow_name=data["workflow_name"],
            description=data["description"],
            trigger_conditions=data["trigger_conditions"],
            steps=data["steps"],
            success_count=data["success_count"],
            failure_count=data["failure_count"],
            is_shared=data["is_shared"],
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py -v`
Expected: PASS (6 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): add Workflow dataclass for procedural memory

Implement Workflow dataclass with:
- Full field support per US-205 requirements
- success_rate property for learning metrics
- to_dict/from_dict for serialization
- Comprehensive unit tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create ProceduralMemory Service Class with create_workflow

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for ProceduralMemory.create_workflow**

Append to `backend/tests/test_procedural_memory.py`:

```python


def test_procedural_memory_has_required_methods() -> None:
    """Test ProceduralMemory class has required interface methods."""
    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    # Check required async methods exist
    assert hasattr(memory, "create_workflow")
    assert hasattr(memory, "get_workflow")
    assert hasattr(memory, "update_workflow")
    assert hasattr(memory, "delete_workflow")
    assert hasattr(memory, "find_matching_workflow")
    assert hasattr(memory, "record_outcome")
    assert hasattr(memory, "list_workflows")


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mock Supabase client for testing."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


@pytest.mark.asyncio
async def test_create_workflow_stores_in_supabase(mock_supabase_client: MagicMock) -> None:
    """Test that create_workflow stores workflow in Supabase."""
    from unittest.mock import patch

    from src.memory.procedural import ProceduralMemory, Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="",  # Will be generated
        user_id="user-456",
        workflow_name="follow_up_sequence",
        description="Standard follow-up",
        trigger_conditions={"event": "meeting_completed"},
        steps=[{"action": "send_email", "template": "follow_up_1"}],
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    memory = ProceduralMemory()

    # Setup mock response
    mock_table = mock_supabase_client.table.return_value
    mock_insert = MagicMock()
    mock_table.insert.return_value = mock_insert
    mock_execute = MagicMock()
    mock_insert.execute.return_value = mock_execute
    mock_execute.data = [{"id": "generated-uuid-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_supabase_client

        result = await memory.create_workflow(workflow)

        assert result != ""
        assert len(result) > 0
        mock_supabase_client.table.assert_called_with("procedural_memories")
        mock_table.insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_workflow_generates_id_if_missing() -> None:
    """Test that create_workflow generates ID if not provided."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory, Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="",  # Empty ID
        user_id="user-456",
        workflow_name="test_workflow",
        description="Test",
        trigger_conditions={},
        steps=[],
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_insert = MagicMock()
    mock_table.insert.return_value = mock_insert
    mock_execute = MagicMock()
    mock_insert.execute.return_value = mock_execute
    mock_execute.data = [{"id": "new-generated-uuid"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        result = await memory.create_workflow(workflow)

        assert result != ""
        # Verify the insert was called with a generated UUID
        call_args = mock_table.insert.call_args
        assert "id" in call_args[0][0]
        assert call_args[0][0]["id"] != ""
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_procedural_memory_has_required_methods -v`
Expected: FAIL with "cannot import name 'ProceduralMemory'"

**Step 3: Add ProceduralMemory class with create_workflow**

Append to `backend/src/memory/procedural.py`:

```python


from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError
from src.db.supabase import SupabaseClient

import uuid


class ProceduralMemory:
    """Service class for procedural memory operations.

    Provides async interface for storing, retrieving, and managing
    learned workflows. Uses Supabase as the underlying storage for
    structured querying and success rate tracking.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            ProceduralMemoryError: If client initialization fails.
        """
        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise ProceduralMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create_workflow(self, workflow: Workflow) -> str:
        """Create a new workflow in procedural memory.

        Args:
            workflow: The Workflow instance to store.

        Returns:
            The ID of the stored workflow.

        Raises:
            ProceduralMemoryError: If storage fails.
        """
        try:
            # Generate ID if not provided
            workflow_id = workflow.id if workflow.id else str(uuid.uuid4())

            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": workflow_id,
                "user_id": workflow.user_id,
                "workflow_name": workflow.workflow_name,
                "description": workflow.description,
                "trigger_conditions": workflow.trigger_conditions,
                "steps": workflow.steps,
                "success_count": workflow.success_count,
                "failure_count": workflow.failure_count,
                "is_shared": workflow.is_shared,
                "version": workflow.version,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            response = client.table("procedural_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise ProceduralMemoryError("Failed to insert workflow")

            logger.info(
                "Created workflow",
                extra={
                    "workflow_id": workflow_id,
                    "user_id": workflow.user_id,
                    "workflow_name": workflow.workflow_name,
                },
            )

            return workflow_id

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create workflow")
            raise ProceduralMemoryError(f"Failed to create workflow: {e}") from e

    async def get_workflow(self, user_id: str, workflow_id: str) -> Workflow:
        """Placeholder for get_workflow."""
        raise NotImplementedError

    async def update_workflow(self, workflow: Workflow) -> None:
        """Placeholder for update_workflow."""
        raise NotImplementedError

    async def delete_workflow(self, user_id: str, workflow_id: str) -> None:
        """Placeholder for delete_workflow."""
        raise NotImplementedError

    async def find_matching_workflow(
        self, user_id: str, context: dict[str, Any]
    ) -> Workflow | None:
        """Placeholder for find_matching_workflow."""
        raise NotImplementedError

    async def record_outcome(self, workflow_id: str, success: bool) -> None:
        """Placeholder for record_outcome."""
        raise NotImplementedError

    async def list_workflows(
        self, user_id: str, include_shared: bool = True
    ) -> list[Workflow]:
        """Placeholder for list_workflows."""
        raise NotImplementedError
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py -v`
Expected: PASS (9 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): add ProceduralMemory service with create_workflow

Implement ProceduralMemory class with:
- Supabase client integration
- create_workflow for storing new workflows
- Method stubs for remaining operations
- Unit tests for create functionality

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement get_workflow Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for get_workflow**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_get_workflow_retrieves_by_id() -> None:
    """Test get_workflow retrieves specific workflow by ID."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_single = MagicMock()
    mock_eq2.single.return_value = mock_single
    mock_execute = MagicMock()
    mock_single.execute.return_value = mock_execute
    mock_execute.data = {
        "id": "wf-123",
        "user_id": "user-456",
        "workflow_name": "follow_up",
        "description": "Test workflow",
        "trigger_conditions": {"event": "meeting"},
        "steps": [{"action": "email"}],
        "success_count": 10,
        "failure_count": 2,
        "is_shared": False,
        "version": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        workflow = await memory.get_workflow(user_id="user-456", workflow_id="wf-123")

        assert workflow is not None
        assert workflow.id == "wf-123"
        assert workflow.workflow_name == "follow_up"
        mock_table.select.assert_called_with("*")


@pytest.mark.asyncio
async def test_get_workflow_raises_not_found() -> None:
    """Test get_workflow raises WorkflowNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import WorkflowNotFoundError
    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_single = MagicMock()
    mock_eq2.single.return_value = mock_single
    mock_execute = MagicMock()
    mock_single.execute.return_value = mock_execute
    mock_execute.data = None

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkflowNotFoundError):
            await memory.get_workflow(user_id="user-456", workflow_id="nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_get_workflow_retrieves_by_id -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement get_workflow**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def get_workflow(self, user_id: str, workflow_id: str) -> Workflow:
        """Retrieve a specific workflow by ID.

        Args:
            user_id: The user who owns the workflow.
            workflow_id: The workflow ID.

        Returns:
            The requested Workflow.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If retrieval fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("procedural_memories")
                .select("*")
                .eq("id", workflow_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise WorkflowNotFoundError(workflow_id)

            return Workflow.from_dict(response.data)

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get workflow", extra={"workflow_id": workflow_id})
            raise ProceduralMemoryError(f"Failed to get workflow: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_get_workflow_retrieves_by_id tests/test_procedural_memory.py::test_get_workflow_raises_not_found -v`
Expected: PASS (2 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement get_workflow for procedural memory

Add get_workflow method with:
- User isolation via user_id check
- WorkflowNotFoundError when not found
- Proper exception handling
- Unit tests for success and not-found cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement update_workflow Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for update_workflow**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_update_workflow_updates_in_supabase() -> None:
    """Test update_workflow updates workflow in Supabase."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory, Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-123",
        user_id="user-456",
        workflow_name="updated_workflow",
        description="Updated description",
        trigger_conditions={"event": "new_event"},
        steps=[{"action": "new_action"}],
        success_count=10,
        failure_count=2,
        is_shared=True,
        version=2,
        created_at=now,
        updated_at=now,
    )

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_eq1 = MagicMock()
    mock_update.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_execute = MagicMock()
    mock_eq2.execute.return_value = mock_execute
    mock_execute.data = [{"id": "wf-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.update_workflow(workflow)

        mock_table.update.assert_called_once()
        # Verify version was incremented
        call_args = mock_table.update.call_args
        assert call_args[0][0]["version"] == 3  # version + 1


@pytest.mark.asyncio
async def test_update_workflow_raises_not_found() -> None:
    """Test update_workflow raises WorkflowNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import WorkflowNotFoundError
    from src.memory.procedural import ProceduralMemory, Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="nonexistent",
        user_id="user-456",
        workflow_name="test",
        description="Test",
        trigger_conditions={},
        steps=[],
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_eq1 = MagicMock()
    mock_update.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_execute = MagicMock()
    mock_eq2.execute.return_value = mock_execute
    mock_execute.data = []  # No rows updated

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkflowNotFoundError):
            await memory.update_workflow(workflow)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_update_workflow_updates_in_supabase -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement update_workflow**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def update_workflow(self, workflow: Workflow) -> None:
        """Update an existing workflow.

        Increments the version number automatically.

        Args:
            workflow: The Workflow instance with updated data.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If update fails.
        """
        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "workflow_name": workflow.workflow_name,
                "description": workflow.description,
                "trigger_conditions": workflow.trigger_conditions,
                "steps": workflow.steps,
                "success_count": workflow.success_count,
                "failure_count": workflow.failure_count,
                "is_shared": workflow.is_shared,
                "version": workflow.version + 1,
                "updated_at": now.isoformat(),
            }

            response = (
                client.table("procedural_memories")
                .update(data)
                .eq("id", workflow.id)
                .eq("user_id", workflow.user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise WorkflowNotFoundError(workflow.id)

            logger.info(
                "Updated workflow",
                extra={
                    "workflow_id": workflow.id,
                    "user_id": workflow.user_id,
                    "new_version": workflow.version + 1,
                },
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update workflow", extra={"workflow_id": workflow.id})
            raise ProceduralMemoryError(f"Failed to update workflow: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_update_workflow_updates_in_supabase tests/test_procedural_memory.py::test_update_workflow_raises_not_found -v`
Expected: PASS (2 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement update_workflow with version increment

Add update_workflow method with:
- Automatic version increment on update
- User isolation via user_id check
- WorkflowNotFoundError when not found
- Unit tests for update and not-found cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement delete_workflow Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for delete_workflow**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_delete_workflow_removes_from_supabase() -> None:
    """Test delete_workflow removes workflow from Supabase."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_delete = MagicMock()
    mock_table.delete.return_value = mock_delete
    mock_eq1 = MagicMock()
    mock_delete.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_execute = MagicMock()
    mock_eq2.execute.return_value = mock_execute
    mock_execute.data = [{"id": "wf-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.delete_workflow(user_id="user-456", workflow_id="wf-123")

        mock_table.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_workflow_raises_not_found() -> None:
    """Test delete_workflow raises WorkflowNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import WorkflowNotFoundError
    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_delete = MagicMock()
    mock_table.delete.return_value = mock_delete
    mock_eq1 = MagicMock()
    mock_delete.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_execute = MagicMock()
    mock_eq2.execute.return_value = mock_execute
    mock_execute.data = []  # No rows deleted

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkflowNotFoundError):
            await memory.delete_workflow(user_id="user-456", workflow_id="nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_delete_workflow_removes_from_supabase -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement delete_workflow**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def delete_workflow(self, user_id: str, workflow_id: str) -> None:
        """Delete a workflow.

        Args:
            user_id: The user who owns the workflow.
            workflow_id: The workflow ID to delete.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If deletion fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("procedural_memories")
                .delete()
                .eq("id", workflow_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise WorkflowNotFoundError(workflow_id)

            logger.info(
                "Deleted workflow",
                extra={"workflow_id": workflow_id, "user_id": user_id},
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete workflow", extra={"workflow_id": workflow_id})
            raise ProceduralMemoryError(f"Failed to delete workflow: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_delete_workflow_removes_from_supabase tests/test_procedural_memory.py::test_delete_workflow_raises_not_found -v`
Expected: PASS (2 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement delete_workflow for procedural memory

Add delete_workflow method with:
- User isolation via user_id check
- WorkflowNotFoundError when not found
- Proper exception handling
- Unit tests for delete and not-found cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement record_outcome Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for record_outcome**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_record_outcome_increments_success_count() -> None:
    """Test record_outcome increments success_count on success."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    # First, setup select to get current counts
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq_select = MagicMock()
    mock_select.eq.return_value = mock_eq_select
    mock_single = MagicMock()
    mock_eq_select.single.return_value = mock_single
    mock_execute_select = MagicMock()
    mock_single.execute.return_value = mock_execute_select
    mock_execute_select.data = {"success_count": 10, "failure_count": 2}

    # Then, setup update
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_eq_update = MagicMock()
    mock_update.eq.return_value = mock_eq_update
    mock_execute_update = MagicMock()
    mock_eq_update.execute.return_value = mock_execute_update
    mock_execute_update.data = [{"id": "wf-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.record_outcome(workflow_id="wf-123", success=True)

        # Verify update was called with incremented success_count
        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args
        assert call_args[0][0]["success_count"] == 11


@pytest.mark.asyncio
async def test_record_outcome_increments_failure_count() -> None:
    """Test record_outcome increments failure_count on failure."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    # Setup select
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq_select = MagicMock()
    mock_select.eq.return_value = mock_eq_select
    mock_single = MagicMock()
    mock_eq_select.single.return_value = mock_single
    mock_execute_select = MagicMock()
    mock_single.execute.return_value = mock_execute_select
    mock_execute_select.data = {"success_count": 10, "failure_count": 2}

    # Setup update
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_eq_update = MagicMock()
    mock_update.eq.return_value = mock_eq_update
    mock_execute_update = MagicMock()
    mock_eq_update.execute.return_value = mock_execute_update
    mock_execute_update.data = [{"id": "wf-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.record_outcome(workflow_id="wf-123", success=False)

        # Verify update was called with incremented failure_count
        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args
        assert call_args[0][0]["failure_count"] == 3


@pytest.mark.asyncio
async def test_record_outcome_raises_not_found() -> None:
    """Test record_outcome raises WorkflowNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import WorkflowNotFoundError
    from src.memory.procedural import ProceduralMemory

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq_select = MagicMock()
    mock_select.eq.return_value = mock_eq_select
    mock_single = MagicMock()
    mock_eq_select.single.return_value = mock_single
    mock_execute_select = MagicMock()
    mock_single.execute.return_value = mock_execute_select
    mock_execute_select.data = None

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkflowNotFoundError):
            await memory.record_outcome(workflow_id="nonexistent", success=True)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_record_outcome_increments_success_count -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement record_outcome**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def record_outcome(self, workflow_id: str, success: bool) -> None:
        """Record the outcome of a workflow execution.

        Updates the success or failure count based on the result.

        Args:
            workflow_id: The workflow that was executed.
            success: True if execution succeeded, False if failed.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If update fails.
        """
        try:
            client = self._get_supabase_client()

            # Get current counts
            response = (
                client.table("procedural_memories")
                .select("success_count, failure_count")
                .eq("id", workflow_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise WorkflowNotFoundError(workflow_id)

            current_success = response.data["success_count"]
            current_failure = response.data["failure_count"]

            # Update the appropriate counter
            now = datetime.now(UTC)
            if success:
                update_data = {
                    "success_count": current_success + 1,
                    "updated_at": now.isoformat(),
                }
            else:
                update_data = {
                    "failure_count": current_failure + 1,
                    "updated_at": now.isoformat(),
                }

            client.table("procedural_memories").update(update_data).eq(
                "id", workflow_id
            ).execute()

            logger.info(
                "Recorded workflow outcome",
                extra={
                    "workflow_id": workflow_id,
                    "success": success,
                    "new_success_count": current_success + (1 if success else 0),
                    "new_failure_count": current_failure + (0 if success else 1),
                },
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception(
                "Failed to record outcome", extra={"workflow_id": workflow_id}
            )
            raise ProceduralMemoryError(f"Failed to record outcome: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_record_outcome_increments_success_count tests/test_procedural_memory.py::test_record_outcome_increments_failure_count tests/test_procedural_memory.py::test_record_outcome_raises_not_found -v`
Expected: PASS (3 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement record_outcome for workflow learning

Add record_outcome method with:
- Increment success_count on successful execution
- Increment failure_count on failed execution
- WorkflowNotFoundError when workflow not found
- Unit tests for success, failure, and not-found cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement find_matching_workflow Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for find_matching_workflow**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_find_matching_workflow_returns_best_match() -> None:
    """Test find_matching_workflow returns workflow matching trigger conditions."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_execute = MagicMock()
    mock_eq.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-123",
            "user_id": "user-456",
            "workflow_name": "meeting_followup",
            "description": "Follow up after meeting",
            "trigger_conditions": {"event": "meeting_completed", "lead_stage": "qualified"},
            "steps": [{"action": "send_email"}],
            "success_count": 20,
            "failure_count": 5,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "wf-456",
            "user_id": "user-456",
            "workflow_name": "cold_outreach",
            "description": "Cold outreach sequence",
            "trigger_conditions": {"event": "new_lead", "source": "conference"},
            "steps": [{"action": "research"}],
            "success_count": 10,
            "failure_count": 10,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        context = {"event": "meeting_completed", "lead_stage": "qualified"}
        workflow = await memory.find_matching_workflow(user_id="user-456", context=context)

        assert workflow is not None
        assert workflow.id == "wf-123"
        assert workflow.workflow_name == "meeting_followup"


@pytest.mark.asyncio
async def test_find_matching_workflow_returns_none_when_no_match() -> None:
    """Test find_matching_workflow returns None when no workflows match."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_execute = MagicMock()
    mock_eq.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-123",
            "user_id": "user-456",
            "workflow_name": "meeting_followup",
            "description": "Follow up after meeting",
            "trigger_conditions": {"event": "meeting_completed"},
            "steps": [{"action": "send_email"}],
            "success_count": 20,
            "failure_count": 5,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        context = {"event": "unknown_event"}
        workflow = await memory.find_matching_workflow(user_id="user-456", context=context)

        assert workflow is None


@pytest.mark.asyncio
async def test_find_matching_workflow_prefers_higher_success_rate() -> None:
    """Test find_matching_workflow prefers workflow with higher success rate."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_execute = MagicMock()
    mock_eq.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-low",
            "user_id": "user-456",
            "workflow_name": "workflow_low",
            "description": "Low success rate",
            "trigger_conditions": {"event": "test"},
            "steps": [{"action": "a"}],
            "success_count": 10,
            "failure_count": 90,  # 10% success rate
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "wf-high",
            "user_id": "user-456",
            "workflow_name": "workflow_high",
            "description": "High success rate",
            "trigger_conditions": {"event": "test"},
            "steps": [{"action": "b"}],
            "success_count": 90,
            "failure_count": 10,  # 90% success rate
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        context = {"event": "test"}
        workflow = await memory.find_matching_workflow(user_id="user-456", context=context)

        assert workflow is not None
        assert workflow.id == "wf-high"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_find_matching_workflow_returns_best_match -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement find_matching_workflow**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def find_matching_workflow(
        self, user_id: str, context: dict[str, Any]
    ) -> Workflow | None:
        """Find the best matching workflow for a given context.

        Matches trigger conditions against the provided context and
        returns the workflow with the highest success rate among matches.

        Args:
            user_id: The user to find workflows for.
            context: The current context to match against trigger conditions.

        Returns:
            The best matching Workflow, or None if no match found.

        Raises:
            ProceduralMemoryError: If the query fails.
        """
        try:
            client = self._get_supabase_client()

            # Get all workflows for this user
            response = (
                client.table("procedural_memories")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data:
                return None

            # Find workflows whose trigger conditions match the context
            matching_workflows: list[Workflow] = []

            for row in response.data:
                workflow = Workflow.from_dict(row)
                trigger_conditions = workflow.trigger_conditions

                # Check if all trigger conditions are satisfied by context
                if self._matches_trigger_conditions(trigger_conditions, context):
                    matching_workflows.append(workflow)

            if not matching_workflows:
                return None

            # Return workflow with highest success rate
            best_workflow = max(matching_workflows, key=lambda w: w.success_rate)

            logger.info(
                "Found matching workflow",
                extra={
                    "workflow_id": best_workflow.id,
                    "workflow_name": best_workflow.workflow_name,
                    "success_rate": best_workflow.success_rate,
                    "context_keys": list(context.keys()),
                },
            )

            return best_workflow

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to find matching workflow")
            raise ProceduralMemoryError(f"Failed to find matching workflow: {e}") from e

    def _matches_trigger_conditions(
        self, trigger_conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Check if context satisfies trigger conditions.

        All trigger conditions must be present in context with matching values.

        Args:
            trigger_conditions: The workflow's trigger conditions.
            context: The current context to match against.

        Returns:
            True if all trigger conditions are satisfied.
        """
        for key, value in trigger_conditions.items():
            if key not in context:
                return False
            if context[key] != value:
                return False
        return True
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_find_matching_workflow_returns_best_match tests/test_procedural_memory.py::test_find_matching_workflow_returns_none_when_no_match tests/test_procedural_memory.py::test_find_matching_workflow_prefers_higher_success_rate -v`
Expected: PASS (3 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement find_matching_workflow for trigger matching

Add find_matching_workflow method with:
- Match trigger conditions against context
- Prefer workflows with higher success rate
- Return None when no workflows match
- Unit tests for matching, no-match, and preference cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement list_workflows Method

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test for list_workflows**

Append to `backend/tests/test_procedural_memory.py`:

```python


@pytest.mark.asyncio
async def test_list_workflows_returns_user_workflows() -> None:
    """Test list_workflows returns workflows for user."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_execute = MagicMock()
    mock_eq.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-1",
            "user_id": "user-456",
            "workflow_name": "workflow_1",
            "description": "First workflow",
            "trigger_conditions": {},
            "steps": [],
            "success_count": 10,
            "failure_count": 2,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "wf-2",
            "user_id": "user-456",
            "workflow_name": "workflow_2",
            "description": "Second workflow",
            "trigger_conditions": {},
            "steps": [],
            "success_count": 5,
            "failure_count": 1,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        workflows = await memory.list_workflows(user_id="user-456")

        assert len(workflows) == 2
        assert workflows[0].id == "wf-1"
        assert workflows[1].id == "wf-2"


@pytest.mark.asyncio
async def test_list_workflows_includes_shared_workflows() -> None:
    """Test list_workflows includes shared workflows when include_shared is True."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_or = MagicMock()
    mock_select.or_.return_value = mock_or
    mock_execute = MagicMock()
    mock_or.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-own",
            "user_id": "user-456",
            "workflow_name": "own_workflow",
            "description": "Own workflow",
            "trigger_conditions": {},
            "steps": [],
            "success_count": 10,
            "failure_count": 2,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "id": "wf-shared",
            "user_id": "other-user",
            "workflow_name": "shared_workflow",
            "description": "Shared workflow",
            "trigger_conditions": {},
            "steps": [],
            "success_count": 50,
            "failure_count": 5,
            "is_shared": True,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        workflows = await memory.list_workflows(user_id="user-456", include_shared=True)

        assert len(workflows) == 2
        # Verify or_ was called for shared workflows
        mock_select.or_.assert_called_once()


@pytest.mark.asyncio
async def test_list_workflows_excludes_shared_when_disabled() -> None:
    """Test list_workflows excludes shared workflows when include_shared is False."""
    from unittest.mock import MagicMock, patch

    from src.memory.procedural import ProceduralMemory

    now = datetime.now(UTC)
    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_execute = MagicMock()
    mock_eq.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "wf-own",
            "user_id": "user-456",
            "workflow_name": "own_workflow",
            "description": "Own workflow",
            "trigger_conditions": {},
            "steps": [],
            "success_count": 10,
            "failure_count": 2,
            "is_shared": False,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        workflows = await memory.list_workflows(user_id="user-456", include_shared=False)

        assert len(workflows) == 1
        # Verify eq was called (not or_)
        mock_select.eq.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_list_workflows_returns_user_workflows -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Implement list_workflows**

Replace the placeholder in `backend/src/memory/procedural.py`:

```python
    async def list_workflows(
        self, user_id: str, include_shared: bool = True
    ) -> list[Workflow]:
        """List all workflows available to a user.

        Args:
            user_id: The user to list workflows for.
            include_shared: Whether to include shared workflows from other users.

        Returns:
            List of Workflow instances.

        Raises:
            ProceduralMemoryError: If the query fails.
        """
        try:
            client = self._get_supabase_client()

            query = client.table("procedural_memories").select("*")

            if include_shared:
                # Get user's own workflows OR shared workflows
                query = query.or_(f"user_id.eq.{user_id},is_shared.eq.true")
            else:
                # Only get user's own workflows
                query = query.eq("user_id", user_id)

            response = query.execute()

            if not response.data:
                return []

            workflows = [Workflow.from_dict(row) for row in response.data]

            logger.info(
                "Listed workflows",
                extra={
                    "user_id": user_id,
                    "include_shared": include_shared,
                    "count": len(workflows),
                },
            )

            return workflows

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to list workflows")
            raise ProceduralMemoryError(f"Failed to list workflows: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_list_workflows_returns_user_workflows tests/test_procedural_memory.py::test_list_workflows_includes_shared_workflows tests/test_procedural_memory.py::test_list_workflows_excludes_shared_when_disabled -v`
Expected: PASS (3 tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/procedural.py --strict && ruff check src/memory/procedural.py && ruff format src/memory/procedural.py --check`
Expected: All pass

**Step 6: Commit**

```bash
cd backend && git add src/memory/procedural.py tests/test_procedural_memory.py && git commit -m "$(cat <<'EOF'
feat(memory): implement list_workflows with shared workflow support

Add list_workflows method with:
- Return all workflows for a user
- Optional inclusion of shared workflows from other users
- Unit tests for listing, shared, and non-shared cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Update Memory Module Exports

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Read current exports**

Verify current state of `backend/src/memory/__init__.py`.

**Step 2: Add ProceduralMemory exports**

Update `backend/src/memory/__init__.py`:

```python
"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
"""

from src.memory.episodic import Episode, EpisodicMemory
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory
from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)

__all__ = [
    # Working Memory
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    # Semantic Memory
    "FactSource",
    "SemanticFact",
    "SemanticMemory",
    # Procedural Memory
    "ProceduralMemory",
    "Workflow",
]
```

**Step 3: Run quality gates**

Run: `cd backend && mypy src/memory/__init__.py --strict && ruff check src/memory/__init__.py && ruff format src/memory/__init__.py --check`
Expected: All pass

**Step 4: Run all tests**

Run: `cd backend && pytest tests/test_procedural_memory.py tests/test_working_memory.py tests/test_episodic_memory.py tests/test_semantic_memory.py -v`
Expected: All pass

**Step 5: Commit**

```bash
cd backend && git add src/memory/__init__.py && git commit -m "$(cat <<'EOF'
feat(memory): export ProceduralMemory and Workflow from memory module

Update memory module exports to include ProceduralMemory and Workflow
classes for use by other parts of the application.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Create Supabase Migration for procedural_memories Table

**Files:**
- Create: `supabase/migrations/20260201000000_create_procedural_memories.sql`

**Step 1: Create migrations directory if needed**

Run: `mkdir -p supabase/migrations`

**Step 2: Create migration file**

Create `supabase/migrations/20260201000000_create_procedural_memories.sql`:

```sql
-- Create procedural_memories table for storing learned workflows
-- Part of US-205: Procedural Memory Implementation

CREATE TABLE IF NOT EXISTS procedural_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workflow_name TEXT NOT NULL,
    description TEXT,
    trigger_conditions JSONB NOT NULL DEFAULT '{}',
    steps JSONB NOT NULL DEFAULT '[]',
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for user lookups (most common query pattern)
CREATE INDEX idx_procedural_memories_user_id ON procedural_memories(user_id);

-- Index for finding shared workflows
CREATE INDEX idx_procedural_memories_is_shared ON procedural_memories(is_shared) WHERE is_shared = TRUE;

-- GIN index for trigger condition JSONB queries
CREATE INDEX idx_procedural_memories_trigger ON procedural_memories USING GIN(trigger_conditions);

-- Enable Row Level Security
ALTER TABLE procedural_memories ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own workflows and shared workflows
CREATE POLICY "Users can read own and shared workflows"
    ON procedural_memories
    FOR SELECT
    USING (user_id = auth.uid() OR is_shared = TRUE);

-- Policy: Users can insert their own workflows
CREATE POLICY "Users can insert own workflows"
    ON procedural_memories
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Policy: Users can update their own workflows
CREATE POLICY "Users can update own workflows"
    ON procedural_memories
    FOR UPDATE
    USING (user_id = auth.uid());

-- Policy: Users can delete their own workflows
CREATE POLICY "Users can delete own workflows"
    ON procedural_memories
    FOR DELETE
    USING (user_id = auth.uid());

-- Add comment for documentation
COMMENT ON TABLE procedural_memories IS 'Stores learned workflow patterns with success tracking for procedural memory';
COMMENT ON COLUMN procedural_memories.trigger_conditions IS 'JSONB conditions that determine when this workflow should be used';
COMMENT ON COLUMN procedural_memories.steps IS 'Ordered JSONB array of actions to perform in this workflow';
COMMENT ON COLUMN procedural_memories.success_count IS 'Number of times this workflow executed successfully';
COMMENT ON COLUMN procedural_memories.failure_count IS 'Number of times this workflow failed';
COMMENT ON COLUMN procedural_memories.is_shared IS 'If true, workflow is available to all users in the same company';
COMMENT ON COLUMN procedural_memories.version IS 'Incremented on each update for optimistic concurrency';
```

**Step 3: Commit**

```bash
git add supabase/migrations/20260201000000_create_procedural_memories.sql && git commit -m "$(cat <<'EOF'
feat(db): add procedural_memories table migration

Create Supabase migration for procedural_memories table with:
- Full schema per US-205 requirements
- JSONB columns for trigger_conditions and steps
- Success/failure tracking columns
- Shared workflow support
- Row Level Security policies
- Appropriate indexes for query patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final Quality Gates and Full Test Run

**Files:**
- All modified files in backend/

**Step 1: Run full backend quality gates**

Run: `cd backend && mypy src/ --strict && ruff check src/ && ruff format src/ --check`
Expected: All pass

**Step 2: Run all backend tests**

Run: `cd backend && pytest tests/ -v`
Expected: All pass

**Step 3: Verify procedural memory tests specifically**

Run: `cd backend && pytest tests/test_procedural_memory.py -v --tb=short`
Expected: All 24 tests pass

**Step 4: Final commit if any cleanup needed**

If any formatting or quality fixes were needed:

```bash
cd backend && git add -A && git commit -m "$(cat <<'EOF'
chore: fix quality gate issues for procedural memory

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-205: Procedural Memory Implementation with:

1. **Workflow Dataclass** - Full data model with serialization, success_rate property
2. **ProceduralMemory Service** - Async service class with all CRUD operations
3. **Trigger Matching** - Context-based workflow discovery with success rate preference
4. **Outcome Recording** - Success/failure tracking for learning
5. **Shared Workflows** - Support for company-wide workflow sharing
6. **Version History** - Automatic version increment on updates
7. **Supabase Migration** - Complete schema with RLS policies and indexes

Total: 12 tasks, ~24 tests, following TDD with frequent commits.
