"""Background job to retry deferred email drafts.

This job runs every 15 minutes to check deferred drafts that are ready
for processing. It re-evaluates active conversations and generates drafts
when conditions are favorable.

Used by the scheduler to follow up on deferred email threads.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Maximum number of retries before a deferred draft expires
MAX_RETRY_COUNT = 3

# Deferral period in minutes
DEFERRAL_PERIOD_MINUTES = 30


async def run_deferred_draft_retry() -> dict[str, Any]:
    """Check deferred drafts and retry those ready for processing.

    For each pending deferred draft past its deferred_until time:
    1. Check if still an active conversation
    2. If yes, defer again with incremented retry count
    3. If max retries reached, mark as expired
    4. If no longer active, trigger draft generation

    Returns:
        Dict with statistics about the retry run.
    """
    stats = {
        "total_checked": 0,
        "processed": 0,
        "skipped": 0,
        "expired": 0,
        "errors": 0,
    }

    try:
        db = SupabaseClient.get_client()
        now = datetime.now(UTC)

        # Find pending deferred drafts past their deferred_until time
        result = (
            db.table("deferred_email_drafts")
            .select("*")
            .eq("status", "pending")
            .lte("deferred_until", now.isoformat())
            .execute()
        )

        deferred = result.data or []

        if not deferred:
            logger.debug("DEFERRED_DRAFT_RETRY: No pending deferred drafts to process")
            return stats

        stats["total_checked"] = len(deferred)
        logger.info(
            "DEFERRED_DRAFT_RETRY: Processing %d deferred drafts",
            len(deferred),
        )

        for item in deferred:
            deferred_id = item["id"]
            thread_id = item["thread_id"]
            user_id = item["user_id"]
            retry_count = item.get("retry_count", 0)

            try:
                # Max retries reached - expire the draft
                if retry_count >= MAX_RETRY_COUNT:
                    db.table("deferred_email_drafts").update(
                        {"status": "expired", "updated_at": now.isoformat()}
                    ).eq("id", deferred_id).execute()

                    logger.info(
                        "DEFERRED_DRAFT_RETRY: Expired deferred draft for thread %s (max retries reached)",
                        thread_id,
                    )
                    stats["expired"] += 1
                    continue

                # Check if still an active conversation
                if await _is_active_conversation(db, user_id, thread_id):
                    # Defer again with incremented retry count
                    new_deferred_until = now + timedelta(minutes=DEFERRAL_PERIOD_MINUTES)

                    db.table("deferred_email_drafts").update(
                        {
                            "deferred_until": new_deferred_until.isoformat(),
                            "retry_count": retry_count + 1,
                            "updated_at": now.isoformat(),
                        }
                    ).eq("id", deferred_id).execute()

                    logger.info(
                        "DEFERRED_DRAFT_RETRY: Re-deferred thread %s until %s (retry %d/%d)",
                        thread_id,
                        new_deferred_until.isoformat(),
                        retry_count + 1,
                        MAX_RETRY_COUNT,
                    )
                    stats["skipped"] += 1
                    continue

                # No longer active - trigger draft generation
                await _trigger_draft_generation(db, user_id, item)

                # Mark as processed
                db.table("deferred_email_drafts").update(
                    {"status": "processed", "updated_at": now.isoformat()}
                ).eq("id", deferred_id).execute()

                logger.info(
                    "DEFERRED_DRAFT_RETRY: Successfully processed deferred draft for thread %s",
                    thread_id,
                )
                stats["processed"] += 1

            except Exception as e:
                logger.error(
                    "DEFERRED_DRAFT_RETRY: Failed to process deferred draft %s: %s",
                    deferred_id,
                    e,
                    exc_info=True,
                )
                # Increment retry_count so the entry eventually expires
                # instead of staying "pending" forever
                try:
                    new_deferred_until = now + timedelta(minutes=DEFERRAL_PERIOD_MINUTES)
                    db.table("deferred_email_drafts").update(
                        {
                            "retry_count": retry_count + 1,
                            "deferred_until": new_deferred_until.isoformat(),
                            "updated_at": now.isoformat(),
                        }
                    ).eq("id", deferred_id).execute()
                except Exception as update_err:
                    logger.error(
                        "DEFERRED_DRAFT_RETRY: Failed to update retry_count for %s: %s",
                        deferred_id,
                        update_err,
                    )
                stats["errors"] += 1

        logger.info(
            "DEFERRED_DRAFT_RETRY: Complete. Checked: %d, Processed: %d, Skipped: %d, Expired: %d, Errors: %d",
            stats["total_checked"],
            stats["processed"],
            stats["skipped"],
            stats["expired"],
            stats["errors"],
        )

    except Exception as e:
        logger.error(
            "DEFERRED_DRAFT_RETRY: Job failed: %s",
            e,
            exc_info=True,
        )
        stats["errors"] += 1

    return stats


async def _is_active_conversation(db: Any, user_id: str, thread_id: str) -> bool:
    """Check if thread has rapid back-and-forth activity (3+ messages in last hour).

    Args:
        db: Supabase client.
        user_id: The user's ID.
        thread_id: The email thread/conversation ID.

    Returns:
        True if active conversation detected, False otherwise.
    """
    try:
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)

        result = (
            db.table("email_scan_log")
            .select("sender_email")
            .eq("user_id", user_id)
            .eq("thread_id", thread_id)
            .gte("scanned_at", one_hour_ago.isoformat())
            .execute()
        )

        if not result.data or len(result.data) < 3:
            return False

        # Check if there are at least 2 different senders (back-and-forth)
        unique_senders = {msg["sender_email"].lower() for msg in result.data}

        return len(unique_senders) >= 2 and len(result.data) >= 3

    except Exception as e:
        logger.warning(
            "DEFERRED_DRAFT_RETRY: Active conversation check failed for thread %s: %s",
            thread_id,
            e,
        )
        # On error, assume NOT active to avoid blocking drafts
        return False


async def _trigger_draft_generation(db: Any, user_id: str, deferred_item: dict) -> None:
    """Trigger draft generation for a deferred email.

    Creates a synthetic email record and calls the AutonomousDraftEngine
    to generate a draft.

    Args:
        db: Supabase client.
        user_id: The user's ID.
        deferred_item: The deferred draft record with email details.
    """
    from src.services.autonomous_draft_engine import get_autonomous_draft_engine

    engine = get_autonomous_draft_engine()

    # Create a minimal email-like object from the deferred item
    class DeferredEmail:
        """Minimal email object for deferred draft processing."""

        def __init__(self, item: dict) -> None:
            self.email_id = item.get("latest_email_id", "")
            self.thread_id = item.get("thread_id", "")
            self.subject = item.get("subject", "")
            self.sender_email = item.get("sender_email", "")
            self.sender_name = None
            self.snippet = ""
            self.urgency = "NORMAL"

    email = DeferredEmail(deferred_item)

    # Get user name
    user_name = await engine._get_user_name(user_id)

    # Process the email
    draft = await engine._process_single_email(
        user_id=user_id,
        user_name=user_name,
        email=email,
        is_learning_mode=False,
    )

    if draft.success:
        logger.info(
            "DEFERRED_DRAFT_RETRY: Draft %s generated for deferred thread %s",
            draft.draft_id,
            deferred_item.get("thread_id"),
        )
    else:
        logger.warning(
            "DEFERRED_DRAFT_RETRY: Draft generation failed for deferred thread %s: %s",
            deferred_item.get("thread_id"),
            draft.error,
        )
