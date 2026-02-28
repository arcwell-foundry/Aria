"""Background job to auto-approve MEDIUM-risk drafts past their timeout.

Runs every 5 minutes. For each pending_review draft whose auto_approve_at
has passed, saves it to the user's email client (Gmail/Outlook) and updates
the status to 'approved'. Dismissed drafts are skipped.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


async def run_draft_auto_approve() -> dict[str, Any]:
    """Find MEDIUM-risk drafts past their auto_approve_at and save to client.

    Returns:
        Dict with statistics about the auto-approve run.
    """
    stats: dict[str, Any] = {
        "total_checked": 0,
        "approved": 0,
        "failed": 0,
    }

    try:
        db = SupabaseClient.get_client()
        now = datetime.now(UTC).isoformat()

        # Find pending_review drafts whose auto_approve_at has passed
        result = (
            db.table("email_drafts")
            .select("id, user_id, recipient_email, subject")
            .eq("status", "pending_review")
            .not_.is_("auto_approve_at", "null")
            .lte("auto_approve_at", now)
            .execute()
        )

        drafts = result.data or []
        if not drafts:
            logger.debug("DRAFT_AUTO_APPROVE: No drafts eligible for auto-approval")
            return stats

        stats["total_checked"] = len(drafts)
        logger.info(
            "DRAFT_AUTO_APPROVE: Processing %d drafts past auto_approve_at",
            len(drafts),
        )

        from src.services.email_client_writer import get_email_client_writer

        client_writer = get_email_client_writer()

        for draft in drafts:
            draft_id = draft["id"]
            user_id = draft["user_id"]

            try:
                # Save to email client
                await client_writer.save_draft_to_client(
                    user_id=user_id,
                    draft_id=draft_id,
                )

                # Update status to approved
                db.table("email_drafts").update(
                    {"status": "approved"}
                ).eq("id", draft_id).execute()

                logger.info(
                    "DRAFT_AUTO_APPROVE: Auto-approved draft %s for user %s (subject: %s)",
                    draft_id,
                    user_id,
                    draft.get("subject", ""),
                )
                stats["approved"] += 1

            except Exception as e:
                logger.warning(
                    "DRAFT_AUTO_APPROVE: Failed to auto-approve draft %s: %s",
                    draft_id,
                    e,
                    exc_info=True,
                )
                stats["failed"] += 1

        logger.info(
            "DRAFT_AUTO_APPROVE: Complete. Checked: %d, Approved: %d, Failed: %d",
            stats["total_checked"],
            stats["approved"],
            stats["failed"],
        )

    except Exception as e:
        logger.error(
            "DRAFT_AUTO_APPROVE: Job failed: %s",
            e,
            exc_info=True,
        )
        stats["failed"] += 1

    return stats
