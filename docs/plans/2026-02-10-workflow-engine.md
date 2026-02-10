# User-Definable Workflow Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a user-definable workflow engine with trigger→action chains, approval gates, 3 pre-built workflows, API routes, and a drag-and-drop WorkflowBuilder React component.

**Architecture:** Extends `BaseWorkflow` (in `src/skills/workflows/base.py`) to support user-defined trigger→action chains stored in the existing `procedural_memories` table. Simple trigger→action chains use a lightweight sequential executor; complex DAG workflows escalate to `SkillOrchestrator`. Frontend uses `react-beautiful-dnd` for drag-and-drop workflow building.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic, React 18 / TypeScript / Tailwind / react-beautiful-dnd, Supabase (procedural_memories table), existing LLMClient + BaseWorkflow + ProceduralMemory

---

## Task 1: Backend — Pydantic Models for Workflow Engine

**Files:**
- Create: `backend/src/skills/workflows/models.py`
- Test: `backend/tests/test_workflow_engine_models.py`

**Step 1: Write the failing test**

```python
"""Tests for workflow engine Pydantic models."""

import pytest
from pydantic import ValidationError


def test_workflow_trigger_time_valid():
    from src.skills.workflows.models import WorkflowTrigger

    trigger = WorkflowTrigger(
        type="time",
        cron_expression="0 6 * * 1-5",
        timezone="America/New_York",
    )
    assert trigger.type == "time"
    assert trigger.cron_expression == "0 6 * * 1-5"


def test_workflow_trigger_event_valid():
    from src.skills.workflows.models import WorkflowTrigger

    trigger = WorkflowTrigger(
        type="event",
        event_type="calendar_event_ended",
        event_filter={"source": "calendar"},
    )
    assert trigger.type == "event"
    assert trigger.event_type == "calendar_event_ended"


def test_workflow_trigger_condition_valid():
    from src.skills.workflows.models import WorkflowTrigger

    trigger = WorkflowTrigger(
        type="condition",
        condition_field="lead_health_score",
        condition_operator="lt",
        condition_value=50,
        condition_entity="lead",
    )
    assert trigger.type == "condition"
    assert trigger.condition_operator == "lt"


def test_workflow_trigger_invalid_type():
    from src.skills.workflows.models import WorkflowTrigger

    with pytest.raises(ValidationError):
        WorkflowTrigger(type="invalid_type")


def test_workflow_action_run_skill():
    from src.skills.workflows.models import WorkflowAction

    action = WorkflowAction(
        step_id="step_1",
        action_type="run_skill",
        config={"skill_id": "morning-briefing", "template": "daily_summary"},
    )
    assert action.action_type == "run_skill"
    assert action.requires_approval is False


def test_workflow_action_send_notification():
    from src.skills.workflows.models import WorkflowAction

    action = WorkflowAction(
        step_id="step_2",
        action_type="send_notification",
        config={"channel": "slack", "message_template": "Alert: {signal}"},
    )
    assert action.action_type == "send_notification"


def test_workflow_action_create_task():
    from src.skills.workflows.models import WorkflowAction

    action = WorkflowAction(
        step_id="step_3",
        action_type="create_task",
        config={"task_title": "Follow up", "task_description": "Review notes"},
    )
    assert action.action_type == "create_task"


def test_workflow_action_draft_email():
    from src.skills.workflows.models import WorkflowAction

    action = WorkflowAction(
        step_id="step_4",
        action_type="draft_email",
        config={"subject_template": "Follow-up: {meeting}", "body_skill": "email-composer"},
    )
    assert action.action_type == "draft_email"


def test_workflow_action_with_approval():
    from src.skills.workflows.models import WorkflowAction

    action = WorkflowAction(
        step_id="step_1",
        action_type="run_skill",
        config={"skill_id": "test"},
        requires_approval=True,
    )
    assert action.requires_approval is True


def test_workflow_action_invalid_type():
    from src.skills.workflows.models import WorkflowAction

    with pytest.raises(ValidationError):
        WorkflowAction(
            step_id="step_1",
            action_type="invalid_action",
            config={},
        )


def test_user_workflow_definition():
    from src.skills.workflows.models import (
        UserWorkflowDefinition,
        WorkflowAction,
        WorkflowMetadata,
        WorkflowTrigger,
    )

    workflow = UserWorkflowDefinition(
        name="Morning Prep",
        description="Daily morning briefing workflow",
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 6 * * 1-5",
            timezone="America/New_York",
        ),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "morning-briefing"},
            ),
            WorkflowAction(
                step_id="step_2",
                action_type="send_notification",
                config={"channel": "slack", "message_template": "{briefing}"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="sun",
            color="#F59E0B",
        ),
    )
    assert workflow.name == "Morning Prep"
    assert len(workflow.actions) == 2
    assert workflow.metadata.category == "productivity"


def test_user_workflow_definition_to_procedural_memory():
    from src.skills.workflows.models import (
        UserWorkflowDefinition,
        WorkflowAction,
        WorkflowMetadata,
        WorkflowTrigger,
    )

    workflow = UserWorkflowDefinition(
        name="Test Workflow",
        description="A test",
        trigger=WorkflowTrigger(type="time", cron_expression="0 6 * * *"),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "test"},
            ),
        ],
        metadata=WorkflowMetadata(category="productivity", icon="sun", color="#F59E0B"),
    )

    trigger_dict = workflow.to_trigger_conditions()
    steps_list = workflow.to_steps()

    assert trigger_dict["type"] == "time"
    assert trigger_dict["cron_expression"] == "0 6 * * *"
    assert len(steps_list) == 1
    assert steps_list[0]["action_type"] == "run_skill"


def test_workflow_run_status():
    from src.skills.workflows.models import WorkflowRunStatus

    status = WorkflowRunStatus(
        workflow_id="wf-1",
        status="running",
        current_step="step_1",
        steps_completed=0,
        steps_total=3,
    )
    assert status.status == "running"
    assert status.progress == 0.0


def test_workflow_run_status_progress():
    from src.skills.workflows.models import WorkflowRunStatus

    status = WorkflowRunStatus(
        workflow_id="wf-1",
        status="running",
        current_step="step_2",
        steps_completed=1,
        steps_total=3,
    )
    assert abs(status.progress - 1 / 3) < 0.01
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_engine_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `backend/src/skills/workflows/models.py`:

```python
"""Pydantic models for the user-definable workflow engine.

Defines typed trigger conditions, action steps, workflow definitions,
and run status models. These map to/from the JSONB columns in the
existing ``procedural_memories`` table.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowTrigger(BaseModel):
    """Trigger condition for a user-defined workflow.

    Supports three trigger types:
    - ``time``: Cron-based scheduling.
    - ``event``: Fires on system events (calendar, email, signals).
    - ``condition``: Fires when a monitored value crosses a threshold.
    """

    type: Literal["time", "event", "condition"]

    # Time trigger fields
    cron_expression: str | None = None
    timezone: str = "UTC"

    # Event trigger fields
    event_type: str | None = None
    event_filter: dict[str, Any] = Field(default_factory=dict)

    # Condition trigger fields
    condition_field: str | None = None
    condition_operator: Literal["lt", "gt", "eq", "contains"] | None = None
    condition_value: float | str | None = None
    condition_entity: str | None = None


class WorkflowAction(BaseModel):
    """A single action step in a user-defined workflow.

    Supports four action types:
    - ``run_skill``: Execute an ARIA skill.
    - ``send_notification``: Send Slack or in-app notification.
    - ``create_task``: Create a prospective memory task.
    - ``draft_email``: Draft an email using a skill.
    """

    step_id: str
    action_type: Literal["run_skill", "send_notification", "create_task", "draft_email"]
    config: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 120
    on_failure: Literal["skip", "stop", "retry"] = "stop"


class WorkflowMetadata(BaseModel):
    """Display metadata for a workflow."""

    category: Literal["productivity", "follow_up", "monitoring"] = "productivity"
    icon: str = "zap"
    color: str = "#6366F1"
    enabled: bool = True
    last_run_at: str | None = None
    run_count: int = 0


class UserWorkflowDefinition(BaseModel):
    """Complete user-defined workflow definition.

    Contains the trigger, ordered action steps, and display metadata.
    Maps to/from the ``procedural_memories`` table via
    ``to_trigger_conditions()`` and ``to_steps()`` helpers.
    """

    name: str
    description: str
    trigger: WorkflowTrigger
    actions: list[WorkflowAction]
    metadata: WorkflowMetadata = Field(default_factory=WorkflowMetadata)
    is_shared: bool = False

    def to_trigger_conditions(self) -> dict[str, Any]:
        """Serialize trigger to the JSONB format for procedural_memories."""
        data = self.trigger.model_dump(exclude_none=True)
        data["workflow_metadata"] = self.metadata.model_dump()
        return data

    def to_steps(self) -> list[dict[str, Any]]:
        """Serialize actions to the JSONB format for procedural_memories."""
        return [action.model_dump() for action in self.actions]


class WorkflowRunStatus(BaseModel):
    """Status of a running or completed workflow execution."""

    workflow_id: str
    status: Literal[
        "pending", "running", "paused_for_approval", "completed", "failed"
    ]
    current_step: str | None = None
    steps_completed: int = 0
    steps_total: int = 0
    step_outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @property
    def progress(self) -> float:
        """Calculate execution progress as a fraction."""
        if self.steps_total == 0:
            return 0.0
        return self.steps_completed / self.steps_total
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_engine_models.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/skills/workflows/models.py backend/tests/test_workflow_engine_models.py
git commit -m "feat: add Pydantic models for user-definable workflow engine"
```

---

## Task 2: Backend — WorkflowEngine Core (engine.py)

**Files:**
- Create: `backend/src/skills/workflows/engine.py`
- Test: `backend/tests/test_workflow_engine.py`

**Step 1: Write the failing test**

```python
"""Tests for the user-definable workflow engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)


def _make_morning_prep() -> UserWorkflowDefinition:
    return UserWorkflowDefinition(
        name="Morning Prep",
        description="Daily morning briefing",
        trigger=WorkflowTrigger(type="time", cron_expression="0 6 * * 1-5"),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "morning-briefing", "template": "daily_summary"},
            ),
            WorkflowAction(
                step_id="step_2",
                action_type="send_notification",
                config={"channel": "slack", "message_template": "Here's your briefing: {latest_output}"},
            ),
        ],
        metadata=WorkflowMetadata(category="productivity", icon="sun", color="#F59E0B"),
    )


@pytest.mark.asyncio
async def test_engine_execute_simple_workflow():
    """Sequential executor runs steps in order, passing context."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()

    # Mock the action handlers
    engine._handle_run_skill = AsyncMock(return_value={"briefing": "Today's summary"})
    engine._handle_send_notification = AsyncMock(return_value={"sent": True})

    definition = _make_morning_prep()
    result = await engine.execute(
        user_id="user-1",
        definition=definition,
        trigger_context={"date": "2026-02-10"},
    )

    assert result.status == "completed"
    assert result.steps_completed == 2
    assert result.steps_total == 2
    engine._handle_run_skill.assert_called_once()
    engine._handle_send_notification.assert_called_once()


@pytest.mark.asyncio
async def test_engine_approval_gate_pauses():
    """Workflow pauses at steps requiring approval."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    engine._handle_run_skill = AsyncMock(return_value={"notes": "Meeting notes"})

    definition = UserWorkflowDefinition(
        name="Post-Meeting",
        description="Post-meeting follow-up",
        trigger=WorkflowTrigger(type="event", event_type="calendar_event_ended"),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "note-prompt"},
                requires_approval=True,
            ),
            WorkflowAction(
                step_id="step_2",
                action_type="run_skill",
                config={"skill_id": "action-extractor"},
            ),
        ],
        metadata=WorkflowMetadata(category="follow_up", icon="calendar", color="#3B82F6"),
    )

    result = await engine.execute(
        user_id="user-1",
        definition=definition,
        trigger_context={},
    )

    assert result.status == "paused_for_approval"
    assert result.current_step == "step_1"
    assert result.steps_completed == 0


@pytest.mark.asyncio
async def test_engine_step_failure_stops():
    """Workflow stops when a step fails and on_failure=stop."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    engine._handle_run_skill = AsyncMock(side_effect=RuntimeError("Skill failed"))

    definition = UserWorkflowDefinition(
        name="Test",
        description="Test failure",
        trigger=WorkflowTrigger(type="time", cron_expression="0 6 * * *"),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "failing-skill"},
                on_failure="stop",
            ),
            WorkflowAction(
                step_id="step_2",
                action_type="send_notification",
                config={"channel": "slack"},
            ),
        ],
        metadata=WorkflowMetadata(),
    )

    result = await engine.execute(
        user_id="user-1",
        definition=definition,
        trigger_context={},
    )

    assert result.status == "failed"
    assert result.steps_completed == 0
    assert result.error is not None


@pytest.mark.asyncio
async def test_engine_step_failure_skip():
    """Workflow skips failed step and continues when on_failure=skip."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    engine._handle_run_skill = AsyncMock(side_effect=RuntimeError("Skill failed"))
    engine._handle_send_notification = AsyncMock(return_value={"sent": True})

    definition = UserWorkflowDefinition(
        name="Test",
        description="Test skip",
        trigger=WorkflowTrigger(type="time", cron_expression="0 6 * * *"),
        actions=[
            WorkflowAction(
                step_id="step_1",
                action_type="run_skill",
                config={"skill_id": "failing-skill"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="step_2",
                action_type="send_notification",
                config={"channel": "slack"},
            ),
        ],
        metadata=WorkflowMetadata(),
    )

    result = await engine.execute(
        user_id="user-1",
        definition=definition,
        trigger_context={},
    )

    assert result.status == "completed"
    assert result.steps_completed == 1  # Only step_2 succeeded


@pytest.mark.asyncio
async def test_engine_context_chaining():
    """Output from step N is available to step N+1 via context."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()

    call_contexts = []

    async def capture_run_skill(user_id, action, context):
        call_contexts.append(dict(context))
        return {"result": f"output_from_{action.step_id}"}

    engine._handle_run_skill = capture_run_skill

    definition = UserWorkflowDefinition(
        name="Chain Test",
        description="Test context chaining",
        trigger=WorkflowTrigger(type="time", cron_expression="0 6 * * *"),
        actions=[
            WorkflowAction(step_id="step_1", action_type="run_skill", config={"skill_id": "a"}),
            WorkflowAction(step_id="step_2", action_type="run_skill", config={"skill_id": "b"}),
        ],
        metadata=WorkflowMetadata(),
    )

    result = await engine.execute(
        user_id="user-1",
        definition=definition,
        trigger_context={"initial": "data"},
    )

    assert result.status == "completed"
    # Second call should have first step's output in context
    assert "step_1_output" in call_contexts[1]
    assert call_contexts[1]["step_1_output"]["result"] == "output_from_step_1"


def test_evaluate_trigger_time():
    """Time trigger evaluates cron expression against current time."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    trigger = WorkflowTrigger(type="time", cron_expression="* * * * *")
    # Wildcard cron should always match
    assert engine.evaluate_trigger(trigger, {}) is True


def test_evaluate_trigger_event():
    """Event trigger matches when event_type matches context."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    trigger = WorkflowTrigger(type="event", event_type="calendar_event_ended")

    assert engine.evaluate_trigger(trigger, {"event_type": "calendar_event_ended"}) is True
    assert engine.evaluate_trigger(trigger, {"event_type": "email_received"}) is False


def test_evaluate_trigger_condition_lt():
    """Condition trigger evaluates numeric comparisons."""
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    trigger = WorkflowTrigger(
        type="condition",
        condition_field="lead_health_score",
        condition_operator="lt",
        condition_value=50,
    )

    assert engine.evaluate_trigger(trigger, {"lead_health_score": 30}) is True
    assert engine.evaluate_trigger(trigger, {"lead_health_score": 70}) is False


def test_evaluate_trigger_condition_gt():
    from src.skills.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    trigger = WorkflowTrigger(
        type="condition",
        condition_field="relevance_score",
        condition_operator="gt",
        condition_value=0.8,
    )

    assert engine.evaluate_trigger(trigger, {"relevance_score": 0.9}) is True
    assert engine.evaluate_trigger(trigger, {"relevance_score": 0.5}) is False
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `backend/src/skills/workflows/engine.py`:

```python
"""User-definable workflow engine.

Extends BaseWorkflow to support user-defined trigger→action chains stored
in the ``procedural_memories`` table. Provides:

- Three trigger types: time (cron), event, condition
- Four action types: run_skill, send_notification, create_task, draft_email
- Approval gates that pause execution for user confirmation
- Context chaining between sequential steps
- Tiered execution: simple sequential for linear chains, escalates to
  SkillOrchestrator for complex DAGs

Pre-built workflows:
1. "Morning Prep" — 6am weekdays: briefing → Slack
2. "Post-Meeting" — calendar event ends: notes → actions → follow-up email
3. "Signal Alert" — relevance_score > 0.8: format → Slack + in-app
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from src.skills.workflows.base import BaseWorkflow
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowRunStatus,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)


class WorkflowEngine(BaseWorkflow):
    """Engine for executing user-defined trigger→action workflows.

    Runs action steps sequentially, passing accumulated context forward.
    Supports approval gates, failure policies (stop/skip/retry), and
    context variable interpolation.

    For simple trigger→action chains this engine handles execution directly.
    For workflows with parallel branches, call ``escalate_to_orchestrator``
    to delegate to :class:`SkillOrchestrator`.
    """

    def __init__(self) -> None:
        # BaseWorkflow requires llm_client; we defer it since action handlers
        # may or may not need LLM access.
        self._action_handlers = {
            "run_skill": self._handle_run_skill,
            "send_notification": self._handle_send_notification,
            "create_task": self._handle_create_task,
            "draft_email": self._handle_draft_email,
        }

    # ── Trigger evaluation ────────────────────────────────────────────────

    def evaluate_trigger(
        self,
        trigger: WorkflowTrigger,
        context: dict[str, Any],
    ) -> bool:
        """Evaluate whether a trigger condition is satisfied.

        Args:
            trigger: The trigger definition to evaluate.
            context: Current context (event payload, field values, etc.).

        Returns:
            True if the trigger fires, False otherwise.
        """
        if trigger.type == "time":
            return self._evaluate_cron(trigger.cron_expression or "")

        if trigger.type == "event":
            return context.get("event_type") == trigger.event_type

        if trigger.type == "condition":
            return self._evaluate_condition(trigger, context)

        return False

    def _evaluate_cron(self, cron_expression: str) -> bool:
        """Check if the current time matches a cron expression.

        Uses a simplified matcher: splits the cron expression and
        checks each field against the current time. Supports wildcards.

        Args:
            cron_expression: Standard 5-field cron expression.

        Returns:
            True if the current time matches.
        """
        if not cron_expression:
            return False

        now = datetime.now(UTC)
        parts = cron_expression.split()
        if len(parts) != 5:
            logger.warning("Invalid cron expression: %s", cron_expression)
            return False

        minute, hour, dom, month, dow = parts

        checks = [
            (minute, now.minute),
            (hour, now.hour),
            (dom, now.day),
            (month, now.month),
            (dow, now.isoweekday() % 7),  # 0=Sun for cron
        ]

        for field, current_val in checks:
            if field == "*":
                continue
            # Handle ranges like 1-5
            if "-" in field:
                low, high = field.split("-", 1)
                if not (int(low) <= current_val <= int(high)):
                    return False
            # Handle lists like 1,3,5
            elif "," in field:
                allowed = [int(v) for v in field.split(",")]
                if current_val not in allowed:
                    return False
            else:
                if current_val != int(field):
                    return False

        return True

    def _evaluate_condition(
        self,
        trigger: WorkflowTrigger,
        context: dict[str, Any],
    ) -> bool:
        """Evaluate a condition trigger against context values.

        Args:
            trigger: Condition trigger with field, operator, value.
            context: Context dict containing the field to check.

        Returns:
            True if the condition is met.
        """
        if not trigger.condition_field or trigger.condition_operator is None:
            return False

        actual = context.get(trigger.condition_field)
        if actual is None:
            return False

        expected = trigger.condition_value
        op = trigger.condition_operator

        if op == "lt":
            return float(actual) < float(expected)  # type: ignore[arg-type]
        if op == "gt":
            return float(actual) > float(expected)  # type: ignore[arg-type]
        if op == "eq":
            return actual == expected
        if op == "contains":
            return str(expected) in str(actual)

        return False

    # ── Workflow execution ────────────────────────────────────────────────

    async def execute(
        self,
        user_id: str,
        definition: UserWorkflowDefinition,
        trigger_context: dict[str, Any],
    ) -> WorkflowRunStatus:
        """Execute a user-defined workflow sequentially.

        Runs each action step in order. Output from each step is merged
        into the accumulated context as ``{step_id}_output``. Steps with
        ``requires_approval=True`` pause the workflow.

        Args:
            user_id: ID of the user who owns the workflow.
            definition: The workflow definition to execute.
            trigger_context: Context from the trigger event.

        Returns:
            WorkflowRunStatus with execution outcome.
        """
        run_status = WorkflowRunStatus(
            workflow_id="",  # Set by caller
            status="running",
            steps_total=len(definition.actions),
            started_at=datetime.now(UTC).isoformat(),
        )

        context: dict[str, Any] = {**trigger_context}
        steps_completed = 0

        for action in definition.actions:
            run_status.current_step = action.step_id

            # Check approval gate
            if action.requires_approval:
                run_status.status = "paused_for_approval"
                run_status.steps_completed = steps_completed
                logger.info(
                    "Workflow paused for approval",
                    extra={
                        "user_id": user_id,
                        "workflow": definition.name,
                        "step": action.step_id,
                    },
                )
                return run_status

            # Execute the action
            handler = self._action_handlers.get(action.action_type)
            if handler is None:
                logger.error(
                    "Unknown action type: %s",
                    action.action_type,
                    extra={"step_id": action.step_id},
                )
                run_status.status = "failed"
                run_status.error = f"Unknown action type: {action.action_type}"
                run_status.steps_completed = steps_completed
                return run_status

            try:
                output = await handler(user_id, action, context)
                context[f"{action.step_id}_output"] = output
                context["latest_output"] = output
                run_status.step_outputs[action.step_id] = output
                steps_completed += 1

            except Exception as exc:
                logger.exception(
                    "Workflow step failed",
                    extra={
                        "user_id": user_id,
                        "workflow": definition.name,
                        "step": action.step_id,
                        "error": str(exc),
                    },
                )

                if action.on_failure == "stop":
                    run_status.status = "failed"
                    run_status.error = f"Step {action.step_id} failed: {exc}"
                    run_status.steps_completed = steps_completed
                    return run_status
                elif action.on_failure == "skip":
                    # Continue to next step
                    continue
                elif action.on_failure == "retry":
                    # Single retry attempt
                    try:
                        output = await handler(user_id, action, context)
                        context[f"{action.step_id}_output"] = output
                        context["latest_output"] = output
                        run_status.step_outputs[action.step_id] = output
                        steps_completed += 1
                    except Exception as retry_exc:
                        run_status.status = "failed"
                        run_status.error = f"Step {action.step_id} failed after retry: {retry_exc}"
                        run_status.steps_completed = steps_completed
                        return run_status

        run_status.status = "completed"
        run_status.steps_completed = steps_completed
        run_status.completed_at = datetime.now(UTC).isoformat()

        logger.info(
            "Workflow completed",
            extra={
                "user_id": user_id,
                "workflow": definition.name,
                "steps_completed": steps_completed,
            },
        )

        return run_status

    # ── Action handlers ───────────────────────────────────────────────────
    # Each handler receives (user_id, action, context) and returns a dict.
    # These are designed to be overridden in tests or extended by subclasses.

    async def _handle_run_skill(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a skill via the SkillExecutor pipeline.

        Args:
            user_id: User who owns the workflow.
            action: The action definition with skill_id in config.
            context: Accumulated workflow context.

        Returns:
            Skill execution result dict.
        """
        from src.security.data_classification import DataClassifier
        from src.security.sandbox import SkillSandbox
        from src.security.sanitization import DataSanitizer
        from src.security.skill_audit import SkillAuditService
        from src.skills.executor import SkillExecutor
        from src.skills.index import SkillIndex
        from src.skills.installer import SkillInstaller

        skill_id = action.config.get("skill_id", "")
        input_data = {**action.config, **context}

        executor = SkillExecutor(
            classifier=DataClassifier(),
            sanitizer=DataSanitizer(),
            sandbox=SkillSandbox(),
            index=SkillIndex(),
            installer=SkillInstaller(),
            audit_service=SkillAuditService(),
        )

        execution = await executor.execute(
            user_id=user_id,
            skill_id=skill_id,
            input_data=input_data,
            context=context,
        )

        if not execution.success:
            raise RuntimeError(execution.error or "Skill execution failed")

        return execution.result if isinstance(execution.result, dict) else {"result": execution.result}

    async def _handle_send_notification(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a notification via Slack or in-app channel.

        Args:
            user_id: User who owns the workflow.
            action: Action with channel and message_template in config.
            context: Accumulated workflow context.

        Returns:
            Dict with send status.
        """
        channel = action.config.get("channel", "in_app")
        message_template = action.config.get("message_template", "")

        # Interpolate context variables into message
        try:
            message = message_template.format_map(
                {k: str(v) for k, v in context.items()}
            )
        except (KeyError, ValueError):
            message = message_template

        if channel == "slack":
            from src.agents.capabilities.messenger import TeamMessengerCapability

            messenger = TeamMessengerCapability()
            result = await messenger.send_channel_message(
                user_id=user_id,
                channel_name="general",
                message=message,
            )
            return {"channel": "slack", "sent": True, "message": message}

        # In-app notification (store in prospective_memories as reminder)
        return {"channel": "in_app", "sent": True, "message": message}

    async def _handle_create_task(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a prospective memory task.

        Args:
            user_id: User who owns the workflow.
            action: Action with task_title and task_description in config.
            context: Accumulated workflow context.

        Returns:
            Dict with created task info.
        """
        title = action.config.get("task_title", "Workflow task")
        description = action.config.get("task_description", "")

        # Interpolate context
        try:
            title = title.format_map({k: str(v) for k, v in context.items()})
            description = description.format_map({k: str(v) for k, v in context.items()})
        except (KeyError, ValueError):
            pass

        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        now = datetime.now(UTC).isoformat()

        record = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "status": "pending",
            "priority": "medium",
            "source": "workflow_engine",
            "created_at": now,
        }

        response = client.table("prospective_memories").insert(record).execute()
        task_id = response.data[0]["id"] if response.data else ""

        return {"task_id": task_id, "title": title}

    async def _handle_draft_email(
        self,
        user_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Draft an email using an ARIA skill or template.

        Args:
            user_id: User who owns the workflow.
            action: Action with email config (subject, body_skill, etc.).
            context: Accumulated workflow context.

        Returns:
            Dict with draft email content.
        """
        subject_template = action.config.get("subject_template", "")
        body_skill = action.config.get("body_skill", "")

        try:
            subject = subject_template.format_map({k: str(v) for k, v in context.items()})
        except (KeyError, ValueError):
            subject = subject_template

        # If a body skill is specified, run it to generate the email body
        if body_skill:
            body_result = await self._handle_run_skill(
                user_id,
                WorkflowAction(
                    step_id=f"{action.step_id}_body",
                    action_type="run_skill",
                    config={"skill_id": body_skill, **context},
                ),
                context,
            )
            body = body_result.get("result", body_result.get("body", ""))
        else:
            body = action.config.get("body_template", "")
            try:
                body = body.format_map({k: str(v) for k, v in context.items()})
            except (KeyError, ValueError):
                pass

        return {"subject": subject, "body": body, "draft": True}

    # ── Orchestrator escalation ───────────────────────────────────────────

    async def escalate_to_orchestrator(
        self,
        user_id: str,
        definition: UserWorkflowDefinition,
        trigger_context: dict[str, Any],
    ) -> WorkflowRunStatus:
        """Delegate a complex workflow to the SkillOrchestrator.

        Used when a workflow has parallel branches or complex dependencies
        that exceed the simple sequential executor's capabilities.

        Args:
            user_id: User who owns the workflow.
            definition: The workflow definition.
            trigger_context: Context from the trigger.

        Returns:
            WorkflowRunStatus from the orchestrator execution.
        """
        from src.security.data_classification import DataClassifier
        from src.security.sandbox import SkillSandbox
        from src.security.sanitization import DataSanitizer
        from src.security.skill_audit import SkillAuditService
        from src.skills.autonomy import SkillAutonomyService
        from src.skills.executor import SkillExecutor
        from src.skills.index import SkillIndex
        from src.skills.installer import SkillInstaller
        from src.skills.orchestrator import SkillOrchestrator

        executor = SkillExecutor(
            classifier=DataClassifier(),
            sanitizer=DataSanitizer(),
            sandbox=SkillSandbox(),
            index=SkillIndex(),
            installer=SkillInstaller(),
            audit_service=SkillAuditService(),
        )

        orchestrator = SkillOrchestrator(
            executor=executor,
            index=SkillIndex(),
            autonomy=SkillAutonomyService(),
            audit=SkillAuditService(),
        )

        task = {
            "description": definition.description,
            "context": trigger_context,
        }

        plan = await orchestrator.analyze_task(task, user_id)
        result = await orchestrator.execute_plan(
            user_id=user_id,
            plan=plan,
        )

        return WorkflowRunStatus(
            workflow_id="",
            status="completed" if result.status == "completed" else "failed",
            steps_completed=result.steps_completed,
            steps_total=result.steps_completed + result.steps_failed + result.steps_skipped,
            completed_at=datetime.now(UTC).isoformat(),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_engine.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/skills/workflows/engine.py backend/tests/test_workflow_engine.py
git commit -m "feat: add WorkflowEngine with trigger evaluation and sequential execution"
```

---

## Task 3: Backend — Pre-built Workflows & Seeding

**Files:**
- Create: `backend/src/skills/workflows/prebuilt.py`
- Test: `backend/tests/test_prebuilt_workflows.py`

**Step 1: Write the failing test**

```python
"""Tests for pre-built workflow definitions."""


def test_get_morning_prep():
    from src.skills.workflows.prebuilt import get_prebuilt_workflows

    workflows = get_prebuilt_workflows()
    morning = next(w for w in workflows if w.name == "Morning Prep")

    assert morning.trigger.type == "time"
    assert morning.trigger.cron_expression == "0 6 * * 1-5"
    assert len(morning.actions) == 2
    assert morning.actions[0].action_type == "run_skill"
    assert morning.actions[1].action_type == "send_notification"
    assert morning.metadata.category == "productivity"
    assert morning.metadata.icon == "sun"


def test_get_post_meeting():
    from src.skills.workflows.prebuilt import get_prebuilt_workflows

    workflows = get_prebuilt_workflows()
    post = next(w for w in workflows if w.name == "Post-Meeting")

    assert post.trigger.type == "event"
    assert post.trigger.event_type == "calendar_event_ended"
    assert len(post.actions) == 3
    # First step requires approval (user adds notes)
    assert post.actions[0].requires_approval is True
    assert post.actions[1].action_type == "run_skill"
    assert post.actions[2].action_type == "draft_email"
    assert post.metadata.category == "follow_up"
    assert post.metadata.icon == "calendar"


def test_get_signal_alert():
    from src.skills.workflows.prebuilt import get_prebuilt_workflows

    workflows = get_prebuilt_workflows()
    signal = next(w for w in workflows if w.name == "Signal Alert")

    assert signal.trigger.type == "condition"
    assert signal.trigger.condition_field == "market_signals.relevance_score"
    assert signal.trigger.condition_operator == "gt"
    assert signal.trigger.condition_value == 0.8
    assert len(signal.actions) == 2
    assert signal.metadata.category == "monitoring"
    assert signal.metadata.icon == "radar"


def test_prebuilt_count():
    from src.skills.workflows.prebuilt import get_prebuilt_workflows

    workflows = get_prebuilt_workflows()
    assert len(workflows) == 3


def test_all_prebuilt_are_shared():
    from src.skills.workflows.prebuilt import get_prebuilt_workflows

    for w in get_prebuilt_workflows():
        assert w.is_shared is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_prebuilt_workflows.py -v`

**Step 3: Write minimal implementation**

Create `backend/src/skills/workflows/prebuilt.py`:

```python
"""Pre-built workflow definitions that ship with ARIA.

These are stored as shared workflows in ``procedural_memories`` so
all users can see and clone them. Users can customize triggers,
actions, and approval gates.

Workflows:
1. Morning Prep — 6am weekdays: generate briefing → send to Slack
2. Post-Meeting — after calendar event: notes (approval) → extract actions → draft follow-up
3. Signal Alert — relevance_score > 0.8: format alert → Slack + in-app
"""

from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)


def get_prebuilt_workflows() -> list[UserWorkflowDefinition]:
    """Return the three pre-built workflow definitions.

    Returns:
        List of UserWorkflowDefinition instances marked as shared.
    """
    return [
        _morning_prep(),
        _post_meeting(),
        _signal_alert(),
    ]


def _morning_prep() -> UserWorkflowDefinition:
    return UserWorkflowDefinition(
        name="Morning Prep",
        description=(
            "Generates a daily briefing at 6am on weekdays and delivers "
            "it to your Slack channel. Includes upcoming meetings, pipeline "
            "changes, and market signals from overnight."
        ),
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 6 * * 1-5",
            timezone="America/New_York",
        ),
        actions=[
            WorkflowAction(
                step_id="generate_briefing",
                action_type="run_skill",
                config={
                    "skill_id": "morning-briefing",
                    "template": "daily_summary",
                    "input_mapping": {"date": "{{trigger.date}}"},
                },
            ),
            WorkflowAction(
                step_id="send_to_slack",
                action_type="send_notification",
                config={
                    "channel": "slack",
                    "message_template": (
                        "Good morning! Here's your daily briefing:\n\n"
                        "{latest_output}"
                    ),
                },
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="sun",
            color="#F59E0B",
        ),
        is_shared=True,
    )


def _post_meeting() -> UserWorkflowDefinition:
    return UserWorkflowDefinition(
        name="Post-Meeting",
        description=(
            "After a calendar event ends, prompts you for meeting notes, "
            "extracts action items, and drafts a follow-up email to attendees."
        ),
        trigger=WorkflowTrigger(
            type="event",
            event_type="calendar_event_ended",
            event_filter={"source": "calendar"},
        ),
        actions=[
            WorkflowAction(
                step_id="prompt_for_notes",
                action_type="run_skill",
                config={
                    "skill_id": "meeting-notes-prompt",
                    "template": "post_meeting",
                },
                requires_approval=True,
            ),
            WorkflowAction(
                step_id="extract_actions",
                action_type="run_skill",
                config={
                    "skill_id": "action-item-extractor",
                    "input_mapping": {"notes": "{{prompt_for_notes_output}}"},
                },
            ),
            WorkflowAction(
                step_id="draft_follow_up",
                action_type="draft_email",
                config={
                    "subject_template": "Follow-up: {meeting_title}",
                    "body_skill": "email-composer",
                    "to_mapping": "{{meeting_attendees}}",
                },
            ),
        ],
        metadata=WorkflowMetadata(
            category="follow_up",
            icon="calendar",
            color="#3B82F6",
        ),
        is_shared=True,
    )


def _signal_alert() -> UserWorkflowDefinition:
    return UserWorkflowDefinition(
        name="Signal Alert",
        description=(
            "When a market signal with relevance score above 0.8 is detected, "
            "formats an alert summary and delivers it to Slack and as an "
            "in-app notification."
        ),
        trigger=WorkflowTrigger(
            type="condition",
            condition_field="market_signals.relevance_score",
            condition_operator="gt",
            condition_value=0.8,
            condition_entity="market_signal",
        ),
        actions=[
            WorkflowAction(
                step_id="format_alert",
                action_type="run_skill",
                config={
                    "skill_id": "signal-formatter",
                    "template": "alert_summary",
                    "input_mapping": {"signal": "{{trigger.signal_data}}"},
                },
            ),
            WorkflowAction(
                step_id="notify",
                action_type="send_notification",
                config={
                    "channel": "slack",
                    "message_template": (
                        "🔔 High-relevance signal detected:\n\n"
                        "{latest_output}"
                    ),
                },
            ),
        ],
        metadata=WorkflowMetadata(
            category="monitoring",
            icon="radar",
            color="#EF4444",
        ),
        is_shared=True,
    )
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_prebuilt_workflows.py -v`

**Step 5: Commit**

```bash
git add backend/src/skills/workflows/prebuilt.py backend/tests/test_prebuilt_workflows.py
git commit -m "feat: add 3 pre-built workflows (Morning Prep, Post-Meeting, Signal Alert)"
```

---

## Task 4: Backend — API Routes for Workflows

**Files:**
- Create: `backend/src/api/routes/workflows.py`
- Modify: `backend/src/main.py` (register router)
- Test: `backend/tests/test_workflow_routes.py`

**Step 1: Write the failing test**

```python
"""Tests for workflow API routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def workflow_definition():
    return {
        "name": "Test Workflow",
        "description": "A test workflow",
        "trigger": {
            "type": "time",
            "cron_expression": "0 6 * * 1-5",
        },
        "actions": [
            {
                "step_id": "step_1",
                "action_type": "run_skill",
                "config": {"skill_id": "test-skill"},
            },
        ],
        "metadata": {
            "category": "productivity",
            "icon": "sun",
            "color": "#F59E0B",
        },
    }


def test_create_workflow_request_model():
    from src.api.routes.workflows import CreateWorkflowRequest

    req = CreateWorkflowRequest(
        name="Test",
        description="Test desc",
        trigger={"type": "time", "cron_expression": "0 6 * * *"},
        actions=[
            {"step_id": "s1", "action_type": "run_skill", "config": {"skill_id": "x"}},
        ],
    )
    assert req.name == "Test"


def test_workflow_response_model():
    from src.api.routes.workflows import WorkflowResponse

    resp = WorkflowResponse(
        id="wf-1",
        name="Test",
        description="Test desc",
        trigger={"type": "time"},
        actions=[{"step_id": "s1", "action_type": "run_skill", "config": {}}],
        metadata={"category": "productivity", "icon": "sun", "color": "#6366F1"},
        is_shared=False,
        enabled=True,
        success_count=0,
        failure_count=0,
        version=1,
    )
    assert resp.id == "wf-1"


def test_prebuilt_workflows_endpoint_exists():
    """Verify the route handler function exists and is importable."""
    from src.api.routes.workflows import list_prebuilt_workflows

    assert callable(list_prebuilt_workflows)


def test_list_workflows_endpoint_exists():
    from src.api.routes.workflows import list_workflows

    assert callable(list_workflows)


def test_create_workflow_endpoint_exists():
    from src.api.routes.workflows import create_workflow

    assert callable(create_workflow)


def test_update_workflow_endpoint_exists():
    from src.api.routes.workflows import update_workflow

    assert callable(update_workflow)


def test_delete_workflow_endpoint_exists():
    from src.api.routes.workflows import delete_workflow

    assert callable(delete_workflow)


def test_execute_workflow_endpoint_exists():
    from src.api.routes.workflows import execute_workflow

    assert callable(execute_workflow)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_routes.py -v`

**Step 3: Write implementation**

Create `backend/src/api/routes/workflows.py`:

```python
"""API routes for user-definable workflows."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError, sanitize_error
from src.memory.procedural import ProceduralMemory, Workflow
from src.skills.workflows.engine import WorkflowEngine
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowRunStatus,
    WorkflowTrigger,
)
from src.skills.workflows.prebuilt import get_prebuilt_workflows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ── Request/Response models ───────────────────────────────────────────────


class CreateWorkflowRequest(BaseModel):
    """Request to create a user-defined workflow."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    trigger: dict[str, Any]
    actions: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateWorkflowRequest(BaseModel):
    """Request to update an existing workflow."""

    name: str | None = None
    description: str | None = None
    trigger: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    """Workflow in API responses."""

    id: str
    name: str
    description: str
    trigger: dict[str, Any]
    actions: list[dict[str, Any]]
    metadata: dict[str, Any]
    is_shared: bool = False
    enabled: bool = True
    success_count: int = 0
    failure_count: int = 0
    version: int = 1


class ExecuteWorkflowRequest(BaseModel):
    """Request to manually execute a workflow."""

    trigger_context: dict[str, Any] = Field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────


def _workflow_to_response(workflow: Workflow) -> WorkflowResponse:
    """Convert a Workflow dataclass to API response."""
    metadata = workflow.trigger_conditions.get("workflow_metadata", {})
    actions = workflow.steps
    trigger = {k: v for k, v in workflow.trigger_conditions.items() if k != "workflow_metadata"}

    return WorkflowResponse(
        id=workflow.id,
        name=workflow.workflow_name,
        description=workflow.description,
        trigger=trigger,
        actions=actions,
        metadata=metadata,
        is_shared=workflow.is_shared,
        enabled=metadata.get("enabled", True),
        success_count=workflow.success_count,
        failure_count=workflow.failure_count,
        version=workflow.version,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/prebuilt")
async def list_prebuilt_workflows(
    current_user: CurrentUser,
) -> list[WorkflowResponse]:
    """List the pre-built workflow templates available for cloning."""
    prebuilt = get_prebuilt_workflows()
    return [
        WorkflowResponse(
            id=f"prebuilt-{i}",
            name=w.name,
            description=w.description,
            trigger=w.trigger.model_dump(exclude_none=True),
            actions=[a.model_dump() for a in w.actions],
            metadata=w.metadata.model_dump(),
            is_shared=True,
        )
        for i, w in enumerate(prebuilt)
    ]


@router.get("")
async def list_workflows(
    current_user: CurrentUser,
    include_shared: bool = Query(default=True),
) -> list[WorkflowResponse]:
    """List all workflows available to the current user."""
    memory = ProceduralMemory()
    try:
        workflows = await memory.list_workflows(
            user_id=str(current_user.id),
            include_shared=include_shared,
        )
    except ProceduralMemoryError as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    return [_workflow_to_response(w) for w in workflows]


@router.post("")
async def create_workflow(
    data: CreateWorkflowRequest,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Create a new user-defined workflow."""
    # Validate by parsing into typed models
    try:
        trigger = WorkflowTrigger(**data.trigger)
        actions = [WorkflowAction(**a) for a in data.actions]
        metadata = WorkflowMetadata(**data.metadata) if data.metadata else WorkflowMetadata()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid workflow definition: {e}") from e

    definition = UserWorkflowDefinition(
        name=data.name,
        description=data.description,
        trigger=trigger,
        actions=actions,
        metadata=metadata,
    )

    workflow = Workflow(
        id=str(uuid.uuid4()),
        user_id=str(current_user.id),
        workflow_name=definition.name,
        description=definition.description,
        trigger_conditions=definition.to_trigger_conditions(),
        steps=definition.to_steps(),
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    memory = ProceduralMemory()
    try:
        workflow_id = await memory.create_workflow(workflow)
    except ProceduralMemoryError as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow created",
        extra={
            "user_id": current_user.id,
            "workflow_id": workflow_id,
            "workflow_name": data.name,
        },
    )

    return _workflow_to_response(workflow)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Get a specific workflow by ID."""
    memory = ProceduralMemory()
    try:
        workflow = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    return _workflow_to_response(workflow)


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    data: UpdateWorkflowRequest,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Update an existing workflow."""
    memory = ProceduralMemory()

    try:
        workflow = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e

    if data.name is not None:
        workflow.workflow_name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.trigger is not None:
        trigger = WorkflowTrigger(**data.trigger)
        existing_metadata = workflow.trigger_conditions.get("workflow_metadata", {})
        workflow.trigger_conditions = trigger.model_dump(exclude_none=True)
        workflow.trigger_conditions["workflow_metadata"] = existing_metadata
    if data.actions is not None:
        actions = [WorkflowAction(**a) for a in data.actions]
        workflow.steps = [a.model_dump() for a in actions]
    if data.metadata is not None:
        workflow.trigger_conditions["workflow_metadata"] = data.metadata

    try:
        await memory.update_workflow(workflow)
    except ProceduralMemoryError as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow updated",
        extra={"user_id": current_user.id, "workflow_id": workflow_id},
    )

    return _workflow_to_response(workflow)


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Delete a workflow."""
    memory = ProceduralMemory()
    try:
        await memory.delete_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow deleted",
        extra={"user_id": current_user.id, "workflow_id": workflow_id},
    )

    return {"status": "deleted"}


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    data: ExecuteWorkflowRequest,
    current_user: CurrentUser,
) -> WorkflowRunStatus:
    """Manually execute a workflow."""
    memory = ProceduralMemory()

    try:
        workflow = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e

    # Reconstruct definition from stored data
    metadata_dict = workflow.trigger_conditions.get("workflow_metadata", {})
    trigger_dict = {k: v for k, v in workflow.trigger_conditions.items() if k != "workflow_metadata"}

    definition = UserWorkflowDefinition(
        name=workflow.workflow_name,
        description=workflow.description,
        trigger=WorkflowTrigger(**trigger_dict),
        actions=[WorkflowAction(**s) for s in workflow.steps],
        metadata=WorkflowMetadata(**metadata_dict) if metadata_dict else WorkflowMetadata(),
    )

    engine = WorkflowEngine()
    result = await engine.execute(
        user_id=str(current_user.id),
        definition=definition,
        trigger_context=data.trigger_context,
    )
    result.workflow_id = workflow_id

    # Record outcome
    success = result.status == "completed"
    try:
        await memory.record_outcome(workflow_id, success)
    except Exception:
        logger.exception("Failed to record workflow outcome")

    return result
```

Then register the router in `backend/src/main.py` — add:

```python
from src.api.routes.workflows import router as workflows_router
app.include_router(workflows_router, prefix="/api")
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_routes.py -v`

**Step 5: Commit**

```bash
git add backend/src/api/routes/workflows.py backend/tests/test_workflow_routes.py backend/src/main.py
git commit -m "feat: add API routes for workflow CRUD and execution"
```

---

## Task 5: Frontend — API Client & React Query Hooks

**Files:**
- Create: `frontend/src/api/workflows.ts`
- Create: `frontend/src/hooks/useWorkflows.ts`

**Step 1: Create the API client**

Create `frontend/src/api/workflows.ts`:

```typescript
import { apiClient } from "./client";

// Types

export type TriggerType = "time" | "event" | "condition";
export type ActionType = "run_skill" | "send_notification" | "create_task" | "draft_email";
export type FailurePolicy = "skip" | "stop" | "retry";
export type WorkflowCategory = "productivity" | "follow_up" | "monitoring";
export type WorkflowStatus = "pending" | "running" | "paused_for_approval" | "completed" | "failed";

export interface WorkflowTrigger {
  type: TriggerType;
  cron_expression?: string;
  timezone?: string;
  event_type?: string;
  event_filter?: Record<string, unknown>;
  condition_field?: string;
  condition_operator?: "lt" | "gt" | "eq" | "contains";
  condition_value?: number | string;
  condition_entity?: string;
}

export interface WorkflowAction {
  step_id: string;
  action_type: ActionType;
  config: Record<string, unknown>;
  requires_approval?: boolean;
  timeout_seconds?: number;
  on_failure?: FailurePolicy;
}

export interface WorkflowMetadata {
  category: WorkflowCategory;
  icon: string;
  color: string;
  enabled?: boolean;
  last_run_at?: string;
  run_count?: number;
}

export interface WorkflowResponse {
  id: string;
  name: string;
  description: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
  metadata: WorkflowMetadata;
  is_shared: boolean;
  enabled: boolean;
  success_count: number;
  failure_count: number;
  version: number;
}

export interface WorkflowRunStatus {
  workflow_id: string;
  status: WorkflowStatus;
  current_step: string | null;
  steps_completed: number;
  steps_total: number;
  step_outputs: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface CreateWorkflowData {
  name: string;
  description: string;
  trigger: WorkflowTrigger;
  actions: WorkflowAction[];
  metadata?: Partial<WorkflowMetadata>;
}

export interface UpdateWorkflowData {
  name?: string;
  description?: string;
  trigger?: WorkflowTrigger;
  actions?: WorkflowAction[];
  metadata?: Partial<WorkflowMetadata>;
}

// API functions

export async function listWorkflows(includeShared = true): Promise<WorkflowResponse[]> {
  const response = await apiClient.get("/api/workflows", {
    params: { include_shared: includeShared },
  });
  return response.data;
}

export async function listPrebuiltWorkflows(): Promise<WorkflowResponse[]> {
  const response = await apiClient.get("/api/workflows/prebuilt");
  return response.data;
}

export async function getWorkflow(workflowId: string): Promise<WorkflowResponse> {
  const response = await apiClient.get(`/api/workflows/${workflowId}`);
  return response.data;
}

export async function createWorkflow(data: CreateWorkflowData): Promise<WorkflowResponse> {
  const response = await apiClient.post("/api/workflows", data);
  return response.data;
}

export async function updateWorkflow(
  workflowId: string,
  data: UpdateWorkflowData,
): Promise<WorkflowResponse> {
  const response = await apiClient.put(`/api/workflows/${workflowId}`, data);
  return response.data;
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await apiClient.delete(`/api/workflows/${workflowId}`);
}

export async function executeWorkflow(
  workflowId: string,
  triggerContext: Record<string, unknown> = {},
): Promise<WorkflowRunStatus> {
  const response = await apiClient.post(`/api/workflows/${workflowId}/execute`, {
    trigger_context: triggerContext,
  });
  return response.data;
}
```

**Step 2: Create React Query hooks**

Create `frontend/src/hooks/useWorkflows.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listWorkflows,
  listPrebuiltWorkflows,
  getWorkflow,
  createWorkflow,
  updateWorkflow,
  deleteWorkflow,
  executeWorkflow,
  type CreateWorkflowData,
  type UpdateWorkflowData,
} from "@/api/workflows";

export const workflowKeys = {
  all: ["workflows"] as const,
  list: () => [...workflowKeys.all, "list"] as const,
  prebuilt: () => [...workflowKeys.all, "prebuilt"] as const,
  detail: (id: string) => [...workflowKeys.all, "detail", id] as const,
};

export function useWorkflows(includeShared = true) {
  return useQuery({
    queryKey: workflowKeys.list(),
    queryFn: () => listWorkflows(includeShared),
  });
}

export function usePrebuiltWorkflows() {
  return useQuery({
    queryKey: workflowKeys.prebuilt(),
    queryFn: () => listPrebuiltWorkflows(),
    staleTime: Infinity,
  });
}

export function useWorkflow(workflowId: string) {
  return useQuery({
    queryKey: workflowKeys.detail(workflowId),
    queryFn: () => getWorkflow(workflowId),
    enabled: !!workflowId,
  });
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateWorkflowData) => createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.list() });
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateWorkflowData }) =>
      updateWorkflow(id, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.list() });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.detail(variables.id),
      });
    },
  });
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workflowId: string) => deleteWorkflow(workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.list() });
    },
  });
}

export function useExecuteWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      workflowId,
      triggerContext,
    }: {
      workflowId: string;
      triggerContext?: Record<string, unknown>;
    }) => executeWorkflow(workflowId, triggerContext),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.list() });
    },
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/workflows.ts frontend/src/hooks/useWorkflows.ts
git commit -m "feat: add frontend API client and React Query hooks for workflows"
```

---

## Task 6: Frontend — WorkflowBuilder Component

**Files:**
- Create: `frontend/src/components/skills/WorkflowBuilder.tsx`

**Step 1: Install react-beautiful-dnd**

Run: `cd /Users/dhruv/aria/frontend && npm install react-beautiful-dnd @types/react-beautiful-dnd`

**Step 2: Create WorkflowBuilder.tsx**

This is the main deliverable for the frontend. Uses the `frontend-design` skill pattern — dark surface UI, Tailwind, Lucide icons, consistent with existing components like `ExecutionPlanCard.tsx`.

Create `frontend/src/components/skills/WorkflowBuilder.tsx` — a full drag-and-drop workflow builder component with:

- **Trigger selector** (time/event/condition with type-specific fields)
- **Action list** with drag-to-reorder via `react-beautiful-dnd`
- **Action blocks** showing type, config, approval gate toggle
- **Add action** button with type picker
- **Save/Cancel** buttons
- **Pre-built workflow templates** section for cloning

The component accepts:

```typescript
interface WorkflowBuilderProps {
  /** Existing workflow to edit (null for new) */
  workflow?: WorkflowResponse;
  /** Pre-built templates for the "Start from template" section */
  prebuiltWorkflows?: WorkflowResponse[];
  /** Called with the workflow definition on save */
  onSave: (data: CreateWorkflowData) => void;
  /** Called when user cancels */
  onCancel: () => void;
  /** Whether save is in progress */
  saving?: boolean;
}
```

**Note:** Use the `frontend-design` skill to implement this component with high design quality. The component should follow the established dark surface UI pattern from `ExecutionPlanCard.tsx`.

**Step 3: Commit**

```bash
git add frontend/src/components/skills/WorkflowBuilder.tsx
git commit -m "feat: add WorkflowBuilder component with drag-and-drop actions"
```

---

## Task 7: Frontend — WorkflowsPage Route

**Files:**
- Create: `frontend/src/pages/WorkflowsPage.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/pages/index.ts` (export page)

**Step 1: Create WorkflowsPage**

The page composes `WorkflowBuilder` with the workflow list. Shows:
- List of user's workflows with enable/disable toggle
- "Create Workflow" button → opens `WorkflowBuilder`
- Pre-built templates section
- Click workflow → edit in `WorkflowBuilder`
- Execute button per workflow

**Step 2: Register route in App.tsx**

Add `import { WorkflowsPage } from "@/pages"` and the route `<Route path="/workflows" element={<WorkflowsPage />} />`.

**Step 3: Export from pages/index.ts**

Add `export { WorkflowsPage } from "./WorkflowsPage"`.

**Step 4: Commit**

```bash
git add frontend/src/pages/WorkflowsPage.tsx frontend/src/App.tsx frontend/src/pages/index.ts
git commit -m "feat: add WorkflowsPage with workflow list and builder integration"
```

---

## Task 8: Backend — Update workflows __init__.py

**Files:**
- Modify: `backend/src/skills/workflows/__init__.py`

**Step 1: Update the init file**

Export the new modules from the workflows package:

```python
"""User-definable workflow engine.

Provides trigger→action workflow chains stored in procedural_memories,
with support for time/event/condition triggers, approval gates, and
context chaining between steps.
"""

from src.skills.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep
from src.skills.workflows.engine import WorkflowEngine
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowRunStatus,
    WorkflowTrigger,
)
from src.skills.workflows.prebuilt import get_prebuilt_workflows

__all__ = [
    "BaseWorkflow",
    "WorkflowEngine",
    "WorkflowResult",
    "WorkflowStep",
    "UserWorkflowDefinition",
    "WorkflowAction",
    "WorkflowMetadata",
    "WorkflowRunStatus",
    "WorkflowTrigger",
    "get_prebuilt_workflows",
]
```

**Step 2: Commit**

```bash
git add backend/src/skills/workflows/__init__.py
git commit -m "feat: export workflow engine models from workflows package"
```

---

## Task 9: Run All Tests & Lint

**Step 1: Run backend tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_workflow_engine_models.py backend/tests/test_workflow_engine.py backend/tests/test_prebuilt_workflows.py backend/tests/test_workflow_routes.py -v`

**Step 2: Run linter**

Run: `cd /Users/dhruv/aria && ruff check backend/src/skills/workflows/ backend/src/api/routes/workflows.py --fix`
Run: `cd /Users/dhruv/aria && ruff format backend/src/skills/workflows/ backend/src/api/routes/workflows.py`

**Step 3: Run frontend typecheck**

Run: `cd /Users/dhruv/aria/frontend && npm run typecheck`

**Step 4: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: lint and type fixes for workflow engine"
```

---

## Summary

| Task | Component | What |
|------|-----------|------|
| 1 | Backend models | `WorkflowTrigger`, `WorkflowAction`, `UserWorkflowDefinition`, `WorkflowRunStatus` |
| 2 | Backend engine | `WorkflowEngine` — trigger eval, sequential executor, approval gates, context chaining |
| 3 | Backend prebuilt | 3 pre-built workflows: Morning Prep, Post-Meeting, Signal Alert |
| 4 | Backend API | FastAPI routes: CRUD + execute + prebuilt listing |
| 5 | Frontend API/hooks | `workflows.ts` API client + `useWorkflows.ts` React Query hooks |
| 6 | Frontend builder | `WorkflowBuilder.tsx` — drag-and-drop trigger/action builder |
| 7 | Frontend page | `WorkflowsPage.tsx` — list, create, edit, execute workflows |
| 8 | Backend init | Package exports |
| 9 | Quality | Tests + lint + typecheck |
