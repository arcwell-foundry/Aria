"""OperatorAgent module for ARIA.

Provides system operations capabilities including calendar management,
CRM read/write operations, and third-party integration management.

Integration status is checked against the user_integrations table in
Supabase.  When a Composio client is not yet available the agent returns
honest "not configured" messages instead of fabricated mock data.
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


class OperatorAgent(SkillAwareAgent):
    """System operations for calendar, CRM, and integrations.

    The Operator agent manages external system interactions including
    calendar read/write operations, CRM data synchronization, and
    third-party integration management.

    All four public tools check the user's real integration status before
    returning data.  No hardcoded mock data is ever returned.
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
              "integration_id": str | None}``
        """
        integration_types: tuple[str, ...]
        if category == "calendar":
            integration_types = _CALENDAR_INTEGRATION_TYPES
        elif category == "crm":
            integration_types = _CRM_INTEGRATION_TYPES
        else:
            logger.warning("Unknown integration category: %s", category)
            return {"connected": False, "provider": None, "integration_id": None}

        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()

            # Query for any active integration that matches one of the
            # accepted types for this category.
            response = (
                client.table("user_integrations")
                .select("id, integration_type, status")
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
                }

        except Exception:
            logger.warning(
                "Failed to query user_integrations for user %s (category=%s). "
                "Treating as not connected.",
                self.user_id,
                category,
                exc_info=True,
            )

        return {"connected": False, "provider": None, "integration_id": None}

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
        returned.  If the integration exists but the Composio client is
        not yet wired up, a clear status message is returned instead of
        fabricated data.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: Optional end date in YYYY-MM-DD format.
            calendar_id: Optional calendar identifier.

        Returns:
            Dictionary describing connection status and (eventually) events.
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

        # Integration row exists — Composio client is not yet available.
        return {
            "connected": True,
            "provider": status["provider"],
            "message": (
                f"Calendar integration detected ({status['provider']}), "
                "but the Composio client is not yet configured. "
                "Events will be available once Composio setup is complete."
            ),
            "events": [],
            "total_count": 0,
        }

    async def _calendar_write(
        self,
        action: str,
        event: dict[str, Any] | None = None,  # noqa: ARG002 — needed when Composio is wired
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Write calendar operations (create, update, delete).

        Checks the user's integration status first.  Returns honest
        status messages when the integration is missing or the Composio
        client is not yet wired up.

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

        # Integration row exists — Composio client is not yet available.
        return {
            "connected": True,
            "success": False,
            "provider": status["provider"],
            "message": (
                f"Calendar integration detected ({status['provider']}), "
                "but the Composio client is not yet configured. "
                "Write operations will be available once Composio setup is complete."
            ),
        }

    # ------------------------------------------------------------------
    # CRM tools
    # ------------------------------------------------------------------

    async def _crm_read(
        self,
        record_type: str,
        record_id: str | None = None,
        filters: dict[str, Any] | None = None,  # noqa: ARG002 — needed when Composio is wired
    ) -> dict[str, Any]:
        """Read CRM records (leads, contacts, accounts).

        Checks the user's integration status first.  Returns honest
        status messages when the CRM is not connected or when the
        Composio client is not yet wired up.

        Args:
            record_type: Type of record - ``"leads"``, ``"contacts"``, ``"accounts"``.
            record_id: Optional specific record ID to fetch.
            filters: Optional filters for querying records.

        Returns:
            Dictionary with connection status and (eventually) records.
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

        # Integration row exists — Composio client is not yet available.
        return {
            "connected": True,
            "provider": status["provider"],
            "message": (
                f"CRM integration detected ({status['provider']}), "
                "but the Composio client is not yet configured. "
                "CRM records will be available once Composio setup is complete."
            ),
            "records": [],
            "total_count": 0,
        }

    async def _crm_write(
        self,
        action: str,
        record_type: str,
        record: dict[str, Any] | None = None,  # noqa: ARG002 — needed when Composio is wired
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Write CRM operations (create, update, delete).

        Checks the user's integration status first.  Returns honest
        status messages when the CRM is not connected or when the
        Composio client is not yet wired up.

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

        # Integration row exists — Composio client is not yet available.
        return {
            "connected": True,
            "success": False,
            "provider": status["provider"],
            "message": (
                f"CRM integration detected ({status['provider']}), "
                "but the Composio client is not yet configured. "
                "Write operations will be available once Composio setup is complete."
            ),
        }
