"""Draft feedback polling job for email learning mode.

This job runs every 30 minutes to poll email clients for user actions
on ARIA-generated drafts. Since Composio lacks draft webhooks, we use
polling-based detection to track:
- APPROVED: Draft sent without significant edits
- EDITED: Draft sent with user modifications
- REJECTED: Draft deleted without sending
- IGNORED: Draft older than 7 days with no action

The feedback data is used to continuously improve style matching.
"""

import logging
from typing import Any

from src.services.draft_feedback_tracker import get_draft_feedback_tracker

logger = logging.getLogger(__name__)


async def run_draft_feedback_poll() -> dict[str, Any]:
    """Run draft feedback polling for all users with pending drafts.

    Polls email clients to detect user actions on ARIA-generated drafts
    and updates the draft records with the detected actions.

    Returns:
        Dict with statistics about the polling run.
    """
    logger.info("DRAFT_FEEDBACK_POLL: Starting draft feedback polling job")

    try:
        tracker = get_draft_feedback_tracker()
        result = await tracker.poll_all_users()

        logger.info(
            "DRAFT_FEEDBACK_POLL: Complete. Checked %d users, %d drafts total. "
            "Approved: %d, Edited: %d, Rejected: %d, Ignored: %d, Errors: %d",
            result["users_checked"],
            result["total_checked"],
            result["total_approved"],
            result["total_edited"],
            result["total_rejected"],
            result["total_ignored"],
            result["total_errors"],
        )

        return result

    except Exception as e:
        logger.error(
            "DRAFT_FEEDBACK_POLL: Job failed: %s",
            e,
            exc_info=True,
        )
        return {
            "users_checked": 0,
            "total_checked": 0,
            "total_approved": 0,
            "total_edited": 0,
            "total_rejected": 0,
            "total_ignored": 0,
            "total_errors": 1,
            "error": str(e),
        }
