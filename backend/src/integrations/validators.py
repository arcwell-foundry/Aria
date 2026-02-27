"""
Centralized integration status validation.

ALL code that needs to know "is this integration working?" MUST use these functions.
Do NOT query user_integrations directly and check row existence.
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class IntegrationHealth(str, Enum):
    """Assessment of an integration's operational health.

    This goes beyond the stored DB status (IntegrationStatus) to include
    derived states like STALE and NOT_FOUND.
    """

    ACTIVE = "active"  # Connected and recently synced
    STALE = "stale"  # Connected but hasn't synced in 24h+
    DISCONNECTED = "disconnected"  # Row exists but not active
    NOT_FOUND = "not_found"  # No row at all
    ERROR = "error"  # Row exists but in error state


def _not_found_result(integration_type: str) -> dict[str, Any]:
    return {
        "healthy": False,
        "status": IntegrationHealth.NOT_FOUND.value,
        "provider": None,
        "account_email": None,
        "last_sync_at": None,
        "error_message": None,
        "detail": f"No {integration_type} integration found. Please connect in Settings.",
    }


async def check_integration_health(
    user_id: str,
    integration_type: str,
    max_stale_hours: int = 24,
) -> dict[str, Any]:
    """Single source of truth for integration status.

    Queries the user_integrations table and returns a rich health assessment
    that accounts for status, sync state, and staleness.

    Args:
        user_id: The user's ID.
        integration_type: e.g. "gmail", "outlook", "google_calendar".
        max_stale_hours: Hours after which a connected integration is considered stale.

    Returns:
        Dict with keys: healthy, status, provider, account_email,
        last_sync_at, error_message, detail.
    """
    client = SupabaseClient.get_client()

    result = (
        client.table("user_integrations")
        .select("*")
        .eq("user_id", user_id)
        .eq("integration_type", integration_type)
        .execute()
    )

    if not result.data:
        return _not_found_result(integration_type)

    row = result.data[0]
    status = row.get("status", "")
    sync_status = row.get("sync_status", "")
    error_msg = row.get("error_message")
    last_sync = row.get("last_sync_at")
    account_email = row.get("account_email")

    # Not active — row exists but integration is disconnected/pending
    if status != "active":
        return {
            "healthy": False,
            "status": IntegrationHealth.DISCONNECTED.value,
            "provider": integration_type,
            "account_email": account_email,
            "last_sync_at": last_sync,
            "error_message": error_msg,
            "detail": f"{integration_type} is disconnected. Please reconnect in Settings.",
        }

    # Active but last sync failed
    if sync_status == "failed":
        return {
            "healthy": False,
            "status": IntegrationHealth.ERROR.value,
            "provider": integration_type,
            "account_email": account_email,
            "last_sync_at": last_sync,
            "error_message": error_msg,
            "detail": (
                f"{integration_type} is connected but last sync failed. "
                "May need re-authorization."
            ),
        }

    # Active but stale (no recent sync)
    if last_sync:
        try:
            sync_time = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - sync_time > timedelta(hours=max_stale_hours):
                return {
                    "healthy": True,  # Still usable, just stale
                    "status": IntegrationHealth.STALE.value,
                    "provider": integration_type,
                    "account_email": account_email,
                    "last_sync_at": last_sync,
                    "error_message": None,
                    "detail": f"{integration_type} is connected but hasn't synced recently.",
                }
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse last_sync_at for integration",
                extra={"user_id": user_id, "integration_type": integration_type},
            )

    # Fully healthy
    return {
        "healthy": True,
        "status": IntegrationHealth.ACTIVE.value,
        "provider": integration_type,
        "account_email": account_email,
        "last_sync_at": last_sync,
        "error_message": None,
        "detail": f"{integration_type} is connected and working.",
    }


async def get_user_email_integration(user_id: str) -> dict[str, Any]:
    """Check if the user has a working email integration.

    Checks both outlook and gmail, returns the healthy one.
    If neither is healthy, returns the most informative status
    (disconnected > not_found).

    Args:
        user_id: The user's ID.

    Returns:
        Same dict shape as check_integration_health.
    """
    for provider in ("outlook", "gmail"):
        result = await check_integration_health(user_id, provider)
        if result["healthy"]:
            return result

    # Neither is healthy — return the best status for user messaging
    for provider in ("outlook", "gmail"):
        result = await check_integration_health(user_id, provider)
        if result["status"] != IntegrationHealth.NOT_FOUND.value:
            return result  # At least tell them about the disconnected one

    return {
        "healthy": False,
        "status": IntegrationHealth.NOT_FOUND.value,
        "provider": None,
        "account_email": None,
        "last_sync_at": None,
        "error_message": None,
        "detail": "No email integration found. Connect your email in Settings.",
    }
