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
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

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
    metadata: dict[str, Any] = field(default_factory=dict)  # Extensible metadata (e.g. email context)

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
            "metadata": self.metadata,
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
            metadata=data.get("metadata") or {},
        )


class ProspectiveMemory:
    """Service class for prospective memory operations.

    Provides async interface for storing, retrieving, and managing
    future tasks and reminders. Uses Supabase as the underlying storage
    for structured querying and status tracking.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            ProspectiveMemoryError: If client initialization fails.
        """
        from src.core.exceptions import ProspectiveMemoryError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise ProspectiveMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create_task(self, task: ProspectiveTask) -> str:
        """Create a new task in prospective memory.

        Args:
            task: The ProspectiveTask instance to store.

        Returns:
            The ID of the stored task.

        Raises:
            ProspectiveMemoryError: If storage fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            task_id = task.id if task.id else str(uuid.uuid4())

            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": task_id,
                "user_id": task.user_id,
                "task": task.task,
                "description": task.description,
                "trigger_type": task.trigger_type.value,
                "trigger_config": task.trigger_config,
                "status": task.status.value,
                "priority": task.priority.value,
                "related_goal_id": task.related_goal_id,
                "related_lead_id": task.related_lead_id,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "created_at": now.isoformat(),
                "metadata": task.metadata or {},
            }

            response = client.table("prospective_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise ProspectiveMemoryError("Failed to insert task")

            logger.info(
                "Created prospective task",
                extra={
                    "task_id": task_id,
                    "user_id": task.user_id,
                    "task": task.task,
                    "trigger_type": task.trigger_type.value,
                },
            )

            # Audit log the creation
            await log_memory_operation(
                user_id=task.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROSPECTIVE,
                memory_id=task_id,
                metadata={"task": task.task, "trigger_type": task.trigger_type.value},
                suppress_errors=True,
            )

            return task_id

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create task")
            raise ProspectiveMemoryError(f"Failed to create task: {e}") from e

    async def get_task(self, user_id: str, task_id: str) -> ProspectiveTask:
        """Retrieve a specific task by ID.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID.

        Returns:
            The requested ProspectiveTask.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If retrieval fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("id", task_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise TaskNotFoundError(task_id)

            return ProspectiveTask.from_dict(response.data)

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to get task: {e}") from e

    async def update_task(self, task: ProspectiveTask) -> None:
        """Update an existing task.

        Args:
            task: The ProspectiveTask instance with updated data.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            data = {
                "task": task.task,
                "description": task.description,
                "trigger_type": task.trigger_type.value,
                "trigger_config": task.trigger_config,
                "status": task.status.value,
                "priority": task.priority.value,
                "related_goal_id": task.related_goal_id,
                "related_lead_id": task.related_lead_id,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task.id)
                .eq("user_id", task.user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task.id)

            logger.info(
                "Updated prospective task",
                extra={
                    "task_id": task.id,
                    "user_id": task.user_id,
                    "status": task.status.value,
                },
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update task", extra={"task_id": task.id})
            raise ProspectiveMemoryError(f"Failed to update task: {e}") from e

    async def delete_task(self, user_id: str, task_id: str) -> None:
        """Delete a task.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to delete.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If deletion fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .delete()
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Deleted prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to delete task: {e}") from e

    async def complete_task(self, user_id: str, task_id: str) -> None:
        """Mark a task as completed.

        Sets the task status to 'completed' and records the completion time.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to complete.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "status": TaskStatus.COMPLETED.value,
                "completed_at": now.isoformat(),
            }

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Completed prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to complete task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to complete task: {e}") from e

    async def cancel_task(self, user_id: str, task_id: str) -> None:
        """Mark a task as cancelled.

        Sets the task status to 'cancelled'.

        Args:
            user_id: The user who owns the task.
            task_id: The task ID to cancel.

        Raises:
            TaskNotFoundError: If task doesn't exist.
            ProspectiveMemoryError: If update fails.
        """
        from src.core.exceptions import ProspectiveMemoryError, TaskNotFoundError

        try:
            client = self._get_supabase_client()

            data = {"status": TaskStatus.CANCELLED.value}

            response = (
                client.table("prospective_memories")
                .update(data)
                .eq("id", task_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise TaskNotFoundError(task_id)

            logger.info(
                "Cancelled prospective task",
                extra={"task_id": task_id, "user_id": user_id},
            )

        except TaskNotFoundError:
            raise
        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to cancel task", extra={"task_id": task_id})
            raise ProspectiveMemoryError(f"Failed to cancel task: {e}") from e

    async def get_upcoming_tasks(self, user_id: str, limit: int = 10) -> list[ProspectiveTask]:
        """Get upcoming time-based tasks for a user.

        Returns pending tasks with time triggers, ordered by due date.

        Args:
            user_id: The user to get tasks for.
            limit: Maximum number of tasks to return.

        Returns:
            List of upcoming ProspectiveTasks ordered by due date.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", TaskStatus.PENDING.value)
                .eq("trigger_type", TriggerType.TIME.value)
                .order("trigger_config->due_at")
                .limit(limit)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved upcoming tasks",
                extra={"user_id": user_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get upcoming tasks")
            raise ProspectiveMemoryError(f"Failed to get upcoming tasks: {e}") from e

    async def get_overdue_tasks(self, user_id: str) -> list[ProspectiveTask]:
        """Get overdue tasks for a user.

        Returns tasks that have overdue status, ordered by priority.

        Args:
            user_id: The user to get overdue tasks for.

        Returns:
            List of overdue ProspectiveTasks ordered by priority (urgent first).

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", TaskStatus.OVERDUE.value)
                .order("priority", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved overdue tasks",
                extra={"user_id": user_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get overdue tasks")
            raise ProspectiveMemoryError(f"Failed to get overdue tasks: {e}") from e

    async def get_tasks_for_goal(self, user_id: str, goal_id: str) -> list[ProspectiveTask]:
        """Get tasks linked to a specific goal.

        Args:
            user_id: The user to get tasks for.
            goal_id: The goal ID to filter by.

        Returns:
            List of ProspectiveTasks linked to the goal.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("related_goal_id", goal_id)
                .order("created_at", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved tasks for goal",
                extra={"user_id": user_id, "goal_id": goal_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get tasks for goal", extra={"goal_id": goal_id})
            raise ProspectiveMemoryError(f"Failed to get tasks for goal: {e}") from e

    async def get_tasks_for_lead(self, user_id: str, lead_id: str) -> list[ProspectiveTask]:
        """Get tasks linked to a specific lead.

        Args:
            user_id: The user to get tasks for.
            lead_id: The lead ID to filter by.

        Returns:
            List of ProspectiveTasks linked to the lead.

        Raises:
            ProspectiveMemoryError: If the query fails.
        """
        from src.core.exceptions import ProspectiveMemoryError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("related_lead_id", lead_id)
                .order("created_at", desc=True)
                .execute()
            )

            if not response.data:
                return []

            tasks = [ProspectiveTask.from_dict(row) for row in response.data]

            logger.info(
                "Retrieved tasks for lead",
                extra={"user_id": user_id, "lead_id": lead_id, "count": len(tasks)},
            )

            return tasks

        except ProspectiveMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get tasks for lead", extra={"lead_id": lead_id})
            raise ProspectiveMemoryError(f"Failed to get tasks for lead: {e}") from e
