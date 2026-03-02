"""Tests for WebSocket server-side keepalive."""
import asyncio
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_server_sends_ping_periodically():
    """Server should send ping frames to keep connection alive."""
    from src.api.routes.websocket import _start_keepalive, _stop_keepalive

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()

    # Start keepalive with a short interval for testing
    task = _start_keepalive(mock_ws, interval=0.1)

    # Let it run for 0.35 seconds (should get ~3 pings)
    await asyncio.sleep(0.35)

    # Stop keepalive
    _stop_keepalive(task)

    # Should have sent multiple pings
    assert mock_ws.send_json.call_count >= 2

    # Each ping should be a proper ping event
    for call in mock_ws.send_json.call_args_list:
        event = call[0][0]
        assert event["type"] == "ping"


@pytest.mark.asyncio
async def test_keepalive_stops_on_cancel():
    """Keepalive should stop cleanly when cancelled."""
    from src.api.routes.websocket import _start_keepalive, _stop_keepalive

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()

    task = _start_keepalive(mock_ws, interval=0.1)
    await asyncio.sleep(0.15)

    _stop_keepalive(task)
    count_at_stop = mock_ws.send_json.call_count

    # Wait more and verify no more pings are sent
    await asyncio.sleep(0.2)
    assert mock_ws.send_json.call_count == count_at_stop


@pytest.mark.asyncio
async def test_keepalive_handles_send_failure():
    """Keepalive should stop gracefully if send fails (connection closed)."""
    from src.api.routes.websocket import _start_keepalive, _stop_keepalive

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

    task = _start_keepalive(mock_ws, interval=0.05)

    # Let it attempt to send
    await asyncio.sleep(0.15)

    # Task should have completed (not still running)
    assert task.done()
    _stop_keepalive(task)  # Should not raise
