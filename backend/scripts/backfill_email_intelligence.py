#!/usr/bin/env python3
"""Backfill script to extract intelligence from existing emails.

This is a one-time script to process emails already in email_scan_log
that don't have corresponding memory_semantic entries.

Usage:
    cd backend
    python scripts/backfill_email_intelligence.py --user-id <user_id>

For the test user:
    python scripts/backfill_email_intelligence.py --user-id 41475700-c1fb-4f66-8c56-77bd90b73abb
"""

# Load environment variables from .env BEFORE any other imports
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient
from src.services.email_analyzer import EmailCategory
from src.services.email_intelligence import EmailIntelligenceService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_unprocessed_emails(user_id: str, limit: int = 100) -> list[EmailCategory]:
    """Get emails from email_scan_log that haven't been processed for intelligence."""
    supabase = SupabaseClient.get_client()

    # Get all emails for this user that are NEEDS_REPLY or FYI
    response = (
        supabase.table("email_scan_log")
        .select("*")
        .eq("user_id", user_id)
        .in_("category", ["NEEDS_REPLY", "FYI"])
        .order("scanned_at", desc=True)
        .limit(limit)
        .execute()
    )

    emails = response.data or []
    if not emails:
        logger.info("No emails found for user %s", user_id)
        return []

    # Get email_ids that already have memory_semantic entries
    email_ids = [e.get("email_id") for e in emails if e.get("email_id")]

    if email_ids:
        processed_response = (
            supabase.table("memory_semantic")
            .select("metadata->>email_id")
            .eq("user_id", user_id)
            .eq("source", "email_content_extraction")
            .in_("metadata->>email_id", email_ids)
            .execute()
        )

        processed_ids = set()
        for row in processed_response.data or []:
            email_id = row.get("metadata->>email_id")
            if email_id:
                processed_ids.add(email_id)
    else:
        processed_ids = set()

    # Filter to unprocessed emails
    unprocessed = []
    for email in emails:
        if email.get("email_id") not in processed_ids:
            # Convert to EmailCategory format
            category = EmailCategory(
                email_id=email.get("email_id", ""),
                thread_id=email.get("thread_id", email.get("email_id", "")),
                sender_email=email.get("sender_email", ""),
                sender_name=email.get("sender_name", ""),
                subject=email.get("subject", ""),
                snippet=email.get("snippet", "") or "",
                body=email.get("snippet", "") or "",  # Use snippet as body fallback
                category=email.get("category", "FYI"),
                urgency=email.get("urgency", "NORMAL"),
                topic_summary="",
                needs_draft=email.get("needs_draft", False),
                reason=email.get("reason", ""),
            )
            unprocessed.append(category)

    logger.info(
        "Found %d unprocessed emails out of %d total for user %s",
        len(unprocessed),
        len(emails),
        user_id,
    )
    return unprocessed


async def backfill_user(user_id: str, batch_size: int = 50, dry_run: bool = False) -> None:
    """Backfill intelligence for a specific user."""
    logger.info("Starting backfill for user %s (dry_run=%s)", user_id, dry_run)

    if dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    service = EmailIntelligenceService()
    total_processed = 0
    total_facts = 0
    total_insights = 0
    total_actions = 0

    while True:
        # Get batch of unprocessed emails
        emails = await get_unprocessed_emails(user_id, limit=batch_size)

        if not emails:
            logger.info("No more unprocessed emails for user %s", user_id)
            break

        if dry_run:
            logger.info(
                "DRY RUN: Would process %d emails: %s",
                len(emails),
                [e.subject[:50] for e in emails[:5]],
            )
            total_processed += len(emails)
            # In dry run, just continue to get the count
            break

        # Process this batch
        result = await service.extract_and_store(user_id=user_id, emails=emails)

        total_processed += result.emails_processed
        total_facts += result.facts_extracted
        total_insights += result.insights_generated
        total_actions += result.actions_created

        logger.info(
            "Batch complete: %d emails, %d facts, %d insights, %d actions",
            result.emails_processed,
            result.facts_extracted,
            result.insights_generated,
            result.actions_created,
        )

        # Small delay to avoid overwhelming the system
        await asyncio.sleep(0.5)

        # Check if we've processed all available
        if len(emails) < batch_size:
            break

    logger.info(
        "Backfill complete for user %s: "
        "%d emails processed, %d facts extracted, %d insights generated, %d actions created",
        user_id,
        total_processed,
        total_facts,
        total_insights,
        total_actions,
    )


async def verify_results(user_id: str) -> None:
    """Verify the backfill results."""
    supabase = SupabaseClient.get_client()

    # Count memory_semantic entries
    mem_response = (
        supabase.table("memory_semantic")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("source", "email_content_extraction")
        .execute()
    )
    fact_count = mem_response.count or 0

    # Count cross_email_intelligence entries
    intel_response = (
        supabase.table("cross_email_intelligence")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    insight_count = intel_response.count or 0

    # Get sample facts with Nira mentions
    nira_response = (
        supabase.table("memory_semantic")
        .select("fact, metadata->>entity")
        .eq("user_id", user_id)
        .eq("source", "email_content_extraction")
        .ilike("fact", "%nira%")
        .execute()
    )

    print("\n" + "=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    print(f"User ID: {user_id}")
    print(f"Email facts in memory_semantic: {fact_count}")
    print(f"Cross-email intelligence entries: {insight_count}")
    print()

    if nira_response.data:
        print(f"Facts about Nira Systems ({len(nira_response.data)} found):")
        for row in nira_response.data[:5]:
            entity = row.get("metadata->>entity") or row.get("entity", "Unknown")
            fact = row.get("fact", "")[:80]
            print(f"  - [{entity}] {fact}...")
    else:
        print("No facts about Nira Systems found")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill email intelligence for existing emails"
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID to backfill (e.g., 41475700-c1fb-4f66-8c56-77bd90b73abb)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of emails to process per batch (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify results, don't run backfill",
    )

    args = parser.parse_args()

    if args.verify_only:
        asyncio.run(verify_results(args.user_id))
    else:
        asyncio.run(backfill_user(args.user_id, args.batch_size, args.dry_run))
        if not args.dry_run:
            asyncio.run(verify_results(args.user_id))


if __name__ == "__main__":
    main()
