"""Integrations API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.integrations.domain import INTEGRATION_CONFIGS, IntegrationType
from src.integrations.oauth import get_oauth_client
from src.integrations.service import SyncStatus, get_integration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# Request/Response Models
class AuthUrlRequest(BaseModel):
    """Request model for generating OAuth URL."""

    redirect_uri: str = Field(..., description="OAuth callback URL")


class AuthUrlResponse(BaseModel):
    """Response model with OAuth authorization URL."""

    authorization_url: str
    integration_type: str
    display_name: str


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""

    code: str = Field(..., description="OAuth authorization code")
    state: str | None = Field(None, description="OAuth state parameter")


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
        )

        logger.info(
            "Integration connected successfully",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
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
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Manually trigger a sync for an integration.

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

        # Update status to pending
        await service.update_sync_status(integration_id, SyncStatus.PENDING)

        # TODO: Implement actual sync logic per integration type
        # For now, mark as success
        integration = await service.update_sync_status(integration_id, SyncStatus.SUCCESS)

        return integration

    except Exception as e:
        logger.exception("Error syncing integration")
        await service.update_sync_status(
            integration_id,
            SyncStatus.FAILED,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync integration",
        ) from e
