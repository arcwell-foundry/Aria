"""Render cron entry point — runs periodic ARIA tasks outside the web process.

Invoked by: ``python -m src.tasks.scheduled``
Schedule:   Every 15 minutes (configured in render.yaml)

Tasks executed on each invocation:
  1. check_and_prompt_debriefs  — notify users about un-debriefed meetings
  2. check_overdue_commitments  — flag commitments_theirs past their due date
  3. refresh_market_signals     — re-evaluate stale intelligence signals

Uses the same config, DB, and services as the main API.
Results are logged and recorded in aria_activity.
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

# Ensure the backend directory is on the path when invoked as ``python -m src.tasks.scheduled``
# from the backend/ root.
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Configure logging before any app imports
log_format = os.getenv("LOG_FORMAT", "text")
if log_format == "json":
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","name":"%(name)s","level":"%(levelname)s","message":"%(message)s"}',
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger("aria.cron")


async def _check_and_prompt_debriefs() -> dict[str, Any]:
    """Prompt all active users to debrief recent meetings."""
    from src.services.debrief_scheduler import run_debrief_prompt_scheduler

    return await run_debrief_prompt_scheduler()


async def _check_overdue_commitments() -> dict[str, Any]:
    """Scan debriefs for overdue commitments_theirs and send notifications."""
    from src.db.supabase import SupabaseClient
    from src.services.debrief_scheduler import DebriefScheduler

    db = SupabaseClient.get_client()
    scheduler = DebriefScheduler()

    result: dict[str, Any] = {
        "users_processed": 0,
        "overdue_found": 0,
        "errors": 0,
    }

    users_response = (
        db.table("onboarding_state")
        .select("user_id")
        .not_.is_("completed_at", "null")
        .execute()
    )

    for row in users_response.data or []:
        user_id = row["user_id"]
        try:
            overdue = await scheduler._find_overdue_commitments(user_id)
            result["users_processed"] += 1
            result["overdue_found"] += len(overdue)
        except Exception:
            logger.warning("Overdue commitment check failed for user %s", user_id, exc_info=True)
            result["errors"] += 1

    return result


async def _refresh_market_signals() -> dict[str, Any]:
    """Re-evaluate intelligence signals that are older than 24 hours.

    Marks stale signals for re-processing by updating their ``updated_at``
    timestamp so the next intelligence pipeline run picks them up.
    """
    from datetime import timedelta

    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()

    result: dict[str, Any] = {
        "stale_signals_found": 0,
        "signals_refreshed": 0,
        "errors": 0,
    }

    try:
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

        # Find signals that haven't been updated in 24+ hours
        stale_response = (
            db.table("intelligence_signals")
            .select("id, user_id, signal_type")
            .eq("status", "active")
            .lt("updated_at", cutoff)
            .limit(100)
            .execute()
        )

        stale_signals = stale_response.data or []
        result["stale_signals_found"] = len(stale_signals)

        if stale_signals:
            signal_ids = [s["id"] for s in stale_signals]
            now = datetime.now(UTC).isoformat()

            # Touch updated_at to trigger re-evaluation on next pipeline run
            (
                db.table("intelligence_signals")
                .update({"updated_at": now, "status": "pending_refresh"})
                .in_("id", signal_ids)
                .execute()
            )

            result["signals_refreshed"] = len(signal_ids)
            logger.info(
                "Marked %d stale signals for refresh",
                len(signal_ids),
            )

    except Exception:
        logger.exception("Market signal refresh failed")
        result["errors"] += 1

    return result


async def _log_to_activity(task_name: str, result: dict[str, Any]) -> None:
    """Record cron execution in aria_activity for observability."""
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        db.table("aria_activity").insert(
            {
                "activity_type": "cron_execution",
                "title": f"Cron: {task_name}",
                "description": str(result),
                "metadata": {
                    "task": task_name,
                    "result": result,
                    "executed_at": datetime.now(UTC).isoformat(),
                },
            }
        ).execute()
    except Exception:
        # Activity logging is best-effort — don't crash the cron
        logger.debug("Failed to log cron activity for %s", task_name, exc_info=True)


async def run_all() -> None:
    """Execute all scheduled tasks sequentially and log results."""
    started = datetime.now(UTC)
    logger.info("=== ARIA cron run started at %s ===", started.isoformat())

    tasks = [
        ("check_and_prompt_debriefs", _check_and_prompt_debriefs),
        ("check_overdue_commitments", _check_overdue_commitments),
        ("refresh_market_signals", _refresh_market_signals),
    ]

    summary: dict[str, Any] = {}

    for name, func in tasks:
        try:
            logger.info("Running task: %s", name)
            result = await func()
            summary[name] = result
            logger.info("Task %s completed: %s", name, result)
            await _log_to_activity(name, result)
        except Exception:
            logger.exception("Task %s failed", name)
            summary[name] = {"error": True}
            await _log_to_activity(name, {"error": True})

    elapsed = (datetime.now(UTC) - started).total_seconds()
    logger.info("=== ARIA cron run finished in %.1fs ===", elapsed)
    logger.info("Summary: %s", summary)


def main() -> None:
    """Entry point for ``python -m src.tasks.scheduled``."""
    asyncio.run(run_all())


if __name__ == "__main__":
    main()
