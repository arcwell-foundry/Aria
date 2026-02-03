"""Service layer for managing user integrations."""

import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient
from src.integrations.domain import (
    INTEGRATION_CONFIGS,
    IntegrationStatus,
    IntegrationType,
    SyncStatus,
)
from src.integrations.oauth import get_oauth_client

logger = logging.getLogger(__name__)


class IntegrationService:
    """Service for managing user OAuth integrations."""

    async def get_user_integrations(self, user_id: str) -> list[dict[str, Any]]:
        """Get all integrations for a user.

        Args:
            user_id: The user's ID

        Returns:
            List of integration dictionaries

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations").select("*").eq("user_id", user_id).execute()
            )

            return response.data if response.data else []

        except Exception:
            logger.exception("Failed to fetch user integrations")
            raise

    async def get_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
    ) -> dict[str, Any] | None:
        """Get a specific integration for a user.

        Args:
            user_id: The user's ID
            integration_type: The integration type

        Returns:
            Integration dictionary or None if not found
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type.value)
                .maybe_single()
                .execute()
            )

            return response.data

        except Exception:
            logger.exception("Failed to fetch integration")
            return None

    async def create_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
        composio_connection_id: str,
        display_name: str | None = None,
        composio_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new integration connection.

        Args:
            user_id: The user's ID
            integration_type: Type of integration
            composio_connection_id: Composio connection ID
            display_name: Optional display name
            composio_account_id: Optional Composio account ID

        Returns:
            Created integration dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            data = {
                "user_id": user_id,
                "integration_type": integration_type.value,
                "composio_connection_id": composio_connection_id,
                "composio_account_id": composio_account_id,
                "display_name": display_name,
                "status": IntegrationStatus.ACTIVE.value,
                "sync_status": SyncStatus.SUCCESS.value,
            }

            response = client.table("user_integrations").insert(data).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]

            raise Exception("Failed to create integration")

        except Exception:
            logger.exception("Failed to create integration")
            raise

    async def update_integration(
        self,
        integration_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an integration.

        Args:
            integration_id: Integration record ID
            updates: Dictionary of fields to update

        Returns:
            Updated integration dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations").update(updates).eq("id", integration_id).execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0]

            raise Exception("Integration not found")

        except Exception:
            logger.exception("Failed to update integration")
            raise

    async def delete_integration(self, integration_id: str) -> bool:
        """Delete an integration.

        Args:
            integration_id: Integration record ID

        Returns:
            True if successful

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            client.table("user_integrations").delete().eq("id", integration_id).execute()
            return True

        except Exception:
            logger.exception("Failed to delete integration")
            raise

    async def update_sync_status(
        self,
        integration_id: str,
        status: SyncStatus,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update the sync status of an integration.

        Args:
            integration_id: Integration record ID
            status: New sync status
            error_message: Optional error message

        Returns:
            Updated integration dictionary
        """
        updates = {
            "sync_status": status.value,
            "last_sync_at": datetime.now(UTC).isoformat(),
        }

        if error_message:
            updates["error_message"] = error_message

        return await self.update_integration(integration_id, updates)

    async def disconnect_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
    ) -> bool:
        """Disconnect and remove an integration.

        Args:
            user_id: The user's ID
            integration_type: Integration type to disconnect

        Returns:
            True if successful

        Raises:
            Exception: If operation fails
        """
        try:
            # Get the integration
            integration = await self.get_integration(user_id, integration_type)
            if not integration:
                raise Exception("Integration not found")

            # Disconnect from Composio
            oauth_client = get_oauth_client()
            await oauth_client.disconnect_integration(
                user_id, integration["composio_connection_id"]
            )

            # Delete from database
            await self.delete_integration(integration["id"])

            logger.info(
                "Integration disconnected",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )

            return True

        except Exception:
            logger.exception("Failed to disconnect integration")
            raise

    async def get_available_integrations(self, user_id: str) -> list[dict[str, Any]]:
        """Get all available integrations with their connection status.

        Args:
            user_id: The user's ID

        Returns:
            List of available integrations with connection status
        """
        try:
            user_integrations = await self.get_user_integrations(user_id)
            connected_types = {i["integration_type"] for i in user_integrations}

            available = []
            for integration_type, config in INTEGRATION_CONFIGS.items():
                user_integration = next(
                    (
                        i
                        for i in user_integrations
                        if i["integration_type"] == integration_type.value
                    ),
                    None,
                )

                available.append(
                    {
                        "integration_type": integration_type.value,
                        "display_name": config.display_name,
                        "description": config.description,
                        "icon": config.icon,
                        "is_connected": integration_type.value in connected_types,
                        "status": user_integration.get("status") if user_integration else None,
                    }
                )

            return available

        except Exception:
            logger.exception("Failed to fetch available integrations")
            raise

    async def trigger_sync(self, integration_id: str) -> dict[str, Any]:
        """Trigger a manual sync for an integration.

        Args:
            integration_id: Integration record ID

        Returns:
            Updated integration with sync status

        Raises:
            Exception: If sync fails
        """
        try:
            # Update status to pending
            await self.update_sync_status(integration_id, SyncStatus.PENDING)

            # TODO: Implement actual sync logic per integration type
            # For now, mark as success
            integration = await self.update_sync_status(integration_id, SyncStatus.SUCCESS)

            return integration

        except Exception as e:
            logger.exception("Failed to trigger sync")
            await self.update_sync_status(
                integration_id,
                SyncStatus.FAILED,
                error_message=str(e),
            )
            raise


# Singleton instance
_integration_service: IntegrationService | None = None


def get_integration_service() -> IntegrationService:
    """Get or create integration service singleton.

    Returns:
        The shared IntegrationService instance
    """
    global _integration_service
    if _integration_service is None:
        _integration_service = IntegrationService()
    return _integration_service
