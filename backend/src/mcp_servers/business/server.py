"""Business Tools MCP Server definition.

Exposes Calendar, CRM, and Email operations as MCP tools backed by
Composio OAuth integrations.  Each tool enforces DCT permissions before
delegating to the standalone implementation functions in ``tools.py``.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.business.tools import (
    calendar_read_impl,
    calendar_write_impl,
    crm_read_impl,
    crm_write_impl,
    email_send_impl,
)
from src.mcp_servers.middleware import enforce_dct

logger = logging.getLogger(__name__)

business_mcp = FastMCP("aria-business")


# ---------------------------------------------------------------------------
# Calendar tools
# ---------------------------------------------------------------------------


@business_mcp.tool()
async def calendar_read(
    user_id: str,
    start_date: str,
    end_date: str | None = None,
    calendar_id: str | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read calendar events within a date range.

    Requires an active Google Calendar or Outlook integration.

    Args:
        user_id: The requesting user's ID.
        start_date: Start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
        calendar_id: Optional calendar identifier.
        dct: Serialized DelegationCapabilityToken for permission checks.

    Returns:
        Dict with connection status, provider, events list, and total count.
    """
    enforce_dct("calendar_read", "read_calendar", dct)
    return await calendar_read_impl(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        calendar_id=calendar_id,
    )


@business_mcp.tool()
async def calendar_write(
    user_id: str,
    action: str,
    event: dict[str, Any] | None = None,
    event_id: str | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write calendar operations (create, update, delete).

    Requires an active Google Calendar or Outlook integration.

    Args:
        user_id: The requesting user's ID.
        action: Operation type - "create", "update", or "delete".
        event: Event data for create/update operations.
        event_id: Event ID for update/delete operations.
        dct: Serialized DelegationCapabilityToken for permission checks.

    Returns:
        Dict with connection status, success flag, provider, and result data.
    """
    enforce_dct("calendar_write", "write_calendar", dct)
    return await calendar_write_impl(
        user_id=user_id,
        action=action,
        event=event,
        event_id=event_id,
    )


# ---------------------------------------------------------------------------
# CRM tools
# ---------------------------------------------------------------------------


@business_mcp.tool()
async def crm_read(
    user_id: str,
    record_type: str,
    record_id: str | None = None,
    filters: dict[str, Any] | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read CRM records (leads, contacts, accounts).

    Requires an active Salesforce or HubSpot integration.

    Args:
        user_id: The requesting user's ID.
        record_type: Type of record - "leads", "contacts", or "accounts".
        record_id: Optional specific record ID to fetch.
        filters: Optional filters for querying records.
        dct: Serialized DelegationCapabilityToken for permission checks.

    Returns:
        Dict with connection status, provider, records list, and total count.
    """
    enforce_dct("crm_read", "read_crm", dct)
    return await crm_read_impl(
        user_id=user_id,
        record_type=record_type,
        record_id=record_id,
        filters=filters,
    )


@business_mcp.tool()
async def crm_write(
    user_id: str,
    action: str,
    record_type: str,
    record: dict[str, Any] | None = None,
    record_id: str | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write CRM operations (create, update, delete).

    Requires an active Salesforce or HubSpot integration.

    Args:
        user_id: The requesting user's ID.
        action: Operation type - "create", "update", or "delete".
        record_type: Type of record - "leads", "contacts", or "accounts".
        record: Record data for create/update operations.
        record_id: Record ID for update/delete operations.
        dct: Serialized DelegationCapabilityToken for permission checks.

    Returns:
        Dict with connection status, success flag, provider, and result data.
    """
    enforce_dct("crm_write", "write_crm", dct)
    return await crm_write_impl(
        user_id=user_id,
        action=action,
        record_type=record_type,
        record=record,
        record_id=record_id,
    )


# ---------------------------------------------------------------------------
# Email tool
# ---------------------------------------------------------------------------


@business_mcp.tool()
async def email_send(
    user_id: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an email via the user's connected email integration.

    Requires an active Gmail or Outlook integration.

    Args:
        user_id: The requesting user's ID.
        to: Recipient email address.
        subject: Email subject line.
        body: Email body content.
        cc: Optional CC recipient email address.
        dct: Serialized DelegationCapabilityToken for permission checks.

    Returns:
        Dict with sent status, provider, and message.
    """
    enforce_dct("email_send", "send_email", dct)
    return await email_send_impl(
        user_id=user_id,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
    )
