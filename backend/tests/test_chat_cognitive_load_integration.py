"""Tests for chat service cognitive load integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_chat_includes_cognitive_load_in_response() -> None:
    """ChatService should include cognitive load state in response."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.HIGH,
        score=0.65,
        factors={"message_brevity": 0.8},
        recommendation="concise",
    )

    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()

        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor

            with patch("src.services.chat.LLMClient") as mock_llm:
                mock_llm.return_value.generate_response = AsyncMock(return_value="Test response")

                with patch("src.services.chat.MemoryQueryService") as mock_memory:
                    mock_memory.return_value.query = AsyncMock(return_value=[])

                    with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                        mock_wm = MagicMock()
                        mock_wm.get_context_for_llm.return_value = []
                        mock_working.return_value.get_or_create.return_value = mock_wm

                        with patch("src.services.chat.ExtractionService"):
                            with patch.object(
                                ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                                ):
                                    service = ChatService()
                                    result = await service.process_message(
                                        user_id="user-123",
                                        conversation_id="conv-123",
                                        message="Help me quick",
                                    )

    assert "cognitive_load" in result
    assert result["cognitive_load"]["level"] == "high"
    assert result["cognitive_load"]["recommendation"] == "concise"


@pytest.mark.asyncio
async def test_high_load_modifies_system_prompt() -> None:
    """When load is high, system prompt should instruct concise responses."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.HIGH,
        score=0.72,
        factors={},
        recommendation="concise",
    )

    captured_system_prompt = None

    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()

        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor

            with patch("src.services.chat.LLMClient") as mock_llm:
                async def capture_prompt(*args, **kwargs):
                    nonlocal captured_system_prompt
                    captured_system_prompt = kwargs.get("system_prompt", "")
                    return "Response"

                mock_llm.return_value.generate_response = capture_prompt

                with patch("src.services.chat.MemoryQueryService") as mock_memory:
                    mock_memory.return_value.query = AsyncMock(return_value=[])

                    with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                        mock_wm = MagicMock()
                        mock_wm.get_context_for_llm.return_value = []
                        mock_working.return_value.get_or_create.return_value = mock_wm

                        with patch("src.services.chat.ExtractionService"):
                            with patch.object(
                                ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                                ):
                                    service = ChatService()
                                    await service.process_message(
                                        user_id="user-123",
                                        conversation_id="conv-123",
                                        message="Need help",
                                    )

    assert captured_system_prompt is not None
    assert "concise" in captured_system_prompt.lower() or "brief" in captured_system_prompt.lower()


@pytest.mark.asyncio
async def test_low_load_does_not_add_high_load_instruction() -> None:
    """When load is low, system prompt should not include high load instruction."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.LOW,
        score=0.15,
        factors={},
        recommendation="detailed",
    )

    captured_system_prompt = None

    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()

        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor

            with patch("src.services.chat.LLMClient") as mock_llm:
                async def capture_prompt(*args, **kwargs):
                    nonlocal captured_system_prompt
                    captured_system_prompt = kwargs.get("system_prompt", "")
                    return "Response"

                mock_llm.return_value.generate_response = capture_prompt

                with patch("src.services.chat.MemoryQueryService") as mock_memory:
                    mock_memory.return_value.query = AsyncMock(return_value=[])

                    with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                        mock_wm = MagicMock()
                        mock_wm.get_context_for_llm.return_value = []
                        mock_working.return_value.get_or_create.return_value = mock_wm

                        with patch("src.services.chat.ExtractionService"):
                            with patch.object(
                                ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                                ):
                                    service = ChatService()
                                    await service.process_message(
                                        user_id="user-123",
                                        conversation_id="conv-123",
                                        message="I have a question when you have time",
                                    )

    assert captured_system_prompt is not None
    # The HIGH_LOAD_INSTRUCTION contains "cognitive load" and "extremely concise"
    assert "extremely concise" not in captured_system_prompt.lower()


@pytest.mark.asyncio
async def test_critical_load_also_adds_high_load_instruction() -> None:
    """When load is critical, system prompt should include high load instruction."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.CRITICAL,
        score=0.92,
        factors={},
        recommendation="concise_urgent",
    )

    captured_system_prompt = None

    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()

        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor

            with patch("src.services.chat.LLMClient") as mock_llm:
                async def capture_prompt(*args, **kwargs):
                    nonlocal captured_system_prompt
                    captured_system_prompt = kwargs.get("system_prompt", "")
                    return "Response"

                mock_llm.return_value.generate_response = capture_prompt

                with patch("src.services.chat.MemoryQueryService") as mock_memory:
                    mock_memory.return_value.query = AsyncMock(return_value=[])

                    with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                        mock_wm = MagicMock()
                        mock_wm.get_context_for_llm.return_value = []
                        mock_working.return_value.get_or_create.return_value = mock_wm

                        with patch("src.services.chat.ExtractionService"):
                            with patch.object(
                                ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                                ):
                                    service = ChatService()
                                    await service.process_message(
                                        user_id="user-123",
                                        conversation_id="conv-123",
                                        message="URGENT!!!",
                                    )

    assert captured_system_prompt is not None
    assert "concise" in captured_system_prompt.lower() or "brief" in captured_system_prompt.lower()
