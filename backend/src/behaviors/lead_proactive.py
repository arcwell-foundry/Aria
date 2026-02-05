"""Proactive lead behavior monitoring for ARIA.

This module implements autonomous lead monitoring behaviors:
- Silent lead detection: Alert when leads are inactive for 14+ days
- Health drop detection: Alert when health score drops 20+ points

These behaviors run periodically (via scheduler) or on-demand and
send notifications via NotificationService.

Usage:
    ```python
    from src.db.supabase import SupabaseClient
    from src.behaviors.lead_proactive import LeadProactiveBehaviors

    client = SupabaseClient.get_client()
    service = LeadProactiveBehaviors(db_client=client)

    # Check for silent leads and send notifications
    count = await service.check_silent_leads(user_id="user-123")

    # Check for health drops and send notifications
    count = await service.check_health_drops(user_id="user-123")
    ```
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.memory.lead_patterns import LeadPatternDetector
from src.models.notification import NotificationType
from src.services.notification_service import NotificationService

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


class LeadProactiveBehaviors:
    """Service for proactive lead monitoring and alerting.

    Monitors leads for concerning patterns and sends notifications
    to users via NotificationService.
    """

    # Default thresholds
    DEFAULT_INACTIVE_DAYS = 14
    DEFAULT_HEALTH_DROP_THRESHOLD = 20

    def __init__(self, db_client: Client) -> None:
        """Initialize the proactive behaviors service.

        Args:
            db_client: Supabase client for database operations.
        """
        self._db = db_client
        self._pattern_detector = LeadPatternDetector(db_client=db_client)

    async def check_silent_leads(
        self,
        user_id: str,
        inactive_days: int = DEFAULT_INACTIVE_DAYS,
    ) -> int:
        """Check for silent leads and send notifications.

        Finds leads that have been inactive for the specified number of days
        and sends a notification for each one.

        Args:
            user_id: The user to check leads for.
            inactive_days: Days of inactivity to trigger alert (default 14).

        Returns:
            Number of notifications sent.
        """
        silent_leads = await self._pattern_detector.find_silent_leads(
            user_id=user_id,
            inactive_days=inactive_days,
        )

        if not silent_leads:
            logger.debug(
                "No silent leads found",
                extra={"user_id": user_id, "inactive_days": inactive_days},
            )
            return 0

        notification_count = 0

        for lead in silent_leads:
            # Determine recommended action based on inactivity
            if lead.days_inactive >= 30:
                action = "Consider scheduling a check-in call"
            elif lead.days_inactive >= 21:
                action = "Send a follow-up email to re-engage"
            else:
                action = "Review lead status and plan next touchpoint"

            try:
                await NotificationService.create_notification(
                    user_id=user_id,
                    type=NotificationType.LEAD_SILENT,
                    title=f"Silent Lead: {lead.company_name}",
                    message=f"No activity for {lead.days_inactive} days. {action}",
                    link=f"/leads/{lead.lead_id}",
                    metadata={
                        "lead_id": lead.lead_id,
                        "company_name": lead.company_name,
                        "days_inactive": lead.days_inactive,
                        "health_score": lead.health_score,
                    },
                )
                notification_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to send silent lead notification",
                    extra={
                        "user_id": user_id,
                        "lead_id": lead.lead_id,
                        "error": str(e),
                    },
                )

        logger.info(
            "Checked silent leads",
            extra={
                "user_id": user_id,
                "silent_count": len(silent_leads),
                "notifications_sent": notification_count,
            },
        )

        return notification_count
