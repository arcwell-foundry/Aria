"""Signal Deduplication Service.

Groups near-duplicate signals (same event from multiple news sources)
into clusters. The primary signal in each cluster is displayed;
others are accessible as "additional sources."
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SignalDeduplicator:
    """Groups near-duplicate market signals into clusters."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def deduplicate_signals(self, window_hours: int = 48) -> int:
        """Find and cluster near-duplicate signals from the last N hours.

        Uses headline similarity (Jaccard on word sets) + same company + time window.

        Args:
            window_hours: How far back to look for duplicates.

        Returns:
            Number of clusters created.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()

        signals = (
            self._db.table("market_signals")
            .select("id, headline, company_name, detected_at, cluster_id")
            .gte("detected_at", cutoff)
            .is_("cluster_id", "null")
            .order("detected_at", desc=True)
            .execute()
        )

        if not signals.data or len(signals.data) < 2:
            return 0

        clusters_created = 0
        processed: set[str] = set()

        for i, sig_a in enumerate(signals.data):
            if sig_a["id"] in processed:
                continue

            cluster: list[dict[str, Any]] = [sig_a]
            words_a = set((sig_a.get("headline") or "").lower().split())

            for j, sig_b in enumerate(signals.data):
                if i == j or sig_b["id"] in processed:
                    continue

                # Must be same company
                if sig_a.get("company_name") != sig_b.get("company_name"):
                    continue

                # Jaccard similarity on headline words
                words_b = set((sig_b.get("headline") or "").lower().split())
                if not words_a or not words_b:
                    continue

                intersection = words_a & words_b
                union = words_a | words_b
                similarity = len(intersection) / len(union) if union else 0

                if similarity >= 0.4:  # 40% word overlap = likely same event
                    cluster.append(sig_b)

            if len(cluster) > 1:
                cluster_uuid = str(uuid.uuid4())

                # Primary = the one with longest headline (most detail)
                cluster.sort(key=lambda s: len(s.get("headline") or ""), reverse=True)
                primary_id = cluster[0]["id"]

                for sig in cluster:
                    try:
                        self._db.table("market_signals").update(
                            {
                                "cluster_id": cluster_uuid,
                                "is_cluster_primary": sig["id"] == primary_id,
                            }
                        ).eq("id", sig["id"]).execute()
                    except Exception as e:
                        logger.warning(
                            "[SignalDedup] Failed to update signal %s: %s",
                            sig["id"],
                            e,
                        )
                    processed.add(sig["id"])

                clusters_created += 1
                logger.info(
                    "[SignalDedup] Created cluster with %d signals for %s",
                    len(cluster),
                    sig_a.get("company_name", "unknown"),
                )

        return clusters_created
