"""Pydantic models for user-facing workflow definitions.

These models describe *declarative* workflow configurations -- triggers,
actions, and metadata -- that are stored per-user and evaluated by the
workflow engine at runtime.  They map to/from JSONB columns
(``trigger_conditions`` and ``steps``) in the ``procedural_memories``
table.

They are intentionally separate from the execution-oriented
:class:`WorkflowStep` / :class:`WorkflowResult` models in ``base.py``.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TriggerType(str, enum.Enum):
    """Supported trigger types for workflow firing conditions."""

    TIME = "time"
    EVENT = "event"
    CONDITION = "condition"


class ActionType(str, enum.Enum):
    """Supported action types for workflow steps."""

    RUN_SKILL = "run_skill"
    SEND_NOTIFICATION = "send_notification"
    CREATE_TASK = "create_task"
    DRAFT_EMAIL = "draft_email"


class FailurePolicy(str, enum.Enum):
    """What to do when a workflow step fails."""

    SKIP = "skip"
    STOP = "stop"
    RETRY = "retry"


# ---------------------------------------------------------------------------
# WorkflowTrigger
# ---------------------------------------------------------------------------


class WorkflowTrigger(BaseModel):
    """Describes *when* a workflow fires.

    Three trigger types are supported:

    * **time** -- Fires on a cron schedule.  Requires ``cron_expression``
      and optionally ``timezone`` (defaults to ``"UTC"``).
    * **event** -- Fires when a specific event occurs.  Requires
      ``event_type`` and optionally ``event_filter`` for matching.
    * **condition** -- Fires when a data condition is met.  Requires
      ``condition_field``, ``condition_operator``, and ``condition_value``.
      Optionally ``condition_entity`` to scope the evaluation.

    Attributes:
        type: One of ``"time"``, ``"event"``, or ``"condition"``.
        cron_expression: Cron schedule string (time triggers only).
        timezone: IANA timezone for the cron schedule.
        event_type: Event name to listen for (event triggers only).
        event_filter: Optional key-value filter for event matching.
        condition_field: Data field to evaluate (condition triggers only).
        condition_operator: Comparison operator (lt/gt/eq/contains).
        condition_value: Target value for the comparison.
        condition_entity: Entity scope for the condition (e.g. ``"lead"``).
    """

    type: Literal["time", "event", "condition"] = Field(
        ...,
        description="Trigger type: time (cron), event, or condition.",
    )

    # --- Time trigger fields ---
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression for time-based triggers (e.g. '0 9 * * 1-5').",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone for the cron schedule.",
    )

    # --- Event trigger fields ---
    event_type: str | None = Field(
        default=None,
        description="Event name to listen for (e.g. 'meeting_completed').",
    )
    event_filter: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value filter applied to event payloads.",
    )

    # --- Condition trigger fields ---
    condition_field: str | None = Field(
        default=None,
        description="Data field to evaluate (e.g. 'health_score').",
    )
    condition_operator: Literal["lt", "gt", "eq", "contains"] | None = Field(
        default=None,
        description="Comparison operator: lt, gt, eq, or contains.",
    )
    condition_value: Any = Field(
        default=None,
        description="Target value for the condition comparison.",
    )
    condition_entity: str | None = Field(
        default=None,
        description="Entity scope for the condition (e.g. 'lead', 'deal').",
    )

    @property
    def trigger_type(self) -> str:
        """Alias for ``type`` used by the workflow engine."""
        return self.type


# ---------------------------------------------------------------------------
# WorkflowAction
# ---------------------------------------------------------------------------


class WorkflowAction(BaseModel):
    """A single action step within a workflow.

    Attributes:
        step_id: Unique identifier for this step within the workflow.
        action_type: Kind of action to perform.
        config: Action-specific configuration dictionary.
        requires_approval: If ``True``, the workflow pauses before this
            step and waits for explicit user confirmation.
        timeout_seconds: Maximum wall-clock time for this step.
        on_failure: Strategy when the step fails -- ``"skip"`` to continue,
            ``"stop"`` to halt the workflow, or ``"retry"`` to retry once.
    """

    step_id: str = Field(
        ...,
        description="Unique step identifier within the workflow.",
    )
    action_type: Literal["run_skill", "send_notification", "create_task", "draft_email"] = Field(
        ...,
        description="Action type: run_skill, send_notification, create_task, or draft_email.",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific configuration parameters.",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether the workflow pauses for user approval before this step.",
    )
    timeout_seconds: int = Field(
        default=60,
        description="Maximum execution time in seconds for this step.",
    )
    on_failure: Literal["skip", "stop", "retry"] = Field(
        default="stop",
        description="Failure strategy: skip, stop, or retry.",
    )


# ---------------------------------------------------------------------------
# WorkflowMetadata
# ---------------------------------------------------------------------------


class WorkflowMetadata(BaseModel):
    """Display and organisational metadata for a workflow.

    Attributes:
        category: Grouping category for the workflow.
        icon: Icon name for the UI (e.g. ``"clock"``, ``"mail"``).
        color: Hex colour string for the UI (e.g. ``"#3B82F6"``).
        enabled: Whether the workflow is currently active.
        last_run_at: Timestamp of the most recent execution.
        run_count: Total number of times this workflow has been executed.
        name: Display name (used by the engine for quick reference).
        description: Human-readable explanation of the workflow.
    """

    category: Literal["productivity", "follow_up", "monitoring"] = Field(
        ...,
        description="Workflow category: productivity, follow_up, or monitoring.",
    )
    icon: str = Field(
        default="",
        description="Icon name for the UI.",
    )
    color: str = Field(
        default="",
        description="Hex colour string for the UI.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the workflow is currently active.",
    )
    last_run_at: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent execution.",
    )
    run_count: int = Field(
        default=0,
        description="Total number of times this workflow has been executed.",
    )
    name: str = Field(
        default="",
        description="Display name for the workflow (used by the engine).",
    )
    description: str = Field(
        default="",
        description="Human-readable explanation of the workflow.",
    )


# ---------------------------------------------------------------------------
# UserWorkflowDefinition
# ---------------------------------------------------------------------------


class UserWorkflowDefinition(BaseModel):
    """Complete definition of a user-facing workflow.

    Combines a trigger condition, an ordered list of actions, and
    display metadata into a single serialisable unit.  The helper
    methods :meth:`to_trigger_conditions` and :meth:`to_steps` produce
    the JSONB-compatible dicts stored in ``procedural_memories``.

    Attributes:
        id: Unique workflow identifier (UUID string).
        user_id: Owner of this workflow definition.
        name: Display name.
        description: Human-readable description.
        trigger: When the workflow fires.
        actions: Ordered list of actions to execute.
        metadata: Visual / organisational metadata.
        is_shared: ``True`` for pre-built (shared) workflows; ``False``
            for user-created ones.
    """

    id: str = Field(
        default="",
        description="Unique workflow identifier (UUID).",
    )
    user_id: str = Field(
        default="",
        description="User who owns this workflow definition.",
    )
    name: str = Field(
        ...,
        description="Display name for the workflow.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of what this workflow does.",
    )
    trigger: WorkflowTrigger = Field(
        ...,
        description="Trigger condition that causes this workflow to fire.",
    )
    actions: list[WorkflowAction] = Field(
        ...,
        description="Ordered list of actions to execute.",
    )
    metadata: WorkflowMetadata = Field(
        ...,
        description="Display and organisational metadata.",
    )
    is_shared: bool = Field(
        default=False,
        description="True for pre-built shared workflows, False for user-created.",
    )

    def to_trigger_conditions(self) -> dict[str, Any]:
        """Serialize trigger and metadata to a JSONB-compatible dict.

        The result is suitable for storing in the ``trigger_conditions``
        JSONB column of the ``procedural_memories`` table.

        Returns:
            Dictionary containing all trigger fields and a nested
            ``metadata`` sub-dict.
        """
        trigger_data = self.trigger.model_dump(exclude_none=True)
        metadata_data = self.metadata.model_dump(exclude_none=True)
        trigger_data["metadata"] = metadata_data
        return trigger_data

    def to_steps(self) -> list[dict[str, Any]]:
        """Serialize actions to a list of JSONB-compatible dicts.

        The result is suitable for storing in the ``steps`` JSONB column
        of the ``procedural_memories`` table.

        Returns:
            List of action dictionaries, one per step.
        """
        return [action.model_dump() for action in self.actions]


# ---------------------------------------------------------------------------
# WorkflowRunStatus
# ---------------------------------------------------------------------------


class WorkflowRunStatus(BaseModel):
    """Runtime status of a single workflow execution.

    Tracks which step the workflow is on, what has completed, and
    any errors or outputs accumulated along the way.

    Attributes:
        workflow_id: Identifier of the workflow being executed.
        status: Current execution state.
        current_step: Index of the step currently being executed.
        steps_completed: Number of steps that have finished successfully.
        steps_total: Total number of steps in the workflow.
        step_outputs: Mapping of step_id to output dict.
        error: Error message if the workflow failed.
        started_at: Timestamp when execution began.
        completed_at: Timestamp when execution finished.
        paused_at_step: Step ID where execution paused for approval.
    """

    workflow_id: str = Field(
        ...,
        description="Identifier of the workflow being executed.",
    )
    status: Literal["pending", "running", "paused_for_approval", "completed", "failed"] = Field(
        ...,
        description="Current execution state.",
    )
    current_step: int = Field(
        default=0,
        description="Index of the step currently being executed.",
    )
    steps_completed: int = Field(
        default=0,
        description="Number of steps that have finished successfully.",
    )
    steps_total: int = Field(
        default=0,
        description="Total number of steps in the workflow.",
    )
    step_outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of step_id to output dict.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the workflow failed.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when execution began.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when execution finished.",
    )
    paused_at_step: str | None = Field(
        default=None,
        description="Step ID where execution paused for approval.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> float:
        """Calculate execution progress as a percentage (0.0 -- 100.0).

        Returns:
            Percentage of steps completed.  Returns 0.0 when
            ``steps_total`` is zero.
        """
        if self.steps_total == 0:
            return 0.0
        return (self.steps_completed / self.steps_total) * 100.0
