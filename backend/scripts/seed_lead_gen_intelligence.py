#!/usr/bin/env python3
"""One-time seed script for lead gen intelligence in memory_semantic.

Seeds SubIndustryContext, search vocabulary, target examples, buyer personas,
trigger relevance, signal sources, and quality principles for the test user.

Usage:
    cd backend
    python scripts/seed_lead_gen_intelligence.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_USER_ID = "41475700-c1fb-4f66-8c56-77bd90b73abb"


async def main() -> None:
    from src.services.lead_gen_intelligence import seed_lead_gen_intelligence

    # Seed with explicit bioprocessing context for the test user (Repligen)
    count = await seed_lead_gen_intelligence(
        user_id=TEST_USER_ID,
        company_type="equipment_manufacturer",
        modality="bioprocessing",
        posture="seller",
    )
    logger.info("Seeded %d entries for test user %s", count, TEST_USER_ID)

    # Verify
    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()
    result = (
        db.table("memory_semantic")
        .select("fact, metadata->entity_type")
        .eq("user_id", TEST_USER_ID)
        .like("source", "skill_lead_gen%")
        .execute()
    )
    logger.info("Verification: %d entries found", len(result.data or []))
    for row in result.data or []:
        entity_type = row.get("entity_type", "unknown")
        fact_preview = row["fact"][:80]
        logger.info("  [%s] %s...", entity_type, fact_preview)


if __name__ == "__main__":
    asyncio.run(main())
