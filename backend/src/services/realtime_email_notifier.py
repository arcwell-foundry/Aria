"""Real-time email urgency notification service.

Orchestrates urgent email detection, draft generation, and real-time
WebSocket notifications to active users.

This service bridges:
- EmailAnalyzer: Detects urgent emails
- AutonomousDraftEngine: Generates reply drafts (pending user approval)
- WebSocket ConnectionManager: Pushes real-time notifications

If user is active (WebSocket connected): immediate notification
If user is not active: emails already queued via email_scan_log for morning briefing
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.core.ws import ws_manager
from src.services.autonomous_draft_engine import AutonomousDraftEngine, DraftResult
from src.services.email_analyzer import EmailCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class UrgentNotification:
    """An urgent email notification for WebSocket delivery."""

    email_id: str
    sender_name: str
    sender_email: str
    subject: str
    urgency_reason: str
    draft_id: str | None
    draft_saved: bool
    topic_summary: str
    timestamp: str


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------


class RealtimeEmailNotifier:
    """Handles real-time urgent email detection and notification.

    This service:
    1. Receives urgent emails from EmailAnalyzer
    2. Generates draft replies via AutonomousDraftEngine
    3. Saves drafts to user's email client (Gmail/Outlook)
    4. If user is active (WebSocket connected): sends real-time notification
    5. If user is not active: emails remain in email_scan_log for morning briefing
    """

    def __init__(self) -> None:
        """Initialize with lazy-loaded dependencies."""
        self._draft_engine: AutonomousDraftEngine | None = None

    def _get_draft_engine(self) -> AutonomousDraftEngine:
        """Lazily initialize and return the AutonomousDraftEngine."""
        if self._draft_engine is None:
            self._draft_engine = AutonomousDraftEngine()
        return self._draft_engine

    async def process_and_notify(
        self,
        user_id: str,
        urgent_emails: list[EmailCategory],
        generate_drafts: bool = True,
    ) -> list[UrgentNotification]:
        """Process urgent emails and notify user if active.

        For each urgent email:
        1. Generate draft reply (optional, via AutonomousDraftEngine)
        2. Save draft to email client (Gmail/Outlook)
        3. Check if user is active (WebSocket connected)
        4. If active: send real-time notification via WebSocket
        5. If not active: emails remain queued for morning briefing

        Args:
            user_id: The user's ID.
            urgent_emails: List of urgent EmailCategory objects.
            generate_drafts: Whether to generate draft replies (default True).

        Returns:
            List of UrgentNotification objects for logging/tracking.
        """
        notifications: list[UrgentNotification] = []

        if not urgent_emails:
            return notifications

        logger.info(
            "REALTIME_NOTIFIER: Processing %d urgent emails for user %s",
            len(urgent_emails),
            user_id,
        )

        # Check if user is active before processing
        is_user_active = ws_manager.is_connected(user_id)

        for email in urgent_emails:
            try:
                notification = await self._process_single_email(
                    user_id=user_id,
                    email=email,
                    generate_draft=generate_drafts,
                )
                notifications.append(notification)

                # Only send real-time notification if user is active
                if is_user_active:
                    await self._send_urgent_notification(user_id, notification)
                else:
                    logger.info(
                        "REALTIME_NOTIFIER: User %s not active, urgent email queued for briefing",
                        user_id,
                    )

            except Exception as e:
                logger.error(
                    "REALTIME_NOTIFIER: Failed to process urgent email %s: %s",
                    email.email_id,
                    e,
                    exc_info=True,
                )
                # Create failed notification for tracking
                notifications.append(
                    UrgentNotification(
                        email_id=email.email_id,
                        sender_name=email.sender_name,
                        sender_email=email.sender_email,
                        subject=email.subject,
                        urgency_reason="Processing failed",
                        draft_id=None,
                        draft_saved=False,
                        topic_summary=email.topic_summary,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                )

        return notifications

    async def _process_single_email(
        self,
        user_id: str,
        email: EmailCategory,
        generate_draft: bool,
    ) -> UrgentNotification:
        """Process a single urgent email and generate notification data.

        Args:
            user_id: The user's ID.
            email: The urgent EmailCategory to process.
            generate_draft: Whether to generate a draft reply.

        Returns:
            UrgentNotification with all processing results.
        """
        draft_id: str | None = None
        draft_saved = False

        if generate_draft and email.needs_draft:
            try:
                # Generate draft via AutonomousDraftEngine
                # Note: This is a simplified single-email processing
                # For full processing, use draft_engine.process_inbox()
                draft_result = await self._generate_single_draft(user_id, email)

                if draft_result and draft_result.success:
                    draft_id = draft_result.draft_id

            except Exception as e:
                logger.warning(
                    "REALTIME_NOTIFIER: Draft generation failed for %s: %s",
                    email.email_id,
                    e,
                )

        # Determine urgency reason
        urgency_reason = self._determine_urgency_reason(email)

        return UrgentNotification(
            email_id=email.email_id,
            sender_name=email.sender_name,
            sender_email=email.sender_email,
            subject=email.subject,
            urgency_reason=urgency_reason,
            draft_id=draft_id,
            draft_saved=draft_saved,
            topic_summary=email.topic_summary,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _generate_single_draft(
        self,
        user_id: str,
        email: EmailCategory,
    ) -> DraftResult | None:
        """Generate a draft reply for a single urgent email.

        Uses AutonomousDraftEngine's internal method for single email processing.

        Args:
            user_id: The user's ID.
            email: The EmailCategory to generate draft for.

        Returns:
            DraftResult if successful, None otherwise.
        """
        try:
            engine = self._get_draft_engine()

            # Get user name for signature
            user_name = await engine._get_user_name(user_id)

            # Process single email using the engine's internal method
            return await engine._process_single_email(user_id, user_name, email)

        except Exception as e:
            logger.error(
                "REALTIME_NOTIFIER: Single draft generation failed: %s",
                e,
                exc_info=True,
            )
            return None

    def _determine_urgency_reason(self, email: EmailCategory) -> str:
        """Determine the reason for urgency based on email classification.

        Args:
            email: The EmailCategory to analyze.

        Returns:
            Human-readable urgency reason string.
        """
        reasons = []

        # Check the reason field from classification
        reason_lower = email.reason.lower()

        if "keyword" in reason_lower or "urgent" in reason_lower:
            reasons.append("time-sensitive content")
        if "vip" in reason_lower:
            reasons.append("VIP contact")
        if "calendar" in reason_lower or "meeting" in reason_lower:
            reasons.append("upcoming meeting with sender")
        if "overdue" in reason_lower:
            reasons.append("overdue response")
        if "rapid" in reason_lower or "thread" in reason_lower:
            reasons.append("rapid thread activity")

        if not reasons:
            reasons.append("requires immediate attention")

        return ", ".join(reasons)

    async def _send_urgent_notification(
        self,
        user_id: str,
        notification: UrgentNotification,
    ) -> None:
        """Send WebSocket notification for urgent email.

        Args:
            user_id: The user to notify.
            notification: The UrgentNotification to send.
        """
        try:
            # Build natural language message
            message = f"Urgent: {notification.sender_name} emailed about {notification.subject}."
            if notification.draft_saved:
                message += " I've drafted a reply in your email drafts."
            elif notification.draft_id:
                message += " I've prepared a draft reply for your review."

            # Build rich content
            rich_content = [
                {
                    "type": "urgent_email",
                    "email_id": notification.email_id,
                    "sender": notification.sender_name,
                    "sender_email": notification.sender_email,
                    "subject": notification.subject,
                    "urgency_reason": notification.urgency_reason,
                    "draft_id": notification.draft_id,
                    "draft_saved": notification.draft_saved,
                    "topic_summary": notification.topic_summary,
                    "timestamp": notification.timestamp,
                }
            ]

            # Build UI commands
            ui_commands = [
                {
                    "action": "highlight",
                    "element": f"email-{notification.email_id}",
                }
            ]

            # Build suggestions
            suggestions = ["Review draft", "Reply now", "Snooze"]

            # Send via WebSocket
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=message,
                rich_content=rich_content,
                ui_commands=ui_commands,
                suggestions=suggestions,
            )

            logger.info(
                "REALTIME_NOTIFIER: Sent urgent notification to user %s for email %s",
                user_id,
                notification.email_id,
            )

        except Exception as e:
            logger.error(
                "REALTIME_NOTIFIER: Failed to send WebSocket notification: %s",
                e,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_notifier: RealtimeEmailNotifier | None = None


def get_realtime_email_notifier() -> RealtimeEmailNotifier:
    """Get or create the RealtimeEmailNotifier singleton.

    Returns:
        The RealtimeEmailNotifier singleton instance.
    """
    global _notifier
    if _notifier is None:
        _notifier = RealtimeEmailNotifier()
    return _notifier
