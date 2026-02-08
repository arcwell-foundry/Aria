"""Deep sync API routes for US-942 Integration Depth.

This module provides FastAPI routes for manual sync triggers, status queries,
push queue management, and sync configuration.

Key endpoints:
- POST /integrations/sync/{integration_type} - Manual sync trigger
- GET /integrations/sync/status - Get sync status for all integrations
- POST /integrations/sync/queue - Queue a push item for approval
- PUT /integrations/sync/config - Update sync configuration
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import sanitize_error
from src.db.supabase import SupabaseClient
from src.integrations.deep_sync_domain import (
    PushActionType,
    PushPriority,
    SyncConfig,
)
from src.integrations.domain import IntegrationType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/sync", tags=["deep-sync"])


# Request/Response Models
class ManualSyncRequest(BaseModel):
    """Request model for manual sync trigger."""

    integration_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Integration type (salesforce, hubspot, google_calendar, outlook)",
    )


class SyncResultResponse(BaseModel):
    """Response model for sync operation results."""

    direction: str
    integration_type: str
    status: str
    records_processed: int
    records_succeeded: int
    records_failed: int
    memory_entries_created: int
    started_at: str
    completed_at: str | None
    duration_seconds: float | None
    success_rate: float


class SyncStatusResponse(BaseModel):
    """Response model for sync status of an integration."""

    integration_type: str
    last_sync_at: str | None
    last_sync_status: str | None
    next_sync_at: str | None
    sync_count: int


class PushItemRequest(BaseModel):
    """Request model for queuing a push item."""

    integration_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Integration type for the push action",
    )
    action_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Action type (create_note, update_field, create_event)",
    )
    priority: str = Field(
        default="medium",
        min_length=1,
        max_length=20,
        description="Priority level (low, medium, high, critical)",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Action-specific payload data",
    )


class PushItemResponse(BaseModel):
    """Response model for queued push item."""

    queue_id: str
    status: str


class SyncConfigUpdateRequest(BaseModel):
    """Request model for updating sync configuration."""

    sync_interval_minutes: int = Field(
        default=15,
        ge=5,
        le=1440,
        description="Sync interval in minutes (5-1440, default 15)",
    )
    auto_push_enabled: bool = Field(
        default=False,
        description="Enable automatic push of ARIA insights to external systems",
    )


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


@router.post("/{integration_type}", response_model=SyncResultResponse)
async def trigger_manual_sync(
    integration_type: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Trigger a manual sync for the specified integration.

    Validates integration_type and calls the appropriate sync service method
    based on whether it's a CRM or Calendar integration.

    Args:
        integration_type: Type of integration to sync
        current_user: The authenticated user

    Returns:
        SyncResultResponse with sync metrics and status

    Raises:
        HTTPException: 400 for invalid integration_type, 500 for sync failures
    """
    from src.integrations.deep_sync import get_deep_sync_service

    try:
        # Validate integration type
        try:
            integration_enum = IntegrationType(integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            ) from e

        # Get sync service
        service = get_deep_sync_service()

        # Determine sync type based on integration
        crm_types = (IntegrationType.SALESFORCE, IntegrationType.HUBSPOT)
        calendar_types = (IntegrationType.GOOGLE_CALENDAR, IntegrationType.OUTLOOK)

        if integration_enum in crm_types:
            # Perform CRM sync
            result = await service.sync_crm_to_aria(current_user.id, integration_enum)
        elif integration_enum in calendar_types:
            # Perform calendar sync
            result = await service.sync_calendar(current_user.id, integration_enum)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Integration type {integration_type} does not support sync",
            )

        # Format response
        return {
            "direction": result.direction.value,
            "integration_type": result.integration_type.value,
            "status": result.status.value,
            "records_processed": result.records_processed,
            "records_succeeded": result.records_succeeded,
            "records_failed": result.records_failed,
            "memory_entries_created": result.memory_entries_created,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "duration_seconds": result.duration_seconds,
            "success_rate": result.success_rate,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Manual sync failed",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/status", response_model=list[SyncStatusResponse])
async def get_sync_status(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get sync status for all user integrations.

    Queries the integration_sync_state table to retrieve sync status
    for all integrations connected to the user.

    Args:
        current_user: The authenticated user

    Returns:
        List of sync status responses for each integration

    Raises:
        HTTPException: 500 if status retrieval fails
    """
    try:
        client = SupabaseClient.get_client()

        # Get sync state for all user integrations
        response = (
            client.table("integration_sync_state")
            .select("*")
            .eq("user_id", current_user.id)
            .execute()
        )

        sync_states = response.data or []

        # Format response
        status_list = []
        for state in sync_states:
            # Get sync count from logs
            logs_response = (
                client.table("integration_sync_log")
                .select("id", count="exact")  # type: ignore[arg-type]
                .eq("user_id", current_user.id)
                .eq("integration_type", state["integration_type"])
                .execute()
            )

            sync_count = 0
            if logs_response.count is not None:
                sync_count = logs_response.count

            status_list.append(
                {
                    "integration_type": state["integration_type"],
                    "last_sync_at": state.get("last_sync_at"),
                    "last_sync_status": state.get("last_sync_status"),
                    "next_sync_at": state.get("next_sync_at"),
                    "sync_count": sync_count,
                }
            )

        return status_list

    except Exception as e:
        logger.exception(
            "Failed to get sync status",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sync status",
        ) from e


@router.post("/queue", response_model=PushItemResponse, status_code=status.HTTP_201_CREATED)
async def queue_push_item(
    request: PushItemRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Queue a push item for user approval.

    Validates the request and creates a push queue item that will
    require user approval before being pushed to the external system.

    Args:
        request: Push item request with integration_type, action_type, priority, payload
        current_user: The authenticated user

    Returns:
        PushItemResponse with queue_id and status

    Raises:
        HTTPException: 400 for invalid integration_type or action_type, 500 for queue failures
    """
    from src.integrations.deep_sync import get_deep_sync_service

    try:
        # Validate integration type
        try:
            integration_enum = IntegrationType(request.integration_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {request.integration_type}",
            ) from e

        # Validate action type
        try:
            action_enum = PushActionType(request.action_type)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action type: {request.action_type}",
            ) from e

        # Validate priority
        try:
            priority_enum = PushPriority(request.priority)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {request.priority}",
            ) from e

        # Get sync service
        service = get_deep_sync_service()

        # Create push queue item
        from src.integrations.deep_sync_domain import PushQueueItem

        item = PushQueueItem(
            user_id=current_user.id,
            integration_type=integration_enum,
            action_type=action_enum,
            priority=priority_enum,
            payload=request.payload,
        )

        queue_id = await service.queue_push_item(item)

        logger.info(
            "Push item queued successfully",
            extra={
                "user_id": current_user.id,
                "queue_id": queue_id,
                "integration_type": request.integration_type,
                "action_type": request.action_type,
            },
        )

        return {
            "queue_id": queue_id,
            "status": "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to queue push item",
            extra={
                "user_id": current_user.id,
                "integration_type": request.integration_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.put("/config", response_model=MessageResponse)
async def update_sync_config(
    request: SyncConfigUpdateRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Update sync configuration for the user.

    Stores the sync configuration in user_settings.deep_sync_config
    with validation on sync_interval_minutes range.

    Args:
        request: Sync config update request
        current_user: The authenticated user

    Returns:
        MessageResponse confirming the update

    Raises:
        HTTPException: 500 if config update fails
    """
    try:
        client = SupabaseClient.get_client()

        # Create config object
        config = SyncConfig(
            sync_interval_minutes=request.sync_interval_minutes,
            auto_push_enabled=request.auto_push_enabled,
        )

        # Update user settings
        client.table("user_settings").update(
            {
                "deep_sync_config": {
                    "sync_interval_minutes": config.sync_interval_minutes,
                    "auto_push_enabled": config.auto_push_enabled,
                    "push_requires_approval": True,  # Always require approval for now
                    "conflict_resolution": "crm_wins_structured",
                    "max_retries": 3,
                    "retry_backoff_seconds": 60,
                },
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("user_id", current_user.id).execute()

        logger.info(
            "Sync config updated successfully",
            extra={
                "user_id": current_user.id,
                "sync_interval_minutes": request.sync_interval_minutes,
                "auto_push_enabled": request.auto_push_enabled,
            },
        )

        return {
            "message": "Sync configuration updated successfully",
        }

    except Exception as e:
        logger.exception(
            "Failed to update sync config",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e
