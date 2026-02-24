"""Tests for the AutonomyCalibrationService."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# --- Fixtures ---


@pytest.fixture
def mock_user_settings() -> dict[str, Any]:
    """User settings with autonomy_level stored in preferences."""
    return {
        "user_id": "user-001",
        "preferences": {"autonomy_level": 3},
    }


@pytest.fixture
def mock_user_profile() -> dict[str, Any]:
    """User profile with account creation date."""
    return {
        "id": "user-001",
        "created_at": (datetime.now(UTC) - timedelta(days=90)).isoformat(),
    }


@pytest.fixture
def mock_action_stats() -> list[dict[str, Any]]:
    """Action queue records for computing approval/rejection stats."""
    return [
        {"id": "a1", "status": "completed", "risk_level": "low"},
        {"id": "a2", "status": "completed", "risk_level": "medium"},
        {"id": "a3", "status": "completed", "risk_level": "high"},
        {"id": "a4", "status": "rejected", "risk_level": "medium"},
        {"id": "a5", "status": "completed", "risk_level": "low"},
        {"id": "a6", "status": "failed", "risk_level": "low"},
        {"id": "a7", "status": "completed", "risk_level": "low"},
        {"id": "a8", "status": "completed", "risk_level": "medium"},
        {"id": "a9", "status": "rejected", "risk_level": "high"},
        {"id": "a10", "status": "completed", "risk_level": "low"},
    ]


@pytest.fixture
def mock_feedback_records() -> list[dict[str, Any]]:
    """Feedback records for user satisfaction signals."""
    return [
        {"id": "f1", "rating": "up", "type": "response"},
        {"id": "f2", "rating": "up", "type": "response"},
        {"id": "f3", "rating": "down", "type": "response"},
        {"id": "f4", "rating": "up", "type": "response"},
        {"id": "f5", "rating": "up", "type": "response"},
    ]


@pytest.fixture
def mock_email_drafts() -> list[dict[str, Any]]:
    """Email drafts with user_action for approval rate calculation."""
    return [
        {"id": "d1", "user_action": "approved"},
        {"id": "d2", "user_action": "approved"},
        {"id": "d3", "user_action": "edited"},
        {"id": "d4", "user_action": "approved"},
        {"id": "d5", "user_action": "rejected"},
        {"id": "d6", "user_action": "approved"},
    ]


def _build_db_mock(
    *,
    user_profile: dict[str, Any] | None = None,
    user_settings: dict[str, Any] | None = None,
    action_records: list[dict[str, Any]] | None = None,
    feedback_records: list[dict[str, Any]] | None = None,
    email_drafts: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a Supabase client mock that routes table calls."""
    mock_client = MagicMock()
    _table_cache: dict[str, MagicMock] = {}

    def table_router(name: str) -> MagicMock:
        if name in _table_cache:
            return _table_cache[name]
        mock_table = MagicMock()

        if name == "user_profiles":
            mock_select = MagicMock()
            mock_eq = MagicMock()
            mock_maybe_single = MagicMock()
            mock_maybe_single.execute.return_value = MagicMock(
                data=user_profile,
            )
            mock_eq.maybe_single.return_value = mock_maybe_single
            mock_select.eq.return_value = mock_eq
            mock_table.select.return_value = mock_select

        elif name == "user_settings":
            # For select queries
            mock_select = MagicMock()
            mock_eq = MagicMock()
            mock_maybe_single = MagicMock()
            mock_maybe_single.execute.return_value = MagicMock(
                data=user_settings,
            )
            mock_eq.maybe_single.return_value = mock_maybe_single
            mock_select.eq.return_value = mock_eq
            mock_table.select.return_value = mock_select

            # For update queries
            mock_update = MagicMock()
            mock_update_eq = MagicMock()
            mock_update_eq.execute.return_value = MagicMock(
                data=[user_settings] if user_settings else [],
            )
            mock_update.eq.return_value = mock_update_eq
            mock_table.update.return_value = mock_update

        elif name == "aria_action_queue":
            mock_select = MagicMock()
            mock_eq = MagicMock()
            mock_execute = MagicMock()
            mock_execute.execute.return_value = MagicMock(
                data=action_records or [],
            )
            mock_eq.execute = mock_execute.execute
            mock_select.eq.return_value = mock_eq
            mock_table.select.return_value = mock_select

        elif name == "feedback":
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()
            mock_eq2.execute.return_value = MagicMock(
                data=feedback_records or [],
            )
            mock_eq1.eq.return_value = mock_eq2
            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select

        elif name == "email_drafts":
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_neq = MagicMock()
            mock_neq.execute.return_value = MagicMock(
                data=email_drafts or [],
            )
            mock_eq1.neq.return_value = mock_neq
            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select

        elif name == "autonomy_decisions":
            mock_insert = MagicMock()
            mock_insert.execute.return_value = MagicMock(
                data=[{"id": "decision-001"}],
            )
            mock_table.insert.return_value = mock_insert

        _table_cache[name] = mock_table
        return mock_table

    mock_client.table = table_router
    return mock_client


# =============================================================
# classify_action_risk tests
# =============================================================


class TestClassifyActionRisk:
    """Tests for action risk classification."""

    def test_research_is_low_risk(self) -> None:
        """Research actions should be classified as low risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("research", {})
            assert result == "low"

    def test_signal_detection_is_low_risk(self) -> None:
        """Signal detection should be classified as low risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("signal_detection", {})
            assert result == "low"

    def test_briefing_generation_is_low_risk(self) -> None:
        """Briefing generation should be classified as low risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("briefing_generation", {})
            assert result == "low"

    def test_email_drafting_is_medium_risk(self) -> None:
        """Email drafting should be classified as medium risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("email_draft", {})
            assert result == "medium"

    def test_meeting_prep_is_medium_risk(self) -> None:
        """Meeting prep should be classified as medium risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("meeting_prep", {})
            assert result == "medium"

    def test_lead_scoring_is_medium_risk(self) -> None:
        """Lead scoring should be classified as medium risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("lead_scoring", {})
            assert result == "medium"

    def test_sending_email_is_high_risk(self) -> None:
        """Sending emails should be classified as high risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("email_send", {})
            assert result == "high"

    def test_crm_update_is_high_risk(self) -> None:
        """CRM updates should be classified as high risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("crm_update", {})
            assert result == "high"

    def test_calendar_modification_is_high_risk(self) -> None:
        """Calendar modifications should be classified as high risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("calendar_modify", {})
            assert result == "high"

    def test_financial_action_is_critical_risk(self) -> None:
        """Financial actions should always be classified as critical risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("financial_action", {})
            assert result == "critical"

    def test_data_deletion_is_critical_risk(self) -> None:
        """Data deletion should always be classified as critical risk."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("data_deletion", {})
            assert result == "critical"

    def test_unknown_action_defaults_to_high_risk(self) -> None:
        """Unknown action types should default to high risk for safety."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_db_class.get_client.return_value = MagicMock()
            service = AutonomyCalibrationService()
            result = service.classify_action_risk("some_unknown_action", {})
            assert result == "high"


# =============================================================
# should_auto_execute tests
# =============================================================


class TestShouldAutoExecute:
    """Tests for auto-execution decision logic."""

    @pytest.mark.asyncio
    async def test_level_1_never_auto_executes(self) -> None:
        """Level 1 (New) should ask before every action."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 1},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "research", {}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_level_2_blocks_high_risk(self) -> None:
        """Level 2 (Learning) should ask before high-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 2},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "email_send", {}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_level_2_auto_executes_low_risk(self) -> None:
        """Level 2 (Learning) should auto-execute low-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 2},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "research", {}
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_level_3_auto_executes_low_risk(self) -> None:
        """Level 3 (Trusted) should auto-execute low-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 3},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "research", {}
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_level_3_blocks_medium_risk(self) -> None:
        """Level 3 (Trusted) should ask for medium-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 3},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "email_draft", {}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_level_4_auto_executes_medium_risk(self) -> None:
        """Level 4 (Autonomous) should auto-execute medium-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 4},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "email_draft", {}
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_level_4_blocks_high_risk(self) -> None:
        """Level 4 (Autonomous) should ask for high-risk actions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 4},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "email_send", {}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_level_5_auto_executes_everything(self) -> None:
        """Level 5 (Full Trust) should auto-execute everything."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 5},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "email_send", {}
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_level_5_blocks_critical_risk(self) -> None:
        """Level 5 should still block critical-risk actions (always ask)."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 5},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.should_auto_execute(
                "user-001", "financial_action", {}
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_critical_risk_always_blocked_at_any_level(self) -> None:
        """Critical risk actions should always require approval at any level."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            for level in range(1, 6):
                mock_client = _build_db_mock(
                    user_settings={
                        "user_id": "user-001",
                        "preferences": {"autonomy_level": level},
                    },
                )
                mock_db_class.get_client.return_value = mock_client
                service = AutonomyCalibrationService()

                result = await service.should_auto_execute(
                    "user-001", "data_deletion", {}
                )
                assert result is False, (
                    f"Critical action should be blocked at level {level}"
                )

    @pytest.mark.asyncio
    async def test_logs_decision(self) -> None:
        """Auto-execute decisions should be logged to autonomy_decisions."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_settings={
                    "user_id": "user-001",
                    "preferences": {"autonomy_level": 3},
                },
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            await service.should_auto_execute("user-001", "research", {})

            # Verify insert was called on autonomy_decisions table
            mock_client.table("autonomy_decisions").insert.assert_called_once()
            insert_data = mock_client.table(
                "autonomy_decisions"
            ).insert.call_args.args[0]
            assert insert_data["user_id"] == "user-001"
            assert insert_data["action_type"] == "research"
            assert insert_data["risk_level"] == "low"
            assert insert_data["autonomy_level"] == 3
            assert "auto_execute" in insert_data


# =============================================================
# calculate_autonomy_level tests
# =============================================================


class TestCalculateAutonomyLevel:
    """Tests for autonomy level calculation from real user data."""

    @pytest.mark.asyncio
    async def test_new_user_gets_level_1(self) -> None:
        """A brand-new user with no history should get level 1."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_profile={
                    "id": "user-new",
                    "created_at": datetime.now(UTC).isoformat(),
                },
                action_records=[],
                feedback_records=[],
                email_drafts=[],
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-new")
            assert result["level"] == 1
            assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_experienced_user_with_high_approval_gets_higher_level(
        self,
        mock_user_profile: dict[str, Any],
        mock_action_stats: list[dict[str, Any]],
        mock_feedback_records: list[dict[str, Any]],
        mock_email_drafts: list[dict[str, Any]],
    ) -> None:
        """User with 90 days, good approval rate, good feedback should get level 3+."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_profile=mock_user_profile,
                action_records=mock_action_stats,
                feedback_records=mock_feedback_records,
                email_drafts=mock_email_drafts,
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-001")
            assert result["level"] >= 3
            assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_user_with_many_rejections_gets_lower_level(self) -> None:
        """User with high rejection rate should get a lower level."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            # Lots of rejections
            action_records = [
                {"id": f"a{i}", "status": "rejected", "risk_level": "medium"}
                for i in range(8)
            ] + [
                {"id": "a9", "status": "completed", "risk_level": "low"},
                {"id": "a10", "status": "completed", "risk_level": "low"},
            ]
            mock_client = _build_db_mock(
                user_profile={
                    "id": "user-002",
                    "created_at": (
                        datetime.now(UTC) - timedelta(days=60)
                    ).isoformat(),
                },
                action_records=action_records,
                feedback_records=[
                    {"id": "f1", "rating": "down", "type": "response"},
                    {"id": "f2", "rating": "down", "type": "response"},
                ],
                email_drafts=[
                    {"id": "d1", "user_action": "rejected"},
                    {"id": "d2", "user_action": "rejected"},
                    {"id": "d3", "user_action": "rejected"},
                ],
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-002")
            assert result["level"] <= 2

    @pytest.mark.asyncio
    async def test_level_clamped_between_1_and_5(self) -> None:
        """Calculated level should always be between 1 and 5."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            # Very experienced, perfect record
            many_completed = [
                {"id": f"a{i}", "status": "completed", "risk_level": "high"}
                for i in range(100)
            ]
            mock_client = _build_db_mock(
                user_profile={
                    "id": "user-003",
                    "created_at": (
                        datetime.now(UTC) - timedelta(days=365)
                    ).isoformat(),
                },
                action_records=many_completed,
                feedback_records=[
                    {"id": f"f{i}", "rating": "up", "type": "response"}
                    for i in range(50)
                ],
                email_drafts=[
                    {"id": f"d{i}", "user_action": "approved"}
                    for i in range(50)
                ],
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-003")
            assert 1 <= result["level"] <= 5

    @pytest.mark.asyncio
    async def test_returns_reasoning_string(self) -> None:
        """Result should include a human-readable reasoning explanation."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = _build_db_mock(
                user_profile={
                    "id": "user-004",
                    "created_at": (
                        datetime.now(UTC) - timedelta(days=30)
                    ).isoformat(),
                },
                action_records=[],
                feedback_records=[],
                email_drafts=[],
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-004")
            assert isinstance(result["reasoning"], str)
            assert len(result["reasoning"]) > 0

    @pytest.mark.asyncio
    async def test_high_error_rate_lowers_level(self) -> None:
        """High failure rate in actions should lower the calculated level."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            # Half the actions failed
            action_records = [
                {"id": f"a{i}", "status": "failed", "risk_level": "low"}
                for i in range(5)
            ] + [
                {"id": f"b{i}", "status": "completed", "risk_level": "low"}
                for i in range(5)
            ]
            mock_client = _build_db_mock(
                user_profile={
                    "id": "user-005",
                    "created_at": (
                        datetime.now(UTC) - timedelta(days=90)
                    ).isoformat(),
                },
                action_records=action_records,
                feedback_records=[
                    {"id": "f1", "rating": "up", "type": "response"},
                ],
                email_drafts=[
                    {"id": "d1", "user_action": "approved"},
                ],
            )
            mock_db_class.get_client.return_value = mock_client
            service = AutonomyCalibrationService()

            result = await service.calculate_autonomy_level("user-005")
            # High error rate should keep it low
            assert result["level"] <= 3


# =============================================================
# record_action_outcome tests
# =============================================================


class TestRecordActionOutcome:
    """Tests for recording action outcomes to calibration data."""

    @pytest.mark.asyncio
    async def test_records_successful_outcome(self) -> None:
        """Should update the aria_action_queue with outcome data."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_update = MagicMock()
            mock_eq = MagicMock()
            mock_eq.execute.return_value = MagicMock(
                data=[{"id": "action-001", "status": "completed"}],
            )
            mock_update.eq.return_value = mock_eq
            mock_table.update.return_value = mock_update
            mock_client.table.return_value = mock_table
            mock_db_class.get_client.return_value = mock_client

            service = AutonomyCalibrationService()
            result = await service.record_action_outcome(
                "action-001", "success"
            )

            assert result is not None
            mock_table.update.assert_called_once()
            update_data = mock_table.update.call_args.args[0]
            assert update_data["outcome"] == "success"

    @pytest.mark.asyncio
    async def test_records_failure_outcome(self) -> None:
        """Should record failure outcomes for calibration."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_update = MagicMock()
            mock_eq = MagicMock()
            mock_eq.execute.return_value = MagicMock(
                data=[{"id": "action-002", "status": "failed"}],
            )
            mock_update.eq.return_value = mock_eq
            mock_table.update.return_value = mock_update
            mock_client.table.return_value = mock_table
            mock_db_class.get_client.return_value = mock_client

            service = AutonomyCalibrationService()
            result = await service.record_action_outcome(
                "action-002", "failure"
            )

            assert result is not None
            update_data = mock_table.update.call_args.args[0]
            assert update_data["outcome"] == "failure"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_action(self) -> None:
        """Should return None if the action doesn't exist."""
        from src.services.autonomy_calibration import AutonomyCalibrationService

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ) as mock_db_class:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_update = MagicMock()
            mock_eq = MagicMock()
            mock_eq.execute.return_value = MagicMock(data=[])
            mock_update.eq.return_value = mock_eq
            mock_table.update.return_value = mock_update
            mock_client.table.return_value = mock_table
            mock_db_class.get_client.return_value = mock_client

            service = AutonomyCalibrationService()
            result = await service.record_action_outcome(
                "nonexistent", "success"
            )

            assert result is None


# =============================================================
# Singleton getter tests
# =============================================================


class TestGetAutonomyCalibrationService:
    """Tests for the singleton getter function."""

    def test_returns_same_instance(self) -> None:
        """get_autonomy_calibration_service should return a singleton."""
        from src.services.autonomy_calibration import (
            get_autonomy_calibration_service,
        )

        with patch(
            "src.services.autonomy_calibration.SupabaseClient"
        ):
            import src.services.autonomy_calibration as module

            module._autonomy_calibration_service = None

            service1 = get_autonomy_calibration_service()
            service2 = get_autonomy_calibration_service()

            assert service1 is service2

            # Clean up
            module._autonomy_calibration_service = None
