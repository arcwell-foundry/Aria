"""Models for goal execution plans, tasks, and proposals."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GoalPhase(str, Enum):
    PROPOSED = "proposed"
    PLANNING = "planning"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    COMPLETING = "completing"


class GoalTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class GoalTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    agent_type: str
    status: GoalTaskStatus = GoalTaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int = 30
    result: dict[str, Any] | None = None


class ExecutionPlan(BaseModel):
    goal_id: str
    tasks: list[GoalTask]
    execution_mode: str = "parallel"
    estimated_total_minutes: int = 60
    reasoning: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GoalProposal(BaseModel):
    title: str
    description: str
    goal_type: str
    rationale: str
    priority: str  # high, medium, low
    estimated_days: int
    agent_assignments: list[str]
    config: dict[str, Any] = Field(default_factory=dict)


class ProposeGoalsResponse(BaseModel):
    proposals: list[GoalProposal]
    context_summary: str
