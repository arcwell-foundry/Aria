"""Periodic email inbox check job for urgent email detection.

This job runs every 30 minutes during business hours to check for
new urgent emails and trigger real-time notifications.

Used by the scheduler to proactively surface urgent emails without
waiting for the user to manually scan or the morning briefing.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.services.email_analyzer import EmailAnalyzer
from src.services.realtime_email_notifier import get_realtime_email_notifier

logger = logging.getLogger(__name__)


# Business hours configuration (can be moved to user settings later)
DEFAULT_BUSINESS_START_HOUR = 8  # 8 AM
DEFAULT_BUSINESS_END_HOUR = 19  # 7 PM


async def run_periodic_email_check() -> dict[str, Any]:
    """Run periodic inbox check for all users with email integrations.

    For each user with email connected:
    1. Check if within business hours (8 AM - 7 PM user timezone)
    2. Get last processing run watermark from email_processing_runs.completed_at
    3. Scan inbox for emails since watermark
    4. If urgent emails found: trigger RealtimeEmailNotifier

    Returns:
        Dict with statistics about the check run.
    """
    stats = {
        "users_checked": 0,
        "users_skipped_off_hours": 0,
        "users_with_urgent": 0,
        "total_urgent_emails": 0,
        "notifications_sent": 0,
        "errors": 0,
    }

    try:
        db = SupabaseClient.get_client()

        # Get users with active email integrations
        result = (
            db.table("user_integrations")
            .select("user_id, integration_type, metadata")
            .in_("integration_type", ["gmail", "outlook"])
            .eq("status", "active")
            .execute()
        )

        users = result.data or []
        logger.info(
            "PERIODIC_EMAIL_CHECK: Starting check for %d users with email integrations",
            len(users),
        )

        analyzer = EmailAnalyzer()
        notifier = get_realtime_email_notifier()

        for user_record in users:
            user_id = user_record["user_id"]

            try:
                # Check if within business hours
                if not _is_business_hours(user_id, user_record.get("metadata")):
                    stats["users_skipped_off_hours"] += 1
                    continue

                stats["users_checked"] += 1

                # Get last processing run watermark
                since_hours = _calculate_hours_since_last_run(db, user_id)

                if since_hours < 0.5:  # Skip if last run was less than 30 min ago
                    logger.debug(
                        "PERIODIC_EMAIL_CHECK: Skipping user %s - last run %0.1f hours ago",
                        user_id,
                        since_hours,
                    )
                    continue

                # Scan inbox for new emails
                logger.info(
                    "PERIODIC_EMAIL_CHECK: Scanning inbox for user %s (since %0.1f hours)",
                    user_id,
                    since_hours,
                )

                scan_result = await analyzer.scan_inbox(user_id, since_hours=since_hours)

                if scan_result.urgent:
                    stats["users_with_urgent"] += 1
                    stats["total_urgent_emails"] += len(scan_result.urgent)

                    # Process and notify
                    notifications = await notifier.process_and_notify(
                        user_id=user_id,
                        urgent_emails=scan_result.urgent,
                        generate_drafts=True,
                    )
                    stats["notifications_sent"] += len(notifications)

                    logger.info(
                        "PERIODIC_EMAIL_CHECK: User %s has %d urgent emails, sent %d notifications",
                        user_id,
                        len(scan_result.urgent),
                        len(notifications),
                    )
                else:
                    logger.debug(
                        "PERIODIC_EMAIL_CHECK: No urgent emails for user %s",
                        user_id,
                    )

            except Exception as e:
                logger.warning(
                    "PERIODIC_EMAIL_CHECK: Failed for user %s: %s",
                    user_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            "PERIODIC_EMAIL_CHECK: Complete. Checked %d users, %d with urgent emails, "
            "%d total urgent, %d notifications sent, %d errors",
            stats["users_checked"],
            stats["users_with_urgent"],
            stats["total_urgent_emails"],
            stats["notifications_sent"],
            stats["errors"],
        )

    except Exception as e:
        logger.error(
            "PERIODIC_EMAIL_CHECK: Job failed: %s",
            e,
            exc_info=True,
        )
        stats["errors"] += 1

    return stats


def _is_business_hours(
    user_id: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Check if current time is within business hours for the user.

    Business hours: 8 AM - 7 PM in user's timezone.

    Args:
        user_id: The user's ID.
        metadata: Optional user integration metadata with timezone info.

    Returns:
        True if within business hours, False otherwise.
    """
    try:
        # Get user timezone from metadata or use UTC default
        # In production, this should query user_settings for timezone
        user_timezone = None
        if metadata and isinstance(metadata, dict):
            user_timezone = metadata.get("timezone")

        now = datetime.now(UTC)

        # If we have a timezone, convert to local time
        if user_timezone:
            try:
                import zoneinfo

                tz = zoneinfo.ZoneInfo(user_timezone)
                local_now = now.astimezone(tz)
            except Exception:
                local_now = now
        else:
            local_now = now

        current_hour = local_now.hour

        # Check if within business hours (8 AM - 7 PM)
        is_business = DEFAULT_BUSINESS_START_HOUR <= current_hour < DEFAULT_BUSINESS_END_HOUR

        logger.debug(
            "PERIODIC_EMAIL_CHECK: User %s - hour %d, business hours: %s",
            user_id,
            current_hour,
            is_business,
        )

        return is_business

    except Exception as e:
        logger.warning(
            "PERIODIC_EMAIL_CHECK: Failed to check business hours for %s: %s",
            user_id,
            e,
        )
        # Default to True on error to avoid missing urgent emails
        return True


def _calculate_hours_since_last_run(db: Any, user_id: str) -> float:
    """Calculate hours since the last email processing run.

    Uses email_processing_runs.completed_at as the watermark.

    Args:
        db: Supabase client.
        user_id: The user's ID.

    Returns:
        Hours since last run (default 24 hours if no previous run).
    """
    try:
        result = (
            db.table("email_processing_runs")
            .select("completed_at")
            .eq("user_id", user_id)
            .eq("status", "completed")
            .order("completed_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )

        if not result.data or not result.data.get("completed_at"):
            logger.debug(
                "PERIODIC_EMAIL_CHECK: No previous run for user %s, using default 24h",
                user_id,
            )
            return 24.0

        completed_at_str = result.data["completed_at"]
        completed_at = datetime.fromisoformat(
            completed_at_str.replace("Z", "+00:00")
        )

        delta = datetime.now(UTC) - completed_at
        hours = delta.total_seconds() / 3600

        # Cap at 24 hours max
        return min(hours, 24.0)

    except Exception as e:
        logger.warning(
            "PERIODIC_EMAIL_CHECK: Failed to get last run for %s: %s",
            user_id,
            e,
        )
        return 24.0
