#!/usr/bin/env python3
"""Backfill domains column for monitored_entities.

Derives domain names from entity_name by:
1. Lowercasing
2. Removing spaces and punctuation
3. Appending .com

Examples:
  "Cytiva" → ['cytiva.com']
  "Thermo Fisher" → ['thermofisher.com']
  "Pall Corporation" → ['pall.com']

Usage:
  python scripts/backfill_entity_domains.py [--dry-run]
"""

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def derive_domain_from_name(entity_name: str) -> str | None:
    """Derive a domain name from an entity name.

    Args:
        entity_name: The entity name (e.g., "Cytiva", "Thermo Fisher")

    Returns:
        Derived domain (e.g., "cytiva.com", "thermofisher.com") or None if can't derive
    """
    if not entity_name or not entity_name.strip():
        return None

    # Lowercase
    name = entity_name.lower().strip()

    # Remove common suffixes that shouldn't be in domain
    suffixes_to_remove = [
        r"\s+inc\.?$",
        r"\s+inc$",
        r"\s+llc\.?$",
        r"\s+llc$",
        r"\s+ltd\.?$",
        r"\s+ltd$",
        r"\s+corp\.?$",
        r"\s+corp$",
        r"\s+corporation$",
        r"\s+company$",
        r"\s+co\.?$",
        r"\s+sa$",
        r"\s+ag$",
        r"\s+gmbh$",
    ]

    for suffix in suffixes_to_remove:
        name = re.sub(suffix, "", name)

    # Remove spaces and punctuation
    name = re.sub(r"[\s\.\,\-\_\&\+\(\)]+", "", name)

    # Remove leading dots or special chars
    name = name.lstrip(".-")

    # Skip if empty or too short after cleanup
    if len(name) < 2:
        return None

    # Skip if it's mostly numbers or special chars
    if re.match(r"^[0-9\.\-\_]+$", name):
        return None

    return f"{name}.com"


async def backfill_domains(dry_run: bool = False) -> dict:
    """Backfill domains for all monitored_entities with empty domains.

    Args:
        dry_run: If True, don't actually update the database

    Returns:
        Stats dict with counts of processed, updated, skipped, errors
    """
    db = SupabaseClient.get_client()

    stats = {
        "total_entities": 0,
        "empty_domains": 0,
        "updated": 0,
        "skipped_no_derivation": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    try:
        # Fetch all monitored_entities
        result = db.table("monitored_entities").select(
            "id, user_id, entity_name, entity_type, domains"
        ).execute()

        entities = result.data or []
        stats["total_entities"] = len(entities)

        logger.info(f"Found {len(entities)} total monitored_entities")

        # Filter to entities with empty domains
        entities_to_update = [
            e for e in entities
            if not e.get("domains") or len(e.get("domains", [])) == 0
        ]
        stats["empty_domains"] = len(entities_to_update)

        logger.info(f"Found {len(entities_to_update)} entities with empty domains")

        for entity in entities_to_update:
            entity_id = entity["id"]
            entity_name = entity["entity_name"]
            entity_type = entity.get("entity_type", "unknown")

            derived_domain = derive_domain_from_name(entity_name)

            if not derived_domain:
                logger.warning(
                    f"Could not derive domain for entity: '{entity_name}' (type: {entity_type})"
                )
                stats["skipped_no_derivation"] += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update '{entity_name}' → ['{derived_domain}']"
                )
                stats["updated"] += 1
            else:
                try:
                    db.table("monitored_entities").update(
                        {"domains": [derived_domain]}
                    ).eq("id", entity_id).execute()

                    logger.info(
                        f"Updated '{entity_name}' → ['{derived_domain}']"
                    )
                    stats["updated"] += 1
                except Exception as e:
                    logger.error(
                        f"Failed to update entity '{entity_name}' (id: {entity_id}): {e}"
                    )
                    stats["errors"] += 1

    except Exception as e:
        error_msg = str(e)
        if "domains" in error_msg and "does not exist" in error_msg:
            logger.error(
                "ERROR: The 'domains' column does not exist in monitored_entities table. "
                "Please apply the migration first:\n"
                "  1. Go to Supabase Dashboard > SQL Editor\n"
                "  2. Run the migration from: backend/supabase/migrations/20260307200000_monitored_entities_domains.sql"
            )
        else:
            logger.error(f"Failed to fetch entities: {e}")
        stats["errors"] += 1

    return stats


async def main():
    parser = argparse.ArgumentParser(
        description="Backfill domains column for monitored_entities"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    args = parser.parse_args()

    logger.info(f"Starting backfill (dry_run={args.dry_run})")

    stats = await backfill_domains(dry_run=args.dry_run)

    logger.info("=" * 50)
    logger.info("Backfill Summary:")
    logger.info(f"  Total entities: {stats['total_entities']}")
    logger.info(f"  Entities with empty domains: {stats['empty_domains']}")
    logger.info(f"  {'Would update' if args.dry_run else 'Updated'}: {stats['updated']}")
    logger.info(f"  Skipped (no derivation): {stats['skipped_no_derivation']}")
    logger.info(f"  Errors: {stats['errors']}")
    logger.info("=" * 50)

    if args.dry_run:
        logger.info("Run without --dry-run to apply changes")


if __name__ == "__main__":
    asyncio.run(main())
