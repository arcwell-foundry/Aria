"""Tests for OperatorAgent module.

All four tool methods now check integration status via Supabase before
returning data.  Tests mock ``_check_integration_status`` to exercise
both the "not connected" and "connected but Composio unavailable" paths.
Input-validation tests remain unchanged since validation runs before
integration checks.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent() -> Any:
    """Create an OperatorAgent with a mocked LLM client."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    return OperatorAgent(llm_client=mock_llm, user_id="user-123")


def _not_connected() -> dict[str, Any]:
    return {"connected": False, "provider": None, "integration_id": None}


def _connected(provider: str = "google_calendar") -> dict[str, Any]:
    return {"connected": True, "provider": provider, "integration_id": "int-001"}


# ---------------------------------------------------------------------------
# Class metadata
# ---------------------------------------------------------------------------


def test_operator_agent_has_name_and_description() -> None:
    """Test OperatorAgent has correct name and description class attributes."""
    from src.agents.operator import OperatorAgent

    assert OperatorAgent.name == "Operator"
    assert OperatorAgent.description == "System operations for calendar, CRM, and integrations"


# ---------------------------------------------------------------------------
# validate_input (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with operation_type."""
    agent = _make_agent()
    task: dict[str, Any] = {"operation_type": "calendar_read", "parameters": {}}
    assert agent.validate_input(task) is True


def test_validate_input_requires_operation_type() -> None:
    """Test validate_input returns False when operation_type is missing."""
    agent = _make_agent()
    task: dict[str, Any] = {"parameters": {}}
    assert agent.validate_input(task) is False


def test_validate_input_validates_operation_type() -> None:
    """Test validate_input returns False for invalid operation_type."""
    agent = _make_agent()
    task: dict[str, Any] = {"operation_type": "invalid_operation", "parameters": {}}
    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters() -> None:
    """Test validate_input returns False when parameters is missing."""
    agent = _make_agent()
    task: dict[str, Any] = {"operation_type": "calendar_read"}
    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters_as_dict() -> None:
    """Test validate_input returns False when parameters is not a dict."""
    agent = _make_agent()
    task: dict[str, Any] = {"operation_type": "calendar_read", "parameters": "not_a_dict"}
    assert agent.validate_input(task) is False


# ---------------------------------------------------------------------------
# _calendar_read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_read_not_connected() -> None:
    """When no calendar integration is active, returns 'not connected' payload."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_read(start_date="2024-01-01", end_date="2024-01-07")

    assert result["connected"] is False
    assert "not connected" in result["message"].lower()
    assert result["events"] == []
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_calendar_read_connected_but_composio_missing() -> None:
    """When integration exists but Composio is unavailable, returns status message."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_connected("google_calendar"))

    result = await agent._calendar_read(start_date="2024-01-01", end_date="2024-01-07")

    assert result["connected"] is True
    assert result["provider"] == "google_calendar"
    assert "composio" in result["message"].lower()
    assert result["events"] == []
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_calendar_read_returns_events_key() -> None:
    """Regardless of status, result always contains 'events' list."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_read(start_date="2024-01-01")
    assert isinstance(result, dict)
    assert "events" in result
    assert isinstance(result["events"], list)


# ---------------------------------------------------------------------------
# _calendar_write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_write_validates_action_before_integration_check() -> None:
    """Invalid action is rejected even before integration is checked."""
    agent = _make_agent()
    # Should NOT even call _check_integration_status for invalid action
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_write(action="invalid_action", event={})

    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_calendar_write_not_connected() -> None:
    """When no calendar integration, write returns 'not connected'."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_write(action="create", event={"title": "Meeting"})

    assert result["connected"] is False
    assert result["success"] is False
    assert "not connected" in result["message"].lower()


@pytest.mark.asyncio
async def test_calendar_write_connected_but_composio_missing() -> None:
    """When integration exists but Composio unavailable, write returns status."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_connected("outlook_calendar"))

    result = await agent._calendar_write(action="create", event={"title": "Meeting"})

    assert result["connected"] is True
    assert result["success"] is False
    assert result["provider"] == "outlook_calendar"
    assert "composio" in result["message"].lower()


@pytest.mark.asyncio
async def test_calendar_write_update_not_connected() -> None:
    """calendar_write update with valid action but no integration."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_write(action="update", event_id="evt-1")

    assert result["connected"] is False
    assert result["success"] is False


@pytest.mark.asyncio
async def test_calendar_write_delete_not_connected() -> None:
    """calendar_write delete with valid action but no integration."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._calendar_write(action="delete", event_id="evt-1")

    assert result["connected"] is False
    assert result["success"] is False


# ---------------------------------------------------------------------------
# _crm_read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crm_read_not_connected() -> None:
    """When no CRM integration is active, returns 'not connected' payload."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_read(record_type="leads")

    assert result["connected"] is False
    assert "not connected" in result["message"].lower()
    assert result["records"] == []
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_crm_read_connected_but_composio_missing() -> None:
    """When CRM integration exists but Composio unavailable, returns status."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_connected("salesforce"))

    result = await agent._crm_read(record_type="leads")

    assert result["connected"] is True
    assert result["provider"] == "salesforce"
    assert "composio" in result["message"].lower()
    assert result["records"] == []
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_crm_read_returns_records_key() -> None:
    """Regardless of status, result always contains 'records' list."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_read(record_type="leads")
    assert isinstance(result, dict)
    assert "records" in result
    assert isinstance(result["records"], list)


# ---------------------------------------------------------------------------
# _crm_write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crm_write_validates_action_before_integration_check() -> None:
    """Invalid action is rejected before integration check."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_write(action="invalid_action", record_type="leads")

    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_crm_write_validates_record_type_before_integration_check() -> None:
    """Invalid record_type is rejected before integration check."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_write(
        action="create", record_type="invalid_type", record={"name": "Test"}
    )

    assert result["success"] is False
    assert "Invalid record_type" in result["error"]


@pytest.mark.asyncio
async def test_crm_write_not_connected() -> None:
    """When no CRM integration, write returns 'not connected'."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_write(
        action="create", record_type="leads", record={"name": "New Lead"}
    )

    assert result["connected"] is False
    assert result["success"] is False
    assert "not connected" in result["message"].lower()


@pytest.mark.asyncio
async def test_crm_write_connected_but_composio_missing() -> None:
    """When CRM integration exists but Composio unavailable, returns status."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_connected("hubspot"))

    result = await agent._crm_write(
        action="create", record_type="leads", record={"name": "New Lead"}
    )

    assert result["connected"] is True
    assert result["success"] is False
    assert result["provider"] == "hubspot"
    assert "composio" in result["message"].lower()


@pytest.mark.asyncio
async def test_crm_write_update_not_connected() -> None:
    """crm_write update returns not connected when integration missing."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_write(
        action="update", record_type="leads", record_id="lead-001", record={"status": "won"}
    )

    assert result["connected"] is False
    assert result["success"] is False


@pytest.mark.asyncio
async def test_crm_write_delete_not_connected() -> None:
    """crm_write delete returns not connected when integration missing."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    result = await agent._crm_write(action="delete", record_type="leads", record_id="lead-001")

    assert result["connected"] is False
    assert result["success"] is False


# ---------------------------------------------------------------------------
# _check_integration_status (Supabase query)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_integration_status_calendar_connected() -> None:
    """_check_integration_status returns connected when active row exists."""
    agent = _make_agent()

    mock_response = MagicMock()
    mock_response.data = [
        {"id": "int-abc", "integration_type": "google_calendar", "status": "active"}
    ]

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_response

    with (
        patch("src.agents.operator.SupabaseClient", create=True),
        patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client),
    ):
        result = await agent._check_integration_status("calendar")

    assert result["connected"] is True
    assert result["provider"] == "google_calendar"
    assert result["integration_id"] == "int-abc"


@pytest.mark.asyncio
async def test_check_integration_status_crm_not_connected() -> None:
    """_check_integration_status returns not connected when no active row."""
    agent = _make_agent()

    mock_response = MagicMock()
    mock_response.data = []

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_response

    with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
        result = await agent._check_integration_status("crm")

    assert result["connected"] is False
    assert result["provider"] is None
    assert result["integration_id"] is None


@pytest.mark.asyncio
async def test_check_integration_status_db_error_treated_as_not_connected() -> None:
    """_check_integration_status treats database errors as not connected."""
    agent = _make_agent()

    with patch(
        "src.db.supabase.SupabaseClient.get_client",
        side_effect=Exception("DB down"),
    ):
        result = await agent._check_integration_status("calendar")

    assert result["connected"] is False
    assert result["provider"] is None


@pytest.mark.asyncio
async def test_check_integration_status_unknown_category() -> None:
    """_check_integration_status returns not connected for unknown category."""
    agent = _make_agent()
    result = await agent._check_integration_status("unknown_service")

    assert result["connected"] is False
    assert result["provider"] is None


# ---------------------------------------------------------------------------
# execute / run integration (end-to-end via mocked status)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_returns_agent_result() -> None:
    """Test execute returns an AgentResult instance."""
    from src.agents.base import AgentResult

    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    task = {"operation_type": "calendar_read", "parameters": {"start_date": "2024-01-01"}}
    result = await agent.execute(task)

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert "events" in result.data


@pytest.mark.asyncio
async def test_execute_dispatches_to_correct_tool() -> None:
    """Test execute dispatches to correct tool based on operation_type."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    # Test calendar_read
    calendar_task = {
        "operation_type": "calendar_read",
        "parameters": {"start_date": "2024-01-01"},
    }
    calendar_result = await agent.execute(calendar_task)
    assert calendar_result.success is True
    assert "events" in calendar_result.data

    # Test crm_read
    crm_task = {
        "operation_type": "crm_read",
        "parameters": {"record_type": "leads"},
    }
    crm_result = await agent.execute(crm_task)
    assert crm_result.success is True
    assert "records" in crm_result.data


@pytest.mark.asyncio
async def test_execute_handles_unknown_operation_type() -> None:
    """Test execute returns error for unknown operation_type."""
    agent = _make_agent()

    task = {"operation_type": "unknown_operation", "parameters": {}}
    result = await agent.execute(task)

    assert result.success is False
    assert result.error is not None
    assert "Unknown operation_type" in result.error


@pytest.mark.asyncio
async def test_execute_dispatches_calendar_write() -> None:
    """Test execute dispatches to calendar_write tool."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    task = {
        "operation_type": "calendar_write",
        "parameters": {"action": "create", "event": {"title": "Test Event"}},
    }
    result = await agent.execute(task)

    assert result.success is True
    # With no integration, success in the data payload is False
    assert result.data["connected"] is False


@pytest.mark.asyncio
async def test_execute_dispatches_crm_write() -> None:
    """Test execute dispatches to crm_write tool."""
    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    task = {
        "operation_type": "crm_write",
        "parameters": {
            "action": "create",
            "record_type": "leads",
            "record": {"name": "New Lead"},
        },
    }
    result = await agent.execute(task)

    assert result.success is True
    assert result.data["connected"] is False


@pytest.mark.asyncio
async def test_full_operator_workflow_calendar() -> None:
    """End-to-end Operator workflow for calendar operations.

    Verifies state transitions and correct dispatch through ``run()``.
    """
    from src.agents.base import AgentStatus

    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    assert agent.status == AgentStatus.IDLE

    read_task = {
        "operation_type": "calendar_read",
        "parameters": {"start_date": "2024-01-01", "end_date": "2024-01-07"},
    }
    read_result = await agent.run(read_task)

    assert agent.status == AgentStatus.COMPLETE
    assert read_result.success is True
    assert "events" in read_result.data

    # Reset agent for next test
    agent.status = AgentStatus.IDLE

    create_task = {
        "operation_type": "calendar_write",
        "parameters": {"action": "create", "event": {"title": "Q1 Planning"}},
    }
    create_result = await agent.run(create_task)
    assert create_result.success is True


@pytest.mark.asyncio
async def test_full_operator_workflow_crm() -> None:
    """End-to-end Operator workflow for CRM operations."""
    from src.agents.base import AgentStatus

    agent = _make_agent()
    agent._check_integration_status = AsyncMock(return_value=_not_connected())

    read_task = {
        "operation_type": "crm_read",
        "parameters": {"record_type": "leads"},
    }
    read_result = await agent.run(read_task)

    assert agent.status == AgentStatus.COMPLETE
    assert read_result.success is True
    assert "records" in read_result.data

    # Reset
    agent.status = AgentStatus.IDLE

    create_task = {
        "operation_type": "crm_write",
        "parameters": {
            "action": "create",
            "record_type": "leads",
            "record": {"name": "New Prospect"},
        },
    }
    create_result = await agent.run(create_task)
    assert create_result.success is True


@pytest.mark.asyncio
async def test_operator_agent_handles_validation_failure() -> None:
    """Invalid input returns failed result with validation error."""
    from src.agents.base import AgentStatus

    agent = _make_agent()
    invalid_task: dict[str, Any] = {"parameters": {}}

    result = await agent.run(invalid_task)

    assert agent.status == AgentStatus.FAILED
    assert result.success is False
    assert result.error == "Input validation failed"
    assert result.data is None


def test_operator_agent_exported_from_module() -> None:
    """Test OperatorAgent is exported from src.agents module."""
    from src.agents import OperatorAgent

    assert OperatorAgent is not None
    assert OperatorAgent.name == "Operator"
