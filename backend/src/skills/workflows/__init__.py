"""Workflow module for ARIA skills.

Provides the BaseWorkflow class for orchestrating multi-step
skill sequences with dependency management and approval gates,
as well as declarative workflow models and pre-built definitions.
"""

from src.skills.workflows.base import BaseWorkflow, WorkflowStep
from src.skills.workflows.engine import WorkflowEngine
from src.skills.workflows.models import (
    ActionType,
    FailurePolicy,
    TriggerType,
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowRunStatus,
    WorkflowTrigger,
)
from src.skills.workflows.prebuilt import get_prebuilt_workflows

__all__ = [
    "ActionType",
    "BaseWorkflow",
    "FailurePolicy",
    "TriggerType",
    "UserWorkflowDefinition",
    "WorkflowAction",
    "WorkflowEngine",
    "WorkflowMetadata",
    "WorkflowRunStatus",
    "WorkflowStep",
    "WorkflowTrigger",
    "get_prebuilt_workflows",
]
