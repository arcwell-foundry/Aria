"""Trust Calibration Service — per-action-category trust tracking.

Tracks trust scores per (user, action_category) pair. Trust starts at 0.3,
increases logarithmically on success, drops sharply on failure, and combines
with task risk_score to determine approval levels.

Trust update formulas:
  - Success: score + 0.02 * (1.0 - score)   (logarithmic ceiling approach)
  - Failure: score * 0.7                      (sharp 30% drop)
  - Override: score - 0.05                    (fixed penalty)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TRUST_SCORE: float = 0.3
SUCCESS_INCREMENT_FACTOR: float = 0.02  # +0.02 * (1 - current)
FAILURE_DECAY_FACTOR: float = 0.7  # score * 0.7
OVERRIDE_PENALTY: float = 0.05  # score - 0.05

# Approval levels (match TaskCharacteristics constants)
AUTO_EXECUTE = "AUTO_EXECUTE"
EXECUTE_AND_NOTIFY = "EXECUTE_AND_NOTIFY"
APPROVE_PLAN = "APPROVE_PLAN"
APPROVE_EACH = "APPROVE_EACH"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TrustProfile:
    """Trust data for a single (user, action_category) pair."""

    user_id: str
    action_category: str
    trust_score: float = DEFAULT_TRUST_SCORE
    successful_actions: int = 0
    failed_actions: int = 0
    override_count: int = 0
    last_failure_at: datetime | None = None
    last_override_at: datetime | None = None

    @property
    def total_actions(self) -> int:
        """Total number of tracked actions."""
        return self.successful_actions + self.failed_actions

    @property
    def failure_rate(self) -> float:
        """Failure rate as a fraction (0.0–1.0). Returns 0.0 if no actions."""
        if self.total_actions == 0:
            return 0.0
        return self.failed_actions / self.total_actions


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TrustCalibrationService:
    """Per-action-category trust scoring and approval-level computation."""

    async def get_trust_score(self, user_id: str, action_category: str) -> float:
        """Get the current trust score for a user + action category.

        Returns DEFAULT_TRUST_SCORE (0.3) when no row exists or on DB error
        (fail-open).

        Args:
            user_id: The user's UUID.
            action_category: The action category (e.g. "email_send").

        Returns:
            Trust score between 0.0 and 1.0.
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("user_trust_profiles")
                .select("trust_score")
                .eq("user_id", user_id)
                .eq("action_category", action_category)
                .maybe_single()
                .execute()
            )
            if response.data:
                return float(response.data["trust_score"])
        except Exception:
            logger.exception(
                "Failed to fetch trust score for user %s category %s",
                user_id,
                action_category,
            )
        return DEFAULT_TRUST_SCORE

    async def get_trust_profile(self, user_id: str, action_category: str) -> TrustProfile:
        """Get the full trust profile for a user + action category.

        Returns a default TrustProfile when no row exists or on DB error.

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            TrustProfile with current data or defaults.
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("user_trust_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("action_category", action_category)
                .maybe_single()
                .execute()
            )
            if response.data:
                return TrustProfile(
                    user_id=response.data["user_id"],
                    action_category=response.data["action_category"],
                    trust_score=float(response.data["trust_score"]),
                    successful_actions=int(response.data["successful_actions"]),
                    failed_actions=int(response.data["failed_actions"]),
                    override_count=int(response.data["override_count"]),
                    last_failure_at=response.data.get("last_failure_at"),
                    last_override_at=response.data.get("last_override_at"),
                )
        except Exception:
            logger.exception(
                "Failed to fetch trust profile for user %s category %s",
                user_id,
                action_category,
            )
        return TrustProfile(user_id=user_id, action_category=action_category)

    async def get_all_profiles(self, user_id: str) -> list[TrustProfile]:
        """Get all trust profiles for a user across all action categories.

        Args:
            user_id: The user's UUID.

        Returns:
            List of TrustProfile instances (empty on error or no data).
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            response = (
                client.table("user_trust_profiles")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )
            if response.data:
                return [
                    TrustProfile(
                        user_id=row["user_id"],
                        action_category=row["action_category"],
                        trust_score=float(row["trust_score"]),
                        successful_actions=int(row["successful_actions"]),
                        failed_actions=int(row["failed_actions"]),
                        override_count=int(row["override_count"]),
                        last_failure_at=row.get("last_failure_at"),
                        last_override_at=row.get("last_override_at"),
                    )
                    for row in response.data
                ]
        except Exception:
            logger.exception("Failed to fetch all trust profiles for user %s", user_id)
        return []

    async def get_trust_history(
        self, user_id: str, category: str | None = None, days: int = 30
    ) -> list[dict]:
        """Get trust score change history for a user.

        Args:
            user_id: The user's UUID.
            category: Optional action category filter.
            days: Number of days of history to return (default 30).

        Returns:
            List of history dicts with recorded_at, trust_score, change_type,
            action_category. Empty list on error.
        """
        try:
            from datetime import timedelta
            from datetime import timezone as tz

            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            cutoff = (datetime.now(tz.utc) - timedelta(days=days)).isoformat()
            query = (
                client.table("trust_score_history")
                .select("recorded_at, trust_score, change_type, action_category")
                .eq("user_id", user_id)
            )
            if category:
                query = query.eq("action_category", category)
            response = query.gte("recorded_at", cutoff).order("recorded_at").limit(500).execute()
            return response.data or []
        except Exception:
            logger.exception("Failed to fetch trust history for user %s", user_id)
        return []

    async def update_on_success(self, user_id: str, action_category: str) -> float:
        """Record a successful action and increase trust.

        Formula: new_score = min(1.0, current + 0.02 * (1.0 - current))

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            The new trust score after the update.
        """
        current = await self.get_trust_score(user_id, action_category)
        new_score = min(1.0, current + SUCCESS_INCREMENT_FACTOR * (1.0 - current))
        await self._call_update_rpc(
            user_id=user_id,
            action_category=action_category,
            new_score=new_score,
            success_delta=1,
        )
        await self._record_history(user_id, action_category, new_score, "success")
        return new_score

    async def update_on_failure(self, user_id: str, action_category: str) -> float:
        """Record a failed action and decrease trust.

        Formula: new_score = max(0.0, current * 0.7)

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            The new trust score after the update.
        """
        current = await self.get_trust_score(user_id, action_category)
        new_score = max(0.0, current * FAILURE_DECAY_FACTOR)
        await self._call_update_rpc(
            user_id=user_id,
            action_category=action_category,
            new_score=new_score,
            failure_delta=1,
            set_last_failure=True,
        )
        await self._record_history(user_id, action_category, new_score, "failure")
        return new_score

    async def update_on_override(self, user_id: str, action_category: str) -> float:
        """Record a user override and decrease trust.

        Formula: new_score = max(0.0, current - 0.05)

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            The new trust score after the update.
        """
        current = await self.get_trust_score(user_id, action_category)
        new_score = max(0.0, current - OVERRIDE_PENALTY)
        await self._call_update_rpc(
            user_id=user_id,
            action_category=action_category,
            new_score=new_score,
            override_delta=1,
            set_last_override=True,
        )
        await self._record_history(user_id, action_category, new_score, "override")
        return new_score

    async def get_approval_level(
        self, user_id: str, action_category: str, risk_score: float
    ) -> str:
        """Determine the approval level for a task based on trust and risk.

        Approval matrix:

        | Trust \\ Risk  | Low (<0.3) | Medium (0.3-0.6) | High (>=0.6) |
        |---------------|------------|-------------------|--------------|
        | High (>0.8)   | AUTO       | NOTIFY            | APPROVE_PLAN |
        | Med (0.4-0.8) | NOTIFY     | APPROVE_PLAN      | APPROVE_EACH |
        | Low (<=0.4)   | APPROVE_PLAN | APPROVE_EACH   | APPROVE_EACH |

        Args:
            user_id: The user's UUID.
            action_category: The action category.
            risk_score: Task risk score (0.0-1.0).

        Returns:
            One of AUTO_EXECUTE, EXECUTE_AND_NOTIFY, APPROVE_PLAN, APPROVE_EACH.
        """
        trust = await self.get_trust_score(user_id, action_category)
        return self._compute_approval_level(trust, risk_score)

    @staticmethod
    def _compute_approval_level(trust: float, risk_score: float) -> str:
        """Pure computation of approval level from trust and risk values."""
        if trust > 0.8:
            if risk_score < 0.3:
                return AUTO_EXECUTE
            if risk_score < 0.6:
                return EXECUTE_AND_NOTIFY
            return APPROVE_PLAN
        if trust > 0.4:
            if risk_score < 0.3:
                return EXECUTE_AND_NOTIFY
            if risk_score < 0.6:
                return APPROVE_PLAN
            return APPROVE_EACH
        # Low trust (<=0.4) — includes default 0.3 for new categories
        if risk_score < 0.3:
            return APPROVE_PLAN
        return APPROVE_EACH

    async def can_request_autonomy_upgrade(self, user_id: str, action_category: str) -> bool:
        """Check whether ARIA can request more autonomy for this category.

        Requirements:
          - At least 10 successful actions
          - Failure rate <= 10%
          - Trust score >= 0.6

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            True if eligible to request an autonomy upgrade.
        """
        profile = await self.get_trust_profile(user_id, action_category)
        return (
            profile.successful_actions >= 10
            and profile.failure_rate <= 0.10
            and profile.trust_score >= 0.6
        )

    async def format_autonomy_request(self, user_id: str, action_category: str) -> str:
        """Generate a natural-language autonomy upgrade request.

        Args:
            user_id: The user's UUID.
            action_category: The action category.

        Returns:
            Human-readable request string, or a not-eligible message.
        """
        profile = await self.get_trust_profile(user_id, action_category)
        eligible = (
            profile.successful_actions >= 10
            and profile.failure_rate <= 0.10
            and profile.trust_score >= 0.6
        )

        if not eligible:
            return (
                f"I'm not yet ready to request more autonomy for "
                f"{action_category}. I need more successful actions to "
                f"build a strong track record."
            )

        success_rate = round((1.0 - profile.failure_rate) * 100, 0)
        return (
            f"I've handled {profile.successful_actions} {action_category} "
            f"tasks with a {success_rate:.0f}% success rate. "
            f"Would you be comfortable letting me handle these with "
            f"less oversight?"
        )

    async def _record_history(
        self, user_id: str, action_category: str, new_score: float, change_type: str
    ) -> None:
        """Record a trust score change in the history table. Fail-open on errors.

        Args:
            user_id: The user's UUID.
            action_category: The action category.
            new_score: The trust score after the change.
            change_type: One of 'success', 'failure', 'override', 'manual'.
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            client.table("trust_score_history").insert({
                "user_id": user_id,
                "action_category": action_category,
                "trust_score": new_score,
                "change_type": change_type,
            }).execute()
        except Exception:
            logger.exception("Failed to record trust history for user %s", user_id)

    async def _call_update_rpc(
        self,
        user_id: str,
        action_category: str,
        new_score: float,
        success_delta: int = 0,
        failure_delta: int = 0,
        override_delta: int = 0,
        set_last_failure: bool = False,
        set_last_override: bool = False,
    ) -> None:
        """Call the update_trust_score RPC. Fail-open on errors.

        Args:
            user_id: The user's UUID.
            action_category: The action category.
            new_score: Pre-computed new trust score.
            success_delta: Increment for successful_actions counter.
            failure_delta: Increment for failed_actions counter.
            override_delta: Increment for override_count counter.
            set_last_failure: Whether to set last_failure_at to now().
            set_last_override: Whether to set last_override_at to now().
        """
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            client.rpc(
                "update_trust_score",
                {
                    "p_user_id": user_id,
                    "p_action_category": action_category,
                    "p_new_score": new_score,
                    "p_success_delta": success_delta,
                    "p_failure_delta": failure_delta,
                    "p_override_delta": override_delta,
                    "p_set_last_failure": set_last_failure,
                    "p_set_last_override": set_last_override,
                },
            ).execute()
        except Exception:
            logger.exception(
                "Failed to update trust score for user %s category %s",
                user_id,
                action_category,
            )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_service: TrustCalibrationService | None = None


def get_trust_calibration_service() -> TrustCalibrationService:
    """Get or create the TrustCalibrationService singleton.

    Returns:
        The shared TrustCalibrationService instance.
    """
    global _service  # noqa: PLW0603
    if _service is None:
        _service = TrustCalibrationService()
    return _service
