# [Skill Autonomy & Trust System] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a graduated autonomy system for skill execution that builds trust based on successful outcomes, reducing user friction while maintaining security.

**Architecture:**
1. `skill_trust_history` table tracks per-user-per-skill execution statistics
2. `SkillRiskLevel` enum defines risk categories (LOW/MEDIUM/HIGH/CRITICAL)
3. `SKILL_RISK_THRESHOLDS` maps risk levels to auto-approval requirements
4. `SkillAutonomyService` manages trust state and approval decisions
5. Integration with existing audit logging for compliance

**Tech Stack:** Python 3.11+, Supabase (PostgreSQL), pytest, AsyncMock

---

## Task 1: Create database migration for skill_trust_history table

**Files:**
- Create: `supabase/migrations/20260205000001_create_skill_trust_history.sql`

**Step 1: Write the migration file**

```sql
-- Migration: Create skill_trust_history table
-- US-530: Skill Autonomy & Trust System

-- Create skill_trust_history table for per-user-per-skill trust tracking
CREATE TABLE IF NOT EXISTS skill_trust_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    successful_executions INT DEFAULT 0 NOT NULL,
    failed_executions INT DEFAULT 0 NOT NULL,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    session_trust_granted BOOLEAN DEFAULT FALSE NOT NULL,
    globally_approved BOOLEAN DEFAULT FALSE NOT NULL,
    globally_approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, skill_id)
);

-- Index for user-skill lookups (primary access pattern)
CREATE INDEX idx_skill_trust_history_user_skill ON skill_trust_history(user_id, skill_id);

-- Index for finding globally approved skills
CREATE INDEX idx_skill_trust_history_global_approval ON skill_trust_history(user_id, globally_approved) WHERE globally_approved = TRUE;

-- Enable RLS
ALTER TABLE skill_trust_history ENABLE ROW LEVEL SECURITY;

-- Users can read and modify their own trust history
CREATE POLICY "Users can manage own skill trust history"
    ON skill_trust_history
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Service role has full access for backend operations
CREATE POLICY "Service role can manage skill trust history"
    ON skill_trust_history
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_skill_trust_history_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_skill_trust_history_updated_at
    BEFORE UPDATE ON skill_trust_history
    FOR EACH ROW
    EXECUTE FUNCTION update_skill_trust_history_updated_at();

-- Add comment for documentation
COMMENT ON TABLE skill_trust_history IS 'Tracks per-user-per-skill execution history for graduated autonomy. Skills earn trust through successful executions.';
COMMENT ON COLUMN skill_trust_history.session_trust_granted IS 'User granted trust for current session only. Resets on new session.';
COMMENT ON COLUMN skill_trust_history.globally_approved IS 'User granted permanent auto-approval for this skill. Requires explicit revocation.';
```

**Step 2: Verify migration syntax**

Run: `supabase migration validate 20260205000001_create_skill_trust_history.sql`
Expected: No syntax errors reported

**Step 3: Push migration to database**

Run: `supabase db push`
Expected: Migration applied successfully, table created

**Step 4: Commit migration**

```bash
git add supabase/migrations/20260205000001_create_skill_trust_history.sql
git commit -m "feat(autonomy): add skill_trust_history table for graduated autonomy"
```

---

## Task 2: Create SkillRiskLevel enum and constants

**Files:**
- Create: `backend/src/skills/autonomy.py`

**Step 1: Write the failing test for SkillRiskLevel enum**

```python
"""Tests for skill autonomy and trust system."""

from enum import Enum

import pytest

from src.skills.autonomy import SKILL_RISK_THRESHOLDS, SkillRiskLevel


class TestSkillRiskLevel:
    """Tests for SkillRiskLevel enum."""

    def test_risk_level_enum_values(self) -> None:
        """Test SkillRiskLevel has all required risk levels."""
        assert SkillRiskLevel.LOW.value == "low"
        assert SkillRiskLevel.MEDIUM.value == "medium"
        assert SkillRiskLevel.HIGH.value == "high"
        assert SkillRiskLevel.CRITICAL.value == "critical"

    def test_risk_levels_are_ordered(self) -> None:
        """Test risk levels can be compared by severity."""
        levels = list(SkillRiskLevel)
        assert levels == [
            SkillRiskLevel.LOW,
            SkillRiskLevel.MEDIUM,
            SkillRiskLevel.HIGH,
            SkillRiskLevel.CRITICAL,
        ]


class TestSkillRiskThresholds:
    """Tests for SKILL_RISK_THRESHOLDS configuration."""

    def test_thresholds_defined_for_all_risk_levels(self) -> None:
        """Test thresholds exist for all risk levels."""
        assert SkillRiskLevel.LOW in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.MEDIUM in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.HIGH in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.CRITICAL in SKILL_RISK_THRESHOLDS

    def test_low_threshold_requires_3_successes(self) -> None:
        """Test LOW risk requires 3 successful executions."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.LOW]["auto_approve_after"] == 3

    def test_medium_threshold_requires_10_successes(self) -> None:
        """Test MEDIUM risk requires 10 successful executions."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.MEDIUM]["auto_approve_after"] == 10

    def test_high_threshold_never_auto_approves(self) -> None:
        """Test HIGH risk never auto-approves (session trust only)."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.HIGH]["auto_approve_after"] is None

    def test_critical_threshold_never_auto_approves(self) -> None:
        """Test CRITICAL risk never auto-approves (always ask)."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.CRITICAL]["auto_approve_after"] is None

    def test_threshold_values_are_positive_or_none(self) -> None:
        """Test all auto_approve_after values are positive integers or None."""
        for threshold in SKILL_RISK_THRESHOLDS.values():
            value = threshold["auto_approve_after"]
            assert value is None or (isinstance(value, int) and value > 0)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillRiskLevel -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.skills.autonomy'"

**Step 3: Create minimal implementation to make tests pass**

Create `backend/src/skills/autonomy.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillRiskLevel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): add SkillRiskLevel enum and thresholds"
```

---

## Task 3: Create SkillAutonomyService class with get_trust_history

**Files:**
- Modify: `backend/src/skills/autonomy.py`
- Modify: `backend/tests/test_skill_autonomy.py`

**Step 1: Write the failing test**

```python
class TestSkillAutonomyServiceInit:
    """Tests for SkillAutonomyService initialization."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    def test_init_creates_supabase_client(self, mock_get_client: MagicMock) -> None:
        """Test SkillAutonomyService initializes with Supabase client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        service = SkillAutonomyService()

        assert service._client is not None
        mock_get_client.assert_called_once()


class TestSkillAutonomyServiceGetTrustHistory:
    """Tests for SkillAutonomyService.get_trust_history method."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_get_trust_history_returns_existing_record(self, mock_get_client: MagicMock) -> None:
        """Test get_trust_history returns existing trust history record."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 5,
            "failed_executions": 1,
            "last_success": now.isoformat(),
            "last_failure": (now - timedelta(hours=1)).isoformat(),
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": (now - timedelta(days=7)).isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.get_trust_history("user-abc", "skill-pdf")

        assert result is not None
        assert result.user_id == "user-abc"
        assert result.skill_id == "skill-pdf"
        assert result.successful_executions == 5
        assert result.failed_executions == 1

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_get_trust_history_returns_none_for_nonexistent(self, mock_get_client: MagicMock) -> None:
        """Test get_trust_history returns None when no record exists."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await service.get_trust_history("user-abc", "skill-pdf")

        assert result is None

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_get_trust_history_handles_database_error(self, mock_get_client: MagicMock) -> None:
        """Test get_trust_history returns None on database error."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = (
            Exception("Database connection error")
        )

        result = await service.get_trust_history("user-abc", "skill-pdf")

        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceGetTrustHistory -v`
Expected: FAIL with "AttributeError: 'SkillAutonomyService' does not exist" or similar

**Step 3: Implement SkillAutonomyService class**

Add to `backend/src/skills/autonomy.py` (after the dataclass):

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceGetTrustHistory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): add SkillAutonomyService.get_trust_history"
```

---

## Task 4: Implement should_request_approval method

**Files:**
- Modify: `backend/src/skills/autonomy.py`
- Modify: `backend/tests/test_skill_autonomy.py`

**Step 1: Write the failing test**

```python
class TestSkillAutonomyServiceShouldRequestApproval:
    """Tests for SkillAutonomyService.should_request_approval method."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_globally_approved_needs_no_approval(self, mock_get_client: MagicMock) -> None:
        """Test globally approved skills never require approval."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 0,
            "failed_executions": 0,
            "last_success": None,
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": True,  # Globally approved
            "globally_approved_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.LOW)

        assert result is False

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_session_trusted_needs_no_approval(self, mock_get_client: MagicMock) -> None:
        """Test session trusted skills don't require approval."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 0,
            "failed_executions": 0,
            "last_success": None,
            "last_failure": None,
            "session_trust_granted": True,  # Session trust
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.MEDIUM)

        assert result is False

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_no_history_needs_approval(self, mock_get_client: MagicMock) -> None:
        """Test skills with no history require approval."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.LOW)

        assert result is True

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_low_risk_auto_approves_after_3_successes(self, mock_get_client: MagicMock) -> None:
        """Test LOW risk skills auto-approve after 3 successes."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 3,  # Met threshold
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.LOW)

        assert result is False

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_low_risk_needs_approval_before_3_successes(self, mock_get_client: MagicMock) -> None:
        """Test LOW risk skills need approval before 3 successes."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 2,  # Below threshold
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.LOW)

        assert result is True

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_medium_risk_auto_approves_after_10_successes(self, mock_get_client: MagicMock) -> None:
        """Test MEDIUM risk skills auto-approve after 10 successes."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-email",
            "successful_executions": 10,  # Met threshold
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-email", SkillRiskLevel.MEDIUM)

        assert result is False

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_high_risk_always_needs_approval(self, mock_get_client: MagicMock) -> None:
        """Test HIGH risk skills always need approval (no auto-approve)."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-delete",
            "successful_executions": 100,  # Even with many successes
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-delete", SkillRiskLevel.HIGH)

        assert result is True

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_critical_risk_always_needs_approval(self, mock_get_client: MagicMock) -> None:
        """Test CRITICAL risk skills always need approval."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-financial",
            "successful_executions": 100,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-financial", SkillRiskLevel.CRITICAL)

        assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceShouldRequestApproval -v`
Expected: FAIL with "AttributeError: 'SkillAutonomyService' object has no attribute 'should_request_approval'"

**Step 3: Implement should_request_approval method**

Add to `SkillAutonomyService` class in `backend/src/skills/autonomy.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceShouldRequestApproval -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): add should_request_approval decision logic"
```

---

## Task 5: Implement record_execution_outcome method

**Files:**
- Modify: `backend/src/skills/autonomy.py`
- Modify: `backend/tests/test_skill_autonomy.py`

**Step 1: Write the failing test**

```python
class TestSkillAutonomyServiceRecordExecutionOutcome:
    """Tests for SkillAutonomyService.record_execution_outcome method."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_record_success_creates_new_history(self, mock_get_client: MagicMock) -> None:
        """Test recording success creates new trust history if none exists."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        # No existing history
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        # Mock insert response
        now = datetime.now(UTC)
        inserted_row = {
            "id": "new-123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 1,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        mock_insert_response = MagicMock()
        mock_insert_response.data = [inserted_row]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        result = await service.record_execution_outcome("user-abc", "skill-pdf", success=True)

        assert result is not None
        assert result.successful_executions == 1
        assert result.failed_executions == 0
        assert result.last_success is not None

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_record_success_increments_success_count(self, mock_get_client: MagicMock) -> None:
        """Test recording success increments successful_executions."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 2,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        # Mock update response
        updated_row = existing_row.copy()
        updated_row["successful_executions"] = 3
        updated_row["last_success"] = now.isoformat()
        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.record_execution_outcome("user-abc", "skill-pdf", success=True)

        assert result is not None
        assert result.successful_executions == 3
        assert result.failed_executions == 0

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_record_failure_increments_failure_count(self, mock_get_client: MagicMock) -> None:
        """Test recording failure increments failed_executions."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 5,
            "failed_executions": 1,
            "last_success": now.isoformat(),
            "last_failure": now.isoformat(),
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["failed_executions"] = 2
        updated_row["last_failure"] = now.isoformat()
        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.record_execution_outcome("user-abc", "skill-pdf", success=False)

        assert result is not None
        assert result.successful_executions == 5  # Unchanged
        assert result.failed_executions == 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceRecordExecutionOutcome -v`
Expected: FAIL with "AttributeError: 'SkillAutonomyService' object has no attribute 'record_execution_outcome'"

**Step 3: Implement record_execution_outcome method**

Add to `SkillAutonomyService` class in `backend/src/skills/autonomy.py`:

```python
    async def record_execution_outcome(
        self, user_id: str, skill_id: str, *, success: bool
    ) -> TrustHistory | None:
        """Record the outcome of a skill execution.

        Creates or updates trust history for the user-skill pair.
        Tracks successes and failures separately for trust calculation.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier.
            success: True if execution succeeded, False if it failed.

        Returns:
            The updated TrustHistory, or None on error.
        """
        try:
            now = datetime.now(timezone.utc)

            # Check if history exists
            existing = await self.get_trust_history(user_id, skill_id)

            if existing is None:
                # Create new trust history record
                record = {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "successful_executions": 1 if success else 0,
                    "failed_executions": 0 if success else 1,
                    "last_success": now.isoformat() if success else None,
                    "last_failure": now.isoformat() if not success else None,
                    "session_trust_granted": False,
                    "globally_approved": False,
                    "globally_approved_at": None,
                }

                response = self._client.table("skill_trust_history").insert(record).execute()
                if response.data:
                    logger.info(
                        f"Created trust history for user {user_id}, skill {skill_id} "
                        f"(success={success})"
                    )
                    return self._db_row_to_trust_history(response.data[0])
                return None

            # Update existing record
            update_data = {
                "successful_executions": existing.successful_executions + (1 if success else 0),
                "failed_executions": existing.failed_executions + (0 if success else 1),
            }

            if success:
                update_data["last_success"] = now.isoformat()
            else:
                update_data["last_failure"] = now.isoformat()

            response = (
                self._client.table("skill_trust_history")
                .update(update_data)
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .execute()
            )

            if response.data:
                logger.debug(
                    f"Updated trust history for user {user_id}, skill {skill_id} "
                    f"(success={success}, total_successes={update_data['successful_executions']})"
                )
                return self._db_row_to_trust_history(response.data[0])

            return None

        except Exception as e:
            logger.error(f"Error recording execution outcome for user {user_id}, skill {skill_id}: {e}")
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceRecordExecutionOutcome -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): add record_execution_outcome for trust tracking"
```

---

## Task 6: Implement trust management methods (grant_session_trust, grant_global_approval, revoke_trust)

**Files:**
- Modify: `backend/src/skills/autonomy.py`
- Modify: `backend/tests/test_skill_autonomy.py`

**Step 1: Write the failing test**

```python
class TestSkillAutonomyServiceTrustManagement:
    """Tests for SkillAutonomyService trust management methods."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_grant_session_trust_sets_flag(self, mock_get_client: MagicMock) -> None:
        """Test grant_session_trust sets session_trust_granted to True."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 2,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["session_trust_granted"] = True
        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.grant_session_trust("user-abc", "skill-pdf")

        assert result is not None
        assert result.session_trust_granted is True

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_grant_global_approval_sets_flags(self, mock_get_client: MagicMock) -> None:
        """Test grant_global_approval sets globally_approved and timestamp."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 10,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["globally_approved"] = True
        updated_row["globally_approved_at"] = now.isoformat()
        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.grant_global_approval("user-abc", "skill-pdf")

        assert result is not None
        assert result.globally_approved is True
        assert result.globally_approved_at is not None

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_revoke_trust_clears_all_flags(self, mock_get_client: MagicMock) -> None:
        """Test revoke_trust clears both session and global trust flags."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 10,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": True,
            "globally_approved": True,
            "globally_approved_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["session_trust_granted"] = False
        updated_row["globally_approved"] = False
        updated_row["globally_approved_at"] = None
        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.revoke_trust("user-abc", "skill-pdf")

        assert result is not None
        assert result.session_trust_granted is False
        assert result.globally_approved is False
        assert result.globally_approved_at is None

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_revoke_trust_creates_history_if_none_exists(self, mock_get_client: MagicMock) -> None:
        """Test revoke_trust creates history record if none exists (for future use)."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        # No existing history
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        now = datetime.now(UTC)
        inserted_row = {
            "id": "new-123",
            "user_id": "user-abc",
            "skill_id": "skill-pdf",
            "successful_executions": 0,
            "failed_executions": 0,
            "last_success": None,
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        mock_insert_response = MagicMock()
        mock_insert_response.data = [inserted_row]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        result = await service.revoke_trust("user-abc", "skill-pdf")

        assert result is not None
        assert result.session_trust_granted is False
        assert result.globally_approved is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceTrustManagement -v`
Expected: FAIL with missing methods

**Step 3: Implement trust management methods**

Add to `SkillAutonomyService` class in `backend/src/skills/autonomy.py`:

```python
    async def grant_session_trust(self, user_id: str, skill_id: str) -> TrustHistory | None:
        """Grant session-level trust for a skill.

        Session trust allows auto-approval for the current session only.
        Resets when user logs out or new session starts.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier.

        Returns:
            The updated TrustHistory, or None on error.
        """
        try:
            existing = await self.get_trust_history(user_id, skill_id)

            if existing is None:
                # Create new record with session trust
                now = datetime.now(timezone.utc)
                record = {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "last_success": None,
                    "last_failure": None,
                    "session_trust_granted": True,
                    "globally_approved": False,
                    "globally_approved_at": None,
                }

                response = self._client.table("skill_trust_history").insert(record).execute()
                if response.data:
                    logger.info(f"Granted session trust for user {user_id}, skill {skill_id}")
                    return self._db_row_to_trust_history(response.data[0])
                return None

            # Update existing record
            response = (
                self._client.table("skill_trust_history")
                .update({"session_trust_granted": True})
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .execute()
            )

            if response.data:
                logger.info(f"Granted session trust for user {user_id}, skill {skill_id}")
                return self._db_row_to_trust_history(response.data[0])

            return None

        except Exception as e:
            logger.error(f"Error granting session trust for user {user_id}, skill {skill_id}: {e}")
            return None

    async def grant_global_approval(self, user_id: str, skill_id: str) -> TrustHistory | None:
        """Grant permanent global approval for a skill.

        Global approval means the skill will never require approval for this user
        unless explicitly revoked.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier.

        Returns:
            The updated TrustHistory, or None on error.
        """
        try:
            existing = await self.get_trust_history(user_id, skill_id)
            now = datetime.now(timezone.utc)

            if existing is None:
                # Create new record with global approval
                record = {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "last_success": None,
                    "last_failure": None,
                    "session_trust_granted": False,
                    "globally_approved": True,
                    "globally_approved_at": now.isoformat(),
                }

                response = self._client.table("skill_trust_history").insert(record).execute()
                if response.data:
                    logger.info(f"Granted global approval for user {user_id}, skill {skill_id}")
                    return self._db_row_to_trust_history(response.data[0])
                return None

            # Update existing record
            response = (
                self._client.table("skill_trust_history")
                .update({"globally_approved": True, "globally_approved_at": now.isoformat()})
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .execute()
            )

            if response.data:
                logger.info(f"Granted global approval for user {user_id}, skill {skill_id}")
                return self._db_row_to_trust_history(response.data[0])

            return None

        except Exception as e:
            logger.error(f"Error granting global approval for user {user_id}, skill {skill_id}: {e}")
            return None

    async def revoke_trust(self, user_id: str, skill_id: str) -> TrustHistory | None:
        """Revoke all trust (session and global) for a skill.

        Clears both session_trust_granted and globally_approved flags.
        Keeps execution statistics intact.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's identifier.

        Returns:
            The updated TrustHistory, or None on error.
        """
        try:
            existing = await self.get_trust_history(user_id, skill_id)

            if existing is None:
                # Create new revoked record (for future use)
                now = datetime.now(timezone.utc)
                record = {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "last_success": None,
                    "last_failure": None,
                    "session_trust_granted": False,
                    "globally_approved": False,
                    "globally_approved_at": None,
                }

                response = self._client.table("skill_trust_history").insert(record).execute()
                if response.data:
                    logger.info(f"Revoked trust for user {user_id}, skill {skill_id} (new record)")
                    return self._db_row_to_trust_history(response.data[0])
                return None

            # Update existing record - clear all trust flags
            response = (
                self._client.table("skill_trust_history")
                .update({
                    "session_trust_granted": False,
                    "globally_approved": False,
                    "globally_approved_at": None,
                })
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .execute()
            )

            if response.data:
                logger.info(f"Revoked trust for user {user_id}, skill {skill_id}")
                return self._db_row_to_trust_history(response.data[0])

            return None

        except Exception as e:
            logger.error(f"Error revoking trust for user {user_id}, skill {skill_id}: {e}")
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py::TestSkillAutonomyServiceTrustManagement -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): add trust management methods"
```

---

## Task 7: Export from skills module and add integration test

**Files:**
- Modify: `backend/src/skills/__init__.py`
- Modify: `backend/tests/test_skill_autonomy.py`

**Step 1: Update __init__.py to export autonomy classes**

```python
"""Skills module for ARIA.

This module provides skill discovery, installation, execution, and autonomy.
"""

from src.skills.autonomy import (
    SKILL_RISK_THRESHOLDS,
    SkillAutonomyService,
    SkillRiskLevel,
    TrustHistory,
)
from src.skills.index import SkillIndex, SkillIndexEntry
from src.skills.installer import InstalledSkill, SkillInstaller, SkillNotFoundError

__all__ = [
    # Autonomy
    "SKILL_RISK_THRESHOLDS",
    "SkillAutonomyService",
    "SkillRiskLevel",
    "TrustHistory",
    # Index
    "SkillIndex",
    "SkillIndexEntry",
    # Installer
    "InstalledSkill",
    "SkillInstaller",
    "SkillNotFoundError",
]
```

**Step 2: Run tests to verify imports work**

Run: `cd backend && pytest tests/test_skill_autonomy.py -v`
Expected: PASS (all existing tests still pass)

**Step 3: Add integration test for full autonomy workflow**

```python
class TestSkillAutonomyIntegration:
    """Integration tests for full autonomy workflow."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_full_trust_building_workflow(self, mock_get_client: MagicMock) -> None:
        """Test complete workflow: approval needed -> build trust -> auto-approve."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        user_id = "user-123"
        skill_id = "skill-pdf"
        now = datetime.now(UTC)

        # Step 1: First execution - no history, needs approval
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.LOW)
        assert needs_approval is True

        # Step 2: Record first success
        mock_insert_response = MagicMock()
        mock_insert_response.data = [{
            "id": "123",
            "user_id": user_id,
            "skill_id": skill_id,
            "successful_executions": 1,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

        result = await service.record_execution_outcome(user_id, skill_id, success=True)
        assert result.successful_executions == 1

        # Step 3: Second execution - still needs approval (only 1 success)
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            mock_insert_response.data[0]
        )
        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.LOW)
        assert needs_approval is True  # Need 3 for LOW risk

        # Step 4: Record two more successes
        for i in range(2, 4):  # Executions 2 and 3
            mock_client.reset_mock()

            # Current state
            current_row = {
                "id": "123",
                "user_id": user_id,
                "skill_id": skill_id,
                "successful_executions": i - 1,
                "failed_executions": 0,
                "last_success": now.isoformat(),
                "last_failure": None,
                "session_trust_granted": False,
                "globally_approved": False,
                "globally_approved_at": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
                current_row
            )

            # Updated state
            updated_row = current_row.copy()
            updated_row["successful_executions"] = i
            mock_update_response = MagicMock()
            mock_update_response.data = [updated_row]
            mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_update_response
            )

            await service.record_execution_outcome(user_id, skill_id, success=True)

        # Step 5: Now should auto-approve (3 successes)
        mock_client.reset_mock()
        final_row = {
            "id": "123",
            "user_id": user_id,
            "skill_id": skill_id,
            "successful_executions": 3,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            final_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.LOW)
        assert needs_approval is False  # Auto-approved after 3 successes

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_session_trust_workflow(self, mock_get_client: MagicMock) -> None:
        """Test session trust: grant -> use -> revoke."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        user_id = "user-123"
        skill_id = "skill-high-risk"
        now = datetime.now(UTC)

        # Initial state: no trust, needs approval
        base_row = {
            "id": "123",
            "user_id": user_id,
            "skill_id": skill_id,
            "successful_executions": 0,
            "failed_executions": 0,
            "last_success": None,
            "last_failure": None,
            "session_trust_granted": False,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            base_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.HIGH)
        assert needs_approval is True

        # Grant session trust
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            base_row
        )

        trusted_row = base_row.copy()
        trusted_row["session_trust_granted"] = True
        mock_update_response = MagicMock()
        mock_update_response.data = [trusted_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.grant_session_trust(user_id, skill_id)
        assert result.session_trust_granted is True

        # Now doesn't need approval
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            trusted_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.HIGH)
        assert needs_approval is False  # Session trust bypasses

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_revocation_workflow(self, mock_get_client: MagicMock) -> None:
        """Test global approval then revocation."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        user_id = "user-123"
        skill_id = "skill-email"
        now = datetime.now(UTC)

        # Grant global approval
        base_row = {
            "id": "123",
            "user_id": user_id,
            "skill_id": skill_id,
            "successful_executions": 5,
            "failed_executions": 0,
            "last_success": now.isoformat(),
            "last_failure": None,
            "session_trust_granted": True,
            "globally_approved": False,
            "globally_approved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            base_row
        )

        approved_row = base_row.copy()
        approved_row["globally_approved"] = True
        approved_row["globally_approved_at"] = now.isoformat()
        mock_update_response = MagicMock()
        mock_update_response.data = [approved_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.grant_global_approval(user_id, skill_id)
        assert result.globally_approved is True

        # Verify no approval needed
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            approved_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.MEDIUM)
        assert needs_approval is False

        # Revoke trust
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            approved_row
        )

        revoked_row = approved_row.copy()
        revoked_row["session_trust_granted"] = False
        revoked_row["globally_approved"] = False
        revoked_row["globally_approved_at"] = None
        mock_update_response = MagicMock()
        mock_update_response.data = [revoked_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await service.revoke_trust(user_id, skill_id)
        assert result.globally_approved is False
        assert result.session_trust_granted is False

        # Now needs approval again (not enough successes for MEDIUM)
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            revoked_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.MEDIUM)
        assert needs_approval is True  # MEDIUM needs 10 successes, only has 5
```

**Step 4: Run all tests to verify everything passes**

Run: `cd backend && pytest tests/test_skill_autonomy.py -v`
Expected: PASS (all tests pass)

**Step 5: Run type checking**

Run: `cd backend && mypy src/skills/autonomy.py --strict`
Expected: No type errors

**Step 6: Run linting**

Run: `cd backend && ruff check src/skills/autonomy.py`
Expected: No lint errors

**Step 7: Final commit**

```bash
git add backend/src/skills/__init__.py backend/src/skills/autonomy.py backend/tests/test_skill_autonomy.py
git commit -m "feat(autonomy): complete skill autonomy and trust system

- Add skill_trust_history database table
- Implement SkillRiskLevel enum (LOW/MEDIUM/HIGH/CRITICAL)
- Add SKILL_RISK_THRESHOLDS for auto-approval
- Implement SkillAutonomyService with:
  - get_trust_history: retrieve trust state
  - should_request_approval: decision logic
  - record_execution_outcome: track successes/failures
  - grant_session_trust: temporary trust
  - grant_global_approval: permanent trust
  - revoke_trust: clear all trust
- Add comprehensive unit and integration tests
- Export from skills module

US-530"
```

---

## Post-Implementation Verification

After completing all tasks, run these verification commands:

```bash
# 1. All tests pass
cd backend && pytest tests/test_skill_autonomy.py -v

# 2. Type checking passes
cd backend && mypy src/skills/autonomy.py --strict

# 3. Linting passes
cd backend && ruff check src/skills/autonomy.py
cd backend && ruff format --check src/skills/autonomy.py

# 4. Migration applied
supabase migration list | grep 20260205000001

# 5. All skill-related tests still pass
cd backend && pytest tests/test_skill*.py -v
```

Expected output: All tests pass, no type errors, migration shows as applied.
