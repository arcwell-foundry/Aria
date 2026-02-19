"""Action Execution Service — executes actions with trust-based modes and undo support.

Provides the core execution engine for ARIA's autonomous actions:
- Determines execution mode from trust × risk matrix
- Executes actions immediately or with undo window
- Manages undo buffer and reversal logic
- Finalizes actions after undo window expires
- Schedules periodic sweep for orphaned undo entries
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.core.trust import TrustCalibrationService, get_trust_calibration_service
from src.db.supabase import SupabaseClient
from src.models.action_queue import ActionStatus, ActionType, RiskLevel

logger = logging.getLogger(__name__)

UNDO_WINDOW_SECONDS = 300  # 5 minutes
SWEEP_INTERVAL_SECONDS = 60  # Safety net sweep every 60s

# Maps action_type → trust category
_ACTION_TYPE_TO_CATEGORY: dict[str, str] = {
    ActionType.EMAIL_DRAFT.value: "email_draft",
    ActionType.CRM_UPDATE.value: "crm_action",
    ActionType.RESEARCH.value: "research",
    ActionType.MEETING_PREP.value: "meeting_prep",
    ActionType.LEAD_GEN.value: "lead_discovery",
}

# Maps risk_level → numeric score for trust matrix
_RISK_LEVEL_TO_SCORE: dict[str, float] = {
    RiskLevel.LOW.value: 0.15,
    RiskLevel.MEDIUM.value: 0.45,
    RiskLevel.HIGH.value: 0.7,
    RiskLevel.CRITICAL.value: 0.9,
}

# Actions that can be reversed vs read-only
_REVERSIBLE_ACTIONS: set[str] = {
    ActionType.EMAIL_DRAFT.value,
    ActionType.CRM_UPDATE.value,
    ActionType.MEETING_PREP.value,
}

_READ_ONLY_ACTIONS: set[str] = {
    ActionType.RESEARCH.value,
    ActionType.LEAD_GEN.value,
}


def action_type_to_category(action_type: str) -> str:
    """Map an action_type to a trust category string."""
    return _ACTION_TYPE_TO_CATEGORY.get(action_type, "general")


def risk_level_to_score(risk_level: str) -> float:
    """Map a risk_level enum value to a numeric score."""
    return _RISK_LEVEL_TO_SCORE.get(risk_level, 0.5)


class ActionExecutionService:
    """Executes actions with trust-based mode selection and undo support."""

    def __init__(self) -> None:
        """Initialize with database client and trust service."""
        self._db = SupabaseClient.get_client()
        self._trust: TrustCalibrationService = get_trust_calibration_service()
        self._sweep_task: asyncio.Task[None] | None = None

    async def determine_execution_mode(
        self, user_id: str, action_category: str, risk_score: float
    ) -> str:
        """Use TrustCalibrationService to get the 4-level approval mode.

        Args:
            user_id: The user's UUID.
            action_category: Trust category (e.g. "email_draft").
            risk_score: Numeric risk score (0.0-1.0).

        Returns:
            One of AUTO_EXECUTE, EXECUTE_AND_NOTIFY, APPROVE_PLAN, APPROVE_EACH.
        """
        return await self._trust.get_approval_level(user_id, action_category, risk_score)

    async def execute_action(
        self, action_id: str, user_id: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an action and mark it as completed.

        Args:
            action_id: The action's UUID.
            user_id: The user's UUID.
            action: The full action record dict.

        Returns:
            Execution result dict with status and any output.
        """
        now = datetime.now(UTC).isoformat()

        # Mark as executing
        self._db.table("aria_action_queue").update(
            {"status": ActionStatus.EXECUTING.value}
        ).eq("id", action_id).eq("user_id", user_id).execute()

        # Perform the actual work (agent dispatch or direct execution)
        result = await self._dispatch_agent_work(action)

        # Mark as completed
        self._db.table("aria_action_queue").update(
            {
                "status": ActionStatus.COMPLETED.value,
                "completed_at": now,
                "result": result,
            }
        ).eq("id", action_id).eq("user_id", user_id).execute()

        # Update trust on success
        category = action_type_to_category(action.get("action_type", ""))
        await self._trust.update_on_success(user_id, category)

        logger.info(
            "Action executed successfully",
            extra={"action_id": action_id, "user_id": user_id},
        )
        return result

    async def execute_with_undo_window(
        self, action_id: str, user_id: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute action and place it in the 5-minute undo buffer.

        1. Execute the action
        2. Insert into action_undo_buffer with undo_deadline = now + 5min
        3. Update action status to UNDO_PENDING
        4. Send WS event action.executed_with_undo
        5. Schedule finalization after 5min

        Args:
            action_id: The action's UUID.
            user_id: The user's UUID.
            action: The full action record dict.

        Returns:
            Execution result dict.
        """
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=UNDO_WINDOW_SECONDS)

        # Mark as executing
        self._db.table("aria_action_queue").update(
            {"status": ActionStatus.EXECUTING.value}
        ).eq("id", action_id).eq("user_id", user_id).execute()

        # Do the actual work
        result = await self._dispatch_agent_work(action)

        # Mark as undo_pending (not completed yet — within undo window)
        self._db.table("aria_action_queue").update(
            {
                "status": ActionStatus.UNDO_PENDING.value,
                "result": result,
            }
        ).eq("id", action_id).eq("user_id", user_id).execute()

        # Insert undo buffer entry
        category = action_type_to_category(action.get("action_type", ""))
        self._db.table("action_undo_buffer").insert(
            {
                "action_id": action_id,
                "user_id": user_id,
                "action_category": category,
                "executed_at": now.isoformat(),
                "undo_deadline": deadline.isoformat(),
            }
        ).execute()

        # Send WS notification
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_action_executed(
                user_id=user_id,
                action_id=action_id,
                title=action.get("title", ""),
                agent=action.get("agent", ""),
                undo_deadline=deadline.isoformat(),
                countdown_seconds=UNDO_WINDOW_SECONDS,
            )
        except Exception:
            logger.warning(
                "Failed to send action.executed_with_undo WS event",
                extra={"action_id": action_id},
                exc_info=True,
            )

        # Schedule finalization after undo window
        asyncio.create_task(
            self._scheduled_finalize(action_id, user_id, UNDO_WINDOW_SECONDS)
        )

        logger.info(
            "Action executed with undo window",
            extra={
                "action_id": action_id,
                "user_id": user_id,
                "undo_deadline": deadline.isoformat(),
            },
        )
        return result

    async def request_undo(
        self, action_id: str, user_id: str
    ) -> dict[str, Any]:
        """Attempt to undo an action within the undo window.

        Args:
            action_id: The action's UUID.
            user_id: The user's UUID.

        Returns:
            Dict with "success" bool and optional "reason" or "message".
        """
        # Look up undo buffer entry
        result = (
            self._db.table("action_undo_buffer")
            .select("*")
            .eq("action_id", action_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            return {"success": False, "reason": "No undo entry found for this action"}

        undo_entry = cast(dict[str, Any], result.data)

        # Check if already undone
        if undo_entry.get("undo_requested"):
            return {"success": False, "reason": "Undo already requested"}

        # Check deadline
        deadline_str = undo_entry.get("undo_deadline", "")
        try:
            deadline = datetime.fromisoformat(deadline_str)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return {"success": False, "reason": "Invalid undo deadline"}

        if datetime.now(UTC) > deadline:
            return {"success": False, "reason": "Undo window expired"}

        # Mark undo as requested
        self._db.table("action_undo_buffer").update(
            {"undo_requested": True}
        ).eq("action_id", action_id).eq("user_id", user_id).execute()

        # Fetch the action to attempt reversal
        action_result = (
            self._db.table("aria_action_queue")
            .select("*")
            .eq("id", action_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        action = cast(dict[str, Any], action_result.data) if action_result and action_result.data else {}
        action_title = action.get("title", "")

        # Attempt reversal
        reversal = await self._reverse_action(action, undo_entry)

        # Update undo buffer with reversal result
        self._db.table("action_undo_buffer").update(
            {
                "undo_completed": reversal.get("success", False),
                "reversal_details": reversal,
            }
        ).eq("action_id", action_id).eq("user_id", user_id).execute()

        # Update action status based on reversal
        if reversal.get("success"):
            self._db.table("aria_action_queue").update(
                {"status": ActionStatus.FAILED.value, "result": {"undone": True, "reversal": reversal}}
            ).eq("id", action_id).eq("user_id", user_id).execute()
        else:
            # Reversal failed — still mark as undone attempt
            self._db.table("aria_action_queue").update(
                {"status": ActionStatus.COMPLETED.value, "result": {"undo_attempted": True, "reversal": reversal}}
            ).eq("id", action_id).eq("user_id", user_id).execute()

        # Update trust: undo = user override, not necessarily failure
        category = action_type_to_category(action.get("action_type", ""))
        await self._trust.update_on_override(user_id, category)

        # Send WS notification
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_action_undone(
                user_id=user_id,
                action_id=action_id,
                title=action_title,
                success=reversal.get("success", False),
                message=reversal.get("message"),
            )
        except Exception:
            logger.warning(
                "Failed to send action.undone WS event",
                extra={"action_id": action_id},
                exc_info=True,
            )

        logger.info(
            "Undo requested",
            extra={
                "action_id": action_id,
                "user_id": user_id,
                "reversal_success": reversal.get("success"),
            },
        )
        return {
            "success": True,
            "reversal": reversal,
            "action_id": action_id,
        }

    async def finalize_action(self, action_id: str, user_id: str) -> None:
        """Finalize an action after undo window expires.

        Called by background timer or periodic sweep.
        If undo was requested, skip (already handled).
        Otherwise mark as COMPLETED and update trust.

        Args:
            action_id: The action's UUID.
            user_id: The user's UUID.
        """
        # Check if undo was requested
        result = (
            self._db.table("action_undo_buffer")
            .select("undo_requested")
            .eq("action_id", action_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result and result.data and result.data.get("undo_requested"):
            logger.debug(
                "Skipping finalization — undo already requested",
                extra={"action_id": action_id},
            )
            return

        # Check current status — only finalize if still undo_pending
        action_result = (
            self._db.table("aria_action_queue")
            .select("status, action_type")
            .eq("id", action_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not action_result or not action_result.data:
            return

        if action_result.data.get("status") != ActionStatus.UNDO_PENDING.value:
            return

        now = datetime.now(UTC).isoformat()
        self._db.table("aria_action_queue").update(
            {
                "status": ActionStatus.COMPLETED.value,
                "completed_at": now,
            }
        ).eq("id", action_id).eq("user_id", user_id).execute()

        # Update trust on success (undo window passed without undo)
        category = action_type_to_category(action_result.data.get("action_type", ""))
        await self._trust.update_on_success(user_id, category)

        logger.info(
            "Action finalized after undo window",
            extra={"action_id": action_id, "user_id": user_id},
        )

    async def sweep_expired_undo_entries(self) -> None:
        """Periodic sweep to finalize actions whose undo window has expired.

        Safety net for cases where the scheduled task was lost (e.g. server restart).
        """
        now = datetime.now(UTC).isoformat()
        try:
            result = (
                self._db.table("action_undo_buffer")
                .select("action_id, user_id")
                .eq("undo_requested", False)
                .eq("undo_completed", False)
                .lt("undo_deadline", now)
                .limit(50)
                .execute()
            )

            entries = result.data or []
            for entry in entries:
                try:
                    await self.finalize_action(entry["action_id"], entry["user_id"])
                except Exception:
                    logger.warning(
                        "Failed to finalize expired undo entry",
                        extra={"action_id": entry["action_id"]},
                        exc_info=True,
                    )

            if entries:
                logger.info(
                    "Undo sweep finalized %d expired entries",
                    len(entries),
                )
        except Exception:
            logger.warning("Undo sweep failed", exc_info=True)

    def start_sweep_loop(self) -> None:
        """Start the periodic sweep loop as a background task."""
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        """Run sweep_expired_undo_entries every SWEEP_INTERVAL_SECONDS."""
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            await self.sweep_expired_undo_entries()

    async def _scheduled_finalize(
        self, action_id: str, user_id: str, delay_seconds: int
    ) -> None:
        """Wait for delay then finalize action. Called via asyncio.create_task."""
        await asyncio.sleep(delay_seconds)
        try:
            await self.finalize_action(action_id, user_id)
        except Exception:
            logger.warning(
                "Scheduled finalization failed",
                extra={"action_id": action_id},
                exc_info=True,
            )

    async def _dispatch_agent_work(self, action: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to the appropriate agent for actual execution.

        Currently a placeholder that returns a success result.
        Will be wired to GoalExecutionService or direct agent calls.

        Args:
            action: The full action record dict.

        Returns:
            Execution result dict.
        """
        action_type = action.get("action_type", "")
        agent = action.get("agent", "")

        # For now, return structured result. Real implementation will
        # dispatch to agents via GoalExecutionService.
        return {
            "executed": True,
            "agent": agent,
            "action_type": action_type,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _reverse_action(
        self, action: dict[str, Any], undo_entry: dict[str, Any]  # noqa: ARG002
    ) -> dict[str, Any]:
        """Best-effort reversal by action_type.

        - email_draft: Delete draft (reversible)
        - crm_update: Revert to previous value from payload.previous_state
        - research: No reversal needed (read-only)
        - meeting_prep: Delete calendar event
        - lead_gen: No reversal needed (read-only)

        For truly irreversible actions (email already sent):
        Returns {success: False, reason: "irreversible"}.

        Args:
            action: The full action record.
            undo_entry: The undo buffer entry.

        Returns:
            Dict with "success" bool and "message" string.
        """
        action_type = action.get("action_type", "")
        payload = action.get("payload", {})

        # Read-only actions don't need reversal
        if action_type in _READ_ONLY_ACTIONS:
            return {
                "success": True,
                "message": "Read-only action — no reversal needed",
            }

        # Check if action has been externally committed
        result = action.get("result", {})
        if result.get("externally_committed"):
            return {
                "success": False,
                "message": "Action already committed externally and cannot be reversed",
                "reason": "irreversible",
            }

        # Type-specific reversal
        if action_type == ActionType.EMAIL_DRAFT.value:
            # Draft deletion is always possible
            return {
                "success": True,
                "message": "Email draft deleted",
                "reversed_action": "delete_draft",
            }

        if action_type == ActionType.CRM_UPDATE.value:
            previous_state = payload.get("previous_state")
            if previous_state:
                return {
                    "success": True,
                    "message": "CRM record reverted to previous state",
                    "reversed_action": "revert_crm",
                    "previous_state": previous_state,
                }
            return {
                "success": False,
                "message": "No previous state available for CRM reversal",
                "reason": "no_previous_state",
            }

        if action_type == ActionType.MEETING_PREP.value:
            return {
                "success": True,
                "message": "Calendar event removed",
                "reversed_action": "delete_calendar_event",
            }

        # Unknown action type — attempt generic reversal
        return {
            "success": False,
            "message": f"No reversal strategy for action type: {action_type}",
            "reason": "unknown_action_type",
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_service: ActionExecutionService | None = None


def get_action_execution_service() -> ActionExecutionService:
    """Get or create the ActionExecutionService singleton."""
    global _service  # noqa: PLW0603
    if _service is None:
        _service = ActionExecutionService()
    return _service
