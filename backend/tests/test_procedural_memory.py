"""Tests for procedural memory module."""

import json
from datetime import UTC, datetime
from typing import Any


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


# --- ProceduralMemory Service Tests ---

import pytest
from unittest.mock import MagicMock


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
