"""Notification integration helper for ARIA services.

This module provides a convenient interface for other services to create notifications.
"""

import logging

from src.models.notification import NotificationType
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def notify_briefing_ready(user_id: str, briefing_date: str) -> None:
    """Notify user that their daily briefing is ready.

    Args:
        user_id: The user's UUID.
        briefing_date: The briefing date (YYYY-MM-DD).
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.BRIEFING_READY,
            title="Daily Briefing Ready",
            message=f"Your briefing for {briefing_date} is ready to view.",
            link="/briefing",
            metadata={"briefing_date": briefing_date},
        )
        logger.info("Briefing ready notification created", extra={"user_id": user_id})
    except Exception as e:
        logger.error(
            "Failed to create briefing notification", extra={"user_id": user_id, "error": str(e)}
        )


async def notify_signal_detected(
    user_id: str,
    company_name: str,
    signal_type: str,
    headline: str,
    lead_id: str | None = None,
) -> None:
    """Notify user about a detected market signal.

    Args:
        user_id: The user's UUID.
        company_name: Name of the company.
        signal_type: Type of signal.
        headline: Signal headline.
        lead_id: Optional linked lead memory ID.
    """
    try:
        link = f"/leads/{lead_id}" if lead_id else "/leads"
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.SIGNAL_DETECTED,
            title=f"Signal Detected: {company_name}",
            message=headline,
            link=link,
            metadata={"company": company_name, "signal_type": signal_type, "lead_id": lead_id},
        )
        logger.info(
            "Signal detected notification created",
            extra={"user_id": user_id, "company": company_name},
        )
    except Exception as e:
        logger.error(
            "Failed to create signal notification", extra={"user_id": user_id, "error": str(e)}
        )


async def notify_task_due(user_id: str, task_title: str, task_id: str, due_date: str) -> None:
    """Notify user about a task due soon.

    Args:
        user_id: The user's UUID.
        task_title: Title of the task.
        task_id: The task's UUID.
        due_date: Due date string.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.TASK_DUE,
            title=f"Task Due: {task_title}",
            message=f"This task is due on {due_date}",
            link=f"/goals?task={task_id}",
            metadata={"task_id": task_id, "due_date": due_date},
        )
        logger.info("Task due notification created", extra={"user_id": user_id, "task_id": task_id})
    except Exception as e:
        logger.error(
            "Failed to create task notification", extra={"user_id": user_id, "error": str(e)}
        )


async def notify_meeting_brief_ready(
    user_id: str, meeting_title: str, calendar_event_id: str
) -> None:
    """Notify user that a meeting brief is ready.

    Args:
        user_id: The user's UUID.
        meeting_title: Title of the meeting.
        calendar_event_id: Calendar event ID.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.MEETING_BRIEF_READY,
            title=f"Meeting Brief Ready: {meeting_title}",
            message="Your pre-meeting research brief has been generated.",
            link=f"/meeting-brief/{calendar_event_id}",
            metadata={"meeting_title": meeting_title, "calendar_event_id": calendar_event_id},
        )
        logger.info(
            "Meeting brief ready notification created",
            extra={"user_id": user_id, "event_id": calendar_event_id},
        )
    except Exception as e:
        logger.error(
            "Failed to create meeting brief notification",
            extra={"user_id": user_id, "error": str(e)},
        )


async def notify_draft_ready(
    user_id: str,
    draft_type: str,
    recipient: str,
    draft_id: str,
) -> None:
    """Notify user that an email draft is ready.

    Args:
        user_id: The user's UUID.
        draft_type: Type of draft (e.g., "follow_up", "intro").
        recipient: Recipient email/name.
        draft_id: The draft's UUID.
    """
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.DRAFT_READY,
            title="Email Draft Ready",
            message=f"Your {draft_type} draft to {recipient} is ready for review.",
            link=f"/drafts/{draft_id}",
            metadata={"draft_id": draft_id, "draft_type": draft_type, "recipient": recipient},
        )
        logger.info(
            "Draft ready notification created", extra={"user_id": user_id, "draft_id": draft_id}
        )
    except Exception as e:
        logger.error(
            "Failed to create draft notification", extra={"user_id": user_id, "error": str(e)}
        )
