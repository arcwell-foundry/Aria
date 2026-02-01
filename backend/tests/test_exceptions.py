"""Tests for custom exceptions."""

from src.core.exceptions import GraphitiConnectionError, WorkingMemoryError


def test_graphiti_connection_error_attributes() -> None:
    """Test GraphitiConnectionError has correct attributes."""
    error = GraphitiConnectionError("Connection refused")
    assert error.message == "Failed to connect to Neo4j: Connection refused"
    assert error.code == "GRAPHITI_CONNECTION_ERROR"
    assert error.status_code == 503


def test_working_memory_error_attributes() -> None:
    """Test WorkingMemoryError has correct attributes."""
    error = WorkingMemoryError("Context window exceeded")
    assert error.message == "Memory operation failed: Context window exceeded"
    assert error.code == "WORKING_MEMORY_ERROR"
    assert error.status_code == 400


def test_episodic_memory_error_attributes() -> None:
    """Test EpisodicMemoryError has correct attributes."""
    from src.core.exceptions import EpisodicMemoryError

    error = EpisodicMemoryError("Failed to store episode")
    assert error.message == "Episodic memory operation failed: Failed to store episode"
    assert error.code == "EPISODIC_MEMORY_ERROR"
    assert error.status_code == 500


def test_episode_not_found_error_attributes() -> None:
    """Test EpisodeNotFoundError has correct attributes."""
    from src.core.exceptions import EpisodeNotFoundError

    error = EpisodeNotFoundError("ep-123")
    assert error.message == "Episode with ID 'ep-123' not found"
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404
