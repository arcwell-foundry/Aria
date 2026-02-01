"""Tests for custom exceptions."""

from src.core.exceptions import GraphitiConnectionError, MemoryError


def test_graphiti_connection_error_attributes() -> None:
    """Test GraphitiConnectionError has correct attributes."""
    error = GraphitiConnectionError("Connection refused")
    assert error.message == "Failed to connect to Neo4j: Connection refused"
    assert error.code == "GRAPHITI_CONNECTION_ERROR"
    assert error.status_code == 503


def test_memory_error_attributes() -> None:
    """Test MemoryError has correct attributes."""
    error = MemoryError("Context window exceeded")
    assert error.message == "Memory operation failed: Context window exceeded"
    assert error.code == "MEMORY_ERROR"
    assert error.status_code == 400
