"""Background scheduler for periodic ARIA tasks (P2-36).

Uses APScheduler to run the AmbientGapFiller daily for each active user.
Controlled by the ENABLE_SCHEDULER env var (default True).
Set ENABLE_SCHEDULER=false to disable during tests or CI.

Alternative: The ``POST /admin/run-ambient-gaps`` endpoint can be triggered
by an external cron (Railway cron, Supabase pg_cron, etc.) if APScheduler
is not desired.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag — default on; set ENABLE_SCHEDULER=false to disable
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("true", "1", "yes")
logger.info("Scheduler enabled: %s", ENABLE_SCHEDULER)


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


async def _run_medium_action_timeout() -> None:
    """Auto-approve MEDIUM risk actions that have been pending for over 30 minutes.

    Queries aria_action_queue for actions with status='pending' and
    risk_level='medium' where created_at is more than 30 minutes ago.
    Updates their status to 'auto_approved' and sets approved_at.
    """
    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        cutoff = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        # Find MEDIUM risk actions pending for more than 30 minutes
        result = (
            db.table("aria_action_queue")
            .select("id, user_id, title")
            .eq("status", "pending")
            .eq("risk_level", "medium")
            .lt("created_at", cutoff)
            .execute()
        )

        actions = result.data or []
        if not actions:
            return

        logger.info(
            "Medium action timeout: auto-approving %d actions",
            len(actions),
        )

        now = datetime.now(UTC).isoformat()
        action_ids = [a["id"] for a in actions]

        # Batch update all timed-out actions
        (
            db.table("aria_action_queue")
            .update(
                {
                    "status": "auto_approved",
                    "approved_at": now,
                }
            )
            .in_("id", action_ids)
            .execute()
        )

        for action in actions:
            logger.info(
                "Medium action auto-approved after 30-min timeout",
                extra={
                    "action_id": action["id"],
                    "user_id": action["user_id"],
                    "title": action["title"],
                },
            )

    except Exception:
        logger.exception("Medium action timeout scheduler run failed")


async def _run_ooda_goal_checks() -> None:
    """Run a single OODA iteration for each active goal.

    Queries all goals with status='active', creates an OODALoop for each,
    and runs one monitoring iteration. If the OODA decides 'complete',
    triggers goal completion with retrospective.
    """
    try:
        from src.core.llm import LLMClient
        from src.core.ooda import OODAConfig, OODALoop, OODAState
        from src.db.supabase import SupabaseClient
        from src.memory.episodic import EpisodicMemory
        from src.memory.semantic import SemanticMemory
        from src.memory.working import WorkingMemory
        from src.services.goal_execution import GoalExecutionService

        db = SupabaseClient.get_client()

        # Find active goals
        result = (
            db.table("goals")
            .select("id, user_id, title, description, goal_type, config, progress")
            .eq("status", "active")
            .execute()
        )

        goals = result.data or []
        logger.info("OODA goal check: processing %d active goals", len(goals))

        llm = LLMClient()
        execution_service = GoalExecutionService()

        for goal in goals:
            try:
                user_id = goal["user_id"]
                goal_id = goal["id"]

                # Create memory services for this user
                episodic = EpisodicMemory(user_id=user_id)
                semantic = SemanticMemory(user_id=user_id)
                working = WorkingMemory(user_id=user_id)

                # Create agent executor callback to bridge OODA → GoalExecutionService
                def _make_executor(uid: str):  # noqa: E301
                    async def _executor(
                        action: str, agent: str, parameters: dict, goal_data: dict
                    ) -> dict:
                        try:
                            result = await execution_service._execute_agent(
                                user_id=uid,
                                goal=goal_data,
                                agent_type=agent or "analyst",
                                context={"action": action, **parameters},
                            )
                            return (
                                result
                                if isinstance(result, dict)
                                else {"success": True, "result": result}
                            )
                        except Exception as exc:
                            return {"success": False, "error": str(exc)}

                    return _executor

                agent_executor = _make_executor(user_id)

                # Create OODA loop with single-iteration config
                ooda_config = OODAConfig(max_iterations=1)
                ooda = OODALoop(
                    llm_client=llm,
                    episodic_memory=episodic,
                    semantic_memory=semantic,
                    working_memory=working,
                    config=ooda_config,
                    agent_executor=agent_executor,
                )

                state = OODAState(goal_id=goal_id)
                state = await ooda.run_single_iteration(state, goal)

                decision_action = state.decision.get("action") if state.decision else None

                if state.is_complete or decision_action == "complete":
                    await execution_service.complete_goal_with_retro(goal_id, user_id)
                    logger.info(
                        "OODA decided goal complete",
                        extra={"goal_id": goal_id},
                    )
                elif state.is_blocked:
                    db.table("goals").update(
                        {
                            "config": {
                                **goal.get("config", {}),
                                "health": "blocked",
                                "blocked_reason": state.blocked_reason,
                            }
                        }
                    ).eq("id", goal_id).execute()
                    logger.warning(
                        "OODA detected blocked goal",
                        extra={
                            "goal_id": goal_id,
                            "reason": state.blocked_reason,
                        },
                    )

            except Exception:
                logger.warning(
                    "OODA goal check failed for goal %s",
                    goal.get("id"),
                    exc_info=True,
                )

    except Exception:
        logger.exception("OODA goal checks scheduler run failed")


async def _run_prospective_memory_checks() -> None:
    """Check upcoming and overdue prospective memory tasks for all active users."""
    try:
        from src.db.supabase import SupabaseClient
        from src.memory.prospective import ProspectiveMemory

        db = SupabaseClient.get_client()
        prospective = ProspectiveMemory()

        # Find active users
        result = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )
        user_ids = [row["user_id"] for row in (result.data or [])]
        logger.info("Prospective memory check: processing %d users", len(user_ids))

        for user_id in user_ids:
            try:
                # Check upcoming tasks (due in next 10 min)
                upcoming = await prospective.get_upcoming_tasks(user_id, limit=20)
                for task in upcoming:
                    # Check if due within 10 minutes via trigger_config
                    due_at_str = task.trigger_config.get("due_at")
                    if due_at_str:
                        from datetime import UTC, datetime, timedelta

                        now = datetime.now(UTC)
                        try:
                            due_at = datetime.fromisoformat(due_at_str)
                            if due_at <= now + timedelta(minutes=10):
                                # Send WebSocket notification
                                try:
                                    from src.api.routes.websocket import ws_manager

                                    await ws_manager.send_to_user(
                                        user_id,
                                        {
                                            "type": "prospective.task_due",
                                            "data": {
                                                "task_id": task.id,
                                                "title": task.task,
                                                "description": task.description,
                                                "priority": task.priority.value,
                                                "due_at": due_at_str,
                                            },
                                        },
                                    )
                                except Exception:
                                    logger.debug(
                                        "WebSocket notification skipped for user %s",
                                        user_id,
                                    )
                        except (ValueError, TypeError):
                            pass

                # Check overdue tasks
                overdue = await prospective.get_overdue_tasks(user_id)
                for task in overdue:
                    try:
                        from src.api.routes.websocket import ws_manager

                        await ws_manager.send_to_user(
                            user_id,
                            {
                                "type": "prospective.task_overdue",
                                "data": {
                                    "task_id": task.id,
                                    "title": task.task,
                                    "description": task.description,
                                    "priority": task.priority.value,
                                },
                            },
                        )
                    except Exception:
                        logger.debug(
                            "WebSocket notification skipped for user %s",
                            user_id,
                        )

            except Exception:
                logger.warning(
                    "Prospective memory check failed for user %s",
                    user_id,
                    exc_info=True,
                )

    except Exception:
        logger.exception("Prospective memory check scheduler run failed")


async def _run_working_memory_sync() -> None:
    """Persist all active working memory sessions to Supabase."""
    try:
        from src.memory.working import WorkingMemoryManager

        manager = WorkingMemoryManager()
        count = await manager.persist_all_sessions()
        if count > 0:
            logger.info("Working memory sync: persisted %d sessions", count)
    except Exception:
        logger.exception("Working memory sync failed")


async def _run_webset_polling() -> None:
    """Import new leads from pending Websets.

    Polls Exa Websets for completed items and imports them into
    discovered_leads for user review.
    """
    try:
        from src.services.webset_service import WebsetService

        service = WebsetService()
        result = await service.poll_pending_websets()

        if result["total_jobs"] > 0:
            logger.info(
                "Webset polling complete: %d jobs, %d items imported, %d completed, %d errors",
                result["total_jobs"],
                result["items_imported"],
                result["jobs_completed"],
                result["errors"],
            )
    except Exception:
        logger.exception("Webset polling scheduler run failed")


async def _run_periodic_email_check() -> None:
    """Run periodic inbox check for urgent emails during business hours.

    For each user with email integration:
    1. Check if within business hours (8 AM - 7 PM)
    2. Get watermark from last processing run
    3. Scan inbox for new emails since watermark
    4. Trigger real-time notifications for urgent emails
    """
    try:
        from src.jobs.periodic_email_check import run_periodic_email_check

        result = await run_periodic_email_check()

        if result["users_checked"] > 0:
            logger.info(
                "Periodic email check complete: %d users checked, %d with urgent, "
                "%d total urgent emails, %d notifications sent",
                result["users_checked"],
                result["users_with_urgent"],
                result["total_urgent_emails"],
                result["notifications_sent"],
            )
    except Exception:
        logger.exception("Periodic email check scheduler run failed")


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
        _scheduler.add_job(
            _run_ooda_goal_checks,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="ooda_goal_monitoring",
            name="OODA goal monitoring",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_medium_action_timeout,
            trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
            id="medium_action_timeout",
            name="Medium action 30-min auto-approve timeout",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_prospective_memory_checks,
            trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
            id="prospective_memory_checks",
            name="Prospective memory task trigger checks",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_webset_polling,
            trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
            id="webset_polling",
            name="Webset polling for bulk lead import",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_periodic_email_check,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="periodic_email_check",
            name="Periodic inbox check for urgent emails",
            replace_existing=True,
        )

        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler.add_job(
            _run_working_memory_sync,
            trigger=IntervalTrigger(seconds=30),
            id="working_memory_sync",
            name="Working memory 30-second persistence sync",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "Background scheduler started — ambient gaps at 06:00 daily, "
            "calendar meeting checks every 30 min, "
            "predictive pre-executor every 30 min, "
            "OODA goal monitoring every 30 min, "
            "medium action timeout every 5 min, "
            "prospective memory checks every 5 min, "
            "working memory sync every 30 sec, "
            "webset polling every 5 min, "
            "periodic email check every 30 min"
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
