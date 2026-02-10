"""Tests for the workflow engine.

Covers:
- Simple 2-step workflow completes successfully (mock action handlers)
- Approval gate pauses workflow
- Step failure with on_failure=stop stops workflow
- Step failure with on_failure=skip continues
- Step failure with on_failure=retry retries then stops / succeeds
- Context chaining between steps
- Trigger evaluation for time (wildcard cron), event, condition (lt, gt, eq, contains)
- Escalation to orchestrator
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowRunStatus,
    WorkflowTrigger,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_METADATA = WorkflowMetadata(
    category="productivity",
    name="Test Workflow",
)


def _make_trigger(
    *,
    trigger_type: str = "event",
    **kwargs: Any,
) -> WorkflowTrigger:
    """Build a WorkflowTrigger with sensible defaults."""
    return WorkflowTrigger(type=trigger_type, **kwargs)


def _make_action(
    *,
    step_id: str,
    action_type: str = "run_skill",
    config: dict[str, Any] | None = None,
    requires_approval: bool = False,
    on_failure: str = "stop",
) -> WorkflowAction:
    """Build a WorkflowAction."""
    return WorkflowAction(
        step_id=step_id,
        action_type=action_type,
        config=config or {},
        requires_approval=requires_approval,
        on_failure=on_failure,
    )


def _make_workflow(
    *,
    trigger: WorkflowTrigger | None = None,
    actions: list[WorkflowAction] | None = None,
    workflow_id: str = "wf-1",
    user_id: str = "user-1",
) -> UserWorkflowDefinition:
    """Build a minimal workflow definition for testing."""
    if trigger is None:
        trigger = _make_trigger(event_type="test_event")
    if actions is None:
        actions = []
    return UserWorkflowDefinition(
        id=workflow_id,
        user_id=user_id,
        name="Test Workflow",
        trigger=trigger,
        actions=actions,
        metadata=_DEFAULT_METADATA,
    )


# ---------------------------------------------------------------------------
# Trigger evaluation tests
# ---------------------------------------------------------------------------


class TestTriggerEvaluation:
    """Tests for WorkflowEngine.evaluate_trigger."""

    async def test_event_trigger_matches(self) -> None:
        """Event trigger fires when event_type in context matches."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(trigger_type="event", event_type="deal_closed")
        context: dict[str, Any] = {"event_type": "deal_closed"}
        assert engine.evaluate_trigger(trigger, context) is True

    async def test_event_trigger_no_match(self) -> None:
        """Event trigger does not fire when event_type differs."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(trigger_type="event", event_type="deal_closed")
        context: dict[str, Any] = {"event_type": "deal_opened"}
        assert engine.evaluate_trigger(trigger, context) is False

    async def test_condition_trigger_lt(self) -> None:
        """Condition trigger fires for 'lt' when field value is below threshold."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="health_score",
            condition_operator="lt",
            condition_value=50,
        )
        context: dict[str, Any] = {"health_score": 30}
        assert engine.evaluate_trigger(trigger, context) is True

    async def test_condition_trigger_lt_no_match(self) -> None:
        """Condition trigger does not fire for 'lt' when value is above threshold."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="health_score",
            condition_operator="lt",
            condition_value=50,
        )
        context: dict[str, Any] = {"health_score": 80}
        assert engine.evaluate_trigger(trigger, context) is False

    async def test_condition_trigger_gt(self) -> None:
        """Condition trigger fires for 'gt' when field value exceeds threshold."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="deal_value",
            condition_operator="gt",
            condition_value=100000,
        )
        context: dict[str, Any] = {"deal_value": 250000}
        assert engine.evaluate_trigger(trigger, context) is True

    async def test_condition_trigger_eq(self) -> None:
        """Condition trigger fires for 'eq' when field value equals target."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="stage",
            condition_operator="eq",
            condition_value="closed_won",
        )
        context: dict[str, Any] = {"stage": "closed_won"}
        assert engine.evaluate_trigger(trigger, context) is True

    async def test_condition_trigger_contains(self) -> None:
        """Condition trigger fires for 'contains' when substring is present."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="notes",
            condition_operator="contains",
            condition_value="urgent",
        )
        context: dict[str, Any] = {"notes": "This is an urgent request"}
        assert engine.evaluate_trigger(trigger, context) is True

    async def test_condition_trigger_missing_field(self) -> None:
        """Condition trigger returns False when the field is missing from context."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="condition",
            condition_field="missing_field",
            condition_operator="gt",
            condition_value=10,
        )
        context: dict[str, Any] = {"other_field": 50}
        assert engine.evaluate_trigger(trigger, context) is False

    async def test_time_trigger_wildcard_cron(self) -> None:
        """Time trigger with all-wildcard cron always matches."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        trigger = _make_trigger(
            trigger_type="time",
            cron_expression="* * * * *",
        )
        assert engine.evaluate_trigger(trigger, {}) is True

    async def test_time_trigger_specific_minute_match(self) -> None:
        """Time trigger matches when minute field matches current UTC minute."""
        from datetime import UTC, datetime

        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        now = datetime.now(UTC)
        cron = f"{now.minute} * * * *"
        trigger = _make_trigger(trigger_type="time", cron_expression=cron)
        assert engine.evaluate_trigger(trigger, {}) is True

    async def test_time_trigger_specific_minute_no_match(self) -> None:
        """Time trigger does not match when minute field mismatches."""
        from datetime import UTC, datetime

        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        now = datetime.now(UTC)
        wrong_minute = (now.minute + 30) % 60
        cron = f"{wrong_minute} * * * *"
        trigger = _make_trigger(trigger_type="time", cron_expression=cron)
        assert engine.evaluate_trigger(trigger, {}) is False

    async def test_time_trigger_cron_range(self) -> None:
        """Time trigger matches when current minute is inside a range."""
        from datetime import UTC, datetime

        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        now = datetime.now(UTC)
        start = max(0, now.minute - 1)
        end = min(59, now.minute + 1)
        cron = f"{start}-{end} * * * *"
        trigger = _make_trigger(trigger_type="time", cron_expression=cron)
        assert engine.evaluate_trigger(trigger, {}) is True

    async def test_time_trigger_cron_list(self) -> None:
        """Time trigger matches when current minute appears in a comma list."""
        from datetime import UTC, datetime

        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        now = datetime.now(UTC)
        cron = f"{now.minute},59 * * * *"
        trigger = _make_trigger(trigger_type="time", cron_expression=cron)
        assert engine.evaluate_trigger(trigger, {}) is True


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------


class TestWorkflowExecution:
    """Tests for WorkflowEngine.execute."""

    async def test_simple_two_step_workflow_completes(self) -> None:
        """A two-step workflow runs both steps and returns 'completed'."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "research"},
            ),
            _make_action(
                step_id="step_b",
                action_type="send_notification",
                config={"channel": "#general", "message": "done"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(return_value={"result": "research_data"})
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert isinstance(result, WorkflowRunStatus)
        assert result.status == "completed"
        assert result.steps_completed == 2
        assert result.steps_total == 2
        assert result.error is None

    async def test_approval_gate_pauses_workflow(self) -> None:
        """Workflow pauses at a step with requires_approval=True."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "research"},
            ),
            _make_action(
                step_id="step_b",
                action_type="draft_email",
                config={"template": "follow_up"},
                requires_approval=True,
            ),
            _make_action(
                step_id="step_c",
                action_type="send_notification",
                config={"channel": "#alerts"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(return_value={"data": "ok"})
        engine._handle_draft_email = AsyncMock(return_value={"draft": "email body"})
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "paused_for_approval"
        assert result.paused_at_step == "step_b"
        assert result.steps_completed == 1
        engine._handle_draft_email.assert_not_called()
        engine._handle_send_notification.assert_not_called()

    async def test_failure_stop_halts_workflow(self) -> None:
        """Step failure with on_failure=stop stops the entire workflow."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "broken_skill"},
                on_failure="stop",
            ),
            _make_action(
                step_id="step_b",
                action_type="send_notification",
                config={"channel": "#alerts"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(side_effect=RuntimeError("Skill crashed"))
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "failed"
        assert "Skill crashed" in (result.error or "")
        assert result.steps_completed == 0
        engine._handle_send_notification.assert_not_called()

    async def test_failure_skip_continues_workflow(self) -> None:
        """Step failure with on_failure=skip continues to next step."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "flaky_skill"},
                on_failure="skip",
            ),
            _make_action(
                step_id="step_b",
                action_type="send_notification",
                config={"channel": "#alerts"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(side_effect=RuntimeError("Flaky"))
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "completed"
        assert result.steps_completed == 1
        engine._handle_send_notification.assert_called_once()

    async def test_failure_retry_retries_once_then_stops(self) -> None:
        """Step failure with on_failure=retry retries once then stops if still failing."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "flaky_skill"},
                on_failure="retry",
            ),
            _make_action(
                step_id="step_b",
                action_type="send_notification",
                config={"channel": "#alerts"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(side_effect=RuntimeError("Still broken"))
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "failed"
        assert engine._handle_run_skill.call_count == 2
        engine._handle_send_notification.assert_not_called()

    async def test_failure_retry_succeeds_on_retry(self) -> None:
        """Step failure with on_failure=retry succeeds if the retry works."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="run_skill",
                config={"skill_id": "flaky_skill"},
                on_failure="retry",
            ),
            _make_action(
                step_id="step_b",
                action_type="send_notification",
                config={"channel": "#alerts"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        engine._handle_run_skill = AsyncMock(
            side_effect=[RuntimeError("Transient"), {"result": "ok"}]
        )
        engine._handle_send_notification = AsyncMock(return_value={"sent": True})

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "completed"
        assert result.steps_completed == 2
        assert engine._handle_run_skill.call_count == 2

    async def test_context_chaining_between_steps(self) -> None:
        """Output from step N is in context as {step_id}_output and latest_output for step N+1."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="research",
                action_type="run_skill",
                config={"skill_id": "company_research"},
            ),
            _make_action(
                step_id="email",
                action_type="draft_email",
                config={"template": "intro"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        research_output = {"company": "Acme Corp", "revenue": "10M"}
        engine._handle_run_skill = AsyncMock(return_value=research_output)

        captured_contexts: list[dict[str, Any]] = []

        async def mock_draft_email(
            _user_id: str, _action: WorkflowAction, context: dict[str, Any]
        ) -> dict[str, Any]:
            captured_contexts.append(dict(context))
            return {"draft": "Hello Acme Corp..."}

        engine._handle_draft_email = AsyncMock(side_effect=mock_draft_email)

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "completed"
        assert len(captured_contexts) == 1
        ctx = captured_contexts[0]
        assert ctx["research_output"] == research_output
        assert ctx["latest_output"] == research_output

    async def test_empty_workflow_completes(self) -> None:
        """A workflow with no actions completes immediately."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        workflow = _make_workflow(actions=[])

        result = await engine.execute("user-1", workflow, {})

        assert result.status == "completed"
        assert result.steps_completed == 0
        assert result.steps_total == 0

    async def test_trigger_context_available_to_first_step(self) -> None:
        """The trigger_context dict is passed into the execution context."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        actions = [
            _make_action(
                step_id="step_a",
                action_type="create_task",
                config={"task_name": "Follow up"},
            ),
        ]
        workflow = _make_workflow(actions=actions)

        captured_contexts: list[dict[str, Any]] = []

        async def mock_create_task(
            _user_id: str, _action: WorkflowAction, context: dict[str, Any]
        ) -> dict[str, Any]:
            captured_contexts.append(dict(context))
            return {"task_id": "t-1"}

        engine._handle_create_task = AsyncMock(side_effect=mock_create_task)

        trigger_context: dict[str, Any] = {"deal_id": "deal-42", "event_type": "deal_closed"}
        result = await engine.execute("user-1", workflow, trigger_context)

        assert result.status == "completed"
        assert len(captured_contexts) == 1
        assert captured_contexts[0]["deal_id"] == "deal-42"

    async def test_workflow_run_status_has_correct_workflow_id(self) -> None:
        """WorkflowRunStatus carries the workflow definition's ID."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        workflow = _make_workflow(workflow_id="wf-custom-123", actions=[])

        result = await engine.execute("user-1", workflow, {})

        assert result.workflow_id == "wf-custom-123"


# ---------------------------------------------------------------------------
# Escalation to orchestrator
# ---------------------------------------------------------------------------


class TestEscalateToOrchestrator:
    """Tests for WorkflowEngine.escalate_to_orchestrator."""

    async def test_escalate_to_orchestrator_delegates(self) -> None:
        """escalate_to_orchestrator calls SkillOrchestrator if available."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.analyze_task = AsyncMock(return_value={"plan_id": "p-1"})

        result = await engine.escalate_to_orchestrator(
            user_id="user-1",
            task_description="Complex DAG workflow",
            orchestrator=mock_orchestrator,
        )

        mock_orchestrator.analyze_task.assert_called_once()
        assert result == {"plan_id": "p-1"}

    async def test_escalate_without_orchestrator_returns_error(self) -> None:
        """escalate_to_orchestrator returns error dict when no orchestrator given."""
        from src.skills.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        result = await engine.escalate_to_orchestrator(
            user_id="user-1",
            task_description="Complex DAG workflow",
            orchestrator=None,
        )

        assert "error" in result
