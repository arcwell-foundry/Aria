#!/usr/bin/env python3
"""Apply the domains column migration directly via Supabase RPC."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient


MIGRATION_SQL = """
-- Add domains column to monitored_entities for sender relationship resolution
ALTER TABLE monitored_entities
ADD COLUMN IF NOT EXISTS domains text[] DEFAULT '{}';

-- Add GIN index for efficient array containment queries
CREATE INDEX IF NOT EXISTS idx_monitored_entities_domains
ON monitored_entities USING GIN (domains);

-- Seed .406 Ventures for the test user if not exists
INSERT INTO monitored_entities (user_id, entity_type, entity_name, domains, is_active, monitoring_config)
SELECT
    '41475700-c1fb-4f66-8c56-77bd90b73abb',
    'investor',
    '.406 Ventures',
    ARRAY['406ventures.com'],
    true,
    '{"source": "relationship_seed", "track_news": true}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM monitored_entities
    WHERE user_id = '41475700-c1fb-4f66-8c56-77bd90b73abb'
    AND entity_name ILIKE '%406%'
);
"""


async def apply_migration():
    """Apply the migration using the Supabase client."""
    client = SupabaseClient.get_client()

    # Unfortunately, the Supabase REST client doesn't support DDL directly.
    # We need to use the rpc function or direct SQL.
    # Let's check if there's an exec_sql RPC function available.

    try:
        # Try to execute via RPC if available
        result = client.rpc("exec_sql", {"query": MIGRATION_SQL}).execute()
        print(f"Migration applied via RPC: {result}")
        return True
    except Exception as e:
        print(f"RPC not available: {e}")
        print("\nPlease apply the migration manually using one of these methods:")
        print("\n1. Supabase Dashboard SQL Editor:")
        print("   Go to https://supabase.com/dashboard/project/asqcmailhanhmyoaujje/sql")
        print("   Paste and run the contents of:")
        print("   backend/supabase/migrations/20260307200000_monitored_entities_domains.sql")
        print("\n2. Or use psql with the database URL:")
        print("   psql $DATABASE_URL -f backend/supabase/migrations/20260307200000_monitored_entities_domains.sql")
        return False


if __name__ == "__main__":
    asyncio.run(apply_migration())
