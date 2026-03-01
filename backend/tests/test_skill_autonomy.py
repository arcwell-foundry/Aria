"""Tests for skill autonomy and trust system."""

from datetime import UTC, datetime, timedelta
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest

from src.skills.autonomy import (
    SKILL_RISK_THRESHOLDS,
    SkillAutonomyService,
    SkillRiskLevel,
)


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
        """Test MEDIUM+ skills with no history require approval."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await service.should_request_approval("user-abc", "skill-email", SkillRiskLevel.MEDIUM)

        assert result is True

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_low_risk_always_auto_approves(self, mock_get_client: MagicMock) -> None:
        """Test LOW risk skills always auto-approve regardless of history."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        # No history at all
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await service.should_request_approval("user-abc", "skill-pdf", SkillRiskLevel.LOW)

        assert result is False

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
    async def test_medium_risk_needs_approval_before_10_successes(self, mock_get_client: MagicMock) -> None:
        """Test MEDIUM risk skills need approval before 10 successes."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        now = datetime.now(UTC)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-email",
            "successful_executions": 5,  # Below threshold of 10
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

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-financial", SkillRiskLevel.CRITICAL)

        assert result is True


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


class TestSkillAutonomyIntegration:
    """Integration tests for full autonomy workflow."""

    @patch("src.skills.autonomy.SupabaseClient.get_client")
    async def test_full_trust_building_workflow(self, mock_get_client: MagicMock) -> None:
        """Test complete workflow: approval needed -> build trust -> auto-approve."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = SkillAutonomyService()

        user_id = "user-123"
        skill_id = "skill-email"
        now = datetime.now(UTC)

        # Step 1: First execution - no history, needs approval (MEDIUM risk)
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.MEDIUM)
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

        # Step 3: Second execution - still needs approval (only 1 success, need 10 for MEDIUM)
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            mock_insert_response.data[0]
        )
        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.MEDIUM)
        assert needs_approval is True  # Need 10 for MEDIUM risk

        # Step 4: Record more successes to reach threshold
        for i in range(2, 11):  # Executions 2 through 10
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

        # Step 5: Now should auto-approve (10 successes for MEDIUM)
        mock_client.reset_mock()
        final_row = {
            "id": "123",
            "user_id": user_id,
            "skill_id": skill_id,
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
            final_row
        )

        needs_approval = await service.should_request_approval(user_id, skill_id, SkillRiskLevel.MEDIUM)
        assert needs_approval is False  # Auto-approved after 10 successes

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
