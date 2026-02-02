"""Goal-related Pydantic models for ARIA.

This module contains all models related to goals, goal agents, and agent executions.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GoalType(str, Enum):
    """Type of goal defining its primary purpose."""

    LEAD_GEN = "lead_gen"
    RESEARCH = "research"
    OUTREACH = "outreach"
    ANALYSIS = "analysis"
    CUSTOM = "custom"


class GoalStatus(str, Enum):
    """Current status of a goal."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    FAILED = "failed"


class AgentStatus(str, Enum):
    """Current status of an agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class GoalCreate(BaseModel):
    """Request model for creating a new goal."""

    title: str
    description: str | None = None
    goal_type: GoalType
    config: dict[str, Any] = Field(default_factory=dict)


class GoalUpdate(BaseModel):
    """Request model for updating an existing goal."""

    title: str | None = None
    description: str | None = None
    status: GoalStatus | None = None
    progress: int | None = None
    config: dict[str, Any] | None = None

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, v: int | None) -> int | None:
        """Validate that progress is between 0 and 100."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError("progress must be between 0 and 100")
        return v


class GoalResponse(BaseModel):
    """Response model for goal data."""

    id: str
    user_id: str
    title: str
    description: str | None
    goal_type: GoalType
    status: GoalStatus
    strategy: dict[str, Any] | None
    config: dict[str, Any]
    progress: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GoalAgentResponse(BaseModel):
    """Response model for goal agent data."""

    id: str
    goal_id: str
    agent_type: str
    agent_config: dict[str, Any]
    status: AgentStatus
    created_at: datetime


class AgentExecutionResponse(BaseModel):
    """Response model for agent execution data."""

    id: str
    goal_agent_id: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: str
    tokens_used: int
    execution_time_ms: int | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
