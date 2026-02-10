"""Background scheduler for periodic ARIA tasks (P2-36).

Uses APScheduler to run the AmbientGapFiller daily for each active user.
Controlled by the ENABLE_SCHEDULER env var (default False) so it doesn't
run during tests or local development.

Alternative: The ``POST /admin/run-ambient-gaps`` endpoint can be triggered
by an external cron (Railway cron, Supabase pg_cron, etc.) if APScheduler
is not desired.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag — default off for dev/test
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() in ("true", "1", "yes")


async def _run_ambient_gap_checks() -> None:
    """Iterate over active users and run AmbientGapFiller for each."""
    try:
        from src.db.supabase import SupabaseClient
        from src.onboarding.ambient_gap_filler import AmbientGapFiller

        db = SupabaseClient.get_client()
        filler = AmbientGapFiller()

        # Find users who completed onboarding
        result = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )

        user_ids: list[str] = [row["user_id"] for row in (result.data or [])]
        logger.info("Ambient gap check: processing %d users", len(user_ids))

        for user_id in user_ids:
            try:
                await filler.check_and_generate(user_id)
            except Exception:
                logger.warning("Ambient gap check failed for user %s", user_id, exc_info=True)

    except Exception:
        logger.exception("Ambient gap filler scheduler run failed")


async def _run_predictive_preexec() -> None:
    """Run the predictive pre-executor for all active users."""
    try:
        from src.skills.predictive_preexec import run_predictive_preexec_cron

        await run_predictive_preexec_cron()
    except Exception:
        logger.exception("Predictive pre-executor scheduler run failed")


async def _run_calendar_meeting_checks() -> None:
    """Check upcoming meetings for all active users and trigger briefs."""
    try:
        from src.agents.capabilities.base import UserContext
        from src.agents.capabilities.calendar_intel import CalendarIntelligenceCapability
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        # Find users with active Google Calendar integrations
        result = (
            db.table("user_integrations")
            .select("user_id")
            .eq("integration_type", "google_calendar")
            .eq("status", "active")
            .execute()
        )

        user_ids: list[str] = list({row["user_id"] for row in (result.data or [])})
        logger.info("Calendar meeting check: processing %d users", len(user_ids))

        total_briefs = 0
        for user_id in user_ids:
            try:
                ctx = UserContext(user_id=user_id)
                capability = CalendarIntelligenceCapability(
                    supabase_client=db,
                    memory_service=None,
                    knowledge_graph=None,
                    user_context=ctx,
                )
                briefs = await capability.check_upcoming_meetings()
                total_briefs += briefs
            except Exception:
                logger.warning(
                    "Calendar meeting check failed for user %s",
                    user_id,
                    exc_info=True,
                )

        logger.info("Calendar meeting check complete: %d briefs triggered", total_briefs)

    except Exception:
        logger.exception("Calendar meeting check scheduler run failed")


_scheduler: Any = None


async def start_scheduler() -> None:
    """Start the APScheduler background scheduler if enabled."""
    global _scheduler

    if not ENABLE_SCHEDULER:
        logger.info("Background scheduler disabled (ENABLE_SCHEDULER != true)")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            _run_ambient_gap_checks,
            trigger=CronTrigger(hour=6, minute=0),  # 6:00 AM daily
            id="ambient_gap_filler",
            name="Daily ambient gap filler",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_calendar_meeting_checks,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="calendar_meeting_checks",
            name="Calendar meeting prep checks",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_predictive_preexec,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="predictive_preexec",
            name="Predictive pre-executor (Enhancement 9)",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "Background scheduler started — ambient gaps at 06:00 daily, "
            "calendar meeting checks every 30 min, "
            "predictive pre-executor every 30 min"
        )
    except ImportError:
        logger.warning("apscheduler not installed — background scheduler unavailable")
    except Exception:
        logger.exception("Failed to start background scheduler")


async def stop_scheduler() -> None:
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler stopped")


async def run_ambient_gaps_admin() -> dict[str, Any]:
    """Admin endpoint handler: run ambient gap checks on demand.

    Returns:
        Dict with status and number of users processed.
    """
    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()
    result = (
        db.table("onboarding_state").select("user_id").not_.is_("completed_at", "null").execute()
    )
    user_ids = [row["user_id"] for row in (result.data or [])]

    from src.onboarding.ambient_gap_filler import AmbientGapFiller

    filler = AmbientGapFiller()
    processed = 0
    for user_id in user_ids:
        try:
            await filler.check_and_generate(user_id)
            processed += 1
        except Exception:
            logger.warning("Admin ambient gap check failed for user %s", user_id, exc_info=True)

    return {"status": "complete", "users_processed": processed, "users_total": len(user_ids)}
