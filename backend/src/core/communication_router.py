"""Communication Router service (US-938).

Routes messages to appropriate channels based on priority and user preferences.
Implements priority-based multi-channel notification delivery.
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.supabase import SupabaseClient
from src.models.communication import (
    ChannelResult,
    ChannelType,
    CommunicationRequest,
    CommunicationResponse,
    MessagePriority,
)
from src.models.notification import NotificationType
from src.services.email_service import EmailService
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Singleton instance
_communication_router_instance: CommunicationRouter | None = None


class CommunicationRouter:
    """Service for routing communications to appropriate channels.

    Routes messages based on:
    1. Message priority (CRITICAL, IMPORTANT, FYI, BACKGROUND)
    2. User communication preferences
    3. Channel availability and configuration

    Priority -> Channel Mapping:
    - CRITICAL: in_app + push (always, ignoring preferences)
    - IMPORTANT: in_app + user's preferred channel (email or slack)
    - FYI: in_app only
    - BACKGROUND: no notification (logged only)
    """

    async def route_message(self, request: CommunicationRequest) -> CommunicationResponse:
        """Route a message to appropriate channels based on priority and preferences.

        Args:
            request: Communication request with priority, message, and metadata.

        Returns:
            CommunicationResponse with channels used and per-channel results.

        Raises:
            Does not raise - continues on partial failure, returns error details in response.
        """
        # Determine which channels to use
        if request.force_channels:
            # Override: use specified channels regardless of priority
            channels = [c.value for c in request.force_channels]
        else:
            # Normal routing based on priority and preferences
            user_prefs = await self._get_user_preferences(request.user_id)
            channels = self._determine_channels(request.priority, user_prefs)

        logger.info(
            "Routing message",
            extra={
                "user_id": request.user_id,
                "priority": request.priority.value,
                "channels": channels,
            },
        )

        # Send to each channel and collect results
        results: dict[ChannelType, ChannelResult] = {}
        channels_used: list[ChannelType] = []

        for channel in channels:
            try:
                result_dict = await self._send_to_channel(
                    request.user_id, request.message, channel, request
                )
                channel_type = ChannelType(result_dict["channel"])
                channel_result = ChannelResult(
                    channel=channel_type,
                    success=result_dict["success"],
                    message_id=result_dict.get("message_id"),
                    error=result_dict.get("error"),
                )
                results[channel_type] = channel_result
                if result_dict["success"]:
                    channels_used.append(channel_type)
            except Exception as e:
                # Log error but continue with other channels
                logger.exception(
                    "Error sending to channel",
                    extra={"channel": channel, "user_id": request.user_id},
                )
                channel_type = ChannelType(channel)
                results[channel_type] = ChannelResult(
                    channel=channel_type,
                    success=False,
                    message_id=None,
                    error=str(e),
                )

        return CommunicationResponse(
            user_id=request.user_id,
            priority=request.priority,
            channels_used=channels_used,
            results=results,
        )

    def _determine_channels(
        self, priority: MessagePriority, user_prefs: dict[str, Any]
    ) -> list[str]:
        """Determine which channels to use based on priority and user preferences.

        Args:
            priority: Message priority level.
            user_prefs: User's communication preferences.

        Returns:
            List of channel names (strings) to send to.
        """
        preferred = user_prefs.get("preferred_channels", ["in_app"])

        match priority:
            case MessagePriority.CRITICAL:
                # CRITICAL: always in_app + push, regardless of preferences
                return ["in_app", "push"]
            case MessagePriority.IMPORTANT:
                # IMPORTANT: in_app + first non-in_app preferred channel (if any)
                non_in_app = [ch for ch in preferred if ch != "in_app"]
                if non_in_app:
                    return ["in_app", non_in_app[0]]
                return ["in_app"]
            case MessagePriority.FYI:
                # FYI: in_app only
                return ["in_app"]
            case MessagePriority.BACKGROUND:
                # BACKGROUND: no notifications
                return []
            case _:
                # Default fallback
                return ["in_app"]

    async def _get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user's communication preferences from database.

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary with communication preferences.
            Defaults to in_app only if none set.
        """
        try:
            settings_data = await self._get_user_settings(user_id)
            preferences = settings_data.get("preferences", {})
            comm_prefs = preferences.get("communication", {})

            return {
                "preferred_channels": comm_prefs.get("preferred_channels", ["in_app"]),
                "email_enabled": comm_prefs.get("email_enabled", True),
                "slack_enabled": comm_prefs.get("slack_enabled", False),
            }
        except Exception as e:
            logger.warning(
                "Failed to fetch user preferences, using defaults",
                extra={"user_id": user_id, "error": str(e)},
            )
            return {
                "preferred_channels": ["in_app"],
                "email_enabled": True,
                "slack_enabled": False,
            }

    async def _get_user_settings(self, user_id: str) -> dict[str, Any]:
        """Fetch user settings from database.

        Args:
            user_id: The user's UUID.

        Returns:
            User settings data dictionary.

        Raises:
            Propagates database errors.
        """
        return await SupabaseClient.get_user_settings(user_id)

    async def _get_user_email(self, user_id: str) -> str | None:
        """Get user's email address for email channel.

        Args:
            user_id: The user's UUID.

        Returns:
            User email address or None if not found.
        """
        try:
            # Get user profile which should contain email
            # Note: In auth.users, email is stored, but we need to access it through
            # the user_profiles table or auth context
            client = SupabaseClient.get_client()
            # Try to get from user_profiles first
            response = (
                client.table("user_profiles")
                .select("email")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if response.data:
                # Cast response data to dict type
                data: Any = response.data
                if isinstance(data, dict):
                    return data.get("email")
                # Handle case where data might be a list
                if isinstance(data, list) and len(data) > 0:
                    first_item: Any = data[0]
                    if isinstance(first_item, dict):
                        return first_item.get("email")
            return None
        except Exception as e:
            logger.warning(
                "Failed to fetch user email",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _send_to_channel(
        self, user_id: str, message: str, channel: str, request: CommunicationRequest
    ) -> dict[str, Any]:
        """Send a message to a specific channel.

        Args:
            user_id: The user's UUID.
            message: Message content.
            channel: Channel name (in_app, email, slack, push).
            request: Original communication request for metadata.

        Returns:
            Dictionary with success status, channel name, message_id (if successful), and error (if failed).
        """
        match channel:
            case "in_app":
                # Use NotificationService for in-app notifications
                notification_type = self._map_priority_to_notification_type(request.priority)
                notification = await NotificationService.create_notification(
                    user_id=user_id,
                    type=notification_type,
                    title=request.title or "Notification",
                    message=message,
                    link=request.link,
                    metadata=request.metadata,
                )
                return {
                    "success": True,
                    "channel": "in_app",
                    "message_id": notification.id,
                }

            case "email":
                # Use EmailService for email notifications
                user_email = await self._get_user_email(user_id)
                if not user_email:
                    return {
                        "success": False,
                        "channel": "email",
                        "error": "User email not found",
                    }

                # Check user preferences for email
                user_prefs = await self._get_user_preferences(user_id)
                if not user_prefs.get("email_enabled", True):
                    return {
                        "success": False,
                        "channel": "email",
                        "error": "Email notifications disabled by user",
                    }

                # Send email
                email_service = EmailService()
                title = request.title or "ARIA Notification"
                # Create simple HTML email
                html = f"""
                <html>
                <body>
                    <p>{message}</p>
                </body>
                </html>
                """
                try:
                    email_id = await email_service._send_email(
                        to=user_email,
                        subject=title,
                        html=html,
                    )
                    return {
                        "success": True,
                        "channel": "email",
                        "message_id": email_id,
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "channel": "email",
                        "error": str(e),
                    }

            case "slack":
                # Slack not implemented yet
                return {
                    "success": False,
                    "channel": "slack",
                    "error": "Slack integration not implemented",
                }

            case "push":
                # Push notifications not implemented yet
                return {
                    "success": False,
                    "channel": "push",
                    "error": "Push notifications not implemented",
                }

            case _:
                return {
                    "success": False,
                    "channel": channel,
                    "error": f"Unknown channel: {channel}",
                }

    def _map_priority_to_notification_type(self, priority: MessagePriority) -> NotificationType:
        """Map message priority to notification type for in-app notifications.

        Args:
            priority: Message priority level.

        Returns:
            NotificationType enum value.
        """
        match priority:
            case MessagePriority.CRITICAL:
                return NotificationType.SIGNAL_DETECTED
            case MessagePriority.IMPORTANT:
                return NotificationType.TASK_DUE
            case MessagePriority.FYI:
                return NotificationType.BRIEFING_READY
            case MessagePriority.BACKGROUND:
                return NotificationType.BRIEFING_READY
            case _:
                return NotificationType.BRIEFING_READY


def get_communication_router() -> CommunicationRouter:
    """Get or create the CommunicationRouter singleton.

    Returns:
        CommunicationRouter instance.
    """
    global _communication_router_instance
    if _communication_router_instance is None:
        _communication_router_instance = CommunicationRouter()
    return _communication_router_instance
