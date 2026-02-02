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
    """System operations for calendar, CRM, and integrations.

    The Operator agent manages external system interactions including
    calendar read/write operations, CRM data synchronization, and
    third-party integration management.
    """

    name = "Operator"
    description = "System operations for calendar, CRM, and integrations"
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

        return isinstance(task["parameters"], dict)

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
        # action is guaranteed to be "delete" here due to validation above
        if not event_id:
            return {"success": False, "error": "event_id required for delete"}
        return {
            "success": True,
            "action": "delete",
            "event_id": event_id,
        }

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
        # action is guaranteed to be "delete" here due to validation above
        if not record_id:
            return {"success": False, "error": "record_id required for delete"}
        return {
            "success": True,
            "action": "delete",
            "record_type": record_type,
            "record_id": record_id,
        }
