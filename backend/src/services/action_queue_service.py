"""Action queue service for ARIA (US-937).

This service handles:
- Submitting actions for approval or auto-execution (4-level trust model)
- Approving, rejecting, and batch-approving actions
- Querying the action queue with status filters
- Executing approved actions via ActionExecutionService
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.action_queue import ActionCreate, ActionStatus
from src.services.action_execution import (
    ActionExecutionService,
    action_type_to_category,
    get_action_execution_service,
    risk_level_to_score,
)
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


class ActionQueueService:
    """Manages ARIA's autonomous actions with trust-based approval workflow."""

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()
        self._activity_service = ActivityService()
        self._exec_svc: ActionExecutionService = get_action_execution_service()

    async def submit_action(
        self,
        user_id: str,
        data: ActionCreate,
    ) -> dict[str, Any]:
        """Submit an action routed through the 4-level trust × risk matrix.

        Execution modes:
        - AUTO_EXECUTE: Execute immediately, log in activity
        - EXECUTE_AND_NOTIFY: Execute with 5-min undo window
        - APPROVE_PLAN: Submit as pending, batch-approvable
        - APPROVE_EACH: Submit as pending, individual approval required

        Args:
            user_id: The user's ID.
            data: Action creation data.

        Returns:
            Created action dict.
        """
        # Determine execution mode from trust × risk
        category = action_type_to_category(data.action_type.value)
        risk_score = data.risk_score if data.risk_score is not None else risk_level_to_score(data.risk_level.value)
        mode = await self._exec_svc.determine_execution_mode(user_id, category, risk_score)

        # Determine initial status based on mode
        if mode in ("AUTO_EXECUTE", "EXECUTE_AND_NOTIFY"):
            initial_status = ActionStatus.AUTO_APPROVED.value
            approved_at = datetime.now(UTC).isoformat()
        else:
            initial_status = ActionStatus.PENDING.value
            approved_at = None

        # Insert action record
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
        if data.risk_score is not None:
            insert_data["risk_score"] = data.risk_score
        if data.task_characteristics is not None:
            insert_data["task_characteristics"] = data.task_characteristics
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
                "execution_mode": mode,
                "status": initial_status,
            },
        )

        # Log to activity feed
        try:
            await self._activity_service.record(
                user_id=user_id,
                agent=data.agent.value,
                activity_type="goal_updated",
                title=data.title,
                description=data.description or "",
                reasoning=data.reasoning or "",
                confidence=0.8,
                metadata={
                    "action_id": action["id"],
                    "action_type": data.action_type.value,
                    "risk_level": data.risk_level.value,
                    "execution_mode": mode,
                    "status": initial_status,
                },
            )
        except Exception:
            logger.warning(
                "Failed to log action activity",
                extra={"action_id": action["id"]},
            )

        # Route by execution mode
        if mode == "AUTO_EXECUTE":
            try:
                await self._exec_svc.execute_action(action["id"], user_id, action)
            except Exception:
                logger.warning(
                    "Auto-execute failed, action remains auto_approved",
                    extra={"action_id": action["id"]},
                    exc_info=True,
                )

        elif mode == "EXECUTE_AND_NOTIFY":
            try:
                await self._exec_svc.execute_with_undo_window(action["id"], user_id, action)
            except Exception:
                logger.warning(
                    "Execute-and-notify failed",
                    extra={"action_id": action["id"]},
                    exc_info=True,
                )

        else:
            # APPROVE_PLAN or APPROVE_EACH — broadcast pending event
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
        """Reject a pending action and update trust (override).

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
            action = cast(dict[str, Any], result.data[0])
            logger.info(
                "Action rejected",
                extra={"action_id": action_id, "user_id": user_id, "reason": reason},
            )
            # Update trust: rejection = user override
            try:
                category = action_type_to_category(action.get("action_type", ""))
                await self._exec_svc._trust.update_on_override(user_id, category)
            except Exception:
                logger.warning(
                    "Failed to update trust on rejection",
                    extra={"action_id": action_id},
                    exc_info=True,
                )
            return action

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
        try:
            query = self._db.table("aria_action_queue").select("*").eq("user_id", user_id)

            if status:
                query = query.eq("status", status)

            result = query.order("created_at", desc=True).limit(limit).execute()

            actions = cast(list[dict[str, Any]], result.data or [])
            logger.info(
                "Action queue retrieved",
                extra={"user_id": user_id, "count": len(actions)},
            )
            return actions
        except Exception:
            logger.warning(
                "Failed to fetch action queue, returning empty list",
                extra={"user_id": user_id},
                exc_info=True,
            )
            return []

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
        """Execute an approved action via ActionExecutionService.

        Transitions from approved/auto_approved to executing, then completed.
        Trust is updated on success by the execution service.

        Args:
            action_id: The action ID.
            user_id: The user's ID.

        Returns:
            Updated action dict, or None if not found/approved.
        """
        # Fetch the action to pass full record to execution service
        action = await self.get_action(action_id, user_id)
        if not action:
            return None

        status = action.get("status")
        if status not in (ActionStatus.APPROVED.value, ActionStatus.AUTO_APPROVED.value):
            logger.warning(
                "Action not approved for execution",
                extra={"action_id": action_id, "status": status},
            )
            return None

        await self._exec_svc.execute_action(action_id, user_id, action)

        # Re-fetch to return updated record
        return await self.get_action(action_id, user_id)

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
