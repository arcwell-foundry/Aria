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