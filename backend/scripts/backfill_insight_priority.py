#!/usr/bin/env python3
"""Backfill script to label existing insights and link signals.

Run once after deploying the Intelligence Page V2 changes:
    PYTHONPATH=. python3 scripts/backfill_insight_priority.py

This script will:
1. Add priority_label to all existing insights in jarvis_insights
2. Run signal deduplication to cluster near-duplicate signals
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient
from src.intelligence.signal_deduplication import SignalDeduplicator


async def main():
    """Run the backfill to label insights and dedupe signals."""
    print("Starting insight priority backfill...")

    db = SupabaseClient.get_client()

    # 1. Label existing insights that don't have priority_label set
    print("\n[1/2] Labeling insights without priority_label...")
    try:
        insights_result = (
            db.table("jarvis_insights")
            .select("id, confidence, classification")
            .is_("priority_label", "null")
            .execute()
        )
    except Exception as e:
        print(f"Error fetching insights: {e}")
        return

    insights = insights_result.data or []
    print(f"Found {len(insights)} insights to label")

    if not insights:
        print("No insights to label. Skipping...")
    else:
        labeled_count = 0
        for i in insights:
            conf = i.get("confidence", 0)
            classification = i.get("classification", "")

            if conf >= 0.7 and classification == "threat":
                label = "critical"
            elif conf >= 0.6:
                label = "high"
            elif conf >= 0.4:
                label = "medium"
            else:
                label = "low"

            try:
                db.table("jarvis_insights").update(
                    {"priority_label": label}
                ).eq("id", i["id"]).execute()
                labeled_count += 1
                if labeled_count % 100 == 00:
                    print(f"  Labeled {labeled_count}/{len(insights)} insights...")
            except Exception as e:
                print(f"  Failed to label insight {i['id']}: {e}")

        print(f"[1/2] Complete: Labeled {labeled_count} insights")

    # 2. Run signal deduplication
    print("\n[2/2] Running signal deduplication (90 days window)...")
    try:
        dedup = SignalDeduplicator(db)
        clusters = await dedup.deduplicate_signals(window_hours=2160)  # 90 days
        print(f"[2/2] Complete: Created {clusters} signal clusters")
    except Exception as e:
        print(f"Signal deduplication failed: {e}")

    print("\n=== Backfill complete ===")


if __name__ == "__main__":
    asyncio.run(main())
