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
