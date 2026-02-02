"""Tests for chat service with memory integration."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_memory_results() -> list[dict[str, Any]]:
    """Create mock memory query results."""
    return [
        {
            "id": "fact-1",
            "memory_type": "semantic",
            "content": "User prefers email over phone calls",
            "relevance_score": 0.85,
            "confidence": 0.90,
            "timestamp": datetime.now(UTC),
        },
        {
            "id": "episode-1",
            "memory_type": "episodic",
            "content": "[meeting] Discussed Q3 budget",
            "relevance_score": 0.75,
            "confidence": None,
            "timestamp": datetime.now(UTC),
        },
    ]


@pytest.mark.asyncio
async def test_chat_service_queries_memory_before_responding(
    mock_memory_results: list[dict[str, Any]],
) -> None:
    """Test that ChatService queries relevant memories."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=mock_memory_results)
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response from ARIA")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="What was discussed in Q3?",
        )

        mock_mqs.query.assert_called_once()
        call_kwargs = mock_mqs.query.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert "Q3" in call_kwargs["query"]


@pytest.mark.asyncio
async def test_chat_service_includes_memory_in_llm_context(
    mock_memory_results: list[dict[str, Any]],
) -> None:
    """Test that relevant memories are included in LLM context."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=mock_memory_results)
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response from ARIA")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="What was discussed?",
        )

        call_kwargs = mock_llm.generate_response.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", "")
        assert "prefers email over phone" in system_prompt or "Q3 budget" in system_prompt


@pytest.mark.asyncio
async def test_chat_service_updates_working_memory() -> None:
    """Test that working memory is updated with new messages."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="ARIA's response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello!",
        )

        add_message_calls = mock_working_memory.add_message.call_args_list
        assert len(add_message_calls) == 2
        assert add_message_calls[0].args == ("user", "Hello!")
        assert add_message_calls[1].args[0] == "assistant"


@pytest.mark.asyncio
async def test_chat_response_includes_memory_citations(
    mock_memory_results: list[dict[str, Any]],
) -> None:
    """Test that response includes citations when memory is used."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=mock_memory_results)
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value="Based on our meeting, we discussed Q3 budget."
        )
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        result = await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="What was discussed?",
        )

        assert "citations" in result
        assert isinstance(result["citations"], list)


@pytest.mark.asyncio
async def test_chat_response_returns_conversation_id() -> None:
    """Test that response includes the conversation ID."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Hello!")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        result = await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello!",
        )

        assert result["conversation_id"] == "conv-456"


@pytest.mark.asyncio
async def test_chat_service_uses_default_memory_types() -> None:
    """Test that ChatService defaults to querying episodic and semantic memory."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello!",
        )

        call_kwargs = mock_mqs.query.call_args.kwargs
        assert "episodic" in call_kwargs["memory_types"]
        assert "semantic" in call_kwargs["memory_types"]


@pytest.mark.asyncio
async def test_chat_service_accepts_custom_memory_types() -> None:
    """Test that ChatService can query custom memory types."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="What tasks do I have?",
            memory_types=["prospective"],
        )

        call_kwargs = mock_mqs.query.call_args.kwargs
        assert call_kwargs["memory_types"] == ["prospective"]


@pytest.mark.asyncio
async def test_chat_service_builds_citations_from_memories(
    mock_memory_results: list[dict[str, Any]],
) -> None:
    """Test that citations are built correctly from memory results."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=mock_memory_results)
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        result = await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Tell me about my preferences",
        )

        citations = result["citations"]
        assert len(citations) == 2

        # Check first citation (semantic fact)
        fact_citation = next(c for c in citations if c["id"] == "fact-1")
        assert fact_citation["type"] == "semantic"
        assert fact_citation["confidence"] == 0.90

        # Check second citation (episodic)
        episode_citation = next(c for c in citations if c["id"] == "episode-1")
        assert episode_citation["type"] == "episodic"
        assert episode_citation["confidence"] is None


@pytest.mark.asyncio
async def test_chat_service_no_memory_context_when_empty() -> None:
    """Test that system prompt handles empty memory results gracefully."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        service = ChatService()
        result = await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello!",
        )

        # Should still return a valid response
        assert result["message"] == "Response"
        assert result["citations"] == []


def test_build_system_prompt_with_memories() -> None:
    """Test that _build_system_prompt correctly formats memories."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService"),
        patch("src.services.chat.LLMClient"),
        patch("src.services.chat.WorkingMemoryManager"),
    ):
        service = ChatService()

        memories: list[dict[str, Any]] = [
            {
                "id": "fact-1",
                "memory_type": "semantic",
                "content": "User prefers morning meetings",
                "confidence": 0.95,
            },
            {
                "id": "episode-1",
                "memory_type": "episodic",
                "content": "Had lunch with client",
                "confidence": None,
            },
        ]

        prompt = service._build_system_prompt(memories)

        assert "ARIA" in prompt
        assert "morning meetings" in prompt
        assert "lunch with client" in prompt
        assert "semantic" in prompt
        assert "episodic" in prompt
        # Confidence should be shown for semantic fact
        assert "95%" in prompt


def test_build_system_prompt_without_memories() -> None:
    """Test that _build_system_prompt works with empty memories."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService"),
        patch("src.services.chat.LLMClient"),
        patch("src.services.chat.WorkingMemoryManager"),
    ):
        service = ChatService()
        prompt = service._build_system_prompt([])

        assert "ARIA" in prompt
        assert "Relevant Context" not in prompt


def test_build_citations_truncates_long_content() -> None:
    """Test that _build_citations truncates long content."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService"),
        patch("src.services.chat.LLMClient"),
        patch("src.services.chat.WorkingMemoryManager"),
    ):
        service = ChatService()

        long_content = "A" * 200  # 200 characters
        memories = [
            {
                "id": "long-1",
                "memory_type": "semantic",
                "content": long_content,
                "confidence": 0.8,
            }
        ]

        citations = service._build_citations(memories)

        assert len(citations) == 1
        # Content should be truncated with "..."
        assert len(citations[0]["content"]) == 103  # 100 + "..."
        assert citations[0]["content"].endswith("...")


@pytest.mark.asyncio
async def test_chat_service_extracts_information_from_conversation() -> None:
    """Test that ChatService extracts and stores new information."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
        patch("src.services.chat.ExtractionService") as mock_extract_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value="Great, I'll note that you prefer morning meetings."
        )
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        mock_extract = AsyncMock()
        mock_extract.extract_and_store = AsyncMock(return_value=["fact-123"])
        mock_extract_class.return_value = mock_extract

        service = ChatService()
        await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="I prefer morning meetings.",
        )

        # Verify extraction was called
        mock_extract.extract_and_store.assert_called_once()


@pytest.mark.asyncio
async def test_chat_service_returns_timing_metadata() -> None:
    """Test that ChatService returns timing information."""
    from src.services.chat import ChatService

    with (
        patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
        patch("src.services.chat.LLMClient") as mock_llm_class,
        patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
        patch("src.services.chat.ExtractionService") as mock_extract_class,
    ):
        mock_mqs = AsyncMock()
        mock_mqs.query = AsyncMock(return_value=[])
        mock_mqs_class.return_value = mock_mqs

        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="Response")
        mock_llm_class.return_value = mock_llm

        mock_working_memory = MagicMock()
        mock_working_memory.get_context_for_llm.return_value = []
        mock_wmm = MagicMock()
        mock_wmm.get_or_create.return_value = mock_working_memory
        mock_wmm_class.return_value = mock_wmm

        mock_extract = AsyncMock()
        mock_extract.extract_and_store = AsyncMock(return_value=[])
        mock_extract_class.return_value = mock_extract

        service = ChatService()
        result = await service.process_message(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello",
        )

        # Should include timing metadata
        assert "timing" in result
        assert "memory_query_ms" in result["timing"]
        assert "llm_response_ms" in result["timing"]
        assert "total_ms" in result["timing"]
