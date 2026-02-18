"""Proactive Scout signal scanning job (Task d).

Runs every 15 minutes. For each active user, instantiates the ScoutAgent
to detect new market signals for tracked competitors and active leads.
New signals are stored in ``intelligence_signals`` and routed through
the ProactiveRouter based on relevance score.
"""

import logging
from typing import Any

from src.core.business_hours import get_active_user_ids, get_user_timezone, is_business_hours
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)


async def run_scout_signal_scan_job() -> dict[str, Any]:
    """Run Scout agent signal scan for all active users.

    For each user (within business hours):
    1. Read tracked_competitors from user_preferences + company names from leads
    2. Instantiate ScoutAgent and execute entity search
    3. Deduplicate against existing intelligence_signals
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

                # Store in intelligence_signals
                relevance = float(signal.get("relevance_score", 0.5))
                try:
                    db.table("intelligence_signals").insert(
                        {
                            "user_id": user_id,
                            "signal_type": signal.get("signal_type", "news"),
                            "headline": headline,
                            "summary": signal.get("summary", ""),
                            "relevance_score": relevance,
                            "source": signal.get("source", "scout_agent"),
                            "metadata": signal.get("metadata", {}),
                            "status": "active",
                        }
                    ).execute()
                except Exception:
                    logger.debug("Failed to store signal: %s", headline[:80])
                    continue

                stats["signals_detected"] += 1

                # Route based on relevance
                if relevance >= 0.8:
                    priority = InsightPriority.HIGH
                    stats["signals_routed_high"] += 1
                elif relevance >= 0.6:
                    priority = InsightPriority.MEDIUM
                    stats["signals_routed_medium"] += 1
                else:
                    priority = InsightPriority.LOW
                    stats["signals_routed_low"] += 1

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
    """Gather entity names to scan from user preferences and active leads."""
    entities: set[str] = set()

    # Tracked competitors from user_preferences
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

    # Company names from active leads
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

    return list(entities)


async def _signal_exists(db: Any, user_id: str, headline: str) -> bool:
    """Check if a signal with a similar headline already exists."""
    try:
        result = (
            db.table("intelligence_signals")
            .select("id")
            .eq("user_id", user_id)
            .eq("headline", headline)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False
