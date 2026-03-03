"""Composio meta tool definitions and execution helpers for WebSocket chat.

Provides Anthropic-format tool definitions for the 5 Composio meta tools,
plus a dispatch function that routes tool calls through
``ComposioSessionManager.execute_meta_tool()``.

Includes governance filtering to enforce tenant toolkit approval policies.
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


async def _get_user_tenant_id(user_id: str) -> str | None:
    """Get the company_id (tenant_id) for a user.

    Returns None if user has no company association.
    """
    try:
        from src.db.supabase import get_supabase_client

        db = get_supabase_client()
        result = (
            db.table("user_profiles")
            .select("company_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        record = result.data[0] if result and result.data else None
        if record:
            return record.get("company_id")
        return None
    except Exception:
        logger.exception("Failed to fetch user tenant_id")
        return None


async def _get_approved_toolkits(tenant_id: str) -> set[str] | None:
    """Get approved toolkit slugs for a tenant.

    Returns:
        - A set of approved toolkit slugs if tenant has config rows
        - None if tenant has NO config (permissive default for early customers)
    """
    try:
        from src.db.supabase import get_supabase_client

        db = get_supabase_client()
        result = (
            db.table("tenant_toolkit_config")
            .select("toolkit_slug")
            .eq("tenant_id", tenant_id)
            .eq("status", "approved")
            .execute()
        )
        if result.data is None or len(result.data) == 0:
            # No config rows = permissive mode (allow everything)
            return None
        return {row["toolkit_slug"].upper() for row in result.data}
    except Exception:
        logger.exception("Failed to fetch approved toolkits")
        # On error, default to permissive to avoid blocking users
        return None


async def _is_toolkit_approved(user_id: str, toolkit_slug: str) -> tuple[bool, bool]:
    """Check if a toolkit is approved for a user's tenant.

    Args:
        user_id: The user's ID
        toolkit_slug: The toolkit slug to check (e.g. 'GMAIL', 'SALESFORCE')

    Returns:
        Tuple of (is_approved, has_config):
        - (True, True/False) if approved or no config exists (permissive)
        - (False, True) if explicitly denied (config exists but not approved)
    """
    tenant_id = await _get_user_tenant_id(user_id)
    if not tenant_id:
        # No tenant = permissive mode
        return True, False

    approved_set = await _get_approved_toolkits(tenant_id)
    if approved_set is None:
        # No config rows = permissive mode
        return True, False

    return toolkit_slug.upper() in approved_set, True


def _extract_toolkit_from_tool(tool_data: dict[str, Any]) -> str | None:
    """Extract the toolkit/app slug from a tool definition.

    Composio tools have various structures. Try common patterns.
    """
    # Try 'toolkit' key
    if "toolkit" in tool_data:
        tk = tool_data["toolkit"]
        if isinstance(tk, str):
            return tk
        if isinstance(tk, dict):
            return tk.get("slug") or tk.get("name")
    # Try 'app' key
    if "app" in tool_data:
        app = tool_data["app"]
        if isinstance(app, str):
            return app
        if isinstance(app, dict):
            return app.get("slug") or app.get("name")
    # Try 'appName' or 'app_name'
    if "appName" in tool_data:
        return tool_data["appName"]
    if "app_name" in tool_data:
        return tool_data["app_name"]
    # Try to parse from tool slug (e.g. 'GMAIL_SEND_EMAIL' -> 'GMAIL')
    if "name" in tool_data:
        name = tool_data["name"]
        if isinstance(name, str) and "_" in name:
            return name.split("_")[0]
    return None


async def _filter_search_results_by_governance(
    user_id: str,
    tools_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter COMPOSIO_SEARCH_TOOLS results against tenant governance.

    For each tool:
    - If approved → include as-is (ConnectToolCard path)
    - If NOT approved → add 'needs_admin_approval' flag (RequestToolCard path)
    - If no tenant config → include all (permissive default)
    """
    tenant_id = await _get_user_tenant_id(user_id)
    if not tenant_id:
        return tools_data

    approved_set = await _get_approved_toolkits(tenant_id)
    if approved_set is None:
        # No config = permissive mode
        return tools_data

    filtered: list[dict[str, Any]] = []
    for tool in tools_data:
        toolkit_slug = _extract_toolkit_from_tool(tool)
        if toolkit_slug is None:
            # Can't determine toolkit - include with warning
            tool_copy = dict(tool)
            tool_copy["_governance_warning"] = "Could not determine toolkit for governance check"
            filtered.append(tool_copy)
            continue

        is_approved = toolkit_slug.upper() in approved_set
        tool_copy = dict(tool)
        tool_copy["_toolkit_slug"] = toolkit_slug.upper()
        tool_copy["_approved"] = is_approved
        if not is_approved:
            tool_copy["_needs_admin_approval"] = True
            tool_copy["_approval_reason"] = (
                f"'{toolkit_slug}' is not approved for your organization. "
                "Request admin approval to connect this tool."
            )
        filtered.append(tool_copy)

    return filtered


async def execute_composio_meta_tool(
    user_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Execute a Composio meta tool and return the result.

    Applies governance filtering for:
    - COMPOSIO_SEARCH_TOOLS: filters discovered tools by tenant approval
    - COMPOSIO_MANAGE_CONNECTIONS: checks approval before presenting connect URL

    Returns a dict with ``data``, ``error``, and ``successful`` keys.
    On failure, returns ``{"error": ..., "successful": False}``.
    """
    try:
        from src.integrations.composio_sessions import get_session_manager

        manager = get_session_manager()
        result = await manager.execute_meta_tool(
            user_id=user_id,
            tool_name=tool_name,
            arguments=tool_input,
        )

        # Apply governance filter for SEARCH_TOOLS
        if tool_name == "COMPOSIO_SEARCH_TOOLS" and result.get("successful"):
            data = result.get("data", {})
            if isinstance(data, dict):
                tools = data.get("tools", [])
                if isinstance(tools, list):
                    filtered_tools = await _filter_search_results_by_governance(user_id, tools)
                    result["data"]["tools"] = filtered_tools
                    result["data"]["_governance_applied"] = True

        # Apply governance filter for MANAGE_CONNECTIONS (connect URL)
        if tool_name == "COMPOSIO_MANAGE_CONNECTIONS" and result.get("successful"):
            data = result.get("data", {})
            if isinstance(data, dict):
                toolkit_slug = tool_input.get("toolkit") or tool_input.get("app")
                if toolkit_slug:
                    is_approved, has_config = await _is_toolkit_approved(user_id, toolkit_slug)
                    if not is_approved:
                        # Block the connect URL and return approval request instead
                        result["data"]["_needs_admin_approval"] = True
                        result["data"]["_connect_blocked"] = True
                        result["data"]["_approval_reason"] = (
                            f"'{toolkit_slug}' is not approved for your organization. "
                            "Request admin approval to connect this tool."
                        )
                        # Remove the connect URL if present
                        result["data"].pop("redirectUrl", None)
                        result["data"].pop("connect_url", None)
                        result["data"].pop("url", None)
                    else:
                        result["data"]["_approved"] = True

        return result

    except Exception as exc:
        logger.error(
            "Composio meta tool execution failed: tool=%s user=%s error=%s",
            tool_name,
            user_id,
            exc,
        )
        return {"error": str(exc), "successful": False}
