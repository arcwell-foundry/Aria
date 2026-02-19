"""OODA Cycle Logger for admin dashboard monitoring.

Persists OODA phase executions to the ooda_cycle_logs table
for real-time monitoring via the admin dashboard.

Fail-open design: logging failures never block OODA processing.
"""

import logging
from typing import Any
from uuid import UUID

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class OODALogger:
    """Persists OODA cycle phase data for admin dashboard monitoring."""

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
        """Log a single OODA phase execution.

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
        try:
            client = SupabaseClient.get_client()
            row: dict[str, Any] = {
                "cycle_id": str(cycle_id),
                "goal_id": goal_id,
                "user_id": user_id,
                "phase": phase,
                "iteration": iteration,
                "input_summary": (input_summary or "")[:500],
                "output_summary": (output_summary or "")[:500],
                "tokens_used": tokens_used,
                "duration_ms": duration_ms,
                "thinking_effort": thinking_effort,
                "is_complete": False,
                "agents_dispatched": agents_dispatched,
            }
            client.table("ooda_cycle_logs").insert(row).execute()
        except Exception:
            logger.warning("Failed to log OODA phase %s for cycle %s", phase, cycle_id, exc_info=True)

    async def mark_cycle_complete(
        self,
        *,
        cycle_id: UUID,
    ) -> None:
        """Mark all rows for a cycle as complete.

        Args:
            cycle_id: The cycle to mark complete.
        """
        try:
            client = SupabaseClient.get_client()
            client.table("ooda_cycle_logs").update(
                {"is_complete": True}
            ).eq("cycle_id", str(cycle_id)).execute()
        except Exception:
            logger.warning("Failed to mark OODA cycle %s complete", cycle_id, exc_info=True)
