"""MCP Server registry — tool-to-server mapping and FastAPI mounting.

``TOOL_SERVER_MAP`` maps every MCP tool name to the server that owns it
and the DCT action it requires.  ``mount_mcp_servers(app)`` mounts each
server's SSE transport on FastAPI and stores server instances for
in-process calls via ``MCPToolClient``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from mcp.server.fastmcp import FastMCP

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
