"""Goal API routes for ARIA.

This module provides endpoints for:
- Creating and querying goals
- Managing goal lifecycle (start, pause, complete)
- Tracking goal progress
- Async goal execution (propose, plan, execute, events, cancel, report)
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.models.goal import (
    CreateWithARIARequest,
    GoalCreate,
    GoalStatus,
    GoalUpdate,
    MilestoneCreate,
)
from src.services.goal_service import GoalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goals", tags=["goals"])


def _get_service() -> GoalService:
    """Get goal service instance."""
    return GoalService()


# Response models


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    status: str = Field(
        ..., min_length=1, max_length=50, description="Status of deletion operation"
    )


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


# Goal Lifecycle Endpoints — Static routes (must precede /{goal_id})


@router.get("/dashboard")
async def get_dashboard(current_user: CurrentUser) -> list[dict[str, Any]]:
    """Get dashboard view of goals with milestone counts and health.

    Returns all goals for the user with computed milestone_total and
    milestone_complete counts for dashboard rendering.
    """
    service = _get_service()
    return await service.get_dashboard(current_user.id)


@router.post("/create-with-aria")
async def create_with_aria(
    data: CreateWithARIARequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create a goal collaboratively with ARIA.

    Sends the user's goal idea to ARIA for SMART refinement and returns
    suggestions including refined title, description, sub-tasks, and
    agent assignments.
    """
    service = _get_service()
    return await service.create_with_aria(current_user.id, data.title, data.description)


@router.get("/templates")
async def get_templates(
    current_user: CurrentUser,  # noqa: ARG001
    role: str | None = Query(None, description="Filter templates by role"),
) -> list[dict[str, Any]]:
    """Get goal templates, optionally filtered by role.

    Returns a list of pre-built goal templates that users can use as
    starting points. Use ?role=sales to filter by role.
    """
    service = _get_service()
    return await service.get_templates(role)


# --- Async Goal Execution Endpoints (must precede /{goal_id}) ---


def _get_execution_service():  # type: ignore[no-untyped-def]
    """Get goal execution service instance."""
    from src.services.goal_execution import GoalExecutionService

    return GoalExecutionService()


@router.post("/propose")
async def propose_goals(current_user: CurrentUser) -> dict[str, Any]:
    """Propose goals for the user based on context.

    Uses LLM to analyze user's pipeline, knowledge gaps, and market
    signals to suggest actionable goals ARIA should pursue.
    """
    service = _get_execution_service()
    result = await service.propose_goals(current_user.id)
    logger.info("Goals proposed via API", extra={"user_id": current_user.id})
    return result


@router.post("/{goal_id}/plan")
async def plan_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create an execution plan for a goal.

    Decomposes the goal into sub-tasks with agent assignments and
    dependency ordering. Stores the plan in the database.
    """
    service = _get_execution_service()
    result = await service.plan_goal(goal_id, current_user.id)
    logger.info("Goal planned via API", extra={"goal_id": goal_id})
    return result


@router.post("/{goal_id}/execute")
async def execute_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Start async background execution of a goal.

    Launches agents in background and returns immediately.
    Use the /events endpoint to stream progress updates.
    """
    service = _get_execution_service()
    result = await service.execute_goal_async(goal_id, current_user.id)
    logger.info("Goal execution started via API", extra={"goal_id": goal_id})
    return result


@router.get("/{goal_id}/events")
async def goal_events(
    goal_id: str,
    current_user: CurrentUser,  # noqa: ARG001
) -> StreamingResponse:
    """Stream goal execution events via SSE.

    Returns a Server-Sent Events stream of GoalEvents for real-time
    monitoring of background goal execution. Stream ends when goal
    completes or errors.
    """
    from src.core.event_bus import EventBus

    event_bus = EventBus.get_instance()

    async def event_stream():  # type: ignore[no-untyped-def]
        queue = event_bus.subscribe(goal_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                    if event.event_type in ("goal.complete", "goal.error"):
                        break
                except TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            event_bus.unsubscribe(goal_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{goal_id}/cancel")
async def cancel_goal_execution(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Cancel background execution of a goal.

    Stops any running background tasks and updates goal status to paused.
    """
    service = _get_execution_service()
    result = await service.cancel_goal(goal_id, current_user.id)
    logger.info("Goal cancelled via API", extra={"goal_id": goal_id})
    return result


@router.get("/{goal_id}/report")
async def goal_report(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a narrative progress report for a goal.

    Uses LLM to summarize current progress into a human-readable
    report suitable for the conversation UI.
    """
    service = _get_execution_service()
    result = await service.report_progress(goal_id, current_user.id)
    logger.info("Goal report generated via API", extra={"goal_id": goal_id})
    return result


# --- Standard Goal CRUD Endpoints ---


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


# Goal Detail, Milestone & Retrospective Endpoints


@router.get("/{goal_id}/detail")
async def get_goal_detail(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get full goal detail with milestones and retrospective.

    Returns comprehensive goal information including all milestones
    ordered by sort_order and the associated retrospective (if any).
    """
    service = _get_service()
    detail = await service.get_goal_detail(current_user.id, goal_id)
    if detail is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")
    return detail


@router.post("/{goal_id}/milestone")
async def add_milestone(
    goal_id: str,
    data: MilestoneCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Add a milestone to a goal.

    Creates a new milestone for the specified goal with automatic
    sort_order calculation based on existing milestones.
    """
    service = _get_service()
    milestone = await service.add_milestone(
        current_user.id, goal_id, data.title, data.description, data.due_date
    )
    if milestone is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")
    return milestone


@router.post("/{goal_id}/retrospective")
async def generate_retrospective(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate an AI-powered retrospective for a goal.

    Uses ARIA to analyze the goal's milestones and agent executions,
    producing a structured retrospective with learnings and analysis.
    """
    service = _get_service()
    retro = await service.generate_retrospective(current_user.id, goal_id)
    if retro is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")
    return retro
