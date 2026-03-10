"""Push notification service for time-sensitive ARIA events.

Persists notifications to memory_briefing_queue (durable) and attempts
real-time WebSocket push via the ConnectionManager singleton. If WebSocket
delivery fails, notifications remain undelivered in the queue for the
polling fallback endpoint (GET /api/v1/notifications/pending).
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES: dict[str, dict[str, Any]] = {
    "meeting_starting_soon": {"priority": "high", "ttl_minutes": 30},
    "action_queue_item": {"priority": "high", "ttl_minutes": 60},
    "commitment_overdue": {"priority": "high", "ttl_minutes": 1440},
    "debrief_ready": {"priority": "medium", "ttl_minutes": 120},
    "email_draft_ready": {"priority": "medium", "ttl_minutes": 480},
    "competitive_alert": {"priority": "low", "ttl_minutes": 1440},
    "briefing_ready": {"priority": "high", "ttl_minutes": 60},
}


async def send_notification(
    user_id: str,
    notification_type: str,
    payload: dict[str, Any],
) -> str:
    """Persist notification to memory_briefing_queue and attempt WebSocket push.

    Args:
        user_id: The target user's UUID.
        notification_type: One of the keys in NOTIFICATION_TYPES.
        payload: Notification-specific data (title, IDs, context).

    Returns:
        Notification UUID string, or empty string on failure.
    """
    try:
        db = SupabaseClient.get_client()

        type_config = NOTIFICATION_TYPES.get(notification_type, {})
        items = {
            **payload,
            "notification_type": notification_type,
            "priority": type_config.get("priority", "medium"),
            "ttl_minutes": type_config.get("ttl_minutes", 60),
            "created_at": datetime.now(UTC).isoformat(),
        }

        # 1. Always persist to memory_briefing_queue first (durable)
        result = (
            db.table("memory_briefing_queue")
            .insert({
                "user_id": user_id,
                "briefing_type": notification_type,
                "items": json.dumps(items),
                "is_delivered": False,
            })
            .execute()
        )

        if not result.data:
            logger.error(
                "Failed to insert notification into memory_briefing_queue",
                extra={"user_id": user_id, "notification_type": notification_type},
            )
            return ""

        notification_id = str(result.data[0]["id"])

        logger.info(
            "Push notification queued",
            extra={
                "notification_id": notification_id,
                "user_id": user_id,
                "notification_type": notification_type,
                "priority": type_config.get("priority", "medium"),
            },
        )

        # 2. Attempt WebSocket push if connection manager is available
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_raw_to_user(user_id, {
                "type": "notification",
                "notification_type": notification_type,
                "payload": payload,
                "id": notification_id,
                "priority": type_config.get("priority", "medium"),
            })

            # Mark as delivered if WebSocket push succeeded (user was connected)
            if ws_manager.is_connected(user_id):
                db.table("memory_briefing_queue").update(
                    {"is_delivered": True}
                ).eq("id", notification_id).execute()

                logger.debug(
                    "Push notification delivered via WebSocket",
                    extra={
                        "notification_id": notification_id,
                        "user_id": user_id,
                    },
                )

        except Exception as ws_err:
            # WebSocket not available — notification stays undelivered in queue.
            # Frontend polls GET /api/v1/notifications/pending as fallback.
            logger.debug(
                "WebSocket push not available, notification queued: %s",
                ws_err,
            )

        return notification_id

    except Exception:
        logger.exception(
            "send_notification failed for user %s type %s",
            user_id,
            notification_type,
        )
        return ""
