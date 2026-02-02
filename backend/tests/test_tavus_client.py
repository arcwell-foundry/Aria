"""Tests for Tavus API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.tavus import TavusClient


@pytest.fixture
def tavus_client() -> TavusClient:
    """Create a TavusClient instance with mocked initialization.

    Returns:
        A TavusClient with test configuration.
    """
    with patch.object(TavusClient, "__init__", lambda self: None):
        client = TavusClient()
        client.api_key = "test_key"
        client.persona_id = "test_persona"
        client.headers = {
            "x-api-key": "test_key",
            "Content-Type": "application/json",
        }
        return client


@pytest.mark.asyncio
async def test_create_conversation(tavus_client: TavusClient) -> None:
    """Test creating a new conversation.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "conversation_url": "https://daily.co/room_123",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_conversation(
            user_id="user_123", conversation_name="Test Session"
        )

        assert result["conversation_id"] == "conv_123"
        assert result["conversation_url"] == "https://daily.co/room_123"


@pytest.mark.asyncio
async def test_create_conversation_with_custom_greeting(tavus_client: TavusClient) -> None:
    """Test creating a conversation with a custom greeting.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_456",
            "conversation_url": "https://daily.co/room_456",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_conversation(
            user_id="user_456",
            conversation_name="Test with Greeting",
            custom_greeting="Hello! How can I help you today?",
        )

        assert result["conversation_id"] == "conv_456"


@pytest.mark.asyncio
async def test_get_conversation(tavus_client: TavusClient) -> None:
    """Test getting conversation details.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "status": "active",
            "room_url": "https://daily.co/room_123",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_conversation("conv_123")

        assert result["conversation_id"] == "conv_123"
        assert result["status"] == "active"


@pytest.mark.asyncio
async def test_end_conversation(tavus_client: TavusClient) -> None:
    """Test ending a conversation.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "status": "ended",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.end_conversation("conv_123")

        assert result["status"] == "ended"


@pytest.mark.asyncio
async def test_list_conversations(tavus_client: TavusClient) -> None:
    """Test listing conversations.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversations": [
                {"conversation_id": "conv_1", "status": "active"},
                {"conversation_id": "conv_2", "status": "ended"},
            ]
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_conversations(limit=10)

        assert len(result) == 2
        assert result[0]["conversation_id"] == "conv_1"


@pytest.mark.asyncio
async def test_list_conversations_with_status_filter(tavus_client: TavusClient) -> None:
    """Test listing conversations with status filter.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversations": [
                {"conversation_id": "conv_1", "status": "active"},
            ]
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_conversations(limit=10, status="active")

        assert len(result) == 1
        assert result[0]["status"] == "active"


@pytest.mark.asyncio
async def test_get_persona(tavus_client: TavusClient) -> None:
    """Test getting persona details.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "test_persona",
            "name": "ARIA Assistant",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_persona()

        assert result["persona_id"] == "test_persona"
        assert result["name"] == "ARIA Assistant"


@pytest.mark.asyncio
async def test_health_check_success(tavus_client: TavusClient) -> None:
    """Test health check when API is accessible.

    Args:
        tavus_client: The TavusClient fixture.
    """
    with patch.object(tavus_client, "get_persona", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"persona_id": "test"}

        result = await tavus_client.health_check()

        assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(tavus_client: TavusClient) -> None:
    """Test health check when API is not accessible.

    Args:
        tavus_client: The TavusClient fixture.
    """
    with patch.object(tavus_client, "get_persona", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("API Error")

        result = await tavus_client.health_check()

        assert result is False


@pytest.mark.asyncio
async def test_default_context(tavus_client: TavusClient) -> None:
    """Test the default conversational context.

    Args:
        tavus_client: The TavusClient fixture.
    """
    context = tavus_client._default_context()

    assert "ARIA" in context
    assert "Life Sciences" in context
    assert "Department Director" in context
