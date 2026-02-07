"""Goal API routes for ARIA.

This module provides endpoints for:
- Creating and querying goals
- Managing goal lifecycle (start, pause, complete)
- Tracking goal progress
"""

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.models.goal import GoalCreate, GoalStatus, GoalUpdate
from src.services.goal_service import GoalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goals", tags=["goals"])


def _get_service() -> GoalService:
    """Get goal service instance."""
    return GoalService()


# Response models


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    status: str = Field(..., min_length=1, max_length=50, description="Status of deletion operation")


# Goal Endpoints


@router.post("")
async def create_goal(
    data: GoalCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create a new goal.

    Creates a new goal with the provided title, description, type, and config.
    Goals start in draft status.
    """
    service = _get_service()
    result = await service.create_goal(current_user.id, data)

    logger.info(
        "Goal created via API",
        extra={
            "user_id": current_user.id,
            "goal_id": result["id"],
            "title": data.title,
        },
    )

    return result


@router.get("")
async def list_goals(
    current_user: CurrentUser,
    status: GoalStatus | None = Query(None, description="Filter by goal status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of goals to return"),
) -> list[dict[str, Any]]:
    """List user's goals.

    Returns a list of goals for the current user, optionally filtered by status.
    """
    service = _get_service()
    goals = await service.list_goals(current_user.id, status, limit)

    logger.info(
        "Goals listed via API",
        extra={"user_id": current_user.id, "count": len(goals)},
    )

    return goals


@router.get("/{goal_id}")
async def get_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a specific goal with agents.

    Returns detailed information about a goal including its associated agents.
    """
    service = _get_service()
    goal = await service.get_goal(current_user.id, goal_id)

    if goal is None:
        logger.warning(
            "Goal not found via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal retrieved via API", extra={"goal_id": goal_id})

    return goal


@router.patch("/{goal_id}")
async def update_goal(
    goal_id: str,
    data: GoalUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update a goal.

    Updates the specified fields of a goal. Only provided fields are modified.
    """
    service = _get_service()
    goal = await service.update_goal(current_user.id, goal_id, data)

    if goal is None:
        logger.warning(
            "Goal not found for update via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal updated via API", extra={"goal_id": goal_id})

    return goal


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> DeleteResponse:
    """Delete a goal.

    Permanently deletes a goal and all its associated data.
    """
    service = _get_service()
    await service.delete_goal(current_user.id, goal_id)

    logger.info("Goal deleted via API", extra={"goal_id": goal_id})

    return DeleteResponse(status="deleted")


# Goal Lifecycle Endpoints


@router.post("/{goal_id}/start")
async def start_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Start goal execution.

    Transitions a goal from draft to active status and sets the started_at timestamp.
    """
    service = _get_service()
    goal = await service.start_goal(current_user.id, goal_id)

    if goal is None:
        logger.warning(
            "Goal not found for start via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal started via API", extra={"goal_id": goal_id})

    return goal


@router.post("/{goal_id}/pause")
async def pause_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Pause goal execution.

    Transitions an active goal to paused status.
    """
    service = _get_service()
    goal = await service.pause_goal(current_user.id, goal_id)

    if goal is None:
        logger.warning(
            "Goal not found for pause via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal paused via API", extra={"goal_id": goal_id})

    return goal


@router.post("/{goal_id}/complete")
async def complete_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Mark goal as complete.

    Transitions a goal to complete status, sets progress to 100%, and records completion time.
    """
    service = _get_service()
    goal = await service.complete_goal(current_user.id, goal_id)

    if goal is None:
        logger.warning(
            "Goal not found for complete via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal completed via API", extra={"goal_id": goal_id})

    return goal


# Goal Progress Endpoints


@router.get("/{goal_id}/progress")
async def get_goal_progress(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get goal execution progress.

    Returns goal details along with recent agent executions.
    """
    service = _get_service()
    progress = await service.get_goal_progress(current_user.id, goal_id)

    if progress is None:
        logger.warning(
            "Goal not found for progress via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info("Goal progress retrieved via API", extra={"goal_id": goal_id})

    return progress


@router.patch("/{goal_id}/progress")
async def update_progress(
    goal_id: str,
    current_user: CurrentUser,
    progress: int = Query(..., ge=0, le=100, description="Progress value (0-100)"),
) -> dict[str, Any]:
    """Update goal progress.

    Updates the progress percentage of a goal. Value is clamped to 0-100.
    """
    service = _get_service()
    goal = await service.update_progress(current_user.id, goal_id, progress)

    if goal is None:
        logger.warning(
            "Goal not found for progress update via API",
            extra={"user_id": current_user.id, "goal_id": goal_id},
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")

    logger.info(
        "Goal progress updated via API",
        extra={"goal_id": goal_id, "progress": progress},
    )

    return goal
