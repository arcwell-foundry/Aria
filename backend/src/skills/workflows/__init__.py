"""Workflow module for ARIA skills.

Provides the BaseWorkflow class for orchestrating multi-step
skill sequences with dependency management and approval gates,
as well as declarative workflow models, pre-built definitions,
and workflow composition classes.
"""

from src.skills.workflows.base import BaseWorkflow, WorkflowStep
from src.skills.workflows.deep_research import DeepResearchWorkflow
from src.skills.workflows.domain_intelligence import DomainIntelligenceWorkflow
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
from src.skills.workflows.newsletter_curator import NewsletterCuratorWorkflow
from src.skills.workflows.pre_meeting_pipeline import PreMeetingPipelineWorkflow
from src.skills.workflows.prebuilt import get_prebuilt_workflows
from src.skills.workflows.smart_alerts import SmartAlertsWorkflow

__all__ = [
    "ActionType",
    "BaseWorkflow",
    "DeepResearchWorkflow",
    "DomainIntelligenceWorkflow",
    "FailurePolicy",
    "NewsletterCuratorWorkflow",
    "PreMeetingPipelineWorkflow",
    "SmartAlertsWorkflow",
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
