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
    mock_node.content = (
        "Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: "
        + now.isoformat()
    )
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
    mock_edge.fact = (
        "Subject: John Doe\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: "
        + now.isoformat()
    )
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
    mock_edge.fact = (
        "Subject: John\nPredicate: works_at\nObject: Acme Corp\nConfidence: 0.95\nSource: user_stated\nValid From: "
        + now.isoformat()
    )
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
    mock_edge.fact = (
        "Subject: John\nPredicate: works_at\nObject: Maybe Corp\nConfidence: 0.3\nSource: inferred\nValid From: "
        + now.isoformat()
    )
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


def test_semantic_fact_with_corroboration_fields() -> None:
    """Test SemanticFact includes corroboration tracking fields."""
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
        last_confirmed_at=now,
        corroborating_sources=["crm_import:123", "user_stated:456"],
    )

    assert fact.last_confirmed_at == now
    assert len(fact.corroborating_sources) == 2
    assert "crm_import:123" in fact.corroborating_sources


def test_semantic_fact_to_dict_includes_corroboration() -> None:
    """Test to_dict includes corroboration fields."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="title",
        object="CEO",
        confidence=0.90,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
        last_confirmed_at=now,
        corroborating_sources=["source:1"],
    )

    data = fact.to_dict()

    assert data["last_confirmed_at"] == now.isoformat()
    assert data["corroborating_sources"] == ["source:1"]


def test_semantic_fact_from_dict_restores_corroboration() -> None:
    """Test from_dict restores corroboration fields."""
    now = datetime.now(UTC)
    data = {
        "id": "fact-123",
        "user_id": "user-456",
        "subject": "Jane",
        "predicate": "department",
        "object": "Sales",
        "confidence": 0.85,
        "source": "extracted",
        "valid_from": now.isoformat(),
        "valid_to": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "last_confirmed_at": now.isoformat(),
        "corroborating_sources": ["source:a", "source:b"],
    }

    fact = SemanticFact.from_dict(data)

    assert fact.last_confirmed_at == now
    assert fact.corroborating_sources == ["source:a", "source:b"]


def test_build_fact_body_includes_corroboration_fields() -> None:
    """Test _build_fact_body includes last_confirmed_at and corroborating_sources."""
    now = datetime.now(UTC)
    confirmed = now - timedelta(days=5)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
        last_confirmed_at=confirmed,
        corroborating_sources=["source:abc", "source:def"],
    )

    memory = SemanticMemory()
    body = memory._build_fact_body(fact)

    assert f"Last Confirmed At: {confirmed.isoformat()}" in body
    assert "Corroborating Sources: source:abc,source:def" in body


def test_parse_content_to_fact_handles_corroboration_fields() -> None:
    """Test _parse_content_to_fact parses new fields correctly."""
    now = datetime.now(UTC)
    confirmed = now - timedelta(days=3)

    content = f"""Subject: Jane
Predicate: title
Object: CEO
Confidence: 0.90
Source: crm_import
Valid From: {now.isoformat()}
Last Confirmed At: {confirmed.isoformat()}
Corroborating Sources: source:1,source:2"""

    memory = SemanticMemory()
    fact = memory._parse_content_to_fact(
        fact_id="fact-123",
        content=content,
        user_id="user-456",
        created_at=now,
    )

    assert fact is not None
    assert fact.last_confirmed_at == confirmed
    assert fact.corroborating_sources == ["source:1", "source:2"]


@pytest.mark.asyncio
async def test_confirm_fact_updates_last_confirmed_at() -> None:
    """Test confirm_fact updates the last_confirmed_at timestamp."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Setup mock to return a fact
    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = f"Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: {now.isoformat()}"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-fact"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await memory.confirm_fact(
            user_id="user-456",
            fact_id="fact-123",
            confirming_source="crm_import:789",
        )

        # Should have called add_episode to update the fact
        assert mock_client.add_episode.called


@pytest.mark.asyncio
async def test_confirm_fact_adds_corroborating_source() -> None:
    """Test confirm_fact adds the confirming source to corroborating_sources."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Existing fact with one corroborating source
    existing_sources = "Corroborating Sources: source:existing"
    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = f"Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: {now.isoformat()}\n{existing_sources}"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-fact"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await memory.confirm_fact(
            user_id="user-456",
            fact_id="fact-123",
            confirming_source="crm_import:new",
        )

        # Verify the episode body contains both sources
        call_args = mock_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "source:existing" in episode_body
        assert "crm_import:new" in episode_body


def test_get_effective_confidence_for_fact() -> None:
    """Test get_effective_confidence returns scorer result for a fact."""
    now = datetime.now(UTC)
    confirmed = now - timedelta(days=3)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        last_confirmed_at=confirmed,
        corroborating_sources=["source:1", "source:2"],
    )

    memory = SemanticMemory()
    result = memory.get_effective_confidence(fact, as_of=now)

    # Should be original confidence (confirmed within 7 days) + 2 boosts
    # 0.95 + 0.20 = 1.15, capped at 0.99
    assert result == pytest.approx(0.99)


def test_get_effective_confidence_with_decay() -> None:
    """Test get_effective_confidence applies decay for old facts."""
    now = datetime.now(UTC)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.75,
        source=FactSource.EXTRACTED,
        valid_from=now - timedelta(days=60),
        last_confirmed_at=None,
        corroborating_sources=[],
    )

    memory = SemanticMemory()
    result = memory.get_effective_confidence(fact, as_of=now)

    # 0.75 - ((60-7) * 0.05/30) = 0.75 - 0.0883 = 0.6617
    expected = 0.75 - ((60 - 7) * 0.05 / 30)
    assert result == pytest.approx(expected, rel=0.01)


@pytest.mark.asyncio
async def test_add_fact_logs_audit_entry() -> None:
    """Test that add_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType

    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-audit-test",
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

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-123"

            await memory.add_fact(fact)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == "user-456"
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.SEMANTIC
            assert call_kwargs["memory_id"] == "fact-audit-test"
            assert call_kwargs["suppress_errors"] is True


@pytest.mark.asyncio
async def test_invalidate_fact_logs_audit_entry() -> None:
    """Test that invalidate_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"updated": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-456"

            await memory.invalidate_fact(
                user_id="user-456",
                fact_id="fact-123",
                reason="outdated",
            )

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.INVALIDATE
            assert call_kwargs["memory_type"] == MemoryType.SEMANTIC


@pytest.mark.asyncio
async def test_delete_fact_logs_audit_entry() -> None:
    """Test that delete_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-789"

            await memory.delete_fact(user_id="user-456", fact_id="fact-123")

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.DELETE


@pytest.mark.asyncio
async def test_search_facts_respects_as_of_validity() -> None:
    """Test search_facts filters by validity at as_of date."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=60)

    # Fact that was valid in the past but is now expired
    mock_edge = MagicMock()
    mock_edge.fact = f"Subject: John\nPredicate: works_at\nObject: OldCorp\nConfidence: 0.90\nSource: user_stated\nValid From: {past.isoformat()}\nValid To: {(now - timedelta(days=30)).isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "fact-temporal"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 45 days ago - fact should be valid then
        as_of_date = now - timedelta(days=45)
        results = await memory.search_facts(
            user_id="user-456",
            query="where does John work",
            as_of=as_of_date,
        )

        # Should include the fact (was valid at that time)
        assert len(results) == 1
        assert results[0].object == "OldCorp"


@pytest.mark.asyncio
async def test_search_facts_excludes_invalid_at_as_of() -> None:
    """Test search_facts excludes facts invalid at as_of date."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=60)

    # Fact that was valid in the past but is now expired
    mock_edge = MagicMock()
    mock_edge.fact = f"Subject: John\nPredicate: works_at\nObject: OldCorp\nConfidence: 0.90\nSource: user_stated\nValid From: {past.isoformat()}\nValid To: {(now - timedelta(days=30)).isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "fact-temporal-2"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of today - fact should be expired
        results = await memory.search_facts(
            user_id="user-456",
            query="where does John work",
            as_of=now,
        )

        # Should NOT include the fact (expired)
        assert len(results) == 0
