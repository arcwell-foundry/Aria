"""Skill autonomy and trust system for graduated approval.

This module provides the autonomy system that allows skills to earn trust
through successful executions, reducing user friction while maintaining security.

Risk Levels:
- LOW: Read-only skills (pdf, docx) - auto-approve after 3 successes
- MEDIUM: External API calls (email-sequence, calendar) - auto-approve after 10 successes
- HIGH: Destructive operations (data-deletion) - session trust only
- CRITICAL: Financial/regulated operations - always ask

Trust builds per-user-per-skill. Global approval must be explicitly granted.
Session trust resets when user logs out or new session starts.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class SkillRiskLevel(Enum):
    """Risk level for a skill operation.

    Determines how much trust is required before auto-approval.
    Ordered from least risky (LOW) to most risky (CRITICAL).
    """

    LOW = "low"
    # Read-only operations like document parsing
    # Examples: pdf, docx, pptx

    MEDIUM = "medium"
    # External API calls with side effects
    # Examples: email-sequence, calendar-management, crm-operations

    HIGH = "high"
    # Destructive operations that can't be undone
    # Examples: data-deletion, bulk-operations

    CRITICAL = "critical"
    # Financial, regulated, or high-impact operations
    # Examples: financial-transactions, phi-processing


# Auto-approval thresholds: number of successful executions before auto-approval
SKILL_RISK_THRESHOLDS: dict[SkillRiskLevel, dict[str, Any]] = {
    SkillRiskLevel.LOW: {
        "auto_approve_after": 3,  # 3 successful executions
        "description": "Read-only skills, auto-approve after 3 successes",
    },
    SkillRiskLevel.MEDIUM: {
        "auto_approve_after": 10,  # 10 successful executions
        "description": "External API calls, auto-approve after 10 successes",
    },
    SkillRiskLevel.HIGH: {
        "auto_approve_after": None,  # Never auto-approve, session trust only
        "description": "Destructive operations, session trust only",
    },
    SkillRiskLevel.CRITICAL: {
        "auto_approve_after": None,  # Never auto-approve, always ask
        "description": "Critical operations, always require approval",
    },
}


@dataclass(frozen=True)
class TrustHistory:
    """Trust history for a user-skill pair.

    Attributes match the database schema for skill_trust_history table.
    Immutable - create new instances for updates.
    """

    id: str
    user_id: str
    skill_id: str
    successful_executions: int
    failed_executions: int
    last_success: datetime | None
    last_failure: datetime | None
    session_trust_granted: bool
    globally_approved: bool
    globally_approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SkillAutonomyService:
    """Service for managing skill autonomy and trust.

    Tracks per-user-per-skill execution history and makes approval decisions
    based on risk level and historical success rate.

    Trust builds through successful executions:
    - LOW risk: auto-approve after 3 successes
    - MEDIUM risk: auto-approve after 10 successes
    - HIGH risk: session trust only (never auto-approve)
    - CRITICAL risk: always ask (never auto-approve)

    Global approval can be explicitly granted for any skill.
    Session trust is temporary and resets on logout/new session.
    """

    def __init__(self) -> None:
        """Initialize the autonomy service."""
        self._client = SupabaseClient.get_client()

    def _db_row_to_trust_history(self, row: dict[str, Any]) -> TrustHistory:
        """Convert a database row to a TrustHistory.

        Args:
            row: Dictionary from Supabase representing a skill_trust_history row.

        Returns:
            A TrustHistory with all fields properly typed.
        """
        def parse_dt(value: Any) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return None

        return TrustHistory(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            skill_id=str(row["skill_id"]),
            successful_executions=int(row.get("successful_executions", 0)),
            failed_executions=int(row.get("failed_executions", 0)),
            last_success=parse_dt(row.get("last_success")),
            last_failure=parse_dt(row.get("last_failure")),
            session_trust_granted=bool(row.get("session_trust_granted", False)),
            globally_approved=bool(row.get("globally_approved", False)),
            globally_approved_at=parse_dt(row.get("globally_approved_at")),
            created_at=parse_dt(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=parse_dt(row["updated_at"]) or datetime.now(timezone.utc),
        )

    async def get_trust_history(self, user_id: str, skill_id: str) -> TrustHistory | None:
        """Get trust history for a user-skill pair.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier (from skills_index.id or path).

        Returns:
            The TrustHistory if found, None otherwise.
        """
        try:
            response = (
                self._client.table("skill_trust_history")
                .select("*")
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .single()
                .execute()
            )
            if response.data:
                return self._db_row_to_trust_history(response.data)
            return None
        except Exception as e:
            logger.debug(f"Trust history not found for user {user_id}, skill {skill_id}: {e}")
            return None

    async def should_request_approval(
        self, user_id: str, skill_id: str, risk_level: SkillRiskLevel
    ) -> bool:
        """Determine if skill execution requires user approval.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier.
            risk_level: The risk level of this skill operation.

        Returns:
            True if approval is required, False if execution can proceed.

        Approval logic:
        1. Globally approved skills: never require approval
        2. Session trusted skills: never require approval
        3. No history: require approval (first time)
        4. LOW/MEDIUM risk: auto-approve after threshold successes
        5. HIGH/CRITICAL risk: always require approval
        """
        # Get current trust history
        history = await self.get_trust_history(user_id, skill_id)

        # No history exists - require approval
        if history is None:
            return True

        # Global approval trumps everything
        if history.globally_approved:
            return False

        # Session trust also bypasses checks
        if history.session_trust_granted:
            return False

        # Get auto-approval threshold for this risk level
        threshold_config = SKILL_RISK_THRESHOLDS.get(risk_level, {})
        auto_approve_after = threshold_config.get("auto_approve_after")

        # HIGH and CRITICAL risk never auto-approve
        if auto_approve_after is None:
            return True

        # Check if we've met the success threshold
        return history.successful_executions < auto_approve_after
