"""Meeting bot dispatcher — sends MeetingBaaS bots to join upcoming meetings.

Runs every 5 minutes via scheduler. Scans calendar_events for meetings
starting within the next 30 minutes that have external attendees, extracts
meeting URLs (Zoom/Teams) from metadata, and dispatches a bot via MeetingBaaS.
"""

import logging
import re
from datetime import datetime, timezone

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Regex patterns for extracting meeting URLs from text
ZOOM_URL_PATTERN = re.compile(
    r"https?://[\w.-]*zoom\.us/[jw]/\d+[^\s<>\"']*",
    re.IGNORECASE,
)
TEAMS_URL_PATTERN = re.compile(
    r"https?://teams\.microsoft\.com/l/meetup-join/[^\s<>\"']+",
    re.IGNORECASE,
)


def _extract_meeting_url(metadata: dict | None, title: str | None = None) -> str | None:
    """Extract a Zoom or Teams meeting URL from calendar event metadata.

    Checks the location field first, then the description field.

    Args:
        metadata: The calendar event metadata JSONB.
        title: Optional event title (not used for extraction, just logging).

    Returns:
        Meeting URL string or None if not found.
    """
    if not metadata:
        return None

    # Check location first (most common place for meeting URLs)
    for field in ("location", "description"):
        text = metadata.get(field) or ""
        if not text:
            continue

        # Try Zoom
        match = ZOOM_URL_PATTERN.search(text)
        if match:
            return match.group(0)

        # Try Teams
        match = TEAMS_URL_PATTERN.search(text)
        if match:
            return match.group(0)

    return None


async def run_meeting_bot_dispatcher() -> dict:
    """Dispatch MeetingBaaS bots for upcoming meetings.

    Queries calendar_events for meetings starting within the next 30 minutes
    that have external attendees and no existing meeting_sessions row.

    Returns:
        Dict with events_checked, bots_dispatched, errors counts.
    """
    from src.integrations.meetingbaas.client import MeetingBaaSError, get_meetingbaas_client

    db = SupabaseClient.get_client()
    client = get_meetingbaas_client()

    now = datetime.now(timezone.utc)
    window_end = now.isoformat()
    # Look 30 minutes ahead
    from datetime import timedelta

    window_end_ts = (now + timedelta(minutes=30)).isoformat()

    result = {
        "events_checked": 0,
        "bots_dispatched": 0,
        "skipped_no_url": 0,
        "skipped_existing": 0,
        "errors": 0,
    }

    try:
        # Find calendar events starting in the next 30 minutes
        # with at least 2 attendees (external meeting signal)
        events_resp = (
            db.table("calendar_events")
            .select("id, user_id, title, start_time, attendees, metadata")
            .gte("start_time", window_end)
            .lte("start_time", window_end_ts)
            .execute()
        )

        events = events_resp.data or []
        result["events_checked"] = len(events)

        if not events:
            return result

        # Filter to events with external attendees (>1 attendee)
        external_events = []
        for event in events:
            attendees = event.get("attendees") or []
            if len(attendees) > 1:
                external_events.append(event)

        if not external_events:
            return result

        # Check which events already have meeting_sessions rows
        event_ids = [e["id"] for e in external_events]
        existing_resp = (
            db.table("meeting_sessions")
            .select("calendar_event_id")
            .in_("calendar_event_id", event_ids)
            .execute()
        )
        existing_event_ids = {row["calendar_event_id"] for row in (existing_resp.data or [])}

        for event in external_events:
            event_id = event["id"]
            user_id = event["user_id"]

            if event_id in existing_event_ids:
                result["skipped_existing"] += 1
                continue

            # Extract meeting URL
            meeting_url = _extract_meeting_url(event.get("metadata"), event.get("title"))
            if not meeting_url:
                result["skipped_no_url"] += 1
                logger.debug(
                    "No meeting URL found for event %s: %s",
                    event_id,
                    event.get("title"),
                )
                continue

            # Get user's first name for bot display name
            user_first_name = "Your"
            try:
                profile_resp = (
                    db.table("user_profiles")
                    .select("full_name")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if profile_resp.data and profile_resp.data[0].get("full_name"):
                    user_first_name = profile_resp.data[0]["full_name"].split()[0]
            except Exception:
                logger.debug("Could not fetch user profile for %s", user_id)

            bot_name = f"ARIA — {user_first_name}'s AI Colleague"

            try:
                from src.core.config import settings as _settings

                bot_response = await client.create_bot(
                    meeting_url=meeting_url,
                    bot_name=bot_name,
                    webhook_url=_settings.MEETINGBAAS_WEBHOOK_URL,
                )
                bot_id = bot_response.get("bot_id")

                # Insert meeting_sessions row
                db.table("meeting_sessions").insert(
                    {
                        "calendar_event_id": event_id,
                        "user_id": user_id,
                        "bot_id": bot_id,
                        "status": "joining",
                        "meeting_url": meeting_url,
                        "meeting_title": event.get("title"),
                        "started_at": now.isoformat(),
                    }
                ).execute()

                result["bots_dispatched"] += 1
                logger.info(
                    "Bot dispatched for meeting",
                    extra={
                        "calendar_event_id": event_id,
                        "user_id": user_id,
                        "bot_id": bot_id,
                        "meeting_title": event.get("title"),
                    },
                )

                # Route to universal memory writer
                try:
                    from src.services.memory_writer import write_memory

                    attendees = event.get("attendees") or []
                    attendee_emails = []
                    for att in attendees:
                        if isinstance(att, str):
                            attendee_emails.append(att)
                        elif isinstance(att, dict):
                            email = att.get("email")
                            if email:
                                attendee_emails.append(email)

                    await write_memory(db, user_id, "calendar_event_synced", {
                        "calendar_event_id": event_id,
                        "title": event.get("title"),
                        "attendee_emails": attendee_emails,
                        "start_time": event.get("start_time"),
                    })
                except Exception:
                    logger.exception("Failed to route calendar_event_synced via memory_writer")

            except MeetingBaaSError as e:
                result["errors"] += 1
                logger.error(
                    "Failed to dispatch bot for event %s: %s",
                    event_id,
                    e,
                    exc_info=True,
                )
            except Exception as e:
                result["errors"] += 1
                logger.error(
                    "Unexpected error dispatching bot for event %s: %s",
                    event_id,
                    e,
                    exc_info=True,
                )

    except Exception:
        logger.exception("Meeting bot dispatcher run failed")

    return result
