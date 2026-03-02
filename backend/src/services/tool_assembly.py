"""Tool Assembly Service.

Single source of truth for assembling tools and dispatching tool calls
across all modalities (chat WebSocket, video/avatar, voice).

Replaces inline tool assembly in websocket.py and inline dispatch
in chat.py.
"""

from __future__ import annotations

import asyncio as _aio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.services.composio_tools import (
    COMPOSIO_META_TOOL_NAMES,
    execute_composio_meta_tool,
    get_composio_meta_tool_definitions,
)
from src.services.email_tools import (
    EMAIL_TOOL_DEFINITIONS,
    execute_email_tool,
    get_email_context_for_chat,
    get_calendar_context_for_chat,
    get_email_integration,
)

logger = logging.getLogger(__name__)

# Email tool names for dispatch routing
EMAIL_TOOL_NAMES: frozenset[str] = frozenset(
    t["name"] for t in EMAIL_TOOL_DEFINITIONS
)


@dataclass
class ToolSet:
    """Complete tool set for a user interaction."""

    tools: list[dict[str, Any]] = field(default_factory=list)
    email_integration: dict[str, Any] | None = None
    meta_tool_defs: list[dict[str, Any]] = field(default_factory=list)
    email_context: str = ""
    calendar_context: str = ""


async def _safe(coro, default, label: str):
    """Run a coroutine with timeout, returning *default* on failure."""
    try:
        return await _aio.wait_for(coro, timeout=5.0)
    except Exception:
        logger.warning("tool_assembly: %s failed, using default", label)
        return default


async def get_tools_for_user(user_id: str) -> ToolSet:
    """Assemble all available tools for a user interaction.

    Gathers email integration, email context, calendar context, and
    Composio meta tool definitions in parallel.  Builds a combined
    tool list.

    Called by websocket.py, video.py, and any future voice handler.
    """
    email_integration, email_ctx, calendar_ctx, meta_tool_defs = await _aio.gather(
        _safe(get_email_integration(user_id), None, "email_integration"),
        _safe(get_email_context_for_chat(user_id), "", "email_context"),
        _safe(get_calendar_context_for_chat(user_id), "", "calendar_context"),
        _safe(get_composio_meta_tool_definitions(user_id), [], "meta_tools"),
    )

    all_tools: list[dict[str, Any]] = []
    if email_integration:
        all_tools.extend(EMAIL_TOOL_DEFINITIONS)
    all_tools.extend(meta_tool_defs or [])

    return ToolSet(
        tools=all_tools,
        email_integration=email_integration,
        meta_tool_defs=meta_tool_defs or [],
        email_context=email_ctx or "",
        calendar_context=calendar_ctx or "",
    )


async def dispatch_tool_call(
    user_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    email_integration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route a tool call to the correct handler.

    Central dispatcher replacing inline if/elif chains.

    Args:
        user_id: ARIA user UUID.
        tool_name: Name of the tool being called.
        tool_input: Parameters for the tool.
        email_integration: Email integration record (needed by email tools).

    Returns:
        Tool execution result dict.
    """
    if tool_name in COMPOSIO_META_TOOL_NAMES:
        logger.info("Dispatching Composio meta tool %s for user %s", tool_name, user_id)
        return await execute_composio_meta_tool(
            user_id=user_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    if tool_name in EMAIL_TOOL_NAMES and email_integration is not None:
        logger.info("Dispatching email tool %s for user %s", tool_name, user_id)
        return await execute_email_tool(
            tool_name=tool_name,
            params=tool_input,
            user_id=user_id,
            integration=email_integration,
        )

    logger.warning("Unknown tool %s called for user %s", tool_name, user_id)
    return {"error": f"Tool '{tool_name}' is not available."}
