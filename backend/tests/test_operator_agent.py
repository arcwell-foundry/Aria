"""Tests for OperatorAgent module."""

from typing import Any
from unittest.mock import MagicMock

import pytest


def test_operator_agent_has_name_and_description() -> None:
    """Test OperatorAgent has correct name and description class attributes."""
    from src.agents.operator import OperatorAgent

    assert OperatorAgent.name == "Operator"
    assert OperatorAgent.description == "System operations for calendar, CRM, and integrations"


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
        "parameters": {},
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_operation_type() -> None:
    """Test validate_input returns False when operation_type is missing."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "parameters": {},
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_operation_type() -> None:
    """Test validate_input returns False for invalid operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "invalid_operation",
        "parameters": {},
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters() -> None:
    """Test validate_input returns False when parameters is missing."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters_as_dict() -> None:
    """Test validate_input returns False when parameters is not a dict."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
        "parameters": "not_a_dict",
    }

    assert agent.validate_input(task) is False


@pytest.mark.asyncio
async def test_calendar_read_returns_events() -> None:
    """Test calendar_read returns list of calendar events."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_read(
        start_date="2024-01-01",
        end_date="2024-01-07",
    )

    assert isinstance(result, dict)
    assert "events" in result
    assert isinstance(result["events"], list)


@pytest.mark.asyncio
async def test_calendar_read_filters_by_date_range() -> None:
    """Test calendar_read filters events by start_date and end_date."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_read(
        start_date="2024-01-01",
        end_date="2024-01-07",
    )

    # All events should fall within the date range
    for event in result["events"]:
        assert event["start_date"] >= "2024-01-01"
        assert event["end_date"] <= "2024-01-07"


@pytest.mark.asyncio
async def test_calendar_read_includes_event_metadata() -> None:
    """Test calendar_read events include title, description, attendees."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_read(
        start_date="2024-01-01",
        end_date="2024-01-07",
    )

    if len(result["events"]) > 0:
        event = result["events"][0]
        assert "title" in event
        assert "start_date" in event
        assert "end_date" in event


@pytest.mark.asyncio
async def test_calendar_write_creates_event() -> None:
    """Test calendar_write creates a new calendar event."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="create",
        event={
            "title": "New Meeting",
            "start_date": "2024-02-01",
            "start_time": "10:00",
            "end_date": "2024-02-01",
            "end_time": "11:00",
        },
    )

    assert isinstance(result, dict)
    assert result["success"] is True
    assert "event_id" in result


@pytest.mark.asyncio
async def test_calendar_write_supports_update() -> None:
    """Test calendar_write supports updating existing events."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="update",
        event_id="evt-123",
        event={"title": "Updated Meeting Title"},
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_calendar_write_supports_delete() -> None:
    """Test calendar_write supports deleting events."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="delete",
        event_id="evt-123",
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_calendar_write_validates_action() -> None:
    """Test calendar_write validates action parameter."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="invalid_action",
        event={},
    )

    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_calendar_write_create_requires_event_data() -> None:
    """Test calendar_write create action requires event data."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="create",
        event=None,
    )

    assert result["success"] is False
    assert "error" in result
    assert "Event data required" in result["error"]


@pytest.mark.asyncio
async def test_calendar_write_create_requires_non_empty_event() -> None:
    """Test calendar_write create action fails with empty event dict."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Empty dict evaluates to False in boolean context
    result = await agent._calendar_write(
        action="create",
        event={},
    )

    assert result["success"] is False
    assert "error" in result
    assert "Event data required" in result["error"]


@pytest.mark.asyncio
async def test_calendar_write_update_requires_event_id() -> None:
    """Test calendar_write update action requires event_id."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="update",
        event_id=None,
        event={"title": "Updated Title"},
    )

    assert result["success"] is False
    assert "error" in result
    assert "event_id required" in result["error"]


@pytest.mark.asyncio
async def test_calendar_write_delete_requires_event_id() -> None:
    """Test calendar_write delete action requires event_id."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._calendar_write(
        action="delete",
        event_id=None,
    )

    assert result["success"] is False
    assert "error" in result
    assert "event_id required" in result["error"]


@pytest.mark.asyncio
async def test_crm_read_returns_records() -> None:
    """Test crm_read returns list of CRM records."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
    )

    assert isinstance(result, dict)
    assert "records" in result
    assert isinstance(result["records"], list)


@pytest.mark.asyncio
async def test_crm_read_filters_by_record_type() -> None:
    """Test crm_read filters by record_type (leads, contacts, accounts)."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Test leads
    leads_result = await agent._crm_read(record_type="leads")
    assert leads_result["record_type"] == "leads"

    # Test contacts
    contacts_result = await agent._crm_read(record_type="contacts")
    assert contacts_result["record_type"] == "contacts"


@pytest.mark.asyncio
async def test_crm_read_includes_record_fields() -> None:
    """Test crm_read records include expected fields."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(record_type="leads")

    if len(result["records"]) > 0:
        record = result["records"][0]
        assert "id" in record
        assert "name" in record


@pytest.mark.asyncio
async def test_crm_read_filters_by_id() -> None:
    """Test crm_read can filter by record_id."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        record_id="lead-123",
    )

    assert result["record_type"] == "leads"
    assert result.get("record_id") == "lead-123"


@pytest.mark.asyncio
async def test_crm_read_filters_by_single_filter() -> None:
    """Test crm_read applies single filter parameter correctly."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        filters={"status": "qualified"},
    )

    assert result["record_type"] == "leads"
    assert result["total_count"] == 1
    assert result["records"][0]["status"] == "qualified"


@pytest.mark.asyncio
async def test_crm_read_filters_by_multiple_filters() -> None:
    """Test crm_read applies multiple filter parameters correctly."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        filters={"status": "prospecting", "source": "referral"},
    )

    assert result["record_type"] == "leads"
    assert result["total_count"] == 1
    assert result["records"][0]["status"] == "prospecting"
    assert result["records"][0]["source"] == "referral"


@pytest.mark.asyncio
async def test_crm_read_filters_with_no_matches() -> None:
    """Test crm_read returns empty list when filters match no records."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        filters={"status": "nonexistent_status"},
    )

    assert result["record_type"] == "leads"
    assert result["total_count"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_crm_read_invalid_record_type_returns_empty() -> None:
    """Test crm_read returns empty records for invalid record_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="invalid_type",
    )

    assert result["record_type"] == "invalid_type"
    assert result["total_count"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_crm_read_nonexistent_record_id_returns_empty() -> None:
    """Test crm_read returns empty list when record_id doesn't exist."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        record_id="nonexistent-id",
    )

    assert result["record_type"] == "leads"
    assert result["record_id"] == "nonexistent-id"
    assert result["total_count"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_crm_read_filters_combined_with_record_id() -> None:
    """Test crm_read applies both record_id and additional filters."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        record_id="lead-001",
        filters={"status": "qualified"},
    )

    # Should return lead-001 since it matches the status filter
    assert result["total_count"] == 1
    assert result["records"][0]["id"] == "lead-001"
    assert result["records"][0]["status"] == "qualified"


@pytest.mark.asyncio
async def test_crm_read_filters_mismatch_with_record_id() -> None:
    """Test crm_read returns empty when record_id exists but filters don't match."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        record_id="lead-001",
        filters={"status": "prospecting"},  # lead-001 has status "qualified"
    )

    # lead-001 exists but doesn't match the status filter
    assert result["total_count"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_crm_read_empty_filters_dict() -> None:
    """Test crm_read with empty filters dict returns all records."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="leads",
        filters={},
    )

    # Empty filters should not filter anything
    assert result["total_count"] == 2
    assert len(result["records"]) == 2


@pytest.mark.asyncio
async def test_crm_read_contacts_filters() -> None:
    """Test crm_read filters work correctly for contacts."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="contacts",
        filters={"company": "Acme Corp"},
    )

    assert result["record_type"] == "contacts"
    assert result["total_count"] == 1
    assert result["records"][0]["name"] == "John Smith"
    assert result["records"][0]["company"] == "Acme Corp"


@pytest.mark.asyncio
async def test_crm_read_accounts_filters() -> None:
    """Test crm_read filters work correctly for accounts."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_read(
        record_type="accounts",
        filters={"industry": "Technology"},
    )

    assert result["record_type"] == "accounts"
    assert result["total_count"] == 1
    assert result["records"][0]["name"] == "Acme Corp"
    assert result["records"][0]["industry"] == "Technology"


@pytest.mark.asyncio
async def test_crm_write_creates_record() -> None:
    """Test crm_write creates a new CRM record."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="create",
        record_type="leads",
        record={"name": "New Lead", "status": "prospecting"},
    )

    assert isinstance(result, dict)
    assert result["success"] is True
    assert "record_id" in result


@pytest.mark.asyncio
async def test_crm_write_supports_update() -> None:
    """Test crm_write supports updating existing records."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="update",
        record_type="leads",
        record_id="lead-001",
        record={"status": "qualified"},
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_crm_write_supports_delete() -> None:
    """Test crm_write supports deleting records."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="delete",
        record_type="leads",
        record_id="lead-001",
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_crm_write_validates_action() -> None:
    """Test crm_write validates action parameter."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="invalid_action",
        record_type="leads",
    )

    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_crm_write_create_requires_record_data() -> None:
    """Test crm_write create action requires record data."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="create",
        record_type="leads",
        record=None,
    )

    assert result["success"] is False
    assert "error" in result
    assert "Record data required" in result["error"]


@pytest.mark.asyncio
async def test_crm_write_create_requires_non_empty_record() -> None:
    """Test crm_write create action fails with empty record dict."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Empty dict evaluates to False in boolean context
    result = await agent._crm_write(
        action="create",
        record_type="leads",
        record={},
    )

    assert result["success"] is False
    assert "error" in result
    assert "Record data required" in result["error"]


@pytest.mark.asyncio
async def test_crm_write_update_requires_record_id() -> None:
    """Test crm_write update action requires record_id."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="update",
        record_type="leads",
        record_id=None,
        record={"status": "qualified"},
    )

    assert result["success"] is False
    assert "error" in result
    assert "record_id required" in result["error"]


@pytest.mark.asyncio
async def test_crm_write_delete_requires_record_id() -> None:
    """Test crm_write delete action requires record_id."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="delete",
        record_type="leads",
        record_id=None,
    )

    assert result["success"] is False
    assert "error" in result
    assert "record_id required" in result["error"]


@pytest.mark.asyncio
async def test_crm_write_validates_record_type() -> None:
    """Test crm_write validates record_type parameter."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._crm_write(
        action="create",
        record_type="invalid_type",
        record={"name": "Test"},
    )

    assert result["success"] is False
    assert "error" in result
    assert "Invalid record_type" in result["error"]


@pytest.mark.asyncio
async def test_execute_returns_agent_result() -> None:
    """Test execute returns an AgentResult instance."""
    from src.agents.base import AgentResult
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "calendar_read",
        "parameters": {"start_date": "2024-01-01"},
    }

    result = await agent.execute(task)

    assert isinstance(result, AgentResult)
    assert result.success is True


@pytest.mark.asyncio
async def test_execute_dispatches_to_correct_tool() -> None:
    """Test execute dispatches to correct tool based on operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

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
async def test_execute_passes_parameters() -> None:
    """Test execute passes parameters through to the tool."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "crm_read",
        "parameters": {
            "record_type": "contacts",
            "record_id": "contact-001",
        },
    }

    result = await agent.execute(task)

    assert result.success is True
    assert result.data["record_id"] == "contact-001"


@pytest.mark.asyncio
async def test_execute_handles_unknown_operation_type() -> None:
    """Test execute returns error for unknown operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "unknown_operation",
        "parameters": {},
    }

    result = await agent.execute(task)

    assert result.success is False
    assert result.error is not None
    assert "Unknown operation_type" in result.error


@pytest.mark.asyncio
async def test_execute_dispatches_calendar_write() -> None:
    """Test execute dispatches to calendar_write tool."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "calendar_write",
        "parameters": {
            "action": "create",
            "event": {"title": "Test Event"},
        },
    }

    result = await agent.execute(task)

    assert result.success is True
    assert result.data["success"] is True
    assert result.data["action"] == "create"


@pytest.mark.asyncio
async def test_execute_dispatches_crm_write() -> None:
    """Test execute dispatches to crm_write tool."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

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
    assert result.data["success"] is True
    assert result.data["action"] == "create"

