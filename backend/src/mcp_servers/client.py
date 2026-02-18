"""MCPToolClient — unified interface for agents to call MCP tools.

Handles:
1. Tool → server routing via ``TOOL_SERVER_MAP``
2. Client-side DCT fail-fast (before calling the server)
3. DelegationTrace lifecycle (start → complete/fail)
4. In-process server invocation (no HTTP round-trip)
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.capability_tokens import DelegationCapabilityToken
from src.mcp_servers.middleware import DCTViolation
from src.mcp_servers.registry import TOOL_SERVER_MAP, get_server

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
            ValueError: If *tool_name* is not in ``TOOL_SERVER_MAP``.
            DCTViolation: If the DCT denies the action (client-side fail-fast).
        """
        # 1. Resolve tool → server
        if tool_name not in TOOL_SERVER_MAP:
            raise ValueError(
                f"Unknown MCP tool: '{tool_name}'. "
                f"Known tools: {sorted(TOOL_SERVER_MAP)}"
            )

        server_name, dct_action = TOOL_SERVER_MAP[tool_name]

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
                    task_description=f"MCP tool call: {tool_name}",
                    capability_token=dct.to_dict() if dct else None,
                    inputs={"tool_name": tool_name, "arguments": arguments},
                )
            except Exception:
                logger.warning(
                    "Failed to start delegation trace for %s",
                    tool_name,
                    exc_info=True,
                )

        # 4. Call the server's tool handler in-process
        try:
            server = get_server(server_name)

            # Inject the serialized DCT into the arguments so the server-side
            # middleware can perform authoritative enforcement.
            call_args = dict(arguments)
            if dct is not None:
                call_args["dct"] = dct.to_dict()

            result = await server.call_tool(tool_name, call_args)

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
