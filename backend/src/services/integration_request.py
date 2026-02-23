"""Integration Request Service — conversational prompts for missing integrations.

When an agent execution detects a missing integration, this service sends a
conversational message to the user via WebSocket with actionable UICommands
to connect the integration, rather than failing silently.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Map integration categories to human-readable names and connection details
_INTEGRATION_INFO: dict[str, dict[str, Any]] = {
    "calendar": {
        "display_name": "calendar",
        "providers": ["Google Calendar", "Outlook"],
        "route": "/settings/integrations",
        "benefit": "schedule meetings, check availability, and generate meeting briefs",
    },
    "crm": {
        "display_name": "CRM",
        "providers": ["Salesforce", "HubSpot"],
        "route": "/settings/integrations",
        "benefit": "sync pipeline data, track leads, and update contacts",
    },
    "gmail": {
        "display_name": "email",
        "providers": ["Gmail"],
        "route": "/settings/integrations",
        "benefit": "scan your inbox, draft responses, and track email conversations",
    },
    "outlook_email": {
        "display_name": "email",
        "providers": ["Outlook"],
        "route": "/settings/integrations",
        "benefit": "scan your inbox, draft responses, and track email conversations",
    },
    "slack": {
        "display_name": "Slack",
        "providers": ["Slack"],
        "route": "/settings/integrations",
        "benefit": "send notifications and collaborate with your team",
    },
}


class IntegrationRequestService:
    """Generates conversational integration requests when agents need missing connections."""

    async def send_integration_request(
        self,
        user_id: str,
        integration_category: str,
        agent_name: str,
        task_description: str,
    ) -> bool:
        """Send a conversational integration request to the user via WebSocket.

        Args:
            user_id: The user who needs to connect.
            integration_category: The integration category (calendar, crm, gmail, etc.).
            agent_name: The agent that needs the integration.
            task_description: What the agent was trying to do.

        Returns:
            True if the message was sent, False otherwise.
        """
        from src.core.ws import ws_manager

        info = _INTEGRATION_INFO.get(integration_category, {})
        display_name = info.get("display_name", integration_category)
        providers = info.get("providers", [integration_category.title()])
        route = info.get("route", "/settings/integrations")
        benefit = info.get("benefit", "complete this task")

        provider_list = " or ".join(providers)

        message = (
            f"To {task_description}, I need access to your {display_name}. "
            f"Connecting {provider_list} would let me {benefit}. "
            f"Would you like to set that up?"
        )

        ui_commands = [
            {
                "action": "navigate",
                "route": route,
            },
        ]

        suggestions = [
            f"Connect {providers[0]}",
            "Skip this step",
            "Tell me more",
        ]

        rich_content = [{
            "type": "integration_request",
            "data": {
                "integration": integration_category,
                "display_name": display_name,
                "providers": providers,
                "benefit": benefit,
                "route": route,
                "agent": agent_name,
            },
        }]

        try:
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=message,
                rich_content=rich_content,
                ui_commands=ui_commands,
                suggestions=suggestions,
            )

            # Also store as a conversation message with metadata for tracking
            await self._store_integration_request(
                user_id=user_id,
                integration_category=integration_category,
                agent_name=agent_name,
                message=message,
            )

            logger.info(
                "Integration request sent",
                extra={
                    "user_id": user_id,
                    "integration": integration_category,
                    "agent": agent_name,
                },
            )
            return True
        except Exception:
            logger.warning(
                "Failed to send integration request",
                extra={
                    "user_id": user_id,
                    "integration": integration_category,
                },
                exc_info=True,
            )
            return False

    async def _store_integration_request(
        self,
        user_id: str,
        integration_category: str,
        agent_name: str,
        message: str,
    ) -> None:
        """Store the integration request in login_message_queue for offline users.

        Also records in activity feed so the request is visible in the UI.

        Args:
            user_id: The user's ID.
            integration_category: Which integration is needed.
            agent_name: Which agent triggered the request.
            message: The message that was sent.
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()

            # Store in login_message_queue (in case user is offline when triggered)
            db.table("login_message_queue").insert(
                {
                    "user_id": user_id,
                    "title": f"Connect {integration_category}",
                    "message": message,
                    "category": "integration_request",
                    "metadata": {
                        "type": "integration_request",
                        "integration": integration_category,
                        "agent": agent_name,
                    },
                    "delivered": False,
                }
            ).execute()
        except Exception:
            logger.debug("Failed to store integration request", exc_info=True)

        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            await activity.log_activity(
                user_id=user_id,
                activity_type="integration_request",
                title=f"Integration needed: {integration_category}",
                description=f"{agent_name.title()} needs {integration_category} access",
                metadata={
                    "integration": integration_category,
                    "agent": agent_name,
                },
            )
        except Exception:
            logger.debug("Failed to log integration request activity", exc_info=True)


def check_agent_result_for_missing_integration(
    result: dict[str, Any],
) -> str | None:
    """Check if an agent result indicates a missing integration.

    Args:
        result: The agent execution result dict.

    Returns:
        Integration category string if missing, None otherwise.
    """
    if not isinstance(result, dict):
        return None

    # Operator agent returns {"connected": False} when integration is missing
    if result.get("connected") is False:
        message = result.get("message", "").lower()
        if "calendar" in message:
            return "calendar"
        if "crm" in message or "salesforce" in message or "hubspot" in message:
            return "crm"
        if "email" in message or "gmail" in message:
            return "gmail"
        if "slack" in message:
            return "slack"
        return "unknown"

    return None
