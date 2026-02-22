"""Proactive follow-up job for overdue email commitments.

Runs on a schedule to check all users with email integrations for
overdue commitments (extracted from email threads) and auto-draft
follow-up emails.
"""

import logging
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


async def run_proactive_followup_check() -> dict[str, Any]:
    """Check all email-connected users for overdue commitments and draft follow-ups.

    Returns:
        Dict with statistics about the run.
    """
    stats: dict[str, Any] = {
        "users_checked": 0,
        "total_followups_drafted": 0,
        "errors": 0,
    }

    try:
        from src.services.proactive_followup_engine import ProactiveFollowupEngine

        db = SupabaseClient.get_client()

        # Get users with active email integrations
        result = (
            db.table("user_integrations")
            .select("user_id")
            .in_("integration_type", ["gmail", "outlook"])
            .eq("status", "active")
            .execute()
        )

        user_ids: list[str] = list({row["user_id"] for row in (result.data or [])})

        if not user_ids:
            return stats

        engine = ProactiveFollowupEngine()

        for user_id in user_ids:
            try:
                followups = await engine.check_and_draft_followups(user_id)
                stats["users_checked"] += 1
                stats["total_followups_drafted"] += len(followups)
            except Exception as e:
                stats["errors"] += 1
                logger.warning(
                    "PROACTIVE_FOLLOWUP_JOB: Error for user %s: %s",
                    user_id,
                    e,
                )

    except Exception:
        logger.exception("PROACTIVE_FOLLOWUP_JOB: Fatal error in job run")

    return stats
