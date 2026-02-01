"""Tests for episodic memory module."""

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
