"""Email tools for the chat agent via Composio.

Provides tool definitions and execution handlers so the LLM can
natively access a user's email (Gmail or Outlook) during chat.
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Anthropic tool definitions for email access
EMAIL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "read_recent_emails",
        "description": (
            "Read the user's recent emails from their inbox. "
            "Use when the user asks about their inbox, emails, or messages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of emails to fetch (max 20)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_emails",
        "description": (
            "Search the user's email by keyword, sender, or subject. "
            "Use when the user asks to find specific emails or messages "
            "from a particular person or about a topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keyword, sender name, subject text)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max emails to return",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_email_detail",
        "description": (
            "Read the full content of a specific email by its ID. "
            "Use after listing emails to get the full body of one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The email message ID",
                },
            },
            "required": ["message_id"],
        },
    },
]


async def get_email_integration(user_id: str) -> dict[str, Any] | None:
    """Check if user has an active email integration (Gmail or Outlook).

    Args:
        user_id: The user's ID.

    Returns:
        Integration record dict if found, None otherwise.
    """
    try:
        client = SupabaseClient.get_client()
        for provider in ("gmail", "outlook"):
            result = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", provider)
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if result.data and result.data.get("composio_connection_id"):
                return result.data
        return None
    except Exception as e:
        logger.warning("Failed to check email integration for user %s: %s", user_id, e)
        return None


async def execute_email_tool(
    tool_name: str,
    params: dict[str, Any],
    user_id: str,
    integration: dict[str, Any],
) -> dict[str, Any]:
    """Execute an email tool call via Composio.

    Args:
        tool_name: Name of the tool to execute.
        params: Tool input parameters from the LLM.
        user_id: The user's ID.
        integration: The user's email integration record.

    Returns:
        Tool result dict with data or error.
    """
    from src.integrations.oauth import get_oauth_client

    connection_id = integration["composio_connection_id"]
    provider = integration.get("integration_type", "gmail").lower()
    oauth_client = get_oauth_client()

    try:
        if tool_name == "read_recent_emails":
            return await _read_recent_emails(
                oauth_client, connection_id, provider, user_id, params
            )
        elif tool_name == "search_emails":
            return await _search_emails(
                oauth_client, connection_id, provider, user_id, params
            )
        elif tool_name == "read_email_detail":
            return await _read_email_detail(
                oauth_client, connection_id, provider, user_id, params
            )
        else:
            return {"error": f"Unknown email tool: {tool_name}"}
    except Exception as e:
        logger.error(
            "Email tool %s failed for user %s: %s",
            tool_name,
            user_id,
            e,
            exc_info=True,
        )
        return {"error": f"Failed to execute {tool_name}: {str(e)}"}


async def _read_recent_emails(
    oauth_client: Any,
    connection_id: str,
    provider: str,
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Fetch recent inbox emails."""
    count = min(params.get("count", 10), 20)

    if provider == "outlook":
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="OUTLOOK_LIST_MESSAGES",
            params={"$top": count, "$orderby": "receivedDateTime desc"},
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            messages = result["data"].get("value", [])
            return {"emails": _normalize_outlook_messages(messages)}
        return {"error": result.get("error", "Failed to fetch emails"), "emails": []}
    else:
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="GMAIL_FETCH_EMAILS",
            params={"max_results": count, "label": "INBOX"},
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            emails = result["data"].get("emails", [])
            if not emails:
                emails = result["data"].get("messages", [])
            return {"emails": _normalize_gmail_messages(emails)}
        return {"error": result.get("error", "Failed to fetch emails"), "emails": []}


async def _search_emails(
    oauth_client: Any,
    connection_id: str,
    provider: str,
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Search emails by query."""
    query = params.get("query", "")
    max_results = min(params.get("max_results", 10), 20)

    if provider == "outlook":
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="OUTLOOK_LIST_MESSAGES",
            params={
                "$top": max_results,
                "$search": f'"{query}"',
                "$orderby": "receivedDateTime desc",
            },
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            messages = result["data"].get("value", [])
            return {"emails": _normalize_outlook_messages(messages), "query": query}
        return {"error": result.get("error", "Search failed"), "emails": []}
    else:
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="GMAIL_FETCH_EMAILS",
            params={"query": query, "max_results": max_results},
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            emails = result["data"].get("emails", [])
            if not emails:
                emails = result["data"].get("messages", [])
            return {"emails": _normalize_gmail_messages(emails), "query": query}
        return {"error": result.get("error", "Search failed"), "emails": []}


async def _read_email_detail(
    oauth_client: Any,
    connection_id: str,
    provider: str,
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Read a specific email by ID."""
    message_id = params.get("message_id", "")
    if not message_id:
        return {"error": "message_id is required"}

    if provider == "outlook":
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="OUTLOOK_GET_MESSAGE",
            params={"message_id": message_id},
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            msg = result["data"]
            return {
                "email": {
                    "id": msg.get("id", ""),
                    "subject": msg.get("subject", ""),
                    "from": _extract_outlook_sender(msg),
                    "to": _extract_outlook_recipients(msg, "toRecipients"),
                    "date": msg.get("receivedDateTime", ""),
                    "body": msg.get("body", {}).get("content", ""),
                    "is_read": msg.get("isRead", False),
                }
            }
        return {"error": result.get("error", "Failed to read email")}
    else:
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action="GMAIL_GET_MESSAGE",
            params={"message_id": message_id},
            user_id=user_id,
        )
        if result.get("successful") and result.get("data"):
            msg = result["data"]
            return {
                "email": {
                    "id": msg.get("id", ""),
                    "subject": msg.get("subject", ""),
                    "from": msg.get("sender", msg.get("from", "")),
                    "to": msg.get("to", []),
                    "date": msg.get("date", msg.get("internalDate", "")),
                    "body": msg.get("body", msg.get("snippet", "")),
                    "is_read": not msg.get("labelIds", []),
                }
            }
        return {"error": result.get("error", "Failed to read email")}


def _normalize_outlook_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Outlook messages to a common format."""
    normalized = []
    for msg in messages:
        normalized.append({
            "id": msg.get("id", ""),
            "subject": msg.get("subject", "(no subject)"),
            "from": _extract_outlook_sender(msg),
            "date": msg.get("receivedDateTime", ""),
            "preview": msg.get("bodyPreview", ""),
            "is_read": msg.get("isRead", False),
            "has_attachments": msg.get("hasAttachments", False),
        })
    return normalized


def _normalize_gmail_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Gmail messages to a common format."""
    normalized = []
    for msg in messages:
        normalized.append({
            "id": msg.get("id", msg.get("messageId", "")),
            "subject": msg.get("subject", "(no subject)"),
            "from": msg.get("sender", msg.get("from", "")),
            "date": msg.get("date", msg.get("internalDate", "")),
            "preview": msg.get("snippet", msg.get("preview", "")),
            "is_read": "UNREAD" not in msg.get("labelIds", []),
            "has_attachments": bool(msg.get("attachments")),
        })
    return normalized


def _extract_outlook_sender(msg: dict[str, Any]) -> str:
    """Extract sender string from Outlook message."""
    sender = msg.get("from", {})
    if isinstance(sender, dict):
        addr = sender.get("emailAddress", {})
        name = addr.get("name", "")
        email = addr.get("address", "")
        return f"{name} <{email}>" if name else email
    return str(sender)


def _extract_outlook_recipients(msg: dict[str, Any], field: str) -> list[str]:
    """Extract recipient list from Outlook message."""
    recipients = msg.get(field, [])
    result = []
    for r in recipients:
        if isinstance(r, dict):
            addr = r.get("emailAddress", {})
            name = addr.get("name", "")
            email = addr.get("address", "")
            result.append(f"{name} <{email}>" if name else email)
        else:
            result.append(str(r))
    return result
