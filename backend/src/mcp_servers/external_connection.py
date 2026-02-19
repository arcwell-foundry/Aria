"""ExternalMCPConnection — manage connections to external MCP servers.

Supports two transport modes:
- **stdio**: Launches a subprocess and communicates via stdin/stdout JSON-RPC.
- **sse**: Connects to an HTTP SSE endpoint.

External servers run in sandboxed environments with no ARIA secrets in their env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from src.core.config import settings
from src.mcp_servers.middleware import DCTViolation, enforce_dct
from src.mcp_servers.models import MCPToolInfo

logger = logging.getLogger(__name__)

# Environment variables that must NOT leak to external processes
_SANITIZED_ENV_KEYS = {
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "COMPOSIO_API_KEY",
    "APP_SECRET_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "RESEND_API_KEY",
    "TAVUS_API_KEY",
    "DAILY_API_KEY",
    "EXA_API_KEY",
    "NEO4J_PASSWORD",
}


def _build_sanitized_env() -> dict[str, str]:
    """Build a sanitized environment dict for subprocess execution.

    Copies the current environment but removes all ARIA secret keys.

    Returns:
        Environment dict safe for external process execution.
    """
    env = dict(os.environ)
    for key in _SANITIZED_ENV_KEYS:
        env.pop(key, None)
    return env


class ExternalMCPConnection:
    """Manages a connection to a single external MCP server.

    For stdio transport, launches the server as a subprocess and communicates
    via JSON-RPC over stdin/stdout.

    For SSE transport, connects to the server's HTTP endpoint.

    Usage::

        conn = ExternalMCPConnection(
            server_name="mcp-server-slack",
            transport="stdio",
            connection_config={"command": "npx", "args": ["-y", "mcp-server-slack"]},
        )
        await conn.connect()
        result = await conn.call_tool("send_message", {"channel": "#general", "text": "hello"})
        await conn.disconnect()
    """

    def __init__(
        self,
        server_name: str,
        transport: str = "stdio",
        connection_config: dict[str, Any] | None = None,
        declared_tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the external connection (does not connect yet).

        Args:
            server_name: Unique identifier for this server.
            transport: ``"stdio"`` or ``"sse"``.
            connection_config: Transport-specific configuration.
                For stdio: ``{"command": "npx", "args": ["-y", "pkg-name"], "env": {}}``.
                For SSE: ``{"url": "https://...", "headers": {}}``.
            declared_tools: Expected tool metadata from the registry.
        """
        self.server_name = server_name
        self.transport = transport
        self._config = connection_config or {}
        self._declared_tools = declared_tools or []
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False
        self._request_id = 0
        self._timeout = settings.MCP_EXTERNAL_SUBPROCESS_TIMEOUT

    @property
    def is_connected(self) -> bool:
        """Whether the connection is currently active."""
        return self._connected

    async def connect(self) -> None:
        """Establish the connection to the external server.

        For stdio: starts the subprocess.
        For SSE: validates the endpoint is reachable.

        Raises:
            ConnectionError: If the connection cannot be established.
        """
        if self._connected:
            return

        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ConnectionError(f"Unknown transport: {self.transport}")

    async def _connect_stdio(self) -> None:
        """Start the external server as a subprocess."""
        command = self._config.get("command", "")
        args = self._config.get("args", [])
        extra_env = self._config.get("env", {})

        if not command:
            raise ConnectionError(
                f"No command configured for stdio server '{self.server_name}'"
            )

        env = _build_sanitized_env()
        env.update(extra_env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._connected = True
            logger.info(
                "Connected to external MCP server '%s' (stdio, pid=%s)",
                self.server_name,
                self._process.pid,
            )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to start subprocess for '{self.server_name}': {exc}"
            ) from exc

    async def _connect_sse(self) -> None:
        """Validate that the SSE endpoint is reachable."""
        url = self._config.get("url", "")
        if not url:
            raise ConnectionError(
                f"No URL configured for SSE server '{self.server_name}'"
            )

        import httpx

        headers = self._config.get("headers", {})
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                # Accept any 2xx status
                if 200 <= response.status_code < 300:
                    self._connected = True
                    logger.info(
                        "Connected to external MCP server '%s' (sse, url=%s)",
                        self.server_name,
                        url,
                    )
                else:
                    raise ConnectionError(
                        f"SSE endpoint returned {response.status_code} for '{self.server_name}'"
                    )
        except httpx.HTTPError as exc:
            raise ConnectionError(
                f"Failed to reach SSE endpoint for '{self.server_name}': {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Gracefully shut down the connection.

        For stdio: sends a shutdown request, then terminates the process.
        For SSE: no persistent connection to close.
        """
        if not self._connected:
            return

        if self.transport == "stdio" and self._process is not None:
            try:
                # Try graceful shutdown first
                if self._process.stdin and not self._process.stdin.is_closing():
                    self._process.stdin.close()
                # Wait briefly for process to exit
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
            except Exception:
                logger.warning(
                    "Error during disconnect of '%s'", self.server_name, exc_info=True
                )
            finally:
                self._process = None

        self._connected = False
        logger.info("Disconnected from external MCP server '%s'", self.server_name)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dct_dict: dict[str, Any] | None = None,
        dct_action: str = "",
    ) -> dict[str, Any]:
        """Call a tool on the external MCP server.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Tool arguments.
            dct_dict: Optional serialized DCT for permission enforcement.
            dct_action: DCT action string to check against.

        Returns:
            Tool result dict.

        Raises:
            ConnectionError: If not connected.
            DCTViolation: If the DCT denies the action.
            TimeoutError: If the tool call exceeds the timeout.
        """
        if not self._connected:
            raise ConnectionError(
                f"Not connected to '{self.server_name}'. Call connect() first."
            )

        # DCT enforcement
        if dct_dict and dct_action:
            enforce_dct(tool_name, dct_action, dct_dict)

        if self.transport == "stdio":
            return await self._call_tool_stdio(tool_name, arguments)
        elif self.transport == "sse":
            return await self._call_tool_sse(tool_name, arguments)
        else:
            raise ConnectionError(f"Unknown transport: {self.transport}")

    async def _call_tool_stdio(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a JSON-RPC tool call over stdio."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise ConnectionError(f"Subprocess not available for '{self.server_name}'")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        request_bytes = (json.dumps(request) + "\n").encode()

        try:
            self._process.stdin.write(request_bytes)
            await self._process.stdin.drain()

            # Read response with timeout
            response_bytes = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=self._timeout,
            )

            if not response_bytes:
                raise ConnectionError(
                    f"Empty response from '{self.server_name}' for tool '{tool_name}'"
                )

            response = json.loads(response_bytes.decode())

            if "error" in response:
                error = response["error"]
                return {
                    "error": error.get("message", str(error)),
                    "code": error.get("code", -1),
                }

            result = response.get("result", {})
            return result if isinstance(result, dict) else {"result": result}

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Tool call '{tool_name}' on '{self.server_name}' "
                f"timed out after {self._timeout}s"
            )
        except json.JSONDecodeError as exc:
            raise ConnectionError(
                f"Invalid JSON response from '{self.server_name}': {exc}"
            ) from exc

    async def _call_tool_sse(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a tool call via HTTP POST to the SSE server."""
        import httpx

        url = self._config.get("url", "")
        headers = self._config.get("headers", {})

        # POST to /tools/call endpoint
        call_url = f"{url.rstrip('/')}/tools/call"
        payload = {
            "name": tool_name,
            "arguments": arguments,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    call_url, json=payload, headers=headers
                )
                response.raise_for_status()
                result = response.json()
                return result if isinstance(result, dict) else {"result": result}

        except httpx.TimeoutException:
            raise TimeoutError(
                f"Tool call '{tool_name}' on '{self.server_name}' "
                f"timed out after {self._timeout}s"
            )
        except httpx.HTTPError as exc:
            return {"error": f"HTTP error calling '{tool_name}': {exc}"}

    async def health_check(self) -> str:
        """Perform a health check on the external server.

        Uses a safe read-only probe: lists available tools.

        Returns:
            Health status: ``"healthy"``, ``"degraded"``, or ``"unhealthy"``.
        """
        if not self._connected:
            return "unhealthy"

        try:
            tools = await self.list_tools()
            if tools:
                return "healthy"
            return "degraded"
        except Exception:
            logger.warning(
                "Health check failed for '%s'", self.server_name, exc_info=True
            )
            return "unhealthy"

    async def list_tools(self) -> list[MCPToolInfo]:
        """Discover available tools from the connected server.

        Returns:
            List of tool metadata from the server.
        """
        if not self._connected:
            return []

        if self.transport == "stdio":
            return await self._list_tools_stdio()
        elif self.transport == "sse":
            return await self._list_tools_sse()
        return []

    async def _list_tools_stdio(self) -> list[MCPToolInfo]:
        """List tools via JSON-RPC over stdio."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            return []

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/list",
            "params": {},
        }

        try:
            request_bytes = (json.dumps(request) + "\n").encode()
            self._process.stdin.write(request_bytes)
            await self._process.stdin.drain()

            response_bytes = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=10.0,
            )

            if not response_bytes:
                return []

            response = json.loads(response_bytes.decode())
            tools_data = response.get("result", {}).get("tools", [])
            return [
                MCPToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools_data
                if isinstance(t, dict)
            ]
        except Exception:
            logger.warning(
                "Failed to list tools from '%s'", self.server_name, exc_info=True
            )
            return []

    async def _list_tools_sse(self) -> list[MCPToolInfo]:
        """List tools via HTTP GET from the SSE server."""
        import httpx

        url = self._config.get("url", "")
        headers = self._config.get("headers", {})
        list_url = f"{url.rstrip('/')}/tools/list"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(list_url, headers=headers)
                response.raise_for_status()
                data = response.json()

            tools_data = data.get("tools", []) if isinstance(data, dict) else []
            return [
                MCPToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools_data
                if isinstance(t, dict)
            ]
        except Exception:
            logger.warning(
                "Failed to list tools from '%s'", self.server_name, exc_info=True
            )
            return []
