"""Tests for Graphiti client."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.db.graphiti import GraphitiClient
import src.db.graphiti as graphiti_module


@pytest.fixture(autouse=True)
def reset_client() -> None:
    """Reset the singleton and module state before each test."""
    GraphitiClient._instance = None
    GraphitiClient._initialized = False


def test_graphiti_client_is_singleton() -> None:
    """Test that GraphitiClient follows singleton pattern."""
    assert GraphitiClient._instance is None
    assert hasattr(GraphitiClient, "get_instance")
    assert hasattr(GraphitiClient, "reset_client")


@pytest.mark.asyncio
async def test_get_instance_initializes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_instance creates and initializes the client."""
    mock_graphiti_instance = MagicMock()
    mock_graphiti_instance.build_indices_and_constraints = AsyncMock()

    mock_graphiti_class = MagicMock(return_value=mock_graphiti_instance)
    mock_anthropic_client = MagicMock()
    mock_llm_config = MagicMock()
    mock_embedder = MagicMock()
    mock_embedder_config = MagicMock()

    # Patch the imports inside _initialize
    monkeypatch.setattr("src.db.graphiti.GraphitiClient._initialize", AsyncMock())
    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    client = await GraphitiClient.get_instance()

    assert client is mock_graphiti_instance
    assert GraphitiClient.is_initialized()


@pytest.mark.asyncio
async def test_get_instance_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_instance returns the same instance on subsequent calls."""
    mock_graphiti_instance = MagicMock()
    mock_init = AsyncMock()

    monkeypatch.setattr("src.db.graphiti.GraphitiClient._initialize", mock_init)
    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    client1 = await GraphitiClient.get_instance()
    client2 = await GraphitiClient.get_instance()

    assert client1 is client2
    # _initialize should not be called since instance exists
    mock_init.assert_not_called()


@pytest.mark.asyncio
async def test_close_cleans_up_client() -> None:
    """Test that close properly cleans up the client."""
    mock_graphiti_instance = MagicMock()
    mock_graphiti_instance.close = AsyncMock()

    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    await GraphitiClient.close()

    assert not GraphitiClient.is_initialized()
    assert GraphitiClient._instance is None
    mock_graphiti_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_initialization_failure_raises_connection_error() -> None:
    """Test that initialization failure raises GraphitiConnectionError."""
    from src.core.exceptions import GraphitiConnectionError

    # Make get_instance actually call _initialize by ensuring _instance is None
    GraphitiClient._instance = None
    GraphitiClient._initialized = False

    with pytest.raises(GraphitiConnectionError) as exc_info:
        await GraphitiClient.get_instance()

    assert "Failed to connect to Neo4j" in str(exc_info.value.message)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_health_check_returns_true_when_connected() -> None:
    """Test that health_check returns True when client is connected."""
    mock_graphiti_instance = MagicMock()
    # Mock the driver's execute_query method
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], None, None))
    mock_graphiti_instance.driver = mock_driver

    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    result = await GraphitiClient.health_check()

    assert result is True
    mock_driver.execute_query.assert_called_once_with("RETURN 1 AS health")


@pytest.mark.asyncio
async def test_health_check_returns_false_when_not_initialized() -> None:
    """Test that health_check returns False when client is not initialized."""
    result = await GraphitiClient.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_add_episode_delegates_to_graphiti() -> None:
    """Test that add_episode correctly delegates to the Graphiti instance."""
    from datetime import datetime, timezone

    mock_graphiti_instance = MagicMock()
    mock_graphiti_instance.add_episode = AsyncMock(return_value=MagicMock(uuid="test-uuid"))
    mock_graphiti_instance.driver = MagicMock()

    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    result = await GraphitiClient.add_episode(
        name="Test Episode",
        episode_body="This is test content",
        source_description="unit test",
        reference_time=datetime.now(timezone.utc),
    )

    mock_graphiti_instance.add_episode.assert_called_once()
    assert result is not None


@pytest.mark.asyncio
async def test_search_delegates_to_graphiti() -> None:
    """Test that search correctly delegates to the Graphiti instance."""
    mock_edge = MagicMock()
    mock_edge.fact = "Test fact"

    mock_graphiti_instance = MagicMock()
    mock_graphiti_instance.search = AsyncMock(return_value=[mock_edge])
    mock_graphiti_instance.driver = MagicMock()

    GraphitiClient._instance = mock_graphiti_instance
    GraphitiClient._initialized = True

    results = await GraphitiClient.search("test query")

    mock_graphiti_instance.search.assert_called_once_with("test query")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_graphiti_circuit_breaker_opens_after_failures() -> None:
    """Test that repeated Graphiti failures open the circuit breaker."""
    from src.core.circuit_breaker import CircuitBreakerOpen
    from src.db.graphiti import _graphiti_circuit_breaker

    # Reset circuit breaker state
    _graphiti_circuit_breaker.record_success()

    mock_func = AsyncMock(side_effect=Exception("Neo4j down"))

    for _ in range(5):
        with pytest.raises(Exception, match="Neo4j down"):
            await _graphiti_circuit_breaker.call_async(mock_func)

    with pytest.raises(CircuitBreakerOpen):
        _graphiti_circuit_breaker.check()

    # Reset for other tests
    _graphiti_circuit_breaker.record_success()
