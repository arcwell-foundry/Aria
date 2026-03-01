"""Intelligence Pulse Engine — signal routing layer.

Receives raw signals from producers (scout, email, goals, OODA, calendar),
scores salience, computes priority, routes to delivery channel, persists,
and triggers delivery.

Callers:
    - scout_signal_scan_job.py (market signals)
    - autonomous_draft_engine.py (urgent emails)
    - goal_execution.py (goal completion/blocked)
    - scheduler.py OODA checks (goal state changes)
    - scheduler.py pulse_sweep (overdue prospective memories)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Salience weights (must sum to 1.0)
_W_GOAL = 0.30
_W_TIME = 0.25
_W_VALUE = 0.20
_W_PREF = 0.15
_W_SURPRISE = 0.10

# Default thresholds (used when user has no pulse_config row)
_DEFAULT_IMMEDIATE = 90
_DEFAULT_CHECK_IN = 70
_DEFAULT_MORNING = 50
_DEFAULT_SILENT_BELOW = 30


class IntelligencePulseEngine:
    """Routes signals from producers to delivery channels.

    Args:
        supabase_client: Supabase DB client (from SupabaseClient.get_client()).
        llm_client: LLMClient instance for salience scoring (should be Haiku).
        notification_service: NotificationService class for immediate delivery.
    """

    def __init__(
        self,
        supabase_client: Any,
        llm_client: Any,
        notification_service: Any,
    ) -> None:
        self._db = supabase_client
        self._llm = llm_client
        self._notifications = notification_service

    async def process_signal(
        self,
        user_id: str,
        signal: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Main entry point. Score, route, persist, and deliver a signal.

        Args:
            user_id: The user's UUID.
            signal: Dict with keys:
                - source: str (e.g. 'scout_agent', 'email_scanner', 'calendar')
                - title: str
                - content: str
                - signal_category: str (e.g. 'competitive', 'deal_health', 'calendar', 'email', 'goal')
                - pulse_type: str ('scheduled', 'event', 'intelligent')
                - entities: list[str] (optional)
                - related_goal_id: str (optional)
                - related_lead_id: str (optional)
                - raw_data: dict (optional)

        Returns:
            The persisted pulse_signals record dict, or None on failure.
        """
        try:
            # 1. Fetch context
            active_goals = await self._fetch_active_goals(user_id)
            user_config = await self._fetch_user_config(user_id)

            # 2. Score salience
            scores = await self._score_salience(user_id, signal, active_goals)

            # 3. Compute priority
            priority_score = (
                scores["goal_relevance"] * _W_GOAL
                + scores["time_sensitivity"] * _W_TIME
                + scores["value_impact"] * _W_VALUE
                + scores["user_preference"] * _W_PREF
                + scores["surprise_factor"] * _W_SURPRISE
            ) * 100

            # 4. Determine channel
            immediate_t = user_config.get("immediate_threshold", _DEFAULT_IMMEDIATE)
            check_in_t = user_config.get("check_in_threshold", _DEFAULT_CHECK_IN)
            morning_t = user_config.get("morning_brief_threshold", _DEFAULT_MORNING)
            channel = self._determine_channel_static(
                priority_score, immediate_t, check_in_t, morning_t,
            )

            # 5. Persist
            record = await self._persist_signal(user_id, signal, scores, priority_score, channel)
            if record is None:
                return None

            # 6. Deliver
            await self._deliver(record, channel, user_id)

            return record

        except Exception:
            logger.exception(
                "IntelligencePulseEngine: failed to process signal",
                extra={"user_id": user_id, "source": signal.get("source")},
            )
            return None

    async def _fetch_active_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch user's active goals for relevance scoring."""
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "pending"])
                .execute()
            )
            return result.data or []
        except Exception:
            logger.warning("Pulse: failed to fetch active goals", extra={"user_id": user_id})
            return []

    async def _fetch_user_config(self, user_id: str) -> dict[str, Any]:
        """Fetch user pulse config, returning defaults if none exists."""
        try:
            result = (
                self._db.table("user_pulse_config")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception:
            logger.debug("Pulse: no user config found, using defaults", extra={"user_id": user_id})
        return {
            "immediate_threshold": _DEFAULT_IMMEDIATE,
            "check_in_threshold": _DEFAULT_CHECK_IN,
            "morning_brief_threshold": _DEFAULT_MORNING,
        }

    async def _score_salience(
        self,
        user_id: str,
        signal: dict[str, Any],
        active_goals: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate 5 salience dimensions.

        Uses deterministic rules for time_sensitivity, value_impact, user_preference.
        Uses LLM (Haiku) for goal_relevance and surprise_factor when no direct match.
        """
        goal_relevance = 0.1
        time_sensitivity = 0.3
        value_impact = 0.3
        user_preference = 0.5
        surprise_factor = 0.3

        source = signal.get("source", "")
        category = signal.get("signal_category", "")
        related_goal_id = signal.get("related_goal_id")

        # --- goal_relevance ---
        if related_goal_id:
            # Direct goal reference
            if any(g["id"] == related_goal_id for g in active_goals):
                goal_relevance = 0.9
            else:
                goal_relevance = 0.5
        elif active_goals:
            # Try LLM scoring for entity overlap
            try:
                goal_titles = ", ".join(g["title"] for g in active_goals[:5])
                prompt = (
                    f"Rate 0.0-1.0 how relevant this signal is to the user's active goals.\n"
                    f"Goals: {goal_titles}\n"
                    f"Signal: {signal.get('title', '')} — {signal.get('content', '')[:200]}\n"
                    f"Return JSON: {{\"goal_relevance\": 0.X, \"surprise_factor\": 0.X}}"
                )
                resp = await self._llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="You are a sales intelligence scoring engine. Return only valid JSON.",
                    max_tokens=100,
                    temperature=0.0,
                )
                parsed = json.loads(resp)
                goal_relevance = max(0.0, min(1.0, float(parsed.get("goal_relevance", 0.3))))
                surprise_factor = max(0.0, min(1.0, float(parsed.get("surprise_factor", 0.3))))
            except Exception:
                logger.debug("Pulse: LLM scoring failed, using defaults")
                goal_relevance = 0.3

        # --- time_sensitivity ---
        if category == "calendar":
            # Calendar events are time-sensitive by nature
            raw = signal.get("raw_data", {})
            hours_until = raw.get("hours_until") if raw else None
            if hours_until is not None:
                if hours_until <= 2:
                    time_sensitivity = 1.0
                elif hours_until <= 24:
                    time_sensitivity = 0.7
                else:
                    time_sensitivity = 0.4
            else:
                time_sensitivity = 0.7
        elif category == "email":
            time_sensitivity = 0.8
        elif source == "scout_agent":
            time_sensitivity = 0.6
        elif category == "goal":
            time_sensitivity = 0.5

        # --- value_impact ---
        if category == "deal_health":
            value_impact = 0.8
        elif category in ("competitive", "regulatory"):
            value_impact = 0.7
        elif category == "goal":
            value_impact = 0.6
        elif category == "email":
            value_impact = 0.5
        elif category == "calendar":
            value_impact = 0.4

        return {
            "goal_relevance": goal_relevance,
            "time_sensitivity": time_sensitivity,
            "value_impact": value_impact,
            "user_preference": user_preference,
            "surprise_factor": surprise_factor,
        }

    @staticmethod
    def _determine_channel_static(
        priority_score: float,
        immediate_threshold: int = _DEFAULT_IMMEDIATE,
        check_in_threshold: int = _DEFAULT_CHECK_IN,
        morning_brief_threshold: int = _DEFAULT_MORNING,
    ) -> str:
        """Route signal to delivery channel based on priority and thresholds."""
        if priority_score >= immediate_threshold:
            return "immediate"
        elif priority_score >= check_in_threshold:
            return "check_in"
        elif priority_score >= morning_brief_threshold:
            return "morning_brief"
        elif priority_score >= _DEFAULT_SILENT_BELOW:
            return "weekly_digest"
        else:
            return "silent"

    async def _persist_signal(
        self,
        user_id: str,
        signal: dict[str, Any],
        scores: dict[str, float],
        priority_score: float,
        channel: str,
    ) -> dict[str, Any] | None:
        """Insert signal record into pulse_signals table."""
        try:
            now = datetime.now(UTC).isoformat()
            row = {
                "user_id": user_id,
                "pulse_type": signal.get("pulse_type", "event"),
                "source": signal.get("source", "unknown"),
                "signal_category": signal.get("signal_category"),
                "title": signal["title"],
                "content": signal["content"],
                "entities": signal.get("entities", []),
                "related_goal_id": signal.get("related_goal_id"),
                "related_lead_id": signal.get("related_lead_id"),
                "raw_data": signal.get("raw_data"),
                "goal_relevance": scores["goal_relevance"],
                "time_sensitivity": scores["time_sensitivity"],
                "value_impact": scores["value_impact"],
                "user_preference": scores["user_preference"],
                "surprise_factor": scores["surprise_factor"],
                "priority_score": round(priority_score, 2),
                "delivery_channel": channel,
                "detected_at": now,
                "created_at": now,
            }
            # Mark silent signals as immediately delivered
            if channel == "silent":
                row["delivered_at"] = now

            result = self._db.table("pulse_signals").insert(row).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception:
            logger.exception(
                "Pulse: failed to persist signal",
                extra={"user_id": user_id, "title": signal.get("title")},
            )
            return None

    async def _deliver(
        self,
        record: dict[str, Any],
        channel: str,
        user_id: str,
    ) -> None:
        """Execute delivery based on channel.

        - immediate: notification + WebSocket push
        - check_in: no action (consumed by chat priming at next conversation)
        - morning_brief: no action (consumed by briefing generator)
        - weekly_digest: no action (consumed by weekly digest job)
        - silent: already marked delivered
        """
        if channel != "immediate":
            return

        try:
            from src.models.notification import NotificationType

            await self._notifications.create_notification(
                user_id=user_id,
                type=NotificationType.SIGNAL_DETECTED,
                title=record["title"],
                message=record["content"][:500],
                metadata={
                    "pulse_signal_id": record["id"],
                    "source": record["source"],
                    "priority_score": record["priority_score"],
                },
            )
        except Exception:
            logger.warning(
                "Pulse: notification delivery failed",
                extra={"user_id": user_id, "signal_id": record.get("id")},
            )

        # WebSocket push for real-time
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_signal(
                user_id=user_id,
                signal_type=record.get("signal_category", "system"),
                title=record["title"],
                severity="high" if record.get("priority_score", 0) >= 90 else "medium",
                data={
                    "pulse_signal_id": record["id"],
                    "content": record["content"][:300],
                    "source": record["source"],
                },
            )
        except Exception:
            logger.debug("Pulse: WebSocket push failed (user may not be connected)")

        # Mark as delivered
        try:
            self._db.table("pulse_signals").update(
                {"delivered_at": datetime.now(UTC).isoformat()}
            ).eq("id", record["id"]).execute()
        except Exception:
            logger.debug("Pulse: failed to mark signal as delivered")


# ---------------------------------------------------------------------------
# Module-level convenience: lazy singleton
# ---------------------------------------------------------------------------

_engine_instance: IntelligencePulseEngine | None = None


def get_pulse_engine() -> IntelligencePulseEngine:
    """Get or create the global IntelligencePulseEngine singleton.

    Uses Haiku model for cost-effective salience scoring.
    """
    global _engine_instance
    if _engine_instance is None:
        from src.core.llm import LLMClient
        from src.db.supabase import SupabaseClient
        from src.services.notification_service import NotificationService

        _engine_instance = IntelligencePulseEngine(
            supabase_client=SupabaseClient.get_client(),
            llm_client=LLMClient(model="claude-haiku-4-5-20251001"),
            notification_service=NotificationService,
        )
    return _engine_instance
