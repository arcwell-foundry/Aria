"""Tests for Tavus API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.tavus import (
    TavusAPIError,
    TavusClient,
    TavusConnectionError,
)


@pytest.fixture
def tavus_client() -> TavusClient:
    """Create a TavusClient instance with mocked initialization.

    Returns:
        A TavusClient with test configuration.
    """
    with patch.object(TavusClient, "__init__", lambda self: None):
        client = TavusClient()
        client.api_key = MagicMock()
        client.api_key.get_secret_value = MagicMock(return_value="test_key")
        client.persona_id = "test_persona"
        client.replica_id = "test_replica"
        client.callback_url = "https://example.com/callback"
        client.guardrails_id = "test_guardrails"
        client.headers = {
            "x-api-key": "test_key",
            "Content-Type": "application/json",
        }
        return client


# ====================
# Conversation Tests
# ====================


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
async def test_create_conversation_with_all_params(tavus_client: TavusClient) -> None:
    """Test creating a conversation with all optional parameters.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_789",
            "conversation_url": "https://daily.co/room_789",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_conversation(
            user_id="user_789",
            conversation_name="Full Test",
            context="Custom context",
            custom_greeting="Hi there!",
            properties={"custom_prop": "value"},
            replica_id="custom_replica",
            callback_url="https://example.com/custom_callback",
            memory_stores=[{"type": "redis", "key": "session_123"}],
            document_ids=["doc_1", "doc_2"],
            document_tags=["sales", "pharma"],
            retrieval_strategy="semantic",
            audio_only=True,
        )

        assert result["conversation_id"] == "conv_789"
        # Verify the payload included all parameters
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["replica_id"] == "custom_replica"
        assert payload["callback_url"] == "https://example.com/custom_callback"
        assert payload["memory_stores"] == [{"type": "redis", "key": "session_123"}]
        assert payload["document_ids"] == ["doc_1", "doc_2"]
        assert payload["document_tags"] == ["sales", "pharma"]
        assert payload["retrieval_strategy"] == "semantic"
        assert payload["audio_only"] is True


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
async def test_get_conversation_verbose(tavus_client: TavusClient) -> None:
    """Test getting conversation details with verbose flag.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "status": "ended",
            "transcript": [{"speaker": "user", "text": "Hello"}],
            "perception_analysis": {"engagement": 0.95},
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_conversation("conv_123", verbose=True)

        assert result["conversation_id"] == "conv_123"
        assert "transcript" in result
        assert "perception_analysis" in result
        # Verify verbose param was passed
        call_args = mock_client.get.call_args
        assert call_args.kwargs["params"]["verbose"] == "true"


@pytest.mark.asyncio
async def test_get_conversation_non_verbose(tavus_client: TavusClient) -> None:
    """Test getting conversation details without verbose flag.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "status": "active",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_conversation("conv_123", verbose=False)

        assert result["conversation_id"] == "conv_123"
        call_args = mock_client.get.call_args
        assert call_args.kwargs["params"]["verbose"] == "false"


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
async def test_delete_conversation(tavus_client: TavusClient) -> None:
    """Test deleting a conversation.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "conversation_id": "conv_123",
            "deleted": True,
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.delete = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.delete_conversation("conv_123")

        assert result["deleted"] is True
        mock_client.delete.assert_called_once()


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


# ====================
# Persona Tests
# ====================


@pytest.mark.asyncio
async def test_create_persona(tavus_client: TavusClient) -> None:
    """Test creating a new persona.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "persona_123",
            "persona_name": "Test Persona",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_persona(
            persona_name="Test Persona",
            system_prompt="You are a helpful assistant.",
            context="ARIA context",
            layers={"layer1": {"config": "value"}},
            default_replica_id="replica_123",
        )

        assert result["persona_id"] == "persona_123"
        assert result["persona_name"] == "Test Persona"


@pytest.mark.asyncio
async def test_create_persona_with_optional_params(tavus_client: TavusClient) -> None:
    """Test creating a persona with optional parameters.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "persona_456",
            "persona_name": "Enhanced Persona",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_persona(
            persona_name="Enhanced Persona",
            system_prompt="You are a helpful assistant.",
            context="ARIA context",
            layers={"layer1": {"config": "value"}},
            default_replica_id="replica_123",
            document_ids=["doc_1", "doc_2"],
            guardrails_id="guardrails_123",
        )

        assert result["persona_id"] == "persona_456"
        # Verify optional params were included in payload
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["document_ids"] == ["doc_1", "doc_2"]
        assert payload["guardrails_id"] == "guardrails_123"


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
async def test_get_persona_with_explicit_id(tavus_client: TavusClient) -> None:
    """Test getting persona details with explicit ID.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "explicit_persona",
            "name": "Custom Persona",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_persona("explicit_persona")

        assert result["persona_id"] == "explicit_persona"


@pytest.mark.asyncio
async def test_get_persona_missing_id(tavus_client: TavusClient) -> None:
    """Test getting persona without ID raises ValueError.

    Args:
        tavus_client: The TavusClient fixture.
    """
    tavus_client.persona_id = None

    with pytest.raises(ValueError, match="Persona ID is required"):
        await tavus_client.get_persona()


@pytest.mark.asyncio
async def test_patch_persona(tavus_client: TavusClient) -> None:
    """Test patching a persona using JSON Patch format.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "persona_123",
            "persona_name": "Updated Persona",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.patch = AsyncMock(return_value=mock_response)

    patches = [
        {"op": "replace", "path": "/persona_name", "value": "Updated Persona"},
    ]

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.patch_persona("persona_123", patches)

        assert result["persona_name"] == "Updated Persona"
        mock_client.patch.assert_called_once()


@pytest.mark.asyncio
async def test_list_personas(tavus_client: TavusClient) -> None:
    """Test listing all personas.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "personas": [
                {"persona_id": "persona_1", "persona_name": "ARIA"},
                {"persona_id": "persona_2", "persona_name": "Helper"},
            ]
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_personas()

        assert len(result) == 2
        assert result[0]["persona_id"] == "persona_1"


@pytest.mark.asyncio
async def test_delete_persona(tavus_client: TavusClient) -> None:
    """Test deleting a persona.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "persona_id": "persona_123",
            "deleted": True,
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.delete = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.delete_persona("persona_123")

        assert result["deleted"] is True
        mock_client.delete.assert_called_once()


# ====================
# Document Tests
# ====================


@pytest.mark.asyncio
async def test_create_document(tavus_client: TavusClient) -> None:
    """Test creating a document in the knowledge base.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "document_id": "doc_123",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_document(
            document_name="Test Document",
            file_url_or_path="https://example.com/doc.pdf",
        )

        assert result["document_id"] == "doc_123"


@pytest.mark.asyncio
async def test_create_document_with_tags_and_crawl(tavus_client: TavusClient) -> None:
    """Test creating a document with tags and crawl enabled.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "document_id": "doc_456",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_document(
            document_name="Crawled Document",
            file_url_or_path="https://example.com/docs/",
            tags=["api", "reference"],
            crawl=True,
        )

        assert result["document_id"] == "doc_456"
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["tags"] == ["api", "reference"]
        assert payload["crawl"] is True


@pytest.mark.asyncio
async def test_get_document(tavus_client: TavusClient) -> None:
    """Test getting document details.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "document_id": "doc_123",
            "document_name": "Test Document",
            "status": "processed",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_document("doc_123")

        assert result["document_id"] == "doc_123"
        assert result["status"] == "processed"


@pytest.mark.asyncio
async def test_list_documents(tavus_client: TavusClient) -> None:
    """Test listing all documents.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "documents": [
                {"document_id": "doc_1", "document_name": "Doc 1"},
                {"document_id": "doc_2", "document_name": "Doc 2"},
            ]
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_documents()

        assert len(result) == 2
        assert result[0]["document_id"] == "doc_1"


@pytest.mark.asyncio
async def test_delete_document(tavus_client: TavusClient) -> None:
    """Test deleting a document.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "document_id": "doc_123",
            "deleted": True,
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.delete = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.delete_document("doc_123")

        assert result["deleted"] is True
        mock_client.delete.assert_called_once()


# ====================
# Guardrails Tests
# ====================


@pytest.mark.asyncio
async def test_create_guardrails(tavus_client: TavusClient) -> None:
    """Test creating guardrails configuration.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "guardrails_id": "gr_123",
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    guardrails_config = [
        {"type": "topic", "action": "block", "topics": ["politics"]},
    ]

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.create_guardrails(guardrails_config)

        assert result["guardrails_id"] == "gr_123"


@pytest.mark.asyncio
async def test_get_guardrails(tavus_client: TavusClient) -> None:
    """Test getting guardrails configuration.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "guardrails_id": "gr_123",
            "guardrails": [
                {"type": "topic", "action": "block", "topics": ["politics"]},
            ],
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_guardrails("gr_123")

        assert result["guardrails_id"] == "gr_123"
        assert len(result["guardrails"]) == 1


# ====================
# Replica Tests
# ====================


@pytest.mark.asyncio
async def test_list_replicas(tavus_client: TavusClient) -> None:
    """Test listing all replicas.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "replicas": [
                {"replica_id": "replica_1", "name": "Default"},
                {"replica_id": "replica_2", "name": "Custom"},
            ]
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_replicas()

        assert len(result) == 2
        assert result[0]["replica_id"] == "replica_1"


@pytest.mark.asyncio
async def test_get_replica(tavus_client: TavusClient) -> None:
    """Test getting replica details with training progress.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "replica_id": "replica_123",
            "name": "ARIA Replica",
            "status": "ready",
            "training_progress": 100,
        }
    )
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.get_replica("replica_123")

        assert result["replica_id"] == "replica_123"
        assert result["training_progress"] == 100


# ====================
# Health Check Tests
# ====================


@pytest.mark.asyncio
async def test_health_check_conversations_endpoint(tavus_client: TavusClient) -> None:
    """Test health check using conversations endpoint.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.health_check()

        assert result is True
        # Verify it called the conversations endpoint with limit=1
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "conversations" in call_args.args[0]
        assert call_args.kwargs["params"]["limit"] == 1


@pytest.mark.asyncio
async def test_health_check_failure(tavus_client: TavusClient) -> None:
    """Test health check when API is not accessible.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.health_check()

        assert result is False


# ====================
# Error Handling Tests
# ====================


@pytest.mark.asyncio
async def test_tavus_api_error(tavus_client: TavusClient) -> None:
    """Test that TavusAPIError is raised on HTTP error.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json = MagicMock(
        return_value={"message": "Invalid request", "code": "BAD_REQUEST"}
    )

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=mock_response,
        )
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TavusAPIError) as exc_info:
            await tavus_client.get_conversation("conv_123")

        assert exc_info.value.status_code == 400
        assert exc_info.value.details == {"message": "Invalid request", "code": "BAD_REQUEST"}


@pytest.mark.asyncio
async def test_tavus_api_error_non_json_response(tavus_client: TavusClient) -> None:
    """Test TavusAPIError handles non-JSON error responses.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json = MagicMock(side_effect=Exception("Not JSON"))
    mock_response.text = "Internal Server Error"

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TavusAPIError) as exc_info:
            await tavus_client.get_conversation("conv_123")

        assert exc_info.value.status_code == 500
        assert exc_info.value.details == "Internal Server Error"


@pytest.mark.asyncio
async def test_tavus_connection_error(tavus_client: TavusClient) -> None:
    """Test that TavusConnectionError is raised on connection error.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=httpx.RequestError("Connection refused", request=MagicMock())
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TavusConnectionError) as exc_info:
            await tavus_client.get_conversation("conv_123")

        assert "Failed to connect to Tavus API" in str(exc_info.value)


# ====================
# Default Context Test
# ====================


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


# ====================
# List Response Edge Cases
# ====================


@pytest.mark.asyncio
async def test_list_conversations_empty_response(tavus_client: TavusClient) -> None:
    """Test listing conversations with empty response.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={})
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_conversations()

        assert result == []


@pytest.mark.asyncio
async def test_list_personas_empty_response(tavus_client: TavusClient) -> None:
    """Test listing personas with empty response.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={})
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_personas()

        assert result == []


@pytest.mark.asyncio
async def test_list_documents_empty_response(tavus_client: TavusClient) -> None:
    """Test listing documents with empty response.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={})
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_documents()

        assert result == []


@pytest.mark.asyncio
async def test_list_replicas_empty_response(tavus_client: TavusClient) -> None:
    """Test listing replicas with empty response.

    Args:
        tavus_client: The TavusClient fixture.
    """
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={})
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tavus_client.list_replicas()

        assert result == []
