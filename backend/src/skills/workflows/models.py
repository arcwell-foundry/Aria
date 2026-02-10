"""Pydantic models for user-facing workflow definitions.

These models describe *declarative* workflow configurations — triggers,
actions, and metadata — that are stored per-user and evaluated by the
workflow engine at runtime.  They are intentionally separate from the
execution-oriented :class:`WorkflowStep` / :class:`WorkflowResult` models
in ``base.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowTrigger(BaseModel):
    """Describes *when* a workflow fires.

    Attributes:
        type: One of ``"cron"``, ``"event"``, or ``"condition"``.
        params: Trigger-specific parameters.  For cron triggers this
            includes ``schedule``; for event triggers, ``event_name``;
            for condition triggers, ``expression``.
    """

    type: str  # "cron" | "event" | "condition"
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowAction(BaseModel):
    """A single action within a workflow.

    Attributes:
        type: Action kind — ``"run_skill"``, ``"send_notification"``,
            or ``"draft_email"``.
        skill_id: Skill identifier (only for ``run_skill`` actions).
        config: Action-specific configuration.
        requires_approval: If ``True``, the workflow pauses before this
            action and waits for explicit user confirmation.
    """

    type: str  # "run_skill" | "send_notification" | "draft_email"
    skill_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class WorkflowMetadata(BaseModel):
    """Visual / organisational metadata for a workflow.

    Attributes:
        category: Grouping tag (e.g. ``"productivity"``, ``"follow_up"``).
        icon: Icon name for the UI.
        color: Hex colour string for the UI.
        description: Human-readable explanation of the workflow.
    """

    category: str
    icon: str
    color: str
    description: str = ""


class UserWorkflowDefinition(BaseModel):
    """Complete definition of a user-facing workflow.

    Attributes:
        name: Display name.
        trigger: When the workflow fires.
        actions: Ordered list of actions to execute.
        metadata: Visual / organisational metadata.
        is_shared: ``True`` for pre-built (shared) workflows; ``False``
            for user-created ones.
    """

    name: str
    trigger: WorkflowTrigger
    actions: list[WorkflowAction]
    metadata: WorkflowMetadata
    is_shared: bool = False
