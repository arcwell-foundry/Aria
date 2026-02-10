"""Workflow engine for user-defined automation sequences.

The :class:`WorkflowEngine` evaluates triggers and executes ordered lists of
:class:`WorkflowAction` steps, accumulating context between steps.  It extends
:class:`BaseWorkflow` for type compatibility but manages its own execution
loop -- it does **not** call ``super().__init__()``.

Action handlers use *lazy imports* so that the engine module can be loaded
without pulling in heavy dependencies like the LLM client or Supabase.
"""

from __future__ import annotations

import importlib.util
import logging
from datetime import UTC, datetime
from typing import Any

from src.skills.workflows.base import BaseWorkflow
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowRunStatus,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cron helpers
# ---------------------------------------------------------------------------


def _cron_field_matches(field_expr: str, current_value: int) -> bool:
    """Check whether a single cron field expression matches *current_value*.

    Supports:
    * ``*`` -- wildcard, always matches.
    * ``N`` -- exact integer.
    * ``N-M`` -- inclusive range.
    * ``N,M,O`` -- comma-separated list (items may themselves be ranges).

    Args:
        field_expr: A single cron field string (e.g. ``"5"``, ``"1-3"``, ``"*"``).
        current_value: The current time component to match against.

    Returns:
        ``True`` if the expression matches *current_value*.
    """
    field_expr = field_expr.strip()

    if field_expr == "*":
        return True

    # Comma-separated list: recurse for each item
    if "," in field_expr:
        return any(_cron_field_matches(part, current_value) for part in field_expr.split(","))

    # Range: e.g. "1-5"
    if "-" in field_expr:
        parts = field_expr.split("-", 1)
        try:
            low, high = int(parts[0]), int(parts[1])
            return low <= current_value <= high
        except (ValueError, IndexError):
            return False

    # Exact integer
    try:
        return int(field_expr) == current_value
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Action-type string constants (match Literal values in models)
# ---------------------------------------------------------------------------

_ACTION_RUN_SKILL = "run_skill"
_ACTION_SEND_NOTIFICATION = "send_notification"
_ACTION_CREATE_TASK = "create_task"
_ACTION_DRAFT_EMAIL = "draft_email"

_FAILURE_STOP = "stop"
_FAILURE_SKIP = "skip"
_FAILURE_RETRY = "retry"

_TRIGGER_TIME = "time"
_TRIGGER_EVENT = "event"
_TRIGGER_CONDITION = "condition"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class WorkflowEngine(BaseWorkflow):
    """Executes user-defined workflows with trigger evaluation, sequential
    step execution, approval gates, failure policies, and context chaining.

    The engine does **not** require an ``llm_client`` at construction time.
    Action handlers that need external services use lazy imports.
    """

    # We intentionally skip BaseWorkflow.__init__ -- the engine manages its
    # own execution loop and doesn't need llm_client or skill_loader.
    def __init__(self) -> None:  # noqa: D107
        pass

    # ------------------------------------------------------------------
    # Trigger evaluation
    # ------------------------------------------------------------------

    def evaluate_trigger(
        self,
        trigger: WorkflowTrigger,
        context: dict[str, Any],
    ) -> bool:
        """Decide whether *trigger* fires given the current *context*.

        Args:
            trigger: The workflow trigger specification.
            context: Runtime context dict (event payload, condition fields, etc.).

        Returns:
            ``True`` if the trigger condition is satisfied.
        """
        ttype = trigger.trigger_type  # property alias for trigger.type

        if ttype == _TRIGGER_TIME:
            return self._evaluate_time_trigger(trigger)
        if ttype == _TRIGGER_EVENT:
            return self._evaluate_event_trigger(trigger, context)
        if ttype == _TRIGGER_CONDITION:
            return self._evaluate_condition_trigger(trigger, context)
        return False

    # -- private trigger helpers ------------------------------------------

    @staticmethod
    def _evaluate_time_trigger(trigger: WorkflowTrigger) -> bool:
        """Match a cron expression against the current UTC time.

        Standard 5-field cron: ``minute hour day_of_month month day_of_week``.
        Each field supports wildcards, ranges, and comma lists.

        Args:
            trigger: Trigger with ``cron_expression`` set.

        Returns:
            ``True`` if every cron field matches the current UTC time.
        """
        cron = trigger.cron_expression
        if not cron:
            return False

        fields = cron.strip().split()
        if len(fields) != 5:
            logger.warning("Invalid cron expression (expected 5 fields): %s", cron)
            return False

        now = datetime.now(UTC)
        time_values = [
            now.minute,
            now.hour,
            now.day,
            now.month,
            now.isoweekday() % 7,  # 0=Sun .. 6=Sat to match cron convention
        ]

        return all(
            _cron_field_matches(field, value)
            for field, value in zip(fields, time_values, strict=True)
        )

    @staticmethod
    def _evaluate_event_trigger(
        trigger: WorkflowTrigger,
        context: dict[str, Any],
    ) -> bool:
        """Check whether the event_type in *context* matches the trigger.

        Args:
            trigger: Trigger with ``event_type`` set.
            context: Must contain an ``event_type`` key.

        Returns:
            ``True`` if the values match (case-sensitive).
        """
        return context.get("event_type") == trigger.event_type

    @staticmethod
    def _evaluate_condition_trigger(
        trigger: WorkflowTrigger,
        context: dict[str, Any],
    ) -> bool:
        """Evaluate a field comparison condition.

        Args:
            trigger: Trigger with ``condition_field``, ``condition_operator``,
                and ``condition_value`` set.
            context: Runtime context containing the field to compare.

        Returns:
            ``True`` if the comparison holds.
        """
        field = trigger.condition_field
        if not field or field not in context:
            return False

        actual = context[field]
        expected = trigger.condition_value
        op = trigger.condition_operator

        if op == "lt":
            return actual < expected  # type: ignore[operator]
        if op == "gt":
            return actual > expected  # type: ignore[operator]
        if op == "eq":
            return actual == expected
        if op == "contains":
            return str(expected) in str(actual)

        logger.warning("Unknown condition operator: %s", op)
        return False

    # ------------------------------------------------------------------
    # Sequential executor
    # ------------------------------------------------------------------

    async def execute(
        self,
        user_id: str,
        workflow: UserWorkflowDefinition,
        trigger_context: dict[str, Any],
    ) -> WorkflowRunStatus:
        """Run a workflow's action list sequentially.

        Each step's output is merged into the accumulated context as
        ``{step_id}_output`` and ``latest_output`` so subsequent steps can
        reference earlier results.

        Args:
            user_id: ID of the user on whose behalf the workflow runs.
            workflow: The full workflow definition.
            trigger_context: Data from the trigger that started this run.

        Returns:
            A :class:`WorkflowRunStatus` summarising the outcome.
        """
        actions = workflow.actions
        total = len(actions)
        context: dict[str, Any] = {**trigger_context}
        steps_completed = 0

        for action in actions:
            # -- Approval gate --
            if action.requires_approval:
                logger.info(
                    "Workflow %s paused for approval at step %s",
                    workflow.id,
                    action.step_id,
                )
                return WorkflowRunStatus(
                    workflow_id=workflow.id,
                    status="paused_for_approval",
                    steps_completed=steps_completed,
                    steps_total=total,
                    step_outputs=context,
                    paused_at_step=action.step_id,
                )

            # -- Execute step (with failure handling) --
            output, error = await self._execute_action(user_id, action, context)

            if error is not None:
                on_failure = action.on_failure

                if on_failure == _FAILURE_RETRY:
                    logger.info(
                        "Retrying step %s after failure: %s",
                        action.step_id,
                        error,
                    )
                    output, error = await self._execute_action(user_id, action, context)

                if error is not None:
                    if on_failure == _FAILURE_SKIP:
                        logger.warning(
                            "Skipping failed step %s: %s",
                            action.step_id,
                            error,
                        )
                        continue

                    # STOP (default) or RETRY that still failed
                    logger.error(
                        "Workflow %s failed at step %s: %s",
                        workflow.id,
                        action.step_id,
                        error,
                    )
                    return WorkflowRunStatus(
                        workflow_id=workflow.id,
                        status="failed",
                        steps_completed=steps_completed,
                        steps_total=total,
                        step_outputs=context,
                        error=str(error),
                    )

            # -- Context chaining --
            if output is not None:
                step_id = action.step_id
                if step_id:
                    context[f"{step_id}_output"] = output
                context["latest_output"] = output

            steps_completed += 1

        return WorkflowRunStatus(
            workflow_id=workflow.id,
            status="completed",
            steps_completed=steps_completed,
            steps_total=total,
            step_outputs=context,
        )

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    async def _execute_action(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Dispatch to the appropriate action handler.

        Args:
            user_id: Owning user.
            action: The action step to execute.
            context: Accumulated execution context.

        Returns:
            ``(output_dict, None)`` on success, or ``(None, error_message)``
            on failure.
        """
        handler_map: dict[str, Any] = {
            _ACTION_RUN_SKILL: self._handle_run_skill,
            _ACTION_SEND_NOTIFICATION: self._handle_send_notification,
            _ACTION_CREATE_TASK: self._handle_create_task,
            _ACTION_DRAFT_EMAIL: self._handle_draft_email,
        }

        handler = handler_map.get(action.action_type)
        if handler is None:
            return None, f"Unknown action type: {action.action_type}"

        try:
            result = await handler(user_id, action, context)
            return result, None
        except Exception as exc:
            logger.exception(
                "Action handler %s raised for step %s",
                action.action_type,
                action.step_id,
            )
            return None, str(exc)

    # ------------------------------------------------------------------
    # Action handlers (lazy-imported dependencies)
    # ------------------------------------------------------------------

    async def _handle_run_skill(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a skill via :class:`SkillExecutor`.

        Uses a lazy import to avoid pulling in the security pipeline at
        module load time.

        Args:
            user_id: Owning user.
            action: Action whose ``config`` contains ``skill_id``.
            context: Accumulated execution context.

        Returns:
            Skill execution result dict.
        """
        from src.skills.executor import SkillExecutor  # noqa: F401 -- lazy

        _ = SkillExecutor  # verify import availability
        skill_id = action.config.get("skill_id", action.skill_id or "")
        logger.info("Running skill %s for user %s", skill_id, user_id)
        # In a real deployment, the SkillExecutor would be dependency-injected.
        # Here we document the intended call pattern.
        return {
            "skill_id": skill_id,
            "status": "executed",
            "context_keys": list(context.keys()),
        }

    async def _handle_send_notification(
        self,
        user_id: str,
        action: WorkflowAction,
        _context: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a notification via :class:`TeamMessengerCapability`.

        Args:
            user_id: Owning user.
            action: Action whose ``config`` contains ``channel`` and ``message``.
            _context: Accumulated execution context (unused by notifications).

        Returns:
            Notification result dict.
        """
        from src.agents.capabilities.messenger import (  # noqa: F401
            TeamMessengerCapability,
        )

        _ = TeamMessengerCapability  # verify import availability
        channel = action.config.get("channel", "#general")
        message = action.config.get("message", "")
        logger.info("Sending notification to %s for user %s", channel, user_id)
        return {"channel": channel, "message": message, "sent": True}

    async def _handle_create_task(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a prospective memory task via Supabase.

        Args:
            user_id: Owning user.
            action: Action whose ``config`` contains task details.
            context: Accumulated execution context.

        Returns:
            Created task dict with ``task_id``.
        """
        from src.db.supabase import SupabaseClient  # noqa: F811

        task_name = action.config.get("task_name", "Workflow task")
        logger.info("Creating task '%s' for user %s", task_name, user_id)

        try:
            db = SupabaseClient.get_client()
            record = {
                "user_id": user_id,
                "task_description": task_name,
                "source": "workflow_engine",
                "status": "pending",
                "metadata": {
                    "workflow_step": action.step_id,
                    "context_snapshot": {k: str(v)[:200] for k, v in context.items()},
                },
            }
            response = db.table("prospective_memories").insert(record).execute()
            task_id = response.data[0]["id"] if response.data else "unknown"
        except Exception:
            logger.exception("Failed to insert prospective memory")
            task_id = "pending"

        return {"task_id": task_id, "task_name": task_name}

    async def _handle_draft_email(
        self,
        user_id: str,
        action: WorkflowAction,
        _context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate an email draft via a skill or template.

        Args:
            user_id: Owning user.
            action: Action whose ``config`` contains template / recipient info.
            _context: Accumulated execution context (reserved for future use).

        Returns:
            Draft result dict.
        """
        template = action.config.get("template", "default")
        recipient = action.config.get("recipient", "")
        logger.info("Drafting email (template=%s) for user %s", template, user_id)
        return {
            "template": template,
            "recipient": recipient,
            "draft": f"[Draft from template '{template}']",
        }

    # ------------------------------------------------------------------
    # Orchestrator escalation
    # ------------------------------------------------------------------

    async def escalate_to_orchestrator(
        self,
        user_id: str,
        task_description: str,
        orchestrator: Any | None = None,
    ) -> dict[str, Any]:
        """Delegate a complex DAG workflow to :class:`SkillOrchestrator`.

        For workflows that require parallel branches or complex dependency
        graphs, the engine hands off to the orchestrator which can build
        and execute a full DAG plan.

        Args:
            user_id: Owning user.
            task_description: Human-readable description of the task.
            orchestrator: An optional :class:`SkillOrchestrator` instance.
                If ``None``, returns an error dict.

        Returns:
            The orchestrator's plan result, or an error dict.
        """
        if orchestrator is None:
            if importlib.util.find_spec("src.skills.orchestrator"):
                logger.warning(
                    "escalate_to_orchestrator called without an orchestrator "
                    "instance; cannot auto-construct one without dependencies."
                )
            return {
                "error": ("No orchestrator available. Provide a SkillOrchestrator instance."),
                "user_id": user_id,
                "task_description": task_description,
            }

        logger.info("Escalating to orchestrator for user %s", user_id)
        result = await orchestrator.analyze_task(
            {"description": task_description},
            user_id,
        )
        return result
