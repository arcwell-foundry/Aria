"""Tests for chat API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_chat_endpoint_returns_response(test_client: TestClient) -> None:
    """Test POST /api/v1/chat returns response."""
    from src.services.chat import ChatService

    with patch.object(
        ChatService,
        "process_message",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.return_value = {
            "message": "Hello! How can I help you today?",
            "citations": [],
            "conversation_id": "conv-123",
        }

        response = test_client.post(
            "/api/v1/chat",
            json={
                "message": "Hello",
                "conversation_id": "conv-123",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "citations" in data
    assert "conversation_id" in data


def test_chat_endpoint_requires_message(test_client: TestClient) -> None:
    """Test POST /api/v1/chat requires message field."""
    response = test_client.post(
        "/api/v1/chat",
        json={"conversation_id": "conv-123"},
    )
    assert response.status_code == 422


def test_chat_endpoint_generates_conversation_id(test_client: TestClient) -> None:
    """Test POST /api/v1/chat generates conversation_id if not provided."""
    from src.services.chat import ChatService

    with patch.object(
        ChatService,
        "process_message",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.return_value = {
            "message": "Response",
            "citations": [],
            "conversation_id": "generated-id",
        }

        response = test_client.post(
            "/api/v1/chat",
            json={"message": "Hello"},
        )

    assert response.status_code == 200
    call_kwargs = mock_process.call_args.kwargs
    assert "conversation_id" in call_kwargs
    assert call_kwargs["conversation_id"] is not None


def test_chat_endpoint_includes_citations(test_client: TestClient) -> None:
    """Test POST /api/v1/chat includes memory citations."""
    from src.services.chat import ChatService

    with patch.object(
        ChatService,
        "process_message",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.return_value = {
            "message": "Based on our meeting, the Q3 budget is $500K.",
            "citations": [
                {
                    "id": "episode-1",
                    "type": "episodic",
                    "content": "Meeting about Q3 budget",
                    "confidence": None,
                }
            ],
            "conversation_id": "conv-123",
        }

        response = test_client.post(
            "/api/v1/chat",
            json={
                "message": "What's the Q3 budget?",
                "conversation_id": "conv-123",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["citations"]) == 1
    assert data["citations"][0]["type"] == "episodic"


def test_chat_endpoint_requires_authentication() -> None:
    """Test POST /api/v1/chat requires authentication."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
    )
    assert response.status_code == 401
