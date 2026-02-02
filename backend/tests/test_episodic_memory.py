"""Tests for episodic memory module."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.episodic import Episode, EpisodicMemory


def test_episode_initialization() -> None:
    """Test Episode initializes with required fields."""
    now = datetime.now(UTC)
    episode = Episode(
        id="ep-123",
        user_id="user-456",
        event_type="meeting",
        content="Met with John to discuss Q1 goals",
        participants=["John Doe", "Jane Smith"],
        occurred_at=now,
        recorded_at=now,
        context={"location": "Office", "project": "Q1 Planning"},
    )

    assert episode.id == "ep-123"
    assert episode.user_id == "user-456"
    assert episode.event_type == "meeting"
    assert episode.content == "Met with John to discuss Q1 goals"
    assert episode.participants == ["John Doe", "Jane Smith"]
    assert episode.occurred_at == now
    assert episode.recorded_at == now
    assert episode.context["location"] == "Office"


def test_episode_with_minimal_fields() -> None:
    """Test Episode works with minimal required fields."""
    now = datetime.now(UTC)
    episode = Episode(
        id="ep-124",
        user_id="user-456",
        event_type="note",
        content="Quick note about something",
        participants=[],
        occurred_at=now,
        recorded_at=now,
        context={},
    )

    assert episode.id == "ep-124"
    assert episode.participants == []
    assert episode.context == {}


def test_episode_to_dict_serializes_correctly() -> None:
    """Test Episode.to_dict returns a serializable dictionary."""
    now = datetime.now(UTC)
    episode = Episode(
        id="ep-123",
        user_id="user-456",
        event_type="meeting",
        content="Team standup",
        participants=["Alice", "Bob"],
        occurred_at=now,
        recorded_at=now,
        context={"room": "Conference A"},
    )

    data = episode.to_dict()

    assert data["id"] == "ep-123"
    assert data["user_id"] == "user-456"
    assert data["event_type"] == "meeting"
    assert data["content"] == "Team standup"
    assert data["participants"] == ["Alice", "Bob"]
    assert data["occurred_at"] == now.isoformat()
    assert data["recorded_at"] == now.isoformat()
    assert data["context"] == {"room": "Conference A"}

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_episode_from_dict_deserializes_correctly() -> None:
    """Test Episode.from_dict creates Episode from dictionary."""
    now = datetime.now(UTC)
    data = {
        "id": "ep-123",
        "user_id": "user-456",
        "event_type": "call",
        "content": "Sales call with prospect",
        "participants": ["Prospect"],
        "occurred_at": now.isoformat(),
        "recorded_at": now.isoformat(),
        "context": {"deal_value": 50000},
    }

    episode = Episode.from_dict(data)

    assert episode.id == "ep-123"
    assert episode.user_id == "user-456"
    assert episode.event_type == "call"
    assert episode.content == "Sales call with prospect"
    assert episode.participants == ["Prospect"]
    assert episode.occurred_at == now
    assert episode.recorded_at == now
    assert episode.context["deal_value"] == 50000


def test_episodic_memory_has_required_methods() -> None:
    """Test EpisodicMemory class has required interface methods."""
    from src.memory.episodic import EpisodicMemory

    memory = EpisodicMemory()

    # Check required async methods exist
    assert hasattr(memory, "store_episode")
    assert hasattr(memory, "get_episode")
    assert hasattr(memory, "query_by_time_range")
    assert hasattr(memory, "query_by_event_type")
    assert hasattr(memory, "query_by_participant")
    assert hasattr(memory, "semantic_search")
    assert hasattr(memory, "delete_episode")


@pytest.fixture
def mock_graphiti_client() -> MagicMock:
    """Create a mock GraphitiClient for testing."""
    mock_instance = MagicMock()
    mock_instance.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-ep-123"))
    return mock_instance


@pytest.mark.asyncio
async def test_store_episode_stores_in_graphiti(mock_graphiti_client: MagicMock) -> None:
    """Test that store_episode stores episode in Graphiti."""
    now = datetime.now(UTC)
    episode = Episode(
        id="ep-123",
        user_id="user-456",
        event_type="meeting",
        content="Team standup discussion",
        participants=["Alice", "Bob"],
        occurred_at=now,
        recorded_at=now,
        context={"room": "Conference A"},
    )

    memory = EpisodicMemory()

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_graphiti_client

        result = await memory.store_episode(episode)

        assert result == "ep-123"
        mock_graphiti_client.add_episode.assert_called_once()


@pytest.mark.asyncio
async def test_store_episode_generates_id_if_missing() -> None:
    """Test that store_episode generates ID if not provided."""
    now = datetime.now(UTC)
    episode = Episode(
        id="",  # Empty ID
        user_id="user-456",
        event_type="note",
        content="Quick note",
        participants=[],
        occurred_at=now,
        recorded_at=now,
        context={},
    )

    memory = EpisodicMemory()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="new-uuid"))

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_client

        result = await memory.store_episode(episode)

        # Should have generated a UUID
        assert result != ""
        assert len(result) > 0


@pytest.mark.asyncio
async def test_query_by_time_range_returns_episodes() -> None:
    """Test query_by_time_range returns episodes in range."""
    now = datetime.now(UTC)
    start = now - timedelta(days=7)
    end = now

    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Event Type: meeting\nContent: First meeting"
    mock_edge.created_at = now - timedelta(days=1)

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.query_by_time_range("user-456", start, end, limit=10)
        assert isinstance(results, list)
        mock_client.search.assert_called_once()


@pytest.mark.asyncio
async def test_query_by_event_type_filters_correctly() -> None:
    """Test query_by_event_type returns only matching event types."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Event Type: meeting\nContent: Team sync"
    mock_edge.created_at = datetime.now(UTC)

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.query_by_event_type("user-456", "meeting", limit=10)
        assert isinstance(results, list)
        call_args = mock_client.search.call_args
        assert "meeting" in call_args[0][0]


@pytest.mark.asyncio
async def test_query_by_participant_searches_correctly() -> None:
    """Test query_by_participant searches for participant name."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Event Type: meeting\nParticipants: John Doe, Jane\nContent: Discussed project"
    mock_edge.created_at = datetime.now(UTC)

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.query_by_participant("user-456", "John Doe", limit=10)
        assert isinstance(results, list)
        call_args = mock_client.search.call_args
        assert "John Doe" in call_args[0][0]


@pytest.mark.asyncio
async def test_semantic_search_queries_graphiti() -> None:
    """Test semantic_search uses Graphiti's semantic search."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Event Type: meeting\nContent: Discussed Q1 revenue targets"
    mock_edge.created_at = datetime.now(UTC)

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.semantic_search("user-456", "revenue goals discussion", limit=5)
        assert isinstance(results, list)
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert "revenue goals discussion" in call_args[0][0]


@pytest.mark.asyncio
async def test_delete_episode_removes_from_graphiti() -> None:
    """Test delete_episode removes episode from Graphiti."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        await memory.delete_episode(user_id="user-456", episode_id="ep-123")
        mock_driver.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_episode_retrieves_by_id() -> None:
    """Test get_episode retrieves specific episode by ID."""
    now = datetime.now(UTC)
    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = "Event Type: meeting\nContent: Team sync"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        episode = await memory.get_episode(user_id="user-456", episode_id="ep-123")
        assert episode is not None
        mock_driver.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_episode_raises_not_found() -> None:
    """Test get_episode raises EpisodeNotFoundError when not found."""
    from src.core.exceptions import EpisodeNotFoundError

    memory = EpisodicMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        with pytest.raises(EpisodeNotFoundError):
            await memory.get_episode(user_id="user-456", episode_id="nonexistent")


@pytest.mark.asyncio
async def test_store_episode_logs_audit_entry() -> None:
    """Test that store_episode logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType
    from src.memory.episodic import Episode, EpisodicMemory

    now = datetime.now(UTC)
    episode = Episode(
        id="ep-audit-test",
        user_id="user-456",
        event_type="meeting",
        content="Met with client",
        participants=["John"],
        occurred_at=now,
        recorded_at=now,
        context={},
    )

    memory = EpisodicMemory()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-uuid"))

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.episodic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-ep-123"

            await memory.store_episode(episode)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == "user-456"
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.EPISODIC
            assert call_kwargs["suppress_errors"] is True


@pytest.mark.asyncio
async def test_query_by_time_range_respects_as_of_for_recorded_at() -> None:
    """Test query_by_time_range filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    # Episode occurred in the past but was recorded "today"
    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Q1 planning\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-123"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 7 days ago - should NOT include episode recorded today
        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_time_range(
            user_id="user-456",
            start=past - timedelta(days=5),
            end=past + timedelta(days=5),
            as_of=as_of_date,
        )

        # Episode should be filtered out (recorded after as_of)
        assert len(results) == 0


@pytest.mark.asyncio
async def test_query_by_event_type_respects_as_of() -> None:
    """Test query_by_event_type filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Team sync\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-456"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 7 days ago - should NOT include episode recorded today
        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_event_type(
            user_id="user-456",
            event_type="meeting",
            as_of=as_of_date,
        )

        assert len(results) == 0


@pytest.mark.asyncio
async def test_query_by_participant_respects_as_of() -> None:
    """Test query_by_participant filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Discussion with John\nParticipants: John Smith\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-789"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_participant(
            user_id="user-456",
            participant="John",
            as_of=as_of_date,
        )

        assert len(results) == 0
