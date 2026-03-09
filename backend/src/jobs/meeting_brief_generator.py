"""Background job for pre-meeting brief generation.

Scans the calendar_events table directly to find meetings needing briefs,
creates pending brief stubs, enriches attendee profiles, and generates
brief content. Runs on a cron schedule via the scheduler.

Key design:
- Queries ALL users dynamically (no hardcoded user_ids)
- Looks ahead 48 hours and back 2 hours
- Filters out buffer/internal events and events with 0 external attendees
- Uses calendar_events.id (UUID) as calendar_event_id, not external_id
- Deduplicates against existing meeting_briefs rows
- Enriches attendees via Exa (non-blocking) before generating brief
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.services.meeting_brief import MeetingBriefService

logger = logging.getLogger(__name__)

# Titles containing these substrings are skipped (case-insensitive)
_SKIP_TITLE_SUBSTRINGS = ["[", "buffer"]


def _should_skip_event(event: dict[str, Any]) -> bool:
    """Check whether a calendar event should be skipped for brief generation.

    Skips buffer events (titles containing '[' or 'buffer') and events
    with zero external attendees.

    Args:
        event: Calendar event row from database.

    Returns:
        True if the event should be skipped.
    """
    title = (event.get("title") or "").lower()
    for skip in _SKIP_TITLE_SUBSTRINGS:
        if skip.lower() in title:
            return True

    # Skip events with no attendees
    attendees = event.get("attendees")
    if not attendees:
        return True
    if isinstance(attendees, list) and len(attendees) == 0:
        return True

    return False


def _extract_attendee_emails(attendees: Any) -> list[str]:
    """Extract email addresses from the attendees JSONB field.

    The attendees field in calendar_events is JSONB and can be:
    - A list of strings (emails)
    - A list of dicts with 'email' key (Google/Outlook format)

    Args:
        attendees: Raw attendees value from database.

    Returns:
        List of email address strings.
    """
    if not attendees:
        return []

    emails: list[str] = []
    if isinstance(attendees, list):
        for item in attendees:
            if isinstance(item, str) and "@" in item:
                emails.append(item.lower())
            elif isinstance(item, dict):
                email = item.get("email") or item.get("emailAddress", "")
                if email and "@" in email:
                    emails.append(email.lower())
    return emails


async def find_calendar_events_needing_briefs(
    hours_ahead: int = 48,
    hours_back: int = 2,
) -> list[dict[str, Any]]:
    """Find calendar events that need meeting briefs.

    Scans the calendar_events table for ALL users. Returns events within
    the time window that pass filters and don't already have a brief.

    Args:
        hours_ahead: Hours to look ahead from now (default 48).
        hours_back: Hours to look back from now (default 2).

    Returns:
        List of calendar event dicts that need briefs generated.
    """
    db = SupabaseClient.get_client()

    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours_back)
    window_end = now + timedelta(hours=hours_ahead)

    # Fetch calendar events in the window for all users
    result = (
        db.table("calendar_events")
        .select("id, user_id, title, start_time, end_time, attendees, source, external_id")
        .gte("start_time", window_start.isoformat())
        .lte("start_time", window_end.isoformat())
        .order("start_time", desc=False)
        .execute()
    )

    all_events = cast(list[dict[str, Any]], result.data or [])
    logger.info(
        "Calendar events in window",
        extra={
            "total_events": len(all_events),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )

    if not all_events:
        return []

    # Collect all event UUIDs to check which already have briefs
    event_ids = [str(e["id"]) for e in all_events]

    # Query existing briefs to avoid duplicates
    # Supabase .in_() has limits, so batch if needed
    existing_event_ids: set[str] = set()
    batch_size = 50
    for i in range(0, len(event_ids), batch_size):
        batch = event_ids[i : i + batch_size]
        existing_result = (
            db.table("meeting_briefs")
            .select("calendar_event_id")
            .in_("calendar_event_id", batch)
            .execute()
        )
        for row in existing_result.data or []:
            existing_event_ids.add(str(row["calendar_event_id"]))

    # Filter events
    events_needing_briefs: list[dict[str, Any]] = []
    for event in all_events:
        event_id = str(event["id"])

        # Already has a brief
        if event_id in existing_event_ids:
            continue

        # Skip buffer/internal events
        if _should_skip_event(event):
            continue

        events_needing_briefs.append(event)

    logger.info(
        "Events needing briefs after filtering",
        extra={
            "needing_briefs": len(events_needing_briefs),
            "already_have_briefs": len(existing_event_ids),
            "skipped_filters": len(all_events) - len(events_needing_briefs) - len(existing_event_ids),
        },
    )

    return events_needing_briefs


async def _enrich_attendees(
    emails: list[str],
) -> dict[str, dict[str, Any]]:
    """Enrich attendee profiles: check cache first, then Exa for missing.

    Non-blocking — if enrichment fails for any attendee, we still return
    whatever data is available.

    Args:
        emails: List of attendee email addresses.

    Returns:
        Dict mapping email to profile data.
    """
    if not emails:
        return {}

    from src.services.attendee_profile import AttendeeProfileService

    profile_service = AttendeeProfileService()

    # Step 1: Check cache for all emails
    cached_profiles = await profile_service.get_profiles_batch(emails)

    # Step 2: Find emails not in cache or stale
    emails_to_enrich: list[str] = []
    for email in emails:
        if email not in cached_profiles:
            emails_to_enrich.append(email)
        else:
            # Check if stale (older than 7 days)
            if await profile_service.is_stale(email, max_age_days=7):
                emails_to_enrich.append(email)

    if not emails_to_enrich:
        logger.info("All attendee profiles cached", extra={"count": len(cached_profiles)})
        return cached_profiles

    # Step 3: Enrich missing profiles via Exa
    logger.info(
        "Enriching attendee profiles",
        extra={"cached": len(cached_profiles), "to_enrich": len(emails_to_enrich)},
    )

    async def _enrich_single(email: str) -> tuple[str, dict[str, Any] | None]:
        """Enrich a single attendee by email via Exa."""
        try:
            from src.agents.capabilities.enrichment_providers.exa_provider import (
                ExaEnrichmentProvider,
            )

            exa = ExaEnrichmentProvider()

            # Use email domain to guess company
            domain = email.split("@")[1] if "@" in email else ""
            company_hint = domain.split(".")[0].title() if domain else ""

            # Search by email to find profile
            person = await exa.search_person(
                name=email.split("@")[0].replace(".", " ").title(),
                company=company_hint,
                role="",
            )

            if person and (person.name or person.title or person.company):
                # Cache the result
                profile = await profile_service.upsert_profile(
                    email=email,
                    name=person.name or None,
                    title=person.title or None,
                    company=person.company or company_hint or None,
                    linkedin_url=person.linkedin_url or None,
                    profile_data={
                        "bio": person.bio,
                        "web_mentions": person.web_mentions[:3],
                        "social_profiles": person.social_profiles,
                    },
                    research_status="completed",
                )
                return email, profile
            else:
                # Mark as not found so we don't retry too often
                profile = await profile_service.upsert_profile(
                    email=email,
                    research_status="not_found",
                )
                return email, profile

        except Exception as exc:
            logger.warning(
                "Failed to enrich attendee %s: %s",
                email,
                exc,
            )
            return email, None

    # Run enrichment concurrently with asyncio.gather
    enrichment_tasks = [_enrich_single(email) for email in emails_to_enrich[:10]]  # Cap at 10
    results = await asyncio.gather(*enrichment_tasks, return_exceptions=True)

    # Merge enriched profiles with cached
    all_profiles = dict(cached_profiles)
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Enrichment task failed: %s", result)
            continue
        email, profile = result
        if profile:
            all_profiles[email] = profile

    return all_profiles


async def run_meeting_brief_job(
    hours_ahead: int = 48,
    hours_back: int = 2,
) -> dict[str, Any]:
    """Run the meeting brief generation job.

    Scans calendar_events for all users, creates pending brief stubs,
    enriches attendees, and generates brief content.

    Args:
        hours_ahead: Hours to look ahead (default 48).
        hours_back: Hours to look back (default 2).

    Returns:
        Summary dict with events_found, briefs_created, briefs_generated, errors.
    """
    events = await find_calendar_events_needing_briefs(
        hours_ahead=hours_ahead,
        hours_back=hours_back,
    )

    db = SupabaseClient.get_client()
    service = MeetingBriefService()
    briefs_created = 0
    briefs_generated = 0
    errors = 0

    for event in events:
        event_id = str(event["id"])
        user_id = str(event["user_id"])
        title = event.get("title") or "Untitled Meeting"
        start_time = event.get("start_time", "")
        attendee_emails = _extract_attendee_emails(event.get("attendees"))

        try:
            # Parse start_time
            if isinstance(start_time, str):
                meeting_time = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00")
                )
            else:
                meeting_time = start_time

            # Step 1: Create pending brief stub using UUID as calendar_event_id
            brief = await service.upsert_brief(
                user_id=user_id,
                calendar_event_id=event_id,
                meeting_title=title,
                meeting_time=meeting_time,
                attendees=attendee_emails,
            )
            brief_id = str(brief["id"])
            briefs_created += 1

            logger.info(
                "Created pending brief for calendar event",
                extra={
                    "brief_id": brief_id,
                    "event_id": event_id,
                    "user_id": user_id,
                    "title": title,
                    "attendee_count": len(attendee_emails),
                },
            )

            # Step 2: Enrich attendees (non-blocking)
            enriched_profiles = await _enrich_attendees(attendee_emails)

            # Step 3: Generate brief content
            result = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            if result is not None:
                # Ensure enriched attendee profiles are stored in brief_content
                if enriched_profiles:
                    brief_content = result
                    brief_content["attendees"] = {
                        email: {
                            "email": email,
                            "name": p.get("name"),
                            "title": p.get("title"),
                            "company": p.get("company"),
                            "linkedin_url": p.get("linkedin_url"),
                            "profile_data": p.get("profile_data"),
                        }
                        for email, p in enriched_profiles.items()
                    }
                    # Update the brief with enriched attendee data
                    db.table("meeting_briefs").update(
                        {"brief_content": brief_content}
                    ).eq("id", brief_id).execute()

                briefs_generated += 1
                logger.info(
                    "Generated meeting brief",
                    extra={
                        "brief_id": brief_id,
                        "user_id": user_id,
                        "title": title,
                        "enriched_attendees": len(enriched_profiles),
                    },
                )

                # Record activity
                try:
                    from src.services.activity_service import ActivityService

                    await ActivityService().record(
                        user_id=user_id,
                        agent="analyst",
                        activity_type="meeting_prepped",
                        title=f"Prepared for: {title}",
                        description=(
                            f"Generated meeting brief for '{title}' "
                            f"with {len(enriched_profiles)} enriched attendee profiles."
                        ),
                        confidence=0.9,
                        related_entity_type="meeting_brief",
                        related_entity_id=brief_id,
                        metadata={
                            "meeting_title": title,
                            "attendee_count": len(attendee_emails),
                            "enriched_count": len(enriched_profiles),
                        },
                    )
                except Exception:
                    logger.debug("Failed to record meeting_prepped activity", exc_info=True)
            else:
                errors += 1
                logger.warning(
                    "Brief generation returned None",
                    extra={"brief_id": brief_id, "user_id": user_id},
                )
        except Exception as e:
            errors += 1
            logger.exception(
                "Failed to generate meeting brief for event",
                extra={
                    "event_id": event_id,
                    "user_id": user_id,
                    "error": str(e),
                },
            )

    result_summary = {
        "events_found": len(events),
        "briefs_created": briefs_created,
        "briefs_generated": briefs_generated,
        "errors": errors,
        "hours_ahead": hours_ahead,
        "hours_back": hours_back,
    }

    logger.info("Meeting brief job completed", extra=result_summary)
    return result_summary


async def backfill_meeting_briefs() -> dict[str, Any]:
    """One-time backfill: generate briefs for all calendar events with attendees.

    Queries all calendar events that have external attendees and don't
    already have briefs. No time window restriction.

    Returns:
        Summary dict with events_found, briefs_created, briefs_generated, errors.
    """
    db = SupabaseClient.get_client()

    # Fetch all calendar events with attendees
    result = (
        db.table("calendar_events")
        .select("id, user_id, title, start_time, end_time, attendees, source, external_id")
        .order("start_time", desc=False)
        .execute()
    )

    all_events = cast(list[dict[str, Any]], result.data or [])
    logger.info("Backfill: found %d total calendar events", len(all_events))

    # Filter: must have attendees, skip buffer events
    eligible_events: list[dict[str, Any]] = []
    for event in all_events:
        if _should_skip_event(event):
            continue
        # Extra filter: skip BiotechTuesday events
        title = (event.get("title") or "").lower()
        if title.startswith("biotechtuesday"):
            continue
        eligible_events.append(event)

    # Check which already have briefs
    event_ids = [str(e["id"]) for e in eligible_events]
    existing_event_ids: set[str] = set()
    batch_size = 50
    for i in range(0, len(event_ids), batch_size):
        batch = event_ids[i : i + batch_size]
        existing_result = (
            db.table("meeting_briefs")
            .select("calendar_event_id")
            .in_("calendar_event_id", batch)
            .execute()
        )
        for row in existing_result.data or []:
            existing_event_ids.add(str(row["calendar_event_id"]))

    events_to_process = [
        e for e in eligible_events if str(e["id"]) not in existing_event_ids
    ]

    logger.info(
        "Backfill: %d events eligible, %d already have briefs, %d to process",
        len(eligible_events),
        len(existing_event_ids),
        len(events_to_process),
    )

    service = MeetingBriefService()
    briefs_created = 0
    briefs_generated = 0
    errs = 0

    for event in events_to_process:
        event_id = str(event["id"])
        user_id = str(event["user_id"])
        title = event.get("title") or "Untitled Meeting"
        start_time = event.get("start_time", "")
        attendee_emails = _extract_attendee_emails(event.get("attendees"))

        try:
            if isinstance(start_time, str):
                meeting_time = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00")
                )
            else:
                meeting_time = start_time

            brief = await service.upsert_brief(
                user_id=user_id,
                calendar_event_id=event_id,
                meeting_title=title,
                meeting_time=meeting_time,
                attendees=attendee_emails,
            )
            brief_id = str(brief["id"])
            briefs_created += 1

            # Enrich attendees
            enriched_profiles = await _enrich_attendees(attendee_emails)

            # Generate content
            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            if content is not None:
                if enriched_profiles:
                    content["attendees"] = {
                        email: {
                            "email": email,
                            "name": p.get("name"),
                            "title": p.get("title"),
                            "company": p.get("company"),
                            "linkedin_url": p.get("linkedin_url"),
                            "profile_data": p.get("profile_data"),
                        }
                        for email, p in enriched_profiles.items()
                    }
                    db.table("meeting_briefs").update(
                        {"brief_content": content}
                    ).eq("id", brief_id).execute()

                briefs_generated += 1
                logger.info(
                    "Backfill: generated brief for '%s'",
                    title,
                    extra={"brief_id": brief_id, "event_id": event_id},
                )
            else:
                errs += 1
        except Exception as e:
            errs += 1
            logger.exception(
                "Backfill: failed for event %s: %s",
                event_id,
                e,
            )

    summary = {
        "events_found": len(events_to_process),
        "briefs_created": briefs_created,
        "briefs_generated": briefs_generated,
        "errors": errs,
    }

    logger.info("Backfill complete", extra=summary)
    return summary
