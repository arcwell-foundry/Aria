"""Tests for workflow engine Pydantic models.

Covers WorkflowTrigger, WorkflowAction, WorkflowMetadata,
UserWorkflowDefinition, and WorkflowRunStatus models used
by the workflow engine to map to/from JSONB columns in the
procedural_memories table.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# WorkflowTrigger tests
# ---------------------------------------------------------------------------


class TestWorkflowTriggerTime:
    """Tests for time-based workflow triggers."""

    def test_valid_time_trigger(self) -> None:
        """Time trigger with cron_expression and timezone is valid."""
        from src.skills.workflows.models import WorkflowTrigger

        trigger = WorkflowTrigger(
            type="time",
            cron_expression="0 9 * * 1-5",
            timezone="America/New_York",
        )

        assert trigger.type == "time"
        assert trigger.cron_expression == "0 9 * * 1-5"
        assert trigger.timezone == "America/New_York"

    def test_time_trigger_default_timezone(self) -> None:
        """Time trigger defaults timezone to UTC."""
        from src.skills.workflows.models import WorkflowTrigger

        trigger = WorkflowTrigger(
            type="time",
            cron_expression="0 9 * * *",
        )

        assert trigger.timezone == "UTC"


class TestWorkflowTriggerEvent:
    """Tests for event-based workflow triggers."""

    def test_valid_event_trigger(self) -> None:
        """Event trigger with event_type and event_filter is valid."""
        from src.skills.workflows.models import WorkflowTrigger

        trigger = WorkflowTrigger(
            type="event",
            event_type="meeting_completed",
            event_filter={"lead_stage": "qualified"},
        )

        assert trigger.type == "event"
        assert trigger.event_type == "meeting_completed"
        assert trigger.event_filter == {"lead_stage": "qualified"}

    def test_event_trigger_default_filter(self) -> None:
        """Event trigger defaults event_filter to empty dict."""
        from src.skills.workflows.models import WorkflowTrigger

        trigger = WorkflowTrigger(
            type="event",
            event_type="deal_closed",
        )

        assert trigger.event_filter == {}


class TestWorkflowTriggerCondition:
    """Tests for condition-based workflow triggers."""

    def test_valid_condition_trigger(self) -> None:
        """Condition trigger with all fields is valid."""
        from src.skills.workflows.models import WorkflowTrigger

        trigger = WorkflowTrigger(
            type="condition",
            condition_field="health_score",
            condition_operator="lt",
            condition_value=30,
            condition_entity="lead",
        )

        assert trigger.type == "condition"
        assert trigger.condition_field == "health_score"
        assert trigger.condition_operator == "lt"
        assert trigger.condition_value == 30
        assert trigger.condition_entity == "lead"

    def test_condition_trigger_operators(self) -> None:
        """All condition operators (lt, gt, eq, contains) are valid."""
        from src.skills.workflows.models import WorkflowTrigger

        for op in ("lt", "gt", "eq", "contains"):
            trigger = WorkflowTrigger(
                type="condition",
                condition_field="score",
                condition_operator=op,
                condition_value=50,
            )
            assert trigger.condition_operator == op

    def test_condition_trigger_invalid_operator(self) -> None:
        """Invalid condition_operator raises ValidationError."""
        from src.skills.workflows.models import WorkflowTrigger

        with pytest.raises(ValidationError):
            WorkflowTrigger(
                type="condition",
                condition_field="score",
                condition_operator="not_equal",
                condition_value=50,
            )


class TestWorkflowTriggerInvalid:
    """Tests for invalid trigger configurations."""

    def test_invalid_trigger_type(self) -> None:
        """Invalid trigger type raises ValidationError."""
        from src.skills.workflows.models import WorkflowTrigger

        with pytest.raises(ValidationError):
            WorkflowTrigger(type="webhook")


# ---------------------------------------------------------------------------
# WorkflowAction tests
# ---------------------------------------------------------------------------


class TestWorkflowAction:
    """Tests for WorkflowAction model."""

    def test_valid_run_skill_action(self) -> None:
        """run_skill action with config is valid."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-1",
            action_type="run_skill",
            config={"skill_id": "company_research", "depth": "deep"},
        )

        assert action.step_id == "step-1"
        assert action.action_type == "run_skill"
        assert action.config["skill_id"] == "company_research"
        assert action.requires_approval is False
        assert action.on_failure == "stop"

    def test_valid_send_notification_action(self) -> None:
        """send_notification action is valid."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-2",
            action_type="send_notification",
            config={"channel": "slack", "message": "Deal stage changed"},
        )

        assert action.action_type == "send_notification"

    def test_valid_create_task_action(self) -> None:
        """create_task action is valid."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-3",
            action_type="create_task",
            config={"title": "Follow up with client", "due_hours": 24},
        )

        assert action.action_type == "create_task"

    def test_valid_draft_email_action(self) -> None:
        """draft_email action is valid."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-4",
            action_type="draft_email",
            config={"template": "follow_up_1", "recipient": "contact@example.com"},
        )

        assert action.action_type == "draft_email"

    def test_invalid_action_type(self) -> None:
        """Invalid action_type raises ValidationError."""
        from src.skills.workflows.models import WorkflowAction

        with pytest.raises(ValidationError):
            WorkflowAction(
                step_id="step-x",
                action_type="delete_database",
                config={},
            )

    def test_action_with_approval_gate(self) -> None:
        """Action with requires_approval=True sets the flag."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-5",
            action_type="draft_email",
            config={"template": "cold_outreach"},
            requires_approval=True,
        )

        assert action.requires_approval is True

    def test_action_with_timeout(self) -> None:
        """Action with custom timeout_seconds."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-6",
            action_type="run_skill",
            config={"skill_id": "deep_analysis"},
            timeout_seconds=120,
        )

        assert action.timeout_seconds == 120

    def test_action_on_failure_values(self) -> None:
        """on_failure accepts skip, stop, retry."""
        from src.skills.workflows.models import WorkflowAction

        for strategy in ("skip", "stop", "retry"):
            action = WorkflowAction(
                step_id="step-7",
                action_type="run_skill",
                config={},
                on_failure=strategy,
            )
            assert action.on_failure == strategy

    def test_action_invalid_on_failure(self) -> None:
        """Invalid on_failure value raises ValidationError."""
        from src.skills.workflows.models import WorkflowAction

        with pytest.raises(ValidationError):
            WorkflowAction(
                step_id="step-8",
                action_type="run_skill",
                config={},
                on_failure="explode",
            )

    def test_action_default_timeout(self) -> None:
        """Action has a sensible default timeout_seconds."""
        from src.skills.workflows.models import WorkflowAction

        action = WorkflowAction(
            step_id="step-9",
            action_type="run_skill",
            config={},
        )

        assert action.timeout_seconds == 60


# ---------------------------------------------------------------------------
# WorkflowMetadata tests
# ---------------------------------------------------------------------------


class TestWorkflowMetadata:
    """Tests for WorkflowMetadata model."""

    def test_valid_metadata(self) -> None:
        """Metadata with all fields is valid."""
        from src.skills.workflows.models import WorkflowMetadata

        now = datetime.now(UTC)
        metadata = WorkflowMetadata(
            category="productivity",
            icon="clock",
            color="#3B82F6",
            enabled=True,
            last_run_at=now,
            run_count=42,
        )

        assert metadata.category == "productivity"
        assert metadata.icon == "clock"
        assert metadata.color == "#3B82F6"
        assert metadata.enabled is True
        assert metadata.last_run_at == now
        assert metadata.run_count == 42

    def test_metadata_categories(self) -> None:
        """All valid categories are accepted."""
        from src.skills.workflows.models import WorkflowMetadata

        for cat in ("productivity", "follow_up", "monitoring"):
            metadata = WorkflowMetadata(category=cat)
            assert metadata.category == cat

    def test_metadata_invalid_category(self) -> None:
        """Invalid category raises ValidationError."""
        from src.skills.workflows.models import WorkflowMetadata

        with pytest.raises(ValidationError):
            WorkflowMetadata(category="invalid_category")

    def test_metadata_defaults(self) -> None:
        """Metadata has sensible defaults."""
        from src.skills.workflows.models import WorkflowMetadata

        metadata = WorkflowMetadata(category="productivity")

        assert metadata.enabled is True
        assert metadata.run_count == 0
        assert metadata.last_run_at is None
        assert metadata.icon == ""
        assert metadata.color == ""


# ---------------------------------------------------------------------------
# UserWorkflowDefinition tests
# ---------------------------------------------------------------------------


class TestUserWorkflowDefinition:
    """Tests for UserWorkflowDefinition model."""

    def _build_definition(self) -> Any:
        """Build a complete UserWorkflowDefinition for reuse."""
        from src.skills.workflows.models import (
            UserWorkflowDefinition,
            WorkflowAction,
            WorkflowMetadata,
            WorkflowTrigger,
        )

        trigger = WorkflowTrigger(
            type="event",
            event_type="meeting_completed",
            event_filter={"lead_stage": "qualified"},
        )

        actions = [
            WorkflowAction(
                step_id="step-1",
                action_type="run_skill",
                config={"skill_id": "company_research", "depth": "deep"},
            ),
            WorkflowAction(
                step_id="step-2",
                action_type="draft_email",
                config={"template": "follow_up"},
                requires_approval=True,
            ),
            WorkflowAction(
                step_id="step-3",
                action_type="create_task",
                config={"title": "Schedule follow-up call", "due_hours": 48},
            ),
        ]

        metadata = WorkflowMetadata(
            category="follow_up",
            icon="mail",
            color="#10B981",
            enabled=True,
            run_count=5,
        )

        return UserWorkflowDefinition(
            name="Post-Meeting Follow-Up",
            description="Automatically research and follow up after qualified meetings",
            trigger=trigger,
            actions=actions,
            metadata=metadata,
            is_shared=False,
        )

    def test_full_definition_creation(self) -> None:
        """Full UserWorkflowDefinition with trigger, actions, metadata is valid."""
        definition = self._build_definition()

        assert definition.name == "Post-Meeting Follow-Up"
        assert len(definition.actions) == 3
        assert definition.trigger.type == "event"
        assert definition.metadata.category == "follow_up"
        assert definition.is_shared is False

    def test_to_trigger_conditions(self) -> None:
        """to_trigger_conditions() serializes trigger and metadata to JSONB dict."""
        definition = self._build_definition()

        result = definition.to_trigger_conditions()

        assert isinstance(result, dict)
        # Should contain trigger data
        assert result["type"] == "event"
        assert result["event_type"] == "meeting_completed"
        assert result["event_filter"] == {"lead_stage": "qualified"}
        # Should contain metadata
        assert result["metadata"]["category"] == "follow_up"
        assert result["metadata"]["icon"] == "mail"
        assert result["metadata"]["enabled"] is True

    def test_to_steps(self) -> None:
        """to_steps() serializes actions to list of dicts."""
        definition = self._build_definition()

        result = definition.to_steps()

        assert isinstance(result, list)
        assert len(result) == 3

        # First step
        assert result[0]["step_id"] == "step-1"
        assert result[0]["action_type"] == "run_skill"
        assert result[0]["config"]["skill_id"] == "company_research"
        assert result[0]["requires_approval"] is False

        # Second step (with approval)
        assert result[1]["step_id"] == "step-2"
        assert result[1]["action_type"] == "draft_email"
        assert result[1]["requires_approval"] is True

        # Third step
        assert result[2]["step_id"] == "step-3"
        assert result[2]["action_type"] == "create_task"

    def test_is_shared_default_false(self) -> None:
        """is_shared defaults to False."""
        from src.skills.workflows.models import (
            UserWorkflowDefinition,
            WorkflowAction,
            WorkflowMetadata,
            WorkflowTrigger,
        )

        definition = UserWorkflowDefinition(
            name="Test",
            description="Test workflow",
            trigger=WorkflowTrigger(type="event", event_type="test"),
            actions=[
                WorkflowAction(
                    step_id="s1",
                    action_type="create_task",
                    config={"title": "Do thing"},
                )
            ],
            metadata=WorkflowMetadata(category="productivity"),
        )

        assert definition.is_shared is False


# ---------------------------------------------------------------------------
# WorkflowRunStatus tests
# ---------------------------------------------------------------------------


class TestWorkflowRunStatus:
    """Tests for WorkflowRunStatus model."""

    def test_valid_pending_status(self) -> None:
        """Pending run status is valid."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-123",
            status="pending",
            current_step=0,
            steps_completed=0,
            steps_total=3,
        )

        assert status.workflow_id == "wf-123"
        assert status.status == "pending"
        assert status.current_step == 0
        assert status.steps_completed == 0
        assert status.steps_total == 3

    def test_valid_running_status(self) -> None:
        """Running status with partial progress."""
        from src.skills.workflows.models import WorkflowRunStatus

        now = datetime.now(UTC)
        status = WorkflowRunStatus(
            workflow_id="wf-456",
            status="running",
            current_step=2,
            steps_completed=1,
            steps_total=4,
            step_outputs={"step-1": {"result": "success"}},
            started_at=now,
        )

        assert status.status == "running"
        assert status.current_step == 2
        assert status.step_outputs == {"step-1": {"result": "success"}}

    def test_valid_completed_status(self) -> None:
        """Completed status with all steps done."""
        from src.skills.workflows.models import WorkflowRunStatus

        now = datetime.now(UTC)
        status = WorkflowRunStatus(
            workflow_id="wf-789",
            status="completed",
            current_step=3,
            steps_completed=3,
            steps_total=3,
            started_at=now,
            completed_at=now,
        )

        assert status.status == "completed"
        assert status.completed_at is not None

    def test_valid_failed_status(self) -> None:
        """Failed status with error message."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-err",
            status="failed",
            current_step=2,
            steps_completed=1,
            steps_total=3,
            error="Skill execution timed out",
        )

        assert status.status == "failed"
        assert status.error == "Skill execution timed out"

    def test_valid_paused_for_approval_status(self) -> None:
        """Paused-for-approval status is valid."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-pause",
            status="paused_for_approval",
            current_step=2,
            steps_completed=1,
            steps_total=4,
        )

        assert status.status == "paused_for_approval"

    def test_invalid_status_value(self) -> None:
        """Invalid status value raises ValidationError."""
        from src.skills.workflows.models import WorkflowRunStatus

        with pytest.raises(ValidationError):
            WorkflowRunStatus(
                workflow_id="wf-bad",
                status="exploding",
                current_step=0,
                steps_completed=0,
                steps_total=1,
            )

    def test_progress_calculation(self) -> None:
        """progress property calculates percentage correctly."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-prog",
            status="running",
            current_step=2,
            steps_completed=2,
            steps_total=4,
        )

        assert status.progress == 50.0

    def test_progress_zero_steps(self) -> None:
        """progress returns 0.0 when steps_total is 0."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-zero",
            status="pending",
            current_step=0,
            steps_completed=0,
            steps_total=0,
        )

        assert status.progress == 0.0

    def test_progress_completed(self) -> None:
        """progress returns 100.0 when all steps completed."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-done",
            status="completed",
            current_step=5,
            steps_completed=5,
            steps_total=5,
        )

        assert status.progress == 100.0

    def test_default_step_outputs(self) -> None:
        """step_outputs defaults to empty dict."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-def",
            status="pending",
            current_step=0,
            steps_completed=0,
            steps_total=2,
        )

        assert status.step_outputs == {}

    def test_default_timestamps_are_none(self) -> None:
        """started_at and completed_at default to None."""
        from src.skills.workflows.models import WorkflowRunStatus

        status = WorkflowRunStatus(
            workflow_id="wf-ts",
            status="pending",
            current_step=0,
            steps_completed=0,
            steps_total=1,
        )

        assert status.started_at is None
        assert status.completed_at is None
        assert status.error is None
