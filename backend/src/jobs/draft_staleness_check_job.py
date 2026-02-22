"""Draft staleness check job for detecting outdated drafts.

This job runs every 15 minutes to check if pending drafts have become
stale because the email thread has evolved since the draft was created.

A stale draft is one where:
- It's older than 6 hours
- It's still in 'pending' user_action state
- New messages have arrived in the thread since draft creation

When detected, the draft is marked with is_stale=True and aria_notes
is updated with a warning message for the user.
"""

import logging
from typing import Any

from src.db.supabase import SupabaseClient
from src.services.autonomous_draft_engine import get_autonomous_draft_engine

logger = logging.getLogger(__name__)


async def run_draft_staleness_check() -> dict[str, Any]:
    """Run draft staleness check for all users with email integrations.

    For each user with email integration:
    1. Get pending drafts older than 6 hours
    2. Check if thread has new messages since draft creation
    3. Mark stale drafts with warning in aria_notes

    Returns:
        Dict with statistics about the check run.
    """
    stats = {
        "users_checked": 0,
        "drafts_checked": 0,
        "drafts_marked_stale": 0,
        "errors": 0,
    }

    try:
        db = SupabaseClient.get_client()

        # Get users with active email integrations who have pending drafts
        result = (
            db.table("user_integrations")
            .select("user_id")
            .in_("integration_type", ["gmail", "outlook"])
            .eq("status", "active")
            .execute()
        )

        users = result.data or []
        logger.info(
            "DRAFT_STALENESS_CHECK: Starting check for %d users with email integrations",
            len(users),
        )

        engine = get_autonomous_draft_engine()

        for user_record in users:
            user_id = user_record["user_id"]

            try:
                # Check staleness for this user's drafts
                result = await engine.check_draft_staleness(user_id)

                stats["users_checked"] += 1
                stats["drafts_checked"] += result.get("checked", 0)
                stats["drafts_marked_stale"] += result.get("stale", 0)

            except Exception as e:
                logger.warning(
                    "DRAFT_STALENESS_CHECK: Failed for user %s: %s",
                    user_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            "DRAFT_STALENESS_CHECK: Complete. Users: %d, Drafts checked: %d, "
            "Marked stale: %d, Errors: %d",
            stats["users_checked"],
            stats["drafts_checked"],
            stats["drafts_marked_stale"],
            stats["errors"],
        )

    except Exception as e:
        logger.error(
            "DRAFT_STALENESS_CHECK: Job failed: %s",
            e,
            exc_info=True,
        )
        stats["errors"] += 1

    return stats
