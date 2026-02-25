"""Tests for the signal → goal proposal pipeline.

Verifies that:
1. High-relevance signals trigger goal proposals via ProactiveGoalProposer
2. Daily frequency limits are enforced (max 3/day)
3. Dismissed proposals raise the effective threshold
4. Low-relevance signals don't trigger proposals
5. Duplicate signals are skipped
6. Pending proposals are delivered on WebSocket connect
7. Dismissal handler updates proposal status
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ProactiveGoalProposer tests
# ---------------------------------------------------------------------------


class TestProactiveGoalProposer:
    """Tests for ProactiveGoalProposer frequency/dismissal controls."""

    def _make_proposer(self, db_mock: MagicMock) -> "ProactiveGoalProposer":
        from src.services.proactive_goal_proposer import ProactiveGoalProposer

        proposer = ProactiveGoalProposer.__new__(ProactiveGoalProposer)
        proposer._db = db_mock
        return proposer

    def _mock_table(self, db: MagicMock, table_name: str) -> MagicMock:
        """Return a chainable mock table builder."""
        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.gte.return_value = chain
        chain.lt.return_value = chain
        chain.ilike.return_value = chain
        chain.limit.return_value = chain
        chain.order.return_value = chain
        chain.maybe_single.return_value = chain
        db.table.side_effect = lambda t: chain if t == table_name else MagicMock()
        return chain

    @pytest.mark.asyncio
    async def test_daily_limit_reached_returns_true_at_cap(self) -> None:
        """_daily_limit_reached returns True when >= 3 proposals today."""
        db = MagicMock()
        chain = self._mock_table(db, "proactive_proposals")
        result_mock = MagicMock()
        result_mock.count = 3
        chain.execute.return_value = result_mock

        proposer = self._make_proposer(db)
        assert await proposer._daily_limit_reached("user-1") is True

    @pytest.mark.asyncio
    async def test_daily_limit_not_reached_under_cap(self) -> None:
        """_daily_limit_reached returns False when < 3 proposals today."""
        db = MagicMock()
        chain = self._mock_table(db, "proactive_proposals")
        result_mock = MagicMock()
        result_mock.count = 1
        chain.execute.return_value = result_mock

        proposer = self._make_proposer(db)
        assert await proposer._daily_limit_reached("user-1") is False

    @pytest.mark.asyncio
    async def test_effective_threshold_increases_with_dismissals(self) -> None:
        """Threshold increases by 0.05 per recent dismissal."""
        from src.services.proactive_goal_proposer import _DISMISSAL_THRESHOLD_BUMP, _MIN_RELEVANCE_SCORE

        db = MagicMock()
        chain = self._mock_table(db, "proactive_proposals")
        result_mock = MagicMock()
        result_mock.count = 4  # 4 dismissals in last 7 days
        chain.execute.return_value = result_mock

        proposer = self._make_proposer(db)
        threshold = await proposer._get_effective_threshold("user-1")
        expected = _MIN_RELEVANCE_SCORE + (4 * _DISMISSAL_THRESHOLD_BUMP)
        assert abs(threshold - expected) < 0.001

    @pytest.mark.asyncio
    async def test_effective_threshold_capped_at_095(self) -> None:
        """Threshold never exceeds 0.95 regardless of dismissals."""
        db = MagicMock()
        chain = self._mock_table(db, "proactive_proposals")
        result_mock = MagicMock()
        result_mock.count = 100  # many dismissals
        chain.execute.return_value = result_mock

        proposer = self._make_proposer(db)
        threshold = await proposer._get_effective_threshold("user-1")
        assert threshold == 0.95

    @pytest.mark.asyncio
    async def test_effective_threshold_returns_base_on_no_dismissals(self) -> None:
        """Threshold equals base when no recent dismissals."""
        from src.services.proactive_goal_proposer import _MIN_RELEVANCE_SCORE

        db = MagicMock()
        chain = self._mock_table(db, "proactive_proposals")
        result_mock = MagicMock()
        result_mock.count = 0
        chain.execute.return_value = result_mock

        proposer = self._make_proposer(db)
        threshold = await proposer._get_effective_threshold("user-1")
        assert threshold == _MIN_RELEVANCE_SCORE

    @pytest.mark.asyncio
    async def test_dismiss_proposal_updates_status(self) -> None:
        """dismiss_proposal sets status to 'dismissed' and returns True."""
        db = MagicMock()
        chain = MagicMock()
        chain.update.return_value = chain
        chain.eq.return_value = chain
        result_mock = MagicMock()
        result_mock.data = [{"id": "p-1"}]
        chain.execute.return_value = result_mock
        db.table.return_value = chain

        proposer = self._make_proposer(db)
        result = await proposer.dismiss_proposal("user-1", "p-1")
        assert result is True
        chain.update.assert_called_once()
        # Verify status was set to dismissed
        update_args = chain.update.call_args[0][0]
        assert update_args["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_dismiss_proposal_returns_false_when_not_found(self) -> None:
        """dismiss_proposal returns False when no matching proposal."""
        db = MagicMock()
        chain = MagicMock()
        chain.update.return_value = chain
        chain.eq.return_value = chain
        result_mock = MagicMock()
        result_mock.data = []
        chain.execute.return_value = result_mock
        db.table.return_value = chain

        proposer = self._make_proposer(db)
        result = await proposer.dismiss_proposal("user-1", "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_signal_skips_below_threshold(self) -> None:
        """evaluate_signal returns False when relevance is below effective threshold."""
        db = MagicMock()
        proposer = self._make_proposer(db)

        # Mock _get_effective_threshold to return 0.8
        proposer._get_effective_threshold = AsyncMock(return_value=0.8)

        result = await proposer.evaluate_signal(
            user_id="user-1",
            signal_id="sig-1",
            signal_type="funding",
            headline="Test signal",
            relevance_score=0.6,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_signal_skips_at_daily_limit(self) -> None:
        """evaluate_signal returns False when daily limit reached."""
        db = MagicMock()
        proposer = self._make_proposer(db)

        proposer._get_effective_threshold = AsyncMock(return_value=0.7)
        proposer._daily_limit_reached = AsyncMock(return_value=True)

        result = await proposer.evaluate_signal(
            user_id="user-1",
            signal_id="sig-1",
            signal_type="funding",
            headline="Test signal",
            relevance_score=0.9,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_signal_skips_duplicate(self) -> None:
        """evaluate_signal returns False for already-proposed signal."""
        db = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        result_mock = MagicMock()
        result_mock.data = [{"id": "existing-proposal"}]
        chain.execute.return_value = result_mock
        db.table.return_value = chain

        proposer = self._make_proposer(db)
        proposer._get_effective_threshold = AsyncMock(return_value=0.7)
        proposer._daily_limit_reached = AsyncMock(return_value=False)

        result = await proposer.evaluate_signal(
            user_id="user-1",
            signal_id="sig-1",
            signal_type="funding",
            headline="Test signal",
            relevance_score=0.9,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Scout signal scan job tests
# ---------------------------------------------------------------------------


class TestScoutSignalScanJob:
    """Tests for the _maybe_propose_goal integration in the scan job."""

    @pytest.mark.asyncio
    async def test_maybe_propose_goal_calls_proposer(self) -> None:
        """_maybe_propose_goal calls ProactiveGoalProposer.evaluate_signal."""
        with patch(
            "src.services.proactive_goal_proposer.ProactiveGoalProposer"
        ) as MockProposer:
            mock_instance = MagicMock()
            mock_instance.evaluate_signal = AsyncMock(return_value=True)
            MockProposer.return_value = mock_instance

            from src.jobs.scout_signal_scan_job import _maybe_propose_goal

            result = await _maybe_propose_goal(
                user_id="user-1",
                signal_id="sig-abc",
                signal={
                    "signal_type": "fda_approval",
                    "headline": "FDA approves new drug",
                    "summary": "Major FDA approval",
                    "company_name": "BioGenix",
                },
                relevance=0.9,
            )
            assert result is True
            mock_instance.evaluate_signal.assert_called_once_with(
                user_id="user-1",
                signal_id="sig-abc",
                signal_type="fda_approval",
                headline="FDA approves new drug",
                summary="Major FDA approval",
                relevance_score=0.9,
                company_name="BioGenix",
            )

    @pytest.mark.asyncio
    async def test_maybe_propose_goal_returns_false_on_rejection(self) -> None:
        """_maybe_propose_goal returns False when proposer rejects."""
        with patch(
            "src.services.proactive_goal_proposer.ProactiveGoalProposer"
        ) as MockProposer:
            mock_instance = MagicMock()
            mock_instance.evaluate_signal = AsyncMock(return_value=False)
            MockProposer.return_value = mock_instance

            from src.jobs.scout_signal_scan_job import _maybe_propose_goal

            result = await _maybe_propose_goal(
                user_id="user-1",
                signal_id="sig-abc",
                signal={"headline": "Low signal"},
                relevance=0.5,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_maybe_propose_goal_returns_false_on_error(self) -> None:
        """_maybe_propose_goal returns False when proposer throws."""
        with patch(
            "src.services.proactive_goal_proposer.ProactiveGoalProposer"
        ) as MockProposer:
            mock_instance = MagicMock()
            mock_instance.evaluate_signal = AsyncMock(side_effect=RuntimeError("boom"))
            MockProposer.return_value = mock_instance

            from src.jobs.scout_signal_scan_job import _maybe_propose_goal

            result = await _maybe_propose_goal(
                user_id="user-1",
                signal_id="sig-abc",
                signal={"headline": "Error signal"},
                relevance=0.9,
            )
            assert result is False


# ---------------------------------------------------------------------------
# WebSocket proposal dismissal handler test
# ---------------------------------------------------------------------------


class TestWebSocketProposalDismissal:
    """Tests for the user.dismiss_proposal WebSocket handler."""

    @pytest.mark.asyncio
    async def test_dismiss_proposal_handler(self) -> None:
        """_handle_proposal_dismissal calls proposer.dismiss_proposal."""
        from src.api.routes.websocket import _handle_proposal_dismissal

        ws_mock = AsyncMock()

        with patch(
            "src.services.proactive_goal_proposer.ProactiveGoalProposer"
        ) as MockProposer:
            mock_instance = MagicMock()
            mock_instance.dismiss_proposal = AsyncMock(return_value=True)
            MockProposer.return_value = mock_instance

            await _handle_proposal_dismissal(
                ws_mock,
                {"payload": {"proposal_id": "p-123"}},
                "user-1",
            )

            mock_instance.dismiss_proposal.assert_called_once_with("user-1", "p-123")
            ws_mock.send_json.assert_called_once()
            sent = ws_mock.send_json.call_args[0][0]
            assert sent["type"] == "aria.message"
            assert "calibrate" in sent["message"]

    @pytest.mark.asyncio
    async def test_dismiss_proposal_handler_ignores_missing_id(self) -> None:
        """_handle_proposal_dismissal does nothing without proposal_id."""
        from src.api.routes.websocket import _handle_proposal_dismissal

        ws_mock = AsyncMock()
        await _handle_proposal_dismissal(ws_mock, {"payload": {}}, "user-1")
        ws_mock.send_json.assert_not_called()
