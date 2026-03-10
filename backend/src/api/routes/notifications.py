"""Notification API routes for ARIA."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.models.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Max notifications to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    unread_only: bool = Query(False, description="Only return unread"),
) -> NotificationListResponse:
    """List notifications for the current user.

    Returns paginated list of notifications ordered by creation date (newest first).
    Includes total count and unread count.
    """
    user_id = current_user.id
    return await NotificationService.get_notifications(
        user_id=user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread/count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: CurrentUser,
) -> UnreadCountResponse:
    """Get the count of unread notifications."""
    user_id = current_user.id
    return await NotificationService.get_unread_count(user_id=user_id)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
) -> NotificationResponse:
    """Mark a single notification as read."""
    user_id = current_user.id
    return await NotificationService.mark_as_read(notification_id=notification_id, user_id=user_id)


@router.put("/read-all")
async def mark_all_read(
    current_user: CurrentUser,
) -> JSONResponse:
    """Mark all notifications as read for the current user."""
    user_id = current_user.id
    count = await NotificationService.mark_all_as_read(user_id=user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Marked {count} notifications as read", "count": count},
    )


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: CurrentUser,
) -> None:
    """Delete a notification."""
    user_id = current_user.id
    await NotificationService.delete_notification(notification_id=notification_id, user_id=user_id)


# =========================================================================
# Push notification polling fallback (memory_briefing_queue)
# =========================================================================


@router.get("/pending")
async def get_pending_notifications(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=50, description="Max pending notifications"),
) -> JSONResponse:
    """Return all undelivered push notifications for the current user.

    Polls memory_briefing_queue for notifications that were not delivered
    via WebSocket. Used as a fallback when the user's WebSocket connection
    is unavailable.
    """
    user_id = current_user.id
    try:
        db = SupabaseClient.get_client()
        result = (
            db.table("memory_briefing_queue")
            .select("id, briefing_type, items, created_at")
            .eq("user_id", user_id)
            .eq("is_delivered", False)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        notifications: list[dict[str, Any]] = []
        for row in result.data or []:
            items = row.get("items")
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except (json.JSONDecodeError, TypeError):
                    items = {}

            notifications.append({
                "id": row["id"],
                "notification_type": row["briefing_type"],
                "payload": items,
                "created_at": row["created_at"],
            })

        return JSONResponse({"notifications": notifications, "count": len(notifications)})

    except Exception:
        logger.exception("Failed to fetch pending notifications for user %s", user_id)
        return JSONResponse(
            {"notifications": [], "count": 0, "error": "Failed to fetch"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post("/pending/{notification_id}/dismiss")
async def dismiss_pending_notification(
    notification_id: str,
    current_user: CurrentUser,
) -> JSONResponse:
    """Dismiss a pending push notification by marking it as delivered.

    Args:
        notification_id: The memory_briefing_queue row UUID.
    """
    user_id = current_user.id
    try:
        db = SupabaseClient.get_client()
        result = (
            db.table("memory_briefing_queue")
            .update({"is_delivered": True})
            .eq("id", notification_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            return JSONResponse(
                {"error": "Notification not found"},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return JSONResponse({"ok": True, "id": notification_id})

    except Exception:
        logger.exception(
            "Failed to dismiss notification %s for user %s",
            notification_id,
            user_id,
        )
        return JSONResponse(
            {"error": "Failed to dismiss"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
