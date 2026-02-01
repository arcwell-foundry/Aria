"""Tests for episodic memory module."""

import json
from datetime import UTC, datetime

from src.memory.episodic import Episode


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
