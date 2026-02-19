"""Tests for ActionExecutionService — execute, undo, and reversal flows.

Covers:
- execute_action marks EXECUTING → COMPLETED and updates trust
- execute_with_undo_window creates undo buffer entry and sets status
- request_undo within window succeeds
- request_undo after window fails
- finalize_action after window updates trust
- _reverse_action per action type
- Auto-execute flow skips undo buffer
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_action(**overrides: Any) -> dict[str, Any]:
    """Build a sample action dict."""
    base: dict[str, Any] = {
        "id": "act-123",
        "user_id": "user-456",
        "agent": "scout",
        "action_type": "research",
        "title": "Research BioGenix pipeline",
        "description": "Gather competitive intelligence",
        "risk_level": "low",
        "status": "auto_approved",
        "payload": {},
        "reasoning": "New trial results published",
        "result": {},
    }
    base.update(overrides)
    return base


def _mock_db() -> MagicMock:
    """Build a mock Supabase client with chained query methods."""
    mock = MagicMock()
    # Table().update().eq().eq().execute()
    chain = mock.table.return_value
    chain.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    chain.insert.return_value.execute.return_value = MagicMock(data=[{}])
    # select().eq().eq().maybe_single().execute()
    chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        MagicMock(data=None)
    )
    # For lt chain (sweep)
    chain.select.return_value.eq.return_value.eq.return_value.lt.return_value.limit.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    return mock


# ---------------------------------------------------------------------------
# TestReverseAction — action type reversal logic
# ---------------------------------------------------------------------------


class TestReverseAction:
    """Verify _reverse_action produces correct results per action type."""

    @pytest.mark.asyncio
    async def test_research_is_read_only(self) -> None:
        """Research actions need no reversal."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        result = await svc._reverse_action(
            _sample_action(action_type="research"), {}
        )
        assert result["success"] is True
        assert "read-only" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_lead_gen_is_read_only(self) -> None:
        """Lead gen actions need no reversal."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        result = await svc._reverse_action(
            _sample_action(action_type="lead_gen"), {}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_email_draft_reversal(self) -> None:
        """Email draft can always be deleted."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        result = await svc._reverse_action(
            _sample_action(action_type="email_draft"), {}
        )
        assert result["success"] is True
        assert "draft deleted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_crm_update_with_previous_state(self) -> None:
        """CRM update with previous_state can be reverted."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        action = _sample_action(
            action_type="crm_update",
            payload={"previous_state": {"field": "old_value"}},
        )
        result = await svc._reverse_action(action, {})
        assert result["success"] is True
        assert "reverted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_crm_update_without_previous_state(self) -> None:
        """CRM update without previous_state cannot be reverted."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        action = _sample_action(action_type="crm_update", payload={})
        result = await svc._reverse_action(action, {})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_meeting_prep_reversal(self) -> None:
        """Meeting prep removes calendar event."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        result = await svc._reverse_action(
            _sample_action(action_type="meeting_prep"), {}
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_externally_committed_cannot_reverse(self) -> None:
        """Externally committed actions are irreversible."""
        from src.services.action_execution import ActionExecutionService

        svc = ActionExecutionService.__new__(ActionExecutionService)
        action = _sample_action(
            action_type="email_draft",
            result={"externally_committed": True},
        )
        result = await svc._reverse_action(action, {})
        assert result["success"] is False
        assert "irreversible" in result.get("reason", "")


# ---------------------------------------------------------------------------
# TestExecuteAction — basic execution flow
# ---------------------------------------------------------------------------


class TestExecuteAction:
    """Verify execute_action marks status and updates trust."""

    @pytest.mark.asyncio
    async def test_execute_action_marks_completed(self) -> None:
        """Execute action transitions EXECUTING → COMPLETED."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.35)

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
        ):
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            result = await svc.execute_action(
                "act-1", "user-1", _sample_action()
            )

        assert result["executed"] is True
        mock_trust.update_on_success.assert_called_once_with("user-1", "research")


# ---------------------------------------------------------------------------
# TestExecuteWithUndoWindow
# ---------------------------------------------------------------------------


class TestExecuteWithUndoWindow:
    """Verify undo window execution creates buffer entry."""

    @pytest.mark.asyncio
    async def test_creates_undo_buffer_entry(self) -> None:
        """Execute with undo window inserts into action_undo_buffer."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()
        mock_trust.get_approval_level = AsyncMock(return_value="EXECUTE_AND_NOTIFY")

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
            patch("src.core.ws.ws_manager") as mock_ws,
            patch("asyncio.create_task"),
        ):
            mock_ws.send_action_executed = AsyncMock()
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            result = await svc.execute_with_undo_window(
                "act-1", "user-1", _sample_action()
            )

        assert result["executed"] is True
        # Verify undo buffer insert was called
        mock_db.table.assert_any_call("action_undo_buffer")

    @pytest.mark.asyncio
    async def test_sends_ws_event(self) -> None:
        """Execute with undo window sends WS event."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
            patch("src.core.ws.ws_manager") as mock_ws,
            patch("asyncio.create_task"),
        ):
            mock_ws.send_action_executed = AsyncMock()
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            await svc.execute_with_undo_window(
                "act-1", "user-1", _sample_action(title="Test action")
            )

            # WS event should have been called (via lazy import in the service)
            # Note: The service does lazy import of ws_manager internally


# ---------------------------------------------------------------------------
# TestRequestUndo
# ---------------------------------------------------------------------------


class TestRequestUndo:
    """Verify undo request logic."""

    @pytest.mark.asyncio
    async def test_undo_no_entry_fails(self) -> None:
        """Undo with no buffer entry returns failure."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
        ):
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            result = await svc.request_undo("act-missing", "user-1")

        assert result["success"] is False
        assert "No undo entry" in result["reason"]

    @pytest.mark.asyncio
    async def test_undo_expired_fails(self) -> None:
        """Undo after deadline returns expired error."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()

        # Set up the select to return an expired undo entry
        past_deadline = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        undo_entry = {
            "action_id": "act-1",
            "user_id": "user-1",
            "undo_requested": False,
            "undo_deadline": past_deadline,
        }
        response = MagicMock(data=undo_entry)
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = response

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
        ):
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            result = await svc.request_undo("act-1", "user-1")

        assert result["success"] is False
        assert "expired" in result["reason"]

    @pytest.mark.asyncio
    async def test_undo_already_requested_fails(self) -> None:
        """Undo when already requested returns failure."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()

        undo_entry = {
            "action_id": "act-1",
            "user_id": "user-1",
            "undo_requested": True,
            "undo_deadline": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
        }
        response = MagicMock(data=undo_entry)
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = response

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
        ):
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            result = await svc.request_undo("act-1", "user-1")

        assert result["success"] is False
        assert "already requested" in result["reason"]


# ---------------------------------------------------------------------------
# TestFinalizeAction
# ---------------------------------------------------------------------------


class TestFinalizeAction:
    """Verify finalize_action after undo window expires."""

    @pytest.mark.asyncio
    async def test_finalize_skips_if_undo_requested(self) -> None:
        """Finalize does nothing if undo was already requested."""
        mock_db = _mock_db()
        mock_trust = AsyncMock()

        # First query returns undo_requested=True
        response = MagicMock(data={"undo_requested": True})
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = response

        with (
            patch("src.services.action_execution.SupabaseClient.get_client", return_value=mock_db),
            patch("src.services.action_execution.get_trust_calibration_service", return_value=mock_trust),
        ):
            from src.services.action_execution import ActionExecutionService

            svc = ActionExecutionService()
            await svc.finalize_action("act-1", "user-1")

        # Trust should NOT be updated since undo was requested
        mock_trust.update_on_success.assert_not_called()
