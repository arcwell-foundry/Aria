"""Composio resilience wrapper with auth-failure failover.

Wraps ``ComposioOAuthClient.execute_action`` /
``execute_action_sync`` to detect authentication errors
(401 / token-expired) and automatically try alternative
Composio connections for the same user+integration_type.

On successful failover the ``composio_connection_id`` in
``user_integrations`` is hot-swapped. When all connections
fail the row is marked ``sync_status='failed'`` and the
user receives a WebSocket notification so the frontend can
display a reconnection banner.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient
from src.integrations.oauth import ComposioOAuthClient, get_oauth_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ComposioAuthError(Exception):
    """Raised when all Composio connections fail with auth errors."""

    def __init__(
        self,
        message: str,
        *,
        user_id: str,
        integration_type: str,
    ) -> None:
        super().__init__(message)
        self.user_id = user_id
        self.integration_type = integration_type


# ---------------------------------------------------------------------------
# Auth-error detection
# ---------------------------------------------------------------------------

_AUTH_ERROR_KEYWORDS = frozenset({
    "unauthorized",
    "token expired",
    "invalid_grant",
    "invalid_token",
    "token has been expired",
    "token is expired",
    "access token expired",
    "refresh token expired",
    "authentication failed",
    "oauth token",
    "compacttoken parsing failed",
    "errorcode: 700003",
})


def _is_auth_error(
    result: dict[str, Any] | None = None,
    exc: Exception | None = None,
) -> bool:
    """Return True if the failure is an authentication / token error.

    Auth errors indicate user-specific credential problems (expired
    token, revoked consent). They are NOT counted against the circuit
    breaker because they are user-scoped, not service-wide.

    Network errors, timeouts, and rate-limit errors return False so
    the existing circuit breaker can handle them.
    """
    haystack = ""

    if result is not None:
        # Composio wraps provider errors: result["data"]["statusCode"]
        data = result.get("data") or {}
        if isinstance(data, dict):
            status_code = data.get("statusCode") or data.get("status_code")
            if status_code == 401:
                return True

        # Also check the top-level error string
        error_str = str(result.get("error", ""))
        haystack += error_str.lower()

    if exc is not None:
        haystack += str(exc).lower()
        # Check for HTTP 401 in exception message
        if "401" in str(exc) and ("unauthorized" in str(exc).lower() or "auth" in str(exc).lower()):
            return True

    if not haystack:
        return False

    return any(kw in haystack for kw in _AUTH_ERROR_KEYWORDS)


# ---------------------------------------------------------------------------
# Alternative connection discovery
# ---------------------------------------------------------------------------

# Map integration_type to Composio toolkit_slug
_TOOLKIT_SLUG_MAP: dict[str, str] = {
    "outlook": "outlook",
    "gmail": "gmail",
    "google_calendar": "googlecalendar",
    "salesforce": "salesforce",
    "hubspot": "hubspot",
    "slack": "slack",
}


async def _find_alternative_connections(
    oauth_client: ComposioOAuthClient,
    failed_connection_id: str,
    integration_type: str,
) -> list[str]:
    """Query Composio for other ACTIVE connections of the same type.

    Returns connection IDs that are ACTIVE and differ from the failed
    one. Returns an empty list when no alternatives exist.
    """
    toolkit_slug = _TOOLKIT_SLUG_MAP.get(integration_type.lower(), integration_type.lower())

    try:
        def _list_accounts() -> Any:
            return oauth_client._client.client.connected_accounts.list(
                toolkit_slug=toolkit_slug,
            )

        result = await asyncio.to_thread(_list_accounts)
        items = getattr(result, "items", result) if not isinstance(result, list) else result

        alternatives: list[str] = []
        for item in items:
            conn_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
            status = str(getattr(item, "status", None) or (item.get("status", "") if isinstance(item, dict) else "")).upper()
            if conn_id and conn_id != failed_connection_id and status == "ACTIVE":
                alternatives.append(conn_id)

        logger.info(
            "Found %d alternative Composio connections for %s (excluding %s)",
            len(alternatives),
            toolkit_slug,
            failed_connection_id,
        )
        return alternatives

    except Exception as e:
        logger.warning(
            "Failed to list alternative Composio connections for %s: %s",
            toolkit_slug,
            e,
        )
        return []


def _find_alternative_connections_sync(
    oauth_client: ComposioOAuthClient,
    failed_connection_id: str,
    integration_type: str,
) -> list[str]:
    """Synchronous variant of ``_find_alternative_connections``."""
    toolkit_slug = _TOOLKIT_SLUG_MAP.get(integration_type.lower(), integration_type.lower())

    try:
        result = oauth_client._client.client.connected_accounts.list(
            toolkit_slug=toolkit_slug,
        )
        items = getattr(result, "items", result) if not isinstance(result, list) else result

        alternatives: list[str] = []
        for item in items:
            conn_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
            status = str(getattr(item, "status", None) or (item.get("status", "") if isinstance(item, dict) else "")).upper()
            if conn_id and conn_id != failed_connection_id and status == "ACTIVE":
                alternatives.append(conn_id)

        logger.info(
            "Found %d alternative Composio connections (sync) for %s (excluding %s)",
            len(alternatives),
            toolkit_slug,
            failed_connection_id,
        )
        return alternatives

    except Exception as e:
        logger.warning(
            "Failed to list alternative Composio connections (sync) for %s: %s",
            toolkit_slug,
            e,
        )
        return []


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _update_connection_id(
    integration_id: str,
    new_connection_id: str,
) -> None:
    """Hot-swap the connection_id in user_integrations."""
    try:
        db = SupabaseClient.get_client()
        db.table("user_integrations").update({
            "composio_connection_id": new_connection_id,
            "last_sync_at": datetime.now(UTC).isoformat(),
            "sync_status": "success",
            "error_message": None,
        }).eq("id", integration_id).execute()
    except Exception as e:
        logger.error("Failed to update connection_id for integration %s: %s", integration_id, e)


def _mark_sync_failed(
    integration_id: str,
    error_message: str,
) -> None:
    """Set sync_status='failed' on a user_integration row."""
    try:
        db = SupabaseClient.get_client()
        db.table("user_integrations").update({
            "sync_status": "failed",
            "error_message": error_message,
        }).eq("id", integration_id).execute()
    except Exception as e:
        logger.error("Failed to mark sync failed for integration %s: %s", integration_id, e)


def _touch_last_sync(integration_id: str) -> None:
    """Update last_sync_at on a successful call."""
    try:
        db = SupabaseClient.get_client()
        db.table("user_integrations").update({
            "last_sync_at": datetime.now(UTC).isoformat(),
        }).eq("id", integration_id).execute()
    except Exception as e:
        logger.debug("Failed to touch last_sync_at for integration %s: %s", integration_id, e)


async def _notify_auth_failure(user_id: str, integration_type: str) -> None:
    """Send a WebSocket signal to the user about the auth failure."""
    try:
        from src.core.ws import ws_manager
        from src.models.ws_events import SignalEvent

        event = SignalEvent(
            signal_type="integration_auth_failed",
            title=f"Your {integration_type.title()} connection needs attention",
            severity="high",
            data={
                "integration_type": integration_type,
                "action": "reconnect",
            },
        )
        await ws_manager.send_to_user(user_id, event)
    except Exception as e:
        logger.debug("Failed to send auth failure WS notification: %s", e)


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------

async def execute_with_refresh(
    *,
    user_id: str,
    integration_id: str,
    connection_id: str,
    integration_type: str,
    action: str,
    params: dict[str, Any],
    oauth_client: ComposioOAuthClient | None = None,
) -> dict[str, Any]:
    """Execute a Composio action with automatic auth-failure failover.

    1. Try the primary connection.
    2. On auth error, find alternative Composio connections for the
       same user+integration_type.
    3. Try each alternative — on first success, hot-swap the
       connection_id in ``user_integrations`` and return the result.
    4. If all fail, mark ``sync_status='failed'``, send a WS signal,
       and raise ``ComposioAuthError``.
    5. Non-auth errors are re-raised as-is (circuit breaker handles them).

    Args:
        user_id: The user's ID.
        integration_id: The user_integrations row ID.
        connection_id: The primary Composio connection nanoid.
        integration_type: e.g. 'outlook', 'gmail'.
        action: Composio tool slug.
        params: Action parameters.
        oauth_client: Optional pre-built client (uses singleton if None).

    Returns:
        The Composio action result dict.

    Raises:
        ComposioAuthError: When all connections fail with auth errors.
        Exception: Non-auth errors are re-raised unchanged.
    """
    if oauth_client is None:
        oauth_client = get_oauth_client()

    # --- Attempt primary connection ---
    try:
        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
            user_id=user_id,
        )
    except Exception as exc:
        if not _is_auth_error(exc=exc):
            raise
        # Auth error from exception — fall through to failover
        result = None
        logger.warning(
            "Auth error (exception) on primary connection %s for user %s action %s: %s",
            connection_id, user_id, action, exc,
        )
    else:
        # Check if the result itself indicates auth failure
        if result.get("successful") or not _is_auth_error(result=result):
            # Success or non-auth error — return as-is
            # Fire-and-forget last_sync_at update on success
            if result.get("successful"):
                asyncio.create_task(asyncio.to_thread(_touch_last_sync, integration_id))
            return result
        logger.warning(
            "Auth error (result) on primary connection %s for user %s action %s: %s",
            connection_id, user_id, action, result.get("error"),
        )

    # --- Failover: try alternative connections ---
    alternatives = await _find_alternative_connections(
        oauth_client, connection_id, integration_type,
    )

    for alt_id in alternatives:
        try:
            alt_result = await oauth_client.execute_action(
                connection_id=alt_id,
                action=action,
                params=params,
                user_id=user_id,
            )
        except Exception as alt_exc:
            logger.debug(
                "Alternative connection %s also failed: %s", alt_id, alt_exc,
            )
            continue

        if alt_result.get("successful"):
            logger.info(
                "Failover succeeded: swapping connection %s → %s for integration %s",
                connection_id, alt_id, integration_id,
            )
            # Hot-swap in DB (fire-and-forget)
            asyncio.create_task(
                asyncio.to_thread(_update_connection_id, integration_id, alt_id)
            )
            return alt_result

        if _is_auth_error(result=alt_result):
            logger.debug(
                "Alternative connection %s auth error: %s",
                alt_id, alt_result.get("error"),
            )
            continue

        # Non-auth error from alternative — return it (caller handles)
        return alt_result

    # --- All connections exhausted ---
    error_msg = (
        f"All Composio connections failed for {integration_type} "
        f"(user {user_id}, action {action}). Re-authorization required."
    )
    logger.error(error_msg)
    _mark_sync_failed(integration_id, error_msg)
    await _notify_auth_failure(user_id, integration_type)

    raise ComposioAuthError(
        error_msg,
        user_id=user_id,
        integration_type=integration_type,
    )


# ---------------------------------------------------------------------------
# Sync wrapper
# ---------------------------------------------------------------------------

def execute_with_refresh_sync(
    *,
    user_id: str,
    integration_id: str,
    connection_id: str,
    integration_type: str,
    action: str,
    params: dict[str, Any],
    oauth_client: ComposioOAuthClient | None = None,
) -> dict[str, Any]:
    """Synchronous variant of ``execute_with_refresh``.

    Used by ``email_bootstrap.py`` and ``autonomous_draft_engine.py``
    which call ``execute_action_sync`` inside async functions.

    Args:
        user_id: The user's ID.
        integration_id: The user_integrations row ID.
        connection_id: The primary Composio connection nanoid.
        integration_type: e.g. 'outlook', 'gmail'.
        action: Composio tool slug.
        params: Action parameters.
        oauth_client: Optional pre-built client (uses singleton if None).

    Returns:
        The Composio action result dict.

    Raises:
        ComposioAuthError: When all connections fail with auth errors.
        Exception: Non-auth errors are re-raised unchanged.
    """
    if oauth_client is None:
        oauth_client = get_oauth_client()

    # --- Attempt primary connection ---
    try:
        result = oauth_client.execute_action_sync(
            connection_id=connection_id,
            action=action,
            params=params,
            user_id=user_id,
        )
    except Exception as exc:
        if not _is_auth_error(exc=exc):
            raise
        result = None
        logger.warning(
            "Auth error (exception, sync) on primary connection %s for user %s action %s: %s",
            connection_id, user_id, action, exc,
        )
    else:
        if result.get("successful") or not _is_auth_error(result=result):
            if result.get("successful"):
                _touch_last_sync(integration_id)
            return result
        logger.warning(
            "Auth error (result, sync) on primary connection %s for user %s action %s: %s",
            connection_id, user_id, action, result.get("error"),
        )

    # --- Failover ---
    alternatives = _find_alternative_connections_sync(
        oauth_client, connection_id, integration_type,
    )

    for alt_id in alternatives:
        try:
            alt_result = oauth_client.execute_action_sync(
                connection_id=alt_id,
                action=action,
                params=params,
                user_id=user_id,
            )
        except Exception as alt_exc:
            logger.debug(
                "Alternative connection (sync) %s also failed: %s", alt_id, alt_exc,
            )
            continue

        if alt_result.get("successful"):
            logger.info(
                "Failover succeeded (sync): swapping connection %s → %s for integration %s",
                connection_id, alt_id, integration_id,
            )
            _update_connection_id(integration_id, alt_id)
            return alt_result

        if _is_auth_error(result=alt_result):
            logger.debug(
                "Alternative connection (sync) %s auth error: %s",
                alt_id, alt_result.get("error"),
            )
            continue

        return alt_result

    # --- All connections exhausted ---
    error_msg = (
        f"All Composio connections failed (sync) for {integration_type} "
        f"(user {user_id}, action {action}). Re-authorization required."
    )
    logger.error(error_msg)
    _mark_sync_failed(integration_id, error_msg)

    # Can't send WS notification from sync context — caller should handle

    raise ComposioAuthError(
        error_msg,
        user_id=user_id,
        integration_type=integration_type,
    )
