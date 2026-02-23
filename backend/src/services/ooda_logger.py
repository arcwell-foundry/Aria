"""OODA Cycle Logger for admin dashboard monitoring.

Persists OODA cycle executions to the ooda_cycle_logs table
for real-time monitoring via the admin dashboard.

The table stores ONE row per full OODA cycle with columns for each phase.

Fail-open design: logging failures never block OODA processing.
"""

import logging
from typing import Any
from uuid import UUID

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class OODALogger:
    """Persists OODA cycle data for admin dashboard monitoring.

    Accumulates phase data across log_phase() calls, then writes
    a single row to ooda_cycle_logs on mark_cycle_complete().
    """

    def __init__(self) -> None:
        self._cycles: dict[str, dict[str, Any]] = {}

    async def log_phase(
        self,
        *,
        cycle_id: UUID,
        goal_id: str,
        user_id: str,
        phase: str,
        iteration: int = 0,
        input_summary: str | None = None,
        output_summary: str | None = None,
        tokens_used: int = 0,
        duration_ms: int = 0,
        thinking_effort: str | None = None,
        agents_dispatched: list[str] | None = None,
    ) -> None:
        """Accumulate phase data for a cycle.

        Args:
            cycle_id: UUID grouping phases of one OODA run.
            goal_id: The goal being pursued.
            user_id: Owner of the OODA cycle.
            phase: One of observe/orient/decide/act.
            iteration: Current iteration number.
            input_summary: Brief description of phase input.
            output_summary: Brief description of phase output.
            tokens_used: Tokens consumed in this phase.
            duration_ms: Phase execution time in milliseconds.
            thinking_effort: Thinking level used (routine/complex/critical).
            agents_dispatched: Agents dispatched during this phase.
        """
        key = str(cycle_id)
        if key not in self._cycles:
            self._cycles[key] = {
                "goal_id": goal_id,
                "user_id": user_id,
                "agent": (agents_dispatched[0] if agents_dispatched else None),
                "total_tokens": 0,
                "total_duration_ms": 0,
                "metadata": {},
            }

        cycle = self._cycles[key]
        cycle["total_tokens"] = cycle.get("total_tokens", 0) + tokens_used
        cycle["total_duration_ms"] = cycle.get("total_duration_ms", 0) + duration_ms

        if phase == "observe":
            cycle["observe_duration_ms"] = duration_ms
            cycle["observe_context_tokens"] = tokens_used
        elif phase == "orient":
            cycle["orient_duration_ms"] = duration_ms
            cycle["orient_model"] = thinking_effort
            cycle["orient_extended_thinking"] = thinking_effort in ("complex", "critical")
        elif phase == "decide":
            cycle["decide_duration_ms"] = duration_ms
            cycle["decide_action"] = (output_summary or "")[:200]
            cycle["decide_confidence"] = None
        elif phase == "act":
            cycle["act_duration_ms"] = duration_ms
            cycle["act_success"] = True
            if agents_dispatched:
                cycle["agent"] = agents_dispatched[0]

    async def mark_cycle_complete(
        self,
        *,
        cycle_id: UUID,
    ) -> None:
        """Write the accumulated cycle data to ooda_cycle_logs.

        Args:
            cycle_id: The cycle to persist and mark complete.
        """
        key = str(cycle_id)
        cycle = self._cycles.pop(key, None)
        if not cycle:
            return

        try:
            client = SupabaseClient.get_client()
            row: dict[str, Any] = {
                "user_id": cycle.get("user_id"),
                "agent": cycle.get("agent") or "ooda",
                "goal_id": cycle.get("goal_id"),
                "observe_duration_ms": cycle.get("observe_duration_ms"),
                "observe_context_tokens": cycle.get("observe_context_tokens"),
                "orient_duration_ms": cycle.get("orient_duration_ms"),
                "orient_model": cycle.get("orient_model"),
                "orient_extended_thinking": cycle.get("orient_extended_thinking", False),
                "decide_duration_ms": cycle.get("decide_duration_ms"),
                "decide_action": cycle.get("decide_action"),
                "decide_confidence": cycle.get("decide_confidence"),
                "act_duration_ms": cycle.get("act_duration_ms"),
                "act_success": cycle.get("act_success"),
                "total_duration_ms": cycle.get("total_duration_ms", 0),
                "total_tokens": cycle.get("total_tokens", 0),
                "metadata": cycle.get("metadata", {}),
            }
            client.table("ooda_cycle_logs").insert(row).execute()
            logger.info("Persisted OODA cycle %s", key)
        except Exception:
            logger.warning("Failed to persist OODA cycle %s", key, exc_info=True)
