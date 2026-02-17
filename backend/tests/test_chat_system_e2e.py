"""System-level end-to-end tests for the chat pipeline.

Builds on the helpers defined in ``test_chat_e2e`` to verify higher-level
behaviours:

1. Response envelope completeness (all 6 required fields with correct types)
2. CompanionOrchestrator integration (build_full_context enhances system prompt)
3. Memory storage after each chat turn (working + episodic)
4. Memory retrieval across follow-up messages
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_chat_e2e import _make_chat_service, _run_process_message, _wire_mocks


# ============================================================================
# 1. Response envelope contains all required fields with correct types
# ============================================================================


class TestChatResponseEnvelope:
    """Every chat response must include the 6 required envelope fields."""

    @pytest.mark.asyncio
    async def test_chat_response_envelope(self) -> None:
        """Verify response includes message, rich_content, ui_commands,
        suggestions, citations, and timing with correct types."""
        service = _make_chat_service()
        _wire_mocks(service)

        result = await _run_process_message(service)

        # All 6 required fields must be present
        assert "message" in result
        assert "rich_content" in result
        assert "ui_commands" in result
        assert "suggestions" in result
        assert "citations" in result
        assert "timing" in result

        # Type checks
        assert isinstance(result["message"], str)
        assert isinstance(result["rich_content"], list)
        assert isinstance(result["ui_commands"], list)
        assert isinstance(result["suggestions"], list)
        assert isinstance(result["citations"], list)
        assert isinstance(result["timing"], dict)

        # message must contain the LLM mock response
        assert result["message"] == "I found some insights about Lonza."

        # timing must have numeric values for core keys
        for key in ("memory_query_ms", "llm_response_ms", "total_ms"):
            assert key in result["timing"]
            assert isinstance(result["timing"][key], (int, float))


# ============================================================================
# 2. CompanionOrchestrator enhances the LLM system prompt
# ============================================================================


class TestCompanionEnhancesResponse:
    """Verify CompanionOrchestrator.build_full_context() is called and its
    output is injected into the system prompt sent to the LLM."""

    @pytest.mark.asyncio
    async def test_companion_enhances_response(self) -> None:
        """build_full_context output should appear in the LLM system prompt."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        # Build a mock CompanionContext that renders recognisable sections
        mock_companion_ctx = MagicMock()
        mock_companion_ctx.to_system_prompt_sections.return_value = (
            "## Communication Style Calibration\n"
            "Direct, analytical\n\n"
            "## Emotional Context\n"
            "- Detected: engaged\n"
            "- Acknowledgment: User is engaged"
        )
        mock_companion_ctx.build_time_ms = 42.0
        mock_companion_ctx.failed_subsystems = []
        mock_companion_ctx.mental_state = None

        # Wire the companion orchestrator to return our mock context
        service._companion_orchestrator = MagicMock()
        service._companion_orchestrator.build_full_context = AsyncMock(
            return_value=mock_companion_ctx
        )
        service._companion_orchestrator.post_response_hooks = AsyncMock()
        service._companion_orchestrator.generate_ui_commands = MagicMock(return_value=[])

        result = await _run_process_message(service)

        # build_full_context must have been called
        service._companion_orchestrator.build_full_context.assert_called_once()

        # The system prompt passed to LLM should contain companion sections
        call_kwargs = mocks["llm_generate"].call_args.kwargs
        system_prompt: str = call_kwargs.get("system_prompt", "")
        assert "Emotional Context" in system_prompt or "Communication Style" in system_prompt

        # Response should still be valid
        assert result["message"] == "I found some insights about Lonza."


# ============================================================================
# 3. Memory is stored after each chat turn
# ============================================================================


class TestMemoryStoredAfterChat:
    """Working memory and episodic memory should be updated after a turn."""

    @pytest.mark.asyncio
    async def test_memory_stored_after_chat(self) -> None:
        """After process_message, episodic memory store and working memory
        get_or_create must both have been called."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        await _run_process_message(service)

        # Episodic memory store_episode must be called exactly once
        mocks["store_episode"].assert_called_once()

        # Working memory manager get_or_create must have been called
        # (called at the start of process_message and again during
        # plan extension detection)
        assert service._working_memory_manager.get_or_create.call_count >= 1

        # The working_memory mock should have had add_message called
        # (once for the user message, once for the assistant response)
        wm = mocks["working_memory"]
        assert wm.add_message.call_count == 2
        # First call: user message
        assert wm.add_message.call_args_list[0][0][0] == "user"
        # Second call: assistant response
        assert wm.add_message.call_args_list[1][0][0] == "assistant"


# ============================================================================
# 4. Follow-up message triggers memory retrieval with prior context
# ============================================================================


class TestFollowUpRetrievesMemory:
    """On a second message, memory_query should be called with prior context."""

    @pytest.mark.asyncio
    async def test_follow_up_retrieves_memory(self) -> None:
        """Two sequential messages should each trigger a memory query,
        and on the second call the memory store should contain prior data."""
        service = _make_chat_service()
        mocks = _wire_mocks(service)

        # First message — memory returns empty (default from _wire_mocks)
        await _run_process_message(
            service,
            user_id="user-1",
            conversation_id="conv-1",
            message="Research Lonza for me",
        )

        # After first message, memory_query should have been called once
        assert mocks["memory_query"].call_count == 1

        # Now simulate memory returning prior context on the next query
        mocks["memory_query"].return_value = [
            {
                "id": "mem-001",
                "content": "Research Lonza for me",
                "memory_type": "episodic",
                "confidence": 0.9,
            },
        ]

        # Second message — a follow-up question
        await _run_process_message(
            service,
            user_id="user-1",
            conversation_id="conv-1",
            message="What about their pricing?",
        )

        # memory_query should now have been called at least twice (once per message)
        assert mocks["memory_query"].call_count >= 2

        # The second call should have received the follow-up message as the query
        second_call_kwargs = mocks["memory_query"].call_args_list[1].kwargs
        assert second_call_kwargs["query"] == "What about their pricing?"
        assert second_call_kwargs["user_id"] == "user-1"
