"""Post-meeting debrief prompt job.

Runs every 5 minutes via APScheduler. Checks for calendar meetings that
ended in the last 10 minutes, filters to external-attendee meetings
without existing debriefs, and pushes notifications + WebSocket events
so the user is proactively prompted to debrief.

Idempotent: uses event_log with event_type='meeting_ended_debrief_prompt'
to avoid re-notifying for the same meeting.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from src.core.ws import ws_manager
from src.db.supabase import SupabaseClient
from src.models.notification import NotificationType
from src.models.ws_events import WSEvent
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Domains to exclude when checking for external attendees
_PLATFORM_DOMAINS = {"@lu.ma", "@calendar.google.com", "@resource.calendar.google.com"}

# How far back to look for ended meetings (minutes)
_LOOKBACK_MINUTES = 10


def _extract_external_attendees(
    attendees: list[Any] | str | None,
    user_email: str | None,
) -> list[str]:
    """Return external attendee emails, filtering out the user and platform domains.

    Args:
        attendees: Raw attendees from calendar_events (JSONB or string).
        user_email: The user's own email address (excluded from results).

    Returns:
        List of external attendee email strings.
    """
    if not attendees:
        return []

    if isinstance(attendees, str):
        try:
            attendees = json.loads(attendees)
        except (ValueError, TypeError):
            return []

    if not isinstance(attendees, list):
        return []

    user_email_lower = (user_email or "").lower().strip()
    external: list[str] = []

    for att in attendees:
        email = ""
        if isinstance(att, str):
            email = att.strip().lower()
        elif isinstance(att, dict):
            # Google format: {"email": "..."} or Outlook: {"emailAddress": {"address": "..."}}
            email = (
                att.get("email", "")
                or (att.get("emailAddress", {}) or {}).get("address", "")
            ).strip().lower()

        if not email:
            continue
        if email == user_email_lower:
            continue
        if any(email.endswith(domain) for domain in _PLATFORM_DOMAINS):
            continue
        external.append(email)

    return external


def _build_debrief_link(event: dict[str, Any], external_emails: list[str]) -> str:
    """Build the /?debrief=... query string link for a meeting.

    Args:
        event: Calendar event dict with id, title, start_time, end_time.
        external_emails: List of external attendee email addresses.

    Returns:
        URL path with query parameters for the debrief.
    """
    params = (
        f"debrief={event['id']}"
        f"&title={quote(event.get('title', ''), safe='')}"
        f"&start_time={quote(event.get('start_time', ''), safe='')}"
        f"&end_time={quote(event.get('end_time', ''), safe='')}"
        f"&attendee_emails={quote(','.join(external_emails), safe='')}"
    )
    return f"/?{params}"


async def run_meeting_end_check() -> dict[str, Any]:
    """Check for recently ended meetings and prompt debriefs.

    For each active user:
    1. Query calendar_events ending in the last 10 minutes
    2. Filter to real meetings with external attendees
    3. Skip if debrief already exists or already notified (event_log)
    4. Create notification, WebSocket event, event_log entry, action queue item

    Returns:
        Summary dict with processing statistics.
    """
    stats: dict[str, Any] = {
        "users_checked": 0,
        "meetings_found": 0,
        "notifications_sent": 0,
        "already_debriefed": 0,
        "already_notified": 0,
        "no_external_attendees": 0,
        "errors": 0,
    }

    try:
        db = SupabaseClient.get_client()

        # Find active users (completed onboarding)
        users_response = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )
        user_ids = [row["user_id"] for row in (users_response.data or [])]

        if not user_ids:
            logger.debug("Meeting end check: no active users found")
            return stats

        now = datetime.now(UTC)
        lookback = now - timedelta(minutes=_LOOKBACK_MINUTES)

        for user_id in user_ids:
            stats["users_checked"] += 1
            try:
                await _check_user_meetings(
                    db, user_id, lookback.isoformat(), now.isoformat(), stats
                )
            except Exception:
                logger.warning(
                    "Meeting end check failed for user %s",
                    user_id,
                    exc_info=True,
                )
                stats["errors"] += 1

    except Exception:
        logger.exception("Meeting end check job failed")

    if stats["notifications_sent"] > 0:
        logger.info(
            "Meeting end check complete: %d notifications sent across %d users",
            stats["notifications_sent"],
            stats["users_checked"],
        )
    else:
        logger.debug("Meeting end check complete: no new debrief prompts")

    return stats


async def _check_user_meetings(
    db: Any,
    user_id: str,
    lookback_iso: str,
    now_iso: str,
    stats: dict[str, Any],
) -> None:
    """Check a single user's recently ended meetings.

    Args:
        db: Supabase client.
        user_id: The user's UUID.
        lookback_iso: ISO timestamp for the lookback window start.
        now_iso: ISO timestamp for now.
        stats: Mutable stats dict to increment.
    """
    # Get user's email for attendee filtering
    user_email = await _get_user_email(db, user_id)

    # Query meetings that ended in the lookback window
    events_response = (
        db.table("calendar_events")
        .select("id, title, start_time, end_time, attendees, external_company")
        .eq("user_id", user_id)
        .gte("end_time", lookback_iso)
        .lte("end_time", now_iso)
        .execute()
    )

    events = events_response.data or []

    for event in events:
        title = event.get("title") or ""

        # Skip bracket-prefixed system events (buffers, padding)
        if title.startswith("["):
            continue

        stats["meetings_found"] += 1

        # Check for external attendees
        external_emails = _extract_external_attendees(
            event.get("attendees"), user_email
        )
        if not external_emails:
            stats["no_external_attendees"] += 1
            continue

        event_id = event["id"]

        # Check if already notified (idempotency via event_log)
        already_notified = (
            db.table("event_log")
            .select("id")
            .eq("user_id", user_id)
            .eq("event_type", "meeting_ended_debrief_prompt")
            .eq("source_id", event_id)
            .limit(1)
            .execute()
        )
        if already_notified.data:
            stats["already_notified"] += 1
            continue

        # Check if debrief already exists
        debrief_exists = (
            db.table("meeting_debriefs")
            .select("id")
            .eq("user_id", user_id)
            .eq("meeting_id", event_id)
            .limit(1)
            .execute()
        )
        if debrief_exists.data:
            stats["already_debriefed"] += 1
            continue

        # All checks passed — send notification
        await _send_debrief_prompt(db, user_id, event, external_emails)
        stats["notifications_sent"] += 1


async def _get_user_email(db: Any, user_id: str) -> str | None:
    """Get the user's email from user_profiles.

    Args:
        db: Supabase client.
        user_id: The user's UUID.

    Returns:
        The user's email address or None.
    """
    try:
        response = (
            db.table("user_profiles")
            .select("email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0].get("email")
    except Exception:
        logger.debug("Could not fetch email for user %s", user_id)
    return None


async def _send_debrief_prompt(
    db: Any,
    user_id: str,
    event: dict[str, Any],
    external_emails: list[str],
) -> None:
    """Create notification, WebSocket event, event_log, and action queue entry.

    Args:
        db: Supabase client.
        user_id: The user's UUID.
        event: Calendar event dict.
        external_emails: List of external attendee emails.
    """
    meeting_title = event.get("title", "Meeting")
    event_id = event["id"]
    debrief_link = _build_debrief_link(event, external_emails)

    # Human-readable attendee names (use email prefix as name)
    attendee_names = ", ".join(
        email.split("@")[0].replace(".", " ").title()
        for email in external_emails[:3]
    )
    if len(external_emails) > 3:
        attendee_names += f" +{len(external_emails) - 3} more"

    message = (
        f"Your meeting with {attendee_names} just ended. "
        "Ready to capture a quick debrief?"
    )

    # 1. Create notification
    try:
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.MEETING_DEBRIEF_PROMPT,
            title=f"Meeting ended: {meeting_title}",
            message=message,
            link=debrief_link,
            metadata={
                "meeting_id": event_id,
                "meeting_title": meeting_title,
                "attendees": external_emails,
            },
        )
    except Exception:
        logger.warning(
            "Failed to create debrief notification for meeting %s",
            event_id,
            exc_info=True,
        )

    # 2. Push via WebSocket
    try:
        ws_event = WSEvent(
            type="debrief.prompt",
            data={
                "meeting_id": event_id,
                "meeting_title": meeting_title,
                "attendees": attendee_names,
                "link": debrief_link,
            },
        )
        await ws_manager.send_to_user(user_id, ws_event)
    except Exception:
        logger.debug(
            "Could not send debrief WebSocket event for user %s (not connected?)",
            user_id,
        )

    # 3. Log to event_log for idempotency
    try:
        db.table("event_log").insert({
            "user_id": user_id,
            "event_type": "meeting_ended_debrief_prompt",
            "event_source": "calendar",
            "source_id": event_id,
            "payload": {
                "meeting_title": meeting_title,
                "attendees": external_emails,
                "link": debrief_link,
            },
            "status": "processed",
        }).execute()
    except Exception:
        logger.warning(
            "Failed to log debrief prompt event for meeting %s",
            event_id,
            exc_info=True,
        )

    # 4. Create action queue entry
    try:
        db.table("aria_action_queue").insert({
            "user_id": user_id,
            "agent": "operator",
            "action_type": "debrief",
            "title": f"Debrief: {meeting_title}",
            "description": (
                f"Your meeting with {attendee_names} just ended. "
                "Capture outcomes, commitments, and next steps."
            ),
            "risk_level": "low",
            "status": "pending",
            "payload": {
                "meeting_id": event_id,
                "meeting_title": meeting_title,
                "attendees": external_emails,
                "link": debrief_link,
            },
        }).execute()
    except Exception:
        logger.warning(
            "Failed to create action queue entry for meeting %s",
            event_id,
            exc_info=True,
        )

    logger.info(
        "Debrief prompt sent for meeting '%s'",
        meeting_title,
        extra={
            "user_id": user_id,
            "meeting_id": event_id,
            "attendees": external_emails,
        },
    )
