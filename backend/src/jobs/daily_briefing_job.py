"""Background job for daily briefing generation.

This job generates daily briefings for all active users. For beta, it runs
as a startup check that generates any missing briefings for today. For
production, wire this into APScheduler, Celery Beat, or an external cron.

Timezone-aware: each user's preferred briefing_time and timezone are read
from the user_preferences table so the job only generates a briefing once
the user's local clock has passed their configured time.
"""

import logging
from datetime import date, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from src.db.supabase import SupabaseClient
from src.services.briefing import BriefingService
from src.services.email_service import EmailService

logger = logging.getLogger(__name__)

# Default briefing hour (24h) when no preference is set
DEFAULT_BRIEFING_HOUR = 6
DEFAULT_BRIEFING_MINUTE = 0
DEFAULT_TIMEZONE = "UTC"


def _parse_briefing_time(time_str: str) -> tuple[int, int]:
    """Parse a HH:MM time string into (hour, minute).

    Args:
        time_str: Time string in HH:MM or HH:MM:SS format.

    Returns:
        Tuple of (hour, minute).
    """
    parts = time_str.strip().split(":")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return DEFAULT_BRIEFING_HOUR, DEFAULT_BRIEFING_MINUTE


def _is_briefing_due(
    timezone_str: str,
    briefing_time_str: str,
) -> bool:
    """Check whether the user's local time has passed their briefing time today.

    Args:
        timezone_str: IANA timezone string (e.g. "America/New_York").
        briefing_time_str: HH:MM time string from user_preferences.

    Returns:
        True if the user's current local time is at or past their briefing time.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except (KeyError, ValueError):
        logger.warning(
            "Invalid timezone, falling back to UTC",
            extra={"timezone": timezone_str},
        )
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    hour, minute = _parse_briefing_time(briefing_time_str)

    briefing_today = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now_local >= briefing_today


def _today_in_user_tz(timezone_str: str) -> date:
    """Get today's date in the user's timezone.

    Args:
        timezone_str: IANA timezone string.

    Returns:
        Today's date in the user's local timezone.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except (KeyError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


async def _get_active_users_with_preferences() -> list[dict[str, Any]]:
    """Fetch active users joined with their briefing preferences.

    Returns a list of dicts with user_id, timezone, briefing_time, email,
    full_name, and notification_email.
    """
    db = SupabaseClient.get_client()

    # Get all user profiles (active users)
    profiles_result = db.table("user_profiles").select("id, full_name").execute()
    profiles = cast(list[dict[str, Any]], profiles_result.data or [])

    if not profiles:
        return []

    user_ids = [p["id"] for p in profiles]

    # Batch-fetch preferences for all users
    prefs_result = (
        db.table("user_preferences")
        .select("user_id, timezone, briefing_time, notification_email")
        .in_("user_id", user_ids)
        .execute()
    )
    prefs_by_user: dict[str, dict[str, Any]] = {
        p["user_id"]: p for p in (prefs_result.data or []) if isinstance(p, dict)
    }

    # Build combined list
    users = []
    for profile in profiles:
        uid = profile["id"]
        pref = prefs_by_user.get(uid, {})
        users.append(
            {
                "user_id": uid,
                "full_name": profile.get("full_name", ""),
                "timezone": pref.get("timezone", DEFAULT_TIMEZONE),
                "briefing_time": pref.get(
                    "briefing_time", f"{DEFAULT_BRIEFING_HOUR:02d}:{DEFAULT_BRIEFING_MINUTE:02d}"
                ),
                "notification_email": pref.get("notification_email", True),
            }
        )

    return users


async def _briefing_exists(user_id: str, briefing_date: date) -> bool:
    """Check if a briefing already exists for the user on this date.

    Args:
        user_id: The user's UUID.
        briefing_date: The date to check.

    Returns:
        True if a briefing row exists.
    """
    db = SupabaseClient.get_client()
    result = (
        db.table("daily_briefings")
        .select("id")
        .eq("user_id", user_id)
        .eq("briefing_date", briefing_date.isoformat())
        .execute()
    )
    return bool(result.data)


async def _send_briefing_email(user_id: str, full_name: str, briefing_date: date) -> None:
    """Send a briefing-ready email notification.

    Uses the weekly_summary template as a lightweight carrier since there
    is no dedicated briefing email template yet. Fails silently so that
    email issues never block briefing generation.

    Args:
        user_id: The user's UUID.
        full_name: The user's display name.
        briefing_date: Date of the briefing.
    """
    try:
        db = SupabaseClient.get_client()
        # Fetch user email from auth metadata via user_profiles + auth
        auth_result = db.auth.admin.get_user_by_id(user_id)
        email = getattr(auth_result, "user", None)
        if email and hasattr(email, "email"):
            email_address = email.email
        else:
            logger.debug("No email found for user", extra={"user_id": user_id})
            return

        email_service = EmailService()
        await email_service.send_weekly_summary(
            to=email_address,
            name=full_name or "there",
            summary_data={
                "Type": "Daily Briefing",
                "Date": briefing_date.isoformat(),
                "Action": "View your briefing in ARIA",
            },
        )
        logger.info(
            "Briefing email sent",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )
    except Exception:
        # Email failures should never block the job
        logger.exception(
            "Failed to send briefing email",
            extra={"user_id": user_id},
        )


async def run_daily_briefing_job() -> dict[str, Any]:
    """Generate daily briefings for all active users whose briefing time has passed.

    For each user:
    1. Check if their local time has passed their configured briefing_time
    2. Check if today's briefing already exists (skip if so)
    3. Call BriefingService.generate_briefing (includes Scout signal data + notification)
    4. Optionally send a briefing-ready email

    Returns:
        Summary dict with users_checked, generated, skipped, and errors.
    """
    logger.info("Daily briefing job starting")

    users = await _get_active_users_with_preferences()

    if not users:
        logger.info("No active users found for daily briefing job")
        return {"users_checked": 0, "generated": 0, "skipped": 0, "errors": 0}

    briefing_service = BriefingService()
    generated = 0
    skipped = 0
    errors = 0

    for user in users:
        user_id = user["user_id"]
        tz_str = user["timezone"]
        briefing_time_str = str(user["briefing_time"])

        try:
            # Only generate if the user's local time has passed their briefing time
            if not _is_briefing_due(tz_str, briefing_time_str):
                skipped += 1
                continue

            # Determine "today" in the user's timezone
            user_today = _today_in_user_tz(tz_str)

            # Skip if briefing already exists
            if await _briefing_exists(user_id, user_today):
                skipped += 1
                continue

            # Consume queued insights (LOW-priority items from proactive pipeline)
            queued_insights = await _consume_briefing_queue(user_id)

            # Generate the briefing (this also creates an in-app notification)
            await briefing_service.generate_briefing(
                user_id=user_id,
                briefing_date=user_today,
                queued_insights=queued_insights if queued_insights else None,
            )
            generated += 1

            logger.info(
                "Generated daily briefing",
                extra={
                    "user_id": user_id,
                    "briefing_date": user_today.isoformat(),
                    "timezone": tz_str,
                    "queued_insights": len(queued_insights),
                },
            )

            # Create video briefing session if enabled
            await _maybe_create_video_briefing(user_id, user_today)

            # Send email notification if enabled
            if user.get("notification_email", True):
                await _send_briefing_email(
                    user_id=user_id,
                    full_name=user.get("full_name", ""),
                    briefing_date=user_today,
                )

        except Exception:
            errors += 1
            logger.exception(
                "Failed to generate briefing for user",
                extra={"user_id": user_id},
            )

    result = {
        "users_checked": len(users),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }

    logger.info("Daily briefing job completed", extra=result)
    return result


async def _consume_briefing_queue(user_id: str) -> list[dict[str, Any]]:
    """Consume unconsumed items from briefing_queue for this user.

    Marks all consumed items so they won't be included again.

    Args:
        user_id: The user's UUID.

    Returns:
        List of queued insight dicts.
    """
    try:
        db = SupabaseClient.get_client()

        result = (
            db.table("briefing_queue")
            .select("id, title, message, category, metadata")
            .eq("user_id", user_id)
            .eq("consumed", False)
            .order("created_at", desc=False)
            .limit(20)
            .execute()
        )

        items = result.data or []
        if not items:
            return []

        # Mark as consumed
        item_ids = [item["id"] for item in items]
        db.table("briefing_queue").update(
            {"consumed": True}
        ).in_("id", item_ids).execute()

        logger.info(
            "Consumed %d briefing queue items for user %s",
            len(items),
            user_id,
        )

        return items

    except Exception:
        logger.warning(
            "Failed to consume briefing queue for user %s",
            user_id,
            exc_info=True,
        )
        return []


async def _maybe_create_video_briefing(user_id: str, briefing_date: date) -> None:
    """Create a Tavus video briefing session if the user has it enabled.

    Args:
        user_id: The user's UUID.
        briefing_date: Date of the briefing.
    """
    try:
        db = SupabaseClient.get_client()

        prefs_result = (
            db.table("user_preferences")
            .select("video_briefing_enabled")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not prefs_result or not prefs_result.data:
            return

        if not prefs_result.data.get("video_briefing_enabled", False):
            return

        from src.services.briefing import BriefingService

        briefing_service = BriefingService()
        result = await briefing_service.create_video_briefing_session(user_id)

        if result.get("session_id"):
            logger.info(
                "Video briefing session created for daily briefing",
                extra={
                    "user_id": user_id,
                    "session_id": result["session_id"],
                    "briefing_date": briefing_date.isoformat(),
                },
            )

            # Create notification about video briefing
            from src.models.notification import NotificationType
            from src.services.notification_service import NotificationService

            await NotificationService.create_notification(
                user_id=user_id,
                type=NotificationType.VIDEO_SESSION_READY,
                title="Video Briefing Ready",
                message="Your morning video briefing is ready to watch.",
                link="/briefing",
                metadata={
                    "session_id": result["session_id"],
                    "briefing_date": briefing_date.isoformat(),
                },
            )

    except Exception:
        logger.warning(
            "Video briefing creation failed for user %s",
            user_id,
            exc_info=True,
        )


async def run_startup_briefing_check() -> dict[str, Any]:
    """Lightweight startup check that generates any missing briefings.

    Called once during app startup. Delegates to run_daily_briefing_job
    which already handles the "already exists" and timezone checks.

    Returns:
        Summary dict from run_daily_briefing_job.
    """
    logger.info("Running startup briefing check")
    return await run_daily_briefing_job()
