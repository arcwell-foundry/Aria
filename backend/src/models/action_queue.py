"""Action queue Pydantic models for ARIA (US-937).

This module contains models for the autonomous action queue and approval workflow.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionAgent(str, Enum):
    """Agent that initiated the action."""

    SCOUT = "scout"
    ANALYST = "analyst"
    HUNTER = "hunter"
    OPERATOR = "operator"
    SCRIBE = "scribe"
    STRATEGIST = "strategist"


class ActionType(str, Enum):
    """Type of autonomous action."""

    EMAIL_DRAFT = "email_draft"
    CRM_UPDATE = "crm_update"
    RESEARCH = "research"
    MEETING_PREP = "meeting_prep"
    LEAD_GEN = "lead_gen"


class RiskLevel(str, Enum):
    """Risk level determining approval workflow."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(str, Enum):
    """Execution mode determined by trust × risk matrix."""

    AUTO_EXECUTE = "auto_execute"
    EXECUTE_AND_NOTIFY = "execute_and_notify"
    APPROVE_PLAN = "approve_plan"
    APPROVE_EACH = "approve_each"


class ActionStatus(str, Enum):
    """Current status of an action."""

    PENDING = "pending"
    APPROVED = "approved"
    AUTO_APPROVED = "auto_approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    UNDO_PENDING = "undo_pending"


class ActionCreate(BaseModel):
    """Request model for submitting a new action."""

    agent: ActionAgent
    action_type: ActionType
    title: str
    description: str | None = None
    risk_level: RiskLevel
    payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: str | None = None
    risk_score: float | None = None
    task_characteristics: dict[str, Any] | None = None


class ActionReject(BaseModel):
    """Request model for rejecting an action."""

    reason: str | None = None


class BatchApproveRequest(BaseModel):
    """Request model for batch-approving actions."""

    action_ids: list[str]
