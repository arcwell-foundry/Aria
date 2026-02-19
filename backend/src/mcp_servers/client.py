"""MCPToolClient — unified interface for agents to call MCP tools.

Handles:
1. Tool → server routing via ``resolve_tool()`` (built-in + external)
2. Client-side DCT fail-fast (before calling the server)
3. DelegationTrace lifecycle (start → complete/fail)
4. In-process server invocation for built-in tools
5. External tool routing through ``ExternalConnectionPool``
6. ``CapabilityGapEvent`` emission when tools are not found
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.capability_tokens import DelegationCapabilityToken
from src.mcp_servers.middleware import DCTViolation
from src.mcp_servers.models import CapabilityGapEvent
from src.mcp_servers.registry import TOOL_SERVER_MAP, get_server, resolve_tool

logger = logging.getLogger(__name__)


class MCPToolClient:
    """Client for agents to invoke MCP tools with DCT enforcement and tracing.

    Usage::

        client = MCPToolClient(user_id="u-123", delegation_trace_service=trace_svc)
        result = await client.call_tool(
            "pubmed_search",
            {"query": "CRISPR"},
            dct=my_dct,
            delegatee="analyst",
        )
    """

    def __init__(
        self,
        user_id: str,
        delegation_trace_service: Any | None = None,
    ) -> None:
        """Initialize the MCP tool client.

        Args:
            user_id: ID of the user on whose behalf tools are called.
            delegation_trace_service: Optional ``DelegationTraceService``
                instance for audit logging.
        """
        self._user_id = user_id
        self._trace_service = delegation_trace_service

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dct: DelegationCapabilityToken | None = None,
        goal_id: str | None = None,
        parent_trace_id: str | None = None,
        delegator: str = "orchestrator",
        delegatee: str = "unknown",
    ) -> dict[str, Any]:
        """Call an MCP tool by name with DCT enforcement and tracing.

        Resolves tools from built-in servers first, then user's external
        servers.  If the tool is not found anywhere, emits a
        ``CapabilityGapEvent`` before raising.

        Args:
            tool_name: Registered MCP tool name (e.g. ``"pubmed_search"``).
            arguments: Tool arguments dict.
            dct: Optional capability token for permission enforcement.
            goal_id: Optional goal ID for trace linkage.
            parent_trace_id: Optional parent trace ID for tree building.
            delegator: Name of the delegating entity.
            delegatee: Name of the agent calling the tool.

        Returns:
            Tool result dict.

        Raises:
            ValueError: If *tool_name* is not found in any tool map.
            DCTViolation: If the DCT denies the action (client-side fail-fast).
        """
        # 1. Resolve tool → server (built-in first, then external)
        try:
            server_name, dct_action, is_external = resolve_tool(
                tool_name, self._user_id
            )
        except KeyError:
            self._emit_gap_event(tool_name, delegatee)
            raise ValueError(
                f"Unknown MCP tool: '{tool_name}'. "
                f"Known tools: {sorted(TOOL_SERVER_MAP)}"
            )

        # 2. Client-side DCT fail-fast
        if dct is not None:
            if not dct.is_valid():
                raise DCTViolation(tool_name, dct.delegatee, dct_action)
            if not dct.can_perform(dct_action):
                raise DCTViolation(tool_name, dct.delegatee, dct_action)

        # 3. Start delegation trace (non-blocking — failure here should not
        #    prevent the tool call from executing)
        trace_id: str | None = None
        if self._trace_service is not None:
            try:
                trace_id = await self._trace_service.start_trace(
                    user_id=self._user_id,
                    goal_id=goal_id,
                    parent_trace_id=parent_trace_id,
                    delegator=delegator,
                    delegatee=delegatee,
                    task_description=f"MCP tool call: {tool_name}"
                    + (" (external)" if is_external else ""),
                    capability_token=dct.to_dict() if dct else None,
                    inputs={"tool_name": tool_name, "arguments": arguments},
                )
            except Exception:
                logger.warning(
                    "Failed to start delegation trace for %s",
                    tool_name,
                    exc_info=True,
                )

        # 4. Route to the appropriate handler
        try:
            if is_external:
                result = await self._call_external_tool(
                    server_name, tool_name, arguments, dct_action=dct_action, dct=dct
                )
            else:
                result = await self._call_builtin_tool(
                    server_name, tool_name, arguments, dct=dct
                )

            # 5a. Complete trace on success
            if trace_id and self._trace_service:
                try:
                    await self._trace_service.complete_trace(
                        trace_id=trace_id,
                        outputs=result if isinstance(result, dict) else {"result": str(result)},
                        status="completed",
                    )
                except Exception:
                    logger.warning(
                        "Failed to complete trace %s for %s",
                        trace_id,
                        tool_name,
                        exc_info=True,
                    )

            return result if isinstance(result, dict) else {"result": result}

        except DCTViolation:
            # Re-raise DCT violations so the caller sees them
            if trace_id and self._trace_service:
                try:
                    await self._trace_service.fail_trace(
                        trace_id=trace_id,
                        error_message=f"DCT violation on {tool_name}",
                    )
                except Exception:
                    pass
            raise

        except Exception as exc:
            # 5b. Fail trace on error
            if trace_id and self._trace_service:
                try:
                    await self._trace_service.fail_trace(
                        trace_id=trace_id,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.warning(
                        "Failed to record trace failure %s for %s",
                        trace_id,
                        tool_name,
                        exc_info=True,
                    )
            raise

    async def _call_builtin_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dct: DelegationCapabilityToken | None = None,
    ) -> dict[str, Any]:
        """Call a built-in (in-process) MCP server tool.

        Args:
            server_name: Name of the built-in server.
            tool_name: Tool to invoke.
            arguments: Tool arguments.
            dct: Optional DCT for server-side enforcement.

        Returns:
            Tool result dict.
        """
        server = get_server(server_name)
        call_args = dict(arguments)
        if dct is not None:
            call_args["dct"] = dct.to_dict()
        result = await server.call_tool(tool_name, call_args)
        return result if isinstance(result, dict) else {"result": result}

    async def _call_external_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dct_action: str = "",
        dct: DelegationCapabilityToken | None = None,
    ) -> dict[str, Any]:
        """Route a tool call through the external connection pool.

        Args:
            server_name: External server identifier.
            tool_name: Tool to invoke.
            arguments: Tool arguments.
            dct_action: DCT action string for enforcement.
            dct: Optional DCT for permission enforcement.

        Returns:
            Tool result dict.
        """
        from src.mcp_servers.connection_pool import ExternalConnectionPool

        pool = ExternalConnectionPool.instance()
        conn = await pool.get_connection(self._user_id, server_name)
        return await conn.call_tool(
            tool_name,
            arguments,
            dct_dict=dct.to_dict() if dct else None,
            dct_action=dct_action,
        )

    def _emit_gap_event(self, tool_name: str, requesting_agent: str) -> None:
        """Emit a CapabilityGapEvent when a tool is not found.

        The event is logged for the OODA loop to pick up asynchronously.

        Args:
            tool_name: The tool that was requested but not found.
            requesting_agent: The agent that made the request.
        """
        event = CapabilityGapEvent(
            user_id=self._user_id,
            requested_tool=tool_name,
            requesting_agent=requesting_agent,
            timestamp=datetime.now(UTC).isoformat(),
        )
        logger.info(
            "Capability gap detected: tool='%s' requested_by='%s' user='%s'",
            tool_name,
            requesting_agent,
            self._user_id,
        )

    async def list_tools(
        self,
        server_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List available MCP tools, optionally filtered by server.

        Args:
            server_name: If provided, only return tools from this server.

        Returns:
            List of dicts with ``name``, ``server``, and ``dct_action`` keys.
        """
        tools: list[dict[str, Any]] = []
        for name, (srv, action) in TOOL_SERVER_MAP.items():
            if server_name is not None and srv != server_name:
                continue
            tools.append({
                "name": name,
                "server": srv,
                "dct_action": action,
            })
        return tools
