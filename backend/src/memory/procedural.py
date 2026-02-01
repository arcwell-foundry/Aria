"""Procedural memory module for storing learned workflows.

Procedural memory stores successful workflow patterns with:
- Ordered step sequences for task execution
- Trigger conditions for workflow matching
- Success/failure tracking for learning
- Version history for workflow evolution
- User-specific and shared workflows

Workflows are stored in Supabase for structured querying and
easy integration with the rest of the application state.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Workflow:
    """A procedural memory record representing a learned workflow.

    Stores repeatable patterns of actions with success tracking
    for continuous improvement of task execution.
    """

    id: str
    user_id: str
    workflow_name: str
    description: str
    trigger_conditions: dict[str, Any]  # When to use this workflow
    steps: list[dict[str, Any]]  # Ordered list of actions
    success_count: int
    failure_count: int
    is_shared: bool  # Available to other users in same company
    version: int
    created_at: datetime
    updated_at: datetime

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of this workflow.

        Returns:
            Success rate between 0.0 and 1.0, or 0.0 if no executions.
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        """Serialize workflow to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workflow_name": self.workflow_name,
            "description": self.description,
            "trigger_conditions": self.trigger_conditions,
            "steps": self.steps,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "is_shared": self.is_shared,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create a Workflow instance from a dictionary.

        Args:
            data: Dictionary containing workflow data.

        Returns:
            Workflow instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            workflow_name=data["workflow_name"],
            description=data["description"],
            trigger_conditions=data["trigger_conditions"],
            steps=data["steps"],
            success_count=data["success_count"],
            failure_count=data["failure_count"],
            is_shared=data["is_shared"],
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )
