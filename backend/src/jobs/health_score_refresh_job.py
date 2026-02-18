"""Proactive health score refresh job (Task g).

Runs daily at 6:30 AM. Batch-recalculates health scores for all active
leads using HealthScoreCalculator. Significant drops are routed through
ProactiveRouter to alert the user.
"""

import logging
from typing import Any

from src.core.business_hours import get_active_user_ids
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)


async def run_health_score_refresh_job() -> dict[str, Any]:
    """Recalculate health scores for all active leads across all users.

    For each user:
    1. Query active lead_memories
    2. Gather events, insights, stakeholders for each lead
    3. HealthScoreCalculator.calculate() -> new score
    4. Update lead_memories.health_score + insert into health_score_history
    5. Route significant drops via ProactiveRouter

    Returns:
        Summary dict with refresh statistics.
    """
    stats: dict[str, Any] = {
        "users_processed": 0,
        "leads_scored": 0,
        "drops_detected": 0,
        "drops_high": 0,
        "drops_medium": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Health score refresh: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            stats["users_processed"] += 1

            # Get active leads
            leads_result = (
                db.table("lead_memories")
                .select("id, company_name, health_score, status")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            leads = leads_result.data or []

            if not leads:
                continue

            from src.memory.health_score import HealthScoreCalculator

            calculator = HealthScoreCalculator()

            for lead in leads:
                lead_id = lead["id"]
                old_score = lead.get("health_score") or 50
                company_name = lead.get("company_name", "Unknown")

                try:
                    # Gather scoring inputs
                    events = await _get_lead_events(db, lead_id)
                    insights = await _get_lead_insights(db, lead_id)
                    stakeholders = await _get_lead_stakeholders(db, lead_id)
                    stage_history = await _get_stage_history(db, lead_id)

                    new_score = calculator.calculate(
                        lead=lead,
                        events=events,
                        insights=insights,
                        stakeholders=stakeholders,
                        stage_history=stage_history,
                    )

                    stats["leads_scored"] += 1

                    # Update lead_memories
                    db.table("lead_memories").update(
                        {"health_score": new_score}
                    ).eq("id", lead_id).execute()

                    # Insert history record
                    try:
                        db.table("health_score_history").insert(
                            {
                                "lead_memory_id": lead_id,
                                "user_id": user_id,
                                "score": new_score,
                                "previous_score": old_score,
                            }
                        ).execute()
                    except Exception:
                        logger.debug("Failed to insert health score history for lead %s", lead_id)

                    # Check for significant drops
                    drop = old_score - new_score
                    if drop >= 20:
                        stats["drops_detected"] += 1

                        if drop >= 30:
                            priority = InsightPriority.HIGH
                            stats["drops_high"] += 1
                        else:
                            priority = InsightPriority.MEDIUM
                            stats["drops_medium"] += 1

                        await router.route(
                            user_id=user_id,
                            priority=priority,
                            category=InsightCategory.HEALTH_DROP,
                            title=f"Health Score Drop: {company_name}",
                            message=(
                                f"{company_name}'s health score dropped from "
                                f"{old_score} to {new_score} ({drop} points). "
                                "This may indicate declining engagement."
                            ),
                            link=f"/pipeline?lead={lead_id}",
                            metadata={
                                "lead_id": lead_id,
                                "company_name": company_name,
                                "old_score": old_score,
                                "new_score": new_score,
                                "drop": drop,
                            },
                        )

                except Exception:
                    logger.warning(
                        "Health score calculation failed for lead %s",
                        lead_id,
                        exc_info=True,
                    )
                    stats["errors"] += 1

        except Exception:
            logger.warning(
                "Health score refresh failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Health score refresh complete", extra=stats)
    return stats


async def _get_lead_events(db: Any, lead_id: str) -> list[Any]:
    """Fetch recent events for a lead."""
    try:
        result = (
            db.table("lead_memory_events")
            .select("*")
            .eq("lead_memory_id", lead_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


async def _get_lead_insights(db: Any, lead_id: str) -> list[Any]:
    """Fetch insights for a lead."""
    try:
        result = (
            db.table("lead_memory_insights")
            .select("*")
            .eq("lead_memory_id", lead_id)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


async def _get_lead_stakeholders(db: Any, lead_id: str) -> list[Any]:
    """Fetch stakeholders for a lead."""
    try:
        result = (
            db.table("lead_memory_stakeholders")
            .select("*")
            .eq("lead_memory_id", lead_id)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


async def _get_stage_history(db: Any, lead_id: str) -> list[dict[str, Any]]:
    """Fetch lifecycle stage history for a lead."""
    try:
        result = (
            db.table("lead_memory_events")
            .select("event_type, metadata, created_at")
            .eq("lead_memory_id", lead_id)
            .eq("event_type", "stage_change")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return result.data or []
    except Exception:
        return []
