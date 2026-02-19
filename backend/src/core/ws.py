"""WebSocket ConnectionManager for ARIA real-time communication."""

import logging
from typing import Any

from fastapi import WebSocket

from src.models.ws_events import (
    ActionExecutedEvent,
    ActionPendingEvent,
    ActionUndoneEvent,
    AriaMessageEvent,
    ProgressUpdateEvent,
    SignalEvent,
    ThinkingEvent,
    WSEvent,
)

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per user.

    Tracks connections by user_id, supports broadcasting typed events
    to all of a user's active connections (multiple tabs/devices).
    Automatically removes dead connections on send failure.
    """

    def __init__(self) -> None:
        """Initialize with empty connection registry."""
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(
        self,
        user_id: str,
        websocket: WebSocket,
        session_id: str | None = None,
    ) -> None:
        """Register a new WebSocket connection for a user.

        Args:
            user_id: The authenticated user's ID.
            websocket: The WebSocket connection to track.
            session_id: Optional session ID for session binding.
        """
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info(
            "WebSocket connected",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "total_connections": len(self._connections[user_id]),
            },
        )

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection for a user.

        Args:
            user_id: The user's ID.
            websocket: The WebSocket connection to remove.
        """
        connections = self._connections.get(user_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections and user_id in self._connections:
            del self._connections[user_id]
        logger.info(
            "WebSocket disconnected",
            extra={
                "user_id": user_id,
                "remaining": len(self._connections.get(user_id, [])),
            },
        )

    def is_connected(self, user_id: str) -> bool:
        """Check if a user has any active connections.

        Args:
            user_id: The user's ID.

        Returns:
            True if user has at least one active connection.
        """
        return len(self._connections.get(user_id, [])) > 0

    async def send_to_user(self, user_id: str, event: WSEvent) -> None:
        """Send an event to all of a user's active connections.

        Failed sends are caught per-connection and that connection is
        removed from the registry.

        Args:
            user_id: The user to send to.
            event: The WSEvent to serialize and send.
        """
        connections = self._connections.get(user_id, [])
        if not connections:
            return

        dead: list[WebSocket] = []
        data = event.to_ws_dict()

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                logger.warning(
                    "Failed to send WebSocket event, removing dead connection",
                    extra={"user_id": user_id, "event_type": event.type},
                )
                dead.append(ws)

        for ws in dead:
            self.disconnect(user_id, ws)

    # --- Typed send helpers ---

    async def send_aria_message(
        self,
        user_id: str,
        message: str,
        rich_content: list[dict[str, Any]] | None = None,
        ui_commands: list[dict[str, Any]] | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        """Send an ARIA message event with optional rich content and UI commands."""
        event = AriaMessageEvent(
            message=message,
            rich_content=rich_content or [],
            ui_commands=ui_commands or [],
            suggestions=suggestions or [],
        )
        await self.send_to_user(user_id, event)

    async def send_thinking(self, user_id: str) -> None:
        """Send a thinking/processing indicator."""
        await self.send_to_user(user_id, ThinkingEvent())

    async def send_action_pending(
        self,
        user_id: str,
        action_id: str,
        title: str,
        agent: str,
        risk_level: str,
        description: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send an action pending approval event."""
        event = ActionPendingEvent(
            action_id=action_id,
            title=title,
            agent=agent,
            risk_level=risk_level,
            description=description,
            payload=payload or {},
        )
        await self.send_to_user(user_id, event)

    async def send_progress_update(
        self,
        user_id: str,
        goal_id: str,
        progress: int,
        status: str,
        agent_name: str | None = None,
        message: str | None = None,
    ) -> None:
        """Send a goal progress update event."""
        event = ProgressUpdateEvent(
            goal_id=goal_id,
            progress=progress,
            status=status,
            agent_name=agent_name,
            message=message,
        )
        await self.send_to_user(user_id, event)

    async def send_signal(
        self,
        user_id: str,
        signal_type: str,
        title: str,
        severity: str = "medium",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Send an intelligence signal event."""
        event = SignalEvent(
            signal_type=signal_type,
            title=title,
            severity=severity,
            data=data or {},
        )
        await self.send_to_user(user_id, event)

    async def send_action_executed(
        self,
        user_id: str,
        action_id: str,
        title: str,
        agent: str,
        undo_deadline: str,
        countdown_seconds: int = 300,
    ) -> None:
        """Send an action executed with undo window event."""
        event = ActionExecutedEvent(
            action_id=action_id,
            title=title,
            agent=agent,
            undo_deadline=undo_deadline,
            countdown_seconds=countdown_seconds,
        )
        await self.send_to_user(user_id, event)

    async def send_action_undone(
        self,
        user_id: str,
        action_id: str,
        title: str,
        success: bool,
        message: str | None = None,
    ) -> None:
        """Send an action undone confirmation event."""
        event = ActionUndoneEvent(
            action_id=action_id,
            title=title,
            success=success,
            message=message,
        )
        await self.send_to_user(user_id, event)


# Module-level singleton
ws_manager = ConnectionManager()
