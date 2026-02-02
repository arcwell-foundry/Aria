"""Goal service for ARIA.

This service handles:
- Creating and querying goals
- Managing goal lifecycle (start, pause, complete)
- Tracking goal progress and agent executions
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.goal import GoalCreate, GoalStatus, GoalUpdate

logger = logging.getLogger(__name__)


class GoalService:
    """Service for goal management and execution."""

    def __init__(self) -> None:
        """Initialize goal service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def create_goal(self, user_id: str, data: GoalCreate) -> dict[str, Any]:
        """Create a new goal.

        Args:
            user_id: The user's ID.
            data: Goal creation data.

        Returns:
            Created goal dict.
        """
        logger.info(
            "Creating goal",
            extra={
                "user_id": user_id,
                "title": data.title,
                "goal_type": data.goal_type.value,
            },
        )

        result = (
            self._db.table("goals")
            .insert(
                {
                    "user_id": user_id,
                    "title": data.title,
                    "description": data.description,
                    "goal_type": data.goal_type.value,
                    "config": data.config,
                    "status": GoalStatus.DRAFT.value,
                    "progress": 0,
                }
            )
            .execute()
        )

        goal = cast(dict[str, Any], result.data[0])
        logger.info("Goal created", extra={"goal_id": goal["id"]})
        return goal

    async def get_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Get a goal by ID with its agents.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Goal dict with agents, or None if not found.
        """
        result = (
            self._db.table("goals")
            .select("*, goal_agents(*)")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if result.data is None:
            logger.warning("Goal not found", extra={"user_id": user_id, "goal_id": goal_id})
            return None

        logger.info("Goal retrieved", extra={"goal_id": goal_id})
        return cast(dict[str, Any], result.data)

    async def list_goals(
        self,
        user_id: str,
        status: GoalStatus | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user's goals.

        Args:
            user_id: The user's ID.
            status: Optional filter by goal status.
            limit: Maximum number of goals to return.

        Returns:
            List of goal dicts.
        """
        query = self._db.table("goals").select("*").eq("user_id", user_id)

        if status:
            query = query.eq("status", status.value)

        result = query.order("created_at", desc=True).limit(limit).execute()

        logger.info(
            "Goals listed",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        return cast(list[dict[str, Any]], result.data)

    async def update_goal(
        self,
        user_id: str,
        goal_id: str,
        data: GoalUpdate,
    ) -> dict[str, Any] | None:
        """Update a goal.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            data: Goal update data.

        Returns:
            Updated goal dict, or None if not found.
        """
        # Build update dict, converting enums to values
        update_data: dict[str, Any] = {
            k: v.value if hasattr(v, "value") else v
            for k, v in data.model_dump(exclude_unset=True).items()
        }
        update_data["updated_at"] = datetime.now(UTC).isoformat()

        result = (
            self._db.table("goals")
            .update(update_data)
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal updated", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for update", extra={"goal_id": goal_id})
        return None

    async def delete_goal(self, user_id: str, goal_id: str) -> bool:
        """Delete a goal.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            True if successful.
        """
        self._db.table("goals").delete().eq("id", goal_id).eq("user_id", user_id).execute()

        logger.info("Goal deleted", extra={"goal_id": goal_id})
        return True

    async def start_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Start goal execution.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goals")
            .update(
                {
                    "status": GoalStatus.ACTIVE.value,
                    "started_at": now,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal started", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for start", extra={"goal_id": goal_id})
        return None

    async def pause_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Pause goal execution.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goals")
            .update(
                {
                    "status": GoalStatus.PAUSED.value,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal paused", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for pause", extra={"goal_id": goal_id})
        return None

    async def complete_goal(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Mark goal as complete.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Updated goal dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("goals")
            .update(
                {
                    "status": GoalStatus.COMPLETE.value,
                    "progress": 100,
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Goal completed", extra={"goal_id": goal_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for complete", extra={"goal_id": goal_id})
        return None

    async def update_progress(
        self,
        user_id: str,
        goal_id: str,
        progress: int,
    ) -> dict[str, Any] | None:
        """Update goal progress.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.
            progress: Progress value (0-100, will be clamped).

        Returns:
            Updated goal dict, or None if not found.
        """
        clamped_progress = max(0, min(100, progress))
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("goals")
            .update(
                {
                    "progress": clamped_progress,
                    "updated_at": now,
                }
            )
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Goal progress updated",
                extra={"goal_id": goal_id, "progress": clamped_progress},
            )
            return cast(dict[str, Any], result.data[0])

        logger.warning("Goal not found for progress update", extra={"goal_id": goal_id})
        return None

    async def get_goal_progress(self, user_id: str, goal_id: str) -> dict[str, Any] | None:
        """Get goal with execution progress.

        Args:
            user_id: The user's ID.
            goal_id: The goal ID.

        Returns:
            Goal dict with recent executions, or None if not found.
        """
        goal = await self.get_goal(user_id, goal_id)
        if not goal:
            return None

        # Get agent executions for each agent
        agents = goal.get("goal_agents", [])
        executions: list[dict[str, Any]] = []

        for agent in agents:
            exec_result = (
                self._db.table("agent_executions")
                .select("*")
                .eq("goal_agent_id", agent["id"])
                .order("started_at", desc=True)
                .limit(5)
                .execute()
            )
            executions.extend(cast(list[dict[str, Any]], exec_result.data))

        logger.info(
            "Goal progress retrieved",
            extra={"goal_id": goal_id, "execution_count": len(executions)},
        )

        return {
            **goal,
            "recent_executions": executions,
        }
