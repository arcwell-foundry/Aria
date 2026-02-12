"""Tests for episodic memory persistence of chat turns.

Verifies that each conversation turn in ChatService.process_message()
is stored as an episodic memory for future recall, and that failures
in episodic storage do not break the chat response.
"""

import uuid as uuid_mod
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.episodic import Episode, EpisodicMemory


# ============================================================================
# ChatService has _episodic_memory attribute
# ============================================================================


class TestChatServiceHasEpisodicMemory:
    """Verify ChatService is wired with an EpisodicMemory instance."""

    @patch("src.services.chat.get_supabase_client")
    def test_chat_service_has_episodic_memory_attribute(
        self, mock_supabase: MagicMock
    ) -> None:
        """ChatService.__init__ should create an _episodic_memory attribute."""
        mock_supabase.return_value = MagicMock()

        from src.services.chat import ChatService

        service = ChatService()
        assert hasattr(service, "_episodic_memory")
        assert isinstance(service._episodic_memory, EpisodicMemory)


# ============================================================================
# Episode creation and fields
# ============================================================================


class TestEpisodeCreation:
    """Verify Episode objects are created with correct fields after a chat turn."""

    @pytest.fixture
    def chat_service(self) -> Any:
        """Create a ChatService with mocked dependencies."""
        with patch("src.services.chat.get_supabase_client") as mock_sb:
            mock_sb.return_value = MagicMock()
            from src.services.chat import ChatService

            service = ChatService()
        return service

    @pytest.fixture
    def mock_dependencies(self, chat_service: Any) -> dict[str, AsyncMock]:
        """Patch all async dependencies on the ChatService to isolate episodic storage."""
        mocks: dict[str, AsyncMock] = {}

        # Memory query returns empty
        chat_service._memory_service = MagicMock()
        chat_service._memory_service.query = AsyncMock(return_value=[])
        mocks["memory_query"] = chat_service._memory_service.query

        # LLM returns a fixed response
        chat_service._llm_client = MagicMock()
        chat_service._llm_client.generate_response = AsyncMock(
            return_value="ARIA test response"
        )
        mocks["llm"] = chat_service._llm_client.generate_response

        # Working memory manager
        working_memory = MagicMock()
        working_memory.get_context_for_llm.return_value = [
            {"role": "user", "content": "Hello"},
        ]
        chat_service._working_memory_manager = MagicMock()
        chat_service._working_memory_manager.get_or_create = AsyncMock(return_value=working_memory)
        mocks["working_memory"] = working_memory

        # Cognitive load monitor
        from src.models.cognitive_load import CognitiveLoadState, LoadLevel

        load_state = CognitiveLoadState(
            level=LoadLevel.LOW,
            score=0.2,
            recommendation="",
        )
        chat_service._cognitive_monitor = MagicMock()
        chat_service._cognitive_monitor.estimate_load = AsyncMock(return_value=load_state)

        # Proactive service
        chat_service._proactive_service = MagicMock()
        chat_service._proactive_service.find_volunteerable_context = AsyncMock(
            return_value=[]
        )

        # Personality calibrator
        chat_service._personality_calibrator = MagicMock()
        chat_service._personality_calibrator.get_calibration = AsyncMock(return_value=None)

        # Digital twin
        chat_service._digital_twin = MagicMock()
        chat_service._digital_twin.get_fingerprint = AsyncMock(return_value=None)

        # Priming service
        chat_service._priming_service = MagicMock()
        chat_service._priming_service.prime_conversation = AsyncMock(return_value=None)

        # Extraction service (fire-and-forget)
        chat_service._extraction_service = MagicMock()
        chat_service._extraction_service.extract_and_store = AsyncMock(return_value=None)
        mocks["extraction"] = chat_service._extraction_service.extract_and_store

        # Episodic memory
        chat_service._episodic_memory = MagicMock()
        chat_service._episodic_memory.store_episode = AsyncMock(return_value="ep-id")
        mocks["store_episode"] = chat_service._episodic_memory.store_episode

        # Skill detection — disable
        chat_service._skill_registry_initialized = True
        chat_service._skill_registry = None

        return mocks

    @pytest.mark.asyncio
    async def test_episode_stored_after_chat_turn(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """process_message should call store_episode after generating a response."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="What is Lonza's market share?",
            )

        mock_dependencies["store_episode"].assert_called_once()

    @pytest.mark.asyncio
    async def test_episode_has_correct_event_type(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The stored episode should have event_type='conversation'."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Tell me about Catalent.",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert episode.event_type == "conversation"

    @pytest.mark.asyncio
    async def test_episode_content_contains_user_message_and_response(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode content should contain both the user message and ARIA response."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="What is Lonza's market share?",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert "What is Lonza's market share?" in episode.content
        assert "ARIA test response" in episode.content

    @pytest.mark.asyncio
    async def test_episode_has_valid_uuid_id(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode should have a valid UUID as its ID."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        parsed = uuid_mod.UUID(episode.id)
        assert str(parsed) == episode.id

    @pytest.mark.asyncio
    async def test_episode_has_correct_user_id(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode user_id should match the caller's user_id."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-xyz",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert episode.user_id == "user-xyz"

    @pytest.mark.asyncio
    async def test_episode_participants_include_user_and_aria(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode participants should include the user_id and 'aria'."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert "user-123" in episode.participants
        assert "aria" in episode.participants

    @pytest.mark.asyncio
    async def test_episode_has_occurred_at_and_recorded_at(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode should have both occurred_at and recorded_at datetime fields."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert isinstance(episode.occurred_at, datetime)
        assert isinstance(episode.recorded_at, datetime)
        assert episode.occurred_at.tzinfo is not None
        assert episode.recorded_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_episode_context_has_conversation_metadata(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The episode context dict should contain conversation_id and memory_count."""
        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        assert episode.context["conversation_id"] == "conv-abc"
        assert "memory_count" in episode.context
        assert "had_skill_execution" in episode.context

    @pytest.mark.asyncio
    async def test_episode_content_truncates_long_responses(
        self, chat_service: Any, mock_dependencies: dict[str, AsyncMock]
    ) -> None:
        """The ARIA response portion should be truncated to 500 chars in the episode content."""
        # Set LLM to return a very long response
        long_response = "A" * 1000
        chat_service._llm_client.generate_response = AsyncMock(return_value=long_response)

        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello",
            )

        episode: Episode = mock_dependencies["store_episode"].call_args[0][0]
        # "ARIA responded: " prefix + 500 chars of 'A'
        assert "A" * 500 in episode.content
        assert "A" * 501 not in episode.content


# ============================================================================
# Episodic storage failure does not break chat
# ============================================================================


class TestEpisodicStorageFailureResilience:
    """Verify that failures in episodic memory storage do not break the chat response."""

    @pytest.fixture
    def chat_service(self) -> Any:
        """Create a ChatService with mocked dependencies."""
        with patch("src.services.chat.get_supabase_client") as mock_sb:
            mock_sb.return_value = MagicMock()
            from src.services.chat import ChatService

            service = ChatService()
        return service

    @pytest.mark.asyncio
    async def test_chat_returns_response_when_episodic_storage_fails(
        self, chat_service: Any
    ) -> None:
        """process_message should return a valid response even if store_episode raises."""
        # Patch all dependencies
        chat_service._memory_service = MagicMock()
        chat_service._memory_service.query = AsyncMock(return_value=[])

        chat_service._llm_client = MagicMock()
        chat_service._llm_client.generate_response = AsyncMock(
            return_value="ARIA response"
        )

        working_memory = MagicMock()
        working_memory.get_context_for_llm.return_value = [
            {"role": "user", "content": "Hello"},
        ]
        chat_service._working_memory_manager = MagicMock()
        chat_service._working_memory_manager.get_or_create = AsyncMock(return_value=working_memory)

        from src.models.cognitive_load import CognitiveLoadState, LoadLevel

        load_state = CognitiveLoadState(
            level=LoadLevel.LOW, score=0.2, recommendation=""
        )
        chat_service._cognitive_monitor = MagicMock()
        chat_service._cognitive_monitor.estimate_load = AsyncMock(return_value=load_state)

        chat_service._proactive_service = MagicMock()
        chat_service._proactive_service.find_volunteerable_context = AsyncMock(
            return_value=[]
        )

        chat_service._personality_calibrator = MagicMock()
        chat_service._personality_calibrator.get_calibration = AsyncMock(return_value=None)

        chat_service._digital_twin = MagicMock()
        chat_service._digital_twin.get_fingerprint = AsyncMock(return_value=None)

        chat_service._priming_service = MagicMock()
        chat_service._priming_service.prime_conversation = AsyncMock(return_value=None)

        chat_service._extraction_service = MagicMock()
        chat_service._extraction_service.extract_and_store = AsyncMock(return_value=None)

        # Make episodic memory FAIL
        chat_service._episodic_memory = MagicMock()
        chat_service._episodic_memory.store_episode = AsyncMock(
            side_effect=RuntimeError("Graphiti connection failed")
        )

        # Disable skill detection
        chat_service._skill_registry_initialized = True
        chat_service._skill_registry = None

        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
        ):
            result = await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello ARIA",
            )

        # The response should still be returned despite episodic failure
        assert result["message"] == "ARIA response"
        assert "conversation_id" in result
        assert "timing" in result

    @pytest.mark.asyncio
    async def test_episodic_failure_is_logged_not_raised(
        self, chat_service: Any
    ) -> None:
        """Episodic memory failures should be caught and logged as warnings."""
        # Patch all dependencies
        chat_service._memory_service = MagicMock()
        chat_service._memory_service.query = AsyncMock(return_value=[])

        chat_service._llm_client = MagicMock()
        chat_service._llm_client.generate_response = AsyncMock(
            return_value="ARIA response"
        )

        working_memory = MagicMock()
        working_memory.get_context_for_llm.return_value = [
            {"role": "user", "content": "Hello"},
        ]
        chat_service._working_memory_manager = MagicMock()
        chat_service._working_memory_manager.get_or_create = AsyncMock(return_value=working_memory)

        from src.models.cognitive_load import CognitiveLoadState, LoadLevel

        load_state = CognitiveLoadState(
            level=LoadLevel.LOW, score=0.2, recommendation=""
        )
        chat_service._cognitive_monitor = MagicMock()
        chat_service._cognitive_monitor.estimate_load = AsyncMock(return_value=load_state)

        chat_service._proactive_service = MagicMock()
        chat_service._proactive_service.find_volunteerable_context = AsyncMock(
            return_value=[]
        )

        chat_service._personality_calibrator = MagicMock()
        chat_service._personality_calibrator.get_calibration = AsyncMock(return_value=None)

        chat_service._digital_twin = MagicMock()
        chat_service._digital_twin.get_fingerprint = AsyncMock(return_value=None)

        chat_service._priming_service = MagicMock()
        chat_service._priming_service.prime_conversation = AsyncMock(return_value=None)

        chat_service._extraction_service = MagicMock()
        chat_service._extraction_service.extract_and_store = AsyncMock(return_value=None)

        # Make episodic memory FAIL
        chat_service._episodic_memory = MagicMock()
        chat_service._episodic_memory.store_episode = AsyncMock(
            side_effect=RuntimeError("Neo4j down")
        )

        chat_service._skill_registry_initialized = True
        chat_service._skill_registry = None

        with (
            patch.object(chat_service, "_ensure_conversation_record", new_callable=AsyncMock),
            patch.object(chat_service, "_update_conversation_metadata", new_callable=AsyncMock),
            patch("src.services.chat.get_supabase_client", return_value=MagicMock()),
            patch("src.services.chat.logger") as mock_logger,
        ):
            result = await chat_service.process_message(
                user_id="user-123",
                conversation_id="conv-abc",
                message="Hello ARIA",
            )

        # Should have logged a warning about the failure
        mock_logger.warning.assert_any_call(
            "Failed to store episodic memory: %s",
            mock_logger.warning.call_args_list[-1][0][1]
            if mock_logger.warning.call_args_list
            else None,
        )

        # Response should still be valid
        assert result["message"] == "ARIA response"
