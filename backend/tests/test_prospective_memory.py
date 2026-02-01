"""Tests for prospective memory module."""

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest


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
    from src.memory.prospective import ProspectiveTask

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


def test_prospective_memory_exported_from_memory_module() -> None:
    """Test ProspectiveMemory can be imported from src.memory."""
    from src.memory import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    assert ProspectiveMemory is not None
    assert ProspectiveTask is not None
    assert TaskStatus is not None
    assert TaskPriority is not None
    assert TriggerType is not None
