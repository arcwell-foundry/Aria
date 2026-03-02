"""Integrations API routes."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.integrations.connection_registry import get_connection_registry
from src.integrations.domain import INTEGRATION_CONFIGS, IntegrationType
from src.integrations.oauth import get_oauth_client
from src.integrations.service import get_integration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# Request/Response Models
class AuthUrlRequest(BaseModel):
    """Request model for generating OAuth URL."""

    redirect_uri: str = Field(..., min_length=10, max_length=500, description="OAuth callback URL")


class AuthUrlResponse(BaseModel):
    """Response model with OAuth authorization URL."""

    authorization_url: str
    integration_type: str
    display_name: str


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""

    code: str = Field(..., min_length=10, max_length=500, description="OAuth authorization code")
    state: str | None = Field(None, max_length=100, description="OAuth state parameter")


class IntegrationResponse(BaseModel):
    """Response model for integration data."""

    id: str
    integration_type: str
    display_name: str | None = None
    status: str
    last_sync_at: str | None = None
    sync_status: str
    error_message: str | None = None
    created_at: str | None = None


class AvailableIntegrationResponse(BaseModel):
    """Response model for available integrations."""

    integration_type: str
    display_name: str
    description: str
    icon: str
    is_connected: bool
    status: str | None = None


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List all integrations for the current user.

    Args:
        current_user: The authenticated user

    Returns:
        List of user's integrations
    """
    try:
        service = get_integration_service()
        integrations = await service.get_user_integrations(current_user.id)
        return integrations

    except Exception as e:
        logger.exception("Error fetching integrations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch integrations",
        ) from e


@router.get("/available", response_model=list[AvailableIntegrationResponse])
async def list_available_integrations(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List all available integrations with connection status.

    Args:
        current_user: The authenticated user

    Returns:
        List of available integrations with connection status
    """
    try:
        service = get_integration_service()
        available = await service.get_available_integrations(current_user.id)
        return available

    except Exception as e:
        logger.exception("Error fetching available integrations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch available integrations",
        ) from e


@router.post("/{integration_type}/auth-url", response_model=AuthUrlResponse)
async def get_auth_url(
    integration_type: str,
    request: AuthUrlRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate OAuth authorization URL for an integration.

    Args:
        integration_type: Type of integration to connect
        request: Auth URL request with redirect URI
        current_user: The authenticated user

    Returns:
        Authorization URL and metadata

    Raises:
        HTTPException: If integration type is invalid or request fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            ) from e

        config = INTEGRATION_CONFIGS.get(integration_type_enum)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No configuration for integration type: {integration_type}",
            )

        # Generate auth URL
        oauth_client = get_oauth_client()
        auth_url = await oauth_client.generate_auth_url(
            user_id=current_user.id,
            integration_type=integration_type_enum,
            redirect_uri=request.redirect_uri,
        )

        return {
            "authorization_url": auth_url,
            "integration_type": integration_type,
            "display_name": config.display_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating auth URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        ) from e


@router.post("/{integration_type}/auth-url-popup", response_model=AuthUrlResponse)
async def get_auth_url_popup(
    integration_type: str,
    current_user: CurrentUser,
    request: Request,
) -> dict[str, Any]:
    """Generate OAuth URL for popup-based connection flow.

    Unlike the standard auth-url endpoint, this uses the backend's own
    ``/oauth/callback`` as the redirect URI so the popup can close itself
    via ``postMessage`` after OAuth completes.

    Args:
        integration_type: Type of integration to connect.
        current_user: The authenticated user.
        request: FastAPI request (used to derive the server's base URL).

    Returns:
        Authorization URL and metadata.
    """
    try:
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            ) from e

        config = INTEGRATION_CONFIGS.get(integration_type_enum)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No configuration for integration type: {integration_type}",
            )

        # Build callback URL pointing to our own server
        base_url = str(request.base_url).rstrip("/")
        callback_url = (
            f"{base_url}/api/v1/integrations/oauth/callback"
            f"?integration_type={integration_type}"
        )

        oauth_client = get_oauth_client()
        auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
            user_id=current_user.id,
            integration_type=integration_type_enum,
            redirect_uri=callback_url,
        )

        # Create pending connection row
        registry = get_connection_registry()
        await registry.register_connection(
            user_id=str(current_user.id),
            toolkit_slug=integration_type,
            composio_connection_id=connection_id,
            status="pending",
        )

        return {
            "authorization_url": auth_url,
            "integration_type": integration_type,
            "display_name": config.display_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating popup auth URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        ) from e


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    connected_account_id: str = Query("", alias="connected_account_id"),
    integration_type: str = Query("", alias="integration_type"),
) -> HTMLResponse:
    """OAuth callback for popup flow — returns HTML that posts a message and closes.

    No JWT required — the browser is redirected here by the OAuth provider.
    We identify the user from the pending ``user_connections`` row.

    Args:
        connected_account_id: Composio connection ID from the OAuth redirect.
        integration_type: The integration type (passed via our callback URL).
    """
    # Fallback error HTML
    def _error_html(msg: str) -> HTMLResponse:
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html><head><title>Connection Failed</title></head>
<body style="font-family:sans-serif;text-align:center;padding:40px">
<h2>Connection Failed</h2><p>{msg}</p>
<script>
  window.opener && window.opener.postMessage({{type:'aria_oauth_error',error:'{msg}'}}, '*');
  setTimeout(function(){{ window.close(); }}, 3000);
</script>
</body></html>""",
            status_code=200,
        )

    if not connected_account_id:
        return _error_html("Missing connected_account_id parameter")

    try:
        # Look up the pending connection row
        registry = get_connection_registry()
        pending = await registry.lookup_by_composio_connection_id(connected_account_id)

        if not pending:
            return _error_html("No pending connection found")

        user_id = pending["user_id"]

        # Verify the row was created recently (10-minute window)
        created_at = pending.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                created_dt = created_at
            if datetime.now(UTC) - created_dt > timedelta(minutes=10):
                return _error_html("Connection request expired")

        # Exchange with Composio to verify ACTIVE status
        oauth_client = get_oauth_client()
        toolkit_slug = integration_type or pending.get("toolkit_slug", "")
        connection_data = await oauth_client.exchange_code_for_connection(
            user_id=str(user_id),
            code=connected_account_id,
            integration_type=toolkit_slug,
        )

        account_email = connection_data.get("account_email", "")
        display_name = account_email or toolkit_slug

        config = INTEGRATION_CONFIGS.get(IntegrationType(toolkit_slug)) if toolkit_slug else None
        if config:
            display_name = config.display_name

        # Activate the connection in the registry (includes dual-write)
        await registry.register_connection(
            user_id=str(user_id),
            toolkit_slug=toolkit_slug,
            composio_connection_id=connected_account_id,
            account_email=account_email,
            display_name=display_name,
            status="active",
        )

        # Send WebSocket event
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_integration_connected(
                user_id=str(user_id),
                toolkit_slug=toolkit_slug,
                status="active",
                display_name=display_name,
                account_email=account_email,
            )
        except Exception:
            logger.warning("Failed to send WS integration.connected event", exc_info=True)

        # Trigger email bootstrap for email integrations
        if toolkit_slug in ("gmail", "outlook"):
            try:
                from src.onboarding.email_bootstrap import PriorityEmailIngestion

                bootstrap = PriorityEmailIngestion()
                asyncio.create_task(bootstrap.run_bootstrap(str(user_id)))
                logger.info("Email bootstrap triggered after popup OAuth for %s", toolkit_slug)
            except Exception:
                logger.warning("Failed to trigger email bootstrap after popup OAuth", exc_info=True)

        # Return HTML that signals the opener and closes the popup
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html><head><title>Connected</title></head>
<body style="font-family:sans-serif;text-align:center;padding:40px">
<h2>Connected!</h2>
<p>You can close this window.</p>
<script>
  window.opener && window.opener.postMessage({{
    type: 'aria_oauth_success',
    toolkit_slug: '{toolkit_slug}',
    status: 'active',
    display_name: '{display_name}',
    account_email: '{account_email}'
  }}, '*');
  setTimeout(function(){{ window.close(); }}, 1500);
</script>
</body></html>""",
            status_code=200,
        )

    except Exception as e:
        logger.exception("OAuth callback error")
        return _error_html(f"An error occurred: {str(e)[:100]}")


@router.post(
    "/{integration_type}/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_integration(
    integration_type: str,
    request: OAuthCallbackRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Complete OAuth connection and create integration.

    Args:
        integration_type: Type of integration being connected
        request: OAuth callback request with auth code
        current_user: The authenticated user

    Returns:
        Created integration details

    Raises:
        HTTPException: If connection fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            ) from e

        # Exchange code for connection
        oauth_client = get_oauth_client()
        connection_data = await oauth_client.exchange_code_for_connection(
            user_id=current_user.id,
            code=request.code,
            integration_type=integration_type_enum,
        )

        # Create integration record
        service = get_integration_service()
        integration = await service.create_integration(
            user_id=current_user.id,
            integration_type=integration_type_enum,
            composio_connection_id=connection_data.get("connection_id", ""),
            composio_account_id=connection_data.get("account_id"),
            display_name=connection_data.get("account_email"),
            account_email=connection_data.get("account_email"),
        )

        logger.info(
            "Integration connected successfully",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
        )

        # Dual-write to user_connections registry (non-fatal)
        try:
            registry = get_connection_registry()
            await registry.register_connection(
                user_id=str(current_user.id),
                toolkit_slug=integration_type,
                composio_connection_id=connection_data.get("connection_id", ""),
                account_email=connection_data.get("account_email"),
                display_name=connection_data.get("account_email"),
                status="active",
            )
        except Exception:
            logger.warning("Registry dual-write failed (non-fatal)", exc_info=True)

        # Trigger email bootstrap for email integrations (Gmail/Outlook)
        if integration_type in ("gmail", "outlook"):
            try:
                from src.onboarding.email_bootstrap import PriorityEmailIngestion

                bootstrap = PriorityEmailIngestion()
                asyncio.create_task(bootstrap.run_bootstrap(str(current_user.id)))
                logger.info(
                    "Email bootstrap triggered for user %s after %s connection",
                    current_user.id,
                    integration_type,
                )
            except Exception as e:
                logger.warning(
                    "Failed to trigger email bootstrap for user %s: %s",
                    current_user.id,
                    e,
                )

        return integration

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error connecting integration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect integration",
        ) from e


@router.post("/{integration_type}/disconnect", response_model=MessageResponse)
async def disconnect_integration(
    integration_type: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Disconnect an integration.

    Args:
        integration_type: Type of integration to disconnect
        current_user: The authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If disconnection fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            ) from e

        service = get_integration_service()
        await service.disconnect_integration(current_user.id, integration_type_enum)

        # Dual-write to user_connections registry (non-fatal)
        try:
            registry = get_connection_registry()
            await registry.disconnect(str(current_user.id), integration_type)
        except Exception:
            logger.warning("Registry disconnect dual-write failed (non-fatal)", exc_info=True)

        logger.info(
            "Integration disconnected successfully",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
        )

        return {
            "message": f"Successfully disconnected {integration_type.replace('_', ' ').title()}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error disconnecting integration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect integration",
        ) from e


@router.post("/{integration_id}/sync", response_model=IntegrationResponse)
async def sync_integration(
    integration_id: str,
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, Any]:
    """Manually trigger a sync for an integration.

    Delegates to ``IntegrationService.trigger_sync`` which routes to the
    appropriate DeepSyncService method based on integration type.

    Args:
        integration_id: Integration record ID
        current_user: The authenticated user

    Returns:
        Updated integration details

    Raises:
        HTTPException: If sync fails
    """
    try:
        service = get_integration_service()
        integration = await service.trigger_sync(integration_id)
        return integration

    except Exception as e:
        logger.exception("Error syncing integration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync integration",
        ) from e


@router.post("/debug/trigger-email-bootstrap", response_model=MessageResponse)
async def trigger_email_bootstrap(
    current_user: CurrentUser,
) -> dict[str, str]:
    """Manually trigger email bootstrap for the current user.

    Launches PriorityEmailIngestion.run_bootstrap() as a background task.
    Requires an active email integration (Gmail or Outlook).

    Args:
        current_user: The authenticated user.

    Returns:
        Status message.

    Raises:
        HTTPException: If no email integration found.
    """
    try:
        from src.services.email_tools import get_email_integration

        integration = await get_email_integration(str(current_user.id))
        if not integration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active email integration found. Connect Gmail or Outlook first.",
            )

        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        bootstrap = PriorityEmailIngestion()
        asyncio.create_task(bootstrap.run_bootstrap(str(current_user.id)))

        logger.info(
            "Email bootstrap manually triggered for user %s (provider: %s)",
            current_user.id,
            integration.get("integration_type"),
        )

        return {
            "message": (
                f"Email bootstrap started for {integration.get('integration_type', 'email')}. "
                "Processing runs in the background. Check logs for EMAIL_BOOTSTRAP messages."
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error triggering email bootstrap")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger email bootstrap: {str(e)}",
        ) from e


# ---------------------------------------------------------------------------
# Composio webhook handler (Phase 4C)
# ---------------------------------------------------------------------------


@router.post("/webhooks/composio/connections")
async def composio_connection_webhook(request: Request) -> dict[str, str]:
    """Handle Composio webhook for connection events.

    Composio sends this when:
    - A new connection is created for an ARIA entity
    - A connection is updated (token refresh)
    - A connection is deleted

    Belt-and-suspenders sync alongside the OAuth callback.
    No JWT required — authenticated by Composio webhook signature.
    """
    try:
        payload = await request.json()
        event_type = payload.get("event", "")
        connection_data = payload.get("data", {})

        entity_id = connection_data.get("entity_id", "")
        connection_id = connection_data.get("connection_id", "")
        toolkit = connection_data.get("app_name", "").lower()
        webhook_status = connection_data.get("status", "")

        # Resolve entity_id back to ARIA user_id
        user_id = await _resolve_entity_to_user(entity_id)
        if not user_id:
            logger.warning("Composio webhook: Unknown entity %s", entity_id)
            return {"status": "ignored", "reason": "unknown entity"}

        registry = get_connection_registry()

        if event_type in ("connection.created", "connection.updated"):
            if webhook_status == "active":
                await registry.register_connection(
                    user_id=user_id,
                    toolkit_slug=toolkit,
                    composio_connection_id=connection_id,
                    composio_entity_id=entity_id,
                    status="active",
                    metadata={
                        "synced_via": "composio_webhook",
                        "event_type": event_type,
                    },
                )
                # Notify user if online
                try:
                    from src.core.ws import ws_manager

                    await ws_manager.send_to_user(user_id, {
                        "type": "integration_connected",
                        "toolkit_slug": toolkit,
                        "status": "active",
                    })
                except Exception:
                    pass

        elif event_type == "connection.deleted":
            await registry.disconnect(user_id, toolkit)

        logger.info(
            "Composio webhook processed: event=%s toolkit=%s user=%s",
            event_type, toolkit, user_id,
        )
        return {"status": "ok"}

    except Exception as e:
        logger.error("Composio webhook error: %s", e)
        return {"status": "error", "reason": str(e)[:200]}


async def _resolve_entity_to_user(entity_id: str) -> str | None:
    """Resolve a Composio entity ID back to an ARIA user UUID.

    Entity format: aria_user_{uuid_prefix}
    Looks up user_connections for the mapping.
    """
    if not entity_id or not entity_id.startswith("aria_user_"):
        return None

    prefix = entity_id[len("aria_user_"):]
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()

        # Search by entity_id in user_connections
        result = (
            client.table("user_connections")
            .select("user_id")
            .eq("composio_entity_id", entity_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data["user_id"]

        # Fallback: search user_profiles by ID prefix
        result = (
            client.table("user_profiles")
            .select("id")
            .like("id", f"{prefix}%")
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data["id"] if result.data else None
    except Exception:
        logger.warning("Failed to resolve entity %s to user", entity_id, exc_info=True)
        return None
