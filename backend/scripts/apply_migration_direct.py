#!/usr/bin/env python3
"""Apply migration directly to Supabase using REST API to execute SQL.

This uses the Supabase service role key to execute DDL statements.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings


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
    """Apply the migration via Supabase REST API."""
    # Use Supabase's REST API with service role to execute SQL
    # We can use the /rest/v1/rpc endpoint with a custom function
    # Or we can use the PostgREST direct SQL execution

    url = f"{settings.SUPABASE_URL}/rest/v1/rpc/exec_sql"

    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value(),
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        # Try to execute via RPC
        response = await client.post(
            url,
            headers=headers,
            json={"query": MIGRATION_SQL},
        )

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("Migration applied successfully!")
            return True
        elif response.status_code == 404:
            print("RPC function not found. Trying alternative approach...")
            # The exec_sql RPC doesn't exist. We need another approach.
            return False
        else:
            print(f"Failed to apply migration: {response.text}")
            return False


if __name__ == "__main__":
    asyncio.run(apply_migration())
