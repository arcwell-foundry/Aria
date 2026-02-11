"""Tests for WebSocket ConnectionManager."""

from unittest.mock import AsyncMock

import pytest

from src.core.ws import ConnectionManager
from src.models.ws_events import PongEvent, ThinkingEvent


@pytest.fixture
def manager():
    """Fresh ConnectionManager for each test."""
    mgr = ConnectionManager()
    mgr._connections.clear()
    return mgr


def _make_ws_mock():
    """Create a mock WebSocket with async send_json."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_adds_connection(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws, session_id="sess-1")
    assert "user-1" in manager._connections
    assert ws in manager._connections["user-1"]


@pytest.mark.asyncio
async def test_disconnect_removes_connection(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    manager.disconnect("user-1", ws)
    assert len(manager._connections.get("user-1", [])) == 0


@pytest.mark.asyncio
async def test_disconnect_unknown_user_no_error(manager):
    ws = _make_ws_mock()
    manager.disconnect("nonexistent", ws)  # should not raise


@pytest.mark.asyncio
async def test_send_to_user_broadcasts_to_all_connections(manager):
    ws1 = _make_ws_mock()
    ws2 = _make_ws_mock()
    await manager.connect("user-1", ws1)
    await manager.connect("user-1", ws2)

    event = PongEvent()
    await manager.send_to_user("user-1", event)

    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_send_to_user_removes_dead_connections(manager):
    ws_good = _make_ws_mock()
    ws_dead = _make_ws_mock()
    ws_dead.send_json.side_effect = Exception("connection closed")

    await manager.connect("user-1", ws_good)
    await manager.connect("user-1", ws_dead)

    event = ThinkingEvent()
    await manager.send_to_user("user-1", event)

    # Dead connection should have been removed
    assert ws_dead not in manager._connections["user-1"]
    assert ws_good in manager._connections["user-1"]


@pytest.mark.asyncio
async def test_send_to_nonexistent_user_no_error(manager):
    event = ThinkingEvent()
    await manager.send_to_user("nobody", event)  # should not raise


@pytest.mark.asyncio
async def test_send_aria_message(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)

    await manager.send_aria_message(
        user_id="user-1",
        message="Hello",
        rich_content=[],
        ui_commands=[],
        suggestions=["Ask about pipeline"],
    )

    ws.send_json.assert_called_once()
    sent_data = ws.send_json.call_args[0][0]
    assert sent_data["type"] == "aria.message"
    assert sent_data["message"] == "Hello"


@pytest.mark.asyncio
async def test_send_thinking(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    await manager.send_thinking("user-1")
    sent_data = ws.send_json.call_args[0][0]
    assert sent_data["type"] == "aria.thinking"


@pytest.mark.asyncio
async def test_send_action_pending(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    await manager.send_action_pending(
        user_id="user-1",
        action_id="act-1",
        title="Send email",
        agent="scribe",
        risk_level="high",
        description="Draft outreach email",
    )
    sent_data = ws.send_json.call_args[0][0]
    assert sent_data["type"] == "action.pending"
    assert sent_data["action_id"] == "act-1"


@pytest.mark.asyncio
async def test_send_progress_update(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    await manager.send_progress_update(
        user_id="user-1",
        goal_id="goal-1",
        progress=50,
        status="active",
        agent_name="Scout",
        message="Halfway done",
    )
    sent_data = ws.send_json.call_args[0][0]
    assert sent_data["type"] == "progress.update"
    assert sent_data["goal_id"] == "goal-1"
    assert sent_data["progress"] == 50


@pytest.mark.asyncio
async def test_send_signal(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    await manager.send_signal(
        user_id="user-1",
        signal_type="competitor_news",
        title="Lonza earnings",
        severity="high",
        data={"source": "reuters"},
    )
    sent_data = ws.send_json.call_args[0][0]
    assert sent_data["type"] == "signal.detected"
    assert sent_data["signal_type"] == "competitor_news"


@pytest.mark.asyncio
async def test_multiple_users_isolated(manager):
    ws1 = _make_ws_mock()
    ws2 = _make_ws_mock()
    await manager.connect("user-1", ws1)
    await manager.connect("user-2", ws2)

    await manager.send_thinking("user-1")

    ws1.send_json.assert_called_once()
    ws2.send_json.assert_not_called()


def test_is_connected(manager):
    assert not manager.is_connected("user-1")


@pytest.mark.asyncio
async def test_is_connected_after_connect(manager):
    ws = _make_ws_mock()
    await manager.connect("user-1", ws)
    assert manager.is_connected("user-1")
