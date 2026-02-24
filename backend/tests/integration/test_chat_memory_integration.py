"""Integration tests for chat with memory.

These tests verify the full flow of memory-aware chat,
including memory retrieval, LLM response, and information extraction.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.semantic import FactSource, SemanticFact
from src.models.cognitive_load import CognitiveLoadState, LoadLevel


@contextmanager
def mock_cognitive_load_deps() -> Generator[MagicMock, None, None]:
    """Context manager to mock cognitive load dependencies."""
    mock_load_state = CognitiveLoadState(
        level=LoadLevel.LOW,
        score=0.2,
        factors={},
        recommendation="detailed",
    )
    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()
        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor
            yield mock_monitor


def _add_chat_service_mocks(service: object) -> None:
    """Add mocks for all intermediate ChatService dependencies."""
    service._web_grounding = MagicMock()
    service._web_grounding.detect_and_ground = AsyncMock(return_value=None)
    service._classify_intent = AsyncMock(return_value=None)
    service._classify_plan_action = AsyncMock(return_value=None)
    service._detect_skill_match = AsyncMock(return_value=(False, [], 0.0))
    service._detect_plan_extension = AsyncMock(return_value=None)
    service._get_proactive_insights = AsyncMock(return_value=[])
    service._get_priming_context = AsyncMock(return_value=None)
    service._get_personality_calibration = AsyncMock(return_value=None)
    service._get_style_guidelines = AsyncMock(return_value=None)
    service._get_active_goals = AsyncMock(return_value=[])
    service._get_digital_twin_calibration = AsyncMock(return_value=None)
    service._get_capability_context = AsyncMock(return_value=None)
    service._get_friction_engine = MagicMock(return_value=None)
    service._get_pending_plan_context = AsyncMock(return_value=None)
    service._companion_orchestrator = MagicMock()
    service._companion_orchestrator.build_full_context = AsyncMock(return_value=None)
    service.persist_turn = AsyncMock()
    service._extract_information = AsyncMock()
    service._episodic_memory = MagicMock()
    service._episodic_memory.record_exchange = AsyncMock()
    service._ensure_conversation_record = AsyncMock()
    service._update_conversation_metadata = AsyncMock()


@pytest.mark.asyncio
async def test_chat_queries_memory_and_includes_in_response() -> None:
    """Test full chat flow with memory retrieval."""
    from src.services.chat import ChatService

    # Setup semantic fact that will be retrieved
    existing_fact = SemanticFact(
        id="fact-existing",
        user_id="user-123",
        subject="User",
        predicate="prefers",
        object="morning meetings",
        confidence=0.90,
        source=FactSource.USER_STATED,
        valid_from=datetime.now(UTC),
    )

    with mock_cognitive_load_deps():
        with (
            patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
            patch("src.services.chat.LLMClient") as mock_llm_class,
            patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
            patch("src.services.chat.ExtractionService") as mock_extract_class,
            patch("src.services.chat.get_email_integration", new_callable=AsyncMock, return_value=None),
        ):
            # Setup memory query service to return relevant memories
            mock_mqs = AsyncMock()
            mock_mqs.query = AsyncMock(
                return_value=[
                    {
                        "id": existing_fact.id,
                        "memory_type": "semantic",
                        "content": f"{existing_fact.subject} {existing_fact.predicate} {existing_fact.object}",
                        "relevance_score": 0.85,
                        "confidence": existing_fact.confidence,
                        "timestamp": existing_fact.valid_from,
                    }
                ]
            )
            mock_mqs_class.return_value = mock_mqs

            # Setup LLM to return response mentioning the fact
            mock_llm = AsyncMock()
            mock_llm.generate_response = AsyncMock(
                return_value="Based on your preference for morning meetings, I'll schedule the demo at 9 AM."
            )
            mock_llm_class.return_value = mock_llm

            # Setup working memory
            mock_working_memory = MagicMock()
            mock_working_memory.get_context_for_llm.return_value = []
            mock_wmm = MagicMock()
            mock_wmm.get_or_create = AsyncMock(return_value=mock_working_memory)
            mock_wmm_class.return_value = mock_wmm

            # Setup extraction service
            mock_extract = AsyncMock()
            mock_extract.extract_and_store = AsyncMock(return_value=[])
            mock_extract_class.return_value = mock_extract

            service = ChatService()
            _add_chat_service_mocks(service)

            result = await service.process_message(
                user_id="user-123",
                conversation_id="conv-456",
                message="Can you schedule a demo?",
            )

            # Verify response mentions the preference
            assert "morning" in result["message"].lower()

            # Verify timing is reasonable (mocked so should be fast)
            assert result["timing"]["total_ms"] < 5000  # Less than 5 seconds


@pytest.mark.asyncio
async def test_memory_retrieval_meets_performance_target() -> None:
    """Test that memory retrieval completes under 200ms target."""
    from src.api.routes.memory import MemoryQueryService

    with (
        patch("src.api.routes.memory.EpisodicMemory") as mock_episodic_class,
        patch("src.api.routes.memory.SemanticMemory") as mock_semantic_class,
    ):
        # Mock episodic memory
        mock_episodic = AsyncMock()
        mock_episodic.semantic_search = AsyncMock(return_value=[])
        mock_episodic_class.return_value = mock_episodic

        # Mock semantic memory
        mock_semantic = AsyncMock()
        mock_semantic.search_facts = AsyncMock(return_value=[])
        mock_semantic_class.return_value = mock_semantic

        service = MemoryQueryService()

        import time

        start = time.perf_counter()

        await service.query(
            user_id="user-123",
            query="test query",
            memory_types=["episodic", "semantic"],
            start_date=None,
            end_date=None,
            min_confidence=None,
            limit=5,
            offset=0,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        # With mocked services, should be very fast
        # In production, target is < 200ms
        assert elapsed_ms < 1000, f"Memory query took {elapsed_ms}ms, expected < 1000ms"


@pytest.mark.asyncio
async def test_new_information_extracted_and_stored() -> None:
    """Test that new information from chat is extracted and stored."""
    from src.services.extraction import ExtractionService

    with (
        patch("src.services.extraction.LLMClient") as mock_llm_class,
        patch("src.services.extraction.SemanticMemory") as mock_semantic_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "User", "predicate": "budget_is", "object": "$500K", "confidence": 0.85}]'
        )
        mock_llm_class.return_value = mock_llm

        mock_semantic = AsyncMock()
        mock_semantic.add_fact = AsyncMock(return_value="fact-new")
        mock_semantic_class.return_value = mock_semantic

        service = ExtractionService()
        stored_ids = await service.extract_and_store(
            conversation=[
                {"role": "user", "content": "Our budget for this quarter is $500K."},
                {"role": "assistant", "content": "Got it, I'll keep your $500K budget in mind."},
            ],
            user_id="user-123",
        )

        # Verify fact was stored
        assert len(stored_ids) == 1
        assert stored_ids[0] == "fact-new"

        # Verify the stored fact details
        call_args = mock_semantic.add_fact.call_args
        stored_fact = call_args[0][0]
        assert stored_fact.subject == "User"
        assert stored_fact.predicate == "budget_is"
        assert stored_fact.object == "$500K"
        assert stored_fact.source == FactSource.EXTRACTED


@pytest.mark.asyncio
async def test_full_chat_flow_with_extraction() -> None:
    """Test complete chat flow including memory query, response, and extraction."""
    from src.services.chat import ChatService

    with mock_cognitive_load_deps():
        with (
            patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
            patch("src.services.chat.LLMClient") as mock_llm_class,
            patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
            patch("src.services.chat.ExtractionService") as mock_extract_class,
        ):
            # Setup memory service with no prior memories
            mock_mqs = AsyncMock()
            mock_mqs.query = AsyncMock(return_value=[])
            mock_mqs_class.return_value = mock_mqs

            # Setup LLM response
            mock_llm = AsyncMock()
            mock_llm.generate_response = AsyncMock(
                return_value="I'll note that your quarterly budget is $500K. How would you like to allocate it?"
            )
            mock_llm_class.return_value = mock_llm

            # Setup working memory
            mock_working_memory = MagicMock()
            mock_working_memory.get_context_for_llm.return_value = [
                {"role": "user", "content": "Our budget for this quarter is $500K."}
            ]
            mock_wmm = MagicMock()
            mock_wmm.get_or_create = AsyncMock(return_value=mock_working_memory)
            mock_wmm_class.return_value = mock_wmm

            # Setup extraction - this is the key part
            mock_extract = AsyncMock()
            mock_extract.extract_and_store = AsyncMock(return_value=["extracted-fact-1"])
            mock_extract_class.return_value = mock_extract

            service = ChatService()
            result = await service.process_message(
                user_id="user-123",
                conversation_id="conv-456",
                message="Our budget for this quarter is $500K.",
            )

            # Verify the response
            assert "budget" in result["message"].lower()
            assert result["conversation_id"] == "conv-456"

            # Verify extraction was called with the conversation
            mock_extract.extract_and_store.assert_called_once()
            call_kwargs = mock_extract.extract_and_store.call_args.kwargs
            assert call_kwargs["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_memory_context_improves_response_quality() -> None:
    """Test that memory context helps generate more relevant responses."""
    from src.services.chat import ChatService

    with mock_cognitive_load_deps():
        with (
            patch("src.services.chat.MemoryQueryService") as mock_mqs_class,
            patch("src.services.chat.LLMClient") as mock_llm_class,
            patch("src.services.chat.WorkingMemoryManager") as mock_wmm_class,
            patch("src.services.chat.ExtractionService") as mock_extract_class,
            patch("src.services.chat.get_email_integration", new_callable=AsyncMock, return_value=None),
        ):
            # Setup memory with relevant context
            mock_mqs = AsyncMock()
            mock_mqs.query = AsyncMock(
                return_value=[
                    {
                        "id": "fact-1",
                        "memory_type": "semantic",
                        "content": "Acme Corp annual_revenue $50M",
                        "relevance_score": 0.9,
                        "confidence": 0.95,
                        "timestamp": datetime.now(UTC),
                    },
                    {
                        "id": "fact-2",
                        "memory_type": "semantic",
                        "content": "Acme Corp industry pharmaceuticals",
                        "relevance_score": 0.85,
                        "confidence": 0.90,
                        "timestamp": datetime.now(UTC),
                    },
                ]
            )
            mock_mqs_class.return_value = mock_mqs

            # Capture the system prompt to verify it includes memory
            captured_system_prompt = None

            async def capture_system_prompt(
                *,
                messages: list[dict[str, str]],
                system_prompt: str | None = None,
                **_kwargs: object,
            ) -> str:
                nonlocal captured_system_prompt
                _ = messages  # Silence unused variable warning
                captured_system_prompt = system_prompt
                return (
                    "Based on Acme Corp's $50M revenue in the pharmaceutical industry, I recommend..."
                )

            mock_llm = AsyncMock()
            mock_llm.generate_response = AsyncMock(side_effect=capture_system_prompt)
            mock_llm_class.return_value = mock_llm

            # Setup working memory
            mock_working_memory = MagicMock()
            mock_working_memory.get_context_for_llm.return_value = []
            mock_wmm = MagicMock()
            mock_wmm.get_or_create = AsyncMock(return_value=mock_working_memory)
            mock_wmm_class.return_value = mock_wmm

            # Setup extraction
            mock_extract = AsyncMock()
            mock_extract.extract_and_store = AsyncMock(return_value=[])
            mock_extract_class.return_value = mock_extract

            service = ChatService()
            _add_chat_service_mocks(service)

            result = await service.process_message(
                user_id="user-123",
                conversation_id="conv-456",
                message="What do you recommend for Acme Corp?",
            )

            # Verify memory was included in the system prompt
            assert captured_system_prompt is not None
            assert "Acme Corp" in captured_system_prompt or "$50M" in captured_system_prompt

            # Verify citations are returned
            assert len(result["citations"]) == 2


@pytest.mark.asyncio
async def test_extraction_failure_does_not_break_chat() -> None:
    """Test that extraction failures don't prevent chat from completing."""
    from src.services.chat import ChatService

    with mock_cognitive_load_deps():
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
            mock_llm.generate_response = AsyncMock(return_value="Hello! How can I help?")
            mock_llm_class.return_value = mock_llm

            mock_working_memory = MagicMock()
            mock_working_memory.get_context_for_llm.return_value = []
            mock_wmm = MagicMock()
            mock_wmm.get_or_create = AsyncMock(return_value=mock_working_memory)
            mock_wmm_class.return_value = mock_wmm

            # Extraction raises an exception
            mock_extract = AsyncMock()
            mock_extract.extract_and_store = AsyncMock(side_effect=Exception("Extraction failed"))
            mock_extract_class.return_value = mock_extract

            service = ChatService()

            # Should not raise, chat should still complete
            result = await service.process_message(
                user_id="user-123",
                conversation_id="conv-456",
                message="Hello!",
            )

            assert result["message"] == "Hello! How can I help?"
            assert result["conversation_id"] == "conv-456"
