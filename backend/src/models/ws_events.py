"""WebSocket event models for ARIA real-time communication."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WSEventType(str, Enum):
    """WebSocket event types matching frontend expectations."""

    ARIA_MESSAGE = "aria.message"
    THINKING = "aria.thinking"
    ACTION_PENDING = "action.pending"
    PROGRESS_UPDATE = "progress.update"
    SIGNAL_DETECTED = "signal.detected"
    ARIA_SPEAKING = "aria.speaking"
    FRICTION_CHALLENGE = "friction.challenge"
    FRICTION_FLAG = "friction.flag"
    ACTION_EXECUTED_WITH_UNDO = "action.executed_with_undo"
    ACTION_UNDO_EXPIRED = "action.undo_expired"
    ACTION_UNDO_COMPLETED = "action.undo_completed"
    CONNECTED = "connected"
    PONG = "pong"


class WSEvent(BaseModel):
    """Base WebSocket event."""

    type: WSEventType

    def to_ws_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON WebSocket transmission."""
        return self.model_dump(mode="json")


class AriaMessageEvent(WSEvent):
    """ARIA sends a message with optional rich content and UI commands."""

    type: WSEventType = WSEventType.ARIA_MESSAGE
    message: str
    rich_content: list[dict[str, Any]] = Field(default_factory=list)
    ui_commands: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ThinkingEvent(WSEvent):
    """ARIA is processing/thinking indicator."""

    type: WSEventType = WSEventType.THINKING


class AriaSpeakingEvent(WSEvent):
    """ARIA avatar speaking state change."""

    type: WSEventType = WSEventType.ARIA_SPEAKING
    is_speaking: bool


class ActionPendingEvent(WSEvent):
    """An action requires user approval."""

    type: WSEventType = WSEventType.ACTION_PENDING
    action_id: str
    title: str
    agent: str
    risk_level: str
    description: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ProgressUpdateEvent(WSEvent):
    """Goal progress update from agent execution."""

    type: WSEventType = WSEventType.PROGRESS_UPDATE
    goal_id: str
    progress: int
    status: str
    agent_name: str | None = None
    message: str | None = None


class SignalEvent(WSEvent):
    """Intelligence signal detected."""

    type: WSEventType = WSEventType.SIGNAL_DETECTED
    signal_type: str
    title: str
    severity: str = "medium"
    data: dict[str, Any] = Field(default_factory=dict)


class ConnectedEvent(WSEvent):
    """Connection established confirmation."""

    type: WSEventType = WSEventType.CONNECTED
    user_id: str
    session_id: str | None = None


class PongEvent(WSEvent):
    """Heartbeat pong response."""

    type: WSEventType = WSEventType.PONG


class FrictionChallengeEvent(WSEvent):
    """Cognitive friction challenge — ARIA pushes back on a user request."""

    type: WSEventType = WSEventType.FRICTION_CHALLENGE
    challenge_id: str
    user_message: str
    reasoning: str
    original_request: str
    proceed_if_confirmed: bool
    conversation_id: str | None = None


class FrictionFlagEvent(WSEvent):
    """Cognitive friction flag — informational concern appended to a response."""

    type: WSEventType = WSEventType.FRICTION_FLAG
    flag_message: str
    message_id: str | None = None


class ActionExecutedWithUndoEvent(WSEvent):
    """An action was executed with an undo window."""

    type: WSEventType = WSEventType.ACTION_EXECUTED_WITH_UNDO
    action_id: str
    title: str
    description: str | None = None
    agent: str
    undo_deadline: str
    undo_duration_seconds: int = 300


class ActionUndoExpiredEvent(WSEvent):
    """The undo window for an action has expired."""

    type: WSEventType = WSEventType.ACTION_UNDO_EXPIRED
    action_id: str


class ActionUndoCompletedEvent(WSEvent):
    """An action was successfully undone."""

    type: WSEventType = WSEventType.ACTION_UNDO_COMPLETED
    action_id: str
    reversal_summary: str | None = None
