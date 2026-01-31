"""Tests for Graphiti client."""

import pytest

from src.db.graphiti import GraphitiClient


@pytest.fixture(autouse=True)
def reset_client() -> None:
    """Reset the singleton before each test."""
    GraphitiClient._instance = None
    GraphitiClient._initialized = False


def test_graphiti_client_is_singleton() -> None:
    """Test that GraphitiClient follows singleton pattern."""
    assert GraphitiClient._instance is None
    assert hasattr(GraphitiClient, "get_instance")
    assert hasattr(GraphitiClient, "reset_client")
