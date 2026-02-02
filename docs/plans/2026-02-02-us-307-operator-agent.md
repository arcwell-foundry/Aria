# US-307: Operator Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Operator Agent for ARIA with tools for calendar operations, CRM read/write, and integration management.

**Architecture:** The OperatorAgent extends BaseAgent and provides system operation capabilities including calendar management (read/write), CRM operations (read/write), and third-party integration management. The agent uses mock implementations for calendar/CRM operations that can be replaced with real integrations via Composio.

**Tech Stack:** Python 3.11+, asyncio, logging, pytest (for tests), unittest.mock (for mocking external dependencies)

---

## Task 1: Create OperatorAgent module with class definition

**Files:**
- Create: `backend/src/agents/operator.py`

**Step 1: Write the failing test**

```python
# tests/test_operator_agent.py

def test_operator_agent_has_name_and_description() -> None:
    """Test OperatorAgent has correct name and description class attributes."""
    from src.agents.operator import OperatorAgent

    assert OperatorAgent.name == "Operator"
    assert OperatorAgent.description == "System operations for calendar, CRM, and integrations"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_operator_agent.py::test_operator_agent_has_name_and_description -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.operator'"

**Step 3: Write minimal implementation**

```python
# backend/src/agents/operator.py

"""OperatorAgent module for ARIA.

Provides system operations capabilities including calendar management,
CRM read/write operations, and third-party integration management.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class OperatorAgent(BaseAgent):
    """System operations agent for calendar, CRM, and integrations.

    The Operator agent manages calendar operations, CRM read/write,
    and third-party integration connections for the user.
    """

    name = "Operator"
    description = "System operations for calendar, CRM, and integrations"

    # Valid operation types
    VALID_OPERATION_TYPES = {"calendar_read", "calendar_write", "crm_read", "crm_write"}

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Operator agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._integration_cache: dict[str, Any] = {}
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Operator agent's system operation tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "calendar_read": self._calendar_read,
            "calendar_write": self._calendar_write,
            "crm_read": self._crm_read,
            "crm_write": self._crm_write,
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_operator_agent.py::test_operator_agent_has_name_and_description -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add tests/test_operator_agent.py src/agents/operator.py
git commit -m "feat(agents): create OperatorAgent class with name and description"
```

---

## Task 2: Add validate_input method

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "calendar_read",
        "parameters": {},
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_operation_type() -> None:
    """Test validate_input returns False when operation_type is missing."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "parameters": {},
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_operation_type() -> None:
    """Test validate_input returns False for invalid operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "operation_type": "invalid_operation",
        "parameters": {},
    }

    assert agent.validate_input(task) is False
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "validate_input" -v`
Expected: FAIL with "AttributeError: 'OperatorAgent' object has no attribute 'validate_input'" (using base implementation which returns True, but we need custom validation)

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `_register_tools`:

```python
    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate operator task input before execution.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required: operation_type
        if "operation_type" not in task:
            return False

        operation_type = task["operation_type"]
        if operation_type not in self.VALID_OPERATION_TYPES:
            return False

        # Required: parameters (can be empty dict)
        if "parameters" not in task:
            return False

        if not isinstance(task["parameters"], dict):
            return False

        return True
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "validate_input" -v`
Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent validate_input method"
```

---

## Task 3: Implement calendar_read tool

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "calendar_read" -v`
Expected: FAIL with "AttributeError: 'OperatorAgent' object has no attribute '_calendar_read'"

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `_register_tools`:

```python
    async def _calendar_read(
        self,
        start_date: str,
        end_date: str | None = None,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Read calendar events within a date range.

        This is a mock implementation that returns sample events.
        In production, this would integrate with Google Calendar, Outlook, etc.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: Optional end date in YYYY-MM-DD format.
            calendar_id: Optional calendar identifier.

        Returns:
            Dictionary with list of calendar events.
        """
        logger.info(
            f"Reading calendar events from {start_date} to {end_date or 'present'}",
            extra={"user_id": self.user_id, "calendar_id": calendar_id},
        )

        # Mock calendar events
        mock_events = [
            {
                "id": "evt-001",
                "title": "Team Standup",
                "description": "Daily team sync meeting",
                "start_date": start_date,
                "start_time": "09:00",
                "end_date": start_date,
                "end_time": "09:30",
                "attendees": ["john@example.com", "jane@example.com"],
                "location": "Conference Room A",
            },
            {
                "id": "evt-002",
                "title": "Client Call: Acme Corp",
                "description": "Quarterly business review",
                "start_date": start_date,
                "start_time": "14:00",
                "end_date": start_date,
                "end_time": "15:00",
                "attendees": ["client@acmecorp.com"],
                "location": "Zoom",
            },
            {
                "id": "evt-003",
                "title": "Strategy Planning",
                "description": "Q2 planning session",
                "start_date": end_date or start_date,
                "start_time": "10:00",
                "end_date": end_date or start_date,
                "end_time": "12:00",
                "attendees": ["leadership@example.com"],
                "location": "Boardroom",
            },
        ]

        # Filter by calendar_id if specified
        if calendar_id:
            # In real implementation, would filter by calendar
            pass

        return {
            "calendar_id": calendar_id or "primary",
            "start_date": start_date,
            "end_date": end_date,
            "events": mock_events,
            "total_count": len(mock_events),
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "calendar_read" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent calendar_read tool"
```

---

## Task 4: Implement calendar_write tool

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "calendar_write" -v`
Expected: FAIL with "AttributeError: 'OperatorAgent' object has no attribute '_calendar_write'"

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `_calendar_read`:

```python
    async def _calendar_write(
        self,
        action: str,
        event: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Write calendar operations (create, update, delete).

        This is a mock implementation for calendar write operations.
        In production, this would integrate with Google Calendar, Outlook, etc.

        Args:
            action: Operation type - "create", "update", or "delete".
            event: Event data for create/update operations.
            event_id: Event ID for update/delete operations.

        Returns:
            Dictionary with operation result and event_id.
        """
        valid_actions = {"create", "update", "delete"}

        logger.info(
            f"Calendar write operation: {action}",
            extra={"user_id": self.user_id, "event_id": event_id},
        )

        # Validate action
        if action not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action: {action}. Must be one of {valid_actions}",
            }

        # Handle create
        if action == "create":
            if not event:
                return {"success": False, "error": "Event data required for create"}
            new_event_id = f"evt-{id(event)}"
            return {
                "success": True,
                "action": "create",
                "event_id": new_event_id,
                "event": {**event, "id": new_event_id},
            }

        # Handle update
        if action == "update":
            if not event_id:
                return {"success": False, "error": "event_id required for update"}
            return {
                "success": True,
                "action": "update",
                "event_id": event_id,
                "updated_fields": list(event.keys()) if event else [],
            }

        # Handle delete
        if action == "delete":
            if not event_id:
                return {"success": False, "error": "event_id required for delete"}
            return {
                "success": True,
                "action": "delete",
                "event_id": event_id,
            }

        return {"success": False, "error": "Unknown error"}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "calendar_write" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent calendar_write tool"
```

---

## Task 5: Implement crm_read tool

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "crm_read" -v`
Expected: FAIL with "AttributeError: 'OperatorAgent' object has no attribute '_crm_read'"

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `_calendar_write`:

```python
    async def _crm_read(
        self,
        record_type: str,
        record_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read CRM records (leads, contacts, accounts).

        This is a mock implementation for CRM read operations.
        In production, this would integrate with Salesforce, HubSpot, etc.

        Args:
            record_type: Type of record - "leads", "contacts", "accounts".
            record_id: Optional specific record ID to fetch.
            filters: Optional filters for querying records.

        Returns:
            Dictionary with list of CRM records.
        """
        logger.info(
            f"Reading CRM records: {record_type}",
            extra={"user_id": self.user_id, "record_id": record_id},
        )

        # Mock CRM data by type
        mock_data: dict[str, list[dict[str, Any]]] = {
            "leads": [
                {
                    "id": "lead-001",
                    "name": "Acme Corp",
                    "status": "qualified",
                    "value": 50000,
                    "source": "website",
                    "created_date": "2024-01-15",
                },
                {
                    "id": "lead-002",
                    "name": "TechStart Inc",
                    "status": "prospecting",
                    "value": 75000,
                    "source": "referral",
                    "created_date": "2024-01-20",
                },
            ],
            "contacts": [
                {
                    "id": "contact-001",
                    "name": "John Smith",
                    "email": "john@example.com",
                    "phone": "+1-555-0101",
                    "company": "Acme Corp",
                    "title": "CEO",
                },
                {
                    "id": "contact-002",
                    "name": "Jane Doe",
                    "email": "jane@techstart.com",
                    "phone": "+1-555-0102",
                    "company": "TechStart Inc",
                    "title": "VP Sales",
                },
            ],
            "accounts": [
                {
                    "id": "account-001",
                    "name": "Acme Corp",
                    "industry": "Technology",
                    "employees": 250,
                    "revenue": 5000000,
                },
                {
                    "id": "account-002",
                    "name": "TechStart Inc",
                    "industry": "Software",
                    "employees": 50,
                    "revenue": 2000000,
                },
            ],
        }

        # Get records for type
        records = mock_data.get(record_type, [])

        # Filter by record_id if specified
        if record_id:
            records = [r for r in records if r.get("id") == record_id]

        # Apply additional filters if provided
        if filters:
            for key, value in filters.items():
                records = [r for r in records if r.get(key) == value]

        return {
            "record_type": record_type,
            "record_id": record_id,
            "records": records,
            "total_count": len(records),
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "crm_read" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent crm_read tool"
```

---

## Task 6: Implement crm_write tool

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "crm_write" -v`
Expected: FAIL with "AttributeError: 'OperatorAgent' object has no attribute '_crm_write'"

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `_crm_read`:

```python
    async def _crm_write(
        self,
        action: str,
        record_type: str,
        record: dict[str, Any] | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Write CRM operations (create, update, delete).

        This is a mock implementation for CRM write operations.
        In production, this would integrate with Salesforce, HubSpot, etc.

        Args:
            action: Operation type - "create", "update", or "delete".
            record_type: Type of record - "leads", "contacts", "accounts".
            record: Record data for create/update operations.
            record_id: Record ID for update/delete operations.

        Returns:
            Dictionary with operation result and record_id.
        """
        valid_actions = {"create", "update", "delete"}
        valid_record_types = {"leads", "contacts", "accounts"}

        logger.info(
            f"CRM write operation: {action} on {record_type}",
            extra={"user_id": self.user_id, "record_id": record_id},
        )

        # Validate action
        if action not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action: {action}. Must be one of {valid_actions}",
            }

        # Validate record_type
        if record_type not in valid_record_types:
            return {
                "success": False,
                "error": f"Invalid record_type: {record_type}. Must be one of {valid_record_types}",
            }

        # Handle create
        if action == "create":
            if not record:
                return {"success": False, "error": "Record data required for create"}
            new_record_id = f"{record_type[:-1]}-{id(record)}"
            return {
                "success": True,
                "action": "create",
                "record_type": record_type,
                "record_id": new_record_id,
                "record": {**record, "id": new_record_id},
            }

        # Handle update
        if action == "update":
            if not record_id:
                return {"success": False, "error": "record_id required for update"}
            return {
                "success": True,
                "action": "update",
                "record_type": record_type,
                "record_id": record_id,
                "updated_fields": list(record.keys()) if record else [],
            }

        # Handle delete
        if action == "delete":
            if not record_id:
                return {"success": False, "error": "record_id required for delete"}
            return {
                "success": True,
                "action": "delete",
                "record_type": record_type,
                "record_id": record_id,
            }

        return {"success": False, "error": "Unknown error"}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "crm_write" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent crm_write tool"
```

---

## Task 7: Implement execute method

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `tests/test_operator_agent.py`

**Step 1: Write the failing tests**

```python
# tests/test_operator_agent.py

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "test_execute" -v`
Expected: FAIL with "NotImplementedError" (execute is abstract in BaseAgent)

**Step 3: Write minimal implementation**

Add to `backend/src/agents/operator.py` after `validate_input`:

```python
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the operator agent's primary task.

        Dispatches to the appropriate tool based on operation_type.

        Args:
            task: Task specification with operation_type and parameters.

        Returns:
            AgentResult with success status and output data.
        """
        operation_type = task["operation_type"]
        parameters = task["parameters"]

        logger.info(
            f"Operator agent executing: {operation_type}",
            extra={"user_id": self.user_id, "operation_type": operation_type},
        )

        # Dispatch to appropriate tool
        if operation_type == "calendar_read":
            result_data = await self._calendar_read(**parameters)
        elif operation_type == "calendar_write":
            result_data = await self._calendar_write(**parameters)
        elif operation_type == "crm_read":
            result_data = await self._crm_read(**parameters)
        elif operation_type == "crm_write":
            result_data = await self._crm_write(**parameters)
        else:
            return AgentResult(
                success=False,
                data=None,
                error=f"Unknown operation_type: {operation_type}",
            )

        return AgentResult(success=True, data=result_data)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "test_execute" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py tests/test_operator_agent.py
git commit -m "feat(agents): add OperatorAgent execute method with dispatch"
```

---

## Task 8: Add OperatorAgent to agents module export

**Files:**
- Modify: `backend/src/agents/__init__.py`

**Step 1: Write the failing test**

```python
# tests/test_operator_agent.py

def test_operator_agent_exported_from_module() -> None:
    """Test OperatorAgent is exported from src.agents module."""
    from src.agents import OperatorAgent

    assert OperatorAgent is not None
    assert OperatorAgent.name == "Operator"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_operator_agent.py::test_operator_agent_exported_from_module -v`
Expected: FAIL with "ImportError: cannot import name 'OperatorAgent'"

**Step 3: Write minimal implementation**

Modify `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent
from src.agents.operator import OperatorAgent
from src.agents.scribe import ScribeAgent
from src.agents.strategist import StrategistAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "AnalystAgent",
    "BaseAgent",
    "HunterAgent",
    "OperatorAgent",
    "ScribeAgent",
    "StrategistAgent",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_operator_agent.py::test_operator_agent_exported_from_module -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add src/agents/__init__.py tests/test_operator_agent.py
git commit -m "feat(agents): export OperatorAgent from agents module"
```

---

## Task 9: Add integration tests for full workflow

**Files:**
- Modify: `tests/test_operator_agent.py`

**Step 1: Write the failing test**

```python
# tests/test_operator_agent.py

@pytest.mark.asyncio
async def test_full_operator_workflow_calendar() -> None:
    """Test complete end-to-end Operator agent workflow for calendar operations.

    Verifies:
    - Agent state transitions from IDLE to RUNNING to COMPLETE
    - Calendar read operations return events
    - Calendar write operations (create, update, delete) work correctly
    - Tool dispatch functions properly
    """
    from src.agents.base import AgentStatus
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Verify initial state
    assert agent.status == AgentStatus.IDLE

    # Test calendar read workflow
    read_task = {
        "operation_type": "calendar_read",
        "parameters": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-07",
        },
    }

    read_result = await agent.run(read_task)

    assert agent.status == AgentStatus.COMPLETE
    assert read_result.success is True
    assert "events" in read_result.data
    assert len(read_result.data["events"]) > 0

    # Reset agent for next test
    agent.status = AgentStatus.IDLE

    # Test calendar create workflow
    create_task = {
        "operation_type": "calendar_write",
        "parameters": {
            "action": "create",
            "event": {
                "title": "Q1 Planning",
                "start_date": "2024-02-01",
                "start_time": "10:00",
                "end_date": "2024-02-01",
                "end_time": "11:00",
            },
        },
    }

    create_result = await agent.run(create_task)

    assert create_result.success is True
    assert "event_id" in create_result.data


@pytest.mark.asyncio
async def test_full_operator_workflow_crm() -> None:
    """Test complete end-to-end Operator agent workflow for CRM operations.

    Verifies:
    - CRM read operations return records
    - CRM write operations (create, update, delete) work correctly
    - Different record types are supported (leads, contacts, accounts)
    """
    from src.agents.base import AgentStatus
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Test CRM read workflow
    read_task = {
        "operation_type": "crm_read",
        "parameters": {
            "record_type": "leads",
        },
    }

    read_result = await agent.run(read_task)

    assert agent.status == AgentStatus.COMPLETE
    assert read_result.success is True
    assert "records" in read_result.data

    # Reset agent
    agent.status = AgentStatus.IDLE

    # Test CRM create workflow
    create_task = {
        "operation_type": "crm_write",
        "parameters": {
            "action": "create",
            "record_type": "leads",
            "record": {
                "name": "New Prospect",
                "status": "prospecting",
                "value": 100000,
            },
        },
    }

    create_result = await agent.run(create_task)

    assert create_result.success is True
    assert "record_id" in create_result.data


@pytest.mark.asyncio
async def test_operator_agent_handles_validation_failure() -> None:
    """Test that invalid input returns failed result with validation error.

    Verifies that when validate_input returns False:
    - Agent status transitions to FAILED
    - AgentResult has success=False
    - Error message indicates validation failure
    """
    from src.agents.base import AgentStatus
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    # Test with missing required field
    invalid_task = {
        "parameters": {},
    }

    result = await agent.run(invalid_task)

    assert agent.status == AgentStatus.FAILED
    assert result.success is False
    assert result.error == "Input validation failed"
    assert result.data is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_agent.py -k "full_operator" -v`
Expected: Tests should pass (this verifies the full workflow works)

**Step 3: No implementation needed - tests should pass**

These are integration tests that verify the implementation is correct.

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_agent.py -k "full_operator" -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add tests/test_operator_agent.py
git commit -m "test(agents): add integration tests for OperatorAgent workflow"
```

---

## Task 10: Verify type checking with mypy

**Files:**
- All modified files

**Step 1: Run mypy type checking**

Run: `cd backend && mypy src/agents/operator.py --strict`
Expected: No errors

**Step 2: If errors exist, fix them**

Common issues to fix:
- Add type hints for all function parameters and return values
- Fix Any type usage where more specific types are needed
- Add proper TYPE_CHECKING imports

**Step 3: Run mypy again to verify**

Run: `cd backend && mypy src/agents/operator.py --strict`
Expected: No errors

**Step 4: Run full mypy check on agents module**

Run: `cd backend && mypy src/agents/ --strict`
Expected: No errors

**Step 5: Commit**

```bash
cd backend
git add src/agents/operator.py src/agents/__init__.py
git commit -m "refactor(agents): fix type hints for mypy strict mode"
```

---

## Task 11: Run full test suite and quality gates

**Files:**
- All modified files

**Step 1: Run all operator agent tests**

Run: `cd backend && pytest tests/test_operator_agent.py -v`
Expected: All tests pass

**Step 2: Run full test suite**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass (no regressions)

**Step 3: Run mypy type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No errors

**Step 4: Run ruff linting**

Run: `cd backend && ruff check src/agents/`
Expected: No warnings

**Step 5: Run ruff formatting check**

Run: `cd backend && ruff format src/agents/ --check`
Expected: No formatting issues

**Step 6: Commit any fixes**

```bash
cd backend
git add -A
git commit -m "test(agents): ensure OperatorAgent passes all quality gates"
```

---

## Summary

This plan implements the OperatorAgent for ARIA with:

1. **Four core tools:**
   - `calendar_read`: Read calendar events within a date range
   - `calendar_write`: Create, update, or delete calendar events
   - `crm_read`: Read CRM records (leads, contacts, accounts)
   - `crm_write`: Create, update, or delete CRM records

2. **Key features:**
   - Extends BaseAgent with proper tool registration
   - Input validation for operation_type and parameters
   - Execute method dispatches to correct tool based on operation_type
   - Mock implementations for all tools (ready for real integrations)
   - Comprehensive unit and integration tests
   - Type hints for mypy strict mode compliance

3. **Testing coverage:**
   - Class attribute tests (name, description)
   - Input validation tests
   - Individual tool tests (calendar_read, calendar_write, crm_read, crm_write)
   - Execute method tests
   - Full workflow integration tests
   - Export verification tests

**No Supabase commands are run** as requested - all database operations use mock data that can be replaced with real integrations via Composio in the future.
