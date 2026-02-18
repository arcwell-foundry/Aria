"""Proactive stale leads detection job (Task h).

Runs daily at 7:00 AM. Wraps existing LeadProactiveBehaviors.check_silent_leads
and adds ProactiveRouter integration for priority-based delivery.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.business_hours import get_active_user_ids
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)

# Thresholds for staleness
STALE_HIGH_DAYS = 30
STALE_MEDIUM_DAYS = 14


async def run_stale_leads_job() -> dict[str, Any]:
    """Check for stale leads across all active users.

    For each user:
    1. Run LeadProactiveBehaviors.check_silent_leads (creates notifications)
    2. Additionally query leads with last_activity_at > 14 days ago
    3. Route via ProactiveRouter: 30+ days -> HIGH, 14-29 days -> MEDIUM

    Returns:
        Summary dict with detection statistics.
    """
    stats: dict[str, Any] = {
        "users_processed": 0,
        "notifications_from_behaviors": 0,
        "stale_leads_high": 0,
        "stale_leads_medium": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Stale leads check: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            stats["users_processed"] += 1

            # Run existing proactive behaviors (creates its own notifications)
            try:
                from src.behaviors.lead_proactive import LeadProactiveBehaviors

                behaviors = LeadProactiveBehaviors(db_client=db)
                notifs = await behaviors.check_silent_leads(user_id)
                stats["notifications_from_behaviors"] += notifs
            except Exception:
                logger.warning(
                    "LeadProactiveBehaviors.check_silent_leads failed for user %s",
                    user_id,
                    exc_info=True,
                )

            # Additional query for ProactiveRouter-based routing
            cutoff_medium = (datetime.now(UTC) - timedelta(days=STALE_MEDIUM_DAYS)).isoformat()

            leads_result = (
                db.table("lead_memories")
                .select("id, company_name, last_activity_at")
                .eq("user_id", user_id)
                .eq("status", "active")
                .lt("last_activity_at", cutoff_medium)
                .order("last_activity_at", desc=False)
                .limit(20)
                .execute()
            )

            stale_leads = leads_result.data or []

            for lead in stale_leads:
                lead_id = lead["id"]
                company_name = lead.get("company_name", "Unknown")
                last_activity = lead.get("last_activity_at")

                # Calculate days inactive
                days_inactive = STALE_MEDIUM_DAYS  # fallback
                if last_activity:
                    try:
                        last_dt = datetime.fromisoformat(
                            last_activity.replace("Z", "+00:00")
                        )
                        days_inactive = (datetime.now(UTC) - last_dt).days
                    except (ValueError, TypeError):
                        pass

                if days_inactive >= STALE_HIGH_DAYS:
                    priority = InsightPriority.HIGH
                    stats["stale_leads_high"] += 1
                else:
                    priority = InsightPriority.MEDIUM
                    stats["stale_leads_medium"] += 1

                await router.route(
                    user_id=user_id,
                    priority=priority,
                    category=InsightCategory.STALE_LEAD,
                    title=f"Silent Lead: {company_name}",
                    message=(
                        f"{company_name} has had no activity for {days_inactive} days. "
                        "Consider reaching out to re-engage this relationship."
                    ),
                    link=f"/pipeline?lead={lead_id}",
                    metadata={
                        "lead_id": lead_id,
                        "company_name": company_name,
                        "days_inactive": days_inactive,
                    },
                )

        except Exception:
            logger.warning(
                "Stale leads check failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Stale leads check complete", extra=stats)
    return stats
