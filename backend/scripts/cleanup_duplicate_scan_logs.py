"""Clean up duplicate email_scan_log entries.

For each (user_id, email_id) pair, keeps only the latest scan entry
(by scanned_at) and deletes the rest. This fixes the data bloat caused
by repeated rescanning of the same emails.

Usage:
    python -m scripts.cleanup_duplicate_scan_logs [--dry-run] [--user-id USER_ID]
"""

import argparse
import logging
import sys

from src.db.supabase import SupabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def cleanup_duplicate_scan_logs(
    dry_run: bool = False,
    user_id: str | None = None,
) -> dict[str, int]:
    """Delete duplicate email_scan_log entries, keeping only the latest per email_id.

    Args:
        dry_run: If True, only report what would be deleted without deleting.
        user_id: Optional user_id to scope cleanup to a single user.

    Returns:
        Dict with stats: duplicates_found, rows_deleted.
    """
    db = SupabaseClient.get_client()
    stats = {"duplicates_found": 0, "rows_deleted": 0}

    # Step 1: Find (user_id, email_id) pairs with more than one entry
    # We do this by querying all entries and grouping in Python,
    # since Supabase REST API doesn't support GROUP BY HAVING.

    query = db.table("email_scan_log").select("id, user_id, email_id, scanned_at")
    if user_id:
        query = query.eq("user_id", user_id)

    # Fetch in pages to handle large datasets
    page_size = 1000
    offset = 0
    all_rows: list[dict] = []

    while True:
        result = query.order("scanned_at", desc=True).range(offset, offset + page_size - 1).execute()
        if not result.data:
            break
        all_rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    logger.info("Fetched %d total email_scan_log entries", len(all_rows))

    # Step 2: Group by (user_id, email_id) and find duplicates
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in all_rows:
        key = (row["user_id"], row["email_id"])
        groups.setdefault(key, []).append(row)

    # Step 3: For each group with >1 entry, keep the latest, delete the rest
    ids_to_delete: list[str] = []
    for _key, rows in groups.items():
        if len(rows) <= 1:
            continue
        # Sort by scanned_at descending (already sorted, but be safe)
        rows.sort(key=lambda r: r.get("scanned_at", ""), reverse=True)
        # Keep the first (latest), delete the rest
        duplicates = rows[1:]
        stats["duplicates_found"] += len(duplicates)
        ids_to_delete.extend(r["id"] for r in duplicates)

    if not ids_to_delete:
        logger.info("No duplicate entries found. Database is clean.")
        return stats

    logger.info(
        "Found %d duplicate entries across %d email_id groups",
        len(ids_to_delete),
        sum(1 for rows in groups.values() if len(rows) > 1),
    )

    if dry_run:
        logger.info("[DRY RUN] Would delete %d rows. Skipping.", len(ids_to_delete))
        return stats

    # Step 4: Delete in batches
    batch_size = 100
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i : i + batch_size]
        db.table("email_scan_log").delete().in_("id", batch).execute()
        stats["rows_deleted"] += len(batch)
        logger.info("Deleted batch %d-%d (%d rows)", i, i + len(batch), len(batch))

    logger.info(
        "Cleanup complete: %d duplicates found, %d rows deleted",
        stats["duplicates_found"],
        stats["rows_deleted"],
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up duplicate email_scan_log entries")
    parser.add_argument("--dry-run", action="store_true", help="Only report, don't delete")
    parser.add_argument("--user-id", type=str, help="Scope to a specific user_id")
    args = parser.parse_args()

    result = cleanup_duplicate_scan_logs(dry_run=args.dry_run, user_id=args.user_id)
    logger.info("Result: %s", result)
    sys.exit(0)
