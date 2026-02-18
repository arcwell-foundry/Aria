"""Proactive battle card refresh job (Task j).

Runs weekly on Monday at 7:30 AM. For each user's tracked competitors,
runs Scout web/news search and updates battle cards via BattleCardService.
Routed as LOW priority (included in next morning briefing).
"""

import logging
from typing import Any

from src.core.business_hours import get_active_user_ids
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)


async def run_battle_card_refresh_job() -> dict[str, Any]:
    """Refresh battle cards for all active users' tracked competitors.

    For each user:
    1. Read tracked_competitors from user_preferences
    2. For each competitor: run Scout web/news search
    3. Fetch existing battle card via BattleCardService
    4. LLM synthesize new intel into updates
    5. Update via BattleCardService.update_battle_card
    6. Route via ProactiveRouter (LOW)

    Returns:
        Summary dict with refresh statistics.
    """
    stats: dict[str, Any] = {
        "users_processed": 0,
        "competitors_scanned": 0,
        "cards_updated": 0,
        "cards_created": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Battle card refresh: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            stats["users_processed"] += 1

            # Get tracked competitors
            prefs_result = (
                db.table("user_preferences")
                .select("tracked_competitors")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            competitors: list[str] = []
            if prefs_result and prefs_result.data:
                tracked = prefs_result.data.get("tracked_competitors") or []
                if isinstance(tracked, list):
                    competitors = [c for c in tracked if isinstance(c, str)]

            if not competitors:
                continue

            for competitor in competitors:
                try:
                    stats["competitors_scanned"] += 1

                    # Search for recent intel via Scout
                    intel = await _gather_competitor_intel(competitor)

                    if not intel:
                        continue

                    # Find or create battle card
                    from src.services.battle_card_service import BattleCardService

                    service = BattleCardService()

                    # Check if battle card exists for this competitor
                    existing_result = (
                        db.table("battle_cards")
                        .select("id")
                        .eq("user_id", user_id)
                        .ilike("company_name", competitor)
                        .limit(1)
                        .execute()
                    )

                    if existing_result.data:
                        card_id = existing_result.data[0]["id"]
                        await service.update_battle_card(
                            card_id=card_id,
                            data={"recent_intel": intel, "auto_refreshed": True},
                            source="auto",
                        )
                        stats["cards_updated"] += 1
                    else:
                        # No existing card — skip creation (battle cards are typically
                        # created via the Strategist agent in conversation)
                        continue

                    # Route as LOW priority
                    await router.route(
                        user_id=user_id,
                        priority=InsightPriority.LOW,
                        category=InsightCategory.BATTLE_CARD_UPDATE,
                        title=f"Battle Card Updated: {competitor}",
                        message=f"New competitive intelligence gathered for {competitor}.",
                        link="/intelligence/battle-cards",
                        metadata={
                            "competitor": competitor,
                            "intel_items": len(intel),
                        },
                    )

                except Exception:
                    logger.warning(
                        "Battle card refresh failed for competitor %s (user %s)",
                        competitor,
                        user_id,
                        exc_info=True,
                    )
                    stats["errors"] += 1

        except Exception:
            logger.warning(
                "Battle card refresh failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Battle card refresh complete", extra=stats)
    return stats


async def _gather_competitor_intel(competitor: str) -> list[dict[str, Any]]:
    """Run Scout-style web search for a competitor and return intel items."""
    intel: list[dict[str, Any]] = []

    try:
        from src.agents.scout import ScoutAgent
        from src.core.llm import LLMClient

        scout = ScoutAgent(llm_client=LLMClient())
        result = await scout.execute(
            {
                "entities": [competitor],
                "signal_types": ["news", "product", "hiring", "funding"],
            }
        )

        if result.success and result.data:
            signals = result.data if isinstance(result.data, list) else []
            for signal in signals[:10]:
                intel.append(
                    {
                        "headline": signal.get("headline", ""),
                        "summary": signal.get("summary", ""),
                        "signal_type": signal.get("signal_type", ""),
                        "source": signal.get("source", ""),
                    }
                )

    except Exception:
        logger.debug("Scout search failed for competitor %s", competitor, exc_info=True)

    return intel
