#!/usr/bin/env python3
"""Backfill script to populate NULL snippets in email_scan_log.

Fetches email bodies from Gmail/Outlook via Composio for scan log
entries that have NULL snippets, then updates them.

Usage:
    cd backend
    python scripts/backfill_email_snippets.py --user-id <user_id>

    # Dry run (count only, no updates):
    python scripts/backfill_email_snippets.py --user-id <user_id> --dry-run

    # With rate limiting:
    python scripts/backfill_email_snippets.py --user-id <user_id> --delay 1.0
"""

import os
from pathlib import Path
from dotenv import load_dotenv

if not os.environ.get("ANTHROPIC_API_KEY"):
    load_dotenv(Path(__file__).parent.parent / ".env")

import argparse
import asyncio
import logging
import re
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def get_null_snippet_emails(user_id: str) -> list[dict]:
    """Get distinct email_ids with NULL snippets from email_scan_log."""
    supabase = SupabaseClient.get_client()

    result = (
        supabase.table("email_scan_log")
        .select("id, email_id, sender_email")
        .eq("user_id", user_id)
        .is_("snippet", "null")
        .order("scanned_at", desc=True)
        .execute()
    )

    if not result.data:
        return []

    # Deduplicate by email_id — keep the most recent scan entry
    seen: dict[str, dict] = {}
    for row in result.data:
        eid = row.get("email_id")
        if eid and eid not in seen:
            seen[eid] = row

    return list(seen.values())


async def get_user_email_integration(user_id: str) -> dict | None:
    """Get the user's active email integration."""
    supabase = SupabaseClient.get_client()

    result = (
        supabase.table("user_integrations")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .in_("integration_type", ["gmail", "outlook"])
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


async def fetch_email_body(
    oauth_client,
    connection_id: str,
    email_id: str,
    provider: str,
    user_id: str,
) -> str | None:
    """Fetch a single email's body from Composio."""
    try:
        if provider == "gmail":
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="GMAIL_GET_MESSAGE",
                params={"message_id": email_id},
                user_id=user_id,
            )
        else:
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="OUTLOOK_GET_MESSAGE",
                params={"message_id": email_id},
                user_id=user_id,
            )

        if not response.get("successful") or not response.get("data"):
            return None

        data = response["data"]

        # Extract body from various response formats
        body = (
            data.get("body")
            or data.get("textBody")
            or data.get("snippet")
            or data.get("text")
            or ""
        )

        if isinstance(body, dict):
            body = body.get("content", body.get("data", ""))

        if not isinstance(body, str) or not body.strip():
            return None

        # Strip HTML if present
        if "<" in body:
            body = _strip_html(body)

        return body[:500] if body else None

    except Exception as e:
        logger.warning("Failed to fetch body for email %s: %s", email_id, e)
        return None


async def update_snippet(scan_id: str, snippet: str, email_id: str) -> bool:
    """Update a scan log entry's snippet."""
    try:
        supabase = SupabaseClient.get_client()
        supabase.table("email_scan_log").update(
            {"snippet": snippet}
        ).eq("id", scan_id).execute()

        # Also update ALL entries with same email_id that have NULL snippet
        supabase.table("email_scan_log").update(
            {"snippet": snippet}
        ).eq("email_id", email_id).is_("snippet", "null").execute()

        return True
    except Exception as e:
        logger.warning("Failed to update snippet for %s: %s", scan_id, e)
        return False


async def backfill(user_id: str, dry_run: bool = False, delay: float = 0.5):
    """Run the backfill process."""
    logger.info("Starting snippet backfill for user %s", user_id)

    # Get integration
    integration = await get_user_email_integration(user_id)
    if not integration:
        logger.error("No active email integration found for user %s", user_id)
        return

    provider = integration["integration_type"]
    connection_id = integration["connection_id"]
    logger.info("Using %s integration (connection: %s)", provider, connection_id[:8])

    # Get emails needing backfill
    null_entries = await get_null_snippet_emails(user_id)
    total = len(null_entries)
    logger.info("Found %d unique emails with NULL snippets", total)

    if dry_run:
        logger.info("DRY RUN — no updates will be made")
        return

    if total == 0:
        logger.info("Nothing to backfill!")
        return

    oauth_client = get_oauth_client()
    success = 0
    failed = 0

    for i, entry in enumerate(null_entries, 1):
        email_id = entry["email_id"]
        scan_id = entry["id"]

        body = await fetch_email_body(
            oauth_client, connection_id, email_id, provider, user_id
        )

        if body:
            if await update_snippet(scan_id, body, email_id):
                success += 1
                logger.info(
                    "Backfilled %d/%d: %s (%.0f chars)",
                    i, total, email_id[:20], len(body),
                )
            else:
                failed += 1
        else:
            failed += 1
            logger.debug("No body available for email %s", email_id[:20])

        # Rate limit
        if delay > 0:
            await asyncio.sleep(delay)

    logger.info(
        "Backfill complete: %d success, %d failed out of %d total",
        success, failed, total,
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill NULL email snippets")
    parser.add_argument("--user-id", required=True, help="User ID to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no updates")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    asyncio.run(backfill(args.user_id, args.dry_run, args.delay))


if __name__ == "__main__":
    main()
