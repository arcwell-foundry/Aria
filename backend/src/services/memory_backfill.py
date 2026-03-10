"""Multi-user retroactive memory backfill.

Iterates over ALL users with data in ARIA and routes their historical
emails, calendar events, debriefs, and pipeline leads through the
universal memory_writer. Never hardcodes user IDs.

Usage:
    from src.services.memory_backfill import run_backfill
    totals = await run_backfill(db)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.services.memory_writer import write_memory

logger = logging.getLogger(__name__)


async def get_all_user_ids(db: Any) -> list[str]:
    """Return all user IDs that have data in ARIA.

    Uses email_scan_log, calendar_events, and meeting_debriefs as
    the source of truth -- never queries auth.users directly
    (RLS/permissions issue).

    Args:
        db: Supabase client instance.

    Returns:
        Deduplicated list of user ID strings.
    """
    user_ids: set[str] = set()

    for table in ("email_scan_log", "calendar_events", "meeting_debriefs"):
        try:
            result = (
                db.table(table)
                .select("user_id")
                .limit(10000)
                .execute()
            )
            for row in (result.data or []):
                uid = row.get("user_id")
                if uid:
                    user_ids.add(str(uid))
        except Exception:
            logger.exception("[Backfill] Failed to query user_ids from %s", table)

    return sorted(user_ids)


async def backfill_user(db: Any, user_id: str) -> dict[str, int]:
    """Run all backfills for a single user.

    Args:
        db: Supabase client instance.
        user_id: The user to backfill.

    Returns:
        Counts of items processed per category.
    """
    counts: dict[str, int] = {
        "emails": 0,
        "calendar_events": 0,
        "debriefs": 0,
        "leads": 0,
    }

    # GUARD: skip if already backfilled (check lead_memory_events)
    try:
        existing = (
            db.table("lead_memory_events")
            .select("id", count="exact")
            .eq("source", "email_scan")
            .limit(1)
            .execute()
        )
        if (existing.count or 0) > 10:
            logger.info("[Backfill] Already run for user %s, skipping", user_id)
            return counts
    except Exception:
        # Table might not exist or query might fail — continue with backfill
        pass

    # ----------------------------------------------------------------
    # 1. EMAIL BACKFILL
    # ----------------------------------------------------------------
    try:
        emails = (
            db.table("email_scan_log")
            .select("id, sender_email, sender_name, subject, snippet, category, urgency, confidence, scanned_at")
            .eq("user_id", user_id)
            .order("scanned_at")
            .execute()
        )
        rows = emails.data or []
        for i, row in enumerate(rows):
            await write_memory(db, user_id, "email_scanned", {
                "email_id": str(row.get("id", "")),
                "sender_email": row.get("sender_email") or "",
                "sender_name": row.get("sender_name") or "",
                "subject": row.get("subject") or "",
                "snippet": row.get("snippet") or "",
                "category": row.get("category") or "general",
                "urgency": row.get("urgency") or "normal",
                "confidence": float(row.get("confidence") or 0.7),
                "scanned_at": row["scanned_at"] if row.get("scanned_at") else datetime.now(UTC).isoformat(),
            })
            if (i + 1) % 50 == 0:
                logger.info("[Backfill] User %s: backfilled %d/%d emails", user_id, i + 1, len(rows))
        counts["emails"] = len(rows)
    except Exception:
        logger.exception("[Backfill] Email backfill failed for user %s", user_id)

    # ----------------------------------------------------------------
    # 2. CALENDAR BACKFILL
    # ----------------------------------------------------------------
    try:
        events = (
            db.table("calendar_events")
            .select("id, title, start_time, attendees, external_company")
            .eq("user_id", user_id)
            .order("start_time")
            .execute()
        )
        for row in (events.data or []):
            attendees = row.get("attendees") or []
            attendee_strs: list[str] = []
            attendee_emails: list[str] = []

            if isinstance(attendees, list):
                for a in attendees:
                    if isinstance(a, dict):
                        name = a.get("displayName") or a.get("email", "")
                        email = a.get("email", "")
                        if name:
                            attendee_strs.append(name)
                        if email:
                            attendee_emails.append(email)
                    elif isinstance(a, str):
                        attendee_strs.append(a)
                        attendee_emails.append(a)

            await write_memory(db, user_id, "calendar_event_synced", {
                "calendar_event_id": str(row.get("id", "")),
                "title": row.get("title") or "Untitled meeting",
                "attendees_str": ", ".join(filter(None, attendee_strs)) or row.get("external_company") or "",
                "time": row["start_time"] if row.get("start_time") else "",
                "attendee_emails": attendee_emails,
            })
            counts["calendar_events"] += 1
    except Exception:
        logger.exception("[Backfill] Calendar backfill failed for user %s", user_id)

    # ----------------------------------------------------------------
    # 3. DEBRIEF BACKFILL
    # ----------------------------------------------------------------
    try:
        debriefs = (
            db.table("meeting_debriefs")
            .select("id, meeting_title, meeting_time, summary, action_items, next_steps, stakeholder_signals, attendee_emails")
            .eq("user_id", user_id)
            .order("meeting_time", desc=False)
            .execute()
        )
        for row in (debriefs.data or []):
            await write_memory(db, user_id, "meeting_debrief_approved", {
                "debrief_id": str(row.get("id", "")),
                "meeting_title": row.get("meeting_title") or "Meeting",
                "summary": row.get("summary") or "",
                "action_items": row.get("action_items") or [],
                "next_steps": row.get("next_steps") or [],
                "stakeholder_signals": row.get("stakeholder_signals") or {},
                "attendee_emails": list(row.get("attendee_emails") or []),
                "meeting_time": row["meeting_time"] if row.get("meeting_time") else datetime.now(UTC).isoformat(),
            })
            counts["debriefs"] += 1
    except Exception:
        logger.exception("[Backfill] Debrief backfill failed for user %s", user_id)

    # ----------------------------------------------------------------
    # 4. PIPELINE LEADS BACKFILL (if table exists)
    # ----------------------------------------------------------------
    try:
        # Test if table exists by querying with limit 0
        test = db.table("pipeline_leads").select("id").eq("user_id", user_id).limit(1).execute()
        # If we get here, the table exists
        leads = (
            db.table("pipeline_leads")
            .select("id, company_name, contact_name, title, source")
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )
        for row in (leads.data or []):
            await write_memory(db, user_id, "lead_created", {
                "company": row.get("company_name") or "",
                "contact_name": row.get("contact_name") or "",
                "title": row.get("title") or "",
                "source": row.get("source") or "pipeline",
            })
            counts["leads"] += 1
    except Exception:
        # Table might not exist — that's fine
        logger.debug("[Backfill] pipeline_leads not available for user %s", user_id)

    return counts


async def run_backfill(db: Any) -> dict[str, int]:
    """Entry point. Run backfill for ALL users with data in ARIA.

    Args:
        db: Supabase client instance.

    Returns:
        Aggregate counts across all users.
    """
    user_ids = await get_all_user_ids(db)
    logger.info("[Backfill] Starting memory backfill for %d users", len(user_ids))

    total: dict[str, int] = {
        "users": len(user_ids),
        "emails": 0,
        "calendar_events": 0,
        "debriefs": 0,
        "leads": 0,
    }

    for user_id in user_ids:
        try:
            counts = await backfill_user(db, user_id)
            for k, v in counts.items():
                total[k] += v
        except Exception:
            logger.exception("[Backfill] Failed for user %s", user_id)
            continue

    logger.info("[Backfill] Complete: %s", total)
    return total
