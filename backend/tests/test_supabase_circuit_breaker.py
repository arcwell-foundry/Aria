"""Tests for Supabase client circuit breaker integration."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.circuit_breaker import CircuitBreakerOpen


@pytest.mark.asyncio
async def test_supabase_get_user_opens_circuit_after_failures() -> None:
    """Test that repeated Supabase failures open the circuit breaker."""
    from src.db.supabase import SupabaseClient, _supabase_circuit_breaker

    # Reset circuit state
    _supabase_circuit_breaker.record_success()

    with patch.object(SupabaseClient, "get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = (
            Exception("connection refused")
        )
        mock_get_client.return_value = mock_client

        for _ in range(5):
            with pytest.raises(Exception):
                await SupabaseClient.get_user_by_id("test-id")

        with pytest.raises(CircuitBreakerOpen):
            await SupabaseClient.get_user_by_id("test-id")

    # Reset for other tests
    _supabase_circuit_breaker.record_success()


@pytest.mark.asyncio
async def test_supabase_circuit_resets_on_success() -> None:
    """Test that a successful call resets the circuit breaker."""
    from src.db.supabase import SupabaseClient, _supabase_circuit_breaker

    # Reset circuit state
    _supabase_circuit_breaker.record_success()

    with patch.object(SupabaseClient, "get_client") as mock_get_client:
        mock_client = MagicMock()

        call_count = 0

        def side_effect() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("connection refused")
            result = MagicMock()
            result.data = {"id": "test-id", "full_name": "Test User"}
            return result

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute = side_effect
        mock_get_client.return_value = mock_client

        # 3 failures (under threshold)
        for _ in range(3):
            with pytest.raises(Exception):
                await SupabaseClient.get_user_by_id("test-id")

        # Successful call should reset
        result = await SupabaseClient.get_user_by_id("test-id")
        assert result["id"] == "test-id"
        assert _supabase_circuit_breaker._failure_count == 0

    _supabase_circuit_breaker.record_success()
