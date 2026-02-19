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
    ACTION_EXECUTED = "action.executed_with_undo"
    ACTION_UNDONE = "action.undone"
    STEP_STARTED = "execution.step_started"
    STEP_COMPLETED = "execution.step_completed"
    STEP_RETRYING = "execution.step_retrying"
    EXECUTION_COMPLETE = "execution.complete"
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


class StepStartedEvent(WSEvent):
    """An execution step has started."""

    type: WSEventType = WSEventType.STEP_STARTED
    goal_id: str
    step_id: str
    agent: str
    title: str


class StepCompletedEvent(WSEvent):
    """An execution step has completed (success or failure)."""

    type: WSEventType = WSEventType.STEP_COMPLETED
    goal_id: str
    step_id: str
    agent: str
    success: bool
    result_summary: str | None = None
    error_message: str | None = None


class StepRetryingEvent(WSEvent):
    """An execution step is being retried."""

    type: WSEventType = WSEventType.STEP_RETRYING
    goal_id: str
    step_id: str
    agent: str
    retry_count: int
    reason: str


class ExecutionCompleteEvent(WSEvent):
    """An entire goal execution has completed."""

    type: WSEventType = WSEventType.EXECUTION_COMPLETE
    goal_id: str
    title: str
    success: bool
    steps_completed: int
    steps_total: int
    summary: str | None = None


class ConnectedEvent(WSEvent):
    """Connection established confirmation."""

    type: WSEventType = WSEventType.CONNECTED
    user_id: str
    session_id: str | None = None


class ActionExecutedEvent(WSEvent):
    """An action was executed with an undo window."""

    type: WSEventType = WSEventType.ACTION_EXECUTED
    action_id: str
    title: str
    agent: str
    undo_deadline: str  # ISO timestamp
    countdown_seconds: int = 300


class ActionUndoneEvent(WSEvent):
    """An action was undone within the undo window."""

    type: WSEventType = WSEventType.ACTION_UNDONE
    action_id: str
    title: str
    success: bool
    message: str | None = None


class PongEvent(WSEvent):
    """Heartbeat pong response."""

    type: WSEventType = WSEventType.PONG
