"""Notification service for ARIA.

This service handles creating, retrieving, and managing user notifications.
It also handles sending email notifications when user preferences allow.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import DatabaseError, NotFoundError
from src.db.supabase import SupabaseClient
from src.models.notification import (
    NotificationListResponse,
    NotificationResponse,
    NotificationType,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing user notifications."""

    @staticmethod
    async def create_notification(
        user_id: str,
        type: NotificationType,
        title: str,
        message: str | None = None,
        link: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationResponse:
        """Create a new notification for a user.

        Args:
            user_id: The user's UUID.
            type: Type of notification.
            title: Notification title.
            message: Optional message body.
            link: Optional navigation link.
            metadata: Optional additional data.

        Returns:
            Created notification.

        Raises:
            DatabaseError: If creation fails.
        """
        try:
            client = SupabaseClient.get_client()
            data: dict[str, Any] = {
                "user_id": user_id,
                "type": type.value,
                "title": title,
                "message": message,
                "link": link,
                "metadata": metadata or {},
            }
            response = client.table("notifications").insert(data).execute()
            if response.data and len(response.data) > 0:
                logger.info(
                    "Notification created",
                    extra={
                        "user_id": user_id,
                        "type": type.value,
                        "notification_id": response.data[0]["id"],
                    },
                )
                return NotificationResponse(**response.data[0])
            raise DatabaseError("Failed to create notification")
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error creating notification", extra={"user_id": user_id, "type": type.value}
            )
            raise DatabaseError(f"Failed to create notification: {e}") from e

    @staticmethod
    async def get_notifications(
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Get notifications for a user with pagination.

        Args:
            user_id: The user's UUID.
            limit: Max number of notifications to return.
            offset: Pagination offset.
            unread_only: If True, only return unread notifications.

        Returns:
            Paginated notification list with counts.

        Raises:
            DatabaseError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            query = client.table("notifications").select("*", count="exact").eq("user_id", user_id)

            if unread_only:
                query = query.is_("read_at", "null")

            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            response = query.execute()

            # Get unread count
            count_response = (
                client.table("notifications")
                .select("*", count="exact")
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            unread_count = count_response.count or 0

            notifications = [NotificationResponse(**item) for item in response.data or []]

            return NotificationListResponse(
                notifications=notifications,
                total=response.count or 0,
                unread_count=unread_count,
            )
        except Exception as e:
            logger.exception("Error fetching notifications", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch notifications: {e}") from e

    @staticmethod
    async def get_unread_count(user_id: str) -> UnreadCountResponse:
        """Get the count of unread notifications for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Unread count.

        Raises:
            DatabaseError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .select("*", count="exact")
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            return UnreadCountResponse(count=response.count or 0)
        except Exception as e:
            logger.exception("Error fetching unread count", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch unread count: {e}") from e

    @staticmethod
    async def mark_as_read(notification_id: str, user_id: str) -> NotificationResponse:
        """Mark a single notification as read.

        Args:
            notification_id: The notification UUID.
            user_id: The user's UUID (for authorization).

        Returns:
            Updated notification.

        Raises:
            NotFoundError: If notification not found.
            DatabaseError: If update fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .update({"read_at": datetime.now(UTC).isoformat()})
                .eq("id", notification_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return NotificationResponse(**response.data[0])
            raise NotFoundError("Notification", notification_id)
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception(
                "Error marking notification as read", extra={"notification_id": notification_id}
            )
            raise DatabaseError(f"Failed to mark notification as read: {e}") from e

    @staticmethod
    async def mark_all_as_read(user_id: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Number of notifications marked as read.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .update({"read_at": datetime.now(UTC).isoformat()})
                .eq("user_id", user_id)
                .is_("read_at", "null")
                .execute()
            )
            count = len(response.data or [])
            logger.info(
                "Marked all notifications as read", extra={"user_id": user_id, "count": count}
            )
            return count
        except Exception as e:
            logger.exception("Error marking all as read", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to mark all notifications as read: {e}") from e

    @staticmethod
    async def delete_notification(notification_id: str, user_id: str) -> None:
        """Delete a notification.

        Args:
            notification_id: The notification UUID.
            user_id: The user's UUID (for authorization).

        Raises:
            NotFoundError: If notification not found.
            DatabaseError: If deletion fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("notifications")
                .delete()
                .eq("id", notification_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not response.data or len(response.data) == 0:
                raise NotFoundError("Notification", notification_id)
            logger.info(
                "Notification deleted",
                extra={"notification_id": notification_id, "user_id": user_id},
            )
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception(
                "Error deleting notification", extra={"notification_id": notification_id}
            )
            raise DatabaseError(f"Failed to delete notification: {e}") from e
