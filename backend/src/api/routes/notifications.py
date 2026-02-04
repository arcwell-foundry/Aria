"""Notification API routes for ARIA."""

import logging

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from src.api.deps import get_current_user
from src.models.notification import (
    MarkReadRequest,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100, description="Max notifications to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    unread_only: bool = Query(False, description="Only return unread"),
    current_user: dict = Depends(get_current_user),
) -> NotificationListResponse:
    """List notifications for the current user.

    Returns paginated list of notifications ordered by creation date (newest first).
    Includes total count and unread count.
    """
    user_id = current_user["id"]
    return await NotificationService.get_notifications(
        user_id=user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread/count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
) -> UnreadCountResponse:
    """Get the count of unread notifications."""
    user_id = current_user["id"]
    return await NotificationService.get_unread_count(user_id=user_id)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
) -> NotificationResponse:
    """Mark a single notification as read."""
    user_id = current_user["id"]
    return await NotificationService.mark_as_read(notification_id=notification_id, user_id=user_id)


@router.put("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Mark all notifications as read for the current user."""
    user_id = current_user["id"]
    count = await NotificationService.mark_all_as_read(user_id=user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Marked {count} notifications as read", "count": count},
    )


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete a notification."""
    user_id = current_user["id"]
    await NotificationService.delete_notification(notification_id=notification_id, user_id=user_id)
