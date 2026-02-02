# US-206: Prospective Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement prospective memory for future tasks, allowing ARIA to remember commitments, follow-ups, and scheduled reminders.

**Architecture:** Prospective memory stores time-based, event-based, and condition-based tasks in Supabase. Tasks have statuses (pending, completed, cancelled, overdue) and can link to goals and leads. The implementation mirrors the existing ProceduralMemory pattern with dataclass models and async service methods.

**Tech Stack:** Python 3.11+, Supabase (PostgreSQL), Pydantic/dataclasses, pytest for testing

---

## Task 1: Add ProspectiveMemory Exception Classes

**Files:**
- Modify: `backend/src/core/exceptions.py`
- Test: `backend/tests/test_exceptions.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_exceptions.py`:

```python
def test_prospective_memory_error_initialization() -> None:
    """Test ProspectiveMemoryError initializes correctly."""
    from src.core.exceptions import ProspectiveMemoryError

    error = ProspectiveMemoryError("Test error message")

    assert str(error) == "Prospective memory operation failed: Test error message"
    assert error.code == "PROSPECTIVE_MEMORY_ERROR"
    assert error.status_code == 500


def test_task_not_found_error_initialization() -> None:
    """Test TaskNotFoundError initializes correctly."""
    from src.core.exceptions import TaskNotFoundError

    error = TaskNotFoundError("task-123")

    assert "task-123" in str(error)
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_exceptions.py::test_prospective_memory_error_initialization tests/test_exceptions.py::test_task_not_found_error_initialization -v`
Expected: FAIL with "ImportError: cannot import name 'ProspectiveMemoryError'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` (after ProceduralMemoryError):

```python
class ProspectiveMemoryError(ARIAException):
    """Prospective memory operation error (500).

    Used for failures when storing or retrieving tasks from Supabase.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize prospective memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Prospective memory operation failed: {message}",
            code="PROSPECTIVE_MEMORY_ERROR",
            status_code=500,
        )


class TaskNotFoundError(NotFoundError):
    """Prospective task not found error (404)."""

    def __init__(self, task_id: str) -> None:
        """Initialize task not found error.

        Args:
            task_id: The ID of the task that was not found.
        """
        super().__init__(resource="Task", resource_id=task_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_exceptions.py::test_prospective_memory_error_initialization tests/test_exceptions.py::test_task_not_found_error_initialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_exceptions.py
git commit -m "$(cat <<'EOF'
feat(memory): add ProspectiveMemoryError and TaskNotFoundError exceptions

Add exception classes for prospective memory operations:
- ProspectiveMemoryError for general operation failures
- TaskNotFoundError for task lookup failures

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Database Migration

**Files:**
- Create: `supabase/migrations/20260201000001_create_prospective_memories.sql`

**Step 1: Write the migration**

Create `supabase/migrations/20260201000001_create_prospective_memories.sql`:

```sql
-- Create prospective_memories table for storing future tasks and reminders
-- Part of US-206: Prospective Memory Implementation

CREATE TABLE IF NOT EXISTS prospective_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    description TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('time', 'event', 'condition')),
    trigger_config JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'overdue')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    related_goal_id UUID,
    related_lead_id UUID,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for user + status queries (most common pattern)
CREATE INDEX idx_prospective_memories_user_status ON prospective_memories(user_id, status);

-- Index for status queries (finding overdue, pending tasks)
CREATE INDEX idx_prospective_memories_status ON prospective_memories(status);

-- Index for priority queries
CREATE INDEX idx_prospective_memories_priority ON prospective_memories(user_id, priority);

-- GIN index for trigger_config JSONB queries
CREATE INDEX idx_prospective_memories_trigger ON prospective_memories USING GIN(trigger_config);

-- Index for related goal lookups
CREATE INDEX idx_prospective_memories_goal ON prospective_memories(related_goal_id) WHERE related_goal_id IS NOT NULL;

-- Index for related lead lookups
CREATE INDEX idx_prospective_memories_lead ON prospective_memories(related_lead_id) WHERE related_lead_id IS NOT NULL;

-- Enable Row Level Security
ALTER TABLE prospective_memories ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own tasks
CREATE POLICY "Users can read own tasks"
    ON prospective_memories
    FOR SELECT
    USING (user_id = auth.uid());

-- Policy: Users can insert their own tasks
CREATE POLICY "Users can insert own tasks"
    ON prospective_memories
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Policy: Users can update their own tasks
CREATE POLICY "Users can update own tasks"
    ON prospective_memories
    FOR UPDATE
    USING (user_id = auth.uid());

-- Policy: Users can delete their own tasks
CREATE POLICY "Users can delete own tasks"
    ON prospective_memories
    FOR DELETE
    USING (user_id = auth.uid());

-- Add comments for documentation
COMMENT ON TABLE prospective_memories IS 'Stores future tasks, reminders, and follow-ups for prospective memory';
COMMENT ON COLUMN prospective_memories.trigger_type IS 'Type of trigger: time (due_at), event (external trigger), or condition (state-based)';
COMMENT ON COLUMN prospective_memories.trigger_config IS 'JSONB config for trigger. time: {"due_at": timestamp}, event: {"event": "email_received", "from": "john@acme.com"}, condition: {"field": "lead_stage", "value": "qualified"}';
COMMENT ON COLUMN prospective_memories.status IS 'Task status: pending, completed, cancelled, or overdue';
COMMENT ON COLUMN prospective_memories.priority IS 'Task priority: low, medium, high, or urgent';
COMMENT ON COLUMN prospective_memories.related_goal_id IS 'Optional link to a goal this task supports';
COMMENT ON COLUMN prospective_memories.related_lead_id IS 'Optional link to a lead this task relates to';
```

**Step 2: Verify migration syntax**

Run: `cd supabase && supabase db lint`
Expected: No errors (or run locally with `supabase db reset` if available)

**Step 3: Commit**

```bash
git add supabase/migrations/20260201000001_create_prospective_memories.sql
git commit -m "$(cat <<'EOF'
feat(db): add prospective_memories table migration

Create Supabase table for prospective memory with:
- Trigger types: time, event, condition
- Status tracking: pending, completed, cancelled, overdue
- Priority levels: low, medium, high, urgent
- Links to goals and leads
- RLS policies for user isolation
- Indexes for common query patterns

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create ProspectiveTask Dataclass

**Files:**
- Create: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_prospective_memory.py`:

```python
"""Tests for prospective memory module."""

import json
from datetime import UTC, datetime
from typing import Any


def test_trigger_type_enum_values() -> None:
    """Test TriggerType enum has required values."""
    from src.memory.prospective import TriggerType

    assert TriggerType.TIME.value == "time"
    assert TriggerType.EVENT.value == "event"
    assert TriggerType.CONDITION.value == "condition"


def test_task_status_enum_values() -> None:
    """Test TaskStatus enum has required values."""
    from src.memory.prospective import TaskStatus

    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.CANCELLED.value == "cancelled"
    assert TaskStatus.OVERDUE.value == "overdue"


def test_task_priority_enum_values() -> None:
    """Test TaskPriority enum has required values."""
    from src.memory.prospective import TaskPriority

    assert TaskPriority.LOW.value == "low"
    assert TaskPriority.MEDIUM.value == "medium"
    assert TaskPriority.HIGH.value == "high"
    assert TaskPriority.URGENT.value == "urgent"


def test_prospective_task_initialization() -> None:
    """Test ProspectiveTask initializes with required fields."""
    from src.memory.prospective import (
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    due_at = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
    task = ProspectiveTask(
        id="task-123",
        user_id="user-456",
        task="Follow up with Dr. Smith",
        description="Send research paper summary",
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": due_at.isoformat()},
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        related_goal_id="goal-789",
        related_lead_id="lead-012",
        completed_at=None,
        created_at=now,
    )

    assert task.id == "task-123"
    assert task.user_id == "user-456"
    assert task.task == "Follow up with Dr. Smith"
    assert task.description == "Send research paper summary"
    assert task.trigger_type == TriggerType.TIME
    assert task.trigger_config["due_at"] == due_at.isoformat()
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.HIGH
    assert task.related_goal_id == "goal-789"
    assert task.related_lead_id == "lead-012"
    assert task.completed_at is None
    assert task.created_at == now


def test_prospective_task_to_dict_serializes_correctly() -> None:
    """Test ProspectiveTask.to_dict returns a serializable dictionary."""
    from src.memory.prospective import (
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    due_at = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
    task = ProspectiveTask(
        id="task-123",
        user_id="user-456",
        task="Follow up with Dr. Smith",
        description="Send research paper summary",
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": due_at.isoformat()},
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        related_goal_id="goal-789",
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    data = task.to_dict()

    assert data["id"] == "task-123"
    assert data["user_id"] == "user-456"
    assert data["task"] == "Follow up with Dr. Smith"
    assert data["trigger_type"] == "time"
    assert data["status"] == "pending"
    assert data["priority"] == "high"
    assert data["related_goal_id"] == "goal-789"
    assert data["related_lead_id"] is None
    assert data["completed_at"] is None
    assert data["created_at"] == now.isoformat()

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_prospective_task_from_dict_deserializes_correctly() -> None:
    """Test ProspectiveTask.from_dict creates ProspectiveTask from dictionary."""
    from src.memory.prospective import (
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    completed = datetime(2026, 2, 10, 15, 30, 0, tzinfo=UTC)
    data: dict[str, Any] = {
        "id": "task-123",
        "user_id": "user-456",
        "task": "Review proposal",
        "description": "Check budget section",
        "trigger_type": "event",
        "trigger_config": {"event": "email_received", "from": "cfo@acme.com"},
        "status": "completed",
        "priority": "medium",
        "related_goal_id": None,
        "related_lead_id": "lead-012",
        "completed_at": completed.isoformat(),
        "created_at": now.isoformat(),
    }

    task = ProspectiveTask.from_dict(data)

    assert task.id == "task-123"
    assert task.user_id == "user-456"
    assert task.task == "Review proposal"
    assert task.description == "Check budget section"
    assert task.trigger_type == TriggerType.EVENT
    assert task.trigger_config == {"event": "email_received", "from": "cfo@acme.com"}
    assert task.status == TaskStatus.COMPLETED
    assert task.priority == TaskPriority.MEDIUM
    assert task.related_goal_id is None
    assert task.related_lead_id == "lead-012"
    assert task.completed_at == completed
    assert task.created_at == now


def test_prospective_task_from_dict_handles_datetime_objects() -> None:
    """Test ProspectiveTask.from_dict handles datetime objects directly."""
    from src.memory.prospective import (
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    data: dict[str, Any] = {
        "id": "task-123",
        "user_id": "user-456",
        "task": "Test task",
        "description": None,
        "trigger_type": "condition",
        "trigger_config": {"field": "lead_stage", "value": "qualified"},
        "status": "pending",
        "priority": "low",
        "related_goal_id": None,
        "related_lead_id": None,
        "completed_at": None,
        "created_at": now,  # datetime object, not string
    }

    task = ProspectiveTask.from_dict(data)

    assert task.created_at == now
    assert task.completed_at is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_trigger_type_enum_values -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.prospective'"

**Step 3: Write minimal implementation**

Create `backend/src/memory/prospective.py`:

```python
"""Prospective memory module for storing future tasks and reminders.

Prospective memory stores tasks for future execution with:
- Time-based triggers (due dates/times)
- Event-based triggers (external events)
- Condition-based triggers (state changes)
- Status tracking (pending, completed, cancelled, overdue)
- Priority levels for task ordering
- Links to related goals and leads

Tasks are stored in Supabase for structured querying and
integration with the rest of the application state.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of triggers for prospective tasks."""

    TIME = "time"  # Due at specific time
    EVENT = "event"  # Triggered by external event
    CONDITION = "condition"  # Triggered by state change


class TaskStatus(Enum):
    """Status values for prospective tasks."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class TaskPriority(Enum):
    """Priority levels for prospective tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProspectiveTask:
    """A prospective memory record representing a future task.

    Stores reminders, follow-ups, and scheduled tasks with
    various trigger mechanisms and priority tracking.
    """

    id: str
    user_id: str
    task: str  # Short task description
    description: str | None  # Detailed description
    trigger_type: TriggerType
    trigger_config: dict[str, Any]  # Trigger-specific configuration
    status: TaskStatus
    priority: TaskPriority
    related_goal_id: str | None  # Optional link to a goal
    related_lead_id: str | None  # Optional link to a lead
    completed_at: datetime | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "task": self.task,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "trigger_config": self.trigger_config,
            "status": self.status.value,
            "priority": self.priority.value,
            "related_goal_id": self.related_goal_id,
            "related_lead_id": self.related_lead_id,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProspectiveTask":
        """Create a ProspectiveTask instance from a dictionary.

        Args:
            data: Dictionary containing task data.

        Returns:
            ProspectiveTask instance with restored state.
        """
        # Parse created_at
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        # Parse completed_at (may be None)
        completed_at = data.get("completed_at")
        if completed_at is not None and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            task=data["task"],
            description=data.get("description"),
            trigger_type=TriggerType(data["trigger_type"]),
            trigger_config=data["trigger_config"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]),
            related_goal_id=data.get("related_goal_id"),
            related_lead_id=data.get("related_lead_id"),
            completed_at=completed_at,
            created_at=created_at,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): add ProspectiveTask dataclass and enums

Add core data structures for prospective memory:
- TriggerType enum (time, event, condition)
- TaskStatus enum (pending, completed, cancelled, overdue)
- TaskPriority enum (low, medium, high, urgent)
- ProspectiveTask dataclass with serialization

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement ProspectiveMemory.create_task

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
import pytest
from unittest.mock import MagicMock


def test_prospective_memory_has_required_methods() -> None:
    """Test ProspectiveMemory class has required interface methods."""
    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

    assert hasattr(memory, "create_task")
    assert hasattr(memory, "get_task")
    assert hasattr(memory, "update_task")
    assert hasattr(memory, "delete_task")
    assert hasattr(memory, "complete_task")
    assert hasattr(memory, "cancel_task")
    assert hasattr(memory, "get_upcoming_tasks")
    assert hasattr(memory, "get_overdue_tasks")
    assert hasattr(memory, "get_tasks_for_goal")
    assert hasattr(memory, "get_tasks_for_lead")


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mock Supabase client for testing."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


@pytest.mark.asyncio
async def test_create_task_stores_in_supabase(mock_supabase_client: MagicMock) -> None:
    """Test that create_task stores task in Supabase."""
    from unittest.mock import patch

    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    due_at = datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC)
    task = ProspectiveTask(
        id="",  # Will be generated
        user_id="user-456",
        task="Follow up with Dr. Smith",
        description="Send research paper",
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": due_at.isoformat()},
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        related_goal_id=None,
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    memory = ProspectiveMemory()

    mock_table = mock_supabase_client.table.return_value
    mock_insert = MagicMock()
    mock_table.insert.return_value = mock_insert
    mock_execute = MagicMock()
    mock_insert.execute.return_value = mock_execute
    mock_execute.data = [{"id": "generated-uuid-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_supabase_client

        result = await memory.create_task(task)

        assert result != ""
        assert len(result) > 0
        mock_supabase_client.table.assert_called_with("prospective_memories")
        mock_table.insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_generates_id_if_missing() -> None:
    """Test that create_task generates ID if not provided."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    task = ProspectiveTask(
        id="",  # Empty ID
        user_id="user-456",
        task="Test task",
        description=None,
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": now.isoformat()},
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        related_goal_id=None,
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    memory = ProspectiveMemory()

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

        result = await memory.create_task(task)

        assert result != ""
        call_args = mock_table.insert.call_args
        assert "id" in call_args[0][0]
        assert call_args[0][0]["id"] != ""
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_prospective_memory_has_required_methods -v`
Expected: FAIL with "ImportError: cannot import name 'ProspectiveMemory'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/prospective.py`:

```python
import uuid
from datetime import UTC


class ProspectiveMemory:
    """Service class for prospective memory operations.

    Provides async interface for storing, retrieving, and managing
    future tasks and reminders. Uses Supabase as the underlying storage
    for structured querying and status tracking.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            ProspectiveMemoryError: If client initialization fails.
        """
        from src.core.exceptions import ProspectiveMemoryError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise ProspectiveMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create_task(self, task: ProspectiveTask) -> str:
        """Create a new task in prospective memory.

        Args:
            task: The ProspectiveTask instance to store.

        Returns:
            The ID of the stored task.

        Raises:
            ProspectiveMemoryError: If storage fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            task_id = task.id if task.id else str(uuid.uuid4())

            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": task_id,
                "user_id": task.user_id,
                "task": task.task,
                "description": task.description,
                "trigger_type": task.trigger_type.value,
                "trigger_config": task.trigger_config,
                "status": task.status.value,
                "priority": task.priority.value,
                "related_goal_id": task.related_goal_id,
                "related_lead_id": task.related_lead_id,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "created_at": now.isoformat(),
            }

            response = client.table("prospective_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise ProspectiveMemoryError("Failed to insert task")

            logger.info(
                "Created prospective task",
                extra={
                    "task_id": task_id,
                    "user_id": task.user_id,
                    "task": task.task,
                    "trigger_type": task.trigger_type.value,
                },
            )

            return task_id

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create task")
            raise ProspectiveMemoryError(f"Failed to create task: {e}") from e

    async def get_task(self, user_id: str, task_id: str) -> ProspectiveTask:
        """Placeholder for get_task method."""
        raise NotImplementedError

    async def update_task(self, task: ProspectiveTask) -> None:
        """Placeholder for update_task method."""
        raise NotImplementedError

    async def delete_task(self, user_id: str, task_id: str) -> None:
        """Placeholder for delete_task method."""
        raise NotImplementedError

    async def complete_task(self, user_id: str, task_id: str) -> None:
        """Placeholder for complete_task method."""
        raise NotImplementedError

    async def cancel_task(self, user_id: str, task_id: str) -> None:
        """Placeholder for cancel_task method."""
        raise NotImplementedError

    async def get_upcoming_tasks(
        self, user_id: str, limit: int = 10
    ) -> list[ProspectiveTask]:
        """Placeholder for get_upcoming_tasks method."""
        raise NotImplementedError

    async def get_overdue_tasks(self, user_id: str) -> list[ProspectiveTask]:
        """Placeholder for get_overdue_tasks method."""
        raise NotImplementedError

    async def get_tasks_for_goal(
        self, user_id: str, goal_id: str
    ) -> list[ProspectiveTask]:
        """Placeholder for get_tasks_for_goal method."""
        raise NotImplementedError

    async def get_tasks_for_lead(
        self, user_id: str, lead_id: str
    ) -> list[ProspectiveTask]:
        """Placeholder for get_tasks_for_lead method."""
        raise NotImplementedError
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_prospective_memory_has_required_methods tests/test_prospective_memory.py::test_create_task_stores_in_supabase tests/test_prospective_memory.py::test_create_task_generates_id_if_missing -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory.create_task

Add ProspectiveMemory service class with create_task method:
- Stores tasks in Supabase prospective_memories table
- Auto-generates UUID if not provided
- Logs task creation with structured metadata

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement ProspectiveMemory.get_task

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_get_task_retrieves_by_id() -> None:
    """Test get_task retrieves specific task by ID."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    now = datetime.now(UTC)
    memory = ProspectiveMemory()

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
        "id": "task-123",
        "user_id": "user-456",
        "task": "Follow up",
        "description": "Send email",
        "trigger_type": "time",
        "trigger_config": {"due_at": "2026-02-15T10:00:00+00:00"},
        "status": "pending",
        "priority": "high",
        "related_goal_id": None,
        "related_lead_id": None,
        "completed_at": None,
        "created_at": now.isoformat(),
    }

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        task = await memory.get_task(user_id="user-456", task_id="task-123")

        assert task is not None
        assert task.id == "task-123"
        assert task.task == "Follow up"
        mock_table.select.assert_called_with("*")


@pytest.mark.asyncio
async def test_get_task_raises_not_found() -> None:
    """Test get_task raises TaskNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import TaskNotFoundError
    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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

        with pytest.raises(TaskNotFoundError):
            await memory.get_task(user_id="user-456", task_id="nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_task_retrieves_by_id -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder `get_task` method in `backend/src/memory/prospective.py`:

```python
    async def get_task(self, user_id: str, task_id: str) -> ProspectiveTask:
        """Retrieve a specific task by ID.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID.

        Returns:
            The requested ProspectiveTask.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If retrieval fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("id", task_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise TaskNotFoundError(task_id)

            return ProspectiveTask.from_dict(response.data)

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to get task: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_task_retrieves_by_id tests/test_prospective_memory.py::test_get_task_raises_not_found -v`
Expected: Both tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory.get_task

Add get_task method to retrieve task by ID:
- Queries Supabase by task_id and user_id
- Returns ProspectiveTask deserialized from database
- Raises TaskNotFoundError when not found

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement ProspectiveMemory.update_task and delete_task

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_update_task_updates_in_supabase() -> None:
    """Test update_task updates task in Supabase."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    task = ProspectiveTask(
        id="task-123",
        user_id="user-456",
        task="Updated task",
        description="Updated description",
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": "2026-02-20T10:00:00+00:00"},
        status=TaskStatus.PENDING,
        priority=TaskPriority.URGENT,
        related_goal_id="goal-789",
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    memory = ProspectiveMemory()

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
    mock_execute.data = [{"id": "task-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.update_task(task)

        mock_table.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_raises_not_found() -> None:
    """Test update_task raises TaskNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import TaskNotFoundError
    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    task = ProspectiveTask(
        id="nonexistent",
        user_id="user-456",
        task="Test",
        description=None,
        trigger_type=TriggerType.TIME,
        trigger_config={},
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        related_goal_id=None,
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    memory = ProspectiveMemory()

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
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(TaskNotFoundError):
            await memory.update_task(task)


@pytest.mark.asyncio
async def test_delete_task_removes_from_supabase() -> None:
    """Test delete_task removes task from Supabase."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = [{"id": "task-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.delete_task(user_id="user-456", task_id="task-123")

        mock_table.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_task_raises_not_found() -> None:
    """Test delete_task raises TaskNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import TaskNotFoundError
    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(TaskNotFoundError):
            await memory.delete_task(user_id="user-456", task_id="nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_update_task_updates_in_supabase -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder methods in `backend/src/memory/prospective.py`:

```python
    async def update_task(self, task: ProspectiveTask) -> None:
        """Update an existing task.

        Args:
            task: The ProspectiveTask instance with updated data.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            data = {
                "task": task.task,
                "description": task.description,
                "trigger_type": task.trigger_type.value,
                "trigger_config": task.trigger_config,
                "status": task.status.value,
                "priority": task.priority.value,
                "related_goal_id": task.related_goal_id,
                "related_lead_id": task.related_lead_id,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task.id)
                .eq("user_id", task.user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task.id)

            logger.info(
                "Updated prospective task",
                extra={
                    "task_id": task.id,
                    "user_id": task.user_id,
                    "status": task.status.value,
                },
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update task", extra={"task_id": task.id})
            raise ProspectiveMemoryError(f"Failed to update task: {e}") from e

    async def delete_task(self, user_id: str, task_id: str) -> None:
        """Delete a task.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to delete.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If deletion fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .delete()
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Deleted prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to delete task: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_update_task_updates_in_supabase tests/test_prospective_memory.py::test_update_task_raises_not_found tests/test_prospective_memory.py::test_delete_task_removes_from_supabase tests/test_prospective_memory.py::test_delete_task_raises_not_found -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory update_task and delete_task

Add update and delete operations for prospective tasks:
- update_task: Updates all mutable task fields
- delete_task: Removes task from database
- Both raise TaskNotFoundError when task doesn't exist

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement ProspectiveMemory.complete_task and cancel_task

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_complete_task_sets_completed_status() -> None:
    """Test complete_task sets status to completed and completed_at."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = [{"id": "task-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.complete_task(user_id="user-456", task_id="task-123")

        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args
        assert call_args[0][0]["status"] == "completed"
        assert "completed_at" in call_args[0][0]


@pytest.mark.asyncio
async def test_complete_task_raises_not_found() -> None:
    """Test complete_task raises TaskNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import TaskNotFoundError
    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(TaskNotFoundError):
            await memory.complete_task(user_id="user-456", task_id="nonexistent")


@pytest.mark.asyncio
async def test_cancel_task_sets_cancelled_status() -> None:
    """Test cancel_task sets status to cancelled."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = [{"id": "task-123"}]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        await memory.cancel_task(user_id="user-456", task_id="task-123")

        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args
        assert call_args[0][0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_task_raises_not_found() -> None:
    """Test cancel_task raises TaskNotFoundError when not found."""
    from unittest.mock import MagicMock, patch

    from src.core.exceptions import TaskNotFoundError
    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

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
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        with pytest.raises(TaskNotFoundError):
            await memory.cancel_task(user_id="user-456", task_id="nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_complete_task_sets_completed_status -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder methods in `backend/src/memory/prospective.py`:

```python
    async def complete_task(self, user_id: str, task_id: str) -> None:
        """Mark a task as completed.

        Sets the task status to 'completed' and records the completion time.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to complete.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "status": TaskStatus.COMPLETED.value,
                "completed_at": now.isoformat(),
            }

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Completed prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to complete task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to complete task: {e}") from e

    async def cancel_task(self, user_id: str, task_id: str) -> None:
        """Mark a task as cancelled.

        Sets the task status to 'cancelled'.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to cancel.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            data = {"status": TaskStatus.CANCELLED.value}

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Cancelled prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to cancel task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to cancel task: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_complete_task_sets_completed_status tests/test_prospective_memory.py::test_complete_task_raises_not_found tests/test_prospective_memory.py::test_cancel_task_sets_cancelled_status tests/test_prospective_memory.py::test_cancel_task_raises_not_found -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory complete_task and cancel_task

Add status transition methods for prospective tasks:
- complete_task: Sets status to completed with timestamp
- cancel_task: Sets status to cancelled
- Both raise TaskNotFoundError when task doesn't exist

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement ProspectiveMemory.get_upcoming_tasks

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_get_upcoming_tasks_returns_pending_time_tasks() -> None:
    """Test get_upcoming_tasks returns pending time-based tasks ordered by due date."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    now = datetime.now(UTC)
    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_eq3 = MagicMock()
    mock_eq2.eq.return_value = mock_eq3
    mock_order = MagicMock()
    mock_eq3.order.return_value = mock_order
    mock_limit = MagicMock()
    mock_order.limit.return_value = mock_limit
    mock_execute = MagicMock()
    mock_limit.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "task-1",
            "user_id": "user-456",
            "task": "Task 1",
            "description": None,
            "trigger_type": "time",
            "trigger_config": {"due_at": "2026-02-15T10:00:00+00:00"},
            "status": "pending",
            "priority": "high",
            "related_goal_id": None,
            "related_lead_id": None,
            "completed_at": None,
            "created_at": now.isoformat(),
        },
        {
            "id": "task-2",
            "user_id": "user-456",
            "task": "Task 2",
            "description": None,
            "trigger_type": "time",
            "trigger_config": {"due_at": "2026-02-20T10:00:00+00:00"},
            "status": "pending",
            "priority": "medium",
            "related_goal_id": None,
            "related_lead_id": None,
            "completed_at": None,
            "created_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_upcoming_tasks(user_id="user-456", limit=10)

        assert len(tasks) == 2
        assert tasks[0].id == "task-1"
        assert tasks[1].id == "task-2"


@pytest.mark.asyncio
async def test_get_upcoming_tasks_returns_empty_list_when_none() -> None:
    """Test get_upcoming_tasks returns empty list when no tasks found."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_eq3 = MagicMock()
    mock_eq2.eq.return_value = mock_eq3
    mock_order = MagicMock()
    mock_eq3.order.return_value = mock_order
    mock_limit = MagicMock()
    mock_order.limit.return_value = mock_limit
    mock_execute = MagicMock()
    mock_limit.execute.return_value = mock_execute
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_upcoming_tasks(user_id="user-456")

        assert tasks == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_upcoming_tasks_returns_pending_time_tasks -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder method in `backend/src/memory/prospective.py`:

```python
    async def get_upcoming_tasks(
        self, user_id: str, limit: int = 10
    ) -> list[ProspectiveTask]:
        """Get upcoming time-based tasks for a user.

        Returns pending tasks with time triggers, ordered by due date.

        Args:
            user_id: The user to get tasks for.
            limit: Maximum number of tasks to return.

        Returns:
            List of upcoming ProspectiveTasks ordered by due date.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", TaskStatus.PENDING.value)
                .eq("trigger_type", TriggerType.TIME.value)
                .order("trigger_config->due_at")
                .limit(limit)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved upcoming tasks",
                extra={"user_id": user_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get upcoming tasks")
            raise ProspectiveMemoryError(f"Failed to get upcoming tasks: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_upcoming_tasks_returns_pending_time_tasks tests/test_prospective_memory.py::test_get_upcoming_tasks_returns_empty_list_when_none -v`
Expected: Both tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory.get_upcoming_tasks

Add method to retrieve upcoming time-based tasks:
- Filters for pending status and time trigger type
- Orders by due_at date ascending
- Supports configurable limit

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement ProspectiveMemory.get_overdue_tasks

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_get_overdue_tasks_returns_overdue_tasks() -> None:
    """Test get_overdue_tasks returns tasks with overdue status."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    now = datetime.now(UTC)
    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "task-overdue",
            "user_id": "user-456",
            "task": "Overdue task",
            "description": None,
            "trigger_type": "time",
            "trigger_config": {"due_at": "2026-01-15T10:00:00+00:00"},
            "status": "overdue",
            "priority": "high",
            "related_goal_id": None,
            "related_lead_id": None,
            "completed_at": None,
            "created_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_overdue_tasks(user_id="user-456")

        assert len(tasks) == 1
        assert tasks[0].id == "task-overdue"


@pytest.mark.asyncio
async def test_get_overdue_tasks_returns_empty_list_when_none() -> None:
    """Test get_overdue_tasks returns empty list when no overdue tasks."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_overdue_tasks(user_id="user-456")

        assert tasks == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_overdue_tasks_returns_overdue_tasks -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder method in `backend/src/memory/prospective.py`:

```python
    async def get_overdue_tasks(self, user_id: str) -> list[ProspectiveTask]:
        """Get overdue tasks for a user.

        Returns tasks that have overdue status, ordered by priority.

        Args:
            user_id: The user to get overdue tasks for.

        Returns:
            List of overdue ProspectiveTasks ordered by priority (urgent first).

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", TaskStatus.OVERDUE.value)
                .order("priority", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved overdue tasks",
                extra={"user_id": user_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get overdue tasks")
            raise ProspectiveMemoryError(f"Failed to get overdue tasks: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_overdue_tasks_returns_overdue_tasks tests/test_prospective_memory.py::test_get_overdue_tasks_returns_empty_list_when_none -v`
Expected: Both tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory.get_overdue_tasks

Add method to retrieve overdue tasks:
- Filters for overdue status
- Orders by priority descending (urgent first)

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement ProspectiveMemory.get_tasks_for_goal and get_tasks_for_lead

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Test: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_get_tasks_for_goal_returns_linked_tasks() -> None:
    """Test get_tasks_for_goal returns tasks linked to a specific goal."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    now = datetime.now(UTC)
    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "task-goal",
            "user_id": "user-456",
            "task": "Task for goal",
            "description": None,
            "trigger_type": "time",
            "trigger_config": {"due_at": "2026-02-15T10:00:00+00:00"},
            "status": "pending",
            "priority": "high",
            "related_goal_id": "goal-789",
            "related_lead_id": None,
            "completed_at": None,
            "created_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_tasks_for_goal(user_id="user-456", goal_id="goal-789")

        assert len(tasks) == 1
        assert tasks[0].related_goal_id == "goal-789"


@pytest.mark.asyncio
async def test_get_tasks_for_goal_returns_empty_when_none() -> None:
    """Test get_tasks_for_goal returns empty list when no linked tasks."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_tasks_for_goal(user_id="user-456", goal_id="goal-789")

        assert tasks == []


@pytest.mark.asyncio
async def test_get_tasks_for_lead_returns_linked_tasks() -> None:
    """Test get_tasks_for_lead returns tasks linked to a specific lead."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    now = datetime.now(UTC)
    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = [
        {
            "id": "task-lead",
            "user_id": "user-456",
            "task": "Follow up with lead",
            "description": None,
            "trigger_type": "time",
            "trigger_config": {"due_at": "2026-02-15T10:00:00+00:00"},
            "status": "pending",
            "priority": "high",
            "related_goal_id": None,
            "related_lead_id": "lead-012",
            "completed_at": None,
            "created_at": now.isoformat(),
        },
    ]

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_tasks_for_lead(user_id="user-456", lead_id="lead-012")

        assert len(tasks) == 1
        assert tasks[0].related_lead_id == "lead-012"


@pytest.mark.asyncio
async def test_get_tasks_for_lead_returns_empty_when_none() -> None:
    """Test get_tasks_for_lead returns empty list when no linked tasks."""
    from unittest.mock import MagicMock, patch

    from src.memory.prospective import ProspectiveMemory

    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_eq1 = MagicMock()
    mock_select.eq.return_value = mock_eq1
    mock_eq2 = MagicMock()
    mock_eq1.eq.return_value = mock_eq2
    mock_order = MagicMock()
    mock_eq2.order.return_value = mock_order
    mock_execute = MagicMock()
    mock_order.execute.return_value = mock_execute
    mock_execute.data = []

    with patch.object(memory, "_get_supabase_client") as mock_get_client:
        mock_get_client.return_value = mock_client

        tasks = await memory.get_tasks_for_lead(user_id="user-456", lead_id="lead-012")

        assert tasks == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_tasks_for_goal_returns_linked_tasks -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace the placeholder methods in `backend/src/memory/prospective.py`:

```python
    async def get_tasks_for_goal(
        self, user_id: str, goal_id: str
    ) -> list[ProspectiveTask]:
        """Get tasks linked to a specific goal.

        Args:
            user_id: The user to get tasks for.
            goal_id: The goal ID to filter by.

        Returns:
            List of ProspectiveTasks linked to the goal.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("related_goal_id", goal_id)
                .order("created_at", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved tasks for goal",
                extra={"user_id": user_id, "goal_id": goal_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get tasks for goal", extra={"goal_id": goal_id})
            raise ProspectiveMemoryError(f"Failed to get tasks for goal: {e}") from e

    async def get_tasks_for_lead(
        self, user_id: str, lead_id: str
    ) -> list[ProspectiveTask]:
        """Get tasks linked to a specific lead.

        Args:
            user_id: The user to get tasks for.
            lead_id: The lead ID to filter by.

        Returns:
            List of ProspectiveTasks linked to the lead.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("related_lead_id", lead_id)
                .order("created_at", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved tasks for lead",
                extra={"user_id": user_id, "lead_id": lead_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get tasks for lead", extra={"lead_id": lead_id})
            raise ProspectiveMemoryError(f"Failed to get tasks for lead: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_get_tasks_for_goal_returns_linked_tasks tests/test_prospective_memory.py::test_get_tasks_for_goal_returns_empty_when_none tests/test_prospective_memory.py::test_get_tasks_for_lead_returns_linked_tasks tests/test_prospective_memory.py::test_get_tasks_for_lead_returns_empty_when_none -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement ProspectiveMemory goal and lead task queries

Add methods to retrieve tasks by related entities:
- get_tasks_for_goal: Returns tasks linked to a specific goal
- get_tasks_for_lead: Returns tasks linked to a specific lead
- Both ordered by created_at descending

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Export ProspectiveMemory from memory module

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_prospective_memory.py` (at the top, after imports):

```python
def test_prospective_memory_exported_from_memory_module() -> None:
    """Test ProspectiveMemory can be imported from src.memory."""
    from src.memory import ProspectiveMemory, ProspectiveTask, TaskPriority, TaskStatus, TriggerType

    assert ProspectiveMemory is not None
    assert ProspectiveTask is not None
    assert TaskStatus is not None
    assert TaskPriority is not None
    assert TriggerType is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_prospective_memory_exported_from_memory_module -v`
Expected: FAIL with "ImportError: cannot import name 'ProspectiveMemory' from 'src.memory'"

**Step 3: Write minimal implementation**

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
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
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
    # Prospective Memory
    "ProspectiveMemory",
    "ProspectiveTask",
    "TriggerType",
    "TaskStatus",
    "TaskPriority",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_prospective_memory_exported_from_memory_module -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_prospective_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): export ProspectiveMemory from memory module

Add prospective memory exports to src.memory:
- ProspectiveMemory service class
- ProspectiveTask dataclass
- TriggerType, TaskStatus, TaskPriority enums

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Run All Quality Gates

**Step 1: Run all tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run mypy type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No errors

**Step 3: Run ruff linting**

Run: `cd backend && ruff check src/`
Expected: No warnings

**Step 4: Run ruff formatting check**

Run: `cd backend && ruff format src/ --check`
Expected: No changes needed (or run `ruff format src/` to fix)

**Step 5: Final commit if any fixes needed**

If any quality gate issues were found and fixed:

```bash
git add -A
git commit -m "$(cat <<'EOF'
fix(memory): address quality gate issues in prospective memory

Fix any type hints, formatting, or linting issues identified
by quality gates.

Part of US-206: Prospective Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-206: Prospective Memory with:

1. **Exception classes** - ProspectiveMemoryError and TaskNotFoundError
2. **Database migration** - prospective_memories table with RLS policies
3. **Data structures** - TriggerType, TaskStatus, TaskPriority enums and ProspectiveTask dataclass
4. **CRUD operations** - create_task, get_task, update_task, delete_task
5. **Status transitions** - complete_task, cancel_task
6. **Query methods** - get_upcoming_tasks, get_overdue_tasks, get_tasks_for_goal, get_tasks_for_lead
7. **Module exports** - All types exported from src.memory

Total: 12 tasks with TDD approach (test first, implement, verify, commit).
