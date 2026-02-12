"""Integration Wizard service for onboarding (US-909).

Manages CRM, Calendar, and Slack integrations via Composio OAuth.
This is straightforward plumbing — each integration is a connect/disconnect toggle.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

logger = logging.getLogger(__name__)


class IntegrationPreferences(BaseModel):
    """User preferences for integrations.

    Users can configure notification routing and sync frequency
    for connected integrations.
    """

    slack_channels: list[str] = Field(default_factory=list)  # Channels ARIA monitors
    notification_enabled: bool = True  # Whether ARIA sends notifications via integrations
    sync_frequency_hours: int = 1  # How often to sync data (1, 6, 12, 24)


class IntegrationStatus(BaseModel):
    """Status of a single integration."""

    name: str  # "SALESFORCE", "HUBSPOT", etc.
    display_name: str  # "Salesforce", "HubSpot", etc.
    category: str  # "crm", "calendar", "slack"
    connected: bool = False
    connected_at: str | None = None
    connection_id: str | None = None


class IntegrationWizardService:
    """Manages third-party integrations for onboarding.

    This service handles the US-909 requirements:
    - CRM connection: Salesforce and HubSpot via Composio OAuth
    - Calendar integration: Google Calendar and Outlook Calendar
    - Slack connection: Workspace OAuth with channel configuration
    - Connection status checking
    - Preferences management (notification routing, sync frequency)
    - Readiness score updates
    - Episodic memory recording
    """

    # Integration configurations
    INTEGRATIONS = {
        # CRM
        "SALESFORCE": {
            "display_name": "Salesforce",
            "category": "crm",
            "composio_type": "salesforce",
        },
        "HUBSPOT": {
            "display_name": "HubSpot",
            "category": "crm",
            "composio_type": "hubspot",
        },
        # Calendar
        "GOOGLECALENDAR": {
            "display_name": "Google Calendar",
            "category": "calendar",
            "composio_type": "googlecalendar",
        },
        "OUTLOOK365CALENDAR": {
            "display_name": "Outlook Calendar",
            "category": "calendar",
            "composio_type": "outlook",
        },
        # Messaging
        "SLACK": {
            "display_name": "Slack",
            "category": "messaging",
            "composio_type": "slack",
        },
    }

    CATEGORY_DESCRIPTIONS = {
        "crm": "Pipeline visibility, deal tracking, contact enrichment",
        "calendar": "Meeting prep, scheduling intelligence, availability awareness",
        "messaging": "Team context, communication patterns, channel monitoring",
    }

    def __init__(self) -> None:
        """Initialize service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_integration_status(self, user_id: str) -> dict[str, Any]:
        """Get connection status for all integrations.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Dict with integration statuses grouped by category:
            {
                "crm": [IntegrationStatus, ...],
                "calendar": [IntegrationStatus, ...],
                "messaging": [IntegrationStatus, ...],
                "preferences": IntegrationPreferences
            }
        """
        # Get user's connected integrations
        result = self._db.table("user_integrations").select("*").eq("user_id", user_id).execute()

        connected_integrations: dict[str, dict[str, Any]] = {}
        if result.data:
            for row in result.data:
                integration_type = row.get("integration_type")
                if integration_type:
                    connected_integrations[integration_type] = {
                        "connected_at": row.get("created_at"),
                        "connection_id": row.get("composio_connection_id"),
                    }

        # Build status for all integrations
        status_by_category: dict[str, list[IntegrationStatus]] = {
            "crm": [],
            "calendar": [],
            "messaging": [],
        }

        for app_name, config in self.INTEGRATIONS.items():
            category = config["category"]
            composio_type = config["composio_type"]
            connected = composio_type in connected_integrations

            status = IntegrationStatus(
                name=app_name,
                display_name=config["display_name"],
                category=category,
                connected=connected,
                connected_at=connected_integrations.get(composio_type, {}).get("connected_at")
                if connected
                else None,
                connection_id=connected_integrations.get(composio_type, {}).get("connection_id")
                if connected
                else None,
            )
            status_by_category[category].append(status)

        # Get user preferences
        preferences = await self._get_preferences(user_id)

        return {
            "crm": [s.model_dump() for s in status_by_category["crm"]],
            "calendar": [s.model_dump() for s in status_by_category["calendar"]],
            "messaging": [s.model_dump() for s in status_by_category["messaging"]],
            "preferences": preferences.model_dump(),
        }

    async def connect_integration(self, user_id: str, app_name: str) -> dict[str, Any]:
        """Initiate OAuth flow for an integration.

        Args:
            user_id: The authenticated user's ID.
            app_name: The integration name (e.g., "SALESFORCE", "GOOGLECALENDAR").

        Returns:
            Dict with auth_url for frontend redirect:
            {"auth_url": str, "connection_id": str, "status": "pending"}
            or {"status": "error", "message": str} on failure.
        """
        if app_name not in self.INTEGRATIONS:
            logger.warning(
                "Invalid integration name",
                extra={"app_name": app_name, "user_id": user_id},
            )
            return {
                "status": "error",
                "message": f"Unknown integration: {app_name}",
            }

        try:
            oauth_client = get_oauth_client()
            integration_type = self.INTEGRATIONS[app_name]["composio_type"]
            redirect_uri = (
                f"{self._get_base_url()}/settings/integrations/callback?redirect_to=onboarding"
            )

            # Generate OAuth URL via Composio SDK (returns real connection ID)
            auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
                user_id=user_id,
                integration_type=integration_type,
                redirect_uri=redirect_uri,
            )

            logger.info(
                "OAuth initiated for integration",
                extra={"user_id": user_id, "app_name": app_name},
            )

            return {
                "auth_url": auth_url,
                "connection_id": connection_id,
                "status": "pending",
            }

        except ValueError as e:
            # Auth config not found — actionable error for the user
            logger.warning(
                "OAuth auth config missing",
                extra={"user_id": user_id, "app_name": app_name, "error": str(e)},
            )
            return {
                "auth_url": "",
                "status": "error",
                "message": str(e),
            }

        except Exception as e:
            logger.warning(
                "OAuth initiation failed",
                extra={"user_id": user_id, "app_name": app_name, "error": str(e)},
            )
            return {
                "auth_url": "",
                "status": "error",
                "message": str(e),
            }

    async def disconnect_integration(self, user_id: str, app_name: str) -> dict[str, Any]:
        """Disconnect an integration.

        Args:
            user_id: The authenticated user's ID.
            app_name: The integration name to disconnect.

        Returns:
            Dict with status: {"status": "disconnected"}
            or {"status": "error", "message": str} on failure.
        """
        if app_name not in self.INTEGRATIONS:
            return {
                "status": "error",
                "message": f"Unknown integration: {app_name}",
            }

        try:
            # Get the connection record
            integration_type = self.INTEGRATIONS[app_name]["composio_type"]
            result = (
                self._db.table("user_integrations")
                .select("composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type)
                .maybe_single()
                .execute()
            )

            if not result or not result.data:
                return {
                    "status": "error",
                    "message": "Integration not connected",
                }

            connection_id = result.data.get("composio_connection_id")

            # Disconnect via Composio if we have a connection_id
            if connection_id:
                try:
                    oauth_client = get_oauth_client()
                    await oauth_client.disconnect_integration(
                        user_id=user_id,
                        connection_id=connection_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Composio disconnect failed, removing local record",
                        extra={"connection_id": connection_id, "error": str(e)},
                    )

            # Remove local record
            (
                self._db.table("user_integrations")
                .delete()
                .eq("user_id", user_id)
                .eq("integration_type", integration_type)
                .execute()
            )

            logger.info(
                "Integration disconnected",
                extra={"user_id": user_id, "app_name": app_name},
            )

            return {"status": "disconnected"}

        except Exception as e:
            logger.warning(
                "Disconnect failed",
                extra={"user_id": user_id, "app_name": app_name, "error": str(e)},
            )
            return {
                "status": "error",
                "message": str(e),
            }

    async def save_integration_preferences(
        self, user_id: str, preferences: IntegrationPreferences
    ) -> dict[str, Any]:
        """Save integration preferences and update readiness scores.

        Args:
            user_id: The authenticated user's ID.
            preferences: The integration preferences to save.

        Returns:
            Dict with save status: {"status": "saved"}
        """
        # Save to user_settings (merge into existing integrations JSONB)
        existing = (
            self._db.table("user_settings")
            .select("integrations")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        merged_integrations = (
            existing.data.get("integrations", {}) if existing and existing.data else {}
        )
        merged_integrations["slack_channels"] = preferences.slack_channels
        merged_integrations["notification_enabled"] = preferences.notification_enabled
        merged_integrations["sync_frequency_hours"] = preferences.sync_frequency_hours
        self._db.table("user_settings").upsert(
            {
                "user_id": user_id,
                "integrations": merged_integrations,
            },
            on_conflict="user_id",
        ).execute()

        # Update readiness score (integrations domain)
        # Each connected integration contributes to readiness
        status = await self.get_integration_status(user_id)
        connected_count = (
            sum(1 for i in status["crm"] if i["connected"])
            + sum(1 for i in status["calendar"] if i["connected"])
            + (1 if status["messaging"] and any(i["connected"] for i in status["messaging"]) else 0)
        )

        # Update readiness: each integration = ~15 points, max 60 (4 integrations)
        readiness_update = min(60.0, connected_count * 15.0)

        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(
                user_id,
                {"integrations": readiness_update},
            )
        except Exception as e:
            logger.warning(
                "Readiness update failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Create prospective memory entries for unconnected integrations (knowledge gaps)
        try:
            missing_categories: list[str] = []
            if not any(i["connected"] for i in status["crm"]):
                missing_categories.append("CRM")
            if not any(i["connected"] for i in status["calendar"]):
                missing_categories.append("Calendar")
            if not any(i["connected"] for i in status["messaging"]):
                missing_categories.append("Slack")

            if missing_categories:
                for category in missing_categories:
                    self._db.table("prospective_memories").insert(
                        {
                            "user_id": user_id,
                            "task": f"Connect {category} integration for richer intelligence",
                            "due_date": None,
                            "status": "pending",
                            "metadata": {
                                "type": "integration_gap",
                                "category": category.lower(),
                                "priority": "medium",
                                "source": "onboarding_integration_wizard",
                            },
                        }
                    ).execute()
        except Exception as e:
            logger.warning(
                "Failed to create integration gap entries",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Record in episodic memory
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_integrations_configured",
                content=f"Integration preferences saved. {connected_count} integrations connected.",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "connected_count": connected_count,
                    "slack_channels": preferences.slack_channels,
                    "notification_enabled": preferences.notification_enabled,
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(
                "Episodic record failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Audit log entry
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.PROCEDURAL,
            metadata={
                "action": "integration_preferences_saved",
                "connected_count": connected_count,
                "slack_channels": preferences.slack_channels,
            },
            suppress_errors=True,
        )

        logger.info(
            "Integration preferences saved",
            extra={"user_id": user_id, "connected_count": connected_count},
        )

        return {"status": "saved", "connected_count": connected_count}

    async def _get_preferences(self, user_id: str) -> IntegrationPreferences:
        """Get user's integration preferences.

        Args:
            user_id: The user's ID.

        Returns:
            IntegrationPreferences instance with defaults if not set.
        """
        result = (
            self._db.table("user_settings")
            .select("integrations")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result and result.data and result.data.get("integrations"):
            integrations = result.data["integrations"]
            return IntegrationPreferences(
                slack_channels=integrations.get("slack_channels", []),
                notification_enabled=integrations.get("notification_enabled", True),
                sync_frequency_hours=integrations.get("sync_frequency_hours", 1),
            )

        return IntegrationPreferences()

    def _get_base_url(self) -> str:
        """Get the base URL for OAuth redirects.

        In production, this comes from environment config.
        For local development, defaults to localhost.
        """
        from src.core.config import settings

        # Use first CORS origin as the redirect base
        origins = settings.cors_origins_list
        return origins[0] if origins else "http://localhost:5173"
