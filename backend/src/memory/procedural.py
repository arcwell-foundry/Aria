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
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

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


class ProceduralMemory:
    """Service class for procedural memory operations.

    Provides async interface for storing, retrieving, and managing
    learned workflows. Uses Supabase as the underlying storage for
    structured querying and success rate tracking.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            ProceduralMemoryError: If client initialization fails.
        """
        from src.core.exceptions import ProceduralMemoryError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise ProceduralMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create_workflow(self, workflow: Workflow) -> str:
        """Create a new workflow in procedural memory.

        Args:
            workflow: The Workflow instance to store.

        Returns:
            The ID of the stored workflow.

        Raises:
            ProceduralMemoryError: If storage fails.
        """
        from src.core.exceptions import ProceduralMemoryError

        try:
            # Generate ID if not provided
            workflow_id = workflow.id if workflow.id else str(uuid.uuid4())

            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "id": workflow_id,
                "user_id": workflow.user_id,
                "workflow_name": workflow.workflow_name,
                "description": workflow.description,
                "trigger_conditions": workflow.trigger_conditions,
                "steps": workflow.steps,
                "success_count": workflow.success_count,
                "failure_count": workflow.failure_count,
                "is_shared": workflow.is_shared,
                "version": workflow.version,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            response = client.table("procedural_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise ProceduralMemoryError("Failed to insert workflow")

            logger.info(
                "Created workflow",
                extra={
                    "workflow_id": workflow_id,
                    "user_id": workflow.user_id,
                    "workflow_name": workflow.workflow_name,
                },
            )

            # Audit log the creation
            await log_memory_operation(
                user_id=workflow.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROCEDURAL,
                memory_id=workflow_id,
                metadata={"workflow_name": workflow.workflow_name},
                suppress_errors=True,
            )

            return workflow_id

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create workflow")
            raise ProceduralMemoryError(f"Failed to create workflow: {e}") from e

    async def get_workflow(self, user_id: str, workflow_id: str) -> Workflow:
        """Retrieve a specific workflow by ID.

        Args:
            user_id: The user who owns the workflow.
            workflow_id: The workflow ID.

        Returns:
            The requested Workflow.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If retrieval fails.
        """
        from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("procedural_memories")
                .select("*")
                .eq("id", workflow_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise WorkflowNotFoundError(workflow_id)

            return Workflow.from_dict(response.data)

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get workflow", extra={"workflow_id": workflow_id})
            raise ProceduralMemoryError(f"Failed to get workflow: {e}") from e

    async def update_workflow(self, workflow: Workflow) -> None:
        """Update an existing workflow.

        Increments the version number automatically.

        Args:
            workflow: The Workflow instance with updated data.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If update fails.
        """
        from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            data = {
                "workflow_name": workflow.workflow_name,
                "description": workflow.description,
                "trigger_conditions": workflow.trigger_conditions,
                "steps": workflow.steps,
                "success_count": workflow.success_count,
                "failure_count": workflow.failure_count,
                "is_shared": workflow.is_shared,
                "version": workflow.version + 1,
                "updated_at": now.isoformat(),
            }

            response = (
                client.table("procedural_memories")
                .update(data)
                .eq("id", workflow.id)
                .eq("user_id", workflow.user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise WorkflowNotFoundError(workflow.id)

            logger.info(
                "Updated workflow",
                extra={
                    "workflow_id": workflow.id,
                    "user_id": workflow.user_id,
                    "new_version": workflow.version + 1,
                },
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update workflow", extra={"workflow_id": workflow.id})
            raise ProceduralMemoryError(f"Failed to update workflow: {e}") from e

    async def delete_workflow(self, user_id: str, workflow_id: str) -> None:
        """Delete a workflow.

        Args:
            user_id: The user who owns the workflow.
            workflow_id: The workflow ID to delete.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If deletion fails.
        """
        from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("procedural_memories")
                .delete()
                .eq("id", workflow_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise WorkflowNotFoundError(workflow_id)

            logger.info(
                "Deleted workflow",
                extra={"workflow_id": workflow_id, "user_id": user_id},
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete workflow", extra={"workflow_id": workflow_id})
            raise ProceduralMemoryError(f"Failed to delete workflow: {e}") from e

    async def find_matching_workflow(
        self, user_id: str, context: dict[str, Any]
    ) -> Workflow | None:
        """Find the best matching workflow for a given context.

        Matches trigger conditions against the provided context and
        returns the workflow with the highest success rate among matches.

        Args:
            user_id: The user to find workflows for.
            context: The current context to match against trigger conditions.

        Returns:
            The best matching Workflow, or None if no match found.

        Raises:
            ProceduralMemoryError: If the query fails.
        """
        from src.core.exceptions import ProceduralMemoryError

        try:
            client = self._get_supabase_client()

            # Get all workflows for this user
            response = (
                client.table("procedural_memories").select("*").eq("user_id", user_id).execute()
            )

            if not response.data:
                return None

            # Find workflows whose trigger conditions match the context
            matching_workflows: list[Workflow] = []

            for row in response.data:
                workflow = Workflow.from_dict(row)
                trigger_conditions = workflow.trigger_conditions

                # Check if all trigger conditions are satisfied by context
                if self._matches_trigger_conditions(trigger_conditions, context):
                    matching_workflows.append(workflow)

            if not matching_workflows:
                return None

            # Return workflow with highest success rate
            best_workflow = max(matching_workflows, key=lambda w: w.success_rate)

            logger.info(
                "Found matching workflow",
                extra={
                    "workflow_id": best_workflow.id,
                    "workflow_name": best_workflow.workflow_name,
                    "success_rate": best_workflow.success_rate,
                    "context_keys": list(context.keys()),
                },
            )

            return best_workflow

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to find matching workflow")
            raise ProceduralMemoryError(f"Failed to find matching workflow: {e}") from e

    def _matches_trigger_conditions(
        self, trigger_conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Check if context satisfies trigger conditions.

        All trigger conditions must be present in context with matching values.

        Args:
            trigger_conditions: The workflow's trigger conditions.
            context: The current context to match against.

        Returns:
            True if all trigger conditions are satisfied.
        """
        for key, value in trigger_conditions.items():
            if key not in context:
                return False
            if context[key] != value:
                return False
        return True

    async def record_outcome(self, workflow_id: str, success: bool) -> None:
        """Record the outcome of a workflow execution.

        Updates the success or failure count based on the result.

        Args:
            workflow_id: The workflow that was executed.
            success: True if execution succeeded, False if failed.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ProceduralMemoryError: If update fails.
        """
        from src.core.exceptions import ProceduralMemoryError, WorkflowNotFoundError

        try:
            client = self._get_supabase_client()

            # Get current counts
            response = (
                client.table("procedural_memories")
                .select("success_count, failure_count")
                .eq("id", workflow_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise WorkflowNotFoundError(workflow_id)

            current_success = response.data["success_count"]
            current_failure = response.data["failure_count"]

            # Update the appropriate counter
            now = datetime.now(UTC)
            if success:
                update_data = {
                    "success_count": current_success + 1,
                    "updated_at": now.isoformat(),
                }
            else:
                update_data = {
                    "failure_count": current_failure + 1,
                    "updated_at": now.isoformat(),
                }

            client.table("procedural_memories").update(update_data).eq("id", workflow_id).execute()

            logger.info(
                "Recorded workflow outcome",
                extra={
                    "workflow_id": workflow_id,
                    "success": success,
                    "new_success_count": current_success + (1 if success else 0),
                    "new_failure_count": current_failure + (0 if success else 1),
                },
            )

        except WorkflowNotFoundError:
            raise
        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to record outcome", extra={"workflow_id": workflow_id})
            raise ProceduralMemoryError(f"Failed to record outcome: {e}") from e

    async def list_workflows(self, user_id: str, include_shared: bool = True) -> list[Workflow]:
        """List all workflows available to a user.

        Args:
            user_id: The user to list workflows for.
            include_shared: Whether to include shared workflows from other users.

        Returns:
            List of Workflow instances.

        Raises:
            ProceduralMemoryError: If the query fails.
        """
        from src.core.exceptions import ProceduralMemoryError

        try:
            client = self._get_supabase_client()

            query = client.table("procedural_memories").select("*")

            if include_shared:
                # Get user's own workflows OR shared workflows
                query = query.or_(f"user_id.eq.{user_id},is_shared.eq.true")
            else:
                # Only get user's own workflows
                query = query.eq("user_id", user_id)

            response = query.execute()

            if not response.data:
                return []

            workflows = [Workflow.from_dict(row) for row in response.data]

            logger.info(
                "Listed workflows",
                extra={
                    "user_id": user_id,
                    "include_shared": include_shared,
                    "count": len(workflows),
                },
            )

            return workflows

        except ProceduralMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to list workflows")
            raise ProceduralMemoryError(f"Failed to list workflows: {e}") from e
