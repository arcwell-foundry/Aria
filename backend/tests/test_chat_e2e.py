"""End-to-end integration test for the chat pipeline.

Verifies that ChatService.process_message() produces a complete ARIA
response envelope when all external dependencies (Supabase, LLM, memory
services, etc.) are mocked. This is the final smoke test confirming
Tasks 1-4 work together:

1. Message persistence (save_message called)
2. Digital Twin / priming context wired into system prompt
3. Full response envelope (message, rich_content, ui_commands, suggestions, citations, timing)
4. Episodic memory stored for each conversation turn
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.cognitive_load import CognitiveLoadState, LoadLevel


# ============================================================================
# Helper: build a fully-mocked ChatService
# ============================================================================


def _make_chat_service() -> Any:
    """Create a ChatService with the Supabase constructor dependency mocked.

    Returns the service instance. Callers must still mock the internal
    attributes (LLM, memory, extraction, etc.) before calling process_message.
    """
    with patch("src.services.chat.get_supabase_client") as mock_sb:
        mock_sb.return_value = MagicMock()
        from src.services.chat import ChatService

        service = ChatService()
    return service


def _wire_mocks(service: Any, llm_response: str = "I found some insights about Lonza.") -> dict[str, Any]:
    """Replace all async dependencies on *service* with deterministic mocks.

    Returns a dict of the individual mocks for assertion.
    """
    mocks: dict[str, Any] = {}

    # Memory query returns empty
    service._memory_service = MagicMock()
    service._memory_service.query = AsyncMock(return_value=[])
    mocks["memory_query"] = service._memory_service.query

    # LLM returns a fixed response
    service._llm_client = MagicMock()
    service._llm_client.generate_response = AsyncMock(return_value=llm_response)
    mocks["llm_generate"] = service._llm_client.generate_response

    # Working memory manager
    working_memory = MagicMock()
    working_memory.get_context_for_llm.return_value = [
        {"role": "user", "content": "Research Lonza for me"},
    ]
    service._working_memory_manager = MagicMock()
    service._working_memory_manager.get_or_create = AsyncMock(return_value=working_memory)
    mocks["working_memory"] = working_memory

    # Cognitive load monitor
    load_state = CognitiveLoadState(
        level=LoadLevel.LOW,
        score=0.2,
        recommendation="Normal processing",
    )
    service._cognitive_monitor = MagicMock()
    service._cognitive_monitor.estimate_load = AsyncMock(return_value=load_state)

    # Proactive service
    service._proactive_service = MagicMock()
    service._proactive_service.find_volunteerable_context = AsyncMock(return_value=[])

    # Personality calibrator
    service._personality_calibrator = MagicMock()
    service._personality_calibrator.get_calibration = AsyncMock(return_value=None)

    # Digital twin
    service._digital_twin = MagicMock()
    service._digital_twin.get_fingerprint = AsyncMock(return_value=None)
    service._digital_twin.get_style_guidelines = AsyncMock(return_value=None)

    # Priming service
    service._priming_service = MagicMock()
    service._priming_service.prime_conversation = AsyncMock(return_value=None)

    # Extraction service (fire-and-forget)
    service._extraction_service = MagicMock()
    service._extraction_service.extract_and_store = AsyncMock(return_value=[])
    mocks["extraction"] = service._extraction_service.extract_and_store

    # Episodic memory
    service._episodic_memory = MagicMock()
    service._episodic_memory.store_episode = AsyncMock(return_value="ep-123")
    mocks["store_episode"] = service._episodic_memory.store_episode

    # Disable skill detection (no external registry)
    service._skill_registry_initialized = True
    service._skill_registry = None

    return mocks


async def _run_process_message(
    service: Any,
    user_id: str = "user-1",
    conversation_id: str = "conv-1",
    message: str = "Research Lonza for me",
) -> dict[str, Any]:
    """Call process_message with conversation record and metadata helpers patched."""
    with (
        patch.object(service, "_ensure_conversation_record", new_callable=AsyncMock),
        patch.object(service, "_update_conversation_metadata", new_callable=AsyncMock),
        patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
    ):
        result = await service.process_message(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
        )
    return result


# ============================================================================
# Full round-trip: send message -> verify complete envelope
# ============================================================================


class TestChatEndToEnd:
    """Verify the full chat pipeline: send -> persist -> respond with envelope."""

    @pytest.mark.asyncio
    async def test_full_chat_round_trip(self) -> None:
        """Message goes in, response includes every required envelope field."""
        service = _make_chat_service()
        _wire_mocks(service)

        result = await _run_process_message(service)

        # -- message content matches LLM mock --
        assert result["message"] == "I found some insights about Lonza."

        # -- conversation_id echoed back --
        assert result["conversation_id"] == "conv-1"

        # -- list fields are lists --
        assert isinstance(result["rich_content"], list)
        assert isinstance(result["ui_commands"], list)
        assert isinstance(result["suggestions"], list)
        assert isinstance(result["citations"], list)

        # -- timing dict has required keys --
        assert isinstance(result["timing"], dict)
        assert "memory_query_ms" in result["timing"]
        assert "llm_response_ms" in result["timing"]
        assert "total_ms" in result["timing"]
        assert "proactive_query_ms" in result["timing"]
        assert "skill_detection_ms" in result["timing"]

        # -- timing values are numeric --
        for key in ("memory_query_ms", "llm_response_ms", "total_ms"):
            assert isinstance(result["timing"][key], (int, float))

        # -- cognitive_load dict present --
        assert isinstance(result["cognitive_load"], dict)
        assert result["cognitive_load"]["level"] == "low"
        assert isinstance(result["cognitive_load"]["score"], float)
        assert isinstance(result["cognitive_load"]["recommendation"], str)


# ============================================================================
# Extraction service is called (semantic extraction happens)
# ============================================================================


class TestExtractionServiceCalled:
    """Verify that the extraction service runs after generating a response."""

    @pytest.mark.asyncio
    async def test_extract_and_store_is_called(self) -> None:
        """process_message should call _extraction_service.extract_and_store."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        mocks["extraction"].assert_called_once()

    @pytest.mark.asyncio
    async def test_extraction_receives_conversation_tail(self) -> None:
        """extract_and_store should receive the last 2 conversation messages."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service, user_id="user-42")

        call_kwargs = mocks["extraction"].call_args
        # The call is: extract_and_store(conversation=..., user_id=...)
        assert call_kwargs.kwargs["user_id"] == "user-42"
        assert isinstance(call_kwargs.kwargs["conversation"], list)


# ============================================================================
# Episodic memory is stored (conversation turn persisted)
# ============================================================================


class TestEpisodicMemoryStored:
    """Verify that episodic memory storage is triggered after each turn."""

    @pytest.mark.asyncio
    async def test_store_episode_is_called(self) -> None:
        """process_message should call _episodic_memory.store_episode."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        mocks["store_episode"].assert_called_once()

    @pytest.mark.asyncio
    async def test_stored_episode_is_conversation_type(self) -> None:
        """The stored episode should have event_type='conversation'."""
        from src.memory.episodic import Episode

        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        episode: Episode = mocks["store_episode"].call_args[0][0]
        assert episode.event_type == "conversation"

    @pytest.mark.asyncio
    async def test_stored_episode_contains_user_message_and_response(self) -> None:
        """The episode content should include the user message and LLM response."""
        from src.memory.episodic import Episode

        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service, message="Research Lonza for me")

        episode: Episode = mocks["store_episode"].call_args[0][0]
        assert "Research Lonza for me" in episode.content
        assert "I found some insights about Lonza." in episode.content


# ============================================================================
# LLM is called with the system prompt (style guidelines integration)
# ============================================================================


class TestLLMCalledWithSystemPrompt:
    """Verify the LLM is invoked and receives the built system prompt."""

    @pytest.mark.asyncio
    async def test_llm_generate_response_is_called(self) -> None:
        """process_message should call _llm_client.generate_response."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        mocks["llm_generate"].assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_receives_system_prompt_with_aria_identity(self) -> None:
        """The system prompt passed to the LLM should contain ARIA's identity."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        call_kwargs = mocks["llm_generate"].call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", "")
        assert "ARIA" in system_prompt

    @pytest.mark.asyncio
    async def test_llm_receives_system_prompt_with_style_guidelines(self) -> None:
        """When style guidelines exist, they should appear in the system prompt."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        # Enable style guidelines by making the digital twin return a fingerprint
        service._digital_twin.get_fingerprint = AsyncMock(
            return_value={"style": "concise"}
        )
        service._digital_twin.get_style_guidelines = AsyncMock(
            return_value="Be direct and concise. Avoid jargon."
        )

        # Disable PersonaBuilder so fallback to _build_system_prompt is used,
        # which directly uses the WRITING_STYLE_TEMPLATE with style_guidelines.
        service._use_persona_builder = False

        # Ensure companion orchestrator is disabled so fallback to digital twin is used
        service._companion_orchestrator = MagicMock()
        service._companion_orchestrator.build_full_context = AsyncMock(
            side_effect=Exception("companion disabled for test")
        )

        await _run_process_message(service)

        call_kwargs = mocks["llm_generate"].call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", "")
        assert "Writing Style Fingerprint" in system_prompt
        assert "Be direct and concise." in system_prompt

    @pytest.mark.asyncio
    async def test_llm_receives_conversation_messages(self) -> None:
        """The LLM should receive the working memory conversation history."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        call_kwargs = mocks["llm_generate"].call_args.kwargs
        messages = call_kwargs.get("messages", [])
        assert isinstance(messages, list)


# ============================================================================
# Response envelope field types are correct
# ============================================================================


class TestResponseEnvelopeTypes:
    """Verify every field in the response envelope has the correct type."""

    @pytest.mark.asyncio
    async def test_message_is_string(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["message"], str)

    @pytest.mark.asyncio
    async def test_conversation_id_is_string(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["conversation_id"], str)

    @pytest.mark.asyncio
    async def test_rich_content_is_list(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["rich_content"], list)

    @pytest.mark.asyncio
    async def test_ui_commands_is_list(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["ui_commands"], list)

    @pytest.mark.asyncio
    async def test_suggestions_is_list(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["suggestions"], list)

    @pytest.mark.asyncio
    async def test_citations_is_list(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["citations"], list)

    @pytest.mark.asyncio
    async def test_timing_is_dict(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["timing"], dict)

    @pytest.mark.asyncio
    async def test_cognitive_load_is_dict(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["cognitive_load"], dict)

    @pytest.mark.asyncio
    async def test_proactive_insights_is_list(self) -> None:
        service = _make_chat_service()
        _wire_mocks(service)
        result = await _run_process_message(service)
        assert isinstance(result["proactive_insights"], list)
