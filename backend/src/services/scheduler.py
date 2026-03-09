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

        # Find users with active calendar integrations (any provider)
        result = (
            db.table("user_integrations")
            .select("user_id")
            .in_(
                "integration_type",
                [
                    "google_calendar",
                    "googlecalendar",
                    "outlook",
                    "outlook365calendar",
                    "microsoft_calendar",
                ],
            )
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
        from src.core.ws import ws_manager
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

        # Create shared service instances for OODA loop (best-effort)
        ooda_logger = None
        try:
            from src.services.ooda_logger import OODALogger

            ooda_logger = OODALogger()
        except Exception:
            logger.warning("OODALogger unavailable for scheduler OODA checks")

        persona_builder = None
        try:
            from src.core.persona import get_persona_builder

            persona_builder = get_persona_builder()
        except Exception:
            logger.warning("PersonaBuilder unavailable for scheduler OODA checks")

        trust_service = None
        try:
            from src.core.trust import get_trust_calibration_service

            trust_service = get_trust_calibration_service()
        except Exception:
            logger.warning("TrustCalibrationService unavailable for scheduler OODA checks")

        dct_minter = None
        try:
            from src.core.capability_tokens import DCTMinter

            dct_minter = DCTMinter()
        except Exception:
            logger.warning("DCTMinter unavailable for scheduler OODA checks")

        cost_governor = None
        try:
            from src.core.cost_governor import CostGovernor

            cost_governor = CostGovernor()
        except Exception:
            logger.warning("CostGovernor unavailable for scheduler OODA checks")

        for goal in goals:
            try:
                user_id = goal["user_id"]
                goal_id = goal["id"]

                # Create memory services for this user
                episodic = EpisodicMemory()
                semantic = SemanticMemory()
                working = WorkingMemory(
                    conversation_id=f"ooda-{goal_id}",
                    user_id=user_id,
                )

                # Create agent executor callback to bridge OODA → GoalExecutionService
                # OODALoop.act() calls: agent_executor(action=, agent=, parameters=, goal=,
                #   capability_token=, approval_level=)
                def _make_executor(uid: str):  # noqa: E301
                    async def _executor(
                        action: str,
                        agent: str,
                        parameters: dict,
                        goal: dict,
                        **kwargs: Any,  # absorbs capability_token, approval_level
                    ) -> dict:
                        try:
                            result = await execution_service._execute_agent(
                                user_id=uid,
                                goal=goal,
                                agent_type=agent or "analyst",
                                context={"action": action, **parameters},
                            )
                            return (
                                result
                                if isinstance(result, dict)
                                else {"success": True, "result": result}
                            )
                        except Exception as exc:
                            logger.error(
                                "Agent executor failed",
                                extra={
                                    "user_id": uid,
                                    "agent": agent,
                                    "action": action,
                                    "error": str(exc),
                                },
                                exc_info=True,
                            )
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
                    ooda_logger=ooda_logger,
                    user_id=user_id,
                    persona_builder=persona_builder,
                    trust_service=trust_service,
                    dct_minter=dct_minter,
                    cost_governor=cost_governor,
                )

                state = OODAState(goal_id=goal_id)
                state = await ooda.run_single_iteration(state, goal)

                decision_action = state.decision.get("action") if state.decision else None

                # Emit WebSocket progress event after OODA iteration
                try:
                    agent_name = (
                        state.decision.get("agent") if state.decision else None
                    )
                    await ws_manager.send_progress_update(
                        user_id=user_id,
                        goal_id=goal_id,
                        progress=goal.get("progress", 0),
                        status="active",
                        agent_name=agent_name,
                        message=f"OODA iteration complete for: {goal.get('title', '')}",
                    )
                except Exception:
                    pass  # User may not be connected

                if state.is_complete or decision_action == "complete":
                    await execution_service.complete_goal_with_retro(goal_id, user_id)
                    logger.info(
                        "OODA decided goal complete",
                        extra={"goal_id": goal_id},
                    )

                    # Emit WebSocket completion event
                    try:
                        await ws_manager.send_execution_complete(
                            user_id=user_id,
                            goal_id=goal_id,
                            title=goal.get("title", ""),
                            success=True,
                            steps_completed=1,
                            steps_total=1,
                            summary=f"Goal '{goal.get('title', '')}' completed",
                        )
                    except Exception:
                        pass  # User may not be connected

                    # Route OODA completion signal through Pulse Engine
                    try:
                        from src.services.intelligence_pulse import get_pulse_engine

                        pulse_engine = get_pulse_engine()
                        await pulse_engine.process_signal(
                            user_id=user_id,
                            signal={
                                "source": "ooda",
                                "title": f"Goal completed: {goal.get('title', '')}",
                                "content": f"OODA loop determined goal '{goal.get('title', '')}' is complete",
                                "signal_category": "goal",
                                "pulse_type": "intelligent",
                                "related_goal_id": goal_id,
                                "raw_data": {"goal_id": goal_id, "action": "complete"},
                            },
                        )
                    except Exception:
                        logger.debug("Pulse engine failed for OODA completion signal")

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

                    # Emit WebSocket blocked event
                    try:
                        await ws_manager.send_progress_update(
                            user_id=user_id,
                            goal_id=goal_id,
                            progress=goal.get("progress", 0),
                            status="blocked",
                            message=f"Blocked: {state.blocked_reason or 'Unknown reason'}",
                        )
                    except Exception:
                        pass  # User may not be connected

                    # Route OODA blocked signal through Pulse Engine
                    try:
                        from src.services.intelligence_pulse import get_pulse_engine

                        pulse_engine = get_pulse_engine()
                        await pulse_engine.process_signal(
                            user_id=user_id,
                            signal={
                                "source": "ooda",
                                "title": f"Goal blocked: {goal.get('title', '')}",
                                "content": f"Blocked reason: {state.blocked_reason or 'Unknown'}",
                                "signal_category": "goal",
                                "pulse_type": "intelligent",
                                "related_goal_id": goal_id,
                                "raw_data": {"goal_id": goal_id, "action": "blocked", "reason": state.blocked_reason},
                            },
                        )
                    except Exception:
                        logger.debug("Pulse engine failed for OODA blocked signal")

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


async def _run_draft_feedback_poll() -> None:
    """Poll for user feedback on ARIA-generated email drafts.

    Checks email clients to detect:
    - APPROVED: Draft sent without significant edits
    - EDITED: Draft sent with user modifications
    - REJECTED: Draft deleted without sending
    - IGNORED: Draft older than 7 days with no action
    """
    try:
        from src.jobs.draft_feedback_poll_job import run_draft_feedback_poll

        result = await run_draft_feedback_poll()

        if result["users_checked"] > 0:
            logger.info(
                "Draft feedback poll complete: %d users, %d drafts checked. "
                "Approved: %d, Edited: %d, Rejected: %d, Ignored: %d",
                result["users_checked"],
                result["total_checked"],
                result["total_approved"],
                result["total_edited"],
                result["total_rejected"],
                result["total_ignored"],
            )
    except Exception:
        logger.exception("Draft feedback poll scheduler run failed")


async def _run_deferred_draft_retry() -> None:
    """Retry deferred email drafts.

    Checks deferred_email_drafts for threads that were postponed due to
    active conversations and retries draft generation if conditions allow.
    """
    try:
        from src.jobs.deferred_draft_retry_job import run_deferred_draft_retry

        result = await run_deferred_draft_retry()

        if result["total_checked"] > 0:
            logger.info(
                "Deferred draft retry: %d checked, %d processed, %d skipped, %d expired, %d errors",
                result["total_checked"],
                result["processed"],
                result["skipped"],
                result["expired"],
                result["errors"],
            )
    except Exception:
        logger.exception("Deferred draft retry scheduler run failed")


async def _run_proactive_followup_check() -> None:
    """Check for overdue email commitments and draft follow-up emails.

    For each user with email integration:
    1. Query prospective_memories for overdue email commitments
    2. Generate contextual follow-up drafts via LLM
    3. Save drafts to email_drafts and push to email client
    """
    try:
        from src.jobs.proactive_followup_job import run_proactive_followup_check

        result = await run_proactive_followup_check()

        if result["users_checked"] > 0 or result["total_followups_drafted"] > 0:
            logger.info(
                "Proactive followup check: %d users checked, %d drafts generated, %d errors",
                result["users_checked"],
                result["total_followups_drafted"],
                result["errors"],
            )
    except Exception:
        logger.exception("Proactive followup check scheduler run failed")


async def _run_style_recalibration() -> None:
    """Run weekly style recalibration for email writing.

    For each user:
    1. Fetch sent emails from past 7 days
    2. Fetch edited drafts from past 7 days
    3. Re-analyze writing style if enough data
    4. Update fingerprint and recipient profiles
    """
    try:
        from src.jobs.style_recalibration_job import run_style_recalibration_job

        result = await run_style_recalibration_job()

        if result["users_processed"] > 0:
            logger.info(
                "Style recalibration complete: %d users processed, "
                "%d fingerprints updated, %d profiles updated, %d skipped",
                result["users_processed"],
                result["fingerprints_updated"],
                result["profiles_updated"],
                result["users_skipped_insufficient_data"],
            )
    except Exception:
        logger.exception("Style recalibration scheduler run failed")


async def _run_daily_improvement_cycle() -> None:
    """Run daily improvement cycle for all active users."""
    try:
        from src.companion.self_improvement import SelfImprovementLoop
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )

        user_ids: list[str] = [row["user_id"] for row in (result.data or [])]
        logger.info("Daily improvement cycle: processing %d users", len(user_ids))

        for user_id in user_ids:
            try:
                service = SelfImprovementLoop()
                await service.run_improvement_cycle(user_id)
            except Exception:
                logger.warning("Daily improvement cycle failed for user %s", user_id, exc_info=True)

    except Exception:
        logger.exception("Daily improvement cycle scheduler run failed")


async def _run_weekly_improvement_report() -> None:
    """Generate weekly improvement report for all active users."""
    try:
        from src.companion.self_improvement import SelfImprovementLoop
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("onboarding_state")
            .select("user_id")
            .not_.is_("completed_at", "null")
            .execute()
        )

        user_ids: list[str] = [row["user_id"] for row in (result.data or [])]
        logger.info("Weekly improvement report: processing %d users", len(user_ids))

        for user_id in user_ids:
            try:
                service = SelfImprovementLoop()
                await service.generate_weekly_report(user_id)
            except Exception:
                logger.warning(
                    "Weekly improvement report failed for user %s", user_id, exc_info=True
                )

    except Exception:
        logger.exception("Weekly improvement report scheduler run failed")


async def _run_debrief_prompt_checks() -> None:
    """Check for meetings that ended recently and prompt for debriefs."""
    try:
        from src.services.debrief_scheduler import run_debrief_prompt_scheduler

        result = await run_debrief_prompt_scheduler()

        if result["users_processed"] > 0:
            logger.info(
                "Debrief prompt scheduler complete: %d users processed, "
                "%d notifications sent, %d errors",
                result["users_processed"],
                result["total_notifications"],
                result["errors"],
            )
    except Exception:
        logger.exception("Debrief prompt scheduler run failed")


async def _run_meeting_end_check() -> None:
    """Check for meetings that just ended and send debrief prompts."""
    try:
        from src.jobs.meeting_end_check import run_meeting_end_check

        result = await run_meeting_end_check()

        if result["notifications_sent"] > 0:
            logger.info(
                "Meeting end check complete: %d notifications sent, "
                "%d meetings found, %d errors",
                result["notifications_sent"],
                result["meetings_found"],
                result["errors"],
            )
    except Exception:
        logger.exception("Meeting end check scheduler run failed")


async def _run_competitive_docs_refresh() -> None:
    """Monthly refresh of competitive intelligence docs in Tavus Knowledge Base.

    Re-generates battle card summary documents from the battle_cards table
    and re-uploads them to Tavus for RAG retrieval during video conversations.
    """
    try:
        from scripts.setup_tavus_knowledge_base import refresh_competitive_docs

        result = await refresh_competitive_docs()
        logger.info(
            "Competitive docs refresh complete: uploaded=%d, deleted=%d, skipped=%d",
            result.get("uploaded", 0),
            result.get("deleted", 0),
            result.get("skipped", 0),
        )
    except Exception:
        logger.exception("Competitive docs refresh scheduler run failed")


async def _run_battle_card_product_enrichment() -> None:
    """Monthly enrichment of battle cards with competitor product data via Exa."""
    try:
        from src.db.supabase import SupabaseClient
        from src.intelligence.battle_card_enrichment import BattleCardEnricher

        db = SupabaseClient.get_client()

        exa_client = None
        try:
            from src.core.config import settings

            if settings.exa_configured:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                exa_client = ExaEnrichmentProvider()
        except Exception:
            logger.warning("Exa client not available for battle card enrichment")

        enricher = BattleCardEnricher(supabase_client=db, exa_client=exa_client)
        count = await enricher.enrich_all_battle_cards()
        logger.info(
            "Battle card product enrichment complete: %d cards enriched", count
        )
    except Exception:
        logger.exception("Battle card product enrichment scheduler run failed")


async def _run_scout_signal_scan() -> None:
    """Run proactive Scout signal scan for market intelligence."""
    try:
        from src.jobs.scout_signal_scan_job import run_scout_signal_scan_job

        result = await run_scout_signal_scan_job()

        if result["users_checked"] > 0:
            logger.info(
                "Scout signal scan complete: %d users checked, %d signals detected",
                result["users_checked"],
                result["signals_detected"],
            )
    except Exception:
        logger.exception("Scout signal scan scheduler run failed")


async def _run_daily_briefing_check() -> None:
    """Run daily briefing generation check for all users."""
    try:
        from src.jobs.daily_briefing_job import run_daily_briefing_job

        result = await run_daily_briefing_job()

        if result["generated"] > 0:
            logger.info(
                "Daily briefing check: %d generated, %d skipped, %d errors",
                result["generated"],
                result["skipped"],
                result["errors"],
            )
    except Exception:
        logger.exception("Daily briefing check scheduler run failed")


async def _run_health_score_refresh() -> None:
    """Run batch health score recalculation for all leads."""
    try:
        from src.jobs.health_score_refresh_job import run_health_score_refresh_job

        result = await run_health_score_refresh_job()

        if result["leads_scored"] > 0:
            logger.info(
                "Health score refresh: %d leads scored, %d drops detected",
                result["leads_scored"],
                result["drops_detected"],
            )
    except Exception:
        logger.exception("Health score refresh scheduler run failed")


async def _run_stale_leads_check() -> None:
    """Run stale leads detection for all users."""
    try:
        from src.jobs.stale_leads_job import run_stale_leads_job

        result = await run_stale_leads_job()

        if result["users_processed"] > 0:
            logger.info(
                "Stale leads check: %d users, %d high, %d medium",
                result["users_processed"],
                result["stale_leads_high"],
                result["stale_leads_medium"],
            )
    except Exception:
        logger.exception("Stale leads check scheduler run failed")


async def _run_weekly_digest() -> None:
    """Run weekly digest generation for all users."""
    try:
        from src.jobs.weekly_digest_job import run_weekly_digest_job

        result = await run_weekly_digest_job()

        if result["digests_generated"] > 0:
            logger.info(
                "Weekly digest: %d generated, %d skipped",
                result["digests_generated"],
                result["digests_skipped_existing"],
            )
    except Exception:
        logger.exception("Weekly digest scheduler run failed")


async def _run_meeting_brief_generation() -> None:
    """Scan calendar_events, create brief stubs, enrich attendees, generate content.

    Single-stage pipeline that directly scans calendar_events table for ALL users,
    looks ahead 48h and back 2h, skips buffer events, enriches attendees via Exa,
    and generates brief content via Claude.
    """
    try:
        from src.jobs.meeting_brief_generator import run_meeting_brief_job

        result = await run_meeting_brief_job(hours_ahead=48, hours_back=2)

        if result["events_found"] > 0:
            logger.info(
                "Meeting brief generation: %d events, %d briefs created, %d generated, %d errors",
                result["events_found"],
                result["briefs_created"],
                result["briefs_generated"],
                result["errors"],
            )
    except Exception:
        logger.exception("Meeting brief generation scheduler run failed")


async def _run_battle_card_refresh() -> None:
    """Run weekly battle card refresh for tracked competitors."""
    try:
        from src.jobs.battle_card_refresh_job import run_battle_card_refresh_job

        result = await run_battle_card_refresh_job()

        if result["competitors_scanned"] > 0:
            logger.info(
                "Battle card refresh: %d competitors scanned, %d cards updated",
                result["competitors_scanned"],
                result["cards_updated"],
            )
    except Exception:
        logger.exception("Battle card refresh scheduler run failed")


async def _run_conversion_score_batch() -> None:
    """Run weekly conversion score batch recalculation."""
    try:
        from src.jobs.conversion_score_batch_job import run_conversion_score_batch_job

        result = await run_conversion_score_batch_job()

        if result["leads_scored"] > 0:
            logger.info(
                "Conversion score batch: %d leads scored, %d significant changes",
                result["leads_scored"],
                result["significant_changes"],
            )
    except Exception:
        logger.exception("Conversion score batch scheduler run failed")


async def _run_draft_staleness_check() -> None:
    """Check for stale drafts where thread has evolved since draft creation."""
    try:
        from src.jobs.draft_staleness_check_job import run_draft_staleness_check

        result = await run_draft_staleness_check()

        if result["drafts_marked_stale"] > 0:
            logger.info(
                "Draft staleness check: %d users, %d drafts checked, %d marked stale",
                result["users_checked"],
                result["drafts_checked"],
                result["drafts_marked_stale"],
            )
    except Exception:
        logger.exception("Draft staleness check scheduler run failed")


async def _run_stalled_goal_kickstart() -> None:
    """Backfill missing goal_agents and kickstart active goals with 0% progress.

    For each active goal:
    1. Check if it has any goal_agents rows — if not, insert one using config.agent_type
    2. If progress is 0 and no agent_executions exist, trigger synchronous execution
    3. Record goal_updates and send WebSocket events
    """
    try:
        from src.core.ws import ws_manager
        from src.db.supabase import SupabaseClient
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
        if not goals:
            return

        logger.info("Stalled goal kickstart: checking %d active goals", len(goals))

        execution_service = GoalExecutionService()
        kickstarted = 0

        for goal in goals:
            goal_id = goal["id"]
            user_id = goal["user_id"]

            try:
                # Check if goal has goal_agents rows
                agents_result = (
                    db.table("goal_agents")
                    .select("id, agent_type")
                    .eq("goal_id", goal_id)
                    .in_("status", ["active", "running", "pending"])
                    .execute()
                )
                existing_agents = agents_result.data or []

                # Backfill missing goal_agents
                if not existing_agents:
                    agent_type = goal.get("config", {}).get("agent_type", "analyst")
                    logger.info(
                        "Backfilling goal_agents for stalled goal",
                        extra={
                            "goal_id": goal_id,
                            "user_id": user_id,
                            "agent_type": agent_type,
                        },
                    )
                    try:
                        db.table("goal_agents").insert(
                            {
                                "goal_id": goal_id,
                                "agent_type": agent_type,
                                "agent_config": {"source": "stalled_goal_kickstart"},
                                "status": "pending",
                            }
                        ).execute()
                    except Exception:
                        logger.warning(
                            "Failed to backfill goal_agents",
                            extra={"goal_id": goal_id},
                            exc_info=True,
                        )

                # Check if goal has any executions already
                exec_result = (
                    db.table("agent_executions")
                    .select("id", count="exact")
                    .eq("goal_agent_id", existing_agents[0]["id"] if existing_agents else "none")
                    .eq("status", "complete")
                    .limit(1)
                    .execute()
                )
                has_executions = bool(exec_result.data)

                # Only kickstart goals with 0 progress and no executions
                progress = goal.get("progress") or 0
                if progress == 0 and not has_executions:
                    logger.info(
                        "Kickstarting stalled goal execution",
                        extra={
                            "goal_id": goal_id,
                            "user_id": user_id,
                            "title": goal.get("title"),
                        },
                    )

                    try:
                        await ws_manager.send_progress_update(
                            user_id=user_id,
                            goal_id=goal_id,
                            progress=0,
                            status="active",
                            message=f"Kickstarting execution: {goal.get('title', '')}",
                        )
                    except Exception:
                        pass  # User may not be connected

                    try:
                        await execution_service.execute_goal_sync(goal_id, user_id)
                        kickstarted += 1
                    except Exception:
                        logger.warning(
                            "Stalled goal kickstart execution failed",
                            extra={"goal_id": goal_id},
                            exc_info=True,
                        )

            except Exception:
                logger.warning(
                    "Stalled goal kickstart failed for goal %s",
                    goal_id,
                    exc_info=True,
                )

        logger.info("Stalled goal kickstart complete: %d goals kickstarted", kickstarted)

    except Exception:
        logger.exception("Stalled goal kickstart scheduler run failed")


async def _run_draft_auto_approve() -> None:
    """Auto-approve MEDIUM-risk drafts past their auto_approve_at timeout."""
    try:
        from src.jobs.draft_auto_approve_job import run_draft_auto_approve

        await run_draft_auto_approve()
    except Exception:
        logger.exception("Draft auto-approve scheduler run failed")


async def _run_salience_decay() -> None:
    """Run daily salience decay for all user memories."""
    try:
        from src.jobs.salience_decay import run_salience_decay_job

        result = await run_salience_decay_job()
        logger.info(
            "Salience decay job completed: %d users, %d records updated",
            result.get("users_processed", 0),
            result.get("records_updated", 0),
        )
    except Exception:
        logger.exception("Salience decay scheduler run failed")


async def _run_pulse_sweep() -> None:
    """Sweep for signals that don't have explicit producer hooks.

    Catches:
    1. Goals that changed status meaningfully since last check
    2. Overdue prospective memories
    """
    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()

        # Time window: signals from the last 15 minutes
        cutoff = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()

        # 1. Goals that recently changed to blocked or complete
        try:
            goals_result = (
                db.table("goals")
                .select("id, user_id, title, status, updated_at")
                .gt("updated_at", cutoff)
                .in_("status", ["blocked", "complete"])
                .execute()
            )
            for goal in (goals_result.data or []):
                # Deduplicate: check if pulse_signals already has this goal+status
                existing = (
                    db.table("pulse_signals")
                    .select("id")
                    .eq("related_goal_id", goal["id"])
                    .eq("source", "pulse_sweep")
                    .gt("created_at", cutoff)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                await pulse_engine.process_signal(
                    user_id=goal["user_id"],
                    signal={
                        "source": "pulse_sweep",
                        "title": f"Goal {goal['status']}: {goal.get('title', '')}",
                        "content": f"Goal '{goal.get('title', '')}' changed to {goal['status']}",
                        "signal_category": "goal",
                        "pulse_type": "scheduled",
                        "related_goal_id": goal["id"],
                        "raw_data": {"goal_id": goal["id"], "status": goal["status"]},
                    },
                )
        except Exception:
            logger.warning("Pulse sweep: goal status check failed", exc_info=True)

        # 2. Overdue prospective memories
        try:
            now = datetime.now(UTC).isoformat()
            overdue_result = (
                db.table("prospective_memories")
                .select("id, user_id, task, description, priority")
                .eq("status", "active")
                .is_("completed_at", "null")
                .lte("trigger_at", now)
                .limit(20)
                .execute()
            )
            for task in (overdue_result.data or []):
                # Deduplicate
                existing = (
                    db.table("pulse_signals")
                    .select("id")
                    .eq("source", "pulse_sweep")
                    .eq("title", f"Overdue: {task.get('task', '')[:80]}")
                    .eq("user_id", task["user_id"])
                    .gt("created_at", cutoff)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                await pulse_engine.process_signal(
                    user_id=task["user_id"],
                    signal={
                        "source": "pulse_sweep",
                        "title": f"Overdue: {task.get('task', '')[:80]}",
                        "content": task.get("description", "Overdue prospective memory task"),
                        "signal_category": "goal",
                        "pulse_type": "scheduled",
                        "raw_data": {"prospective_memory_id": task["id"]},
                    },
                )
        except Exception:
            logger.warning("Pulse sweep: overdue memory check failed", exc_info=True)

    except Exception:
        logger.exception("Pulse sweep scheduler run failed")


async def _run_capability_demand_check() -> None:
    """Check if any capabilities have crossed suggestion threshold.

    When a user has needed a capability 3+ times without direct access,
    generate a proactive pulse signal suggesting they connect the tool.

    Delegates to IntelligencePulseEngine.generate_tool_suggestion_pulses()
    for the actual pulse generation logic.
    """
    try:
        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()

        # Get unique users with unresolved demand (the actual pulse generation
        # logic is delegated to generate_tool_suggestion_pulses)
        demands_result = (
            db.table("capability_demand")
            .select("user_id")
            .gte("times_needed", 3)
            .eq("suggestion_threshold_reached", False)
            .execute()
        )

        # Get unique user IDs
        user_ids = {d["user_id"] for d in (demands_result.data or [])}

        for user_id in user_ids:
            try:
                # Delegate pulse generation to the engine method
                pulses = await pulse_engine.generate_tool_suggestion_pulses(user_id)

                for pulse in pulses:
                    # Convert to process_signal format and persist
                    await pulse_engine.process_signal(
                        user_id=user_id,
                        signal={
                            "pulse_type": "intelligent",
                            "source": "capability_demand",
                            "title": pulse["title"],
                            "content": pulse["message"],
                            "signal_category": "capability",
                            "raw_data": {
                                "action": pulse.get("action"),
                                "metadata": pulse.get("metadata"),
                            },
                        },
                    )

                    # Mark threshold reached for this capability
                    capability_name = pulse.get("metadata", {}).get("capability_name")
                    if capability_name:
                        (
                            db.table("capability_demand")
                            .update({"suggestion_threshold_reached": True})
                            .eq("user_id", user_id)
                            .eq("capability_name", capability_name)
                            .execute()
                        )

                    logger.info(
                        "Capability demand pulse generated",
                        extra={
                            "user_id": user_id,
                            "title": pulse["title"],
                        },
                    )

            except Exception:
                logger.warning(
                    "Capability demand check failed for user",
                    extra={"user_id": user_id},
                    exc_info=True,
                )

    except Exception:
        logger.exception("Capability demand check scheduler run failed")


async def _run_skill_health_check() -> None:
    """Check health of ARIA-generated skills every 6 hours."""
    try:
        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine
        from src.services.skill_trust import SkillHealthMonitor

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()
        monitor = SkillHealthMonitor(db, pulse_engine=pulse_engine)
        await monitor.check_all_active_skills()
    except Exception:
        logger.exception("Skill health check scheduler run failed")


async def _cleanup_expired_ecosystem_cache() -> None:
    """Remove expired ecosystem search cache entries daily."""
    try:
        from datetime import datetime, timezone

        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        (
            db.table("ecosystem_search_cache")
            .delete()
            .lt("expires_at", datetime.now(timezone.utc).isoformat())
            .execute()
        )
        logger.info("Expired ecosystem search cache cleaned")
    except Exception:
        logger.exception("Ecosystem cache cleanup failed")


async def _cleanup_stale_goal_agents() -> None:
    """Mark stale pending/running goal agents as failed.

    Targets agents that:
    - Have status 'pending' and were created more than 24 hours ago
    - Have a parent goal that is already 'failed' or 'cancelled'
    """
    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        now = datetime.now(UTC).isoformat()

        # Stale pending agents older than 24 hours
        stale_result = (
            db.table("goal_agents")
            .update({"status": "failed", "updated_at": now})
            .in_("status", ["pending", "running"])
            .lt("created_at", cutoff)
            .execute()
        )
        stale_count = len(stale_result.data) if stale_result.data else 0

        # Agents whose parent goal is already failed/cancelled
        failed_goals = (
            db.table("goals")
            .select("id")
            .in_("status", ["failed", "cancelled"])
            .execute()
        )
        orphan_count = 0
        if failed_goals.data:
            failed_ids = [g["id"] for g in failed_goals.data]
            for goal_id in failed_ids:
                orphan_result = (
                    db.table("goal_agents")
                    .update({"status": "failed", "updated_at": now})
                    .eq("goal_id", goal_id)
                    .in_("status", ["pending", "running"])
                    .execute()
                )
                orphan_count += len(orphan_result.data) if orphan_result.data else 0

        if stale_count or orphan_count:
            logger.info(
                "Cleaned up stale goal agents: %d stale, %d orphaned",
                stale_count,
                orphan_count,
            )
    except Exception:
        logger.exception("Stale goal agents cleanup failed")


async def _run_connection_health_check() -> None:
    """Daily job: verify active connections still work.

    For each active connection, makes a lightweight API call through
    the session manager. If it fails with 401/403, marks the connection
    as expired and sends a Pulse notification to the user.

    Runs once daily, staggered to avoid rate limits.
    """
    import asyncio

    logger.info("Connection health check starting")

    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient
        from src.integrations.connection_registry import get_connection_registry

        registry = get_connection_registry()
        db = SupabaseClient.get_client()

        # Get all active connections not verified in last 24h
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        result = (
            db.table("user_connections")
            .select("id, user_id, toolkit_slug, composio_connection_id, last_health_check_at, failure_count")
            .eq("status", "active")
            .or_(f"last_health_check_at.is.null,last_health_check_at.lt.{cutoff}")
            .limit(100)  # batch size
            .execute()
        )

        connections = result.data or []
        logger.info("Checking health of %d connections", len(connections))

        for conn in connections:
            user_id = conn["user_id"]
            toolkit = conn["toolkit_slug"]
            connection_id = conn.get("composio_connection_id")

            try:
                # Attempt a lightweight action through the session
                test_action = _get_health_check_action(toolkit)
                if test_action and connection_id:
                    from src.integrations.composio_sessions import get_session_manager

                    session_mgr = get_session_manager()
                    await session_mgr.execute_action(
                        user_id=user_id,
                        action=test_action,
                        params={"limit": 1},
                        connection_id=connection_id,
                    )

                # Success — update last_health_check_at
                db.table("user_connections").update({
                    "last_health_check_at": datetime.now(UTC).isoformat(),
                    "failure_count": 0,
                }).eq("id", conn["id"]).execute()

            except Exception as e:
                error_str = str(e).lower()
                if "401" in error_str or "403" in error_str or "token" in error_str:
                    # Auth failure — mark as expired
                    logger.warning(
                        "Connection expired: user=%s toolkit=%s: %s",
                        user_id, toolkit, e,
                    )
                    await registry.mark_connection_expired(user_id, toolkit)

                    # Send Pulse notification
                    try:
                        from src.core.ws import ws_manager

                        await ws_manager.send_to_user(user_id, {
                            "type": "integration_expired",
                            "toolkit_slug": toolkit,
                            "message": (
                                f"Your {toolkit.replace('_', ' ').title()} connection "
                                f"has expired. Reconnect to keep ARIA working smoothly."
                            ),
                        })
                    except Exception:
                        pass
                else:
                    # Transient error — increment failure count but don't expire
                    db.table("user_connections").update({
                        "last_health_check_at": datetime.now(UTC).isoformat(),
                        "failure_count": (conn.get("failure_count") or 0) + 1,
                    }).eq("id", conn["id"]).execute()

            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)

    except Exception:
        logger.exception("Connection health check failed")

    logger.info("Connection health check complete")


def _get_health_check_action(toolkit_slug: str) -> str | None:
    """Map toolkit to a lightweight read-only action for health checks."""
    health_check_actions = {
        "OUTLOOK365": "OUTLOOK365_LIST_MESSAGES",
        "GMAIL": "GMAIL_LIST_MESSAGES",
        "SALESFORCE": "SALESFORCE_GET_USER_INFO",
        "HUBSPOT": "HUBSPOT_GET_ACCOUNT_INFO",
        "GOOGLECALENDAR": "GOOGLECALENDAR_LIST_CALENDARS",
        "GOOGLE_CALENDAR": "GOOGLE_CALENDAR_LIST_CALENDARS",
        "SLACK": "SLACK_AUTH_TEST",
        "ZOOM": "ZOOM_GET_USER",
    }
    return health_check_actions.get(toolkit_slug.upper())


async def _run_battle_card_metrics_recompute() -> None:
    """Daily recompute of battle card threat metrics from market signals.

    For each battle card:
    1. Query market_signals by company_name (including aliases)
    2. Compute 30-day and previous-30-day signal counts
    3. Calculate momentum, threat_score, threat_level
    4. Update the card's analysis JSON and last_updated
    """
    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient
        from src.utils.company_aliases import get_signal_company_names_for_battle_card

        db = SupabaseClient.get_client()

        # Get all battle cards
        cards_result = (
            db.table("battle_cards")
            .select("id, competitor_name, company_id, analysis")
            .execute()
        )
        cards = cards_result.data or []

        if not cards:
            return

        logger.info("Battle card metrics recompute: processing %d cards", len(cards))

        now = datetime.now(UTC)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        sixty_days_ago = (now - timedelta(days=60)).isoformat()

        updated = 0
        for card in cards:
            try:
                card_id = card["id"]
                competitor_name = card.get("competitor_name", "")

                # Get all name variants for this battle card
                name_variants = get_signal_company_names_for_battle_card(
                    competitor_name, company_id=card.get("company_id"), db=db,
                )

                # Query signals from last 30 days across all name variants
                signals_30d: list[dict] = []
                signals_prev_30d: list[dict] = []

                for name in name_variants:
                    result_30d = (
                        db.table("market_signals")
                        .select("id, signal_type, relevance_score")
                        .eq("company_name", name)
                        .gte("created_at", thirty_days_ago)
                        .execute()
                    )
                    signals_30d.extend(result_30d.data or [])

                    result_prev = (
                        db.table("market_signals")
                        .select("id, signal_type, relevance_score")
                        .eq("company_name", name)
                        .gte("created_at", sixty_days_ago)
                        .lt("created_at", thirty_days_ago)
                        .execute()
                    )
                    signals_prev_30d.extend(result_prev.data or [])

                count_30d = len(signals_30d)
                count_prev_30d = len(signals_prev_30d)

                # Momentum calculation
                if count_prev_30d > 0 and count_30d > count_prev_30d * 1.25:
                    momentum = "increasing"
                elif count_prev_30d > 0 and count_30d < count_prev_30d * 0.75:
                    momentum = "declining"
                else:
                    momentum = "stable"

                # High-impact signals
                high_impact_types = {"product", "funding", "fda_approval", "clinical_trial"}
                high_impact = [
                    s for s in signals_30d
                    if s.get("signal_type") in high_impact_types
                ]

                # Threat score
                threat_score = round(
                    (min(count_30d, 10) / 10 * 0.4)
                    + (min(len(high_impact), 5) / 5 * 0.35)
                    + (0.7 if count_30d else (0.4 if count_prev_30d else 0.1)) * 0.25,
                    2,
                )

                # Threat level
                if threat_score >= 0.65:
                    threat_level = "high"
                elif threat_score >= 0.35:
                    threat_level = "medium"
                else:
                    threat_level = "low"

                # Average relevance
                relevance_scores = [
                    s.get("relevance_score", 0) for s in signals_30d
                    if s.get("relevance_score") is not None
                ]
                avg_relevance = (
                    round(sum(relevance_scores) / len(relevance_scores), 2)
                    if relevance_scores
                    else 0
                )

                # Merge into existing analysis
                existing_analysis = card.get("analysis") or {}
                existing_analysis.update({
                    "signals_30d": count_30d,
                    "signals_prev_30d": count_prev_30d,
                    "momentum": momentum,
                    "threat_score": threat_score,
                    "threat_level": threat_level,
                    "high_impact_count": len(high_impact),
                    "avg_relevance": avg_relevance,
                    "metrics_updated_at": now.isoformat(),
                })

                # Detect significant metric changes for memory compounding
                old_analysis = card.get("analysis") or {}
                old_threat = old_analysis.get("threat_level")
                old_momentum = old_analysis.get("momentum")
                threat_level_changed = old_threat is not None and old_threat != threat_level
                momentum_changed = old_momentum is not None and old_momentum != momentum

                (
                    db.table("battle_cards")
                    .update({
                        "analysis": existing_analysis,
                        "last_updated": now.isoformat(),
                    })
                    .eq("id", card_id)
                    .execute()
                )

                # Memory compounding: write summary when metrics shift
                if threat_level_changed or momentum_changed:
                    try:
                        # Find a user_id associated with this battle card's company
                        card_company_id = card.get("company_id")
                        if card_company_id:
                            user_result = (
                                db.table("user_profiles")
                                .select("id")
                                .eq("company_id", card_company_id)
                                .limit(1)
                                .execute()
                            )
                            if user_result.data:
                                bc_user_id = user_result.data[0]["id"]
                                db.table("memory_semantic").insert(
                                    {
                                        "user_id": bc_user_id,
                                        "fact": (
                                            f"[Battle Card Update] {competitor_name}: "
                                            f"Threat level is now {threat_level}, "
                                            f"momentum {momentum}. "
                                            f"{count_30d} signals in 30d."
                                        ),
                                        "confidence": 0.9,
                                        "source": "battle_card_recompute",
                                        "metadata": {
                                            "competitor_name": competitor_name,
                                            "threat_level": threat_level,
                                            "momentum": momentum,
                                            "old_threat_level": old_threat,
                                            "old_momentum": old_momentum,
                                        },
                                    }
                                ).execute()
                    except Exception:
                        logger.debug(
                            "Failed to write battle card memory for %s",
                            competitor_name,
                        )

                updated += 1

            except Exception:
                logger.warning(
                    "Battle card metrics recompute failed for card %s",
                    card.get("id"),
                    exc_info=True,
                )

        logger.info(
            "Battle card metrics recompute complete: %d/%d cards updated",
            updated,
            len(cards),
        )

    except Exception:
        logger.exception("Battle card metrics recompute scheduler run failed")


async def _run_market_cap_update() -> None:
    """Monthly enrichment of market cap data for user's company and competitors.

    Uses Exa search to find recent market cap / valuation data for:
    1. The user's own company
    2. All competitors from battle_cards

    Results are logged for now; parsing can be improved later.
    """
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        # Try to import Exa provider
        try:
            from src.agents.capabilities.enrichment_providers.exa_provider import (
                ExaEnrichmentProvider,
            )
        except ImportError:
            logger.warning("Exa provider not available — skipping market cap update")
            return

        exa = ExaEnrichmentProvider()

        # Get all companies (user companies) from user_profiles → companies
        profiles_result = (
            db.table("user_profiles")
            .select("company_id")
            .not_.is_("company_id", "null")
            .execute()
        )
        company_ids = list({p["company_id"] for p in (profiles_result.data or [])})

        companies_to_search: list[str] = []
        for company_id in company_ids:
            try:
                company_result = (
                    db.table("companies")
                    .select("name")
                    .eq("id", company_id)
                    .limit(1)
                    .execute()
                )
                if company_result.data:
                    name = company_result.data[0].get("name")
                    if name:
                        companies_to_search.append(name)
            except Exception:
                logger.warning(
                    "Failed to fetch company name for id %s",
                    company_id,
                    exc_info=True,
                )

        # Get all competitors from battle_cards
        cards_result = (
            db.table("battle_cards")
            .select("competitor_name")
            .execute()
        )
        for card in (cards_result.data or []):
            name = card.get("competitor_name")
            if name and name not in companies_to_search:
                companies_to_search.append(name)

        if not companies_to_search:
            logger.info("Market cap update: no companies to search")
            return

        logger.info(
            "Market cap update: searching %d companies",
            len(companies_to_search),
        )

        for company_name in companies_to_search:
            try:
                query = f"{company_name} market capitalization valuation 2026"
                results = await exa.search_fast(query, num_results=3)

                if results:
                    logger.info(
                        "Market cap search for '%s': %d results — %s",
                        company_name,
                        len(results),
                        "; ".join(r.title[:80] for r in results[:3]),
                    )
                else:
                    logger.info(
                        "Market cap search for '%s': no results",
                        company_name,
                    )
            except Exception:
                logger.warning(
                    "Market cap search failed for '%s'",
                    company_name,
                    exc_info=True,
                )

    except Exception:
        logger.exception("Market cap update scheduler run failed")


async def _run_reconciliation_sweep() -> None:
    """Safety net: Check for events that webhooks might have missed.

    Runs every 30 min. Catches stragglers that Composio triggers didn't deliver.
    Checks: "Are there emails in inbox that DON'T have a matching event_log entry?"

    Currently a stub — will be wired to existing email scan logic later.
    """
    logger.info("Reconciliation sweep: stub (not yet implemented)")


async def _run_conference_enrichment() -> None:
    """Weekly: Enrich upcoming conferences with exhibitor/speaker data via Exa."""
    logger.info("[Scheduler] Running conference enrichment")
    try:
        from src.db.supabase import SupabaseClient
        from src.intelligence.conference_intelligence import (
            ConferenceIntelligenceEngine,
        )

        db = SupabaseClient.get_client()

        exa = None
        try:
            from src.services.exa_service import get_exa_client

            exa = get_exa_client()
        except Exception:
            pass

        engine = ConferenceIntelligenceEngine(db, exa)
        count = await engine.enrich_upcoming_conferences(days_ahead=90)
        logger.info(
            "[Scheduler] Conference enrichment complete: %d participants added",
            count,
        )
    except Exception:
        logger.exception("[Scheduler] Conference enrichment failed")


async def _run_conference_recommendations() -> None:
    """Weekly: Regenerate conference recommendations for all users."""
    logger.info("[Scheduler] Running conference recommendations")
    try:
        from src.db.supabase import SupabaseClient
        from src.intelligence.conference_intelligence import (
            ConferenceIntelligenceEngine,
        )

        db = SupabaseClient.get_client()
        engine = ConferenceIntelligenceEngine(db)

        users = db.table("user_profiles").select("id").execute()
        if users.data:
            for user in users.data:
                recs = await engine.generate_recommendations(user["id"])
                logger.info(
                    "[Scheduler] Generated %d recommendations for user %s",
                    len(recs),
                    user["id"],
                )
    except Exception:
        logger.exception("[Scheduler] Conference recommendations failed")


async def _run_pre_conference_briefings() -> None:
    """Generate pre-conference briefings for upcoming conferences (14-30 days out)."""
    try:
        from datetime import datetime, timedelta, timezone

        from src.db.supabase import SupabaseClient
        from src.intelligence.conference_intelligence import ConferenceIntelligenceEngine

        db = SupabaseClient.get_client()
        now = datetime.now(timezone.utc).date()
        window_start = now + timedelta(days=14)
        window_end = now + timedelta(days=30)

        recs = (
            db.table("conference_recommendations")
            .select("user_id, conference_id")
            .in_("recommendation_type", ["must_attend", "consider"])
            .execute()
        )

        if not recs.data:
            return

        for rec in recs.data:
            try:
                conf = (
                    db.table("conferences")
                    .select("id, name, start_date")
                    .eq("id", rec["conference_id"])
                    .gte("start_date", window_start.isoformat())
                    .lte("start_date", window_end.isoformat())
                    .limit(1)
                    .execute()
                )
                if not conf.data:
                    continue

                existing = (
                    db.table("conference_insights")
                    .select("id")
                    .eq("user_id", rec["user_id"])
                    .eq("conference_id", rec["conference_id"])
                    .eq("insight_type", "pre_conference_briefing")
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                engine = ConferenceIntelligenceEngine(db)
                await engine.generate_pre_conference_briefing(
                    rec["user_id"], rec["conference_id"]
                )
                logger.info(
                    "Pre-conference briefing generated for %s",
                    conf.data[0]["name"],
                )
            except Exception:
                logger.warning(
                    "Failed to generate pre-conference briefing for conference %s",
                    rec["conference_id"],
                    exc_info=True,
                )
    except Exception:
        logger.warning("Pre-conference briefing job failed", exc_info=True)


async def _run_hunter_lead_generation() -> None:
    """Run Hunter agent lead generation for all active lead gen goals.

    Queries all active lead generation goals across all users,
    runs Hunter agent for each goal, creates discovered leads,
    generates outbound email drafts, and saves drafts to email client.
    Updates goal progress incrementally after each lead batch.
    """
    try:
        from src.jobs.hunter_lead_job import run_hunter_lead_generation_job

        result = await run_hunter_lead_generation_job()

        if result["leads_found"] > 0 or result["goals_processed"] > 0:
            logger.info(
                "Hunter lead generation: users=%d, goals=%d, leads=%d, errors=%d",
                result["users_checked"],
                result["goals_processed"],
                result["leads_found"],
                result["errors"],
            )
    except Exception:
        logger.exception("Hunter lead generation scheduler run failed")


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
            _run_meeting_brief_generation,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="meeting_brief_generation",
            name="Process pending meeting briefs",
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
            _run_stalled_goal_kickstart,
            trigger=CronTrigger(minute="*/10"),  # Every 10 minutes
            id="stalled_goal_kickstart",
            name="Stalled goal backfill and kickstart",
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
            _run_draft_auto_approve,
            trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
            id="draft_auto_approve",
            name="Auto-approve MEDIUM-risk drafts past timeout",
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
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="periodic_email_check",
            name="Periodic inbox check for urgent emails",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_draft_feedback_poll,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="draft_feedback_poll",
            name="Draft feedback polling for learning mode",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_deferred_draft_retry,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="deferred_draft_retry",
            name="Retry deferred email drafts for deduplication",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_proactive_followup_check,
            trigger=CronTrigger(hour="*/4"),  # Every 4 hours
            id="proactive_followup_check",
            name="Proactive follow-up drafts for overdue commitments",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_style_recalibration,
            trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),  # Sunday 2 AM
            id="style_recalibration",
            name="Weekly style recalibration for writing profiles",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_daily_improvement_cycle,
            trigger=CronTrigger(hour=23, minute=30),  # 11:30 PM daily
            id="daily_improvement_cycle",
            name="Daily self-improvement cycle analysis",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_weekly_improvement_report,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),  # Sunday 3 AM
            id="weekly_improvement_report",
            name="Weekly self-improvement report generation",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_debrief_prompt_checks,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="debrief_prompt_checks",
            name="Meeting debrief prompt scheduler",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_meeting_end_check,
            trigger=CronTrigger(minute="*/5"),  # Every 5 minutes
            id="meeting_end_check",
            name="Check for ended meetings needing debrief",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_competitive_docs_refresh,
            trigger=CronTrigger(day=1, hour=3, minute=0),  # 1st of month, 3 AM
            id="competitive_docs_refresh",
            name="Monthly Tavus KB competitive docs refresh",
            replace_existing=True,
        )
        # --- Proactive Intelligence Pipeline jobs ---
        _scheduler.add_job(
            _run_scout_signal_scan,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="scout_signal_scan",
            name="Proactive Scout market signal scan",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_daily_briefing_check,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="daily_briefing_check",
            name="Daily briefing generation check",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_health_score_refresh,
            trigger=CronTrigger(hour=6, minute=30),  # 6:30 AM daily
            id="health_score_refresh",
            name="Daily health score batch refresh",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_stale_leads_check,
            trigger=CronTrigger(hour=7, minute=0),  # 7:00 AM daily
            id="stale_leads_check",
            name="Daily stale leads detection",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_weekly_digest,
            trigger=CronTrigger(day_of_week="mon", hour=7, minute=0),  # Monday 7 AM
            id="weekly_digest",
            name="Weekly digest generation",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_battle_card_refresh,
            trigger=CronTrigger(day_of_week="mon", hour=7, minute=30),  # Monday 7:30 AM
            id="battle_card_refresh",
            name="Weekly battle card refresh",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_conversion_score_batch,
            trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),  # Monday 8 AM
            id="conversion_score_batch",
            name="Weekly conversion score batch recalculation",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_draft_staleness_check,
            trigger=CronTrigger(minute="*/15"),  # Every 15 minutes
            id="draft_staleness_check",
            name="Draft staleness detection for evolved threads",
            replace_existing=True,
        )

        _scheduler.add_job(
            _run_salience_decay,
            trigger=CronTrigger(hour=2, minute=0),  # 2:00 AM daily
            id="salience_decay",
            name="Daily memory salience decay update",
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
        _scheduler.add_job(
            _run_pulse_sweep,
            trigger=CronTrigger(minute="*/15"),
            id="pulse_sweep",
            name="Intelligence Pulse Engine sweep for missed signals",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_capability_demand_check,
            trigger=CronTrigger(hour="*/6"),
            id="capability_demand_check",
            name="Capability demand proactive suggestion check",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_skill_health_check,
            trigger=CronTrigger(hour="*/6"),
            id="skill_health_check",
            name="Check health of ARIA-generated skills",
            replace_existing=True,
        )
        _scheduler.add_job(
            _cleanup_expired_ecosystem_cache,
            trigger=CronTrigger(hour=3, minute=0),
            id="ecosystem_cache_cleanup",
            name="Clean expired ecosystem search cache",
            replace_existing=True,
        )
        _scheduler.add_job(
            _cleanup_stale_goal_agents,
            trigger=CronTrigger(hour=0, minute=0),
            id="cleanup_stale_goal_agents",
            name="Clean up stale pending goal agents",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_reconciliation_sweep,
            trigger=CronTrigger(minute="*/30"),
            id="reconciliation_sweep",
            name="Event reconciliation sweep",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_connection_health_check,
            trigger=CronTrigger(hour=4, minute=0),  # 4 AM daily
            id="connection_health_check",
            name="Daily connection health verification",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        _scheduler.add_job(
            _run_battle_card_metrics_recompute,
            trigger=CronTrigger(hour=2, minute=0),  # 2 AM UTC daily
            id="battle_card_metrics_recompute",
            name="Daily battle card threat metrics recompute",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_market_cap_update,
            trigger=CronTrigger(day=1, hour=3, minute=0),  # 1st of month, 3 AM UTC
            id="market_cap_update",
            name="Monthly market cap Exa enrichment",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_conference_enrichment,
            trigger=CronTrigger(day_of_week="mon", hour=4, minute=0),
            id="conference_enrichment",
            name="Weekly conference exhibitor/speaker enrichment",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_conference_recommendations,
            trigger=CronTrigger(day_of_week="mon", hour=5, minute=0),
            id="conference_recommendations",
            name="Weekly conference recommendations refresh",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_pre_conference_briefings,
            trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
            id="pre_conference_briefings",
            name="Weekly pre-conference briefing generation",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_battle_card_product_enrichment,
            trigger=CronTrigger(day=15, hour=3, minute=0),
            id="battle_card_product_enrichment",
            name="Monthly battle card product enrichment via Exa",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_hunter_lead_generation,
            trigger=CronTrigger(minute="*/30"),  # Every 30 minutes
            id="hunter_lead_generation",
            name="Hunter agent lead generation for active goals",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "Background scheduler started with %d jobs — "
            "includes proactive pipeline: scout scan every 15 min, "
            "daily briefing check every 15 min, "
            "health score refresh at 06:30, "
            "stale leads check at 07:00, "
            "weekly digest Monday 07:00, "
            "battle card refresh Monday 07:30, "
            "conversion score batch Monday 08:00, "
            "email check every 15 min, "
            "hunter lead generation every 30 min",
            len(_scheduler.get_jobs()),
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
