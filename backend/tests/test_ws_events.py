"""Tests for WebSocket event models."""

from src.models.ws_events import (
    ActionPendingEvent,
    AriaMessageEvent,
    ConnectedEvent,
    PongEvent,
    ProgressUpdateEvent,
    SignalEvent,
    ThinkingEvent,
    WSEventType,
)


def test_event_type_values():
    assert WSEventType.ARIA_MESSAGE == "aria.message"
    assert WSEventType.THINKING == "aria.thinking"
    assert WSEventType.ACTION_PENDING == "action.pending"
    assert WSEventType.PROGRESS_UPDATE == "progress.update"
    assert WSEventType.SIGNAL_DETECTED == "signal.detected"
    assert WSEventType.CONNECTED == "connected"
    assert WSEventType.PONG == "pong"


def test_aria_message_event_serializes():
    event = AriaMessageEvent(
        message="Here is the battle card",
        rich_content=[{"type": "battle_card", "data": {"name": "Lonza"}}],
        ui_commands=[{"action": "navigate", "route": "/intelligence"}],
        suggestions=["Compare with Catalent"],
    )
    data = event.to_ws_dict()
    assert data["type"] == "aria.message"
    assert data["payload"]["message"] == "Here is the battle card"
    assert len(data["payload"]["rich_content"]) == 1
    assert len(data["payload"]["ui_commands"]) == 1
    assert len(data["payload"]["suggestions"]) == 1


def test_thinking_event_serializes():
    event = ThinkingEvent()
    data = event.to_ws_dict()
    assert data["type"] == "aria.thinking"


def test_action_pending_event_serializes():
    event = ActionPendingEvent(
        action_id="act-123",
        title="Send follow-up email to Lonza",
        agent="scribe",
        risk_level="medium",
        description="Draft and send follow-up email",
    )
    data = event.to_ws_dict()
    assert data["type"] == "action.pending"
    assert data["payload"]["action_id"] == "act-123"
    assert data["payload"]["risk_level"] == "medium"


def test_progress_update_event_serializes():
    event = ProgressUpdateEvent(
        goal_id="goal-456",
        progress=75,
        status="active",
        agent_name="Scout",
        message="Competitive analysis complete",
    )
    data = event.to_ws_dict()
    assert data["type"] == "progress.update"
    assert data["payload"]["progress"] == 75


def test_signal_event_serializes():
    event = SignalEvent(
        signal_type="competitor_news",
        title="Lonza acquires new facility",
        severity="medium",
        data={"source": "reuters", "url": "https://example.com"},
    )
    data = event.to_ws_dict()
    assert data["type"] == "signal.detected"
    assert data["payload"]["signal_type"] == "competitor_news"


def test_connected_event():
    event = ConnectedEvent(user_id="user-1", session_id="sess-1")
    data = event.to_ws_dict()
    assert data["type"] == "connected"
    assert data["payload"]["user_id"] == "user-1"


def test_pong_event():
    event = PongEvent()
    data = event.to_ws_dict()
    assert data["type"] == "pong"


class TestThinkingEventWithAgentContext:
    def test_thinking_event_has_optional_agent_field(self) -> None:
        """ThinkingEvent can include agent name."""
        event = ThinkingEvent(
            is_thinking=True,
            agent="hunter",
        )

        assert event.agent == "hunter"

    def test_thinking_event_has_optional_phase_field(self) -> None:
        """ThinkingEvent can include OODA phase."""
        event = ThinkingEvent(
            is_thinking=True,
            agent="analyst",
            phase="observe",
        )

        assert event.phase == "observe"

    def test_thinking_event_has_optional_progress_field(self) -> None:
        """ThinkingEvent can include progress indicator."""
        event = ThinkingEvent(
            is_thinking=True,
            agent="strategist",
            phase="decide",
            progress=0.5,
        )

        assert event.progress == 0.5

    def test_thinking_event_message_field(self) -> None:
        """ThinkingEvent can include human-readable message."""
        event = ThinkingEvent(
            is_thinking=True,
            message="Hunter agent searching for leads...",
        )

        assert event.message == "Hunter agent searching for leads..."

    def test_thinking_event_serializes_correctly(self) -> None:
        """ThinkingEvent serializes to correct WebSocket dict format."""
        event = ThinkingEvent(
            is_thinking=True,
            message="Analyst processing data...",
            agent="analyst",
            phase="orient",
            progress=0.3,
        )

        ws_dict = event.to_ws_dict()

        assert ws_dict["type"] == "aria.thinking"
        assert ws_dict["payload"]["message"] == "Analyst processing data..."
        assert ws_dict["payload"]["agent"] == "analyst"
        assert ws_dict["payload"]["phase"] == "orient"
        assert ws_dict["payload"]["progress"] == 0.3
