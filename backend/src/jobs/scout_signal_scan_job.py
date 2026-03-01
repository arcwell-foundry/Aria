"""Proactive Scout signal scanning job (Task d).

Runs every 15 minutes. For each active user, instantiates the ScoutAgent
to detect new market signals for tracked competitors and active leads.
New signals are stored in ``market_signals`` and routed through
the ProactiveRouter based on relevance score.

High-relevance signals (>= 0.8) are additionally evaluated by the
ProactiveGoalProposer to generate actionable goal proposals delivered
via WebSocket (or queued for next login).
"""

import logging
from typing import Any

from src.core.business_hours import get_active_user_ids, get_user_timezone, is_business_hours
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)

# Minimum relevance score to trigger a goal proposal (not just a notification)
_GOAL_PROPOSAL_THRESHOLD = 0.8


async def run_scout_signal_scan_job() -> dict[str, Any]:
    """Run Scout agent signal scan for all active users.

    For each user (within business hours):
    1. Read tracked_competitors from user_preferences + company names from leads
    2. Instantiate ScoutAgent and execute entity search
    3. Deduplicate against existing market_signals
    4. Store new signals and route via ProactiveRouter

    Returns:
        Summary dict with scan statistics.
    """
    stats: dict[str, Any] = {
        "users_checked": 0,
        "users_skipped_off_hours": 0,
        "signals_detected": 0,
        "signals_routed_high": 0,
        "signals_routed_medium": 0,
        "signals_routed_low": 0,
        "goal_proposals_generated": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Scout signal scan: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            tz = get_user_timezone(user_id)
            if not is_business_hours(tz):
                stats["users_skipped_off_hours"] += 1
                continue

            stats["users_checked"] += 1

            # Gather entities to scan
            entities = await _get_scan_entities(db, user_id)
            if not entities:
                continue

            # Run Scout agent
            try:
                from src.agents.scout import ScoutAgent
                from src.core.llm import LLMClient

                scout = ScoutAgent(llm_client=LLMClient())
                result = await scout.execute(
                    {"entities": entities, "signal_types": ["news", "funding", "regulatory"]}
                )

                if not result.success or not result.data:
                    continue

                signals = result.data if isinstance(result.data, list) else []
            except Exception:
                logger.warning(
                    "Scout agent execution failed for user %s",
                    user_id,
                    exc_info=True,
                )
                stats["errors"] += 1
                continue

            # Deduplicate and store
            for signal in signals:
                headline = signal.get("headline", "")
                if not headline:
                    continue

                if await _signal_exists(db, user_id, headline):
                    continue

                # Store in market_signals (the canonical table read by briefing,
                # signals API, causal reasoning, and all downstream consumers)
                relevance = float(signal.get("relevance_score", 0.5))
                signal_id: str | None = None
                try:
                    insert_result = db.table("market_signals").insert(
                        {
                            "user_id": user_id,
                            "company_name": signal.get("company_name", "Unknown"),
                            "signal_type": signal.get("signal_type", "news"),
                            "headline": headline,
                            "summary": signal.get("summary", ""),
                            "source_name": signal.get("source", "scout_agent"),
                            "source_url": signal.get("source_url"),
                            "relevance_score": relevance,
                            "metadata": signal.get("metadata", {}),
                        }
                    ).execute()
                    if insert_result.data:
                        signal_id = insert_result.data[0].get("id")
                except Exception:
                    logger.debug("Failed to store signal: %s", headline[:80])
                    continue

                stats["signals_detected"] += 1

                # Route through Intelligence Pulse Engine
                try:
                    from src.services.intelligence_pulse import get_pulse_engine

                    pulse_engine = get_pulse_engine()
                    await pulse_engine.process_signal(
                        user_id=user_id,
                        signal={
                            "source": "scout_agent",
                            "title": headline,
                            "content": signal.get("summary", ""),
                            "signal_category": signal.get("signal_type", "news"),
                            "pulse_type": "event",
                            "entities": [signal.get("company_name", "Unknown")],
                            "raw_data": signal,
                        },
                    )
                except Exception:
                    logger.debug("Pulse engine routing failed for signal: %s", headline[:60])

                # Route based on relevance
                if relevance >= _GOAL_PROPOSAL_THRESHOLD:
                    priority = InsightPriority.HIGH
                    stats["signals_routed_high"] += 1
                elif relevance >= 0.6:
                    priority = InsightPriority.MEDIUM
                    stats["signals_routed_medium"] += 1
                else:
                    priority = InsightPriority.LOW
                    stats["signals_routed_low"] += 1

                # For HIGH signals: generate a goal proposal with GoalPlanCard
                if relevance >= _GOAL_PROPOSAL_THRESHOLD and signal_id:
                    proposed = await _maybe_propose_goal(
                        user_id=user_id,
                        signal_id=signal_id,
                        signal=signal,
                        relevance=relevance,
                    )
                    if proposed:
                        stats["goal_proposals_generated"] += 1
                        # Goal proposer already handles WebSocket/login delivery,
                        # so skip the plain ProactiveRouter notification
                        continue

                # Fallback: route as a plain notification (no goal card)
                await router.route(
                    user_id=user_id,
                    priority=priority,
                    category=InsightCategory.MARKET_SIGNAL,
                    title=f"Market Signal: {headline[:60]}",
                    message=signal.get("summary", headline),
                    link="/intelligence",
                    metadata={
                        "signal_type": signal.get("signal_type"),
                        "relevance": relevance,
                    },
                )

        except Exception:
            logger.warning(
                "Scout signal scan failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Scout signal scan complete", extra=stats)
    return stats


async def _get_scan_entities(db: Any, user_id: str) -> list[str]:
    """Gather entity names to scan from all available sources."""
    entities: set[str] = set()

    # 1. Tracked competitors from user_preferences
    try:
        prefs_result = (
            db.table("user_preferences")
            .select("tracked_competitors")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if prefs_result and prefs_result.data:
            competitors = prefs_result.data.get("tracked_competitors") or []
            if isinstance(competitors, list):
                entities.update(c for c in competitors if isinstance(c, str))
    except Exception:
        pass

    # 2. Company names from active leads (lead_memories)
    try:
        leads_result = (
            db.table("lead_memories")
            .select("company_name")
            .eq("user_id", user_id)
            .eq("status", "active")
            .limit(20)
            .execute()
        )
        for lead in leads_result.data or []:
            name = lead.get("company_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 3. Entity names from monitored_entities table
    try:
        monitored_result = (
            db.table("monitored_entities")
            .select("entity_name")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(20)
            .execute()
        )
        for entity in monitored_result.data or []:
            name = entity.get("entity_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 4. Company names from discovered_leads (populated by Hunter agent)
    try:
        discovered_result = (
            db.table("discovered_leads")
            .select("company_name")
            .eq("user_id", user_id)
            .limit(20)
            .execute()
        )
        for lead in discovered_result.data or []:
            name = lead.get("company_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 5. Company names from existing market_signals (bootstrap from past analysis)
    if not entities:
        try:
            signals_result = (
                db.table("market_signals")
                .select("company_name")
                .eq("user_id", user_id)
                .neq("company_name", "Market")
                .limit(10)
                .execute()
            )
            for sig in signals_result.data or []:
                name = sig.get("company_name")
                if name:
                    entities.add(name)
        except Exception:
            pass

    return list(entities)


async def _signal_exists(db: Any, user_id: str, headline: str) -> bool:
    """Check if a signal with a similar headline already exists."""
    try:
        result = (
            db.table("market_signals")
            .select("id")
            .eq("user_id", user_id)
            .eq("headline", headline)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


async def _maybe_propose_goal(
    user_id: str,
    signal_id: str,
    signal: dict[str, Any],
    relevance: float,
) -> bool:
    """Evaluate a high-relevance signal and generate a goal proposal.

    Calls ProactiveGoalProposer.evaluate_signal() which handles:
    - LLM-based goal proposal generation
    - Deduplication (won't re-propose for same signal)
    - Storage in proactive_proposals table
    - WebSocket delivery (or login queue if offline)
    - Rich GoalPlanCard rendering

    Args:
        user_id: Target user UUID.
        signal_id: UUID of the stored market_signals row.
        signal: Raw signal dict from Scout agent.
        relevance: Relevance score (0-1).

    Returns:
        True if a proposal was generated and routed.
    """
    try:
        from src.services.proactive_goal_proposer import ProactiveGoalProposer

        proposer = ProactiveGoalProposer()
        proposed = await proposer.evaluate_signal(
            user_id=user_id,
            signal_id=signal_id,
            signal_type=signal.get("signal_type", "news"),
            headline=signal.get("headline", ""),
            summary=signal.get("summary"),
            relevance_score=relevance,
            company_name=signal.get("company_name"),
        )
        if proposed:
            logger.info(
                "Goal proposal generated from signal",
                extra={
                    "user_id": user_id,
                    "signal_id": signal_id,
                    "headline": signal.get("headline", "")[:80],
                },
            )
        return proposed
    except Exception:
        logger.debug(
            "Goal proposal generation failed for signal %s",
            signal_id,
            exc_info=True,
        )
        return False
