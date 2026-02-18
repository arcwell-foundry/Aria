"""Tests for TrustCalibrationService — per-action-category trust tracking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.trust import (
    APPROVE_EACH,
    APPROVE_PLAN,
    AUTO_EXECUTE,
    DEFAULT_TRUST_SCORE,
    EXECUTE_AND_NOTIFY,
    FAILURE_DECAY_FACTOR,
    OVERRIDE_PENALTY,
    SUCCESS_INCREMENT_FACTOR,
    TrustCalibrationService,
    TrustProfile,
    get_trust_calibration_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase_select(data: dict | None) -> MagicMock:
    """Build a mock Supabase client that returns *data* from a select query."""
    mock_client = MagicMock()
    response = MagicMock()
    response.data = data
    (
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value
    ) = response
    return mock_client


def _mock_supabase_rpc() -> MagicMock:
    """Build a mock Supabase client whose rpc().execute() succeeds."""
    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value = None
    return mock_client


# ---------------------------------------------------------------------------
# TestTrustScoreMath — pure formula verification
# ---------------------------------------------------------------------------


class TestTrustScoreMath:
    """Verify the trust update formulas produce correct values."""

    @pytest.mark.asyncio
    async def test_success_from_default(self) -> None:
        """Success from 0.3 → 0.3 + 0.02*(1-0.3) = 0.314."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.3})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            # First call: get_trust_score (select), second: _call_update_rpc (rpc)
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_success("u1", "email_send")

        expected = 0.3 + SUCCESS_INCREMENT_FACTOR * (1.0 - 0.3)
        assert result == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_success_from_high_score(self) -> None:
        """Success from 0.9 → 0.9 + 0.02*(0.1) = 0.902 (logarithmic slowdown)."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.9})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_success("u1", "email_send")

        expected = 0.9 + SUCCESS_INCREMENT_FACTOR * (1.0 - 0.9)
        assert result == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_success_clamped_at_one(self) -> None:
        """Success from 0.999 should clamp at 1.0."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.999})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_success("u1", "email_send")

        assert result <= 1.0

    @pytest.mark.asyncio
    async def test_failure_from_default(self) -> None:
        """Failure from 0.3 → 0.3 * 0.7 = 0.21."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.3})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_failure("u1", "email_send")

        assert result == pytest.approx(0.3 * FAILURE_DECAY_FACTOR)

    @pytest.mark.asyncio
    async def test_failure_from_high_score(self) -> None:
        """Failure from 0.8 → 0.8 * 0.7 = 0.56."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.8})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_failure("u1", "email_send")

        assert result == pytest.approx(0.8 * FAILURE_DECAY_FACTOR)

    @pytest.mark.asyncio
    async def test_failure_floor_at_zero(self) -> None:
        """Failure from very low score stays >= 0.0."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.001})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_failure("u1", "email_send")

        assert result >= 0.0

    @pytest.mark.asyncio
    async def test_override_from_default(self) -> None:
        """Override from 0.3 → 0.3 - 0.05 = 0.25."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.3})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_override("u1", "email_send")

        assert result == pytest.approx(0.3 - OVERRIDE_PENALTY)

    @pytest.mark.asyncio
    async def test_override_floor_at_zero(self) -> None:
        """Override from 0.02 should clamp at 0.0."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.02})
        rpc_client = _mock_supabase_rpc()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get:
            mock_get.side_effect = [mock_client, rpc_client]
            result = await svc.update_on_override("u1", "email_send")

        assert result == 0.0


# ---------------------------------------------------------------------------
# TestApprovalLevel — all cells of the approval matrix
# ---------------------------------------------------------------------------


class TestApprovalLevel:
    """Verify the trust x risk approval matrix."""

    def test_high_trust_low_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.9, 0.1)
        assert result == AUTO_EXECUTE

    def test_high_trust_medium_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.9, 0.4)
        assert result == EXECUTE_AND_NOTIFY

    def test_high_trust_high_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.9, 0.7)
        assert result == APPROVE_PLAN

    def test_medium_trust_low_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.6, 0.1)
        assert result == EXECUTE_AND_NOTIFY

    def test_medium_trust_medium_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.6, 0.4)
        assert result == APPROVE_PLAN

    def test_medium_trust_high_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.6, 0.7)
        assert result == APPROVE_EACH

    def test_low_trust_low_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.3, 0.1)
        assert result == APPROVE_PLAN

    def test_low_trust_high_risk(self) -> None:
        result = TrustCalibrationService._compute_approval_level(0.3, 0.7)
        assert result == APPROVE_EACH

    def test_new_category_default_is_at_least_approve_plan(self) -> None:
        """Default trust (0.3) should always require at least APPROVE_PLAN."""
        result = TrustCalibrationService._compute_approval_level(DEFAULT_TRUST_SCORE, 0.1)
        assert result in (APPROVE_PLAN, APPROVE_EACH)


# ---------------------------------------------------------------------------
# TestTrustEvolution — multi-step scenarios
# ---------------------------------------------------------------------------


class TestTrustEvolution:
    """Verify multi-step trust evolution patterns."""

    def test_ten_successes_increases_but_stays_below_one(self) -> None:
        """10 consecutive successes from 0.3 should increase but stay < 1.0."""
        score = DEFAULT_TRUST_SCORE
        for _ in range(10):
            score = min(1.0, score + SUCCESS_INCREMENT_FACTOR * (1.0 - score))
        assert score > DEFAULT_TRUST_SCORE
        assert score < 1.0

    def test_failure_then_slow_recovery(self) -> None:
        """A failure followed by successes: trust recovers but slowly."""
        score = 0.8
        # Failure
        score = max(0.0, score * FAILURE_DECAY_FACTOR)
        assert score == pytest.approx(0.56)
        # 5 successes
        for _ in range(5):
            score = min(1.0, score + SUCCESS_INCREMENT_FACTOR * (1.0 - score))
        # Should still be below the original 0.8
        assert score < 0.8

    def test_alternating_success_failure_converges(self) -> None:
        """Alternating success/failure should converge to a stable range."""
        score = DEFAULT_TRUST_SCORE
        scores = []
        for i in range(20):
            if i % 2 == 0:
                score = min(1.0, score + SUCCESS_INCREMENT_FACTOR * (1.0 - score))
            else:
                score = max(0.0, score * FAILURE_DECAY_FACTOR)
            scores.append(score)
        # Last 4 scores should be within a narrow band
        last_four = scores[-4:]
        assert max(last_four) - min(last_four) < 0.1


# ---------------------------------------------------------------------------
# TestGetTrustScore — DB interaction with mocks
# ---------------------------------------------------------------------------


class TestGetTrustScore:
    """Verify get_trust_score DB interaction and fail-open behavior."""

    @pytest.mark.asyncio
    async def test_returns_score_from_db(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select({"trust_score": 0.75})

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.get_trust_score("u1", "email_send")

        assert result == 0.75

    @pytest.mark.asyncio
    async def test_returns_default_when_no_row(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(None)

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.get_trust_score("u1", "email_send")

        assert result == DEFAULT_TRUST_SCORE

    @pytest.mark.asyncio
    async def test_returns_default_on_db_error(self) -> None:
        """Fail-open: DB errors should return default score, not raise."""
        svc = TrustCalibrationService()

        with patch(
            "src.db.supabase.SupabaseClient.get_client",
            side_effect=RuntimeError("DB down"),
        ):
            result = await svc.get_trust_score("u1", "email_send")

        assert result == DEFAULT_TRUST_SCORE


# ---------------------------------------------------------------------------
# TestCanRequestAutonomyUpgrade
# ---------------------------------------------------------------------------


class TestCanRequestAutonomyUpgrade:
    """Verify autonomy upgrade eligibility checks."""

    @pytest.mark.asyncio
    async def test_eligible_with_good_record(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(
            {
                "user_id": "u1",
                "action_category": "email_send",
                "trust_score": 0.7,
                "successful_actions": 15,
                "failed_actions": 1,
                "override_count": 0,
                "last_failure_at": None,
                "last_override_at": None,
            }
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.can_request_autonomy_upgrade("u1", "email_send")

        assert result is True

    @pytest.mark.asyncio
    async def test_not_eligible_too_few_successes(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(
            {
                "user_id": "u1",
                "action_category": "email_send",
                "trust_score": 0.7,
                "successful_actions": 5,
                "failed_actions": 0,
                "override_count": 0,
                "last_failure_at": None,
                "last_override_at": None,
            }
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.can_request_autonomy_upgrade("u1", "email_send")

        assert result is False

    @pytest.mark.asyncio
    async def test_not_eligible_high_failure_rate(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(
            {
                "user_id": "u1",
                "action_category": "email_send",
                "trust_score": 0.7,
                "successful_actions": 10,
                "failed_actions": 5,
                "override_count": 0,
                "last_failure_at": None,
                "last_override_at": None,
            }
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.can_request_autonomy_upgrade("u1", "email_send")

        assert result is False

    @pytest.mark.asyncio
    async def test_not_eligible_no_profile(self) -> None:
        """Default profile (no DB row) should not be eligible."""
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(None)

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            result = await svc.can_request_autonomy_upgrade("u1", "email_send")

        assert result is False


# ---------------------------------------------------------------------------
# TestFormatAutonomyRequest
# ---------------------------------------------------------------------------


class TestFormatAutonomyRequest:
    """Verify autonomy request message formatting."""

    @pytest.mark.asyncio
    async def test_eligible_message_format(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(
            {
                "user_id": "u1",
                "action_category": "email_send",
                "trust_score": 0.7,
                "successful_actions": 25,
                "failed_actions": 1,
                "override_count": 0,
                "last_failure_at": None,
                "last_override_at": None,
            }
        )

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            msg = await svc.format_autonomy_request("u1", "email_send")

        assert "25" in msg
        assert "email_send" in msg
        assert "96%" in msg

    @pytest.mark.asyncio
    async def test_not_eligible_message(self) -> None:
        svc = TrustCalibrationService()
        mock_client = _mock_supabase_select(None)

        with patch("src.db.supabase.SupabaseClient.get_client", return_value=mock_client):
            msg = await svc.format_autonomy_request("u1", "email_send")

        assert "not yet ready" in msg


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """Verify singleton accessor."""

    def test_returns_same_instance(self) -> None:
        import src.core.trust as trust_mod

        trust_mod._service = None  # reset
        svc1 = get_trust_calibration_service()
        svc2 = get_trust_calibration_service()
        assert svc1 is svc2
        trust_mod._service = None  # cleanup


# ---------------------------------------------------------------------------
# TestTrustProfile dataclass
# ---------------------------------------------------------------------------


class TestTrustProfileDataclass:
    """Verify TrustProfile computed properties."""

    def test_total_actions(self) -> None:
        p = TrustProfile(
            user_id="u1",
            action_category="email_send",
            successful_actions=10,
            failed_actions=2,
        )
        assert p.total_actions == 12

    def test_failure_rate(self) -> None:
        p = TrustProfile(
            user_id="u1",
            action_category="email_send",
            successful_actions=9,
            failed_actions=1,
        )
        assert p.failure_rate == pytest.approx(0.1)

    def test_failure_rate_zero_actions(self) -> None:
        p = TrustProfile(user_id="u1", action_category="email_send")
        assert p.failure_rate == 0.0
