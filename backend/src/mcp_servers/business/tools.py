"""Standalone business-tool implementations for the MCP server.

Each function mirrors the logic previously encapsulated inside
``OperatorAgent`` but accepts ``user_id`` as an explicit parameter so
it can be called from the MCP tool layer without an agent instance.

Integration status is checked against the ``user_integrations`` table
in Supabase.  When connected, actions are executed via the Composio SDK
through :class:`~src.integrations.oauth.ComposioOAuthClient`.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.operator import (
    _CALENDAR_INTEGRATION_TYPES,
    _CALENDAR_READ_ACTIONS,
    _CALENDAR_WRITE_ACTIONS,
    _CRM_INTEGRATION_TYPES,
    _CRM_READ_ACTIONS,
    _CRM_WRITE_ACTIONS,
    _SALESFORCE_SOBJECT_MAP,
)

logger = logging.getLogger(__name__)

# Integration types that satisfy the "email" category.
_EMAIL_INTEGRATION_TYPES = ("gmail", "outlook")

# Composio action slugs for sending email per provider.
_EMAIL_SEND_ACTIONS: dict[str, str] = {
    "gmail": "GMAIL_SEND_EMAIL",
    "outlook": "OUTLOOK_SEND_EMAIL",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _check_integration_status(
    user_id: str,
    category: str,
) -> dict[str, Any]:
    """Check user's integration status for a category.

    Queries the ``user_integrations`` table for active integrations
    matching the requested *category* (``"calendar"``, ``"crm"``, or
    ``"email"``).

    Args:
        user_id: The user whose integrations to check.
        category: ``"calendar"``, ``"crm"``, or ``"email"``.

    Returns:
        Dict with ``connected``, ``provider``, ``integration_id``, and
        ``composio_connection_id`` keys.
    """
    integration_types: tuple[str, ...]
    if category == "calendar":
        integration_types = _CALENDAR_INTEGRATION_TYPES
    elif category == "crm":
        integration_types = _CRM_INTEGRATION_TYPES
    elif category == "email":
        integration_types = _EMAIL_INTEGRATION_TYPES
    else:
        logger.warning("Unknown integration category: %s", category)
        return {
            "connected": False,
            "provider": None,
            "integration_id": None,
            "composio_connection_id": None,
        }

    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()

        response = (
            client.table("user_integrations")
            .select("id, integration_type, status, composio_connection_id")
            .eq("user_id", user_id)
            .eq("status", "active")
            .in_("integration_type", list(integration_types))
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            row = response.data[0]
            return {
                "connected": True,
                "provider": row.get("integration_type"),
                "integration_id": row.get("id"),
                "composio_connection_id": row.get("composio_connection_id"),
            }

    except Exception:
        logger.warning(
            "Failed to query user_integrations for user %s (category=%s). "
            "Treating as not connected.",
            user_id,
            category,
            exc_info=True,
        )

    return {
        "connected": False,
        "provider": None,
        "integration_id": None,
        "composio_connection_id": None,
    }


async def _execute_composio_action(
    connection_id: str,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Execute a Composio action via the OAuth client.

    Args:
        connection_id: Composio connection ID for the user's integration.
        action: Composio tool slug (e.g. ``'GOOGLECALENDAR_FIND_EVENT'``).
        params: Parameters for the action.

    Returns:
        Action result dict, or an error / not-configured dict on failure.
    """
    from src.core.config import settings

    if not settings.COMPOSIO_API_KEY:
        return {
            "status": "not_configured",
            "message": "Set COMPOSIO_API_KEY in environment to enable integrations.",
        }

    try:
        from src.integrations.oauth import get_oauth_client

        oauth_client = get_oauth_client()
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
        )
        return result

    except Exception as exc:
        logger.error(
            "Composio action %s failed: %s",
            action,
            exc,
            exc_info=True,
        )
        return {
            "status": "error",
            "message": f"Integration action failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


async def calendar_read_impl(
    user_id: str,
    start_date: str,
    end_date: str | None = None,
    calendar_id: str | None = None,
) -> dict[str, Any]:
    """Read calendar events within a date range.

    Checks the user's calendar integration status first.  If no calendar
    integration is active, returns an honest "not connected" payload.

    Args:
        user_id: The requesting user's ID.
        start_date: Start date in ``YYYY-MM-DD`` format.
        end_date: Optional end date in ``YYYY-MM-DD`` format.
        calendar_id: Optional calendar identifier.

    Returns:
        Dict with ``connected``, ``provider``, ``events``, and
        ``total_count`` keys.
    """
    logger.info(
        "Reading calendar events from %s to %s for user %s",
        start_date,
        end_date or "present",
        user_id,
    )

    status = await _check_integration_status(user_id, "calendar")

    if not status["connected"]:
        return {
            "connected": False,
            "message": (
                "Calendar integration not connected. "
                "Connect Google Calendar or Outlook in Settings > Integrations "
                "to enable calendar access."
            ),
            "events": [],
            "total_count": 0,
        }

    provider = status["provider"]
    connection_id = status.get("composio_connection_id")

    if not connection_id:
        return {
            "connected": True,
            "provider": provider,
            "message": (
                f"Calendar integration detected ({provider}), but the "
                "connection ID is missing. Please reconnect in "
                "Settings > Integrations."
            ),
            "events": [],
            "total_count": 0,
        }

    action_slug = _CALENDAR_READ_ACTIONS.get(provider)  # type: ignore[arg-type]
    if not action_slug:
        return {
            "connected": True,
            "provider": provider,
            "message": f"No calendar read action mapped for provider '{provider}'.",
            "events": [],
            "total_count": 0,
        }

    # Build Composio-compatible params
    composio_params: dict[str, Any] = {
        "timeMin": f"{start_date}T00:00:00Z",
    }
    if end_date:
        composio_params["timeMax"] = f"{end_date}T23:59:59Z"
    if calendar_id:
        composio_params["calendarId"] = calendar_id

    result = await _execute_composio_action(connection_id, action_slug, composio_params)

    if result.get("status") in ("not_configured", "error"):
        return {
            "connected": True,
            "provider": provider,
            "message": result.get("message", "Failed to read calendar events."),
            "events": [],
            "total_count": 0,
        }

    # Normalize: Composio may return events under various keys
    events = result.get("events", result.get("items", result.get("data", [])))
    if not isinstance(events, list):
        events = [events] if events else []

    return {
        "connected": True,
        "provider": provider,
        "events": events,
        "total_count": len(events),
    }


async def calendar_write_impl(
    user_id: str,
    action: str,
    event: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Write calendar operations (create, update, delete).

    Validates the requested *action* and checks the user's calendar
    integration before executing via Composio.

    Args:
        user_id: The requesting user's ID.
        action: ``"create"``, ``"update"``, or ``"delete"``.
        event: Event data for create/update operations.
        event_id: Event ID for update/delete operations.

    Returns:
        Dict with ``connected``, ``success``, ``provider``, and result data.
    """
    valid_actions = {"create", "update", "delete"}

    logger.info(
        "Calendar write operation: %s for user %s",
        action,
        user_id,
    )

    if action not in valid_actions:
        return {
            "success": False,
            "error": f"Invalid action: {action}. Must be one of {valid_actions}",
        }

    status = await _check_integration_status(user_id, "calendar")

    if not status["connected"]:
        return {
            "connected": False,
            "success": False,
            "message": (
                "Calendar integration not connected. "
                "Connect Google Calendar or Outlook in Settings > Integrations "
                "to enable calendar write operations."
            ),
        }

    provider = status["provider"]
    connection_id = status.get("composio_connection_id")

    if not connection_id:
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": (
                f"Calendar integration detected ({provider}), but the "
                "connection ID is missing. Please reconnect in "
                "Settings > Integrations."
            ),
        }

    provider_actions = _CALENDAR_WRITE_ACTIONS.get(provider)  # type: ignore[arg-type]
    action_slug = provider_actions.get(action) if provider_actions else None
    if not action_slug:
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": f"No calendar {action} action mapped for provider '{provider}'.",
        }

    # Build Composio-compatible params
    composio_params: dict[str, Any] = {}
    if event:
        composio_params.update(event)
    if event_id:
        composio_params["eventId"] = event_id

    result = await _execute_composio_action(connection_id, action_slug, composio_params)

    if result.get("status") in ("not_configured", "error"):
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": result.get("message", f"Failed to {action} calendar event."),
        }

    return {
        "connected": True,
        "success": True,
        "provider": provider,
        "data": result,
    }


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------


async def crm_read_impl(
    user_id: str,
    record_type: str,
    record_id: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read CRM records (leads, contacts, accounts).

    Checks the user's CRM integration status first.  Returns honest
    status messages when the CRM is not connected.

    Args:
        user_id: The requesting user's ID.
        record_type: ``"leads"``, ``"contacts"``, or ``"accounts"``.
        record_id: Optional specific record ID to fetch.
        filters: Optional filters for querying records.

    Returns:
        Dict with ``connected``, ``provider``, ``records``, and
        ``total_count`` keys.
    """
    logger.info(
        "Reading CRM records: %s for user %s",
        record_type,
        user_id,
    )

    status = await _check_integration_status(user_id, "crm")

    if not status["connected"]:
        return {
            "connected": False,
            "message": (
                "CRM integration not connected. "
                "Connect Salesforce or HubSpot in Settings > Integrations "
                "to enable CRM data access."
            ),
            "records": [],
            "total_count": 0,
        }

    provider = status["provider"]
    connection_id = status.get("composio_connection_id")

    if not connection_id:
        return {
            "connected": True,
            "provider": provider,
            "message": (
                f"CRM integration detected ({provider}), but the "
                "connection ID is missing. Please reconnect in "
                "Settings > Integrations."
            ),
            "records": [],
            "total_count": 0,
        }

    provider_actions = _CRM_READ_ACTIONS.get(provider)  # type: ignore[arg-type]
    action_slug = provider_actions.get(record_type) if provider_actions else None
    if not action_slug:
        return {
            "connected": True,
            "provider": provider,
            "message": (
                f"No CRM read action mapped for provider '{provider}' "
                f"and record type '{record_type}'."
            ),
            "records": [],
            "total_count": 0,
        }

    # Build Composio-compatible params
    composio_params: dict[str, Any] = {}
    if provider == "salesforce":
        composio_params["sObjectType"] = _SALESFORCE_SOBJECT_MAP.get(
            record_type, record_type
        )
    if record_id:
        composio_params["record_id"] = record_id
    if filters:
        composio_params.update(filters)

    result = await _execute_composio_action(connection_id, action_slug, composio_params)

    if result.get("status") in ("not_configured", "error"):
        return {
            "connected": True,
            "provider": provider,
            "message": result.get("message", "Failed to read CRM records."),
            "records": [],
            "total_count": 0,
        }

    # Normalize: Composio may return records under various keys
    records = result.get("records", result.get("results", result.get("data", [])))
    if not isinstance(records, list):
        records = [records] if records else []

    return {
        "connected": True,
        "provider": provider,
        "records": records,
        "total_count": len(records),
    }


async def crm_write_impl(
    user_id: str,
    action: str,
    record_type: str,
    record: dict[str, Any] | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """Write CRM operations (create, update, delete).

    Validates the requested *action* and *record_type* and checks the
    user's CRM integration before executing via Composio.

    Args:
        user_id: The requesting user's ID.
        action: ``"create"``, ``"update"``, or ``"delete"``.
        record_type: ``"leads"``, ``"contacts"``, or ``"accounts"``.
        record: Record data for create/update operations.
        record_id: Record ID for update/delete operations.

    Returns:
        Dict with ``connected``, ``success``, ``provider``, and result data.
    """
    valid_actions = {"create", "update", "delete"}
    valid_record_types = {"leads", "contacts", "accounts"}

    logger.info(
        "CRM write operation: %s on %s for user %s",
        action,
        record_type,
        user_id,
    )

    if action not in valid_actions:
        return {
            "success": False,
            "error": f"Invalid action: {action}. Must be one of {valid_actions}",
        }
    if record_type not in valid_record_types:
        return {
            "success": False,
            "error": (
                f"Invalid record_type: {record_type}. "
                f"Must be one of {valid_record_types}"
            ),
        }

    status = await _check_integration_status(user_id, "crm")

    if not status["connected"]:
        return {
            "connected": False,
            "success": False,
            "message": (
                "CRM integration not connected. "
                "Connect Salesforce or HubSpot in Settings > Integrations "
                "to enable CRM write operations."
            ),
        }

    provider = status["provider"]
    connection_id = status.get("composio_connection_id")

    if not connection_id:
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": (
                f"CRM integration detected ({provider}), but the "
                "connection ID is missing. Please reconnect in "
                "Settings > Integrations."
            ),
        }

    provider_actions = _CRM_WRITE_ACTIONS.get(provider)  # type: ignore[arg-type]
    action_slug = None
    if provider_actions:
        action_map = provider_actions.get(action)
        if action_map:
            action_slug = action_map.get(record_type)

    if not action_slug:
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": (
                f"No CRM {action} action mapped for provider '{provider}' "
                f"and record type '{record_type}'."
            ),
        }

    # Build Composio-compatible params
    composio_params: dict[str, Any] = {}
    if provider == "salesforce":
        composio_params["sObjectType"] = _SALESFORCE_SOBJECT_MAP.get(
            record_type, record_type
        )
    if record:
        composio_params.update(record)
    if record_id:
        composio_params["record_id"] = record_id

    result = await _execute_composio_action(connection_id, action_slug, composio_params)

    if result.get("status") in ("not_configured", "error"):
        return {
            "connected": True,
            "success": False,
            "provider": provider,
            "message": result.get(
                "message",
                f"Failed to {action} CRM {record_type} record.",
            ),
        }

    return {
        "connected": True,
        "success": True,
        "provider": provider,
        "data": result,
    }


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


async def email_send_impl(
    user_id: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict[str, Any]:
    """Send an email via the user's connected email integration.

    Checks whether the user has a Gmail or Outlook integration connected
    and dispatches the send via the appropriate Composio action slug.

    Args:
        user_id: The requesting user's ID.
        to: Recipient email address.
        subject: Email subject line.
        body: Email body (plain text or HTML depending on provider).
        cc: Optional CC recipient email address.

    Returns:
        Dict with ``sent``, ``provider``, and ``message`` keys.
    """
    logger.info(
        "Sending email for user %s to %s",
        user_id,
        to,
    )

    status = await _check_integration_status(user_id, "email")

    if not status["connected"]:
        return {
            "sent": False,
            "message": (
                "Email integration not connected. "
                "Connect Gmail or Outlook in Settings > Integrations "
                "to enable email sending."
            ),
        }

    provider = status["provider"]
    connection_id = status.get("composio_connection_id")

    if not connection_id:
        return {
            "sent": False,
            "provider": provider,
            "message": (
                f"Email integration detected ({provider}), but the "
                "connection ID is missing. Please reconnect in "
                "Settings > Integrations."
            ),
        }

    action_slug = _EMAIL_SEND_ACTIONS.get(provider)  # type: ignore[arg-type]
    if not action_slug:
        return {
            "sent": False,
            "provider": provider,
            "message": f"No email send action mapped for provider '{provider}'.",
        }

    composio_params: dict[str, Any] = {
        "to": to,
        "subject": subject,
        "body": body,
    }
    if cc:
        composio_params["cc"] = cc

    result = await _execute_composio_action(connection_id, action_slug, composio_params)

    if result.get("status") in ("not_configured", "error"):
        return {
            "sent": False,
            "provider": provider,
            "message": result.get("message", "Failed to send email."),
        }

    return {
        "sent": True,
        "provider": provider,
        "message": f"Email sent successfully via {provider}.",
    }
