"""Tests for conversation episode service."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_conversation_service_exported_from_memory_module() -> None:
    """ConversationService should be importable from src.memory."""
    from src.memory import ConversationEpisode, ConversationService

    assert ConversationService is not None
    assert ConversationEpisode is not None


def test_conversation_episode_module_importable() -> None:
    """ConversationEpisode should be importable from memory.conversation."""
    from src.memory.conversation import ConversationEpisode

    assert ConversationEpisode is not None


def test_conversation_episode_initialization() -> None:
    """ConversationEpisode should initialize with required fields."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    episode = ConversationEpisode(
        id="ep-123",
        user_id="user-456",
        conversation_id="conv-789",
        summary="Discussed Q1 sales targets and pricing strategy.",
        key_topics=["sales", "pricing", "Q1"],
        entities_discussed=["John Doe", "Acme Corp"],
        user_state={"mood": "focused", "confidence": "high"},
        outcomes=[{"type": "decision", "content": "Will send proposal by Friday"}],
        open_threads=[
            {"topic": "pricing", "status": "pending", "context": "awaiting CFO approval"}
        ],
        message_count=15,
        duration_minutes=25,
        started_at=now - timedelta(minutes=25),
        ended_at=now,
    )

    assert episode.id == "ep-123"
    assert episode.user_id == "user-456"
    assert episode.conversation_id == "conv-789"
    assert episode.summary == "Discussed Q1 sales targets and pricing strategy."
    assert len(episode.key_topics) == 3
    assert len(episode.entities_discussed) == 2
    assert episode.user_state["mood"] == "focused"
    assert len(episode.outcomes) == 1
    assert len(episode.open_threads) == 1
    assert episode.message_count == 15
    assert episode.duration_minutes == 25


def test_conversation_episode_to_dict() -> None:
    """ConversationEpisode.to_dict should return serializable dict."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    episode = ConversationEpisode(
        id="ep-123",
        user_id="user-456",
        conversation_id="conv-789",
        summary="Test summary",
        key_topics=["topic1"],
        entities_discussed=["Entity1"],
        user_state={"mood": "neutral"},
        outcomes=[],
        open_threads=[],
        message_count=5,
        duration_minutes=10,
        started_at=now - timedelta(minutes=10),
        ended_at=now,
    )

    data = episode.to_dict()

    assert data["id"] == "ep-123"
    assert data["summary"] == "Test summary"
    assert isinstance(data["started_at"], str)
    assert isinstance(data["ended_at"], str)

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_conversation_episode_from_dict() -> None:
    """ConversationEpisode.from_dict should create episode from dict."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    data = {
        "id": "ep-123",
        "user_id": "user-456",
        "conversation_id": "conv-789",
        "summary": "Restored summary",
        "key_topics": ["restored"],
        "entities_discussed": ["Entity"],
        "user_state": {"mood": "happy"},
        "outcomes": [{"type": "action", "content": "Follow up"}],
        "open_threads": [],
        "message_count": 8,
        "duration_minutes": 15,
        "started_at": now.isoformat(),
        "ended_at": now.isoformat(),
    }

    episode = ConversationEpisode.from_dict(data)

    assert episode.id == "ep-123"
    assert episode.summary == "Restored summary"
    assert episode.user_state["mood"] == "happy"
    assert len(episode.outcomes) == 1


def test_conversation_episode_default_salience_fields() -> None:
    """ConversationEpisode should have default salience tracking fields."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    episode = ConversationEpisode(
        id="ep-123",
        user_id="user-456",
        conversation_id="conv-789",
        summary="Test",
        key_topics=[],
        entities_discussed=[],
        user_state={},
        outcomes=[],
        open_threads=[],
        message_count=1,
        duration_minutes=1,
        started_at=now,
        ended_at=now,
    )

    # Default salience should be 1.0 (fresh memory)
    assert episode.current_salience == 1.0
    # Access count should start at 0
    assert episode.access_count == 0
    # last_accessed_at should be set
    assert episode.last_accessed_at is not None


def test_conversation_episode_to_dict_includes_salience_fields() -> None:
    """ConversationEpisode.to_dict should include salience tracking fields."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    episode = ConversationEpisode(
        id="ep-123",
        user_id="user-456",
        conversation_id="conv-789",
        summary="Test",
        key_topics=[],
        entities_discussed=[],
        user_state={},
        outcomes=[],
        open_threads=[],
        message_count=1,
        duration_minutes=1,
        started_at=now,
        ended_at=now,
        current_salience=0.85,
        last_accessed_at=now,
        access_count=3,
    )

    data = episode.to_dict()

    assert data["current_salience"] == 0.85
    assert data["access_count"] == 3
    assert "last_accessed_at" in data
    assert isinstance(data["last_accessed_at"], str)


def test_conversation_episode_from_dict_restores_salience_fields() -> None:
    """ConversationEpisode.from_dict should restore salience tracking fields."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    data = {
        "id": "ep-123",
        "user_id": "user-456",
        "conversation_id": "conv-789",
        "summary": "Test",
        "key_topics": [],
        "entities_discussed": [],
        "user_state": {},
        "outcomes": [],
        "open_threads": [],
        "message_count": 1,
        "duration_minutes": 1,
        "started_at": now.isoformat(),
        "ended_at": now.isoformat(),
        "current_salience": 0.75,
        "last_accessed_at": now.isoformat(),
        "access_count": 5,
    }

    episode = ConversationEpisode.from_dict(data)

    assert episode.current_salience == 0.75
    assert episode.access_count == 5
    assert episode.last_accessed_at == now


def test_conversation_episode_from_dict_handles_missing_salience_fields() -> None:
    """ConversationEpisode.from_dict should handle missing salience fields gracefully."""
    from src.memory.conversation import ConversationEpisode

    now = datetime.now(UTC)
    data = {
        "id": "ep-123",
        "user_id": "user-456",
        "conversation_id": "conv-789",
        "summary": "Old episode without salience",
        "key_topics": [],
        "entities_discussed": [],
        "user_state": {},
        "outcomes": [],
        "open_threads": [],
        "message_count": 1,
        "duration_minutes": 1,
        "started_at": now.isoformat(),
        "ended_at": now.isoformat(),
        # No salience fields - should use defaults
    }

    episode = ConversationEpisode.from_dict(data)

    # Should use default values
    assert episode.current_salience == 1.0
    assert episode.access_count == 0
    assert episode.last_accessed_at is not None


# ============================================================================
# ConversationService Tests (Task 3)
# ============================================================================


class TestConversationServiceInit:
    """Tests for ConversationService initialization."""

    def test_conversation_service_importable(self) -> None:
        """ConversationService should be importable."""
        from src.memory.conversation import ConversationService

        assert ConversationService is not None

    def test_conversation_service_has_required_methods(self) -> None:
        """ConversationService should have required interface methods."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        assert hasattr(service, "extract_episode")
        assert hasattr(service, "get_recent_episodes")
        assert hasattr(service, "get_open_threads")
        assert hasattr(service, "get_episode")

    def test_conversation_service_stores_clients(self) -> None:
        """ConversationService should store injected clients."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        assert service.db is mock_db
        assert service.llm is mock_llm


class TestFormatMessages:
    """Tests for message formatting helper."""

    def test_format_messages_creates_readable_output(self) -> None:
        """_format_messages should create readable conversation text."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        messages = [
            {"role": "user", "content": "Hello ARIA"},
            {"role": "assistant", "content": "Hello! How can I help?"},
            {"role": "user", "content": "Tell me about Acme Corp"},
        ]

        formatted = service._format_messages(messages)

        assert "User: Hello ARIA" in formatted
        assert "Assistant: Hello! How can I help?" in formatted
        assert "User: Tell me about Acme Corp" in formatted

    def test_format_messages_handles_empty_list(self) -> None:
        """_format_messages should handle empty message list."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        formatted = service._format_messages([])

        assert formatted == ""


# ============================================================================
# ExtractEpisode Tests (Task 4)
# ============================================================================


class TestExtractEpisode:
    """Tests for episode extraction from conversations."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock Supabase client."""
        mock = MagicMock()
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "ep-generated-123",
                    "user_id": "user-456",
                    "conversation_id": "conv-789",
                    "summary": "Test summary",
                    "key_topics": ["topic1"],
                    "entities_discussed": [],
                    "user_state": {},
                    "outcomes": [],
                    "open_threads": [],
                    "message_count": 3,
                    "duration_minutes": 5,
                    "started_at": "2026-02-02T10:00:00+00:00",
                    "ended_at": "2026-02-02T10:05:00+00:00",
                    "current_salience": 1.0,
                    "last_accessed_at": "2026-02-02T10:05:00+00:00",
                    "access_count": 0,
                }
            ]
        )
        return mock

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create mock LLM client."""
        mock = MagicMock()
        # First call returns summary
        # Second call returns extraction JSON
        mock.generate_response = AsyncMock(
            side_effect=[
                "Discussed project timeline and resource allocation. Agreed to weekly check-ins.",
                json.dumps(
                    {
                        "key_topics": ["project timeline", "resources", "check-ins"],
                        "user_state": {
                            "mood": "focused",
                            "confidence": "high",
                            "focus": "planning",
                        },
                        "outcomes": [
                            {"type": "decision", "content": "Weekly check-ins starting Monday"}
                        ],
                        "open_threads": [
                            {
                                "topic": "budget",
                                "status": "pending",
                                "context": "Awaiting finance approval",
                            }
                        ],
                    }
                ),
            ]
        )
        return mock

    @pytest.fixture
    def sample_messages(self) -> list[dict[str, Any]]:
        """Create sample conversation messages."""
        now = datetime.now(UTC)
        return [
            {
                "role": "user",
                "content": "Let's discuss the project timeline",
                "created_at": now - timedelta(minutes=5),
            },
            {
                "role": "assistant",
                "content": "Sure! What's the target deadline?",
                "created_at": now - timedelta(minutes=4),
            },
            {"role": "user", "content": "End of Q1, we need weekly check-ins", "created_at": now},
        ]

    @pytest.mark.asyncio
    async def test_extract_episode_calls_llm_for_summary(
        self, mock_db: MagicMock, mock_llm: MagicMock, sample_messages: list[dict[str, Any]]
    ) -> None:
        """extract_episode should call LLM to generate summary."""
        from src.memory.conversation import ConversationService

        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        await service.extract_episode(
            user_id="user-456",
            conversation_id="conv-789",
            messages=sample_messages,
        )

        # Should have called generate_response twice (summary + extraction)
        assert mock_llm.generate_response.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_episode_stores_in_database(
        self, mock_db: MagicMock, mock_llm: MagicMock, sample_messages: list[dict[str, Any]]
    ) -> None:
        """extract_episode should store episode in database."""
        from src.memory.conversation import ConversationService

        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        await service.extract_episode(
            user_id="user-456",
            conversation_id="conv-789",
            messages=sample_messages,
        )

        mock_db.table.assert_called_with("conversation_episodes")
        mock_db.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_episode_returns_episode_object(
        self, mock_db: MagicMock, mock_llm: MagicMock, sample_messages: list[dict[str, Any]]
    ) -> None:
        """extract_episode should return ConversationEpisode."""
        from src.memory.conversation import ConversationEpisode, ConversationService

        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        result = await service.extract_episode(
            user_id="user-456",
            conversation_id="conv-789",
            messages=sample_messages,
        )

        assert isinstance(result, ConversationEpisode)
        assert result.user_id == "user-456"
        assert result.conversation_id == "conv-789"

    @pytest.mark.asyncio
    async def test_extract_episode_calculates_duration(
        self, mock_db: MagicMock, mock_llm: MagicMock, sample_messages: list[dict[str, Any]]
    ) -> None:
        """extract_episode should calculate duration from timestamps."""
        from src.memory.conversation import ConversationService

        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        await service.extract_episode(
            user_id="user-456",
            conversation_id="conv-789",
            messages=sample_messages,
        )

        # Verify insert was called with duration
        insert_call = mock_db.table.return_value.insert.call_args
        insert_data = insert_call[0][0]
        assert "duration_minutes" in insert_data
        assert insert_data["message_count"] == 3

    @pytest.mark.asyncio
    async def test_extract_episode_handles_malformed_json(
        self, mock_db: MagicMock, sample_messages: list[dict[str, Any]]
    ) -> None:
        """extract_episode should handle malformed LLM JSON gracefully."""
        from src.memory.conversation import ConversationEpisode, ConversationService

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            side_effect=[
                "Valid summary here.",
                "This is not valid JSON at all",  # Malformed JSON
            ]
        )

        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        # Should not raise, should use defaults
        result = await service.extract_episode(
            user_id="user-456",
            conversation_id="conv-789",
            messages=sample_messages,
        )

        assert isinstance(result, ConversationEpisode)

        # Verify the insert was called with empty defaults for extracted fields
        insert_call = mock_db.table.return_value.insert.call_args
        insert_data = insert_call[0][0]
        assert insert_data["key_topics"] == []
        assert insert_data["user_state"] == {}
        assert insert_data["outcomes"] == []
        assert insert_data["open_threads"] == []


# ============================================================================
# GetRecentEpisodes Tests (Task 5)
# ============================================================================


class TestGetRecentEpisodes:
    """Tests for retrieving recent conversation episodes."""

    @pytest.fixture
    def mock_db_with_episodes(self) -> MagicMock:
        """Create mock DB with episode data."""
        mock = MagicMock()
        now = datetime.now(UTC)

        episodes_data = [
            {
                "id": "ep-1",
                "user_id": "user-456",
                "conversation_id": "conv-1",
                "summary": "Discussed Q1 targets",
                "key_topics": ["sales", "Q1"],
                "entities_discussed": ["Acme Corp"],
                "user_state": {"mood": "focused"},
                "outcomes": [],
                "open_threads": [],
                "message_count": 10,
                "duration_minutes": 15,
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "ended_at": (now - timedelta(hours=1, minutes=45)).isoformat(),
                "current_salience": 0.9,
                "last_accessed_at": now.isoformat(),
                "access_count": 2,
            },
            {
                "id": "ep-2",
                "user_id": "user-456",
                "conversation_id": "conv-2",
                "summary": "Weekly sync",
                "key_topics": ["sync", "updates"],
                "entities_discussed": [],
                "user_state": {},
                "outcomes": [{"type": "action", "content": "Review proposal"}],
                "open_threads": [
                    {"topic": "budget", "status": "pending", "context": "Need CFO sign-off"}
                ],
                "message_count": 5,
                "duration_minutes": 8,
                "started_at": (now - timedelta(days=1)).isoformat(),
                "ended_at": (now - timedelta(days=1) + timedelta(minutes=8)).isoformat(),
                "current_salience": 0.7,
                "last_accessed_at": (now - timedelta(days=1)).isoformat(),
                "access_count": 0,
            },
        ]

        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=episodes_data
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_recent_episodes_returns_list(self, mock_db_with_episodes: MagicMock) -> None:
        """get_recent_episodes should return list of episodes."""
        from src.memory.conversation import ConversationEpisode, ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_episodes, llm_client=mock_llm)

        episodes = await service.get_recent_episodes(user_id="user-456", limit=5)

        assert isinstance(episodes, list)
        assert len(episodes) == 2
        assert all(isinstance(ep, ConversationEpisode) for ep in episodes)

    @pytest.mark.asyncio
    async def test_get_recent_episodes_filters_by_salience(
        self, mock_db_with_episodes: MagicMock
    ) -> None:
        """get_recent_episodes should filter by minimum salience."""
        from src.memory.conversation import ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_episodes, llm_client=mock_llm)

        await service.get_recent_episodes(user_id="user-456", min_salience=0.5)

        # Verify gte was called with salience threshold
        mock_db_with_episodes.table.return_value.select.return_value.eq.return_value.gte.assert_called_with(
            "current_salience", 0.5
        )

    @pytest.mark.asyncio
    async def test_get_recent_episodes_orders_by_ended_at(
        self, mock_db_with_episodes: MagicMock
    ) -> None:
        """get_recent_episodes should order by ended_at descending."""
        from src.memory.conversation import ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_episodes, llm_client=mock_llm)

        await service.get_recent_episodes(user_id="user-456")

        mock_db_with_episodes.table.return_value.select.return_value.eq.return_value.gte.return_value.order.assert_called_with(
            "ended_at", desc=True
        )


# ============================================================================
# GetOpenThreads Tests (Task 5)
# ============================================================================


class TestGetOpenThreads:
    """Tests for retrieving open threads across conversations."""

    @pytest.fixture
    def mock_db_with_threads(self) -> MagicMock:
        """Create mock DB with episodes containing open threads."""
        mock = MagicMock()
        now = datetime.now(UTC)

        episodes_with_threads = [
            {
                "conversation_id": "conv-1",
                "ended_at": (now - timedelta(hours=1)).isoformat(),
                "open_threads": [
                    {
                        "topic": "pricing",
                        "status": "awaiting_response",
                        "context": "Client reviewing",
                    },
                ],
            },
            {
                "conversation_id": "conv-2",
                "ended_at": (now - timedelta(days=1)).isoformat(),
                "open_threads": [
                    {"topic": "contract", "status": "pending", "context": "Legal review"},
                    {"topic": "timeline", "status": "blocked", "context": "Waiting on resources"},
                ],
            },
        ]

        mock.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=episodes_with_threads
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_open_threads_returns_list(self, mock_db_with_threads: MagicMock) -> None:
        """get_open_threads should return list of thread dicts."""
        from src.memory.conversation import ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_threads, llm_client=mock_llm)

        threads = await service.get_open_threads(user_id="user-456")

        assert isinstance(threads, list)
        assert len(threads) == 3  # Total threads from both episodes

    @pytest.mark.asyncio
    async def test_get_open_threads_includes_conversation_context(
        self, mock_db_with_threads: MagicMock
    ) -> None:
        """get_open_threads should include source conversation info."""
        from src.memory.conversation import ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_threads, llm_client=mock_llm)

        threads = await service.get_open_threads(user_id="user-456")

        for thread in threads:
            assert "from_conversation" in thread
            assert "conversation_ended" in thread

    @pytest.mark.asyncio
    async def test_get_open_threads_respects_limit(self, mock_db_with_threads: MagicMock) -> None:
        """get_open_threads should respect limit parameter."""
        from src.memory.conversation import ConversationService

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db_with_threads, llm_client=mock_llm)

        threads = await service.get_open_threads(user_id="user-456", limit=2)

        assert len(threads) <= 2


# ============================================================================
# GetEpisode Tests (Task 5)
# ============================================================================


class TestGetEpisode:
    """Tests for retrieving a specific episode."""

    @pytest.mark.asyncio
    async def test_get_episode_returns_episode(self) -> None:
        """get_episode should return specific episode by ID."""
        from src.memory.conversation import ConversationEpisode, ConversationService

        mock_db = MagicMock()
        now = datetime.now(UTC)

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "ep-123",
                "user_id": "user-456",
                "conversation_id": "conv-789",
                "summary": "Test episode",
                "key_topics": [],
                "entities_discussed": [],
                "user_state": {},
                "outcomes": [],
                "open_threads": [],
                "message_count": 5,
                "duration_minutes": 10,
                "started_at": now.isoformat(),
                "ended_at": now.isoformat(),
                "current_salience": 1.0,
                "last_accessed_at": now.isoformat(),
                "access_count": 0,
            }
        )

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        episode = await service.get_episode(user_id="user-456", episode_id="ep-123")

        assert episode is not None
        assert isinstance(episode, ConversationEpisode)
        assert episode.id == "ep-123"

    @pytest.mark.asyncio
    async def test_get_episode_returns_none_when_not_found(self) -> None:
        """get_episode should return None when episode doesn't exist."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        mock_llm = MagicMock()
        service = ConversationService(db_client=mock_db, llm_client=mock_llm)

        episode = await service.get_episode(user_id="user-456", episode_id="nonexistent")

        assert episode is None


# ============================================================================
# Entity Extraction Tests (Task 6)
# ============================================================================


class TestEntityExtraction:
    """Tests for Graphiti entity extraction integration."""

    @pytest.mark.asyncio
    async def test_extract_entities_uses_graphiti(self) -> None:
        """_extract_entities should use Graphiti for entity extraction."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()

        # Create mock nodes with proper name attributes
        source1 = MagicMock()
        source1.name = "John Doe"
        result1 = MagicMock()
        result1.source_node = source1

        source2 = MagicMock()
        source2.name = "Acme Corp"
        result2 = MagicMock()
        result2.source_node = source2

        mock_graphiti = MagicMock()
        mock_graphiti.search = AsyncMock(return_value=[result1, result2])

        service = ConversationService(
            db_client=mock_db,
            llm_client=mock_llm,
            graphiti_client=mock_graphiti,
        )

        messages = [
            {"role": "user", "content": "I spoke with John Doe from Acme Corp"},
        ]

        entities = await service._extract_entities(messages)

        assert isinstance(entities, list)
        assert "John Doe" in entities
        assert "Acme Corp" in entities

    @pytest.mark.asyncio
    async def test_extract_entities_handles_no_graphiti(self) -> None:
        """_extract_entities should work without Graphiti client."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()

        service = ConversationService(
            db_client=mock_db,
            llm_client=mock_llm,
            graphiti_client=None,  # No Graphiti
        )

        messages = [{"role": "user", "content": "Hello"}]
        entities = await service._extract_entities(messages)

        assert entities == []

    @pytest.mark.asyncio
    async def test_extract_entities_extracts_unique_names(self) -> None:
        """_extract_entities should extract unique entity names from source and target nodes."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()

        # Create mock nodes with proper name attributes (MagicMock auto-generates .name)
        source1 = MagicMock()
        source1.name = "John Doe"
        target1 = MagicMock()
        target1.name = "Acme Corp"

        source2 = MagicMock()
        source2.name = "John Doe"  # Duplicate
        target2 = MagicMock()
        target2.name = "Widget Inc"

        result1 = MagicMock()
        result1.source_node = source1
        result1.target_node = target1

        result2 = MagicMock()
        result2.source_node = source2
        result2.target_node = target2

        mock_graphiti = MagicMock()
        mock_graphiti.search = AsyncMock(return_value=[result1, result2])

        service = ConversationService(
            db_client=mock_db,
            llm_client=mock_llm,
            graphiti_client=mock_graphiti,
        )

        messages = [
            {"role": "user", "content": "John Doe from Acme Corp called about Widget Inc"},
        ]

        entities = await service._extract_entities(messages)

        assert isinstance(entities, list)
        assert len(entities) == 3  # John Doe, Acme Corp, Widget Inc (no duplicates)
        assert "John Doe" in entities
        assert "Acme Corp" in entities
        assert "Widget Inc" in entities

    @pytest.mark.asyncio
    async def test_extract_entities_handles_graphiti_error(self) -> None:
        """_extract_entities should handle Graphiti errors gracefully."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()

        mock_graphiti = MagicMock()
        mock_graphiti.search = AsyncMock(side_effect=Exception("Graphiti unavailable"))

        service = ConversationService(
            db_client=mock_db,
            llm_client=mock_llm,
            graphiti_client=mock_graphiti,
        )

        messages = [{"role": "user", "content": "Test message"}]
        entities = await service._extract_entities(messages)

        # Should return empty list on error, not raise
        assert entities == []

    @pytest.mark.asyncio
    async def test_extract_entities_combines_message_content(self) -> None:
        """_extract_entities should combine all message content for search."""
        from src.memory.conversation import ConversationService

        mock_db = MagicMock()
        mock_llm = MagicMock()

        mock_graphiti = MagicMock()
        mock_graphiti.search = AsyncMock(return_value=[])

        service = ConversationService(
            db_client=mock_db,
            llm_client=mock_llm,
            graphiti_client=mock_graphiti,
        )

        messages = [
            {"role": "user", "content": "Hello John"},
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "Call Acme Corp"},
        ]

        await service._extract_entities(messages)

        # Verify search was called with combined text
        mock_graphiti.search.assert_called_once()
        search_arg = mock_graphiti.search.call_args[0][0]
        assert "Hello John" in search_arg
        assert "How can I help?" in search_arg
        assert "Call Acme Corp" in search_arg
