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
from datetime import datetime
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

    async def check_health_drops(
        self,
        user_id: str,
        threshold: int = DEFAULT_HEALTH_DROP_THRESHOLD,
    ) -> int:
        """Check for leads with significant health score drops.

        Compares current health scores to recent history and sends
        notifications for leads that have dropped by the threshold or more.

        Args:
            user_id: The user to check leads for.
            threshold: Minimum score drop to trigger alert (default 20).

        Returns:
            Number of notifications sent.
        """
        from src.memory.health_score import HealthScoreCalculator, HealthScoreHistory

        # Get active leads for user with current health scores
        leads_response = (
            self._db.table("lead_memories")
            .select("id, company_name, health_score")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        if not leads_response.data:
            return 0

        lead_ids = [lead["id"] for lead in leads_response.data]
        lead_map = {lead["id"]: lead for lead in leads_response.data}

        # Get recent health score history for these leads
        history_response = (
            self._db.table("health_score_history")
            .select("lead_memory_id, score, calculated_at")
            .in_("lead_memory_id", lead_ids)
            .order("calculated_at", desc=True)
            .execute()
        )

        # Group history by lead_id and build HealthScoreHistory objects
        history_by_lead: dict[str, list[HealthScoreHistory]] = {}
        for item in history_response.data or []:
            lead_id = item["lead_memory_id"]
            if lead_id not in history_by_lead:
                history_by_lead[lead_id] = []
            history_by_lead[lead_id].append(
                HealthScoreHistory(
                    score=item["score"],
                    calculated_at=datetime.fromisoformat(item["calculated_at"]),
                )
            )

        calculator = HealthScoreCalculator()
        notification_count = 0

        for lead_id, lead_data in lead_map.items():
            current_score = lead_data.get("health_score", 0) or 0
            history = history_by_lead.get(lead_id, [])

            if not history:
                continue

            # Use calculator's alert logic
            if calculator._should_alert(current_score, history, threshold=threshold):
                # Calculate the actual drop for the message
                previous_score = max(history, key=lambda h: h.calculated_at).score
                drop_amount = previous_score - current_score

                # Determine recommended action based on drop severity
                if drop_amount >= 30:
                    action = "Immediate attention required - major engagement issue"
                elif drop_amount >= 25:
                    action = "Review recent interactions for concerns"
                else:
                    action = "Check for engagement opportunities"

                try:
                    await NotificationService.create_notification(
                        user_id=user_id,
                        type=NotificationType.LEAD_HEALTH_DROP,
                        title=f"Health Drop: {lead_data['company_name']}",
                        message=f"Health score dropped {drop_amount} points (from {previous_score} to {current_score}). {action}",
                        link=f"/leads/{lead_id}",
                        metadata={
                            "lead_id": lead_id,
                            "company_name": lead_data["company_name"],
                            "current_score": current_score,
                            "previous_score": previous_score,
                            "drop_amount": drop_amount,
                        },
                    )
                    notification_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to send health drop notification",
                        extra={
                            "user_id": user_id,
                            "lead_id": lead_id,
                            "error": str(e),
                        },
                    )

        logger.info(
            "Checked health drops",
            extra={
                "user_id": user_id,
                "leads_checked": len(lead_map),
                "notifications_sent": notification_count,
            },
        )

        return notification_count
