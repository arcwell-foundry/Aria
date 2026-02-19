"""CapabilityStore — CRUD for the ``installed_capabilities`` table.

Mirrors the ``SkillInstaller`` pattern from ``backend/src/skills/installer.py``:
install, uninstall, list, record_usage, update_health, and stale detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.mcp_servers.models import InstalledCapability

logger = logging.getLogger(__name__)

_TABLE = "installed_capabilities"


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO timestamp string to a datetime, or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _row_to_capability(row: dict[str, Any]) -> InstalledCapability:
    """Convert a database row dict to an ``InstalledCapability``."""
    return InstalledCapability(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        server_name=str(row["server_name"]),
        server_display_name=row.get("server_display_name", ""),
        registry_source=row.get("registry_source", "unknown"),
        registry_package_id=row.get("registry_package_id", ""),
        transport=row.get("transport", "stdio"),
        connection_config=row.get("connection_config") or {},
        declared_tools=row.get("declared_tools") or [],
        declared_permissions=row.get("declared_permissions") or {},
        security_assessment=row.get("security_assessment") or {},
        reliability_score=float(row.get("reliability_score", 0.5)),
        total_calls=int(row.get("total_calls", 0)),
        successful_calls=int(row.get("successful_calls", 0)),
        failed_calls=int(row.get("failed_calls", 0)),
        last_used_at=_parse_dt(row.get("last_used_at")),
        last_health_check_at=_parse_dt(row.get("last_health_check_at")),
        health_status=row.get("health_status", "unknown"),
        is_enabled=bool(row.get("is_enabled", True)),
        installed_at=_parse_dt(row.get("installed_at")),
        created_at=_parse_dt(row.get("created_at")),
        updated_at=_parse_dt(row.get("updated_at")),
    )


class CapabilityStore:
    """CRUD operations for installed MCP capabilities."""

    def __init__(self) -> None:
        self._client = SupabaseClient.get_client()

    async def install(
        self,
        user_id: str,
        server_name: str,
        *,
        server_display_name: str = "",
        registry_source: str = "unknown",
        registry_package_id: str = "",
        transport: str = "stdio",
        connection_config: dict[str, Any] | None = None,
        declared_tools: list[dict[str, Any]] | None = None,
        declared_permissions: dict[str, Any] | None = None,
        security_assessment: dict[str, Any] | None = None,
    ) -> InstalledCapability:
        """Install an external MCP server for a user.

        If a record with the same (user_id, server_name) already exists,
        returns the existing record without modification.

        Args:
            user_id: The user's UUID.
            server_name: Unique server identifier (e.g. ``"mcp-server-slack"``).
            server_display_name: Human-readable display name.
            registry_source: Registry origin (smithery, npm, mcp_run, manual).
            registry_package_id: Package identifier within the registry.
            transport: Connection transport (stdio or sse).
            connection_config: JSONB config for establishing the connection.
            declared_tools: List of tool metadata dicts.
            declared_permissions: Permission requirements dict.
            security_assessment: Security evaluation result dict.

        Returns:
            The installed capability record.
        """
        # Check for existing installation
        existing = await self.get_by_server_name(user_id, server_name)
        if existing is not None:
            logger.info(
                "Capability %s already installed for user %s", server_name, user_id
            )
            return existing

        now = datetime.now()
        record = {
            "user_id": user_id,
            "server_name": server_name,
            "server_display_name": server_display_name,
            "registry_source": registry_source,
            "registry_package_id": registry_package_id,
            "transport": transport,
            "connection_config": connection_config or {},
            "declared_tools": declared_tools or [],
            "declared_permissions": declared_permissions or {},
            "security_assessment": security_assessment or {},
            "installed_at": now.isoformat(),
        }

        try:
            response = self._client.table(_TABLE).insert(record).execute()
            if response.data:
                cap = _row_to_capability(response.data[0])
                logger.info(
                    "Installed capability %s for user %s (transport=%s)",
                    server_name,
                    user_id,
                    transport,
                )
                return cap
            raise Exception("No data returned from insert")
        except Exception:
            logger.exception(
                "Failed to install capability %s for user %s", server_name, user_id
            )
            raise

    async def uninstall(self, user_id: str, server_name: str) -> bool:
        """Remove an installed capability.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier to remove.

        Returns:
            True if a record was deleted, False if none existed.
        """
        try:
            response = (
                self._client.table(_TABLE)
                .delete()
                .eq("user_id", user_id)
                .eq("server_name", server_name)
                .execute()
            )
            deleted = bool(response.data)
            if deleted:
                logger.info("Uninstalled capability %s for user %s", server_name, user_id)
            return deleted
        except Exception:
            logger.exception(
                "Error uninstalling capability %s for user %s", server_name, user_id
            )
            return False

    async def get_by_server_name(
        self, user_id: str, server_name: str
    ) -> InstalledCapability | None:
        """Get a specific installed capability by server name.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier.

        Returns:
            The capability if found, None otherwise.
        """
        try:
            response = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .eq("server_name", server_name)
                .single()
                .execute()
            )
            if response.data:
                return _row_to_capability(response.data)
            return None
        except Exception:
            logger.debug(
                "Capability %s not found for user %s", server_name, user_id
            )
            return None

    async def list_user_capabilities(
        self, user_id: str, *, enabled_only: bool = False
    ) -> list[InstalledCapability]:
        """List all installed capabilities for a user.

        Args:
            user_id: The user's UUID.
            enabled_only: If True, only return enabled capabilities.

        Returns:
            List of installed capabilities, ordered by install date descending.
        """
        try:
            query = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
            )
            if enabled_only:
                query = query.eq("is_enabled", True)
            query = query.order("installed_at", desc=True)
            response = query.execute()
            return [_row_to_capability(row) for row in (response.data or [])]
        except Exception:
            logger.exception("Error listing capabilities for user %s", user_id)
            return []

    async def record_usage(
        self, user_id: str, server_name: str, *, success: bool = True
    ) -> InstalledCapability | None:
        """Record a tool call against an installed capability.

        Increments total_calls and either successful_calls or failed_calls,
        and updates last_used_at and reliability_score.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier.
            success: Whether the tool call succeeded.

        Returns:
            The updated capability record, or None if not found.
        """
        cap = await self.get_by_server_name(user_id, server_name)
        if cap is None:
            logger.warning(
                "Cannot record usage: capability %s not found for user %s",
                server_name,
                user_id,
            )
            return None

        new_total = cap.total_calls + 1
        new_success = cap.successful_calls + (1 if success else 0)
        new_failed = cap.failed_calls + (0 if success else 1)
        new_reliability = new_success / new_total if new_total > 0 else 0.5

        now = datetime.now()
        update_data = {
            "total_calls": new_total,
            "successful_calls": new_success,
            "failed_calls": new_failed,
            "reliability_score": round(new_reliability, 4),
            "last_used_at": now.isoformat(),
        }

        try:
            response = (
                self._client.table(_TABLE)
                .update(update_data)
                .eq("user_id", user_id)
                .eq("server_name", server_name)
                .execute()
            )
            if response.data:
                return _row_to_capability(response.data[0])
            return None
        except Exception:
            logger.exception(
                "Error recording usage for %s (user %s)", server_name, user_id
            )
            return None

    async def update_health(
        self, user_id: str, server_name: str, health_status: str
    ) -> InstalledCapability | None:
        """Update the health status of an installed capability.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier.
            health_status: New status (healthy, degraded, unhealthy).

        Returns:
            The updated capability record, or None if not found.
        """
        now = datetime.now()
        update_data = {
            "health_status": health_status,
            "last_health_check_at": now.isoformat(),
        }

        try:
            response = (
                self._client.table(_TABLE)
                .update(update_data)
                .eq("user_id", user_id)
                .eq("server_name", server_name)
                .execute()
            )
            if response.data:
                return _row_to_capability(response.data[0])
            return None
        except Exception:
            logger.exception(
                "Error updating health for %s (user %s)", server_name, user_id
            )
            return None

    async def set_enabled(
        self, user_id: str, server_name: str, enabled: bool
    ) -> InstalledCapability | None:
        """Enable or disable an installed capability.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier.
            enabled: Whether the capability should be enabled.

        Returns:
            The updated capability record, or None if not found.
        """
        try:
            response = (
                self._client.table(_TABLE)
                .update({"is_enabled": enabled})
                .eq("user_id", user_id)
                .eq("server_name", server_name)
                .execute()
            )
            if response.data:
                return _row_to_capability(response.data[0])
            return None
        except Exception:
            logger.exception(
                "Error setting enabled=%s for %s (user %s)",
                enabled,
                server_name,
                user_id,
            )
            return None

    async def get_unused_capabilities(
        self, user_id: str, days_unused: int = 30
    ) -> list[InstalledCapability]:
        """Find capabilities that haven't been used in the specified period.

        Args:
            user_id: The user's UUID.
            days_unused: Number of days without usage to consider stale.

        Returns:
            List of unused capabilities.
        """
        cutoff = (datetime.now() - timedelta(days=days_unused)).isoformat()
        try:
            # Capabilities where last_used_at is null or before cutoff
            response = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .eq("is_enabled", True)
                .or_(f"last_used_at.is.null,last_used_at.lt.{cutoff}")
                .execute()
            )
            return [_row_to_capability(row) for row in (response.data or [])]
        except Exception:
            logger.exception(
                "Error finding unused capabilities for user %s", user_id
            )
            return []
