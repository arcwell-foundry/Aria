"""Tests for semantic memory module."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.semantic import FactSource, SemanticFact, SemanticMemory


@pytest.fixture
def mock_graphiti_client() -> MagicMock:
    """Create a mock GraphitiClient for testing."""
    mock_instance = MagicMock()
    mock_instance.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-fact-123"))
    mock_instance.search = AsyncMock(return_value=[])
    return mock_instance


def test_fact_source_enum_values() -> None:
    """Test FactSource enum has expected values."""
    assert FactSource.USER_STATED.value == "user_stated"
    assert FactSource.EXTRACTED.value == "extracted"
    assert FactSource.INFERRED.value == "inferred"
    assert FactSource.CRM_IMPORT.value == "crm_import"
    assert FactSource.WEB_RESEARCH.value == "web_research"


def test_semantic_fact_initialization() -> None:
    """Test SemanticFact initializes with required fields."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )

    assert fact.id == "fact-123"
    assert fact.user_id == "user-456"
    assert fact.subject == "John Doe"
    assert fact.predicate == "works_at"
    assert fact.object == "Acme Corp"
    assert fact.confidence == 0.95
    assert fact.source == FactSource.USER_STATED
    assert fact.valid_from == now
    assert fact.valid_to is None
    assert fact.invalidated_at is None
    assert fact.invalidation_reason is None


def test_semantic_fact_with_all_fields() -> None:
    """Test SemanticFact works with all optional fields."""
    now = datetime.now(UTC)
    later = datetime(2026, 12, 31, tzinfo=UTC)
    fact = SemanticFact(
        id="fact-124",
        user_id="user-456",
        subject="Jane Smith",
        predicate="title",
        object="VP of Sales",
        confidence=0.80,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
        valid_to=later,
        invalidated_at=None,
        invalidation_reason=None,
    )

    assert fact.id == "fact-124"
    assert fact.valid_to == later


def test_semantic_fact_to_dict_serializes_correctly() -> None:
    """Test SemanticFact.to_dict returns a serializable dictionary."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )

    data = fact.to_dict()

    assert data["id"] == "fact-123"
    assert data["user_id"] == "user-456"
    assert data["subject"] == "John Doe"
    assert data["predicate"] == "works_at"
    assert data["object"] == "Acme Corp"
    assert data["confidence"] == 0.95
    assert data["source"] == "user_stated"
    assert data["valid_from"] == now.isoformat()
    assert data["valid_to"] is None
    assert data["invalidated_at"] is None
    assert data["invalidation_reason"] is None

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_semantic_fact_from_dict_deserializes_correctly() -> None:
    """Test SemanticFact.from_dict creates SemanticFact from dictionary."""
    now = datetime.now(UTC)
    data = {
        "id": "fact-123",
        "user_id": "user-456",
        "subject": "Jane Smith",
        "predicate": "title",
        "object": "CEO",
        "confidence": 0.90,
        "source": "crm_import",
        "valid_from": now.isoformat(),
        "valid_to": None,
        "invalidated_at": None,
        "invalidation_reason": None,
    }

    fact = SemanticFact.from_dict(data)

    assert fact.id == "fact-123"
    assert fact.user_id == "user-456"
    assert fact.subject == "Jane Smith"
    assert fact.predicate == "title"
    assert fact.object == "CEO"
    assert fact.confidence == 0.90
    assert fact.source == FactSource.CRM_IMPORT
    assert fact.valid_from == now
    assert fact.valid_to is None


def test_semantic_fact_is_valid_returns_true_for_active_fact() -> None:
    """Test is_valid returns True for facts within validity window."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        valid_to=now + timedelta(days=30),
    )

    assert fact.is_valid() is True
    assert fact.is_valid(as_of=now) is True


def test_semantic_fact_is_valid_returns_false_for_invalidated() -> None:
    """Test is_valid returns False for invalidated facts."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        invalidated_at=now - timedelta(days=1),
        invalidation_reason="superseded",
    )

    assert fact.is_valid() is False


def test_semantic_fact_is_valid_returns_false_for_expired() -> None:
    """Test is_valid returns False for facts past valid_to."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=60),
        valid_to=now - timedelta(days=30),
    )

    assert fact.is_valid() is False


def test_semantic_fact_is_valid_with_as_of_date() -> None:
    """Test is_valid checks against specific point in time."""
    now = datetime.now(UTC)
    past = now - timedelta(days=15)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        valid_to=now - timedelta(days=10),
    )

    # Valid at 15 days ago (within window)
    assert fact.is_valid(as_of=past) is True
    # Invalid now (past valid_to)
    assert fact.is_valid() is False


def test_semantic_fact_contradicts_detects_same_subject_predicate() -> None:
    """Test contradicts detects facts with same subject-predicate but different object."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Other Corp",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is True
    assert fact2.contradicts(fact1) is True


def test_semantic_fact_contradicts_returns_false_for_different_predicate() -> None:
    """Test contradicts returns False for different predicates."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="lives_in",
        object="New York",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is False


def test_semantic_fact_contradicts_returns_false_for_same_object() -> None:
    """Test contradicts returns False when objects are the same."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is False


def test_semantic_memory_has_required_methods() -> None:
    """Test SemanticMemory class has required interface methods."""
    memory = SemanticMemory()

    # Check required async methods exist
    assert hasattr(memory, "add_fact")
    assert hasattr(memory, "get_fact")
    assert hasattr(memory, "get_facts_about")
    assert hasattr(memory, "search_facts")
    assert hasattr(memory, "invalidate_fact")
    assert hasattr(memory, "delete_fact")


@pytest.mark.asyncio
async def test_add_fact_stores_in_graphiti(mock_graphiti_client: MagicMock) -> None:
    """Test that add_fact stores fact in Graphiti."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )

    memory = SemanticMemory()

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_graphiti_client

        result = await memory.add_fact(fact)

        assert result == "fact-123"
        mock_graphiti_client.add_episode.assert_called_once()


@pytest.mark.asyncio
async def test_add_fact_generates_id_if_missing() -> None:
    """Test that add_fact generates ID if not provided."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="",  # Empty ID
        user_id="user-456",
        subject="Jane",
        predicate="title",
        object="CEO",
        confidence=0.90,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
    )

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="new-uuid"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_client

        result = await memory.add_fact(fact)

        # Should have generated a UUID
        assert result != ""
        assert len(result) > 0


@pytest.mark.asyncio
async def test_get_fact_retrieves_by_id() -> None:
    """Test get_fact retrieves specific fact by ID."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = "Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: " + now.isoformat()
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        fact = await memory.get_fact(user_id="user-456", fact_id="fact-123")
        assert fact is not None
        mock_driver.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_fact_raises_not_found() -> None:
    """Test get_fact raises FactNotFoundError when not found."""
    from src.core.exceptions import FactNotFoundError

    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        with pytest.raises(FactNotFoundError):
            await memory.get_fact(user_id="user-456", fact_id="nonexistent")


@pytest.mark.asyncio
async def test_get_facts_about_returns_facts_for_subject() -> None:
    """Test get_facts_about returns facts about a specific subject."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Subject: John Doe\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: " + now.isoformat()
    mock_edge.created_at = now

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.get_facts_about(user_id="user-456", subject="John Doe")
        assert isinstance(results, list)
        mock_client.search.assert_called_once()
        # Verify search was called with subject
        call_args = mock_client.search.call_args
        assert "John Doe" in call_args[0][0]


@pytest.mark.asyncio
async def test_get_facts_about_filters_by_validity() -> None:
    """Test get_facts_about respects as_of parameter."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Return empty for simplicity, just testing the method is called
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        now = datetime.now(UTC)
        results = await memory.get_facts_about(
            user_id="user-456",
            subject="John Doe",
            as_of=now,
        )
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_facts_uses_semantic_search() -> None:
    """Test search_facts uses Graphiti's semantic search."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Subject: John\nPredicate: works_at\nObject: Acme Corp\nConfidence: 0.95\nSource: user_stated\nValid From: " + now.isoformat()
    mock_edge.created_at = now

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.search_facts(
            user_id="user-456",
            query="who works at Acme",
            min_confidence=0.5,
            limit=10,
        )
        assert isinstance(results, list)
        mock_client.search.assert_called_once()


@pytest.mark.asyncio
async def test_search_facts_filters_by_confidence() -> None:
    """Test search_facts filters by minimum confidence."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Low confidence fact
    mock_edge = MagicMock()
    mock_edge.fact = "Subject: John\nPredicate: works_at\nObject: Maybe Corp\nConfidence: 0.3\nSource: inferred\nValid From: " + now.isoformat()
    mock_edge.created_at = now

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await memory.search_facts(
            user_id="user-456",
            query="who works where",
            min_confidence=0.5,  # Higher than the fact's confidence
            limit=10,
        )
        # Should filter out the low-confidence fact
        assert len(results) == 0


@pytest.mark.asyncio
async def test_invalidate_fact_soft_deletes() -> None:
    """Test invalidate_fact marks fact as invalidated."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"updated": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        await memory.invalidate_fact(
            user_id="user-456",
            fact_id="fact-123",
            reason="outdated information",
        )
        mock_driver.execute_query.assert_called_once()
        # Verify the query includes invalidation fields
        call_args = mock_driver.execute_query.call_args
        assert "invalidated_at" in call_args[0][0]
        assert "reason" in call_args.kwargs


@pytest.mark.asyncio
async def test_invalidate_fact_raises_not_found() -> None:
    """Test invalidate_fact raises FactNotFoundError when not found."""
    from src.core.exceptions import FactNotFoundError

    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        with pytest.raises(FactNotFoundError):
            await memory.invalidate_fact(
                user_id="user-456",
                fact_id="nonexistent",
                reason="test",
            )


@pytest.mark.asyncio
async def test_delete_fact_removes_from_graphiti() -> None:
    """Test delete_fact permanently removes fact from Graphiti."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        await memory.delete_fact(user_id="user-456", fact_id="fact-123")
        mock_driver.execute_query.assert_called_once()
        # Verify DETACH DELETE is used
        call_args = mock_driver.execute_query.call_args
        assert "DETACH DELETE" in call_args[0][0]


@pytest.mark.asyncio
async def test_delete_fact_raises_not_found() -> None:
    """Test delete_fact raises FactNotFoundError when not found."""
    from src.core.exceptions import FactNotFoundError

    memory = SemanticMemory()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 0}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        with pytest.raises(FactNotFoundError):
            await memory.delete_fact(user_id="user-456", fact_id="nonexistent")
