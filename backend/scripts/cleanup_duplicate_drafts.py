"""Clean up duplicate email_drafts entries for ALL users.

Deduplicates by two strategies:
1. thread_id: For drafts sharing (user_id, thread_id, status='draft'),
   keep the most recent, delete older duplicates.
2. recipient_email + normalized subject: For drafts without thread_id
   or where thread_id differs across scan runs, match by recipient_email
   and subject after stripping Re:/Fwd: prefixes.

Also backfills recipient_name where null, propagating from other drafts
to the same recipient_email.

Usage:
    python -m scripts.cleanup_duplicate_drafts [--dry-run]
"""

import argparse
import logging
import re
import sys

from src.db.supabase import SupabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _normalize_subject(subject: str) -> str:
    """Strip leading Re:/Fwd: prefixes for dedup comparison."""
    return re.sub(r"^(Re:\s*|Fwd?:\s*)+", "", subject, flags=re.IGNORECASE).strip()


def cleanup_duplicate_drafts(dry_run: bool = False) -> dict[str, int]:
    """Delete duplicate email_drafts, keeping the most recent per conversation.

    Args:
        dry_run: If True, only report what would be deleted.

    Returns:
        Dict with stats.
    """
    db = SupabaseClient.get_client()
    stats = {
        "thread_id_dupes_found": 0,
        "subject_dupes_found": 0,
        "rows_deleted": 0,
        "recipient_names_backfilled": 0,
    }

    # Fetch all active drafts
    page_size = 1000
    offset = 0
    all_drafts: list[dict] = []

    while True:
        result = (
            db.table("email_drafts")
            .select("id, user_id, thread_id, recipient_email, recipient_name, subject, created_at, status")
            .in_("status", ["draft", "saved_to_client"])
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        all_drafts.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    logger.info("Fetched %d active draft entries", len(all_drafts))

    ids_to_delete: set[str] = set()

    # --- Strategy 1: Dedup by (user_id, thread_id) ---
    thread_groups: dict[tuple[str, str], list[dict]] = {}
    for draft in all_drafts:
        tid = draft.get("thread_id")
        if not tid:
            continue
        key = (draft["user_id"], tid)
        thread_groups.setdefault(key, []).append(draft)

    for _key, drafts in thread_groups.items():
        if len(drafts) <= 1:
            continue
        drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        dupes = drafts[1:]
        stats["thread_id_dupes_found"] += len(dupes)
        ids_to_delete.update(d["id"] for d in dupes)

    # --- Strategy 2: Dedup by (user_id, recipient_email, normalized_subject) ---
    # Only for drafts NOT already caught by thread_id dedup
    subject_groups: dict[tuple[str, str, str], list[dict]] = {}
    for draft in all_drafts:
        if draft["id"] in ids_to_delete:
            continue
        recipient = (draft.get("recipient_email") or "").lower().strip()
        subj = _normalize_subject(draft.get("subject") or "")
        if not recipient or not subj:
            continue
        key = (draft["user_id"], recipient, subj)
        subject_groups.setdefault(key, []).append(draft)

    for _key, drafts in subject_groups.items():
        if len(drafts) <= 1:
            continue
        drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        dupes = drafts[1:]
        stats["subject_dupes_found"] += len(dupes)
        ids_to_delete.update(d["id"] for d in dupes)

    total_dupes = len(ids_to_delete)
    logger.info(
        "Found %d duplicates (%d by thread_id, %d by subject)",
        total_dupes,
        stats["thread_id_dupes_found"],
        stats["subject_dupes_found"],
    )

    if ids_to_delete and not dry_run:
        batch_size = 100
        delete_list = list(ids_to_delete)
        for i in range(0, len(delete_list), batch_size):
            batch = delete_list[i : i + batch_size]
            db.table("email_drafts").delete().in_("id", batch).execute()
            stats["rows_deleted"] += len(batch)
            logger.info("Deleted batch %d-%d (%d rows)", i, i + len(batch), len(batch))
    elif dry_run:
        logger.info("[DRY RUN] Would delete %d rows. Skipping.", total_dupes)

    # --- Backfill recipient_name where null ---
    logger.info("Starting recipient_name backfill...")
    null_name_drafts: list[dict] = []
    offset = 0
    while True:
        result = (
            db.table("email_drafts")
            .select("id, recipient_email")
            .is_("recipient_name", "null")
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        null_name_drafts.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size

    if null_name_drafts:
        # Collect unique recipient emails that need names
        emails_needing_names = {d["recipient_email"].lower().strip() for d in null_name_drafts if d.get("recipient_email")}

        # Build a mapping of email -> name from drafts that have names
        name_map: dict[str, str] = {}
        for email in emails_needing_names:
            result = (
                db.table("email_drafts")
                .select("recipient_name")
                .eq("recipient_email", email)
                .not_.is_("recipient_name", "null")
                .limit(1)
                .execute()
            )
            if result.data and result.data[0].get("recipient_name"):
                name_map[email] = result.data[0]["recipient_name"]

        # Apply backfills
        if name_map and not dry_run:
            for draft in null_name_drafts:
                email = (draft.get("recipient_email") or "").lower().strip()
                if email in name_map:
                    db.table("email_drafts").update(
                        {"recipient_name": name_map[email]}
                    ).eq("id", draft["id"]).execute()
                    stats["recipient_names_backfilled"] += 1
        elif dry_run:
            backfillable = sum(1 for d in null_name_drafts if (d.get("recipient_email") or "").lower().strip() in name_map)
            logger.info("[DRY RUN] Would backfill %d recipient_name values.", backfillable)

    logger.info(
        "Cleanup complete: %d thread_id dupes, %d subject dupes, %d rows deleted, %d names backfilled",
        stats["thread_id_dupes_found"],
        stats["subject_dupes_found"],
        stats["rows_deleted"],
        stats["recipient_names_backfilled"],
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up duplicate email_drafts entries")
    parser.add_argument("--dry-run", action="store_true", help="Only report, don't delete")
    args = parser.parse_args()

    result = cleanup_duplicate_drafts(dry_run=args.dry_run)
    logger.info("Result: %s", result)
    sys.exit(0)
