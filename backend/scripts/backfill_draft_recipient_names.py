#!/usr/bin/env python3
"""Backfill NULL recipient_name in email_drafts.

Resolves missing names from multiple sources in priority order:
1. email_scan_log (sender_name for matching sender_email)
2. memory_semantic (entity_name where fact contains the email)
3. Email address parsing (john.smith@co.com -> John Smith)

Usage:
    python backend/scripts/backfill_draft_recipient_names.py
    python backend/scripts/backfill_draft_recipient_names.py --dry-run
"""

import argparse
import logging
import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.supabase import SupabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Automated/generic local parts that should not be parsed into names
_SKIP_LOCAL_PARTS = {
    "noreply", "no-reply", "no_reply", "donotreply",
    "do-not-reply", "do_not_reply", "mailer-daemon",
    "postmaster", "admin", "support", "info", "help",
    "notifications", "notification", "alerts", "alert",
    "news", "newsletter", "updates", "billing", "sales",
    "team", "hello", "contact", "feedback", "service",
}


def parse_name_from_email(email_address: str) -> str | None:
    """Derive a human-readable name from an email address."""
    if not email_address or "@" not in email_address:
        return None

    local = email_address.split("@")[0].lower()

    if local in _SKIP_LOCAL_PARTS:
        return None

    parts = re.split(r"[._\-]+", local)
    name_parts = [p for p in parts if len(p) > 1 and not p.isdigit()]

    if not name_parts:
        return None

    return " ".join(p.capitalize() for p in name_parts)


def backfill(dry_run: bool = False) -> None:
    """Backfill NULL recipient_name in email_drafts."""
    db = SupabaseClient.get_client()

    # Step 1: Bulk update from email_scan_log (most reliable source)
    logger.info("Step 1: Backfilling from email_scan_log...")
    if not dry_run:
        try:
            result = db.rpc(
                "backfill_draft_recipient_names_from_scan_log",
                {},
            ).execute()
            logger.info("  RPC result: %s", result.data)
        except Exception:
            # RPC may not exist; fall back to manual approach
            logger.info("  RPC not available, using manual approach...")
            _backfill_from_scan_log(db, dry_run)
    else:
        _backfill_from_scan_log(db, dry_run)

    # Step 2: Backfill from memory_semantic
    logger.info("Step 2: Backfilling from memory_semantic...")
    _backfill_from_memory_semantic(db, dry_run)

    # Step 3: Backfill from email address parsing
    logger.info("Step 3: Backfilling from email address parsing...")
    _backfill_from_email_parsing(db, dry_run)

    # Step 4: Report remaining NULLs
    remaining = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .is_("recipient_name", "null")
        .execute()
    )
    # Also check for empty strings
    empty = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .eq("recipient_name", "")
        .execute()
    )
    null_count = len(remaining.data) if remaining.data else 0
    empty_count = len(empty.data) if empty.data else 0
    logger.info(
        "Remaining: %d NULL + %d empty recipient_name drafts",
        null_count,
        empty_count,
    )
    if remaining.data:
        for row in remaining.data[:10]:
            logger.info("  NULL: id=%s email=%s", row["id"], row["recipient_email"])
    if empty.data:
        for row in empty.data[:10]:
            logger.info("  EMPTY: id=%s email=%s", row["id"], row["recipient_email"])


def _backfill_from_scan_log(db, dry_run: bool) -> None:
    """Update drafts with NULL recipient_name from email_scan_log."""
    # Get all drafts with NULL or empty recipient_name
    drafts_null = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .is_("recipient_name", "null")
        .execute()
    )
    drafts_empty = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .eq("recipient_name", "")
        .execute()
    )

    drafts = (drafts_null.data or []) + (drafts_empty.data or [])
    if not drafts:
        logger.info("  No drafts with NULL/empty recipient_name found.")
        return

    # Collect unique emails
    emails = list({d["recipient_email"] for d in drafts if d.get("recipient_email")})
    logger.info("  Found %d drafts with NULL/empty names, %d unique emails", len(drafts), len(emails))

    # Look up names from scan log
    name_map: dict[str, str] = {}
    for email in emails:
        try:
            result = (
                db.table("email_scan_log")
                .select("sender_name")
                .eq("sender_email", email)
                .neq("sender_name", "")
                .not_.is_("sender_name", "null")
                .order("scanned_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data and result.data[0].get("sender_name"):
                name = result.data[0]["sender_name"].strip()
                if name:
                    name_map[email] = name
        except Exception as e:
            logger.debug("  Scan log lookup failed for %s: %s", email, e)

    logger.info("  Resolved %d names from email_scan_log", len(name_map))

    # Apply updates
    updated = 0
    for draft in drafts:
        email = draft.get("recipient_email", "")
        if email in name_map:
            if dry_run:
                logger.info("  DRY RUN: Would set %s -> '%s'", draft["id"][:8], name_map[email])
            else:
                db.table("email_drafts").update(
                    {"recipient_name": name_map[email]}
                ).eq("id", draft["id"]).execute()
            updated += 1

    logger.info("  %s %d drafts from scan_log", "Would update" if dry_run else "Updated", updated)


def _backfill_from_memory_semantic(db, dry_run: bool) -> None:
    """Update remaining NULL drafts from memory_semantic."""
    drafts_null = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .is_("recipient_name", "null")
        .execute()
    )
    drafts_empty = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .eq("recipient_name", "")
        .execute()
    )

    drafts = (drafts_null.data or []) + (drafts_empty.data or [])
    if not drafts:
        logger.info("  No remaining drafts with NULL/empty names.")
        return

    emails = list({d["recipient_email"] for d in drafts if d.get("recipient_email")})
    logger.info("  %d drafts remaining, %d unique emails", len(drafts), len(emails))

    name_map: dict[str, str] = {}
    for email in emails:
        try:
            result = (
                db.table("memory_semantic")
                .select("entity_name")
                .ilike("fact", f"%{email}%")
                .not_.is_("entity_name", "null")
                .limit(1)
                .execute()
            )
            if result.data and result.data[0].get("entity_name"):
                name = result.data[0]["entity_name"].strip()
                if name:
                    name_map[email] = name
        except Exception as e:
            logger.debug("  Memory semantic lookup failed for %s: %s", email, e)

    logger.info("  Resolved %d names from memory_semantic", len(name_map))

    updated = 0
    for draft in drafts:
        email = draft.get("recipient_email", "")
        if email in name_map:
            if dry_run:
                logger.info("  DRY RUN: Would set %s -> '%s'", draft["id"][:8], name_map[email])
            else:
                db.table("email_drafts").update(
                    {"recipient_name": name_map[email]}
                ).eq("id", draft["id"]).execute()
            updated += 1

    logger.info("  %s %d drafts from memory_semantic", "Would update" if dry_run else "Updated", updated)


def _backfill_from_email_parsing(db, dry_run: bool) -> None:
    """Update remaining NULL drafts by parsing the email address."""
    drafts_null = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .is_("recipient_name", "null")
        .execute()
    )
    drafts_empty = (
        db.table("email_drafts")
        .select("id, recipient_email")
        .eq("recipient_name", "")
        .execute()
    )

    drafts = (drafts_null.data or []) + (drafts_empty.data or [])
    if not drafts:
        logger.info("  No remaining drafts with NULL/empty names.")
        return

    logger.info("  %d drafts remaining for email parsing", len(drafts))

    updated = 0
    for draft in drafts:
        email = draft.get("recipient_email", "")
        parsed = parse_name_from_email(email)
        if parsed:
            if dry_run:
                logger.info("  DRY RUN: Would set %s (%s) -> '%s'", draft["id"][:8], email, parsed)
            else:
                db.table("email_drafts").update(
                    {"recipient_name": parsed}
                ).eq("id", draft["id"]).execute()
            updated += 1

    logger.info("  %s %d drafts from email parsing", "Would update" if dry_run else "Updated", updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill NULL recipient_name in email_drafts")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    backfill(dry_run=args.dry_run)
