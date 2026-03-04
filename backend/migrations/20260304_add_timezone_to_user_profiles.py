"""Migration: Add timezone column to user_profiles.

This migration adds a timezone column to user_profiles to enable
proper timezone conversion for all ARIA interactions.

Run this migration directly against Supabase SQL editor or via the migration runner.

SQL to execute:
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/New_York';

To set timezone for a specific user:
    UPDATE user_profiles SET timezone = 'America/New_York' WHERE full_name = 'Dhruv Patwardhan';
"""

import asyncio
import logging
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


async def run_migration() -> bool:
    """Run the migration to add timezone column.

    Returns:
        True if successful, False otherwise.
    """
    try:
        from src.db.supabase import get_supabase_client

        db = get_supabase_client()

        # Check if timezone column already exists
        check_result = db.table("user_profiles").select("timezone").limit(1).execute()
        logger.info("Timezone column already exists")
        return True

    except Exception as e:
        if "column" in str(e).lower() and "does not exist" in str(e).lower():
            logger.info("Timezone column does not exist - creating it...")
            # Need to use raw SQL via Supabase
            # This requires the SQL to be run manually in Supabase dashboard
            logger.warning(
                "Cannot add column via Supabase Python client. "
                "Please run this SQL in Supabase SQL Editor:\n\n"
                "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/New_York';"
            )
            return False
        logger.error("Migration check failed: %s", e)
        return False


def get_migration_sql() -> str:
    """Return the SQL to run for this migration."""
    return """
-- Add timezone column to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/New_York';

-- Set timezone for existing user (Dhruv)
UPDATE user_profiles SET timezone = 'America/New_York' WHERE full_name = 'Dhruv Patwardhan';

-- Verify the column was added
SELECT id, full_name, timezone FROM user_profiles LIMIT 5;
"""


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Add timezone to user_profiles")
    print("=" * 60)
    print("\nSQL to run in Supabase SQL Editor:\n")
    print(get_migration_sql())
    print("\n" + "=" * 60)
    print("After running the SQL, verify with:")
    print("  SELECT timezone FROM user_profiles LIMIT 1;")
    print("=" * 60)
