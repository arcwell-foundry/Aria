"""Proactive conversion score batch recalculation job (Task k).

Runs weekly on Monday at 8:00 AM. Wraps the existing
ConversionScoringService.batch_score_all_leads and routes significant
score changes through ProactiveRouter.
"""

import logging
from typing import Any

from src.core.business_hours import get_active_user_ids
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)

# Threshold for routing a score change
SIGNIFICANT_CHANGE_PCT = 15


async def run_conversion_score_batch_job() -> dict[str, Any]:
    """Batch-recalculate conversion scores for all active users' leads.

    For each user:
    1. Snapshot current scores from lead_memories.metadata.conversion_score
    2. ConversionScoringService.batch_score_all_leads(user_id)
    3. Compare new scores to snapshots
    4. Route significant changes (>= 15%) via ProactiveRouter (MEDIUM)

    Returns:
        Summary dict with scoring statistics.
    """
    stats: dict[str, Any] = {
        "users_processed": 0,
        "leads_scored": 0,
        "significant_changes": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Conversion score batch: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            stats["users_processed"] += 1

            # Snapshot current scores
            leads_result = (
                db.table("lead_memories")
                .select("id, company_name, metadata")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            leads = leads_result.data or []

            old_scores: dict[str, float] = {}
            lead_names: dict[str, str] = {}
            for lead in leads:
                lead_id = lead["id"]
                lead_names[lead_id] = lead.get("company_name", "Unknown")
                meta = lead.get("metadata") or {}
                if isinstance(meta, dict):
                    old_scores[lead_id] = float(meta.get("conversion_score", 0))

            # Run batch scoring
            from src.services.conversion_scoring import ConversionScoringService

            service = ConversionScoringService()
            batch_result = await service.batch_score_all_leads(user_id)

            stats["leads_scored"] += batch_result.scored

            # Fetch updated scores
            updated_result = (
                db.table("lead_memories")
                .select("id, metadata")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )

            for lead in updated_result.data or []:
                lead_id = lead["id"]
                meta = lead.get("metadata") or {}
                new_score = float(meta.get("conversion_score", 0)) if isinstance(meta, dict) else 0
                old_score = old_scores.get(lead_id, 0)

                if old_score == 0 and new_score == 0:
                    continue

                # Calculate percentage change
                if old_score > 0:
                    change_pct = abs(new_score - old_score) / old_score * 100
                else:
                    change_pct = 100 if new_score > 0 else 0

                if change_pct >= SIGNIFICANT_CHANGE_PCT:
                    stats["significant_changes"] += 1
                    company = lead_names.get(lead_id, "Unknown")

                    direction = "increased" if new_score > old_score else "decreased"

                    await router.route(
                        user_id=user_id,
                        priority=InsightPriority.MEDIUM,
                        category=InsightCategory.CONVERSION_SCORE_CHANGE,
                        title=f"Conversion Score Change: {company}",
                        message=(
                            f"{company}'s conversion probability {direction} "
                            f"from {old_score:.0f}% to {new_score:.0f}% "
                            f"({change_pct:.0f}% change)."
                        ),
                        link=f"/pipeline?lead={lead_id}",
                        metadata={
                            "lead_id": lead_id,
                            "company_name": company,
                            "old_score": old_score,
                            "new_score": new_score,
                            "change_pct": change_pct,
                        },
                    )

        except Exception:
            logger.warning(
                "Conversion score batch failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Conversion score batch complete", extra=stats)
    return stats
