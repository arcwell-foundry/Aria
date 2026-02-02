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
