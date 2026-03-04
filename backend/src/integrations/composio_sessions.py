"""Composio Tool Router session manager.

Wraps Composio's ``ToolRouter.create()`` API to provide session-scoped,
auto-refreshing token management.  Sessions are cached per user with a 30-minute
TTL so we avoid redundant API round-trips while keeping tokens fresh.

This module sits alongside the existing ``oauth.py`` + ``composio_client.py``
stack — it does **not** replace them.  Phase 1 adds the foundation; later
phases will migrate callers to use sessions for tool execution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache
from composio import Composio

from src.core.config import settings
from src.core.resilience import composio_circuit_breaker

if TYPE_CHECKING:
    from composio.core.models.tool_router import ToolRouterSession

logger = logging.getLogger(__name__)

# Session TTL in seconds (30 minutes).
_SESSION_TTL = 30 * 60

# Maximum number of cached sessions.
_SESSION_CACHE_SIZE = 256


class ComposioSessionManager:
    """Manage Composio Tool Router sessions with per-user caching.

    All Composio SDK calls are synchronous — we wrap them with
    ``asyncio.to_thread()`` for FastAPI compatibility, matching the
    pattern used in ``oauth.py``.
    """

    def __init__(self) -> None:
        self._composio: Composio | None = None
        # Values are ToolRouterSession instances (typed as Any to avoid
        # runtime dependency on composio.core.models.tool_router).
        self._sessions: TTLCache[str, Any] = TTLCache(
            maxsize=_SESSION_CACHE_SIZE,
            ttl=_SESSION_TTL,
        )

    @property
    def _client(self) -> Composio:
        """Lazy-initialised Composio SDK client (singleton)."""
        if self._composio is None:
            api_key = (
                settings.COMPOSIO_API_KEY.get_secret_value()
                if settings.COMPOSIO_API_KEY is not None
                else ""
            )
            self._composio = Composio(api_key=api_key)
        return self._composio

    @staticmethod
    def _entity_id(user_id: str) -> str:
        """Build a Composio entity ID scoped to an ARIA user.

        Uses the first 12 characters of the UUID to keep entity IDs
        reasonably short while avoiding collisions.
        """
        prefix = user_id.replace("-", "")[:12]
        return f"aria_user_{prefix}"

    async def get_session(
        self,
        user_id: str,
        *,
        toolkits: list[str] | None = None,
        connected_accounts: dict[str, str] | None = None,
    ) -> ToolRouterSession:
        """Get or create a cached Tool Router session for a user.

        Args:
            user_id: The ARIA user ID.
            toolkits: Optional list of toolkit slugs to enable
                (e.g. ``['outlook', 'gmail', 'salesforce']``).
            connected_accounts: Optional mapping of toolkit slug to
                connected account ID for pre-authenticated sessions.

        Returns:
            A ``ToolRouterSession`` with ``tools()``, ``authorize()``,
            ``toolkits()``, and ``mcp`` available.
        """
        cache_key = user_id
        cached = self._sessions.get(cache_key)
        if cached is not None:
            return cached

        # If no connected_accounts provided, try loading from ConnectionRegistry
        if connected_accounts is None:
            try:
                from src.integrations.connection_registry import get_connection_registry

                registry = get_connection_registry()
                connections = await registry.get_all_connections(user_id)
                if connections:
                    connected_accounts = {
                        c["toolkit_slug"]: c["composio_connection_id"]
                        for c in connections
                        if c.get("composio_connection_id")
                    }
            except Exception:
                logger.debug("Registry lookup for session failed (non-fatal)", exc_info=True)

        composio_circuit_breaker.check()

        entity_id = self._entity_id(user_id)

        def _create() -> ToolRouterSession:
            kwargs: dict[str, Any] = {
                "user_id": entity_id,
            }
            if toolkits is not None:
                kwargs["toolkits"] = toolkits
            if connected_accounts is not None:
                kwargs["connected_accounts"] = connected_accounts
            return self._client.create(**kwargs)

        try:
            session = await asyncio.wait_for(
                asyncio.to_thread(_create),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            composio_circuit_breaker.record_failure()
            logger.error("Composio session creation timed out after 30s for user %s", user_id)
            raise
        except Exception:
            composio_circuit_breaker.record_failure()
            raise

        composio_circuit_breaker.record_success()
        self._sessions[cache_key] = session

        logger.info(
            "Composio session created",
            extra={
                "user_id": user_id,
                "entity_id": entity_id,
                "session_id": session.session_id,
            },
        )
        return session

    async def get_tools(
        self,
        user_id: str,
        *,
        toolkits: list[str] | None = None,
        connected_accounts: dict[str, str] | None = None,
    ) -> Any:
        """Return provider-wrapped tool definitions for Claude function calling.

        Args:
            user_id: The ARIA user ID.
            toolkits: Optional toolkit filter.
            connected_accounts: Optional pre-authenticated connections.

        Returns:
            Tool definitions in the format expected by the configured
            Composio provider (OpenAI format by default).
        """
        session = await self.get_session(
            user_id,
            toolkits=toolkits,
            connected_accounts=connected_accounts,
        )
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(session.tools),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Composio get_tools timed out after 30s for user %s", user_id)
            return []

    async def execute_action(
        self,
        user_id: str,
        action: str,
        params: dict[str, Any],
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a tool action through the session.

        The Tool Router session doesn't expose a direct ``execute()``
        method — tool execution flows through the provider-wrapped tools.
        This method provides a convenience wrapper that delegates to the
        existing ``oauth.py`` ``execute_action()`` while still gaining
        session-level benefits (connection management, tool discovery).

        Args:
            user_id: The ARIA user ID.
            action: The tool slug (e.g. ``'OUTLOOK_GET_MAIL_DELTA'``).
            params: Parameters for the action.
            connection_id: Optional Composio connection nanoid.  If
                provided, delegates directly to ``oauth.py``.

        Returns:
            Action result dict with ``successful``, ``data``, and
            ``error`` keys.
        """
        # Delegate to the existing oauth.py execution path which handles
        # tool versioning, schema preloading, and circuit-breaker logic.
        from src.integrations.oauth import get_oauth_client

        oauth = get_oauth_client()

        if connection_id is None:
            # Without a connection_id we can't execute — raise early.
            raise ValueError(
                "connection_id is required for action execution. "
                "Session-only execution is not yet supported."
            )

        # All Outlook actions have no registered version, skip version check
        skip_version = action.upper().startswith("OUTLOOK")
        return await oauth.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
            user_id=user_id,
            dangerously_skip_version_check=skip_version,
        )

    async def execute_meta_tool(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a Composio meta tool within a user's session.

        Meta tools are session-level operations (search, connect, execute)
        that don't require a ``connection_id`` — they route through the
        ``execute_meta`` HTTP endpoint instead of ``oauth.py``.

        Args:
            user_id: The ARIA user ID.
            tool_name: Meta tool slug (e.g. ``'COMPOSIO_SEARCH_TOOLS'``).
            arguments: Tool-specific parameters.

        Returns:
            Dict with ``data``, ``error``, and ``successful`` keys.
        """
        session = await self.get_session(user_id)

        composio_circuit_breaker.check()

        http_client = self._client.client  # HttpClient instance

        def _execute() -> dict[str, Any]:
            response = http_client.tool_router.session.execute_meta(
                session_id=session.session_id,
                slug=tool_name,
                arguments=arguments,
            )
            return {
                "data": response.data if hasattr(response, "data") else {},
                "error": response.error if hasattr(response, "error") else None,
                "successful": not (hasattr(response, "error") and response.error),
            }

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            composio_circuit_breaker.record_failure()
            logger.error(
                "Composio meta tool timed out after 30s",
                extra={"user_id": user_id, "tool_name": tool_name},
            )
            return {
                "data": None,
                "error": "Tool call timed out after 30 seconds",
                "timed_out": True,
                "successful": False,
            }
        except Exception:
            composio_circuit_breaker.record_failure()
            raise

        composio_circuit_breaker.record_success()
        logger.info(
            "Composio meta tool executed",
            extra={
                "user_id": user_id,
                "tool_name": tool_name,
                "session_id": session.session_id,
                "successful": result.get("successful"),
            },
        )
        return result

    async def close(self) -> None:
        """Clean up sessions and SDK client."""
        self._sessions.clear()
        self._composio = None
        logger.debug("Composio session manager closed")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_session_manager: ComposioSessionManager | None = None


def get_session_manager() -> ComposioSessionManager:
    """Get the singleton session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = ComposioSessionManager()
    return _session_manager
