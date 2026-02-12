"""Action queue service for ARIA (US-937).

This service handles:
- Submitting actions for approval or auto-execution
- Approving, rejecting, and batch-approving actions
- Querying the action queue with status filters
- Executing approved actions
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.action_queue import ActionCreate, ActionStatus, RiskLevel

logger = logging.getLogger(__name__)

# Risk levels that auto-approve when trust is established
AUTO_APPROVE_RISK_LEVELS = {RiskLevel.LOW}


class ActionQueueService:
    """Manages ARIA's autonomous actions with approval workflow."""

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def submit_action(
        self,
        user_id: str,
        data: ActionCreate,
    ) -> dict[str, Any]:
        """Submit an action for approval or auto-execution.

        LOW risk + trust established -> auto_approved
        MEDIUM risk -> pending (notify, auto-approve after timeout)
        HIGH risk -> pending (require explicit approval)
        CRITICAL -> pending (always require approval)

        Args:
            user_id: The user's ID.
            data: Action creation data.

        Returns:
            Created action dict.
        """
        # Determine initial status based on risk level
        if data.risk_level in AUTO_APPROVE_RISK_LEVELS:
            initial_status = ActionStatus.AUTO_APPROVED.value
            approved_at = datetime.now(UTC).isoformat()
        else:
            initial_status = ActionStatus.PENDING.value
            approved_at = None

        insert_data: dict[str, Any] = {
            "user_id": user_id,
            "agent": data.agent.value,
            "action_type": data.action_type.value,
            "title": data.title,
            "description": data.description,
            "risk_level": data.risk_level.value,
            "status": initial_status,
            "payload": data.payload,
            "reasoning": data.reasoning,
        }
        if approved_at:
            insert_data["approved_at"] = approved_at

        result = self._db.table("aria_action_queue").insert(insert_data).execute()

        action = cast(dict[str, Any], result.data[0])
        logger.info(
            "Action submitted",
            extra={
                "action_id": action["id"],
                "user_id": user_id,
                "risk_level": data.risk_level.value,
                "status": initial_status,
            },
        )

        # Broadcast action.pending WebSocket event for pending actions
        if initial_status == ActionStatus.PENDING.value:
            try:
                from src.core.ws import ws_manager

                await ws_manager.send_action_pending(
                    user_id=user_id,
                    action_id=action["id"],
                    title=data.title,
                    agent=data.agent.value,
                    risk_level=data.risk_level.value,
                    description=data.description,
                    payload=data.payload,
                )
                logger.info(
                    "ActionPendingEvent broadcast via WebSocket",
                    extra={
                        "action_id": action["id"],
                        "user_id": user_id,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to broadcast ActionPendingEvent via WebSocket",
                    extra={"action_id": action["id"]},
                    exc_info=True,
                )

        return action

    async def approve_action(
        self,
        action_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Approve a pending action.

        Args:
            action_id: The action ID.
            user_id: The user's ID.

        Returns:
            Updated action dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("aria_action_queue")
            .update(
                {
                    "status": ActionStatus.APPROVED.value,
                    "approved_at": now,
                }
            )
            .eq("id", action_id)
            .eq("user_id", user_id)
            .eq("status", ActionStatus.PENDING.value)
            .execute()
        )

        if result.data:
            logger.info(
                "Action approved",
                extra={"action_id": action_id, "user_id": user_id},
            )
            return cast(dict[str, Any], result.data[0])

        logger.warning(
            "Action not found or not pending for approval",
            extra={"action_id": action_id},
        )
        return None

    async def reject_action(
        self,
        action_id: str,
        user_id: str,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Reject a pending action.

        Args:
            action_id: The action ID.
            user_id: The user's ID.
            reason: Optional rejection reason.

        Returns:
            Updated action dict, or None if not found.
        """
        update_data: dict[str, Any] = {
            "status": ActionStatus.REJECTED.value,
        }
        if reason:
            update_data["result"] = {"rejection_reason": reason}

        result = (
            self._db.table("aria_action_queue")
            .update(update_data)
            .eq("id", action_id)
            .eq("user_id", user_id)
            .eq("status", ActionStatus.PENDING.value)
            .execute()
        )

        if result.data:
            logger.info(
                "Action rejected",
                extra={"action_id": action_id, "user_id": user_id, "reason": reason},
            )
            return cast(dict[str, Any], result.data[0])

        logger.warning(
            "Action not found or not pending for rejection",
            extra={"action_id": action_id},
        )
        return None

    async def batch_approve(
        self,
        action_ids: list[str],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Approve multiple pending actions at once.

        Args:
            action_ids: List of action IDs to approve.
            user_id: The user's ID.

        Returns:
            List of updated action dicts.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("aria_action_queue")
            .update(
                {
                    "status": ActionStatus.APPROVED.value,
                    "approved_at": now,
                }
            )
            .in_("id", action_ids)
            .eq("user_id", user_id)
            .eq("status", ActionStatus.PENDING.value)
            .execute()
        )

        approved = cast(list[dict[str, Any]], result.data)
        logger.info(
            "Actions batch approved",
            extra={
                "user_id": user_id,
                "requested": len(action_ids),
                "approved": len(approved),
            },
        )
        return approved

    async def get_queue(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get the action queue for a user.

        Args:
            user_id: The user's ID.
            status: Optional status filter.
            limit: Maximum number of actions to return.

        Returns:
            List of action dicts ordered by created_at desc.
        """
        query = self._db.table("aria_action_queue").select("*").eq("user_id", user_id)

        if status:
            query = query.eq("status", status)

        result = query.order("created_at", desc=True).limit(limit).execute()

        actions = cast(list[dict[str, Any]], result.data)
        logger.info(
            "Action queue retrieved",
            extra={"user_id": user_id, "count": len(actions)},
        )
        return actions

    async def get_action(
        self,
        action_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Get a single action by ID.

        Args:
            action_id: The action ID.
            user_id: The user's ID.

        Returns:
            Action dict, or None if not found.
        """
        result = (
            self._db.table("aria_action_queue")
            .select("*")
            .eq("id", action_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result is None or result.data is None:
            logger.warning(
                "Action not found",
                extra={"action_id": action_id, "user_id": user_id},
            )
            return None

        return cast(dict[str, Any], result.data)

    async def execute_action(
        self,
        action_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Execute an approved action.

        Transitions from approved/auto_approved to executing, then completed.
        Actual execution is delegated to the appropriate agent.

        Args:
            action_id: The action ID.
            user_id: The user's ID.

        Returns:
            Updated action dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()

        # Mark as executing
        result = (
            self._db.table("aria_action_queue")
            .update({"status": ActionStatus.EXECUTING.value})
            .eq("id", action_id)
            .eq("user_id", user_id)
            .in_("status", [ActionStatus.APPROVED.value, ActionStatus.AUTO_APPROVED.value])
            .execute()
        )

        if not result.data:
            logger.warning(
                "Action not found or not approved for execution",
                extra={"action_id": action_id},
            )
            return None

        # Mark as completed (agent execution is delegated externally)
        completed_result = (
            self._db.table("aria_action_queue")
            .update(
                {
                    "status": ActionStatus.COMPLETED.value,
                    "completed_at": now,
                    "result": {"executed": True},
                }
            )
            .eq("id", action_id)
            .eq("user_id", user_id)
            .execute()
        )

        if completed_result.data:
            logger.info(
                "Action executed and completed",
                extra={"action_id": action_id},
            )
            return cast(dict[str, Any], completed_result.data[0])

        return None

    async def get_pending_count(self, user_id: str) -> int:
        """Get count of pending actions for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Number of pending actions.
        """
        result = (
            self._db.table("aria_action_queue")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("status", ActionStatus.PENDING.value)
            .execute()
        )

        return result.count or 0
