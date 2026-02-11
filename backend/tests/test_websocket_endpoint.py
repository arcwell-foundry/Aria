"""Tests for WebSocket endpoint."""

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
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/user-1"):
        pass


def test_websocket_rejects_invalid_token(client):
    """WebSocket connection with invalid token should be rejected."""
    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = None
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            "/ws/user-1?token=bad-token"
        ):
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
                ws.receive_json()  # consume connected event
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"


def test_websocket_rejects_user_id_mismatch(client):
    """Token user_id must match URL user_id."""
    mock_user = MagicMock()
    mock_user.id = "different-user"

    with patch("src.api.routes.websocket._authenticate_ws_token") as mock_auth:
        mock_auth.return_value = mock_user
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(
            "/ws/user-1?token=valid-token"
        ):
            pass
