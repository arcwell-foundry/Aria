"""Execution Replay Service for skill audit trail visualization.

Assembles a complete replay of a skill execution by joining data from
``skill_audit_log``, ``skill_execution_plans``, and ``skill_working_memory``.
Applies role-based redaction (admin / manager / rep) so that each user tier
sees only the data they are entitled to.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role tiers
# ---------------------------------------------------------------------------


class UserRole(str, Enum):
    """User role tiers for redaction policy."""

    ADMIN = "admin"
    MANAGER = "manager"
    REP = "user"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class WorkingMemoryStep(BaseModel):
    """A single working-memory step within an execution plan."""

    id: str
    step_number: int
    skill_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    extracted_facts: list[dict[str, Any]] = Field(default_factory=list)
    next_step_hints: list[dict[str, Any]] = Field(default_factory=list)
    status: str | None = None
    execution_time_ms: int | None = None
    created_at: str | None = None


class ExecutionPlanData(BaseModel):
    """The execution plan associated with an audit entry."""

    id: str
    task_description: str | None = None
    plan_dag: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    risk_level: str | None = None
    reasoning: str | None = None
    estimated_seconds: int | None = None
    actual_seconds: int | None = None
    approved_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class TrustImpact(BaseModel):
    """Before/after trust snapshot for the skill."""

    successful_executions_before: int = 0
    successful_executions_after: int = 0
    failed_executions_before: int = 0
    failed_executions_after: int = 0
    session_trust_granted: bool = False
    globally_approved: bool = False


class ExecutionReplayData(BaseModel):
    """Complete replay data for a single skill execution."""

    # Audit entry core fields
    execution_id: str
    user_id: str
    skill_id: str
    skill_path: str
    skill_trust_level: str
    task_id: str | None = None
    trigger_reason: str | None = None
    data_classes_requested: list[str] = Field(default_factory=list)
    data_classes_granted: list[str] = Field(default_factory=list)
    data_redacted: bool = False
    tokens_used: list[str] = Field(default_factory=list)
    input_hash: str | None = None
    output_hash: str | None = None
    execution_time_ms: int | None = None
    success: bool = False
    error: str | None = None
    sandbox_config: dict[str, Any] | None = None
    security_flags: list[str] = Field(default_factory=list)
    previous_hash: str | None = None
    entry_hash: str | None = None
    timestamp: str | None = None

    # Joined data
    execution_plan: ExecutionPlanData | None = None
    working_memory_steps: list[WorkingMemoryStep] = Field(default_factory=list)
    trust_impact: TrustImpact | None = None

    # Redaction metadata
    redaction_applied: str = "none"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ReplayService:
    """Assembles execution replay data with role-based redaction.

    Three redaction tiers are supported:

    * **admin** -- sees everything.
    * **manager** -- sees data for granted data classes; denied classes
      are redacted from audit fields.  Working-memory steps are visible.
    * **rep** (default ``user``) -- sees summaries only (``input_summary``
      and ``output_summary``); raw artifacts, facts, and DAG details are
      stripped.
    """

    def __init__(self) -> None:
        """Initialize the replay service."""
        self._client = SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_replay(
        self,
        execution_id: str,
        user_id: str,
    ) -> ExecutionReplayData:
        """Assemble a full execution replay for the given audit entry.

        Args:
            execution_id: Primary key of the ``skill_audit_log`` row.
            user_id: The requesting user's UUID (used for ownership check
                and role lookup).

        Returns:
            A fully-populated :class:`ExecutionReplayData` with redaction
            applied based on the user's role.

        Raises:
            ValueError: If the audit entry is not found or does not
                belong to the requesting user.
        """
        # 1. Fetch audit entry
        audit_entry = await self._fetch_audit_entry(execution_id, user_id)
        if audit_entry is None:
            raise ValueError(f"Audit entry {execution_id} not found for user")

        # 2. Determine user role
        user_role = await self._resolve_user_role(user_id)

        # 3. Fetch execution plan (matched by task_id or timestamp proximity)
        plan = await self._fetch_execution_plan(audit_entry)

        # 4. Fetch working memory steps (if plan found)
        steps: list[dict[str, Any]] = []
        if plan:
            steps = await self._fetch_working_memory_steps(plan["id"])

        # 5. Compute trust impact
        trust_impact = await self._compute_trust_impact(user_id, audit_entry.get("skill_id", ""))

        # 6. Build response model
        replay = self._build_replay(audit_entry, plan, steps, trust_impact)

        # 7. Apply redaction
        replay = self._apply_redaction(replay, user_role)

        return replay

    # ------------------------------------------------------------------
    # Data fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_audit_entry(self, execution_id: str, user_id: str) -> dict[str, Any] | None:
        """Fetch a single audit log entry by ID, scoped to the user.

        Args:
            execution_id: Primary key of the audit entry.
            user_id: The requesting user's UUID.

        Returns:
            The audit entry dict, or ``None`` if not found.
        """
        try:
            response = (
                self._client.table("skill_audit_log")
                .select("*")
                .eq("id", execution_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            return response.data  # type: ignore[return-value]
        except Exception:
            logger.exception(
                "Failed to fetch audit entry",
                extra={"execution_id": execution_id, "user_id": user_id},
            )
            return None

    async def _fetch_execution_plan(self, audit_entry: dict[str, Any]) -> dict[str, Any] | None:
        """Fetch the execution plan matching an audit entry.

        Tries to match by ``task_id`` first.  If the audit entry has no
        ``task_id``, falls back to matching on the same ``user_id`` with
        the closest ``created_at`` timestamp.

        Args:
            audit_entry: The audit entry dict.

        Returns:
            The execution plan dict, or ``None`` if not found.
        """
        user_id = audit_entry.get("user_id", "")
        task_id = audit_entry.get("task_id")

        try:
            # Prefer task_id match
            if task_id:
                response = (
                    self._client.table("skill_execution_plans")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("id", task_id)
                    .maybe_single()
                    .execute()
                )
                if response.data:
                    return response.data  # type: ignore[return-value]

            # Fallback: closest plan by timestamp
            audit_ts = audit_entry.get("timestamp") or audit_entry.get("created_at")
            if audit_ts:
                response = (
                    self._client.table("skill_execution_plans")
                    .select("*")
                    .eq("user_id", user_id)
                    .lte("created_at", audit_ts)
                    .order("created_at", desc=True)
                    .limit(1)
                    .maybe_single()
                    .execute()
                )
                if response.data:
                    return response.data  # type: ignore[return-value]

            return None
        except Exception:
            logger.exception(
                "Failed to fetch execution plan",
                extra={"user_id": user_id, "task_id": task_id},
            )
            return None

    async def _fetch_working_memory_steps(self, plan_id: str) -> list[dict[str, Any]]:
        """Fetch working memory steps for a given plan.

        Args:
            plan_id: The execution plan ID.

        Returns:
            List of working memory step dicts ordered by step_number.
        """
        try:
            response = (
                self._client.table("skill_working_memory")
                .select("*")
                .eq("plan_id", plan_id)
                .order("step_number", desc=False)
                .execute()
            )
            return response.data or []
        except Exception:
            logger.exception(
                "Failed to fetch working memory steps",
                extra={"plan_id": plan_id},
            )
            return []

    async def _resolve_user_role(self, user_id: str) -> UserRole:
        """Determine the user's role from their profile.

        Args:
            user_id: The user's UUID.

        Returns:
            The resolved :class:`UserRole`.  Defaults to ``REP`` if the
            role cannot be determined.
        """
        try:
            profile = await SupabaseClient.get_user_by_id(user_id)
            raw_role = profile.get("role", "user")
            if raw_role == "admin":
                return UserRole.ADMIN
            if raw_role == "manager":
                return UserRole.MANAGER
            return UserRole.REP
        except Exception:
            logger.warning(
                "Could not resolve user role, defaulting to rep",
                extra={"user_id": user_id},
            )
            return UserRole.REP

    async def _compute_trust_impact(self, user_id: str, skill_id: str) -> TrustImpact:
        """Compute trust before/after delta for a skill.

        Uses :class:`SkillAutonomyService` to retrieve current trust
        history.  The *before* values are derived by subtracting one
        from the relevant counter (success or failure).

        Args:
            user_id: The user's UUID.
            skill_id: The skill identifier.

        Returns:
            A :class:`TrustImpact` instance.
        """
        from src.skills.autonomy import SkillAutonomyService

        try:
            autonomy = SkillAutonomyService()
            history = await autonomy.get_trust_history(user_id, skill_id)

            if history is None:
                return TrustImpact()

            # Current values represent "after"
            after_successes = history.successful_executions
            after_failures = history.failed_executions

            # The last execution was either a success or failure;
            # we derive "before" by decrementing the larger-changed counter.
            # Heuristic: if the most recent event is success, decrement
            # successes; otherwise decrement failures.
            before_successes = max(0, after_successes - 1)
            before_failures = after_failures

            if (
                history.last_failure
                and history.last_success
                and history.last_failure > history.last_success
            ):
                before_successes = after_successes
                before_failures = max(0, after_failures - 1)

            return TrustImpact(
                successful_executions_before=before_successes,
                successful_executions_after=after_successes,
                failed_executions_before=before_failures,
                failed_executions_after=after_failures,
                session_trust_granted=history.session_trust_granted,
                globally_approved=history.globally_approved,
            )
        except Exception:
            logger.exception(
                "Failed to compute trust impact",
                extra={"user_id": user_id, "skill_id": skill_id},
            )
            return TrustImpact()

    # ------------------------------------------------------------------
    # Model assembly
    # ------------------------------------------------------------------

    def _build_replay(
        self,
        audit_entry: dict[str, Any],
        plan: dict[str, Any] | None,
        steps: list[dict[str, Any]],
        trust_impact: TrustImpact,
    ) -> ExecutionReplayData:
        """Build the replay response model from raw DB data.

        Args:
            audit_entry: The audit log row.
            plan: The execution plan row (may be ``None``).
            steps: The working memory step rows.
            trust_impact: Computed trust delta.

        Returns:
            A fully-populated :class:`ExecutionReplayData`.
        """
        plan_data: ExecutionPlanData | None = None
        if plan:
            plan_data = ExecutionPlanData(
                id=str(plan["id"]),
                task_description=plan.get("task_description"),
                plan_dag=plan.get("plan_dag") or {},
                status=plan.get("status"),
                risk_level=plan.get("risk_level"),
                reasoning=plan.get("reasoning"),
                estimated_seconds=plan.get("estimated_seconds"),
                actual_seconds=plan.get("actual_seconds"),
                approved_at=_safe_str(plan.get("approved_at")),
                completed_at=_safe_str(plan.get("completed_at")),
                created_at=_safe_str(plan.get("created_at")),
            )

        step_models = [
            WorkingMemoryStep(
                id=str(s["id"]),
                step_number=int(s.get("step_number", 0)),
                skill_id=s.get("skill_id"),
                input_summary=s.get("input_summary"),
                output_summary=s.get("output_summary"),
                artifacts=s.get("artifacts") or [],
                extracted_facts=s.get("extracted_facts") or [],
                next_step_hints=s.get("next_step_hints") or [],
                status=s.get("status"),
                execution_time_ms=s.get("execution_time_ms"),
                created_at=_safe_str(s.get("created_at")),
            )
            for s in steps
        ]

        return ExecutionReplayData(
            execution_id=str(audit_entry["id"]),
            user_id=str(audit_entry["user_id"]),
            skill_id=str(audit_entry["skill_id"]),
            skill_path=str(audit_entry.get("skill_path", "")),
            skill_trust_level=str(audit_entry.get("skill_trust_level", "")),
            task_id=audit_entry.get("task_id"),
            trigger_reason=audit_entry.get("trigger_reason"),
            data_classes_requested=audit_entry.get("data_classes_requested") or [],
            data_classes_granted=audit_entry.get("data_classes_granted") or [],
            data_redacted=bool(audit_entry.get("data_redacted", False)),
            tokens_used=audit_entry.get("tokens_used") or [],
            input_hash=audit_entry.get("input_hash"),
            output_hash=audit_entry.get("output_hash"),
            execution_time_ms=audit_entry.get("execution_time_ms"),
            success=bool(audit_entry.get("success", False)),
            error=audit_entry.get("error"),
            sandbox_config=audit_entry.get("sandbox_config"),
            security_flags=audit_entry.get("security_flags") or [],
            previous_hash=audit_entry.get("previous_hash"),
            entry_hash=audit_entry.get("entry_hash"),
            timestamp=_safe_str(audit_entry.get("timestamp") or audit_entry.get("created_at")),
            execution_plan=plan_data,
            working_memory_steps=step_models,
            trust_impact=trust_impact,
            redaction_applied="none",
        )

    # ------------------------------------------------------------------
    # Redaction
    # ------------------------------------------------------------------

    def _apply_redaction(
        self,
        replay: ExecutionReplayData,
        role: UserRole,
    ) -> ExecutionReplayData:
        """Apply role-based redaction to the replay data.

        * **Admin** -- no changes.
        * **Manager** -- denied data classes are redacted from the audit
          entry fields; working memory remains visible.
        * **Rep** -- raw artifacts, extracted facts, next-step hints, DAG,
          and sandbox config are stripped.  Only summaries remain.

        Args:
            replay: The unredacted replay model.
            role: The requesting user's role tier.

        Returns:
            The replay model with redaction applied.
        """
        if role == UserRole.ADMIN:
            replay.redaction_applied = "none"
            return replay

        if role == UserRole.MANAGER:
            replay.redaction_applied = "manager"
            # Redact denied data class details
            denied_classes = set(replay.data_classes_requested) - set(replay.data_classes_granted)
            if denied_classes:
                replay.security_flags = [
                    f for f in replay.security_flags if not any(dc in f for dc in denied_classes)
                ]
            return replay

        # Rep tier: summaries only
        replay.redaction_applied = "rep"
        replay.input_hash = None
        replay.output_hash = None
        replay.previous_hash = None
        replay.entry_hash = None
        replay.sandbox_config = None
        replay.security_flags = []
        replay.tokens_used = []

        # Strip plan DAG details
        if replay.execution_plan:
            replay.execution_plan.plan_dag = {}
            replay.execution_plan.reasoning = None

        # Strip step raw data, keep summaries
        for step in replay.working_memory_steps:
            step.artifacts = []
            step.extracted_facts = []
            step.next_step_hints = []

        return replay


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _safe_str(value: Any) -> str | None:
    """Convert a value to string or return None if the value is falsy.

    Args:
        value: The value to convert.

    Returns:
        String representation or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
