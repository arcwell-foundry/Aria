"""MCP Server registry — tool-to-server mapping and FastAPI mounting.

``TOOL_SERVER_MAP`` maps every MCP tool name to the server that owns it
and the DCT action it requires.  ``mount_mcp_servers(app)`` mounts each
server's SSE transport on FastAPI and stores server instances for
in-process calls via ``MCPToolClient``.

``EXTERNAL_TOOL_SERVER_MAP`` is a per-user mapping for external MCP servers
installed via the capability management system (Prompt 5B).

``resolve_tool()`` checks built-in tools first, then user-specific external tools.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from mcp.server.fastmcp import FastMCP
    from src.mcp_servers.capability_store import CapabilityStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool → (server_name, dct_action) mapping
# ---------------------------------------------------------------------------

TOOL_SERVER_MAP: dict[str, tuple[str, str]] = {
    # Life Sciences
    "pubmed_search": ("lifesci", "read_pubmed"),
    "pubmed_fetch_details": ("lifesci", "read_pubmed"),
    "clinical_trials_search": ("lifesci", "read_clinicaltrials"),
    "fda_drug_search": ("lifesci", "read_fda"),
    "chembl_search": ("lifesci", "read_chembl"),
    # Exa Web Intelligence
    "exa_search_web": ("exa", "read_exa"),
    "exa_search_news": ("exa", "read_news_apis"),
    "exa_find_similar": ("exa", "read_exa"),
    "exa_answer": ("exa", "read_exa"),
    "exa_research": ("exa", "read_exa"),
    "exa_get_contents": ("exa", "read_exa"),
    # Business Tools
    "calendar_read": ("business", "read_calendar"),
    "calendar_write": ("business", "write_calendar"),
    "crm_read": ("business", "read_crm"),
    "crm_write": ("business", "write_crm"),
    "email_send": ("business", "send_email"),
}


# ---------------------------------------------------------------------------
# Server instances (populated by mount_mcp_servers)
# ---------------------------------------------------------------------------

_servers: dict[str, FastMCP] = {}


def get_server(name: str) -> FastMCP:
    """Return a registered MCP server by name.

    Args:
        name: Server name (``"lifesci"``, ``"exa"``, or ``"business"``).

    Raises:
        KeyError: If the server has not been registered.
    """
    return _servers[name]


def get_all_servers() -> dict[str, FastMCP]:
    """Return all registered servers as a dict keyed by name."""
    return dict(_servers)


# ---------------------------------------------------------------------------
# External tool → (server_name, dct_action) per-user mapping
# ---------------------------------------------------------------------------

# user_id → tool_name → (server_name, dct_action)
EXTERNAL_TOOL_SERVER_MAP: dict[str, dict[str, tuple[str, str]]] = {}


def resolve_tool(
    tool_name: str, user_id: str | None = None
) -> tuple[str, str, bool]:
    """Resolve a tool name to its server, checking built-in first then external.

    Args:
        tool_name: The MCP tool name to resolve.
        user_id: Optional user ID for external tool lookup.

    Returns:
        Tuple of (server_name, dct_action, is_external).

    Raises:
        KeyError: If the tool is not found in any map.
    """
    # Built-in tools take priority
    if tool_name in TOOL_SERVER_MAP:
        server_name, dct_action = TOOL_SERVER_MAP[tool_name]
        return server_name, dct_action, False

    # Check user's external tools
    if user_id and user_id in EXTERNAL_TOOL_SERVER_MAP:
        user_tools = EXTERNAL_TOOL_SERVER_MAP[user_id]
        if tool_name in user_tools:
            server_name, dct_action = user_tools[tool_name]
            return server_name, dct_action, True

    raise KeyError(
        f"Unknown MCP tool: '{tool_name}'. "
        f"Not found in built-in or external tool maps."
    )


def register_external_tools(
    user_id: str,
    server_name: str,
    tools: list[dict[str, Any]],
    default_dct_action: str = "read_external",
) -> None:
    """Register tools from an installed external MCP server.

    Args:
        user_id: The user's UUID.
        server_name: External server identifier.
        tools: List of tool metadata dicts (each must have ``"name"``).
        default_dct_action: Default DCT action for tools without one.
    """
    if user_id not in EXTERNAL_TOOL_SERVER_MAP:
        EXTERNAL_TOOL_SERVER_MAP[user_id] = {}

    user_tools = EXTERNAL_TOOL_SERVER_MAP[user_id]
    registered = 0
    for tool in tools:
        name = tool.get("name", "")
        if not name:
            continue
        dct_action = tool.get("dct_action", default_dct_action)
        user_tools[name] = (server_name, dct_action)
        registered += 1

    logger.info(
        "Registered %d external tools for user %s from server '%s'",
        registered,
        user_id,
        server_name,
    )


def unregister_external_tools(user_id: str, server_name: str) -> None:
    """Remove all tools for a specific external server from a user's map.

    Args:
        user_id: The user's UUID.
        server_name: External server identifier.
    """
    if user_id not in EXTERNAL_TOOL_SERVER_MAP:
        return

    user_tools = EXTERNAL_TOOL_SERVER_MAP[user_id]
    to_remove = [
        name for name, (srv, _) in user_tools.items() if srv == server_name
    ]
    for name in to_remove:
        del user_tools[name]

    logger.info(
        "Unregistered %d external tools for user %s from server '%s'",
        len(to_remove),
        user_id,
        server_name,
    )


async def load_user_external_tools(
    user_id: str, store: CapabilityStore
) -> None:
    """Load a user's external tools from DB into the in-memory map.

    Called lazily on first request for a user's external tools.

    Args:
        user_id: The user's UUID.
        store: CapabilityStore instance for DB access.
    """
    capabilities = await store.list_user_capabilities(user_id, enabled_only=True)
    for cap in capabilities:
        register_external_tools(
            user_id=user_id,
            server_name=cap.server_name,
            tools=cap.declared_tools,
        )

    logger.info(
        "Loaded external tools for user %s from %d capabilities",
        user_id,
        len(capabilities),
    )


# ---------------------------------------------------------------------------
# FastAPI mounting
# ---------------------------------------------------------------------------


def mount_mcp_servers(app: FastAPI) -> None:
    """Import each MCP server module, mount its SSE app, and register it.

    Called once during the FastAPI lifespan startup.  Skipped entirely
    when ``settings.MCP_SERVERS_ENABLED`` is False.

    Args:
        app: The FastAPI application instance.
    """
    if not settings.MCP_SERVERS_ENABLED:
        logger.info("MCP servers disabled (MCP_SERVERS_ENABLED=False)")
        return

    # Lazy imports to avoid circular dependency with agents
    from src.mcp_servers.business.server import business_mcp
    from src.mcp_servers.exa.server import exa_mcp
    from src.mcp_servers.lifesci.server import lifesci_mcp

    server_configs: list[tuple[str, FastMCP, str]] = [
        ("lifesci", lifesci_mcp, settings.MCP_LIFESCI_PATH),
        ("exa", exa_mcp, settings.MCP_EXA_PATH),
        ("business", business_mcp, settings.MCP_BUSINESS_PATH),
    ]

    for name, server, path in server_configs:
        _servers[name] = server
        # Mount the SSE transport for external MCP clients
        app.mount(path, server.sse_app())
        logger.info("Mounted MCP server '%s' at %s", name, path)

    logger.info(
        "MCP servers ready: %d servers, %d tools registered",
        len(_servers),
        len(TOOL_SERVER_MAP),
    )
