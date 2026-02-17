"""Autonomy calibration service for ARIA.

Tracks and manages ARIA's autonomy level per user on a 1-5 scale:
- Level 1 (New): Ask before every action
- Level 2 (Learning): Ask before high-risk actions
- Level 3 (Trusted): Auto-execute low-risk, ask for medium+
- Level 4 (Autonomous): Auto-execute medium-risk, ask for high
- Level 5 (Full Trust): Auto-execute everything, notify after

Integrates with aria_action_queue for tracking and user_settings for storage.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Action type -> risk level mappings
_LOW_RISK_ACTIONS = frozenset({
    "research",
    "signal_detection",
    "briefing_generation",
})

_MEDIUM_RISK_ACTIONS = frozenset({
    "email_draft",
    "meeting_prep",
    "lead_scoring",
    "lead_gen",
})

_HIGH_RISK_ACTIONS = frozenset({
    "email_send",
    "crm_update",
    "calendar_modify",
})

_CRITICAL_RISK_ACTIONS = frozenset({
    "financial_action",
    "data_deletion",
})

# Autonomy level -> maximum auto-executable risk level
# Maps each autonomy level to the set of risk levels it can auto-execute.
# Critical is NEVER auto-executed regardless of level.
_LEVEL_PERMISSIONS: dict[int, set[str]] = {
    1: set(),                          # Ask before everything
    2: {"low"},                        # Auto-execute low only
    3: {"low"},                        # Auto-execute low, ask medium+
    4: {"low", "medium"},              # Auto-execute low+medium, ask high
    5: {"low", "medium", "high"},      # Auto-execute everything except critical
}


class AutonomyCalibrationService:
    """Manages ARIA's autonomy calibration per user."""

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()

    def classify_action_risk(
        self,
        action_type: str,
        context: dict[str, Any],
    ) -> str:
        """Classify an action's risk level.

        Args:
            action_type: The type of action to classify.
            context: Additional context about the action.

        Returns:
            Risk level string: "low", "medium", "high", or "critical".
        """
        if action_type in _LOW_RISK_ACTIONS:
            return "low"
        if action_type in _MEDIUM_RISK_ACTIONS:
            return "medium"
        if action_type in _HIGH_RISK_ACTIONS:
            return "high"
        if action_type in _CRITICAL_RISK_ACTIONS:
            return "critical"

        # Unknown actions default to high for safety
        logger.warning(
            "Unknown action type, defaulting to high risk",
            extra={"action_type": action_type, "context": context},
        )
        return "high"

    async def should_auto_execute(
        self,
        user_id: str,
        action_type: str,
        context: dict[str, Any],
    ) -> bool:
        """Determine whether an action should auto-execute.

        Checks the user's autonomy level against the action's risk level.
        Critical actions always require approval regardless of level.

        Args:
            user_id: The user's ID.
            action_type: The type of action.
            context: Additional action context.

        Returns:
            True if the action should auto-execute, False if approval needed.
        """
        risk_level = self.classify_action_risk(action_type, context)

        # Critical actions always require approval
        if risk_level == "critical":
            auto_execute = False
        else:
            autonomy_level = await self._get_autonomy_level(user_id)
            allowed_risks = _LEVEL_PERMISSIONS.get(autonomy_level, set())
            auto_execute = risk_level in allowed_risks

        # Log the decision
        try:
            autonomy_level_for_log = await self._get_autonomy_level(user_id)
            self._db.table("autonomy_decisions").insert({
                "user_id": user_id,
                "action_type": action_type,
                "risk_level": risk_level,
                "autonomy_level": autonomy_level_for_log,
                "auto_execute": auto_execute,
                "decided_at": datetime.now(UTC).isoformat(),
            }).execute()
        except Exception:
            logger.warning(
                "Failed to log autonomy decision",
                extra={"user_id": user_id, "action_type": action_type},
            )

        logger.info(
            "Auto-execute decision",
            extra={
                "user_id": user_id,
                "action_type": action_type,
                "risk_level": risk_level,
                "auto_execute": auto_execute,
            },
        )

        return auto_execute

    async def calculate_autonomy_level(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Calculate the recommended autonomy level for a user.

        Based on:
        - Account age (days since first login)
        - Total ARIA actions approved vs rejected
        - Error rate (actions that failed)
        - User feedback ratings
        - Email draft approval rate

        Args:
            user_id: The user's ID.

        Returns:
            Dict with 'level' (int 1-5) and 'reasoning' (str).
        """
        # Gather signals
        account_age_days = await self._get_account_age_days(user_id)
        action_stats = await self._get_action_stats(user_id)
        feedback_stats = await self._get_feedback_stats(user_id)
        draft_approval_rate = await self._get_draft_approval_rate(user_id)

        # Compute individual scores (each 0.0 - 1.0)
        age_score = self._compute_age_score(account_age_days)
        approval_score = self._compute_approval_score(action_stats)
        error_score = self._compute_error_score(action_stats)
        feedback_score = self._compute_feedback_score(feedback_stats)
        draft_score = self._compute_draft_score(draft_approval_rate)

        # Weighted average
        weights = {
            "age": 0.15,
            "approval": 0.30,
            "error": 0.20,
            "feedback": 0.15,
            "draft": 0.20,
        }

        composite = (
            age_score * weights["age"]
            + approval_score * weights["approval"]
            + error_score * weights["error"]
            + feedback_score * weights["feedback"]
            + draft_score * weights["draft"]
        )

        # Map composite score to level 1-5
        if composite >= 0.85:
            level = 5
        elif composite >= 0.70:
            level = 4
        elif composite >= 0.50:
            level = 3
        elif composite >= 0.30:
            level = 2
        else:
            level = 1

        reasoning = (
            f"Account age: {account_age_days} days (score: {age_score:.2f}). "
            f"Action approval rate: {approval_score:.2f}. "
            f"Error rate score: {error_score:.2f}. "
            f"Feedback score: {feedback_score:.2f}. "
            f"Draft approval score: {draft_score:.2f}. "
            f"Composite: {composite:.2f} -> Level {level}."
        )

        logger.info(
            "Autonomy level calculated",
            extra={
                "user_id": user_id,
                "level": level,
                "composite": composite,
            },
        )

        return {"level": level, "reasoning": reasoning}

    async def record_action_outcome(
        self,
        action_id: str,
        outcome: str,
    ) -> dict[str, Any] | None:
        """Record the outcome of an action for calibration data.

        Args:
            action_id: The action ID.
            outcome: The outcome string (e.g., "success", "failure").

        Returns:
            Updated action dict, or None if not found.
        """
        result = (
            self._db.table("aria_action_queue")
            .update({
                "outcome": outcome,
                "outcome_recorded_at": datetime.now(UTC).isoformat(),
            })
            .eq("id", action_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Action outcome recorded",
                extra={"action_id": action_id, "outcome": outcome},
            )
            return cast(dict[str, Any], result.data[0])

        logger.warning(
            "Action not found for outcome recording",
            extra={"action_id": action_id},
        )
        return None

    # --- Private helpers ---

    async def _get_autonomy_level(self, user_id: str) -> int:
        """Fetch the stored autonomy level from user_settings.

        Args:
            user_id: The user's ID.

        Returns:
            Autonomy level (1-5), defaults to 1.
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if result.data:
                preferences = result.data.get("preferences", {})
                return int(preferences.get("autonomy_level", 1))
        except Exception:
            logger.warning(
                "Failed to fetch autonomy level, defaulting to 1",
                extra={"user_id": user_id},
            )
        return 1

    async def _get_account_age_days(self, user_id: str) -> int:
        """Get the number of days since account creation.

        Args:
            user_id: The user's ID.

        Returns:
            Number of days since account creation.
        """
        try:
            result = (
                self._db.table("user_profiles")
                .select("created_at")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if result.data and result.data.get("created_at"):
                created_str = result.data["created_at"]
                created_at = datetime.fromisoformat(created_str)
                delta = datetime.now(UTC) - created_at
                return max(0, delta.days)
        except Exception:
            logger.warning(
                "Failed to fetch account age",
                extra={"user_id": user_id},
            )
        return 0

    async def _get_action_stats(
        self,
        user_id: str,
    ) -> dict[str, int]:
        """Get action approval/rejection/failure statistics.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with 'total', 'completed', 'rejected', 'failed' counts.
        """
        try:
            result = (
                self._db.table("aria_action_queue")
                .select("status")
                .eq("user_id", user_id)
                .execute()
            )
            records = result.data or []
            total = len(records)
            completed = sum(
                1 for r in records if r.get("status") == "completed"
            )
            rejected = sum(
                1 for r in records if r.get("status") == "rejected"
            )
            failed = sum(
                1 for r in records if r.get("status") == "failed"
            )
            return {
                "total": total,
                "completed": completed,
                "rejected": rejected,
                "failed": failed,
            }
        except Exception:
            logger.warning(
                "Failed to fetch action stats",
                extra={"user_id": user_id},
            )
            return {"total": 0, "completed": 0, "rejected": 0, "failed": 0}

    async def _get_feedback_stats(
        self,
        user_id: str,
    ) -> dict[str, int]:
        """Get user feedback statistics.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with 'total', 'positive', 'negative' counts.
        """
        try:
            result = (
                self._db.table("feedback")
                .select("rating")
                .eq("user_id", user_id)
                .eq("type", "response")
                .execute()
            )
            records = result.data or []
            total = len(records)
            positive = sum(
                1 for r in records if r.get("rating") == "up"
            )
            negative = sum(
                1 for r in records if r.get("rating") == "down"
            )
            return {"total": total, "positive": positive, "negative": negative}
        except Exception:
            logger.warning(
                "Failed to fetch feedback stats",
                extra={"user_id": user_id},
            )
            return {"total": 0, "positive": 0, "negative": 0}

    async def _get_draft_approval_rate(self, user_id: str) -> float:
        """Get email draft approval rate.

        Args:
            user_id: The user's ID.

        Returns:
            Approval rate as float 0.0-1.0, or 0.0 if no drafts.
        """
        try:
            result = (
                self._db.table("email_drafts")
                .select("user_action")
                .eq("user_id", user_id)
                .neq("user_action", "pending")
                .execute()
            )
            records = result.data or []
            if not records:
                return 0.0
            approved = sum(
                1 for r in records if r.get("user_action") == "approved"
            )
            return approved / len(records)
        except Exception:
            logger.warning(
                "Failed to fetch draft approval rate",
                extra={"user_id": user_id},
            )
            return 0.0

    @staticmethod
    def _compute_age_score(days: int) -> float:
        """Compute score from account age.

        0 days -> 0.0, 180+ days -> 1.0, linear in between.
        """
        return min(1.0, days / 180.0)

    @staticmethod
    def _compute_approval_score(stats: dict[str, int]) -> float:
        """Compute score from action approval rate.

        Returns ratio of completed to total (excluding failed).
        """
        total = stats["total"]
        if total == 0:
            return 0.0
        completed = stats["completed"]
        return completed / total

    @staticmethod
    def _compute_error_score(stats: dict[str, int]) -> float:
        """Compute score from error rate (inverted: low errors = high score).

        0 failures -> 1.0, high failure rate -> 0.0.
        """
        total = stats["total"]
        if total == 0:
            return 0.5  # Neutral when no data
        failed = stats["failed"]
        error_rate = failed / total
        return max(0.0, 1.0 - (error_rate * 2.0))

    @staticmethod
    def _compute_feedback_score(stats: dict[str, int]) -> float:
        """Compute score from user feedback.

        Returns ratio of positive to total feedback.
        """
        total = stats["total"]
        if total == 0:
            return 0.5  # Neutral when no data
        return stats["positive"] / total

    @staticmethod
    def _compute_draft_score(approval_rate: float) -> float:
        """Compute score from draft approval rate.

        Direct pass-through since it's already 0.0-1.0.
        Returns 0.5 (neutral) if no draft data (rate == 0.0 with no drafts).
        """
        return approval_rate if approval_rate > 0.0 else 0.5


# Singleton instance
_autonomy_calibration_service: AutonomyCalibrationService | None = None


def get_autonomy_calibration_service() -> AutonomyCalibrationService:
    """Get or create the AutonomyCalibrationService singleton.

    Returns:
        The AutonomyCalibrationService singleton instance.
    """
    global _autonomy_calibration_service
    if _autonomy_calibration_service is None:
        _autonomy_calibration_service = AutonomyCalibrationService()
    return _autonomy_calibration_service
