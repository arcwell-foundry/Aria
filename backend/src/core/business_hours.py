"""Shared business-hours gating utility for proactive pipeline jobs.

Provides timezone-aware business-hours checks and user timezone lookups
used across all scheduled proactive jobs.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"
DEFAULT_START_HOUR = 7
DEFAULT_END_HOUR = 20


def is_business_hours(
    timezone_str: str,
    start_hour: int = DEFAULT_START_HOUR,
    end_hour: int = DEFAULT_END_HOUR,
) -> bool:
    """Check if the current time is within business hours in the given timezone.

    Args:
        timezone_str: IANA timezone string (e.g. "America/New_York").
        start_hour: Start of business hours (inclusive), 24h format. Default 7.
        end_hour: End of business hours (exclusive), 24h format. Default 20.

    Returns:
        True if the current local time is between start_hour and end_hour.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except (KeyError, ValueError):
        logger.warning(
            "Invalid timezone '%s', falling back to UTC",
            timezone_str,
        )
        tz = ZoneInfo("UTC")

    local_now = datetime.now(tz)
    return start_hour <= local_now.hour < end_hour


def get_user_timezone(user_id: str) -> str:
    """Read the user's preferred timezone from user_preferences.

    Args:
        user_id: The user's UUID.

    Returns:
        IANA timezone string, or DEFAULT_TIMEZONE if not set.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("user_preferences")
            .select("timezone")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            tz = result.data.get("timezone")
            if tz:
                return str(tz)
    except Exception:
        logger.debug(
            "Failed to read timezone for user %s, using default",
            user_id,
        )

    return DEFAULT_TIMEZONE


def get_active_user_ids() -> list[str]:
    """Return user IDs for all users who completed onboarding.

    Shared helper used by proactive pipeline jobs that iterate over
    all active users.

    Returns:
        List of user_id strings.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )
        return [row["user_id"] for row in (result.data or [])]
    except Exception:
        logger.exception("Failed to fetch active user IDs")
        return []
