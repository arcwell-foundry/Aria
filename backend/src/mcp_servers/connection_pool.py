"""ExternalConnectionPool — manages per-user external MCP server connections.

Singleton pool that lazily connects to external servers on first use
and provides cleanup hooks for logout/shutdown.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings
from src.mcp_servers.external_connection import ExternalMCPConnection

logger = logging.getLogger(__name__)


class ExternalConnectionPool:
    """Manages per-user pools of external MCP server connections.

    Connections are lazy-initialized on first ``get_connection()`` call.
    The pool enforces ``MCP_EXTERNAL_MAX_PER_USER`` limit per user.

    Usage::

        pool = ExternalConnectionPool.instance()
        conn = await pool.get_connection(user_id, server_name, transport, config)
        result = await conn.call_tool("tool_name", {"arg": "value"})

        # On user logout
        await pool.close_user_connections(user_id)

        # On shutdown
        await pool.close_all()
    """

    _instance: ExternalConnectionPool | None = None

    def __init__(self) -> None:
        # user_id → (server_name → ExternalMCPConnection)
        self._pools: dict[str, dict[str, ExternalMCPConnection]] = {}

    @classmethod
    def instance(cls) -> ExternalConnectionPool:
        """Get or create the singleton pool instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    async def get_connection(
        self,
        user_id: str,
        server_name: str,
        transport: str = "stdio",
        connection_config: dict[str, Any] | None = None,
        declared_tools: list[dict[str, Any]] | None = None,
    ) -> ExternalMCPConnection:
        """Get or create a connection for a user's external MCP server.

        Lazily connects on first use. If the connection already exists
        and is connected, returns it directly.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier.
            transport: Connection transport (stdio or sse).
            connection_config: Transport-specific configuration.
            declared_tools: Expected tool metadata.

        Returns:
            An active ExternalMCPConnection.

        Raises:
            ConnectionError: If the connection cannot be established.
            ValueError: If user has reached the max server limit.
        """
        # Ensure user pool exists
        if user_id not in self._pools:
            self._pools[user_id] = {}

        user_pool = self._pools[user_id]

        # Return existing connection if healthy
        if server_name in user_pool:
            conn = user_pool[server_name]
            if conn.is_connected:
                return conn
            # Connection died — remove and recreate
            del user_pool[server_name]

        # Check per-user limit
        max_per_user = settings.MCP_EXTERNAL_MAX_PER_USER
        if len(user_pool) >= max_per_user:
            raise ValueError(
                f"User {user_id} has reached the maximum of "
                f"{max_per_user} external MCP servers"
            )

        # Create and connect
        conn = ExternalMCPConnection(
            server_name=server_name,
            transport=transport,
            connection_config=connection_config,
            declared_tools=declared_tools,
        )
        await conn.connect()
        user_pool[server_name] = conn

        logger.info(
            "Pool: created connection for user %s → %s (%s)",
            user_id,
            server_name,
            transport,
        )
        return conn

    async def close_connection(self, user_id: str, server_name: str) -> None:
        """Close a specific user's server connection.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier to disconnect.
        """
        user_pool = self._pools.get(user_id, {})
        conn = user_pool.pop(server_name, None)
        if conn is not None:
            await conn.disconnect()
            logger.info(
                "Pool: closed connection for user %s → %s", user_id, server_name
            )

    async def close_user_connections(self, user_id: str) -> None:
        """Close all connections for a user (e.g. on logout).

        Args:
            user_id: The user's UUID.
        """
        user_pool = self._pools.pop(user_id, {})
        for server_name, conn in user_pool.items():
            try:
                await conn.disconnect()
            except Exception:
                logger.warning(
                    "Error closing connection %s for user %s",
                    server_name,
                    user_id,
                    exc_info=True,
                )
        if user_pool:
            logger.info(
                "Pool: closed %d connections for user %s",
                len(user_pool),
                user_id,
            )

    async def close_all(self) -> None:
        """Close all connections for all users (shutdown hook)."""
        total = 0
        for user_id in list(self._pools.keys()):
            user_pool = self._pools.pop(user_id, {})
            for server_name, conn in user_pool.items():
                try:
                    await conn.disconnect()
                    total += 1
                except Exception:
                    logger.warning(
                        "Error closing connection %s for user %s",
                        server_name,
                        user_id,
                        exc_info=True,
                    )
        if total:
            logger.info("Pool: closed %d total connections on shutdown", total)

    async def health_check_all(self, user_id: str) -> dict[str, str]:
        """Run health checks on all of a user's connections.

        Args:
            user_id: The user's UUID.

        Returns:
            Dict mapping server_name to health status string.
        """
        user_pool = self._pools.get(user_id, {})
        results: dict[str, str] = {}
        for server_name, conn in user_pool.items():
            try:
                status = await conn.health_check()
                results[server_name] = status
            except Exception:
                results[server_name] = "unhealthy"
        return results

    def get_connected_servers(self, user_id: str) -> list[str]:
        """List server names with active connections for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            List of connected server names.
        """
        user_pool = self._pools.get(user_id, {})
        return [name for name, conn in user_pool.items() if conn.is_connected]
