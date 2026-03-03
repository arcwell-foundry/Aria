"""Connection Registry — canonical store for OAuth connection state.

Provides a TTL-cached, audit-logged service for managing user_connections rows.
Dual-writes to user_integrations via IntegrationService for backward compatibility.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from cachetools import TTLCache

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Cache settings
_CACHE_TTL = 120  # seconds
_CACHE_MAX = 512

# Failure threshold: if failure_count exceeds this, status → 'error'
_FAILURE_THRESHOLD = 3


class ConnectionRegistryService:
    """Manage user_connections with caching and audit logging.

    All public methods are async for FastAPI compatibility.
    """

    def __init__(self) -> None:
        # Cache key = f"{user_id}:{toolkit_slug}" → dict row
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=_CACHE_MAX, ttl=_CACHE_TTL
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_connection(
        self, user_id: str, toolkit_slug: str
    ) -> dict[str, Any] | None:
        """Get a single connection, cache-first.

        Args:
            user_id: The user's ID.
            toolkit_slug: The toolkit slug (e.g. 'gmail').

        Returns:
            Connection dict or None if not found / not active.
        """
        cache_key = f"{user_id}:{toolkit_slug}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("user_connections")
                .select("*")
                .eq("user_id", user_id)
                .eq("toolkit_slug", toolkit_slug)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            row = result.data[0] if result and result.data else None
            if row is None:
                return None

            row = cast(dict[str, Any], row)
            self._cache[cache_key] = row
            return row

        except Exception:
            logger.exception("Failed to fetch connection")
            return None

    async def get_all_connections(self, user_id: str) -> list[dict[str, Any]]:
        """Get all active connections for a user.

        Args:
            user_id: The user's ID.

        Returns:
            List of active connection dicts.
        """
        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("user_connections")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            return cast(list[dict[str, Any]], result.data) if result.data else []
        except Exception:
            logger.exception("Failed to fetch all connections")
            return []

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def register_connection(
        self,
        user_id: str,
        toolkit_slug: str,
        composio_connection_id: str | None = None,
        composio_entity_id: str | None = None,
        account_email: str | None = None,
        display_name: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update a connection in user_connections.

        Also dual-writes to user_integrations via IntegrationService.

        Args:
            user_id: The user's ID.
            toolkit_slug: The toolkit slug (e.g. 'gmail').
            composio_connection_id: Composio connection nanoid.
            composio_entity_id: Composio entity ID.
            account_email: The account email address.
            display_name: Human-readable name.
            status: Connection status (default 'active').
            metadata: Extra metadata dict.

        Returns:
            The upserted connection row.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "toolkit_slug": toolkit_slug,
                "status": status,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if composio_connection_id is not None:
                data["composio_connection_id"] = composio_connection_id
            if composio_entity_id is not None:
                data["composio_entity_id"] = composio_entity_id
            if account_email is not None:
                data["account_email"] = account_email
            if display_name is not None:
                data["display_name"] = display_name
            if metadata is not None:
                data["metadata"] = metadata
            if status == "active":
                data["failure_count"] = 0

            response = (
                client.table("user_connections")
                .upsert(data, on_conflict="user_id,toolkit_slug")
                .execute()
            )

            row = cast(dict[str, Any], response.data[0]) if response.data else data

            # Invalidate cache
            self._invalidate(user_id, toolkit_slug)

            # Audit log
            await self._audit(
                user_id=user_id,
                action="register",
                toolkit_slug=toolkit_slug,
                connection_id=row.get("id"),
                detail={
                    "status": status,
                    "composio_connection_id": composio_connection_id,
                    "account_email": account_email,
                },
            )

            # Dual-write to user_integrations (non-fatal)
            if status == "active":
                await self._dual_write_integration(
                    user_id=user_id,
                    toolkit_slug=toolkit_slug,
                    composio_connection_id=composio_connection_id or "",
                    account_email=account_email,
                    display_name=display_name,
                )

            return row

        except Exception:
            logger.exception("Failed to register connection")
            raise

    async def disconnect(self, user_id: str, toolkit_slug: str) -> None:
        """Mark a connection as disconnected.

        Args:
            user_id: The user's ID.
            toolkit_slug: The toolkit slug.
        """
        try:
            client = SupabaseClient.get_client()
            client.table("user_connections").update(
                {"status": "disconnected", "updated_at": datetime.now(UTC).isoformat()}
            ).eq("user_id", user_id).eq("toolkit_slug", toolkit_slug).execute()

            self._invalidate(user_id, toolkit_slug)

            await self._audit(
                user_id=user_id,
                action="disconnect",
                toolkit_slug=toolkit_slug,
                detail={"status": "disconnected"},
            )

        except Exception:
            logger.exception("Failed to disconnect connection")
            raise

    async def record_failure(self, user_id: str, toolkit_slug: str) -> int:
        """Increment failure_count via RPC. Auto-error if threshold exceeded.

        Args:
            user_id: The user's ID.
            toolkit_slug: The toolkit slug.

        Returns:
            The new failure_count.
        """
        try:
            client = SupabaseClient.get_client()
            result = client.rpc(
                "increment_connection_failure_count",
                {"p_user_id": user_id, "p_toolkit_slug": toolkit_slug},
            ).execute()

            new_count = result.data if isinstance(result.data, int) else 0

            if new_count > _FAILURE_THRESHOLD:
                client.table("user_connections").update(
                    {"status": "error", "updated_at": datetime.now(UTC).isoformat()}
                ).eq("user_id", user_id).eq("toolkit_slug", toolkit_slug).execute()

                await self._audit(
                    user_id=user_id,
                    action="auto_error",
                    toolkit_slug=toolkit_slug,
                    detail={"failure_count": new_count, "threshold": _FAILURE_THRESHOLD},
                )

            self._invalidate(user_id, toolkit_slug)
            return new_count

        except Exception:
            logger.exception("Failed to record failure")
            return 0

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def get_recently_added_connections(
        self, user_id: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Get connections activated within the last *hours*.

        Used by OODA Orient to detect tools connected since a goal was planned.

        Args:
            user_id: The user's ID.
            hours: Look-back window in hours (default 24).

        Returns:
            List of recently activated connection dicts.
        """
        try:
            client = SupabaseClient.get_client()
            cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
            result = (
                client.table("user_connections")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "active")
                .gte("updated_at", cutoff)
                .execute()
            )
            return cast(list[dict[str, Any]], result.data) if result.data else []
        except Exception:
            logger.exception("Failed to fetch recently added connections")
            return []

    async def mark_connection_expired(
        self, user_id: str, toolkit_slug: str
    ) -> None:
        """Mark a connection as expired (e.g. token revoked or health check failed).

        Args:
            user_id: The user's ID.
            toolkit_slug: The toolkit slug.
        """
        try:
            client = SupabaseClient.get_client()
            client.table("user_connections").update(
                {"status": "expired", "updated_at": datetime.now(UTC).isoformat()}
            ).eq("user_id", user_id).eq("toolkit_slug", toolkit_slug).execute()

            self._invalidate(user_id, toolkit_slug)

            await self._audit(
                user_id=user_id,
                action="mark_expired",
                toolkit_slug=toolkit_slug,
                detail={"status": "expired", "reason": "health_check_failure"},
            )
        except Exception:
            logger.exception("Failed to mark connection as expired")
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _audit(
        self,
        user_id: str,
        action: str,
        toolkit_slug: str,
        connection_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Insert a row into tool_router_audit_log."""
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "action": action,
                "toolkit_slug": toolkit_slug,
                "detail": detail or {},
            }
            if connection_id:
                data["connection_id"] = connection_id
            client.table("tool_router_audit_log").insert(data).execute()
        except Exception:
            logger.warning("Audit log write failed (non-fatal)", exc_info=True)

    async def _dual_write_integration(
        self,
        user_id: str,
        toolkit_slug: str,
        composio_connection_id: str,
        account_email: str | None,
        display_name: str | None,
    ) -> None:
        """Write to user_integrations via IntegrationService for backward compat."""
        try:
            from src.integrations.domain import IntegrationType
            from src.integrations.service import get_integration_service

            # Map toolkit_slug to IntegrationType
            integration_type = IntegrationType(toolkit_slug)
            service = get_integration_service()

            # Check if integration already exists
            existing = await service.get_integration(user_id, integration_type)
            if existing:
                logger.debug(
                    "Dual-write skipped: integration already exists for %s/%s",
                    user_id,
                    toolkit_slug,
                )
                return

            await service.create_integration(
                user_id=user_id,
                integration_type=integration_type,
                composio_connection_id=composio_connection_id,
                display_name=display_name,
                account_email=account_email,
            )
            logger.info(
                "Dual-write to user_integrations succeeded for %s/%s",
                user_id,
                toolkit_slug,
            )
        except Exception:
            logger.warning("Registry dual-write to user_integrations failed (non-fatal)", exc_info=True)

    def _invalidate(self, user_id: str, toolkit_slug: str) -> None:
        """Remove a cache entry."""
        cache_key = f"{user_id}:{toolkit_slug}"
        self._cache.pop(cache_key, None)

    async def lookup_by_composio_connection_id(
        self, composio_connection_id: str
    ) -> dict[str, Any] | None:
        """Look up a connection by its Composio connection ID.

        Used by webhook handlers and the OAuth callback to find the user.

        Args:
            composio_connection_id: The Composio connection nanoid.

        Returns:
            Connection dict or None.
        """
        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("user_connections")
                .select("*")
                .eq("composio_connection_id", composio_connection_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return cast(dict[str, Any], result.data[0])
            return None
        except Exception:
            logger.exception("Failed to look up connection by composio_connection_id")
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ConnectionRegistryService | None = None


def get_connection_registry() -> ConnectionRegistryService:
    """Get the singleton ConnectionRegistryService instance."""
    global _registry
    if _registry is None:
        _registry = ConnectionRegistryService()
    return _registry
