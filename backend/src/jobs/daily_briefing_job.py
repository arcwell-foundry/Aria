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
    4. Write to memory_briefing_queue for delivery tracking
    5. Create video briefing session if enabled, wire URL back to queue and daily_briefings
    6. Optionally send a briefing-ready email

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
            content = await briefing_service.generate_briefing(
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

            # Enrich signals from market_signals table
            try:
                db = SupabaseClient.get_client()
                enriched = _get_enriched_signals(db, user_id)
                signals = content.get("signals", {})
                if isinstance(signals, dict):
                    signals["competitive_intel"] = enriched["competitor"]
                    signals["company_news"] = enriched["lead_related"]
                    signals["market_trends"] = enriched["market"]
                    content["signals"] = signals
                logger.info(
                    "Enriched briefing signals",
                    extra={
                        "user_id": user_id,
                        "competitor": len(enriched["competitor"]),
                        "lead_related": len(enriched["lead_related"]),
                        "market": len(enriched["market"]),
                    },
                )
            except Exception as enrich_err:
                logger.warning(
                    "Failed to enrich signals: %s",
                    enrich_err,
                    extra={"user_id": user_id},
                )

            # Generate rich spoken briefing script via LLM
            try:
                first_name = (user.get("full_name") or "").split()[0] or "there"
                tavus_script = await _generate_tavus_script(content, user_name=first_name)
                content["tavus_script"] = tavus_script
                logger.info(
                    "Generated tavus_script",
                    extra={"user_id": user_id, "script_chars": len(tavus_script)},
                )

                # Write script to dedicated column on daily_briefings
                try:
                    db = SupabaseClient.get_client()
                    db.table("daily_briefings").update({
                        "tavus_script": tavus_script,
                        "tavus_status": "script_ready",
                        "content": content,
                    }).eq("user_id", user_id).eq("briefing_date", str(user_today)).execute()
                except Exception as script_db_err:
                    logger.warning(
                        "Failed to persist tavus_script to DB: %s",
                        script_db_err,
                        extra={"user_id": user_id},
                    )
            except Exception as script_err:
                logger.warning(
                    "Failed to generate tavus_script: %s",
                    script_err,
                    extra={"user_id": user_id},
                )

            # Write to memory_briefing_queue for delivery tracking
            script_text = content.get("tavus_script", content.get("summary", ""))
            queue_row_id = None
            if script_text:
                try:
                    db = SupabaseClient.get_client()
                    queue_result = db.table("memory_briefing_queue").insert({
                        "user_id": user_id,
                        "briefing_type": "morning",
                        "items": {"script": script_text, "briefing_date": str(user_today)},
                        "is_delivered": False,
                    }).execute()
                    queue_row_id = queue_result.data[0].get("id") if queue_result.data else None
                    logger.info(
                        "Written to memory_briefing_queue",
                        extra={"user_id": user_id, "briefing_date": str(user_today), "queue_id": queue_row_id},
                    )
                except Exception as queue_err:
                    logger.warning(
                        "Failed to write to memory_briefing_queue: %s",
                        queue_err,
                        extra={"user_id": user_id},
                    )

            # Deliver the briefing via user's preferred channel (chat/voice/avatar)
            # This updates delivery_method and delivered_at in daily_briefings
            delivery_result = await briefing_service.deliver_briefing(
                user_id=user_id,
                briefing_date=user_today,
                content=content,
            )
            if delivery_result.get("success"):
                logger.info(
                    "Briefing delivered",
                    extra={
                        "user_id": user_id,
                        "delivery_method": delivery_result.get("delivery_method"),
                    },
                )

            # Create video briefing session if enabled, wire URL back to queue and daily_briefings
            tavus_url = await _maybe_create_video_briefing(user_id, user_today)

            if tavus_url:
                try:
                    db = SupabaseClient.get_client()
                    # Update memory_briefing_queue with the conversation URL
                    if queue_row_id:
                        db.table("memory_briefing_queue").update({
                            "conversation_url": tavus_url,
                            "is_delivered": True,
                        }).eq("id", queue_row_id).execute()
                        logger.info(
                            "Updated memory_briefing_queue with Tavus URL",
                            extra={"user_id": user_id, "queue_id": queue_row_id},
                        )

                    # Update daily_briefings content with tavus_conversation_url
                    # Fetch current content, merge, and update
                    brief_result = db.table("daily_briefings").select("content").eq(
                        "user_id", user_id
                    ).eq("briefing_date", str(user_today)).limit(1).execute()

                    if brief_result.data:
                        current_content = brief_result.data[0].get("content", {})
                        if isinstance(current_content, str):
                            import json
                            current_content = json.loads(current_content)
                        current_content["tavus_conversation_url"] = tavus_url
                        db.table("daily_briefings").update({
                            "content": current_content,
                        }).eq("user_id", user_id).eq("briefing_date", str(user_today)).execute()
                        logger.info(
                            "Updated daily_briefings with Tavus URL",
                            extra={"user_id": user_id, "briefing_date": str(user_today)},
                        )
                except Exception as update_err:
                    logger.warning(
                        "Failed to update Tavus URL in tables: %s",
                        update_err,
                        extra={"user_id": user_id, "tavus_url": tavus_url},
                    )

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


def _get_enriched_signals(db: Any, user_id: str, days_back: int = 7) -> dict[str, list[dict[str, Any]]]:
    """Pull fresh signals from market_signals, categorised for briefing.

    Args:
        db: Supabase client instance.
        user_id: The user's UUID.
        days_back: Number of days to look back for signals.

    Returns:
        Dict with competitor, lead_related, market, and all_fresh signal lists.
    """
    from datetime import timedelta

    cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()

    rows = (
        db.table("market_signals")
        .select("signal_type, headline, company_name, relevance_score, source_url, summary, detected_at")
        .eq("user_id", user_id)
        .gte("detected_at", cutoff)
        .is_("dismissed_at", "null")
        .order("relevance_score", desc=True)
        .limit(50)
        .execute()
        .data or []
    )

    # Known competitor companies
    competitor_companies = {
        "Repligen", "Sartorius", "Cytiva", "Pall Corporation",
        "MilliporeSigma", "Thermo Fisher", "Parker Hannifin",
        "Entegris", "Solaris Biotech", "Pierre Fabre",
    }

    competitor: list[dict[str, Any]] = []
    lead_signals: list[dict[str, Any]] = []
    market: list[dict[str, Any]] = []

    for r in rows:
        co = r.get("company_name", "")
        if co in competitor_companies:
            competitor.append(r)
        elif co in ("Life Sciences Industry", "Industry", "", None):
            market.append(r)
        else:
            lead_signals.append(r)

    return {
        "competitor": competitor[:5],
        "lead_related": lead_signals[:5],
        "market": market[:5],
        "all_fresh": rows[:10],
    }


async def _generate_tavus_script(content: dict[str, Any], user_name: str = "Dhruv") -> str:
    """Generate a rich 8-section spoken briefing script for Tavus.

    Uses Claude to produce a natural, conversational script from assembled
    briefing content. Target: 400-600 words (~3-4 minutes spoken).

    Args:
        content: The assembled briefing content dict.
        user_name: The user's first name for personalisation.

    Returns:
        The spoken script text.
    """
    import os

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Build context from assembled content
    meetings = content.get("calendar", {}).get("key_meetings", [])[:3]
    tasks = content.get("tasks", {}).get("overdue", [])[:3]
    emails = content.get("email_summary", {})
    signals = content.get("signals", {})

    def _format_attendee(a: Any) -> str:
        if isinstance(a, dict):
            return a.get("name") or a.get("email", "?").split("@")[0]
        return str(a)

    meetings_text = "\n".join([
        f"- {m.get('time', '?')}: {m.get('title', '?')} with {', '.join(_format_attendee(a) for a in m.get('attendees', [])[:2])}"
        for m in meetings
    ]) or "No meetings today"

    top_tasks = "\n".join([
        f"- {t.get('title', '?')} (overdue {t.get('days_overdue', '?')} days)"
        for t in tasks
    ]) or "No overdue tasks"

    email_count = emails.get("received_count", 0)
    draft_count = emails.get("draft_count", 0)

    competitor_signals = "\n".join([
        f"- {s.get('company_name')}: {(s.get('headline') or '')[:100]}"
        for s in signals.get("competitive_intel", [])[:3]
    ]) or "No new competitor signals"

    market_signals_text = "\n".join([
        f"- {s.get('company_name', 'Industry')}: {(s.get('headline') or '')[:100]}"
        for s in signals.get("market_trends", [])[:3]
    ]) or "No new market signals"

    lead_signals_text = "\n".join([
        f"- {s.get('company_name')}: {(s.get('headline') or '')[:100]}"
        for s in signals.get("company_news", [])[:3]
    ]) or "No new lead signals"

    # Compute today's date string for the greeting
    today_str = datetime.utcnow().strftime("%A, %B %-d, %Y")

    prompt = f"""You are ARIA, an AI colleague for life sciences commercial teams.
Generate a spoken morning briefing script for {user_name}. This will be read aloud by a Tavus AI avatar.
Today is {today_str}.

Write in a natural, conversational spoken voice. No markdown. No bullet points. No headers.
Use short sentences. Be specific and actionable. Sound like a smart colleague, not a robot.
Target: 400-600 words total (about 3-4 minutes spoken).

DATA FOR TODAY:

MEETINGS ({len(meetings)} today):
{meetings_text}

TOP PRIORITY ACTIONS:
{top_tasks}

EMAILS: {email_count} received, {draft_count} drafts ready for approval

COMPETITOR SIGNALS (last 7 days):
{competitor_signals}

LEAD SIGNALS (last 7 days):
{lead_signals_text}

MARKET/INDUSTRY SIGNALS (last 7 days):
{market_signals_text}

Write the script in this exact order:
1. Greeting (5 sec): "Good morning {user_name}. Here's your briefing for [day, date]."
2. Day at a glance (10 sec): meetings count, draft count, top signal count
3. Meetings (45 sec): for each meeting, who's there and one specific prep note
4. Priority actions (30 sec): top 2-3 overdue items, spoken urgently but calmly
5. Emails (20 sec): drafts ready, most important one called out by name
6. Lead signals (30 sec): any signals about companies you're pursuing
7. Competitor intel (30 sec): what competitors did this week that matters
8. Market/industry (20 sec): one regulatory or market development worth knowing
9. Closing (10 sec): "What would you like to dig into?" followed by 2-3 specific options

Output ONLY the spoken script. Nothing else."""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def _maybe_create_video_briefing(
    user_id: str, briefing_date: date
) -> str | None:
    """Create a Tavus video briefing session if the user has it enabled.

    Args:
        user_id: The user's UUID.
        briefing_date: Date of the briefing.

    Returns:
        The Tavus conversation URL if a session was created, None otherwise.
    """
    try:
        db = SupabaseClient.get_client()

        prefs_result = (
            db.table("user_preferences")
            .select("video_briefing_enabled")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        prefs = prefs_result.data[0] if prefs_result and prefs_result.data else None

        if not prefs:
            return None

        if not prefs.get("video_briefing_enabled", False):
            return None

        from src.services.briefing import BriefingService

        briefing_service = BriefingService()
        result = await briefing_service.create_video_briefing_session(user_id)

        if result.get("session_id"):
            conversation_url = result.get("room_url")
            logger.info(
                "Video briefing session created for daily briefing",
                extra={
                    "user_id": user_id,
                    "session_id": result["session_id"],
                    "briefing_date": briefing_date.isoformat(),
                    "conversation_url": conversation_url,
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

            return conversation_url

    except Exception:
        logger.warning(
            "Video briefing creation failed for user %s",
            user_id,
            exc_info=True,
        )

    return None


async def run_startup_briefing_check() -> dict[str, Any]:
    """Lightweight startup check that generates any missing briefings.

    Called once during app startup. Delegates to run_daily_briefing_job
    which already handles the "already exists" and timezone checks.

    Returns:
        Summary dict from run_daily_briefing_job.
    """
    logger.info("Running startup briefing check")
    return await run_daily_briefing_job()
