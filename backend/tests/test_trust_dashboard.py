"""Tests for trust dashboard service methods."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.core.trust import TrustCalibrationService, TrustProfile


@pytest.fixture
def service() -> TrustCalibrationService:
    return TrustCalibrationService()


@pytest.fixture
def mock_client():
    with patch("src.db.supabase.SupabaseClient") as mock_cls:
        client = MagicMock()
        mock_cls.get_client.return_value = client
        yield client


class TestGetAllProfiles:
    @pytest.mark.asyncio
    async def test_returns_all_profiles(self, service, mock_client) -> None:
        rows = [
            {"user_id": "u1", "action_category": "email_send", "trust_score": 0.7,
             "successful_actions": 20, "failed_actions": 2, "override_count": 1,
             "last_failure_at": None, "last_override_at": None},
            {"user_id": "u1", "action_category": "crm_update", "trust_score": 0.4,
             "successful_actions": 5, "failed_actions": 1, "override_count": 0,
             "last_failure_at": None, "last_override_at": None},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)
        result = await service.get_all_profiles("u1")
        assert len(result) == 2
        assert result[0].action_category == "email_send"
        assert result[1].trust_score == 0.4

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_profiles(self, service, mock_client) -> None:
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        result = await service.get_all_profiles("u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, service, mock_client) -> None:
        mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("db down")
        result = await service.get_all_profiles("u1")
        assert result == []


class TestGetTrustHistory:
    @pytest.mark.asyncio
    async def test_returns_history_for_category(self, service, mock_client) -> None:
        rows = [
            {"recorded_at": "2026-02-17T10:00:00Z", "trust_score": 0.5,
             "change_type": "success", "action_category": "email_send"},
        ]
        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=rows)
        result = await service.get_trust_history("u1", category="email_send")
        assert len(result) == 1
        assert result[0]["trust_score"] == 0.5

    @pytest.mark.asyncio
    async def test_returns_all_categories_history(self, service, mock_client) -> None:
        rows = [
            {"recorded_at": "2026-02-17T10:00:00Z", "trust_score": 0.5,
             "change_type": "success", "action_category": "email_send"},
            {"recorded_at": "2026-02-17T11:00:00Z", "trust_score": 0.6,
             "change_type": "success", "action_category": "crm_update"},
        ]
        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=rows)
        result = await service.get_trust_history("u1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, service, mock_client) -> None:
        mock_client.table.return_value.select.return_value.eq.side_effect = Exception("fail")
        result = await service.get_trust_history("u1")
        assert result == []


class TestRecordHistory:
    @pytest.mark.asyncio
    async def test_inserts_history_row(self, service, mock_client) -> None:
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])
        await service._record_history("u1", "email_send", 0.72, "success")
        mock_client.table.assert_called_with("trust_score_history")
        mock_client.table.return_value.insert.assert_called_once()
        call_args = mock_client.table.return_value.insert.call_args[0][0]
        assert call_args["user_id"] == "u1"
        assert call_args["action_category"] == "email_send"
        assert call_args["trust_score"] == 0.72
        assert call_args["change_type"] == "success"

    @pytest.mark.asyncio
    async def test_silently_handles_error(self, service, mock_client) -> None:
        mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("db error")
        # Should not raise
        await service._record_history("u1", "email_send", 0.72, "success")
