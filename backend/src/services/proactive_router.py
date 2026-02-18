"""Central routing layer for proactive intelligence insights.

Every proactive job routes its findings through ``ProactiveRouter.route()``
which determines the delivery channel based on priority:

- **HIGH**: WebSocket message if online, otherwise queued for login delivery.
- **MEDIUM**: Notification + intel-panel badge via ``signal.detected`` WS event.
- **LOW**: Queued into ``briefing_queue`` for the next morning briefing.

Deduplication prevents the same insight from being delivered twice within
one hour.
"""

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class InsightPriority(str, Enum):
    """Priority level for proactive insights."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightCategory(str, Enum):
    """Category tags for proactive insights."""

    DEBRIEF_PROMPT = "debrief_prompt"
    OVERDUE_COMMITMENT = "overdue_commitment"
    URGENT_EMAIL = "urgent_email"
    MARKET_SIGNAL = "market_signal"
    STALE_LEAD = "stale_lead"
    HEALTH_DROP = "health_drop"
    BATTLE_CARD_UPDATE = "battle_card_update"
    CONVERSION_SCORE_CHANGE = "conversion_score_change"
    WEEKLY_DIGEST = "weekly_digest"


class ProactiveRouter:
    """Routes proactive insights to the correct delivery channel."""

    def __init__(self) -> None:
        self._db: Any = None

    def _get_db(self) -> Any:
        if self._db is None:
            from src.db.supabase import SupabaseClient

            self._db = SupabaseClient.get_client()
        return self._db

    async def route(
        self,
        user_id: str,
        priority: InsightPriority,
        category: InsightCategory,
        title: str,
        message: str,
        rich_content: list[dict[str, Any]] | None = None,
        ui_commands: list[dict[str, Any]] | None = None,
        suggestions: list[str] | None = None,
        link: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Route an insight to the appropriate delivery channel.

        Args:
            user_id: Target user UUID.
            priority: HIGH, MEDIUM, or LOW.
            category: Insight category for dedup and analytics.
            title: Short human-readable title.
            message: Full message text (ARIA's voice).
            rich_content: Optional rich content cards.
            ui_commands: Optional UI commands.
            suggestions: Optional follow-up suggestions.
            link: Optional deep-link URL.
            metadata: Optional extra metadata.

        Returns:
            Dict with ``channel`` key indicating how the insight was delivered.
        """
        # Deduplication check
        if await self._is_duplicate(user_id, category, title):
            logger.debug(
                "Duplicate insight suppressed",
                extra={"user_id": user_id, "category": category.value, "title": title},
            )
            return {"channel": "suppressed_duplicate"}

        if priority == InsightPriority.HIGH:
            return await self._route_high(
                user_id, category, title, message,
                rich_content, ui_commands, suggestions, link, metadata,
            )
        elif priority == InsightPriority.MEDIUM:
            return await self._route_medium(
                user_id, category, title, message, link, metadata,
            )
        else:
            return await self._route_low(
                user_id, category, title, message, metadata,
            )

    # ------------------------------------------------------------------
    # HIGH priority: real-time delivery or login queue
    # ------------------------------------------------------------------

    async def _route_high(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
        message: str,
        rich_content: list[dict[str, Any]] | None,
        ui_commands: list[dict[str, Any]] | None,
        suggestions: list[str] | None,
        link: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Deliver via WebSocket if online, otherwise queue for login."""
        from src.core.ws import ws_manager

        if ws_manager.is_connected(user_id):
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=f"I noticed something important: {message}",
                rich_content=rich_content or [],
                ui_commands=ui_commands or [],
                suggestions=suggestions or [],
            )
            logger.info(
                "HIGH insight delivered via WebSocket",
                extra={"user_id": user_id, "category": category.value},
            )
            return {"channel": "websocket"}

        # User offline — queue for login delivery + create notification
        await self._enqueue_login_message(user_id, category, title, message, metadata)
        await self._create_notification(user_id, category, title, message, link, metadata)
        logger.info(
            "HIGH insight queued for login",
            extra={"user_id": user_id, "category": category.value},
        )
        return {"channel": "login_queue"}

    # ------------------------------------------------------------------
    # MEDIUM priority: notification + intel-panel badge
    # ------------------------------------------------------------------

    async def _route_medium(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
        message: str,
        link: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Create notification and send signal.detected WS event if online."""
        await self._create_notification(user_id, category, title, message, link, metadata)

        from src.core.ws import ws_manager

        if ws_manager.is_connected(user_id):
            await ws_manager.send_to_user(
                user_id,
                {
                    "type": "signal.detected",
                    "payload": {
                        "category": category.value,
                        "title": title,
                        "message": message,
                    },
                },
            )

        logger.info(
            "MEDIUM insight routed as notification",
            extra={"user_id": user_id, "category": category.value},
        )
        return {"channel": "notification"}

    # ------------------------------------------------------------------
    # LOW priority: briefing queue
    # ------------------------------------------------------------------

    async def _route_low(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
        message: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Insert into briefing_queue for inclusion in next morning briefing."""
        db = self._get_db()
        try:
            db.table("briefing_queue").insert(
                {
                    "user_id": user_id,
                    "title": title,
                    "message": message,
                    "category": category.value,
                    "metadata": metadata or {},
                    "consumed": False,
                }
            ).execute()
        except Exception:
            logger.warning(
                "Failed to insert into briefing_queue",
                extra={"user_id": user_id},
                exc_info=True,
            )

        logger.info(
            "LOW insight queued for briefing",
            extra={"user_id": user_id, "category": category.value},
        )
        return {"channel": "briefing_queue"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _is_duplicate(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
    ) -> bool:
        """Check notifications table for a matching (user, type, title) in the last hour."""
        db = self._get_db()
        try:
            cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            result = (
                db.table("notifications")
                .select("id")
                .eq("user_id", user_id)
                .eq("type", category.value)
                .eq("title", title)
                .gte("created_at", cutoff)
                .limit(1)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    async def _create_notification(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
        message: str,
        link: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create notification via NotificationService."""
        try:
            from src.models.notification import NotificationType
            from src.services.notification_service import NotificationService

            # Map category to closest NotificationType
            type_map: dict[InsightCategory, NotificationType] = {
                InsightCategory.MARKET_SIGNAL: NotificationType.SIGNAL_DETECTED,
                InsightCategory.STALE_LEAD: NotificationType.LEAD_SILENT,
                InsightCategory.HEALTH_DROP: NotificationType.LEAD_HEALTH_DROP,
                InsightCategory.WEEKLY_DIGEST: NotificationType.WEEKLY_DIGEST_READY,
                InsightCategory.BATTLE_CARD_UPDATE: NotificationType.BATTLE_CARD_UPDATED,
                InsightCategory.CONVERSION_SCORE_CHANGE: NotificationType.CONVERSION_SCORE_CHANGE,
                InsightCategory.DEBRIEF_PROMPT: NotificationType.MEETING_DEBRIEF_PROMPT,
                InsightCategory.OVERDUE_COMMITMENT: NotificationType.TASK_DUE,
                InsightCategory.URGENT_EMAIL: NotificationType.SIGNAL_DETECTED,
            }

            notif_type = type_map.get(category, NotificationType.SIGNAL_DETECTED)

            await NotificationService.create_notification(
                user_id=user_id,
                type=notif_type,
                title=title,
                message=message,
                link=link,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "Failed to create notification for insight",
                extra={"user_id": user_id, "category": category.value},
                exc_info=True,
            )

    async def _enqueue_login_message(
        self,
        user_id: str,
        category: InsightCategory,
        title: str,
        message: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Insert into login_message_queue for offline users."""
        db = self._get_db()
        try:
            db.table("login_message_queue").insert(
                {
                    "user_id": user_id,
                    "title": title,
                    "message": message,
                    "category": category.value,
                    "metadata": metadata or {},
                    "delivered": False,
                }
            ).execute()
        except Exception:
            logger.warning(
                "Failed to enqueue login message",
                extra={"user_id": user_id},
                exc_info=True,
            )
