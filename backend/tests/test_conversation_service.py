"""Tests for conversation episode service."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock


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
