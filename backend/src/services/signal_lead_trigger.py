"""Signal-to-Lead Trigger Service.

Scans recent market signals every 30 minutes, scores them for bioprocessing
equipment relevance, and auto-creates lead_gen goals for high-scoring signals.

The vision: When Scout detects "Lonza divests capsules business" at 3 AM,
this service identifies it as a buying signal, creates a goal targeting Lonza,
and by 7 AM briefing ARIA says "I found an opportunity from last night's
signals."
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.models.goal import GoalCreate, GoalStatus, GoalType
from src.services.goal_service import GoalService

logger = logging.getLogger(__name__)

# Keyword → relevance score mapping for bioprocessing equipment signals.
# Higher scores indicate stronger buying signals.
_SIGNAL_KEYWORDS: dict[str, int] = {
    "bioreactor installation": 95,
    "bioreactor": 85,
    "facility expansion": 90,
    "manufacturing scale-up": 90,
    "manufacturing expansion": 90,
    "cell therapy manufacturing": 85,
    "gene therapy manufacturing": 85,
    "cell and gene therapy": 85,
    "gmp capacity": 80,
    "gmp facility": 80,
    "upstream bioprocessing": 85,
    "downstream bioprocessing": 85,
    "bioprocessing capacity": 85,
    "biologics manufacturing": 80,
    "cdmo expansion": 85,
    "contract manufacturing": 75,
    "single-use bioprocessing": 90,
    "chromatography system": 80,
    "filtration system": 75,
    "funding round": 60,
    "series b": 60,
    "series c": 65,
    "ipo": 55,
    "hiring": 55,
    "new plant": 85,
    "greenfield": 90,
    "fill finish": 80,
}

# Minimum score to trigger a lead_gen goal
_MIN_TRIGGER_SCORE = 70


class SignalLeadTrigger:
    """Converts high-relevance market signals into lead generation goals.

    Runs on a 30-minute scheduler cycle:
    1. Query market_signals created in the last 30 minutes, not yet processed
    2. Score each signal against bioprocessing equipment keywords
    3. For signals >= 70: check discovered_leads for duplicates, then create goal
    4. Mark signal as processed with score and timestamp
    """

    def __init__(self) -> None:
        """Initialize with database and goal service."""
        self._db = SupabaseClient.get_client()
        self._goal_service = GoalService()

    async def run(self, user_id: str) -> dict[str, Any]:
        """Process recent signals for a single user.

        Args:
            user_id: The user's UUID.

        Returns:
            Summary dict with counts.
        """
        signals_checked = 0
        goals_created = 0
        skipped_existing = 0
        skipped_low_score = 0

        try:
            # Fetch unprocessed signals from the last 30 minutes
            cutoff = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
            result = (
                self._db.table("market_signals")
                .select(
                    "id, entity_name, company_name, headline, summary, "
                    "signal_type, relevance_score, metadata"
                )
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .is_("processed_for_leads_at", "null")
                .execute()
            )

            signals = result.data or []
            if not signals:
                return {
                    "signals_checked": 0,
                    "goals_created": 0,
                    "skipped_existing": 0,
                    "skipped_low_score": 0,
                }

            signals_checked = len(signals)
            logger.info(
                "SignalLeadTrigger: %d unprocessed signals for user %s",
                signals_checked,
                user_id,
            )

            for signal in signals:
                signal_id = signal.get("id")
                # entity_name is the primary company field; fall back to company_name
                company = signal.get("entity_name") or signal.get("company_name") or ""
                headline = signal.get("headline") or ""
                summary_text = signal.get("summary") or ""
                signal_type = signal.get("signal_type") or ""

                # Score the signal
                score = self._score_signal(headline, summary_text, signal_type)

                # Mark as processed regardless of score
                self._mark_processed(signal_id, score)

                if score < _MIN_TRIGGER_SCORE:
                    skipped_low_score += 1
                    continue

                # Check if company already exists in discovered_leads
                if company and self._company_already_discovered(user_id, company):
                    skipped_existing += 1
                    logger.info(
                        "SignalLeadTrigger: skipping %s — already in discovered_leads",
                        company,
                    )
                    continue

                # Create a lead_gen goal
                try:
                    goal_title = f"Signal opportunity: {company} — {signal_type}"
                    goal_data = GoalCreate(
                        title=goal_title[:200],
                        description=(
                            f"Auto-triggered from market signal: {headline}\n\n"
                            f"{summary_text[:500]}"
                        ),
                        goal_type=GoalType.LEAD_GEN,
                        config={
                            "source": "signal_radar",
                            "auto_approve": True,
                            "signal_id": signal_id,
                            "signal_headline": headline[:200],
                            "signal_type": signal_type,
                            "company_name": company,
                            "lead_relevance_score": score,
                            "triggered_at": datetime.now(UTC).isoformat(),
                        },
                    )

                    goal = await self._goal_service.create_goal(user_id, goal_data)
                    goal_id = goal["id"]

                    # Transition to active so the hunter_lead_job picks it up
                    await self._goal_service.start_goal(user_id, goal_id)

                    goals_created += 1
                    logger.info(
                        "SignalLeadTrigger: created goal '%s' (score=%d) for user %s",
                        goal_title,
                        score,
                        user_id,
                    )
                except Exception as exc:
                    logger.exception(
                        "SignalLeadTrigger: failed to create goal for signal %s: %s",
                        signal_id,
                        exc,
                    )

        except Exception as exc:
            logger.exception(
                "SignalLeadTrigger: run failed for user %s: %s", user_id, exc
            )

        summary = {
            "signals_checked": signals_checked,
            "goals_created": goals_created,
            "skipped_existing": skipped_existing,
            "skipped_low_score": skipped_low_score,
        }
        if goals_created > 0:
            logger.info(
                "SignalLeadTrigger: user %s — %d goals created from %d signals",
                user_id,
                goals_created,
                signals_checked,
            )
        return summary

    def _score_signal(
        self, headline: str, summary: str, signal_type: str
    ) -> int:
        """Score a signal for bioprocessing equipment relevance.

        Checks headline, summary, and signal_type against keyword map.
        Returns the highest matching keyword score.

        Args:
            headline: Signal headline text.
            summary: Signal summary text.
            signal_type: Signal type string.

        Returns:
            Integer score 0-100.
        """
        text = f"{headline} {summary} {signal_type}".lower()
        best_score = 0

        for keyword, score in _SIGNAL_KEYWORDS.items():
            if keyword in text:
                best_score = max(best_score, score)

        return best_score

    def _mark_processed(self, signal_id: str, score: int) -> None:
        """Mark a signal as processed for lead generation.

        Args:
            signal_id: The market_signals row ID.
            score: The computed relevance score.
        """
        try:
            self._db.table("market_signals").update(
                {
                    "processed_for_leads_at": datetime.now(UTC).isoformat(),
                    "lead_relevance_score": score,
                }
            ).eq("id", signal_id).execute()
        except Exception as exc:
            logger.warning(
                "SignalLeadTrigger: failed to mark signal %s as processed: %s",
                signal_id,
                exc,
            )

    def _company_already_discovered(self, user_id: str, company_name: str) -> bool:
        """Check if company already exists in discovered_leads.

        Args:
            user_id: The user's UUID.
            company_name: Company name to check.

        Returns:
            True if company already has a discovered lead.
        """
        try:
            result = (
                self._db.table("discovered_leads")
                .select("id")
                .eq("user_id", user_id)
                .ilike("company_name", company_name)
                .limit(1)
                .execute()
            )
            return bool(result.data)
        except Exception as exc:
            logger.warning(
                "SignalLeadTrigger: discovered_leads check failed for %s: %s",
                company_name,
                exc,
            )
            # On error, allow goal creation (don't block on check failure)
            return False
