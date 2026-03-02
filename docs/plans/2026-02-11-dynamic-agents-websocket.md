# Dynamic Agent Creation & WebSocket Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add dynamic agent creation at runtime and a WebSocket server for real-time ARIA-to-frontend communication.

**Architecture:** WebSocket endpoint at `/ws/{user_id}` with JWT auth and a singleton `ConnectionManager` for broadcasting typed events. `DynamicAgentFactory` creates `SkillAwareAgent` subclasses at runtime from goal context. GoalExecutionService wires into WebSocket to push progress, approval requests, and results. Chat streaming endpoint populates `rich_content`, `ui_commands`, and `suggestions` from LLM analysis.

**Tech Stack:** FastAPI native WebSocket, Pydantic models for event types, Python `type()` for dynamic class creation.

---

### Task 1: WebSocket Event Models

**Files:**
- Create: `backend/src/models/ws_events.py`
- Test: `backend/tests/test_ws_events.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_ws_events.py
"""Tests for WebSocket event models."""

from src.models.ws_events import (
    WSEvent,
    WSEventType,
    AriaMessageEvent,
    ThinkingEvent,
    ActionPendingEvent,
    ProgressUpdateEvent,
    SignalEvent,
    ConnectedEvent,
    PongEvent,
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
    assert data["message"] == "Here is the battle card"
    assert len(data["rich_content"]) == 1
    assert len(data["ui_commands"]) == 1
    assert len(data["suggestions"]) == 1


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
    assert data["action_id"] == "act-123"
    assert data["risk_level"] == "medium"


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
    assert data["progress"] == 75


def test_signal_event_serializes():
    event = SignalEvent(
        signal_type="competitor_news",
        title="Lonza acquires new facility",
        severity="medium",
        data={"source": "reuters", "url": "https://example.com"},
    )
    data = event.to_ws_dict()
    assert data["type"] == "signal.detected"
    assert data["signal_type"] == "competitor_news"


def test_connected_event():
    event = ConnectedEvent(user_id="user-1", session_id="sess-1")
    data = event.to_ws_dict()
    assert data["type"] == "connected"
    assert data["user_id"] == "user-1"


def test_pong_event():
    event = PongEvent()
    data = event.to_ws_dict()
    assert data["type"] == "pong"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_ws_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.ws_events'`

**Step 3: Write minimal implementation**

```python
# backend/src/models/ws_events.py
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_ws_events.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/models/ws_events.py backend/tests/test_ws_events.py
git commit -m "feat: add WebSocket event Pydantic models for real-time communication"
```

---

### Task 2: ConnectionManager

**Files:**
- Create: `backend/src/core/ws.py`
- Test: `backend/tests/test_connection_manager.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_connection_manager.py
"""Tests for WebSocket ConnectionManager."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.ws import ConnectionManager
from src.models.ws_events import AriaMessageEvent, PongEvent, ThinkingEvent


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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_connection_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.ws'`

**Step 3: Write minimal implementation**

```python
# backend/src/core/ws.py
"""WebSocket ConnectionManager for ARIA real-time communication."""

import logging
from typing import Any

from fastapi import WebSocket

from src.models.ws_events import (
    ActionPendingEvent,
    AriaMessageEvent,
    ConnectedEvent,
    PongEvent,
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


# Module-level singleton
ws_manager = ConnectionManager()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_connection_manager.py -v`
Expected: All 14 tests PASS

**Step 5: Commit**

```bash
git add backend/src/core/ws.py backend/tests/test_connection_manager.py
git commit -m "feat: add WebSocket ConnectionManager with typed event broadcasting"
```

---

### Task 3: WebSocket Endpoint & Router

**Files:**
- Create: `backend/src/api/routes/websocket.py`
- Modify: `backend/src/main.py` (add import and router registration)
- Test: `backend/tests/test_websocket_endpoint.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_websocket_endpoint.py
"""Tests for WebSocket endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.routes.websocket import router


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_websocket_rejects_missing_token(client):
    """WebSocket connection without token should be rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/user-1"):
            pass


def test_websocket_rejects_invalid_token(client):
    """WebSocket connection with invalid token should be rejected."""
    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = None  # Auth fails
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/user-1?token=bad-token"):
                pass


def test_websocket_accepts_valid_token(client):
    """WebSocket connection with valid token should be accepted."""
    mock_user = MagicMock()
    mock_user.id = "user-1"

    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = mock_user
        with patch("src.api.routes.websocket.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            with client.websocket_connect("/ws/user-1?token=valid-token") as ws:
                # Should receive connected event
                data = ws.receive_json()
                assert data["type"] == "connected"
                assert data["user_id"] == "user-1"


def test_websocket_ping_pong(client):
    """Client ping should receive pong response."""
    mock_user = MagicMock()
    mock_user.id = "user-1"

    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = mock_user
        with patch("src.api.routes.websocket.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            with client.websocket_connect("/ws/user-1?token=valid-token") as ws:
                # Consume connected event
                ws.receive_json()
                # Send ping
                ws.send_json({"type": "ping"})
                # Should receive pong
                data = ws.receive_json()
                assert data["type"] == "pong"


def test_websocket_rejects_user_id_mismatch(client):
    """Token user_id must match URL user_id."""
    mock_user = MagicMock()
    mock_user.id = "different-user"

    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = mock_user
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/user-1?token=valid-token"):
                pass
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_websocket_endpoint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.routes.websocket'`

**Step 3: Write the WebSocket endpoint**

```python
# backend/src/api/routes/websocket.py
"""WebSocket endpoint for ARIA real-time communication."""

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.core.ws import ws_manager
from src.models.ws_events import ConnectedEvent, PongEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _authenticate_ws_token(token: str) -> Any | None:
    """Validate a JWT token for WebSocket authentication.

    Args:
        token: The JWT token from query parameter.

    Returns:
        User object if valid, None if invalid.
    """
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        response = client.auth.get_user(token)
        if response is None or response.user is None:
            return None
        return response.user
    except Exception as e:
        logger.warning("WebSocket auth failed: %s", e)
        return None


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str | None = None,
    session_id: str | None = None,
) -> None:
    """WebSocket endpoint for real-time ARIA communication.

    Args:
        websocket: The WebSocket connection.
        user_id: User ID from URL path.
        token: JWT token for authentication (query param).
        session_id: Optional session ID for session binding (query param).
    """
    # Require token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Authenticate
    user = await _authenticate_ws_token(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify user_id matches token
    if user.id != user_id:
        logger.warning(
            "WebSocket user_id mismatch",
            extra={"url_user_id": user_id, "token_user_id": user.id},
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept connection
    await websocket.accept()
    await ws_manager.connect(user_id, websocket, session_id=session_id)

    # Send connected confirmation
    connected_event = ConnectedEvent(user_id=user_id, session_id=session_id)
    try:
        await websocket.send_json(connected_event.to_ws_dict())
    except Exception:
        ws_manager.disconnect(user_id, websocket)
        return

    # Message loop
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                pong = PongEvent()
                await websocket.send_json(pong.to_ws_dict())

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected",
            extra={"user_id": user_id, "session_id": session_id},
        )
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={"user_id": user_id, "error": str(e)},
        )
    finally:
        ws_manager.disconnect(user_id, websocket)
```

**Step 4: Register the WebSocket router in main.py**

Add import at `backend/src/main.py:14` (in the imports block):
```python
from src.api.routes import websocket as ws_route
```

Add router registration after line 188 (after deep_sync):
```python
# WebSocket endpoint (no /api/v1 prefix — connects at /ws/{user_id})
app.include_router(ws_route.router)
```

Note: The WebSocket router is registered **without** the `/api/v1` prefix so the endpoint is at `/ws/{user_id}` directly.

**Step 5: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_websocket_endpoint.py -v`
Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/websocket.py backend/tests/test_websocket_endpoint.py backend/src/main.py
git commit -m "feat: add WebSocket endpoint with JWT auth, ping/pong heartbeat"
```

---

### Task 4: DynamicAgentFactory

**Files:**
- Create: `backend/src/agents/dynamic_factory.py`
- Modify: `backend/src/agents/__init__.py` (add exports)
- Test: `backend/tests/test_dynamic_factory.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_dynamic_factory.py
"""Tests for DynamicAgentFactory."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec
from src.agents.base import AgentResult, AgentStatus
from src.agents.skill_aware_agent import SkillAwareAgent


@pytest.fixture
def factory():
    return DynamicAgentFactory()


@pytest.fixture
def sample_spec():
    return DynamicAgentSpec(
        name="BoardPrepAgent",
        description="Prepares board meeting materials and executive summaries",
        goal_context="Q1 board meeting preparation for Lonza partnership",
        required_capabilities=["research", "document_generation"],
        task_description="Compile competitive analysis for board deck",
        skill_access=["market-analysis", "competitive-positioning"],
    )


def test_spec_creation(sample_spec):
    assert sample_spec.name == "BoardPrepAgent"
    assert len(sample_spec.required_capabilities) == 2
    assert len(sample_spec.skill_access) == 2


def test_create_agent_class(factory, sample_spec):
    """Factory creates a class that extends SkillAwareAgent."""
    agent_cls = factory.create_agent_class(sample_spec)
    assert issubclass(agent_cls, SkillAwareAgent)
    assert agent_cls.name == "BoardPrepAgent"
    assert agent_cls.description == sample_spec.description
    assert agent_cls.agent_id == "dynamic_BoardPrepAgent"


def test_created_class_has_correct_skills(factory, sample_spec):
    """Dynamic agent class should have skill access configured."""
    agent_cls = factory.create_agent_class(sample_spec)
    # The AGENT_SKILLS should be updated for this agent
    from src.agents.skill_aware_agent import AGENT_SKILLS
    assert "dynamic_BoardPrepAgent" in AGENT_SKILLS
    assert AGENT_SKILLS["dynamic_BoardPrepAgent"] == ["market-analysis", "competitive-positioning"]


def test_create_agent_instance(factory, sample_spec):
    """Factory can create an instance from a spec."""
    mock_llm = MagicMock()
    agent = factory.create_agent(
        spec=sample_spec,
        llm_client=mock_llm,
        user_id="user-1",
    )
    assert isinstance(agent, SkillAwareAgent)
    assert agent.name == "BoardPrepAgent"
    assert agent.user_id == "user-1"


@pytest.mark.asyncio
async def test_agent_execute_uses_llm(factory, sample_spec):
    """Dynamic agent's execute() should call LLM with the generated system prompt."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value='{"result": "analysis complete"}')

    agent = factory.create_agent(
        spec=sample_spec,
        llm_client=mock_llm,
        user_id="user-1",
    )
    result = await agent.execute({"task": "compile analysis"})
    assert result.success
    assert result.data is not None
    mock_llm.generate_response.assert_called_once()


def test_build_system_prompt(factory, sample_spec):
    """System prompt should include agent name, description, and goal context."""
    prompt = factory._build_system_prompt(sample_spec)
    assert "BoardPrepAgent" in prompt
    assert "board meeting materials" in prompt
    assert "Q1 board meeting" in prompt


def test_multiple_agents_independent(factory):
    """Creating multiple dynamic agents should not interfere with each other."""
    spec_a = DynamicAgentSpec(
        name="AgentA",
        description="Agent A",
        goal_context="Context A",
        required_capabilities=["research"],
        task_description="Task A",
        skill_access=["market-analysis"],
    )
    spec_b = DynamicAgentSpec(
        name="AgentB",
        description="Agent B",
        goal_context="Context B",
        required_capabilities=["writing"],
        task_description="Task B",
        skill_access=["email-sequence"],
    )

    cls_a = factory.create_agent_class(spec_a)
    cls_b = factory.create_agent_class(spec_b)

    assert cls_a.name == "AgentA"
    assert cls_b.name == "AgentB"
    assert cls_a is not cls_b
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_dynamic_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.dynamic_factory'`

**Step 3: Write the DynamicAgentFactory**

```python
# backend/src/agents/dynamic_factory.py
"""Dynamic agent factory for creating agents at runtime.

Creates SkillAwareAgent subclasses on-the-fly from goal context,
required capabilities, and task descriptions. Used when the 6 core
agents don't cover a specialized need (e.g., BoardPrepAgent,
DueDiligenceAgent, EventPlanningAgent).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import AGENT_SKILLS, SkillAwareAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class DynamicAgentSpec:
    """Specification for creating a dynamic agent.

    Attributes:
        name: Agent class name (e.g., "BoardPrepAgent").
        description: What this agent does.
        goal_context: The goal it's working toward.
        required_capabilities: Capability tags (e.g., ["research", "document_generation"]).
        task_description: Specific task description.
        skill_access: Skill paths this agent is authorized to use.
    """

    name: str
    description: str
    goal_context: str
    required_capabilities: list[str] = field(default_factory=list)
    task_description: str = ""
    skill_access: list[str] = field(default_factory=list)


class DynamicAgentFactory:
    """Creates SkillAwareAgent subclasses at runtime.

    Given a DynamicAgentSpec, produces a new class extending
    SkillAwareAgent with a generated system prompt and configured
    skill access. Agents can be instantiated and used with the
    existing AgentOrchestrator.
    """

    def _build_system_prompt(self, spec: DynamicAgentSpec) -> str:
        """Build a focused system prompt for the dynamic agent.

        Args:
            spec: The agent specification.

        Returns:
            System prompt string for the agent's LLM calls.
        """
        return (
            f"You are {spec.name}, a specialized ARIA agent.\n\n"
            f"Role: {spec.description}\n\n"
            f"Current Goal: {spec.goal_context}\n\n"
            f"Capabilities: {', '.join(spec.required_capabilities)}\n\n"
            "You are part of ARIA, an AI Department Director for life sciences "
            "commercial teams. Be specific, actionable, and data-driven. "
            "Structure your output as JSON when possible."
        )

    def create_agent_class(self, spec: DynamicAgentSpec) -> type[SkillAwareAgent]:
        """Create a new SkillAwareAgent subclass from a spec.

        Dynamically constructs a class using Python's type() with the
        correct class attributes and method overrides.

        Args:
            spec: The agent specification.

        Returns:
            A new class that extends SkillAwareAgent.
        """
        agent_id = f"dynamic_{spec.name}"
        system_prompt = self._build_system_prompt(spec)

        # Register skill access for this dynamic agent
        AGENT_SKILLS[agent_id] = list(spec.skill_access)

        def _register_tools(self: Any) -> dict[str, Callable[..., Any]]:
            return {}

        async def execute(self: Any, task: dict[str, Any]) -> AgentResult:
            """Execute task using LLM with the generated system prompt."""
            task_str = json.dumps(task, default=str)
            prompt = (
                f"Task: {spec.task_description}\n\n"
                f"Input: {task_str}\n\n"
                "Analyze the input and produce a structured response. "
                "Respond with JSON."
            )
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=system_prompt,
                    max_tokens=2048,
                    temperature=0.3,
                )
                try:
                    data = json.loads(response)
                except json.JSONDecodeError:
                    data = {"raw_response": response.strip()}

                return AgentResult(success=True, data=data)
            except Exception as e:
                logger.error(
                    "Dynamic agent execution failed",
                    extra={"agent": spec.name, "error": str(e)},
                )
                return AgentResult(success=False, data=None, error=str(e))

        # Create the class dynamically
        agent_cls = type(
            spec.name,
            (SkillAwareAgent,),
            {
                "name": spec.name,
                "description": spec.description,
                "agent_id": agent_id,
                "_register_tools": _register_tools,
                "execute": execute,
            },
        )

        logger.info(
            "Created dynamic agent class",
            extra={
                "agent_name": spec.name,
                "agent_id": agent_id,
                "capabilities": spec.required_capabilities,
                "skill_access": spec.skill_access,
            },
        )

        return agent_cls

    def create_agent(
        self,
        spec: DynamicAgentSpec,
        llm_client: "LLMClient",
        user_id: str,
    ) -> SkillAwareAgent:
        """Create and instantiate a dynamic agent from a spec.

        Args:
            spec: The agent specification.
            llm_client: LLM client for agent reasoning.
            user_id: ID of the user this agent works for.

        Returns:
            Instantiated SkillAwareAgent subclass.
        """
        agent_cls = self.create_agent_class(spec)
        return agent_cls(llm_client=llm_client, user_id=user_id)

    async def log_to_procedural_memory(
        self,
        spec: DynamicAgentSpec,
        user_id: str,
    ) -> None:
        """Log the dynamic agent pattern to procedural memory for reuse.

        Stores the agent spec so future similar goals can reuse the
        same agent configuration.

        Args:
            spec: The agent specification to log.
            user_id: The user who triggered creation.
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            db.table("procedural_memories").insert(
                {
                    "user_id": user_id,
                    "procedure_type": "dynamic_agent",
                    "trigger_pattern": spec.goal_context,
                    "procedure": {
                        "name": spec.name,
                        "description": spec.description,
                        "capabilities": spec.required_capabilities,
                        "skill_access": spec.skill_access,
                        "task_description": spec.task_description,
                    },
                    "success_count": 1,
                    "source": "dynamic_agent_factory",
                }
            ).execute()
            logger.info(
                "Logged dynamic agent to procedural memory",
                extra={"agent_name": spec.name, "user_id": user_id},
            )
        except Exception as e:
            logger.warning("Failed to log dynamic agent to procedural memory: %s", e)
```

**Step 4: Update `backend/src/agents/__init__.py`**

Add to imports:
```python
from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec
```

Add to `__all__`:
```python
"DynamicAgentFactory",
"DynamicAgentSpec",
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_dynamic_factory.py -v`
Expected: All 7 tests PASS

**Step 6: Commit**

```bash
git add backend/src/agents/dynamic_factory.py backend/src/agents/__init__.py backend/tests/test_dynamic_factory.py
git commit -m "feat: add DynamicAgentFactory for runtime agent creation"
```

---

### Task 5: Wire GoalExecutionService to WebSocket

**Files:**
- Modify: `backend/src/services/goal_execution.py`
- Test: `backend/tests/test_goal_ws_integration.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_goal_ws_integration.py
"""Tests for GoalExecutionService WebSocket integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ws_manager():
    with patch("src.services.goal_execution.ws_manager") as mock:
        mock.send_thinking = AsyncMock()
        mock.send_progress_update = AsyncMock()
        mock.send_aria_message = AsyncMock()
        mock.send_action_pending = AsyncMock()
        mock.is_connected = MagicMock(return_value=True)
        yield mock


@pytest.fixture
def mock_db():
    with patch("src.services.goal_execution.SupabaseClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.get_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_llm():
    with patch("src.services.goal_execution.LLMClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.generate_response = AsyncMock(
            return_value='{"summary": "test analysis", "recommendations": ["action 1"]}'
        )
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def service(mock_db, mock_llm, mock_ws_manager):
    from src.services.goal_execution import GoalExecutionService
    svc = GoalExecutionService()
    return svc


@pytest.mark.asyncio
async def test_execute_goal_sends_thinking(service, mock_ws_manager, mock_db):
    """execute_goal should send thinking event at start."""
    # Setup goal query to return a goal
    goal_data = {
        "id": "goal-1",
        "title": "Test Goal",
        "description": "Test",
        "config": {"agent_type": "scout", "entities": ["Lonza"]},
        "goal_agents": [],
    }
    mock_result = MagicMock()
    mock_result.data = goal_data
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "exec-1"}])

    with patch.object(service, "_execute_agent", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"agent_type": "scout", "success": True, "content": {}}
        await service.execute_goal("goal-1", "user-1")

    mock_ws_manager.send_thinking.assert_called_with("user-1")


@pytest.mark.asyncio
async def test_execute_goal_sends_progress(service, mock_ws_manager, mock_db):
    """execute_goal should send progress update after agent completion."""
    goal_data = {
        "id": "goal-1",
        "title": "Test Goal",
        "description": "Test",
        "config": {"agent_type": "scout", "entities": ["Lonza"]},
        "goal_agents": [],
    }
    mock_result = MagicMock()
    mock_result.data = goal_data
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "exec-1"}])

    with patch.object(service, "_execute_agent", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"agent_type": "scout", "success": True, "content": {}}
        await service.execute_goal("goal-1", "user-1")

    mock_ws_manager.send_progress_update.assert_called()


@pytest.mark.asyncio
async def test_submit_actions_sends_ws_for_high_risk(mock_ws_manager):
    """High-risk actions should trigger WebSocket notification."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_db_cls, \
         patch("src.services.goal_execution.LLMClient"):
        mock_db_cls.get_client.return_value = MagicMock()
        from src.services.goal_execution import GoalExecutionService
        svc = GoalExecutionService()

        with patch("src.services.goal_execution.ActionQueueService") as mock_queue_cls:
            mock_queue = MagicMock()
            mock_queue.submit_action = AsyncMock(return_value={
                "id": "act-1",
                "title": "High risk action",
                "risk_level": "high",
            })
            mock_queue_cls.return_value = mock_queue

            await svc._submit_actions_to_queue(
                user_id="user-1",
                agent_type="strategist",
                content={"recommendations": ["High risk: restructure team"]},
                goal_id="goal-1",
            )

            # WebSocket notification should have been sent for the submitted action
            # (exact assertion depends on implementation)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_goal_ws_integration.py -v`
Expected: FAIL (ws_manager import doesn't exist in goal_execution yet)

**Step 3: Modify GoalExecutionService**

In `backend/src/services/goal_execution.py`, add import near line 8:
```python
from src.core.ws import ws_manager
```

In `execute_goal()` method, add after the goal status update to "active" (after line 79):
```python
        # Notify frontend that ARIA is thinking
        await ws_manager.send_thinking(user_id)
```

After each agent result is appended in the single-agent path (after line 96) and multi-agent path (after line 107), add progress tracking. Replace the single-agent block:
```python
        if agent_type:
            result = await self._execute_agent(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                context=context,
            )
            results.append(result)
            # Send progress via WebSocket
            await ws_manager.send_progress_update(
                user_id=user_id,
                goal_id=goal_id,
                progress=100,
                status="active",
                agent_name=agent_type,
                message=f"{agent_type.title()} analysis complete",
            )
        else:
            total_agents = len(goal.get("goal_agents", []))
            for i, agent in enumerate(goal.get("goal_agents", [])):
                result = await self._execute_agent(
                    user_id=user_id,
                    goal=goal,
                    agent_type=agent.get("agent_type", ""),
                    context=context,
                    goal_agent_id=agent.get("id"),
                )
                results.append(result)
                # Send progress via WebSocket
                progress_pct = int(((i + 1) / total_agents) * 100) if total_agents else 100
                await ws_manager.send_progress_update(
                    user_id=user_id,
                    goal_id=goal_id,
                    progress=progress_pct,
                    status="active",
                    agent_name=agent.get("agent_type", ""),
                    message=f"{agent.get('agent_type', '').title()} analysis complete",
                )
```

After goal status updated to "complete" (after line 118), add completion message:
```python
        # Send completion via WebSocket
        success_count = sum(1 for r in results if r.get("success"))
        await ws_manager.send_aria_message(
            user_id=user_id,
            message=f"Goal '{goal.get('title', '')}' is complete. {success_count}/{len(results)} agents succeeded.",
            ui_commands=[{"action": "update_intel_panel", "content": {"goal_id": goal_id, "status": "complete"}}],
            suggestions=["Show me the results", "What should I focus on next?"],
        )
```

In `_submit_actions_to_queue()`, after `queue.submit_action()` call (after line 658), add WebSocket notification for HIGH/CRITICAL actions:
```python
                    # Notify via WebSocket for actions needing approval
                    if action_data.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                        await ws_manager.send_action_pending(
                            user_id=user_id,
                            action_id=str(submitted.get("id", "")),
                            title=action_data.title,
                            agent=agent_type,
                            risk_level=action_data.risk_level.value,
                            description=action_data.description,
                        )
```

Note: This requires capturing the return value of `submit_action`. Change the call to:
```python
                    submitted = await queue.submit_action(
                        user_id=user_id,
                        data=action_data,
                    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_goal_ws_integration.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/goal_execution.py backend/tests/test_goal_ws_integration.py
git commit -m "feat: wire GoalExecutionService to WebSocket for real-time progress and approvals"
```

---

### Task 6: Register DynamicAgentFactory with GoalExecutionService

**Files:**
- Modify: `backend/src/services/goal_execution.py`
- Test: `backend/tests/test_goal_dynamic_agents.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_goal_dynamic_agents.py
"""Tests for dynamic agent integration in GoalExecutionService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_deps():
    with patch("src.services.goal_execution.SupabaseClient") as mock_db_cls, \
         patch("src.services.goal_execution.LLMClient") as mock_llm_cls, \
         patch("src.services.goal_execution.ws_manager"):
        mock_db = MagicMock()
        mock_db_cls.get_client.return_value = mock_db
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value='{"result": "ok"}')
        mock_llm_cls.return_value = mock_llm
        yield mock_db, mock_llm


@pytest.fixture
def service(mock_deps):
    from src.services.goal_execution import GoalExecutionService
    return GoalExecutionService()


def test_register_dynamic_agent(service):
    """GoalExecutionService should accept dynamic agent registration."""
    from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec

    factory = DynamicAgentFactory()
    spec = DynamicAgentSpec(
        name="TestDynamicAgent",
        description="Test agent",
        goal_context="Testing",
        required_capabilities=["research"],
        task_description="Run test analysis",
        skill_access=[],
    )
    agent_cls = factory.create_agent_class(spec)
    service.register_dynamic_agent("test_dynamic", agent_cls)
    assert "test_dynamic" in service._dynamic_agents


def test_create_agent_instance_uses_dynamic(service):
    """_create_agent_instance should find dynamically registered agents."""
    from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec

    factory = DynamicAgentFactory()
    spec = DynamicAgentSpec(
        name="CustomAgent",
        description="Custom agent for testing",
        goal_context="Testing dynamic dispatch",
        required_capabilities=["analysis"],
        task_description="Analyze data",
        skill_access=[],
    )
    agent_cls = factory.create_agent_class(spec)
    service.register_dynamic_agent("custom_agent", agent_cls)

    # _create_agent_instance should now find this agent type
    agent = service._create_agent_instance("custom_agent", "user-1")
    assert agent is not None
    assert agent.name == "CustomAgent"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_goal_dynamic_agents.py -v`
Expected: FAIL (`register_dynamic_agent` doesn't exist, `_dynamic_agents` doesn't exist)

**Step 3: Modify GoalExecutionService**

In `__init__()` of `GoalExecutionService`, add:
```python
        self._dynamic_agents: dict[str, type] = {}
```

Add new method after `__init__()`:
```python
    def register_dynamic_agent(self, agent_type: str, agent_class: type) -> None:
        """Register a dynamically created agent class for task routing.

        Args:
            agent_type: The type key to use for dispatch.
            agent_class: The agent class (must extend BaseAgent).
        """
        self._dynamic_agents[agent_type] = agent_class
        logger.info(
            "Registered dynamic agent",
            extra={"agent_type": agent_type, "agent_class": agent_class.__name__},
        )
```

In `_create_agent_instance()`, add a check for dynamic agents after the core agent lookup fails. After `if agent_cls is None:` and before `return None`:
```python
            # Check dynamic agents
            if agent_cls is None:
                agent_cls = self._dynamic_agents.get(agent_type)
                if agent_cls is not None:
                    return agent_cls(llm_client=self._llm, user_id=user_id)
                return None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_goal_dynamic_agents.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/goal_execution.py backend/tests/test_goal_dynamic_agents.py
git commit -m "feat: register dynamic agents with GoalExecutionService for task dispatch"
```

---

### Task 7: Enhance Chat Stream with Rich Content, UI Commands, and Suggestions

**Files:**
- Modify: `backend/src/api/routes/chat.py`
- Test: `backend/tests/test_chat_stream_envelope.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_chat_stream_envelope.py
"""Tests for chat stream envelope fields (rich_content, ui_commands, suggestions)."""

import json

import pytest

from src.api.routes.chat import _analyze_ui_commands, _generate_suggestions


def test_analyze_ui_commands_navigation():
    """Detect navigation intent in ARIA response."""
    response = "Let me show you the pipeline for Lonza. Here's what I found."
    commands = _analyze_ui_commands(response)
    # Should detect pipeline navigation intent
    assert isinstance(commands, list)


def test_analyze_ui_commands_empty_for_plain():
    """No UI commands for plain conversational response."""
    response = "Good morning! How can I help you today?"
    commands = _analyze_ui_commands(response)
    assert commands == []


def test_generate_suggestions_returns_list():
    """Suggestions should be a list of follow-up prompts."""
    message = "I've analyzed the competitive landscape for Lonza."
    conversation = [
        {"role": "user", "content": "What do you know about Lonza?"},
        {"role": "assistant", "content": message},
    ]
    suggestions = _generate_suggestions(message, conversation)
    assert isinstance(suggestions, list)
    assert len(suggestions) <= 4


def test_generate_suggestions_contextual():
    """Suggestions should relate to the conversation context."""
    message = "Here's the battle card for Catalent."
    conversation = [
        {"role": "user", "content": "Show me Catalent's battle card"},
        {"role": "assistant", "content": message},
    ]
    suggestions = _generate_suggestions(message, conversation)
    assert isinstance(suggestions, list)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_chat_stream_envelope.py -v`
Expected: FAIL (`_analyze_ui_commands` and `_generate_suggestions` don't exist)

**Step 3: Add helper functions to chat.py**

Add these functions at the end of `backend/src/api/routes/chat.py` (before the last route or after imports section):

```python
# --- Envelope field generators ---

# Navigation keywords mapped to routes
_ROUTE_KEYWORDS: dict[str, str] = {
    "pipeline": "/pipeline",
    "intelligence": "/intelligence",
    "battle card": "/intelligence/battle-cards",
    "communication": "/communications",
    "action": "/actions",
    "briefing": "/briefing",
    "settings": "/settings",
}


def _analyze_ui_commands(response: str) -> list[dict]:
    """Analyze ARIA's response for UI navigation or highlight intents.

    Scans for route-related keywords and generates navigate commands.
    This is a heuristic approach; the LLM can also produce explicit
    ui_commands in structured responses.

    Args:
        response: The assistant's text response.

    Returns:
        List of UICommand dicts.
    """
    commands: list[dict] = []
    response_lower = response.lower()

    for keyword, route in _ROUTE_KEYWORDS.items():
        if keyword in response_lower:
            commands.append({"action": "navigate", "route": route})
            break  # Only one navigation per response

    return commands


def _generate_suggestions(
    response: str,
    conversation: list[dict],
) -> list[str]:
    """Generate contextual follow-up suggestions.

    Uses simple heuristics based on the response content and
    conversation history. Returns 2-3 follow-up prompts.

    Args:
        response: The assistant's latest response text.
        conversation: Recent conversation messages.

    Returns:
        List of 2-3 suggestion strings.
    """
    suggestions: list[str] = []
    response_lower = response.lower()

    # Context-aware suggestions based on keywords
    if "battle card" in response_lower:
        suggestions.extend([
            "Compare with other competitors",
            "Draft outreach based on this",
        ])
    elif "pipeline" in response_lower:
        suggestions.extend([
            "Which deals need attention?",
            "Show me the forecast",
        ])
    elif "analysis" in response_lower or "landscape" in response_lower:
        suggestions.extend([
            "What are the key risks?",
            "Recommend next steps",
        ])
    elif "email" in response_lower or "draft" in response_lower:
        suggestions.extend([
            "Make it more concise",
            "Adjust the tone",
        ])

    # Always add a generic follow-up if we have fewer than 2
    if len(suggestions) < 2:
        suggestions.append("What should I focus on today?")
    if len(suggestions) < 2:
        suggestions.append("Show me my briefing")

    return suggestions[:4]
```

Then update the `complete` event in the streaming endpoint (around line 336-341) to use these functions:

Replace:
```python
        complete_event = {
            "type": "complete",
            "rich_content": [],
            "ui_commands": [],
            "suggestions": [],
        }
```

With:
```python
        ui_commands = _analyze_ui_commands(full_content)
        suggestions = _generate_suggestions(full_content, conversation_messages[-4:])

        complete_event = {
            "type": "complete",
            "rich_content": [],
            "ui_commands": ui_commands,
            "suggestions": suggestions,
        }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_chat_stream_envelope.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/chat.py backend/tests/test_chat_stream_envelope.py
git commit -m "feat: populate ui_commands and suggestions in chat stream response"
```

---

### Task 8: Run All Tests & Final Verification

**Step 1: Run the full test suite for all new files**

```bash
cd /Users/dhruv/aria && python -m pytest backend/tests/test_ws_events.py backend/tests/test_connection_manager.py backend/tests/test_websocket_endpoint.py backend/tests/test_dynamic_factory.py backend/tests/test_goal_ws_integration.py backend/tests/test_goal_dynamic_agents.py backend/tests/test_chat_stream_envelope.py -v
```

Expected: All tests PASS

**Step 2: Run ruff linting**

```bash
cd /Users/dhruv/aria && ruff check backend/src/core/ws.py backend/src/models/ws_events.py backend/src/api/routes/websocket.py backend/src/agents/dynamic_factory.py backend/src/services/goal_execution.py backend/src/api/routes/chat.py
```

Expected: No errors

**Step 3: Run ruff format**

```bash
cd /Users/dhruv/aria && ruff format backend/src/core/ws.py backend/src/models/ws_events.py backend/src/api/routes/websocket.py backend/src/agents/dynamic_factory.py backend/src/services/goal_execution.py backend/src/api/routes/chat.py
```

**Step 4: Verify server starts**

```bash
cd /Users/dhruv/aria/backend && python -c "from src.main import app; print('App imports successfully')"
```

Expected: `App imports successfully`

**Step 5: Final commit if any formatting changes**

```bash
git add -A && git status
# If changes exist:
git commit -m "style: format new WebSocket and dynamic agent files"
```
