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


class ActionStatus(str, Enum):
    """Current status of an action."""

    PENDING = "pending"
    APPROVED = "approved"
    AUTO_APPROVED = "auto_approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ActionCreate(BaseModel):
    """Request model for submitting a new action."""

    agent: ActionAgent
    action_type: ActionType
    title: str
    description: str | None = None
    risk_level: RiskLevel
    payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: str | None = None


class ActionReject(BaseModel):
    """Request model for rejecting an action."""

    reason: str | None = None


class BatchApproveRequest(BaseModel):
    """Request model for batch-approving actions."""

    action_ids: list[str]
