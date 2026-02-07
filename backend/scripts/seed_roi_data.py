#!/usr/bin/env python3
"""Seed script for ROI Analytics testing (US-943).

This script generates sample data for aria_actions, intelligence_delivered,
and pipeline_impact tables for development and testing purposes.

Usage:
    cd backend && python scripts/seed_roi_data.py --user-id <user_id>
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from supabase import Client, create_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Sample data templates
ACTION_TYPES = [
    "email_draft",
    "meeting_prep",
    "research_report",
    "crm_update",
    "follow_up",
    "lead_discovery",
]

INTELLIGENCE_TYPES = [
    "fact",
    "signal",
    "gap_filled",
    "briefing",
    "proactive_insight",
]

IMPACT_TYPES = [
    "lead_discovered",
    "meeting_prepped",
    "follow_up_sent",
    "deal_influenced",
]

STATUSES = ["pending", "auto_approved", "user_approved", "rejected"]


def get_supabase_client() -> Client:
    """Create Supabase client from environment variables."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    return create_client(url, key)


def seed_aria_actions(client: Client, user_id: UUID, days: int = 30) -> int:
    """Seed sample aria_actions data.

    Args:
        client: Supabase client
        user_id: User ID to seed data for
        days: Number of days to generate data for

    Returns:
        Number of records inserted
    """
    logger.info(f"Seeding aria_actions for user {user_id}...")

    records = []
    now = datetime.utcnow()

    for day in range(days):
        date = now - timedelta(days=day)

        # Generate 2-5 actions per day
        for _ in range(2, 6):
            action_type = ACTION_TYPES[hash(day) % len(ACTION_TYPES)]
            minutes_saved = {
                "email_draft": 15,
                "meeting_prep": 30,
                "research_report": 45,
                "crm_update": 10,
                "follow_up": 8,
                "lead_discovery": 20,
            }.get(action_type, 15)

            record = {
                "user_id": str(user_id),
                "action_type": action_type,
                "source_id": f"source_{day}_{len(records)}",
                "status": STATUSES[hash(day) % len(STATUSES)],
                "estimated_minutes_saved": minutes_saved,
                "metadata": {
                    "context": f"Sample {action_type} action",
                    "generated_by": "seed_script",
                },
                "created_at": date.isoformat(),
                "completed_at": (date + timedelta(minutes=5)).isoformat()
                if hash(day) % 3 != 0
                else None,
            }
            records.append(record)

    # Batch insert
    result = client.table("aria_actions").insert(records).execute()
    count = len(result.data)
    logger.info(f"✓ Inserted {count} aria_actions records")
    return count


def seed_intelligence_delivered(client: Client, user_id: UUID, days: int = 30) -> int:
    """Seed sample intelligence_delivered data.

    Args:
        client: Supabase client
        user_id: User ID to seed data for
        days: Number of days to generate data for

    Returns:
        Number of records inserted
    """
    logger.info(f"Seeding intelligence_delivered for user {user_id}...")

    records = []
    now = datetime.utcnow()

    for day in range(days):
        date = now - timedelta(days=day)

        # Generate 3-7 intelligence items per day
        for _ in range(3, 8):
            intelligence_type = INTELLIGENCE_TYPES[
                hash(day + _) % len(INTELLIGENCE_TYPES)
            ]

            record = {
                "user_id": str(user_id),
                "intelligence_type": intelligence_type,
                "source_id": f"intel_source_{day}_{_}",
                "confidence_score": 0.7 + (hash(day) % 30) / 100,  # 0.7-0.99
                "metadata": {
                    "context": f"Sample {intelligence_type}",
                    "generated_by": "seed_script",
                },
                "delivered_at": date.isoformat(),
            }
            records.append(record)

    # Batch insert
    result = client.table("intelligence_delivered").insert(records).execute()
    count = len(result.data)
    logger.info(f"✓ Inserted {count} intelligence_delivered records")
    return count


def seed_pipeline_impact(client: Client, user_id: UUID, days: int = 30) -> int:
    """Seed sample pipeline_impact data.

    Args:
        client: Supabase client
        user_id: User ID to seed data for
        days: Number of days to generate data for

    Returns:
        Number of records inserted
    """
    logger.info(f"Seeding pipeline_impact for user {user_id}...")

    records = []
    now = datetime.utcnow()

    for day in range(days):
        date = now - timedelta(days=day)

        # Generate 0-3 impact items per day
        for _ in range(hash(day) % 4):
            impact_type = IMPACT_TYPES[hash(day + _) % len(IMPACT_TYPES)]

            # Estimated value in USD
            estimated_value = {
                "lead_discovered": 50000,
                "meeting_prepped": 10000,
                "follow_up_sent": 5000,
                "deal_influenced": 150000,
            }.get(impact_type, 10000)

            record = {
                "user_id": str(user_id),
                "impact_type": impact_type,
                "source_id": f"impact_source_{day}_{_}",
                "estimated_value": float(estimated_value),
                "metadata": {
                    "context": f"Sample {impact_type}",
                    "generated_by": "seed_script",
                },
                "created_at": date.isoformat(),
            }
            records.append(record)

    if not records:
        logger.warning("No pipeline_impact records to insert")
        return 0

    # Batch insert
    result = client.table("pipeline_impact").insert(records).execute()
    count = len(result.data)
    logger.info(f"✓ Inserted {count} pipeline_impact records")
    return count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed ROI analytics data for testing"
    )
    parser.add_argument(
        "--user-id",
        type=str,
        required=True,
        help="User ID to seed data for (UUID)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to generate data for (default: 30)",
    )
    parser.add_argument(
        "--skip-actions",
        action="store_true",
        help="Skip seeding aria_actions",
    )
    parser.add_argument(
        "--skip-intelligence",
        action="store_true",
        help="Skip seeding intelligence_delivered",
    )
    parser.add_argument(
        "--skip-impact",
        action="store_true",
        help="Skip seeding pipeline_impact",
    )

    args = parser.parse_args()

    # Validate user_id
    try:
        user_id = UUID(args.user_id)
    except ValueError:
        logger.error(f"Invalid user_id: {args.user_id}")
        sys.exit(1)

    # Get client
    client = get_supabase_client()

    # Seed data
    total_count = 0

    if not args.skip_actions:
        count = seed_aria_actions(client, user_id, args.days)
        total_count += count

    if not args.skip_intelligence:
        count = seed_intelligence_delivered(client, user_id, args.days)
        total_count += count

    if not args.skip_impact:
        count = seed_pipeline_impact(client, user_id, args.days)
        total_count += count

    logger.info(f"\n✓ Seeding complete! Total records: {total_count}")
    logger.info(f"  User: {user_id}")
    logger.info(f"  Period: {args.days} days")


if __name__ == "__main__":
    main()
