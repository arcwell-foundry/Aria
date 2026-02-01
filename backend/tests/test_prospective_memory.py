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
