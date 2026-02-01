"""Prospective memory module for storing future tasks and reminders.

Prospective memory stores tasks for future execution with:
- Time-based triggers (due dates/times)
- Event-based triggers (external events)
- Condition-based triggers (state changes)
- Status tracking (pending, completed, cancelled, overdue)
- Priority levels for task ordering
- Links to related goals and leads

Tasks are stored in Supabase for structured querying and
integration with the rest of the application state.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of triggers for prospective tasks."""

    TIME = "time"  # Due at specific time
    EVENT = "event"  # Triggered by external event
    CONDITION = "condition"  # Triggered by state change


class TaskStatus(Enum):
    """Status values for prospective tasks."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class TaskPriority(Enum):
    """Priority levels for prospective tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProspectiveTask:
    """A prospective memory record representing a future task.

    Stores reminders, follow-ups, and scheduled tasks with
    various trigger mechanisms and priority tracking.
    """

    id: str
    user_id: str
    task: str  # Short task description
    description: str | None  # Detailed description
    trigger_type: TriggerType
    trigger_config: dict[str, Any]  # Trigger-specific configuration
    status: TaskStatus
    priority: TaskPriority
    related_goal_id: str | None  # Optional link to a goal
    related_lead_id: str | None  # Optional link to a lead
    completed_at: datetime | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "task": self.task,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "trigger_config": self.trigger_config,
            "status": self.status.value,
            "priority": self.priority.value,
            "related_goal_id": self.related_goal_id,
            "related_lead_id": self.related_lead_id,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProspectiveTask":
        """Create a ProspectiveTask instance from a dictionary.

        Args:
            data: Dictionary containing task data.

        Returns:
            ProspectiveTask instance with restored state.
        """
        # Parse created_at
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        # Parse completed_at (may be None)
        completed_at = data.get("completed_at")
        if completed_at is not None and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            task=data["task"],
            description=data.get("description"),
            trigger_type=TriggerType(data["trigger_type"]),
            trigger_config=data["trigger_config"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]),
            related_goal_id=data.get("related_goal_id"),
            related_lead_id=data.get("related_lead_id"),
            completed_at=completed_at,
            created_at=created_at,
        )
