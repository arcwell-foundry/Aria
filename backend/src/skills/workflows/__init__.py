"""Workflow module for ARIA skills.

Provides the BaseWorkflow class for orchestrating multi-step
skill sequences with dependency management and approval gates,
as well as declarative workflow models and pre-built definitions.
"""

from src.skills.workflows.base import BaseWorkflow, WorkflowStep
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)
from src.skills.workflows.prebuilt import get_prebuilt_workflows

__all__ = [
    "BaseWorkflow",
    "UserWorkflowDefinition",
    "WorkflowAction",
    "WorkflowMetadata",
    "WorkflowStep",
    "WorkflowTrigger",
    "get_prebuilt_workflows",
]
