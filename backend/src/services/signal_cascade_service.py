"""Signal Cascade Service — fan out new market signals to downstream systems.

When a new market_signal is written, cascade it to:
1. discovered_leads health score update (if company is already a lead)
2. lead_memory_events (signal event in the lead's timeline)
3. battle_cards recent_developments (if company is a competitor)
4. memory_semantic (company intelligence fact)
5. monitored_entities last_checked_at update
6. pulse_signals (real-time Intelligence page notification)

All operations are fail-open: a single cascade failure never blocks others.
Multi-tenant: all operations filter by user_id from the signal record.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class SignalCascadeService:
    """Fan out a new market signal to all downstream systems."""

    async def cascade(self, signal: dict[str, Any], user_id: str) -> None:
        """Run all cascade operations in parallel. Fail-open on partial failure.

        Args:
            signal: Dict with keys from market_signals row (company_name,
                headline, summary, signal_type, relevance_score, etc.).
            user_id: Owning user UUID.
        """
        tasks = [
            self._update_lead_health(signal, user_id),
            self._write_lead_memory_event(signal, user_id),
            self._update_battle_card(signal, user_id),
            self._write_semantic_memory(signal, user_id),
            self._update_monitored_entity(signal, user_id),
            self._push_pulse_signal(signal, user_id),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        cascade_labels = [
            "lead_health",
            "lead_memory_event",
            "battle_card",
            "semantic_memory",
            "monitored_entity",
            "pulse_signal",
        ]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "[CASCADE] %s failed for %s: %s",
                    cascade_labels[i],
                    signal.get("company_name", "?"),
                    result,
                )

    async def _update_lead_health(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """If the signaling company is a discovered lead, boost its health score."""
        company = signal.get("company_name", "")
        if not company:
            return

        db = SupabaseClient.get_client()
        lead = (
            db.table("discovered_leads")
            .select("id, fit_score")
            .eq("user_id", user_id)
            .ilike("company_name", company)
            .limit(1)
            .execute()
        )

        if lead.data:
            lead_id = lead.data[0]["id"]
            current_score = lead.data[0].get("fit_score") or 0
            buying_score = (signal.get("metadata") or {}).get(
                "lead_relevance_score",
                signal.get("relevance_score", 0.5),
            )
            boost = int(float(buying_score) * 10)
            new_score = min(100, current_score + boost)

            db.table("discovered_leads").update(
                {
                    "fit_score": new_score,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", lead_id).eq("user_id", user_id).execute()

    async def _write_lead_memory_event(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """Add signal as a timeline event in lead memory.

        Note: lead_memory_events has no user_id column — it links through
        lead_memory_id FK to lead_memories.
        """
        company = signal.get("company_name", "")
        if not company:
            return

        db = SupabaseClient.get_client()
        lead_memory = (
            db.table("lead_memories")
            .select("id")
            .eq("user_id", user_id)
            .ilike("company_name", company)
            .limit(1)
            .execute()
        )

        if lead_memory.data:
            db.table("lead_memory_events").insert(
                {
                    "lead_memory_id": lead_memory.data[0]["id"],
                    "event_type": "market_signal",
                    "subject": (signal.get("headline") or "")[:200],
                    "content": signal.get("summary") or "",
                    "occurred_at": (
                        signal.get("detected_at")
                        or datetime.now(UTC).isoformat()
                    ),
                    "source": signal.get("source_name") or "signal_cascade",
                    "metadata": {
                        "signal_type": signal.get("signal_type"),
                        "relevance_score": signal.get("relevance_score"),
                        "signal_id": signal.get("id"),
                    },
                }
            ).execute()

    async def _update_battle_card(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """If signaling company is a competitor, append to battle card overview.

        Note: battle_cards has no metadata or user_id column. Access is
        through company_id (via user_profiles join).
        """
        company = signal.get("company_name", "")
        if not company:
            return

        db = SupabaseClient.get_client()

        # Get user's company_id
        profile = (
            db.table("user_profiles")
            .select("company_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if not profile.data:
            return
        company_id = profile.data[0].get("company_id")
        if not company_id:
            return

        card = (
            db.table("battle_cards")
            .select("id, overview")
            .eq("company_id", company_id)
            .ilike("competitor_name", company)
            .limit(1)
            .execute()
        )

        if card.data:
            existing_overview = card.data[0].get("overview") or ""
            signal_date = (
                signal.get("detected_at", "")[:10]
                if signal.get("detected_at")
                else datetime.now(UTC).strftime("%Y-%m-%d")
            )
            new_entry = (
                f"\n\n[{signal_date}] {signal.get('signal_type', 'signal')}: "
                f"{(signal.get('headline') or '')[:200]}"
            )
            # Keep overview from growing unbounded — trim to last ~3000 chars
            updated_overview = (existing_overview + new_entry)[-3000:]

            db.table("battle_cards").update(
                {
                    "overview": updated_overview,
                    "last_updated": datetime.now(UTC).isoformat(),
                    "update_source": "auto",
                }
            ).eq("id", card.data[0]["id"]).eq(
                "company_id", company_id
            ).execute()

    async def _write_semantic_memory(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """Write signal as a semantic memory fact for future retrieval.

        Note: memory_semantic uses ``fact`` column, not ``content``.
        """
        company = signal.get("company_name", "")
        headline = signal.get("headline", "")
        if not company or not headline:
            return

        db = SupabaseClient.get_client()
        db.table("memory_semantic").insert(
            {
                "user_id": user_id,
                "fact": f"{company}: {headline}",
                "confidence": signal.get("relevance_score", 0.7),
                "source": "signal_cascade",
                "metadata": {
                    "signal_type": signal.get("signal_type"),
                    "company": company,
                    "detected_at": signal.get("detected_at"),
                },
            }
        ).execute()

    async def _update_monitored_entity(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """Update last_checked_at on the monitored entity."""
        company = signal.get("company_name", "")
        if not company:
            return

        db = SupabaseClient.get_client()
        db.table("monitored_entities").update(
            {"last_checked_at": datetime.now(UTC).isoformat()}
        ).eq("user_id", user_id).ilike("entity_name", company).execute()

    async def _push_pulse_signal(
        self, signal: dict[str, Any], user_id: str
    ) -> None:
        """Push high-relevance signals to Intelligence Pulse for real-time delivery."""
        relevance = signal.get("relevance_score", 0)
        if relevance < 0.75:
            return

        high_urgency_types = {
            "fda_approval",
            "clinical_trial_phase3_start",
            "facility_expansion",
            "fda_warning_letter",
        }
        time_sensitivity = (
            0.9 if signal.get("signal_type") in high_urgency_types else 0.5
        )

        db = SupabaseClient.get_client()
        db.table("pulse_signals").insert(
            {
                "user_id": user_id,
                "title": (signal.get("headline") or "")[:200],
                "content": signal.get("summary") or "",
                "pulse_type": "event",
                "signal_category": signal.get("signal_type"),
                "source": signal.get("source_name") or "signal_cascade",
                "goal_relevance": 0.5,
                "time_sensitivity": time_sensitivity,
                "value_impact": relevance,
                "user_preference": 0.5,
                "surprise_factor": 0.6,
                "priority_score": int(relevance * 100),
                "detected_at": (
                    signal.get("detected_at")
                    or datetime.now(UTC).isoformat()
                ),
            }
        ).execute()
