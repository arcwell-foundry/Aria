"""OperatorAgent module for ARIA.

Provides system operations capabilities including calendar management,
CRM read/write operations, and third-party integration management.

Integration status is checked against the user_integrations table in
Supabase.  When connected, actions are executed via the Composio SDK
through the ComposioOAuthClient.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)

# Maps an operation category to the integration_type values that satisfy it.
_CALENDAR_INTEGRATION_TYPES = ("google_calendar", "outlook_calendar", "outlook")
_CRM_INTEGRATION_TYPES = ("salesforce", "hubspot")

# ---------------------------------------------------------------------------
# Composio action slug mappings per provider
# ---------------------------------------------------------------------------

_CALENDAR_READ_ACTIONS: dict[str, str] = {
    "google_calendar": "GOOGLECALENDAR_FIND_EVENT",
    "outlook_calendar": "OUTLOOK_CALENDAR_FIND_EVENTS",
    "outlook": "OUTLOOK_CALENDAR_FIND_EVENTS",
}

_CALENDAR_WRITE_ACTIONS: dict[str, dict[str, str]] = {
    "google_calendar": {
        "create": "GOOGLECALENDAR_CREATE_EVENT",
        "update": "GOOGLECALENDAR_UPDATE_EVENT",
        "delete": "GOOGLECALENDAR_DELETE_EVENT",
    },
    "outlook_calendar": {
        "create": "OUTLOOK_CALENDAR_CREATE_EVENT",
        "update": "OUTLOOK_CALENDAR_UPDATE_EVENT",
        "delete": "OUTLOOK_CALENDAR_DELETE_EVENT",
    },
    "outlook": {
        "create": "OUTLOOK_CALENDAR_CREATE_EVENT",
        "update": "OUTLOOK_CALENDAR_UPDATE_EVENT",
        "delete": "OUTLOOK_CALENDAR_DELETE_EVENT",
    },
}

_CRM_READ_ACTIONS: dict[str, dict[str, str]] = {
    "salesforce": {
        "leads": "SALESFORCE_FETCH_SOBJECT",
        "contacts": "SALESFORCE_FETCH_SOBJECT",
        "accounts": "SALESFORCE_FETCH_SOBJECT",
    },
    "hubspot": {
        "leads": "HUBSPOT_LIST_CONTACTS",
        "contacts": "HUBSPOT_LIST_CONTACTS",
        "accounts": "HUBSPOT_LIST_COMPANIES",
    },
}

# Salesforce uses the same action for all record types with sObject type in
# params.  HubSpot uses different actions per record type.
_CRM_WRITE_ACTIONS: dict[str, dict[str, dict[str, str]]] = {
    "salesforce": {
        "create": {
            "leads": "SALESFORCE_CREATE_SOBJECT",
            "contacts": "SALESFORCE_CREATE_SOBJECT",
            "accounts": "SALESFORCE_CREATE_SOBJECT",
        },
        "update": {
            "leads": "SALESFORCE_UPDATE_SOBJECT",
            "contacts": "SALESFORCE_UPDATE_SOBJECT",
            "accounts": "SALESFORCE_UPDATE_SOBJECT",
        },
        "delete": {
            "leads": "SALESFORCE_DELETE_SOBJECT",
            "contacts": "SALESFORCE_DELETE_SOBJECT",
            "accounts": "SALESFORCE_DELETE_SOBJECT",
        },
    },
    "hubspot": {
        "create": {
            "leads": "HUBSPOT_CREATE_CONTACT",
            "contacts": "HUBSPOT_CREATE_CONTACT",
            "accounts": "HUBSPOT_CREATE_COMPANY",
        },
        "update": {
            "leads": "HUBSPOT_UPDATE_CONTACT",
            "contacts": "HUBSPOT_UPDATE_CONTACT",
            "accounts": "HUBSPOT_UPDATE_COMPANY",
        },
        "delete": {
            "leads": "HUBSPOT_DELETE_CONTACT",
            "contacts": "HUBSPOT_DELETE_CONTACT",
            "accounts": "HUBSPOT_DELETE_COMPANY",
        },
    },
}

# Map internal record_type names to Salesforce SObject type names.
_SALESFORCE_SOBJECT_MAP: dict[str, str] = {
    "leads": "Lead",
    "contacts": "Contact",
    "accounts": "Account",
}


class OperatorAgent(SkillAwareAgent):
    """System operations for calendar, CRM, and integrations.

    The Operator agent manages external system interactions including
    calendar read/write operations, CRM data synchronization, and
    third-party integration management.

    All four public tools check the user's real integration status before
    executing actions via the Composio SDK.
    """

    name = "Operator"
    description = "System operations for calendar, CRM, and integrations"
    agent_id = "operator"
    VALID_OPERATION_TYPES = {"calendar_read", "calendar_write", "crm_read", "crm_write"}

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the Operator agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        self._integration_cache: dict[str, Any] = {}
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )

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
        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

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

    # ------------------------------------------------------------------
    # Integration status helper
    # ------------------------------------------------------------------

    async def _check_integration_status(
        self,
        category: str,
    ) -> dict[str, Any]:
        """Check whether the user has an active integration for *category*.

        Queries the ``user_integrations`` table in Supabase and returns a
        lightweight status dict that the tool methods use to decide what
        to return.

        Args:
            category: ``"calendar"`` or ``"crm"``.

        Returns:
            ``{"connected": bool, "provider": str | None,
              "integration_id": str | None,
              "composio_connection_id": str | None}``
        """
        integration_types: tuple[str, ...]
        if category == "calendar":
            integration_types = _CALENDAR_INTEGRATION_TYPES
        elif category == "crm":
            integration_types = _CRM_INTEGRATION_TYPES
        else:
            logger.warning("Unknown integration category: %s", category)
            return {
                "connected": False,
                "provider": None,
                "integration_id": None,
                "composio_connection_id": None,
            }

        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()

            # Query for any active integration that matches one of the
            # accepted types for this category.
            response = (
                client.table("user_integrations")
                .select("id, integration_type, status, composio_connection_id")
                .eq("user_id", self.user_id)
                .eq("status", "active")
                .in_("integration_type", list(integration_types))
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                row = response.data[0]
                return {
                    "connected": True,
                    "provider": row.get("integration_type"),
                    "integration_id": row.get("id"),
                    "composio_connection_id": row.get("composio_connection_id"),
                }

        except Exception:
            logger.warning(
                "Failed to query user_integrations for user %s (category=%s). "
                "Treating as not connected.",
                self.user_id,
                category,
                exc_info=True,
            )

        return {
            "connected": False,
            "provider": None,
            "integration_id": None,
            "composio_connection_id": None,
        }

    # ------------------------------------------------------------------
    # Composio execution helper
    # ------------------------------------------------------------------

    async def _execute_composio_action(
        self,
        connection_id: str,
        action: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a Composio action via the OAuth client.

        Args:
            connection_id: Composio connection ID for the user's integration.
            action: Composio tool slug (e.g., ``'GOOGLECALENDAR_FIND_EVENT'``).
            params: Parameters for the action.

        Returns:
            Action result dict, or error/not_configured dict on failure.
        """
        from src.core.config import settings

        if not settings.COMPOSIO_API_KEY:
            return {
                "status": "not_configured",
                "message": ("Set COMPOSIO_API_KEY in environment to enable integrations."),
            }

        try:
            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()
            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action=action,
                params=params,
            )
            return result

        except Exception as e:
            logger.error(
                "Composio action %s failed: %s",
                action,
                e,
                exc_info=True,
                extra={"user_id": self.user_id},
            )
            return {
                "status": "error",
                "message": f"Integration action failed: {e}",
            }

    # ------------------------------------------------------------------
    # Calendar tools
    # ------------------------------------------------------------------

    async def _calendar_read(
        self,
        start_date: str,
        end_date: str | None = None,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Read calendar events within a date range.

        Checks the user's integration status first.  If no calendar
        integration is active an honest "not connected" payload is
        returned.  When connected, executes via Composio SDK.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: Optional end date in YYYY-MM-DD format.
            calendar_id: Optional calendar identifier.

        Returns:
            Dictionary with connection status and events.
        """
        logger.info(
            "Reading calendar events from %s to %s",
            start_date,
            end_date or "present",
            extra={"user_id": self.user_id, "calendar_id": calendar_id},
        )

        status = await self._check_integration_status("calendar")

        if not status["connected"]:
            return {
                "connected": False,
                "message": (
                    "Calendar integration not connected. "
                    "Connect Google Calendar or Outlook in Settings > Integrations "
                    "to enable calendar access."
                ),
                "events": [],
                "total_count": 0,
            }

        provider = status["provider"]
        connection_id = status.get("composio_connection_id")

        if not connection_id:
            return {
                "connected": True,
                "provider": provider,
                "message": (
                    f"Calendar integration detected ({provider}), but the "
                    "connection ID is missing. Please reconnect in "
                    "Settings > Integrations."
                ),
                "events": [],
                "total_count": 0,
            }

        action_slug = _CALENDAR_READ_ACTIONS.get(provider)  # type: ignore[arg-type]
        if not action_slug:
            return {
                "connected": True,
                "provider": provider,
                "message": (f"No calendar read action mapped for provider '{provider}'."),
                "events": [],
                "total_count": 0,
            }

        # Build Composio-compatible params
        composio_params: dict[str, Any] = {
            "timeMin": f"{start_date}T00:00:00Z",
        }
        if end_date:
            composio_params["timeMax"] = f"{end_date}T23:59:59Z"
        if calendar_id:
            composio_params["calendarId"] = calendar_id

        result = await self._execute_composio_action(
            connection_id,
            action_slug,
            composio_params,
        )

        if result.get("status") in ("not_configured", "error"):
            return {
                "connected": True,
                "provider": provider,
                "message": result.get("message", "Failed to read calendar events."),
                "events": [],
                "total_count": 0,
            }

        # Normalize: Composio may return events under various keys
        events = result.get("events", result.get("items", result.get("data", [])))
        if not isinstance(events, list):
            events = [events] if events else []

        return {
            "connected": True,
            "provider": provider,
            "events": events,
            "total_count": len(events),
        }

    async def _calendar_write(
        self,
        action: str,
        event: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Write calendar operations (create, update, delete).

        Checks the user's integration status first.  Returns honest
        status messages when the integration is missing.  When connected,
        executes via Composio SDK.

        Args:
            action: Operation type - ``"create"``, ``"update"``, or ``"delete"``.
            event: Event data for create/update operations.
            event_id: Event ID for update/delete operations.

        Returns:
            Dictionary with connection status and operation outcome.
        """
        valid_actions = {"create", "update", "delete"}

        logger.info(
            "Calendar write operation: %s",
            action,
            extra={"user_id": self.user_id, "event_id": event_id},
        )

        # Validate action before checking integration so we give immediate
        # feedback for bad inputs.
        if action not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action: {action}. Must be one of {valid_actions}",
            }

        status = await self._check_integration_status("calendar")

        if not status["connected"]:
            return {
                "connected": False,
                "success": False,
                "message": (
                    "Calendar integration not connected. "
                    "Connect Google Calendar or Outlook in Settings > Integrations "
                    "to enable calendar write operations."
                ),
            }

        provider = status["provider"]
        connection_id = status.get("composio_connection_id")

        if not connection_id:
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": (
                    f"Calendar integration detected ({provider}), but the "
                    "connection ID is missing. Please reconnect in "
                    "Settings > Integrations."
                ),
            }

        provider_actions = _CALENDAR_WRITE_ACTIONS.get(provider)  # type: ignore[arg-type]
        action_slug = provider_actions.get(action) if provider_actions else None
        if not action_slug:
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": (f"No calendar {action} action mapped for provider '{provider}'."),
            }

        # Build Composio-compatible params
        composio_params: dict[str, Any] = {}
        if event:
            composio_params.update(event)
        if event_id:
            composio_params["eventId"] = event_id

        result = await self._execute_composio_action(
            connection_id,
            action_slug,
            composio_params,
        )

        if result.get("status") in ("not_configured", "error"):
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": result.get("message", f"Failed to {action} calendar event."),
            }

        return {
            "connected": True,
            "success": True,
            "provider": provider,
            "data": result,
        }

    # ------------------------------------------------------------------
    # CRM tools
    # ------------------------------------------------------------------

    async def _crm_read(
        self,
        record_type: str,
        record_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read CRM records (leads, contacts, accounts).

        Checks the user's integration status first.  Returns honest
        status messages when the CRM is not connected.  When connected,
        executes via Composio SDK.

        Args:
            record_type: Type of record - ``"leads"``, ``"contacts"``, ``"accounts"``.
            record_id: Optional specific record ID to fetch.
            filters: Optional filters for querying records.

        Returns:
            Dictionary with connection status and records.
        """
        logger.info(
            "Reading CRM records: %s",
            record_type,
            extra={"user_id": self.user_id, "record_id": record_id},
        )

        status = await self._check_integration_status("crm")

        if not status["connected"]:
            return {
                "connected": False,
                "message": (
                    "CRM integration not connected. "
                    "Connect Salesforce or HubSpot in Settings > Integrations "
                    "to enable CRM data access."
                ),
                "records": [],
                "total_count": 0,
            }

        provider = status["provider"]
        connection_id = status.get("composio_connection_id")

        if not connection_id:
            return {
                "connected": True,
                "provider": provider,
                "message": (
                    f"CRM integration detected ({provider}), but the "
                    "connection ID is missing. Please reconnect in "
                    "Settings > Integrations."
                ),
                "records": [],
                "total_count": 0,
            }

        provider_actions = _CRM_READ_ACTIONS.get(provider)  # type: ignore[arg-type]
        action_slug = provider_actions.get(record_type) if provider_actions else None
        if not action_slug:
            return {
                "connected": True,
                "provider": provider,
                "message": (
                    f"No CRM read action mapped for provider '{provider}' "
                    f"and record type '{record_type}'."
                ),
                "records": [],
                "total_count": 0,
            }

        # Build Composio-compatible params
        composio_params: dict[str, Any] = {}
        if provider == "salesforce":
            composio_params["sObjectType"] = _SALESFORCE_SOBJECT_MAP.get(record_type, record_type)
        if record_id:
            composio_params["record_id"] = record_id
        if filters:
            composio_params.update(filters)

        result = await self._execute_composio_action(
            connection_id,
            action_slug,
            composio_params,
        )

        if result.get("status") in ("not_configured", "error"):
            return {
                "connected": True,
                "provider": provider,
                "message": result.get("message", "Failed to read CRM records."),
                "records": [],
                "total_count": 0,
            }

        # Normalize: Composio may return records under various keys
        records = result.get("records", result.get("results", result.get("data", [])))
        if not isinstance(records, list):
            records = [records] if records else []

        return {
            "connected": True,
            "provider": provider,
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

        Checks the user's integration status first.  Returns honest
        status messages when the CRM is not connected.  When connected,
        executes via Composio SDK.

        Args:
            action: Operation type - ``"create"``, ``"update"``, or ``"delete"``.
            record_type: Type of record - ``"leads"``, ``"contacts"``, ``"accounts"``.
            record: Record data for create/update operations.
            record_id: Record ID for update/delete operations.

        Returns:
            Dictionary with connection status and operation outcome.
        """
        valid_actions = {"create", "update", "delete"}
        valid_record_types = {"leads", "contacts", "accounts"}

        logger.info(
            "CRM write operation: %s on %s",
            action,
            record_type,
            extra={"user_id": self.user_id, "record_id": record_id},
        )

        # Validate inputs before checking integration.
        if action not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action: {action}. Must be one of {valid_actions}",
            }
        if record_type not in valid_record_types:
            return {
                "success": False,
                "error": (
                    f"Invalid record_type: {record_type}. Must be one of {valid_record_types}"
                ),
            }

        status = await self._check_integration_status("crm")

        if not status["connected"]:
            return {
                "connected": False,
                "success": False,
                "message": (
                    "CRM integration not connected. "
                    "Connect Salesforce or HubSpot in Settings > Integrations "
                    "to enable CRM write operations."
                ),
            }

        provider = status["provider"]
        connection_id = status.get("composio_connection_id")

        if not connection_id:
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": (
                    f"CRM integration detected ({provider}), but the "
                    "connection ID is missing. Please reconnect in "
                    "Settings > Integrations."
                ),
            }

        provider_actions = _CRM_WRITE_ACTIONS.get(provider)  # type: ignore[arg-type]
        action_slug = None
        if provider_actions:
            action_map = provider_actions.get(action)
            if action_map:
                action_slug = action_map.get(record_type)

        if not action_slug:
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": (
                    f"No CRM {action} action mapped for provider '{provider}' "
                    f"and record type '{record_type}'."
                ),
            }

        # Build Composio-compatible params
        composio_params: dict[str, Any] = {}
        if provider == "salesforce":
            composio_params["sObjectType"] = _SALESFORCE_SOBJECT_MAP.get(record_type, record_type)
        if record:
            composio_params.update(record)
        if record_id:
            composio_params["record_id"] = record_id

        result = await self._execute_composio_action(
            connection_id,
            action_slug,
            composio_params,
        )

        if result.get("status") in ("not_configured", "error"):
            return {
                "connected": True,
                "success": False,
                "provider": provider,
                "message": result.get(
                    "message",
                    f"Failed to {action} CRM {record_type} record.",
                ),
            }

        return {
            "connected": True,
            "success": True,
            "provider": provider,
            "data": result,
        }
