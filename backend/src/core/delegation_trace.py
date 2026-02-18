"""DelegationTraceService — immutable audit trail for every agent delegation.

Each trace records one delegator->delegatee dispatch with full context:
task characteristics, capability token, inputs/outputs, verification result,
cost, and timing. Traces form a tree via parent_trace_id so the full
delegation chain for a goal can be rendered as "show your work".
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

_TABLE = "delegation_traces"

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "re_delegated"})


@dataclass
class DelegationTrace:
    """Domain model for a single delegation trace row."""

    trace_id: str
    goal_id: str | None
    parent_trace_id: str | None
    user_id: str
    delegator: str
    delegatee: str
    task_description: str
    task_characteristics: dict[str, Any] | None = None
    capability_token: dict[str, Any] | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] | None = None
    thinking_trace: str | None = None
    verification_result: dict[str, Any] | None = None
    approval_record: dict[str, Any] | None = None
    cost_usd: float = 0.0
    status: str = "dispatched"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        """Whether this trace is in a terminal status."""
        return self.status in _TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "trace_id": self.trace_id,
            "goal_id": self.goal_id,
            "parent_trace_id": self.parent_trace_id,
            "user_id": self.user_id,
            "delegator": self.delegator,
            "delegatee": self.delegatee,
            "task_description": self.task_description,
            "task_characteristics": self.task_characteristics,
            "capability_token": self.capability_token,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "thinking_trace": self.thinking_trace,
            "verification_result": self.verification_result,
            "approval_record": self.approval_record,
            "cost_usd": float(self.cost_usd),
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationTrace:
        """Create from a database row dict."""
        return cls(
            trace_id=data["trace_id"],
            goal_id=data.get("goal_id"),
            parent_trace_id=data.get("parent_trace_id"),
            user_id=data["user_id"],
            delegator=data["delegator"],
            delegatee=data["delegatee"],
            task_description=data["task_description"],
            task_characteristics=data.get("task_characteristics"),
            capability_token=data.get("capability_token"),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs"),
            thinking_trace=data.get("thinking_trace"),
            verification_result=data.get("verification_result"),
            approval_record=data.get("approval_record"),
            cost_usd=float(data.get("cost_usd", 0)),
            status=data.get("status", "dispatched"),
            started_at=_parse_dt(data.get("started_at")),
            completed_at=_parse_dt(data.get("completed_at")),
            duration_ms=data.get("duration_ms"),
            created_at=_parse_dt(data.get("created_at")),
        )


def _parse_dt(val: str | datetime | None) -> datetime | None:
    """Parse an ISO datetime string or pass through a datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(val)


class DelegationTraceService:
    """CRUD service for the delegation_traces table."""

    def __init__(self) -> None:
        self._client = SupabaseClient.get_client()

    async def start_trace(
        self,
        *,
        user_id: str,
        goal_id: str | None = None,
        parent_trace_id: str | None = None,
        delegator: str,
        delegatee: str,
        task_description: str,
        task_characteristics: dict[str, Any] | None = None,
        capability_token: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> str:
        """Create a new trace row when a delegation begins.

        Returns the trace_id (UUID string).
        """
        trace_id = str(uuid.uuid4())
        row = {
            "trace_id": trace_id,
            "goal_id": goal_id,
            "parent_trace_id": parent_trace_id,
            "user_id": user_id,
            "delegator": delegator,
            "delegatee": delegatee,
            "task_description": task_description,
            "task_characteristics": task_characteristics,
            "capability_token": capability_token,
            "inputs": inputs or {},
            "status": "dispatched",
            "started_at": datetime.now(UTC).isoformat(),
        }
        try:
            self._client.table(_TABLE).insert(row).execute()
            logger.info(
                "Trace started: %s -> %s (trace=%s, goal=%s)",
                delegator,
                delegatee,
                trace_id,
                goal_id,
            )
        except Exception:
            logger.exception("Failed to create delegation trace")
            raise
        return trace_id

    async def complete_trace(
        self,
        *,
        trace_id: str,
        outputs: dict[str, Any] | None = None,
        verification_result: dict[str, Any] | None = None,
        cost_usd: float = 0.0,
        status: str = "completed",
    ) -> None:
        """Mark a trace as completed (or re_delegated) with outputs."""
        now = datetime.now(UTC)
        update_data: dict[str, Any] = {
            "outputs": outputs,
            "verification_result": verification_result,
            "cost_usd": cost_usd,
            "status": status,
            "completed_at": now.isoformat(),
        }
        try:
            self._client.table(_TABLE).update(update_data).eq(
                "trace_id", trace_id
            ).execute()
            logger.info(
                "Trace completed: %s status=%s cost=$%.4f",
                trace_id,
                status,
                cost_usd,
            )
        except Exception:
            logger.exception("Failed to complete delegation trace %s", trace_id)
            raise

    async def fail_trace(
        self,
        *,
        trace_id: str,
        error_message: str,
    ) -> None:
        """Mark a trace as failed with an error message in outputs."""
        now = datetime.now(UTC)
        update_data: dict[str, Any] = {
            "status": "failed",
            "outputs": {"error": error_message},
            "completed_at": now.isoformat(),
        }
        try:
            self._client.table(_TABLE).update(update_data).eq(
                "trace_id", trace_id
            ).execute()
            logger.info("Trace failed: %s error=%s", trace_id, error_message)
        except Exception:
            logger.exception("Failed to mark delegation trace %s as failed", trace_id)
            raise

    async def get_trace_tree(self, *, goal_id: str) -> list[DelegationTrace]:
        """Retrieve all traces for a goal, ordered by creation time (tree)."""
        try:
            response = (
                self._client.table(_TABLE)
                .select("*")
                .eq("goal_id", goal_id)
                .order("created_at", desc=False)
                .execute()
            )
            return [DelegationTrace.from_dict(row) for row in response.data or []]
        except Exception:
            logger.exception("Failed to get trace tree for goal %s", goal_id)
            raise

    async def get_user_traces(
        self,
        *,
        user_id: str,
        limit: int = 20,
        action_category: str | None = None,
    ) -> list[DelegationTrace]:
        """Retrieve recent traces for a user (activity feed)."""
        try:
            query = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if action_category:
                query = query.eq("delegatee", action_category)
            response = query.execute()
            return [DelegationTrace.from_dict(row) for row in response.data or []]
        except Exception:
            logger.exception("Failed to get user traces for %s", user_id)
            raise
