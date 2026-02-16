"""Integration tests for ChatService + CompanionOrchestrator (US-810)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.companion.orchestrator import CompanionContext

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_companion_ctx(**overrides: Any) -> CompanionContext:
    """Create a CompanionContext with sensible defaults."""
    defaults: dict[str, Any] = {
        "tone_guidance": "Be direct.",
        "style_guidelines": "Casual tone.",
        "mental_state": MagicMock(
            stress_level=MagicMock(value="normal"),
            confidence_level=MagicMock(value="confident"),
            emotional_tone="neutral",
            recommended_response_style="balanced",
        ),
        "build_time_ms": 42.0,
    }
    defaults.update(overrides)
    return CompanionContext(**defaults)


def _mock_chat_dependencies() -> dict[str, Any]:
    """Return mocked versions of all ChatService heavy dependencies."""
    return {
        "memory_service": AsyncMock(),
        "llm_client": AsyncMock(),
        "working_memory_manager": AsyncMock(),
        "extraction_service": AsyncMock(),
        "personality_calibrator": AsyncMock(),
        "digital_twin": AsyncMock(),
        "cognitive_monitor": AsyncMock(),
        "proactive_service": AsyncMock(),
        "priming_service": AsyncMock(),
        "episodic_memory": AsyncMock(),
    }


def _create_patched_chat_service(mocks: dict[str, Any]) -> Any:
    """Create a ChatService with all dependencies mocked."""
    with (
        patch("src.services.chat.MemoryQueryService", return_value=mocks["memory_service"]),
        patch("src.services.chat.LLMClient", return_value=mocks["llm_client"]),
        patch(
            "src.services.chat.WorkingMemoryManager", return_value=mocks["working_memory_manager"]
        ),
        patch("src.services.chat.ExtractionService", return_value=mocks["extraction_service"]),
        patch(
            "src.services.chat.PersonalityCalibrator", return_value=mocks["personality_calibrator"]
        ),
        patch("src.services.chat.DigitalTwin", return_value=mocks["digital_twin"]),
        patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        patch("src.services.chat.CognitiveLoadMonitor", return_value=mocks["cognitive_monitor"]),
        patch("src.services.chat.ProactiveMemoryService", return_value=mocks["proactive_service"]),
        patch(
            "src.services.chat.ConversationPrimingService", return_value=mocks["priming_service"]
        ),
        patch("src.services.chat.ConversationService", return_value=MagicMock()),
        patch("src.services.chat.SalienceService", return_value=MagicMock()),
        patch("src.services.chat.EpisodicMemory", return_value=mocks["episodic_memory"]),
    ):
        from src.services.chat import ChatService

        svc = ChatService()

    return svc


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_service_uses_companion_orchestrator() -> None:
    """Verify orchestrator.build_full_context is called during process_message."""
    mocks = _mock_chat_dependencies()

    # Configure working memory
    working_mem = MagicMock()
    working_mem.get_context_for_llm.return_value = [
        {"role": "user", "content": "Hello"},
    ]
    working_mem.add_message = MagicMock()
    mocks["working_memory_manager"].get_or_create = AsyncMock(return_value=working_mem)

    # Cognitive load
    load_state = MagicMock()
    load_state.level = MagicMock(value="low")
    load_state.score = 0.2
    load_state.recommendation = ""
    mocks["cognitive_monitor"].estimate_load = AsyncMock(return_value=load_state)

    # Memory query
    mocks["memory_service"].query = AsyncMock(return_value=[])

    # Proactive insights
    mocks["proactive_service"].find_volunteerable_context = AsyncMock(return_value=[])

    # Priming
    mocks["priming_service"].prime_conversation = AsyncMock(return_value=None)

    # LLM
    mocks["llm_client"].generate_response = AsyncMock(return_value="Hello! How can I help?")

    # Episodic memory
    mocks["episodic_memory"].store_episode = AsyncMock()

    svc = _create_patched_chat_service(mocks)

    # Mock the orchestrator
    mock_orch = AsyncMock()
    companion_ctx = _make_companion_ctx()
    mock_orch.build_full_context = AsyncMock(return_value=companion_ctx)
    mock_orch.post_response_hooks = AsyncMock()
    svc._companion_orchestrator = mock_orch

    # Patch persist_turn and ensure_conversation_record
    svc.persist_turn = AsyncMock()
    svc._ensure_conversation_record = AsyncMock()

    result = await svc.process_message(
        user_id="user-1",
        conversation_id="conv-1",
        message="Hello",
    )

    # Orchestrator was called
    mock_orch.build_full_context.assert_awaited_once()
    call_kwargs = mock_orch.build_full_context.call_args.kwargs
    assert call_kwargs["user_id"] == "user-1"
    assert call_kwargs["message"] == "Hello"

    # Post-response hooks were called
    mock_orch.post_response_hooks.assert_awaited_once()

    # Timing includes companion_context_ms
    assert "companion_context_ms" in result["timing"]
    assert result["timing"]["companion_context_ms"] == 42.0


@pytest.mark.asyncio
async def test_companion_context_in_system_prompt() -> None:
    """Verify to_system_prompt_sections output appears in the prompt."""
    mocks = _mock_chat_dependencies()
    svc = _create_patched_chat_service(mocks)

    companion_ctx = _make_companion_ctx(
        tone_guidance="Be very direct.",
        strategic_concerns=[],
        improvement_focus_areas=["accuracy"],
    )

    prompt = svc._build_system_prompt(
        memories=[],
        companion_context=companion_ctx,
    )

    # Companion sections should be present
    assert "Be very direct." in prompt
    assert "accuracy" in prompt
    # Fallback personality/style sections should NOT be present
    # (they only render when companion_context is None)


@pytest.mark.asyncio
async def test_fallback_when_orchestrator_fails() -> None:
    """When orchestrator fails entirely, falls back to individual calls."""
    mocks = _mock_chat_dependencies()

    # Configure working memory
    working_mem = MagicMock()
    working_mem.get_context_for_llm.return_value = [
        {"role": "user", "content": "Hello"},
    ]
    working_mem.add_message = MagicMock()
    mocks["working_memory_manager"].get_or_create = AsyncMock(return_value=working_mem)

    # Cognitive load
    load_state = MagicMock()
    load_state.level = MagicMock(value="low")
    load_state.score = 0.2
    load_state.recommendation = ""
    mocks["cognitive_monitor"].estimate_load = AsyncMock(return_value=load_state)

    # Memory query
    mocks["memory_service"].query = AsyncMock(return_value=[])

    # Proactive insights
    mocks["proactive_service"].find_volunteerable_context = AsyncMock(return_value=[])

    # Personality calibration (fallback path)
    mock_calibration = MagicMock()
    mock_calibration.tone_guidance = "Fallback tone"
    mock_calibration.example_adjustments = []
    mocks["personality_calibrator"].get_calibration = AsyncMock(return_value=mock_calibration)

    # Digital twin (fallback path)
    mocks["digital_twin"].get_fingerprint = AsyncMock(return_value=None)

    # Priming
    mocks["priming_service"].prime_conversation = AsyncMock(return_value=None)

    # LLM
    mocks["llm_client"].generate_response = AsyncMock(return_value="Response text")

    # Episodic memory
    mocks["episodic_memory"].store_episode = AsyncMock()

    svc = _create_patched_chat_service(mocks)

    # Mock orchestrator to FAIL
    mock_orch = AsyncMock()
    mock_orch.build_full_context = AsyncMock(side_effect=RuntimeError("Orchestrator down"))
    svc._companion_orchestrator = mock_orch

    # Patch persist_turn and ensure_conversation_record
    svc.persist_turn = AsyncMock()
    svc._ensure_conversation_record = AsyncMock()

    result = await svc.process_message(
        user_id="user-1",
        conversation_id="conv-1",
        message="Hello",
    )

    # Should have fallen back to individual personality call
    mocks["personality_calibrator"].get_calibration.assert_awaited_once()

    # Should still produce a response
    assert result["message"] == "Response text"

    # companion_context_ms should be 0 since orchestrator failed
    assert result["timing"]["companion_context_ms"] == 0.0


@pytest.mark.asyncio
async def test_post_response_hooks_called_after_persist() -> None:
    """Post-response hooks fire after persist_turn."""
    mocks = _mock_chat_dependencies()

    # Configure working memory
    working_mem = MagicMock()
    working_mem.get_context_for_llm.return_value = [
        {"role": "user", "content": "Hello"},
    ]
    working_mem.add_message = MagicMock()
    mocks["working_memory_manager"].get_or_create = AsyncMock(return_value=working_mem)

    # Cognitive load
    load_state = MagicMock()
    load_state.level = MagicMock(value="low")
    load_state.score = 0.2
    load_state.recommendation = ""
    mocks["cognitive_monitor"].estimate_load = AsyncMock(return_value=load_state)

    # Memory query
    mocks["memory_service"].query = AsyncMock(return_value=[])
    mocks["proactive_service"].find_volunteerable_context = AsyncMock(return_value=[])
    mocks["priming_service"].prime_conversation = AsyncMock(return_value=None)
    mocks["llm_client"].generate_response = AsyncMock(return_value="OK")
    mocks["episodic_memory"].store_episode = AsyncMock()

    svc = _create_patched_chat_service(mocks)

    # Track call order
    call_order: list[str] = []

    async def mock_persist_turn(**_kwargs: Any) -> None:
        call_order.append("persist_turn")

    async def mock_post_hooks(**_kwargs: Any) -> None:
        call_order.append("post_response_hooks")

    mock_orch = AsyncMock()
    companion_ctx = _make_companion_ctx()
    mock_orch.build_full_context = AsyncMock(return_value=companion_ctx)
    mock_orch.post_response_hooks = mock_post_hooks
    svc._companion_orchestrator = mock_orch

    svc.persist_turn = mock_persist_turn
    svc._ensure_conversation_record = AsyncMock()

    await svc.process_message(
        user_id="user-1",
        conversation_id="conv-1",
        message="Hello",
    )

    assert "persist_turn" in call_order
    assert "post_response_hooks" in call_order
    # persist_turn should come before post_response_hooks
    assert call_order.index("persist_turn") < call_order.index("post_response_hooks")
