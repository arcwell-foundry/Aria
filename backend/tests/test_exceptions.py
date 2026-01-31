"""Tests for custom exceptions."""

from src.core.exceptions import GraphitiConnectionError


def test_graphiti_connection_error_attributes() -> None:
    """Test GraphitiConnectionError has correct attributes."""
    error = GraphitiConnectionError("Connection refused")
    assert error.message == "Failed to connect to Neo4j: Connection refused"
    assert error.code == "GRAPHITI_CONNECTION_ERROR"
    assert error.status_code == 503
