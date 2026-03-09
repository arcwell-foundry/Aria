#!/usr/bin/env python3
"""Backfill script to populate user_replied in email_scan_log from sent folder.

For all email_scan_log rows where user_replied IS NULL, checks the user's
sent folder for matching thread_ids and sets user_replied accordingly.

Usage:
    cd backend
    python scripts/backfill_user_replied.py --user-id <user_id>

    # Dry run (count only, no updates):
    python scripts/backfill_user_replied.py --user-id <user_id> --dry-run
"""

import os
from pathlib import Path
from dotenv import load_dotenv

if not os.environ.get("ANTHROPIC_API_KEY"):
    load_dotenv(Path(__file__).parent.parent / ".env")

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def fetch_sent_thread_ids(
    user_id: str,
    provider: str,
    connection_id: str,
    since_days: int = 30,
) -> dict[str, str]:
    """Fetch sent emails and return thread_id -> earliest sent_at mapping."""
    oauth_client = get_oauth_client()
    since_dt = datetime.now(UTC) - timedelta(days=since_days)
    sent_by_thread: dict[str, str] = {}

    if provider == "outlook":
        response = oauth_client.execute_action_sync(
            connection_id=connection_id,
            action="OUTLOOK_LIST_MESSAGES",
            params={
                "folder": "SentItems",
                "top": 500,
                "sent_date_time_gt": since_dt.isoformat(),
                "orderby": ["sentDateTime desc"],
            },
            user_id=user_id,
            dangerously_skip_version_check=True,
        )
        if response.get("successful"):
            data = response.get("data", {})
            raw = data.get("response_data", data).get("value", [])
            for msg in raw:
                conv_id = msg.get("conversationId")
                sent_at = msg.get("sentDateTime") or msg.get("createdDateTime", "")
                if conv_id:
                    if conv_id not in sent_by_thread or (
                        sent_at and sent_at < sent_by_thread.get(conv_id, "z")
                    ):
                        sent_by_thread[conv_id] = sent_at
        else:
            logger.error("Outlook sent fetch failed: %s", response.get("error"))
    else:
        since_epoch = int(since_dt.timestamp())
        response = oauth_client.execute_action_sync(
            connection_id=connection_id,
            action="GMAIL_FETCH_EMAILS",
            params={
                "label": "SENT",
                "max_results": 500,
                "query": f"after:{since_epoch}",
            },
            user_id=user_id,
        )
        if response.get("successful"):
            gmail_emails = response.get("data", {}).get("emails", [])
            for msg in gmail_emails:
                thread_id = msg.get("threadId") or msg.get("thread_id")
                internal_date = msg.get("internalDate")
                sent_at = ""
                if internal_date:
                    try:
                        sent_at = datetime.fromtimestamp(
                            int(internal_date) / 1000, tz=UTC
                        ).isoformat()
                    except (ValueError, TypeError):
                        pass
                if not sent_at:
                    sent_at = msg.get("date", "")
                if thread_id:
                    if thread_id not in sent_by_thread or (
                        sent_at and sent_at < sent_by_thread.get(thread_id, "z")
                    ):
                        sent_by_thread[thread_id] = sent_at
        else:
            logger.error("Gmail sent fetch failed: %s", response.get("error"))

    return sent_by_thread


async def backfill_user_replied(user_id: str, dry_run: bool = False) -> None:
    """Backfill user_replied for all NULL entries in email_scan_log."""
    supabase = SupabaseClient.get_client()

    # Get email integration
    integration_result = (
        supabase.table("user_integrations")
        .select("integration_type, composio_connection_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .in_("integration_type", ["outlook", "gmail"])
        .limit(1)
        .execute()
    )
    if not integration_result.data:
        logger.error("No active email integration found for user %s", user_id)
        return

    integration = integration_result.data[0]
    provider = integration["integration_type"]
    connection_id = integration["composio_connection_id"]

    logger.info("Using %s integration for user %s", provider, user_id)

    # Get all email_scan_log rows with user_replied IS NULL
    null_rows = (
        supabase.table("email_scan_log")
        .select("id, thread_id, scanned_at")
        .eq("user_id", user_id)
        .is_("user_replied", "null")
        .execute()
    )

    if not null_rows.data:
        logger.info("No email_scan_log rows with NULL user_replied for user %s", user_id)
        return

    logger.info(
        "Found %d email_scan_log rows with NULL user_replied", len(null_rows.data)
    )

    # Collect unique thread_ids
    thread_ids_in_log: set[str] = set()
    for row in null_rows.data:
        tid = row.get("thread_id")
        if tid:
            thread_ids_in_log.add(tid)

    logger.info("Unique thread_ids to check: %d", len(thread_ids_in_log))

    # Fetch sent emails from last 30 days
    sent_by_thread = await fetch_sent_thread_ids(
        user_id, provider, connection_id, since_days=30
    )
    logger.info("Fetched %d sent thread_ids from provider", len(sent_by_thread))

    # Match and update
    updated = 0
    marked_false = 0
    for row in null_rows.data:
        tid = row.get("thread_id")
        if not tid:
            continue

        sent_at = sent_by_thread.get(tid)
        if sent_at:
            scanned_at = row.get("scanned_at", "")
            if sent_at >= scanned_at or not scanned_at:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Would mark user_replied=true for row %s (thread %s, sent_at=%s)",
                        row["id"],
                        tid[:40],
                        sent_at,
                    )
                else:
                    supabase.table("email_scan_log").update(
                        {"user_replied": True}
                    ).eq("id", row["id"]).execute()
                updated += 1
            else:
                if not dry_run:
                    supabase.table("email_scan_log").update(
                        {"user_replied": False}
                    ).eq("id", row["id"]).execute()
                marked_false += 1
        else:
            if not dry_run:
                supabase.table("email_scan_log").update(
                    {"user_replied": False}
                ).eq("id", row["id"]).execute()
            marked_false += 1

    action = "Would update" if dry_run else "Updated"
    logger.info(
        "%s %d rows to user_replied=true, %d to false (user %s)",
        action,
        updated,
        marked_false,
        user_id,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill user_replied column in email_scan_log from sent folder"
    )
    parser.add_argument("--user-id", required=True, help="User ID to backfill")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count matches only, don't update DB",
    )
    args = parser.parse_args()

    await backfill_user_replied(args.user_id, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
