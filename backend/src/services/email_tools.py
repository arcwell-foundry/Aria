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
    {
        "name": "draft_email_reply",
        "description": (
            "Draft a reply to a specific email. Use when the user asks to "
            "draft, write, or reply to an email. Searches for the email, "
            "gathers full context (thread history, recipient research, "
            "writing style, calendar, CRM), generates a style-matched draft, "
            "and saves it to their email drafts folder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_identifier": {
                    "type": "string",
                    "description": (
                        "The email to reply to — a sender name, subject "
                        "keyword, or email ID from a previous search"
                    ),
                },
                "special_instructions": {
                    "type": "string",
                    "description": (
                        "Optional user instructions for the draft, e.g. "
                        "'mention the Q3 timeline' or 'keep it brief'"
                    ),
                },
            },
            "required": ["email_identifier"],
        },
    },
    {
        "name": "check_email_decision",
        "description": (
            "Look up why ARIA did or didn't draft a reply to a specific email. "
            "Use when the user asks 'why didn't you reply to...?' or "
            "'what happened with that email from...?' or wants to understand "
            "ARIA's categorization of an email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sender_query": {
                    "type": "string",
                    "description": "Sender email or name to search for",
                },
                "subject_query": {
                    "type": "string",
                    "description": "Optional subject text to search for",
                },
            },
            "required": ["sender_query"],
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
        for provider in ("outlook", "gmail"):
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
        elif tool_name == "draft_email_reply":
            return await _handle_draft_email_reply(
                oauth_client, connection_id, provider, user_id, params
            )
        elif tool_name == "check_email_decision":
            return await _check_email_decision(user_id, params)
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
            action="OUTLOOK_OUTLOOK_LIST_MESSAGES",
            params={"folder": "Inbox", "top": count, "orderby": ["receivedDateTime desc"]},
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
            action="OUTLOOK_OUTLOOK_LIST_MESSAGES",
            params={
                "folder": "Inbox",
                "top": max_results,
                "$search": f'"{query}"',
                "orderby": ["receivedDateTime desc"],
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
            action="OUTLOOK_OUTLOOK_GET_MESSAGE",
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
            "thread_id": msg.get("conversationId", ""),
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
            "thread_id": msg.get("threadId", msg.get("thread_id", "")),
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


def _parse_sender_email(from_field: str) -> str:
    """Extract bare email address from 'Name <email>' format."""
    if "<" in from_field and ">" in from_field:
        return from_field.split("<")[1].split(">")[0].strip()
    return from_field.strip()


def _parse_sender_name(from_field: str) -> str:
    """Extract display name from 'Name <email>' format."""
    if "<" in from_field:
        return from_field.split("<")[0].strip()
    return ""


async def _handle_draft_email_reply(
    oauth_client: Any,
    connection_id: str,
    provider: str,
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Handle on-demand email draft reply triggered from chat.

    Searches for the matching email, then runs the full drafting pipeline
    (context gathering, style matching, LLM generation, confidence scoring)
    and saves the draft to the user's email client.

    Args:
        oauth_client: Composio OAuth client.
        connection_id: User's Composio connection ID.
        provider: Email provider (outlook/gmail).
        user_id: The user's ID.
        params: Tool input with email_identifier and optional special_instructions.

    Returns:
        Dict with draft details or error.
    """
    email_identifier = params.get("email_identifier", "")
    special_instructions = params.get("special_instructions")

    if not email_identifier:
        return {"error": "email_identifier is required"}

    # 1. Search for the matching email
    search_result = await _search_emails(
        oauth_client, connection_id, provider, user_id,
        {"query": email_identifier, "max_results": 5},
    )

    emails = search_result.get("emails", [])
    if not emails:
        return {"error": f"Couldn't find an email matching '{email_identifier}'"}

    target = emails[0]  # Best match

    # 2. Get full email detail for the body
    detail_result = await _read_email_detail(
        oauth_client, connection_id, provider, user_id,
        {"message_id": target["id"]},
    )

    email_detail = detail_result.get("email", {})

    # 3. Build email data dict for the draft engine
    from_field = email_detail.get("from", target.get("from", ""))
    sender_email = _parse_sender_email(from_field)
    sender_name = _parse_sender_name(from_field)

    email_data = {
        "email_id": email_detail.get("id", target["id"]),
        "thread_id": target.get("thread_id", ""),
        "sender_email": sender_email,
        "sender_name": sender_name or None,
        "subject": email_detail.get("subject", target.get("subject", "")),
        "body": email_detail.get("body", target.get("preview", "")),
        "snippet": target.get("preview", ""),
        "urgency": "NORMAL",
    }

    # 4. Run the full drafting pipeline
    from src.services.autonomous_draft_engine import AutonomousDraftEngine

    engine = AutonomousDraftEngine()
    result = await engine.draft_reply_on_demand(
        user_id=user_id,
        email_data=email_data,
        special_instructions=special_instructions,
    )

    return result


async def _check_email_decision(
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Look up ARIA's categorization decision for a specific email.

    Searches the email_scan_log table by sender email/name and optionally
    by subject to explain why an email was or wasn't drafted.

    Args:
        user_id: The user's ID.
        params: Tool input with sender_query and optional subject_query.

    Returns:
        Dict with decision details or error message.
    """
    sender_query = params.get("sender_query", "")
    subject_query = params.get("subject_query")

    if not sender_query:
        return {"error": "sender_query is required"}

    try:
        client = SupabaseClient.get_client()

        # Build query with ILIKE for case-insensitive search
        query = (
            client.table("email_scan_log")
            .select("*")
            .eq("user_id", user_id)
            .or_(f"sender_email.ilike.%{sender_query}%,sender_name.ilike.%{sender_query}%")
            .order("scanned_at", desc=True)
            .limit(5)
        )

        if subject_query:
            # Add subject filter using ilike
            query = query.ilike("subject", f"%{subject_query}%")

        result = query.execute()

        decisions = result.data or []
        if not decisions:
            return {
                "found": False,
                "message": f"No scan decision found for sender matching '{sender_query}'"
                + (f" with subject containing '{subject_query}'" if subject_query else ""),
            }

        # Format the most recent decision
        latest = decisions[0]
        return {
            "found": True,
            "decision": {
                "email_id": latest.get("email_id", ""),
                "sender_email": latest.get("sender_email", ""),
                "sender_name": latest.get("sender_name"),
                "subject": latest.get("subject"),
                "category": latest.get("category", "UNKNOWN"),
                "urgency": latest.get("urgency", "NORMAL"),
                "needs_draft": latest.get("needs_draft", False),
                "reason": latest.get("reason", "No reason recorded"),
                "scanned_at": latest.get("scanned_at", ""),
            },
            "other_matches": [
                {
                    "sender_email": d.get("sender_email", ""),
                    "subject": d.get("subject"),
                    "category": d.get("category"),
                    "scanned_at": d.get("scanned_at", ""),
                }
                for d in decisions[1:]
            ],
        }

    except Exception as e:
        logger.error(
            "Failed to check email decision for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return {"error": f"Failed to look up email decision: {str(e)}"}
