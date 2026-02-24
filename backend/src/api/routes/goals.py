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
    Goals start in draft status, then auto-plan generates an execution plan
    and transitions to plan_ready for user approval.
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

    # Auto-generate execution plan and present for approval
    try:
        exec_service = _get_execution_service()
        plan_result = await exec_service.plan_goal(result["id"], current_user.id)
        result["execution_plan"] = plan_result
    except Exception as e:
        logger.warning("Auto-plan failed for goal %s: %s", result["id"], e)

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
    """Create a resource-aware execution plan for a goal.

    Gathers user's integrations, trust levels, and company context,
    then uses Claude to decompose the goal into sub-tasks with agent
    assignments, tool requirements, risk levels, and dependency ordering.
    """
    service = _get_execution_service()
    result = await service.plan_goal(goal_id, current_user.id)
    logger.info("Goal planned via API", extra={"goal_id": goal_id})
    return result


@router.get("/{goal_id}/plan")
async def get_goal_plan(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get the execution plan for a goal with per-task resource status.

    Returns the stored execution plan with resource availability checks
    for each task's required tools, an overall readiness score, and
    lists of missing integrations.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()

    # Validate user owns this goal
    goal_result = (
        db.table("goals")
        .select("id, title, status, user_id")
        .eq("id", goal_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not goal_result.data:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Fetch latest plan
    plan_result = (
        db.table("goal_execution_plans")
        .select("*")
        .eq("goal_id", goal_id)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    if not plan_result.data:
        raise HTTPException(status_code=404, detail="No execution plan found for this goal")

    plan_row = plan_result.data
    tasks_raw = plan_row.get("tasks", "[]")
    tasks = json.loads(tasks_raw) if isinstance(tasks_raw, str) else tasks_raw

    # Fetch user's active integrations for resource checking
    integ_result = (
        db.table("user_integrations")
        .select("integration_type, status")
        .eq("user_id", current_user.id)
        .eq("status", "active")
        .execute()
    )
    active_integrations = [
        i["integration_type"] for i in (integ_result.data or [])
    ]

    # Annotate each task with live resource status
    service = _get_execution_service()
    total_tools = 0
    connected_tools = 0
    for task in tasks:
        resource_status: list[dict[str, Any]] = []
        for tool in task.get("tools_needed", []):
            is_connected = service._check_tool_connected(tool, active_integrations)
            resource_status.append({"tool": tool, "connected": is_connected})
            total_tools += 1
            if is_connected:
                connected_tools += 1
        task["resource_status"] = resource_status

    # Compute readiness score
    readiness_score = (
        round((connected_tools / total_tools) * 100) if total_tools > 0 else 100
    )

    # Identify missing integrations
    all_auth_required: set[str] = set()
    for task in tasks:
        for auth in task.get("auth_required", []):
            if auth not in active_integrations:
                all_auth_required.add(auth)

    logger.info(
        "Goal plan retrieved",
        extra={"goal_id": goal_id, "readiness_score": readiness_score},
    )

    return {
        "goal_id": goal_id,
        "title": goal_result.data.get("title", ""),
        "status": goal_result.data.get("status", "draft"),
        "tasks": tasks,
        "execution_mode": plan_row.get("execution_mode", "parallel"),
        "estimated_total_minutes": plan_row.get("estimated_total_minutes", 0),
        "reasoning": plan_row.get("reasoning", ""),
        "readiness_score": readiness_score,
        "missing_integrations": sorted(all_auth_required),
        "connected_integrations": active_integrations,
    }


@router.post("/{goal_id}/approve")
async def approve_goal_plan(
    goal_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve an execution plan and start goal execution.

    Validates that the JWT user owns the goal and the goal is in an
    approvable state (plan_ready or draft), updates the plan row,
    sets goal status to active, triggers async execution, persists
    a confirmation message, and emits a WebSocket event.
    """
    from datetime import UTC, datetime

    from fastapi import HTTPException

    from src.core.ws import ws_manager
    from src.db.supabase import SupabaseClient
    from src.models.ws_events import AriaMessageEvent
    from src.services.conversations import ConversationService

    db = SupabaseClient.get_client()

    # Validate ownership
    goal_result = (
        db.table("goals")
        .select("id, title, status, user_id")
        .eq("id", goal_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not goal_result.data:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal = goal_result.data

    # Validate goal is in an approvable state
    if goal["status"] not in ("plan_ready", "draft"):
        if goal["status"] == "active":
            raise HTTPException(status_code=400, detail="Goal is already executing")
        if goal["status"] == "complete":
            raise HTTPException(status_code=400, detail="Goal is already complete")
        raise HTTPException(
            status_code=400,
            detail=f"Goal cannot be approved in '{goal['status']}' status",
        )

    now = datetime.now(UTC).isoformat()

    # Update goal_execution_plans row: mark as approved
    try:
        db.table("goal_execution_plans").update(
            {"status": "approved", "approved_at": now, "updated_at": now}
        ).eq("goal_id", goal_id).execute()
    except Exception as e:
        logger.warning("Failed to update plan row on approval: %s", e)

    # Activate the goal
    db.table("goals").update(
        {"status": "active", "started_at": now, "updated_at": now}
    ).eq("id", goal_id).execute()

    # Trigger async execution
    service = _get_execution_service()
    await service.execute_goal_async(goal_id, current_user.id)

    # Persist a confirmation message to the conversation
    try:
        conv_result = (
            db.table("conversations")
            .select("id")
            .eq("user_id", current_user.id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if conv_result.data:
            conv_service = ConversationService(db)
            await conv_service.save_message(
                conversation_id=conv_result.data[0]["id"],
                role="assistant",
                content=(
                    f"Starting execution on **{goal['title']}**. "
                    f"I'll keep you updated as each phase completes."
                ),
                metadata={
                    "type": "plan_approved",
                    "data": {"goal_id": goal_id, "title": goal["title"]},
                },
            )
    except Exception as e:
        logger.warning("Failed to persist approval message: %s", e)

    # Emit conversational WebSocket message
    try:
        event = AriaMessageEvent(
            message=(
                f"Starting execution on **{goal['title']}**. "
                f"I'll keep you updated as each phase completes."
            ),
            rich_content=[],
            ui_commands=[
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "goals",
                    "badge_count": 1,
                }
            ],
            suggestions=[
                "Show me the progress",
                "What step is running now?",
                "Pause if anything looks off",
            ],
        )
        await ws_manager.send_to_user(current_user.id, event)
    except Exception as e:
        logger.warning("Failed to send approval WebSocket event: %s", e)

    logger.info(
        "Goal plan approved and execution started",
        extra={"goal_id": goal_id, "user_id": current_user.id},
    )

    return {
        "goal_id": goal_id,
        "status": "active",
        "started_at": now,
        "message": f"Execution started for: {goal['title']}",
    }


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


# --- Goal Proposal Approval ---


def _build_execution_plan(
    goal_id: str,
    title: str,
    goal_type: str,
    agents: list[str],
    timeline: str,
) -> dict[str, Any]:
    """Build an ExecutionPlanCard rich content dict based on goal type.

    Maps different goal types to tailored phase templates so the
    execution plan reflects the actual work involved.

    Args:
        goal_id: Created goal's ID.
        title: Goal title.
        goal_type: Type of goal (lead_gen, research, competitive_intel, etc.).
        agents: Assigned agent names.
        timeline: User-facing timeline string.

    Returns:
        Rich content dict with type 'execution_plan'.
    """
    # Phase templates by goal type
    phase_templates: dict[str, list[dict[str, Any]]] = {
        "lead_gen": [
            {
                "name": "Prospect Identification",
                "timeline": "Days 1-3",
                "agent_filter": ("Hunter", "Scout"),
                "output": "Qualified prospect list with company profiles",
            },
            {
                "name": "Engagement Strategy",
                "timeline": "Days 3-5",
                "agent_filter": ("Strategist", "Analyst"),
                "output": "Personalized outreach strategy per prospect",
            },
            {
                "name": "Outreach Execution",
                "timeline": f"Days 5-{timeline or '14'}",
                "agent_filter": ("Scribe", "Operator"),
                "output": "Email sequences, follow-up tasks, meeting requests",
            },
        ],
        "competitive_intel": [
            {
                "name": "Intelligence Gathering",
                "timeline": "Days 1-3",
                "agent_filter": ("Scout", "Hunter"),
                "output": "Competitor product, pricing, and positioning data",
            },
            {
                "name": "Battle Card Creation",
                "timeline": "Days 3-5",
                "agent_filter": ("Analyst", "Strategist"),
                "output": "Battle cards with feature gaps and objection handling",
            },
            {
                "name": "Team Enablement",
                "timeline": f"Days 5-{timeline or '10'}",
                "agent_filter": ("Scribe",),
                "output": "Talking points, win/loss summaries, competitive alerts",
            },
        ],
        "research": [
            {
                "name": "Data Collection",
                "timeline": "Days 1-4",
                "agent_filter": ("Scout", "Hunter", "Analyst"),
                "output": "Raw data from public sources, databases, and signals",
            },
            {
                "name": "Synthesis & Insights",
                "timeline": "Days 4-7",
                "agent_filter": ("Analyst", "Strategist"),
                "output": "Research report with key findings and recommendations",
            },
            {
                "name": "Deliverable",
                "timeline": f"Days 7-{timeline or '14'}",
                "agent_filter": ("Scribe",),
                "output": "Final report, executive summary, or presentation draft",
            },
        ],
        "outreach": [
            {
                "name": "Audience Mapping",
                "timeline": "Days 1-2",
                "agent_filter": ("Hunter", "Analyst"),
                "output": "Target list with contact details and context",
            },
            {
                "name": "Content Creation",
                "timeline": "Days 2-4",
                "agent_filter": ("Scribe", "Strategist"),
                "output": "Personalized email drafts and messaging sequences",
            },
            {
                "name": "Campaign Execution",
                "timeline": f"Days 4-{timeline or '10'}",
                "agent_filter": ("Operator", "Scribe"),
                "output": "Sent messages, tracked responses, follow-up queue",
            },
        ],
    }

    templates = phase_templates.get(
        goal_type,
        [
            {
                "name": "Discovery",
                "timeline": "Days 1-3",
                "agent_filter": ("Hunter", "Scout", "Analyst"),
                "output": "Research report, lead list, or competitive data",
            },
            {
                "name": "Analysis",
                "timeline": "Days 3-5",
                "agent_filter": ("Analyst", "Strategist"),
                "output": "Strategic insights and recommendations",
            },
            {
                "name": "Execution",
                "timeline": f"Days 5-{timeline or '14'}",
                "agent_filter": ("Scribe", "Operator"),
                "output": "Drafts, outreach, or operational tasks",
            },
        ],
    )

    phases = [
        {
            "name": t["name"],
            "timeline": t["timeline"],
            "agents": [a for a in agents if a in t["agent_filter"]],
            "output": t["output"],
            "status": "pending",
        }
        for t in templates
    ]

    return {
        "type": "execution_plan",
        "data": {
            "goal_id": goal_id,
            "title": title,
            "phases": phases,
            "autonomy": {
                "autonomous": "Research, data gathering, analysis, and report generation",
                "requires_approval": "Sending emails, making calendar changes, contacting leads",
            },
        },
    }


class ApproveGoalProposalRequest(BaseModel):
    """Request body for approving a goal proposal from ARIA's first conversation."""

    title: str
    description: str | None = None
    goal_type: str = "custom"
    rationale: str = ""
    approach: str = ""
    agents: list[str] = Field(default_factory=list)
    timeline: str = ""


@router.post("/approve-proposal")
async def approve_goal_proposal(
    data: ApproveGoalProposalRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a goal proposal from ARIA's first conversation.

    Takes a goal proposal (title, description, agents, timeline) and
    creates it as an active goal. Returns the goal with an execution
    plan card showing phases, agent assignments, and autonomy levels.
    Also pushes a confirmation message via WebSocket.
    """
    from src.models.goal import GoalType

    try:
        goal_type = GoalType(data.goal_type)
    except ValueError:
        goal_type = GoalType.CUSTOM

    service = _get_service()
    goal_data = GoalCreate(
        title=data.title,
        description=data.description or data.rationale,
        goal_type=goal_type,
        config={
            "source": "first_conversation_proposal",
            "rationale": data.rationale,
            "approach": data.approach,
            "agents": data.agents,
            "timeline": data.timeline,
        },
    )
    result = await service.create_goal(current_user.id, goal_data)

    # Generate resource-aware execution plan (queries this user's
    # integrations, trust profiles, and company facts via plan_goal)
    exec_service = _get_execution_service()
    plan_result = await exec_service.plan_goal(result["id"], current_user.id)

    # plan_goal() already emits the plan via WebSocket with rich_content,
    # but if it failed we still send a confirmation message.
    if plan_result.get("error"):
        try:
            from src.core.ws import ws_manager
            from src.models.ws_events import AriaMessageEvent

            # Fall back to legacy phase-based plan if resource-aware planning fails
            execution_plan = _build_execution_plan(
                goal_id=result["id"],
                title=data.title,
                goal_type=data.goal_type,
                agents=data.agents,
                timeline=data.timeline,
            )
            event = AriaMessageEvent(
                message=(
                    f"Great — I've created the goal **{data.title}**. "
                    f"Here's my execution plan. I'll start with discovery and "
                    f"keep you updated on progress."
                ),
                rich_content=[execution_plan],
                ui_commands=[
                    {
                        "action": "update_sidebar_badge",
                        "sidebar_item": "actions",
                        "badge_count": 1,
                    }
                ],
                suggestions=[
                    "Approve the plan",
                    "Adjust the timeline",
                    "Add more detail to phase 1",
                ],
            )
            await ws_manager.send_to_user(current_user.id, event)
        except Exception as e:
            logger.warning("WebSocket delivery failed for goal approval: %s", e)

    logger.info(
        "Goal proposal approved",
        extra={"user_id": current_user.id, "goal_id": result["id"]},
    )
    return {**result, "execution_plan": plan_result}


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
