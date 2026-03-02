"""Composio meta tool definitions and execution helpers for WebSocket chat.

Provides Anthropic-format tool definitions for the 5 Composio meta tools,
plus a dispatch function that routes tool calls through
``ComposioSessionManager.execute_meta_tool()``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The meta tool slugs we expose in the chat path.
COMPOSIO_META_TOOL_NAMES: frozenset[str] = frozenset({
    "COMPOSIO_SEARCH_TOOLS",
    "COMPOSIO_MANAGE_CONNECTIONS",
    "COMPOSIO_MULTI_EXECUTE_TOOL",
    "COMPOSIO_REMOTE_WORKBENCH",
    "COMPOSIO_REMOTE_BASH_TOOL",
})


def _openai_to_anthropic(tool: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single OpenAI-format tool definition to Anthropic format.

    OpenAI format::

        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

    Anthropic format::

        {"name": ..., "description": ..., "input_schema": ...}

    Returns ``None`` if the tool definition is malformed.
    """
    func = tool.get("function") if tool.get("type") == "function" else None
    if func is None:
        # Some SDK versions nest differently — try top-level keys.
        name = tool.get("name")
        if name:
            return {
                "name": name,
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", tool.get("input_schema", {"type": "object", "properties": {}})),
            }
        return None

    return {
        "name": func["name"],
        "description": func.get("description", ""),
        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
    }


async def get_composio_meta_tool_definitions(user_id: str) -> list[dict[str, Any]]:
    """Fetch and convert Composio meta tool definitions for a user session.

    Returns Anthropic-format tool definitions filtered to
    ``COMPOSIO_META_TOOL_NAMES``.  Returns an empty list on any failure
    (graceful degradation — chat still works without meta tools).
    """
    try:
        from src.integrations.composio_sessions import get_session_manager

        manager = get_session_manager()
        raw_tools = await manager.get_tools(user_id)

        if not raw_tools:
            return []

        result: list[dict[str, Any]] = []
        for tool in raw_tools:
            converted = _openai_to_anthropic(tool)
            if converted and converted["name"] in COMPOSIO_META_TOOL_NAMES:
                result.append(converted)

        logger.debug(
            "Fetched %d Composio meta tools for user %s",
            len(result),
            user_id,
        )
        return result

    except Exception as exc:
        logger.warning(
            "Failed to fetch Composio meta tools for user %s: %s",
            user_id,
            exc,
        )
        return []


async def execute_composio_meta_tool(
    user_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Execute a Composio meta tool and return the result.

    Returns a dict with ``data``, ``error``, and ``successful`` keys.
    On failure, returns ``{"error": ..., "successful": False}``.
    """
    try:
        from src.integrations.composio_sessions import get_session_manager

        manager = get_session_manager()
        return await manager.execute_meta_tool(
            user_id=user_id,
            tool_name=tool_name,
            arguments=tool_input,
        )
    except Exception as exc:
        logger.error(
            "Composio meta tool execution failed: tool=%s user=%s error=%s",
            tool_name,
            user_id,
            exc,
        )
        return {"error": str(exc), "successful": False}
