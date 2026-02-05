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

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await service.should_request_approval("user-abc", "skill-financial", SkillRiskLevel.CRITICAL)

        assert result is True
