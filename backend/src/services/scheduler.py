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
                logger.warning(
                    "Ambient gap check failed for user %s", user_id, exc_info=True
                )

    except Exception:
        logger.exception("Ambient gap filler scheduler run failed")


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
        _scheduler.start()
        logger.info("Background scheduler started — ambient gap filler at 06:00 daily")
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
        db.table("onboarding_state")
        .select("user_id")
        .not_.is_("completed_at", "null")
        .execute()
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
