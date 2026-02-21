"""Action queue API routes for ARIA (US-937).

This module provides endpoints for:
- Querying the action queue with status filters
- Approving and rejecting individual actions
- Batch-approving multiple actions
- Viewing action details with reasoning
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.action_queue import ActionCreate, ActionReject, BatchApproveRequest
from src.services.action_queue_service import ActionQueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions", tags=["actions"])


def _get_service() -> ActionQueueService:
    """Get action queue service instance."""
    return ActionQueueService()


# Static routes first (before /{action_id})


@router.get("")
async def list_actions(
    current_user: CurrentUser,
    status: str | None = Query(None, description="Filter by action status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of actions to return"),
) -> list[dict[str, Any]]:
    """List actions in the queue.

    Returns a list of actions for the current user, optionally filtered by status.
    Returns empty list on any service initialization or query failure.
    """
    try:
        service = _get_service()
        actions = await service.get_queue(current_user.id, status, limit)
    except Exception:
        logger.warning(
            "Failed to list actions, returning empty list",
            extra={"user_id": current_user.id},
            exc_info=True,
        )
        return []

    logger.info(
        "Actions listed via API",
        extra={"user_id": current_user.id, "count": len(actions)},
    )

    return actions


@router.post("")
async def submit_action(
    data: ActionCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Submit a new action for approval or auto-execution.

    Actions are routed based on risk level:
    - LOW: auto-approved
    - MEDIUM/HIGH/CRITICAL: pending approval
    """
    service = _get_service()
    result = await service.submit_action(current_user.id, data)

    logger.info(
        "Action submitted via API",
        extra={
            "user_id": current_user.id,
            "action_id": result["id"],
            "risk_level": data.risk_level.value,
        },
    )

    return result


@router.get("/pending-count")
async def get_pending_count(
    current_user: CurrentUser,
) -> dict[str, int]:
    """Get count of pending actions for the current user."""
    try:
        service = _get_service()
        count = await service.get_pending_count(current_user.id)
    except Exception:
        logger.warning(
            "Failed to get pending count, returning 0",
            extra={"user_id": current_user.id},
            exc_info=True,
        )
        return {"count": 0}
    return {"count": count}


@router.post("/batch-approve")
async def batch_approve(
    data: BatchApproveRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve multiple pending actions at once.

    Returns the list of successfully approved actions and count.
    """
    service = _get_service()
    approved = await service.batch_approve(data.action_ids, current_user.id)

    logger.info(
        "Actions batch approved via API",
        extra={
            "user_id": current_user.id,
            "requested": len(data.action_ids),
            "approved": len(approved),
        },
    )

    return {"approved": approved, "count": len(approved)}


# Parameterized routes


@router.get("/{action_id}")
async def get_action(
    action_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get action details including reasoning.

    Returns the full action with payload and reasoning chain.
    """
    service = _get_service()
    action = await service.get_action(action_id, current_user.id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")

    logger.info("Action retrieved via API", extra={"action_id": action_id})

    return action


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a pending action.

    Only pending actions can be approved. Returns the updated action.
    """
    service = _get_service()
    action = await service.approve_action(action_id, current_user.id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found or not pending")

    logger.info(
        "Action approved via API",
        extra={"action_id": action_id, "user_id": current_user.id},
    )

    return action


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: str,
    data: ActionReject,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Reject a pending action with optional reason.

    Only pending actions can be rejected. Returns the updated action.
    """
    service = _get_service()
    action = await service.reject_action(action_id, current_user.id, data.reason)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found or not pending")

    logger.info(
        "Action rejected via API",
        extra={"action_id": action_id, "user_id": current_user.id},
    )

    return action


@router.post("/{action_id}/execute")
async def execute_action(
    action_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Execute an approved action.

    Only approved or auto-approved actions can be executed.
    """
    service = _get_service()
    action = await service.execute_action(action_id, current_user.id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found or not approved")

    logger.info(
        "Action executed via API",
        extra={"action_id": action_id, "user_id": current_user.id},
    )

    return action


@router.post("/{action_id}/undo")
async def undo_action(
    action_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Request undo of a recently executed action within the 5-min window.

    Only actions in undo_pending status with an active undo window can be undone.
    """
    from src.services.action_execution import get_action_execution_service

    svc = get_action_execution_service()
    result = await svc.request_undo(action_id, current_user.id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Undo failed"))

    logger.info(
        "Action undo requested via API",
        extra={"action_id": action_id, "user_id": current_user.id},
    )

    return result
