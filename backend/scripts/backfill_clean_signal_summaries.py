#!/usr/bin/env python3
"""Backfill migration script to clean existing market signal summaries.

This one-time script cleans all existing signal summaries in the database
by removing web scraping markup, navigation artifacts, and other noise.

Usage:
    cd backend
    python scripts/backfill_clean_signal_summaries.py

The script will:
1. Fetch all signals from the database
2. Apply clean_signal_summary() to each summary
3. Update only the signals where the summary changed
4. Report statistics on what was cleaned

Safety:
- Only updates the 'summary' field
- Preserves all other fields unchanged
- Skips signals where cleaning produces no change
- Dry-run mode available with --dry-run flag
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from src.core.text_cleaning import clean_signal_summary
from src.db.supabase import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_clean_summaries(dry_run: bool = False) -> dict:
    """Clean all signal summaries in the database.

    Args:
        dry_run: If True, don't actually update the database.

    Returns:
        Statistics dictionary with counts.
    """
    db = SupabaseClient.get_client()
    stats = {
        "total_signals": 0,
        "cleaned_signals": 0,
        "unchanged_signals": 0,
        "errors": 0,
    }

    # Fetch all signals with their IDs, headlines, and summaries
    logger.info("Fetching all market signals...")
    try:
        result = (
            db.table("market_signals")
            .select("id, headline, summary")
            .order("detected_at", desc=True)
            .execute()
        )
        signals = result.data
        stats["total_signals"] = len(signals)
        logger.info(f"Found {stats['total_signals']} signals to process")
    except Exception as e:
        logger.error(f"Failed to fetch signals: {e}")
        stats["errors"] += 1
        return stats

    if not signals:
        logger.info("No signals found in database")
        return stats

    # Process each signal
    for signal in signals:
        signal_id = signal.get("id")
        headline = signal.get("headline", "")
        raw_summary = signal.get("summary", "")

        if not raw_summary:
            stats["unchanged_signals"] += 1
            continue

        try:
            # Clean the summary
            cleaned_summary = clean_signal_summary(
                raw_text=raw_summary,
                headline=headline,
                max_length=500,
            )

            # Check if anything changed
            if cleaned_summary == raw_summary:
                stats["unchanged_signals"] += 1
                continue

            stats["cleaned_signals"] += 1

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update signal {signal_id[:8]}... "
                    f"(headline: {headline[:50]}...)"
                )
                logger.debug(f"  Before: {raw_summary[:100]}...")
                logger.debug(f"  After:  {cleaned_summary[:100]}...")
            else:
                # Update the signal
                db.table("market_signals").update({"summary": cleaned_summary}).eq(
                    "id", signal_id
                ).execute()
                logger.info(
                    f"Updated signal {signal_id[:8]}... "
                    f"(headline: {headline[:50]}...)"
                )

        except Exception as e:
            logger.error(f"Failed to process signal {signal_id}: {e}")
            stats["errors"] += 1

    return stats


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Clean web scraping markup from market signal summaries"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    logger.info("Starting signal summary cleanup migration...")
    stats = await backfill_clean_summaries(dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total signals:      {stats['total_signals']}")
    print(f"Cleaned signals:    {stats['cleaned_signals']}")
    print(f"Unchanged signals:  {stats['unchanged_signals']}")
    print(f"Errors:             {stats['errors']}")
    print("=" * 60)

    if args.dry_run:
        print("\nDRY RUN COMPLETE - Run without --dry-run to apply changes")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
