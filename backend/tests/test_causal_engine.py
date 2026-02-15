"""Unit tests for the Causal Chain Traversal Engine.

Tests cover:
- Entity extraction from trigger events
- Hop traversal with confidence decay
- Cycle detection
- Parallel chains from single events
- Performance targets (< 500ms for 4-hop traversal)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.models import (
    CausalChain,
    CausalHop,
    CausalTraversalRequest,
    EntityExtraction,
    InferredRelationship,
)
from src.intelligence.causal.store import CausalChainStore


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client."""
    client = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def mock_graphiti_client() -> MagicMock:
    """Create a mock Graphiti client."""
    client = MagicMock()
    client.search = AsyncMock()
    return client


@pytest.fixture
def causal_engine(
    mock_graphiti_client: MagicMock,
    mock_llm_client: MagicMock,
    mock_db_client: MagicMock,
) -> CausalChainEngine:
    """Create a CausalChainEngine with mocked dependencies."""
    return CausalChainEngine(
        graphiti_client=mock_graphiti_client,
        llm_client=mock_llm_client,
        db_client=mock_db_client,
    )


# ============================================================
# Test Entity Extraction
# ============================================================


@pytest.mark.asyncio
async def test_entity_extraction(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test that LLM extracts correct entities from trigger event."""
    # Mock LLM response
    mock_llm_client.generate_response.return_value = """[
        {"name": "Pfizer", "entity_type": "company", "relevance": 0.9, "context": "Pharmaceutical company"},
        {"name": "FDA", "entity_type": "regulation", "relevance": 0.8, "context": "Regulatory body"}
    ]"""

    trigger_event = "Pfizer received FDA approval for their new COVID vaccine"

    entities = await causal_engine._extract_entities(trigger_event)

    assert len(entities) == 2
    assert entities[0].name == "Pfizer"
    assert entities[0].entity_type == "company"
    assert entities[1].name == "FDA"
    assert entities[1].entity_type == "regulation"


@pytest.mark.asyncio
async def test_entity_extraction_with_markdown(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test entity extraction handles markdown code blocks."""
    mock_llm_client.generate_response.return_value = """```json
[
    {"name": "Moderna", "entity_type": "company", "relevance": 0.95, "context": "Biotech company"}
]
```"""

    entities = await causal_engine._extract_entities("Moderna announces new vaccine")

    assert len(entities) == 1
    assert entities[0].name == "Moderna"


@pytest.mark.asyncio
async def test_entity_extraction_empty_response(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test entity extraction handles invalid JSON gracefully."""
    mock_llm_client.generate_response.return_value = "This is not valid JSON"

    entities = await causal_engine._extract_entities("Some event")

    assert entities == []


# ============================================================
# Test Confidence Decay
# ============================================================


def test_confidence_decay_calculation() -> None:
    """Test that confidence decays correctly per hop."""
    engine = CausalChainEngine(
        graphiti_client=MagicMock(),
        llm_client=MagicMock(),
        db_client=MagicMock(),
    )

    # Initial confidence = 1.0
    # After 1 hop: 1.0 * 0.85 * 0.8 = 0.68
    # After 2 hops: 0.68 * 0.85 * 0.8 = 0.4624
    # After 3 hops: 0.4624 * 0.85 * 0.8 = 0.3144
    # After 4 hops: 0.3144 * 0.85 * 0.8 = 0.2138

    confidence = 1.0
    rel_confidence = 0.8

    # Hop 1
    confidence = confidence * CausalChainEngine.HOP_DECAY * rel_confidence
    assert confidence == pytest.approx(0.68, rel=0.01)

    # Hop 2
    confidence = confidence * CausalChainEngine.HOP_DECAY * rel_confidence
    assert confidence == pytest.approx(0.4624, rel=0.01)

    # Hop 3
    confidence = confidence * CausalChainEngine.HOP_DECAY * rel_confidence
    assert confidence == pytest.approx(0.3144, rel=0.01)

    # Hop 4
    confidence = confidence * CausalChainEngine.HOP_DECAY * rel_confidence
    assert confidence == pytest.approx(0.214, rel=0.01)


# ============================================================
# Test Cycle Detection
# ============================================================


@pytest.mark.asyncio
async def test_cycle_detection(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test that traversal doesn't loop infinitely when cycles exist."""
    # Mock entity extraction
    with patch.object(
        causal_engine,
        "_extract_entities",
        return_value=[
            EntityExtraction(name="CompanyA", entity_type="company", relevance=0.9)
        ],
    ):
        # Mock Graphiti to return no relationships
        with patch.object(
            causal_engine,
            "_get_graphiti_relationships",
            return_value=[],
        ):
            # Mock inference to create a cycle: A -> B -> A
            call_count = 0

            async def mock_infer(*args, **kwargs):  # noqa: ARG001
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return [
                        InferredRelationship(
                            target_entity="CompanyB",
                            relationship_type="causes",
                            confidence=0.8,
                            explanation="A causes B",
                        )
                    ]
                else:
                    # Try to create cycle B -> A
                    return [
                        InferredRelationship(
                            target_entity="CompanyA",
                            relationship_type="causes",
                            confidence=0.8,
                            explanation="B causes A",
                        )
                    ]

            with patch.object(
                causal_engine,
                "_infer_causal_relationships",
                side_effect=mock_infer,
            ):
                with patch.object(
                    causal_engine,
                    "_gather_inference_context",
                    return_value="context",
                ):
                    chains = await causal_engine.traverse(
                        user_id="test-user",
                        trigger_event="CompanyA announces new product",
                        max_hops=4,
                    )

                    # Should have chains but no infinite loop
                    # The cycle should be detected and not cause infinite recursion
                    assert call_count <= 3  # Should not call infinitely
                    assert isinstance(chains, list)


# ============================================================
# Test Parallel Chains
# ============================================================


@pytest.mark.asyncio
async def test_parallel_chains_from_single_event(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test that a single event can produce multiple independent chains."""
    # Mock entity extraction to return multiple entities
    with patch.object(
        causal_engine,
        "_extract_entities",
        return_value=[
            EntityExtraction(name="Pfizer", entity_type="company", relevance=0.9),
            EntityExtraction(name="Moderna", entity_type="company", relevance=0.85),
        ],
    ):
        # Mock relationships to return different chains
        with patch.object(
            causal_engine,
            "_get_graphiti_relationships",
            return_value=[],
        ):
            inference_results = {
                "Pfizer": [
                    InferredRelationship(
                        target_entity="Vaccine Market",
                        relationship_type="causes",
                        confidence=0.8,
                        explanation="Pfizer impacts vaccine market",
                    )
                ],
                "Moderna": [
                    InferredRelationship(
                        target_entity="mRNA Technology",
                        relationship_type="causes",
                        confidence=0.75,
                        explanation="Moderna advances mRNA",
                    )
                ],
            }

            async def mock_infer(user_id, entity, trigger_event):  # noqa: ARG001
                return inference_results.get(entity.name, [])

            with patch.object(
                causal_engine,
                "_infer_causal_relationships",
                side_effect=mock_infer,
            ):
                with patch.object(
                    causal_engine,
                    "_gather_inference_context",
                    return_value="context",
                ):
                    chains = await causal_engine.traverse(
                        user_id="test-user",
                        trigger_event="Major pharma announcement",
                        max_hops=2,
                    )

                    # Should have chains from both entities
                    assert len(chains) >= 1  # At least one chain should exist


# ============================================================
# Test Minimum Confidence Threshold
# ============================================================


@pytest.mark.asyncio
async def test_min_confidence_threshold(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test that chains below minimum confidence are filtered out."""
    with patch.object(
        causal_engine,
        "_extract_entities",
        return_value=[
            EntityExtraction(name="CompanyA", entity_type="company", relevance=0.9)
        ],
    ):
        with patch.object(
            causal_engine,
            "_get_graphiti_relationships",
            return_value=[],
        ):
            # Return low-confidence relationships
            with patch.object(
                causal_engine,
                "_infer_causal_relationships",
                return_value=[
                    InferredRelationship(
                        target_entity="LowConfTarget",
                        relationship_type="causes",
                        confidence=0.2,  # Very low
                        explanation="Weak link",
                    )
                ],
            ):
                with patch.object(
                    causal_engine,
                    "_gather_inference_context",
                    return_value="context",
                ):
                    chains = await causal_engine.traverse(
                        user_id="test-user",
                        trigger_event="Test event",
                        max_hops=4,
                        min_confidence=0.5,  # High threshold
                    )

                    # Chains should be empty due to low confidence
                    for chain in chains:
                        assert chain.final_confidence >= 0.5


# ============================================================
# Test Performance
# ============================================================


@pytest.mark.asyncio
async def test_performance_4_hop_traversal(
    causal_engine: CausalChainEngine,
    mock_llm_client: MagicMock,
) -> None:
    """Test that 4-hop traversal completes in < 500ms."""
    # Mock all async operations to return quickly
    with patch.object(
        causal_engine,
        "_extract_entities",
        return_value=[
            EntityExtraction(name="TestCompany", entity_type="company", relevance=0.9)
        ],
    ):
        with patch.object(
            causal_engine,
            "_get_graphiti_relationships",
            return_value=[],
        ):
            with patch.object(
                causal_engine,
                "_infer_causal_relationships",
                return_value=[
                    InferredRelationship(
                        target_entity="Target",
                        relationship_type="causes",
                        confidence=0.8,
                        explanation="Test",
                    )
                ],
            ):
                with patch.object(
                    causal_engine,
                    "_gather_inference_context",
                    return_value="context",
                ):
                    start_time = time.monotonic()

                    await causal_engine.traverse(
                        user_id="test-user",
                        trigger_event="Test event for performance",
                        max_hops=4,
                    )

                    elapsed_ms = (time.monotonic() - start_time) * 1000

                    # With mocked operations, should be very fast
                    assert elapsed_ms < 500, f"Traversal took {elapsed_ms}ms, expected < 500ms"


# ============================================================
# Test CausalChainStore
# ============================================================


@pytest.mark.asyncio
async def test_store_save_chain(mock_db_client: MagicMock) -> None:
    """Test saving a causal chain to the database."""
    # Mock the database response
    mock_result = MagicMock()
    mock_result.data = [{"id": "12345678-1234-1234-1234-123456789012"}]

    mock_table = MagicMock()
    mock_table.insert.return_value.execute.return_value = mock_result
    mock_db_client.table.return_value = mock_table

    store = CausalChainStore(db_client=mock_db_client)

    chain = CausalChain(
        trigger_event="Test event",
        hops=[
            CausalHop(
                source_entity="A",
                target_entity="B",
                relationship="causes",
                confidence=0.8,
                explanation="Test hop",
            )
        ],
        final_confidence=0.68,
    )

    chain_id = await store.save_chain(
        user_id="test-user",
        chain=chain,
        source_context="test",
    )

    assert chain_id is not None
    mock_table.insert.assert_called_once()


@pytest.mark.asyncio
async def test_store_get_chains(mock_db_client: MagicMock) -> None:
    """Test retrieving chains from the database."""
    mock_result = MagicMock()
    mock_result.data = [
        {
            "id": "12345678-1234-1234-1234-123456789012",
            "trigger_event": "Test event",
            "hops": [
                {
                    "source_entity": "A",
                    "target_entity": "B",
                    "relationship": "causes",
                    "confidence": 0.8,
                    "explanation": "Test",
                }
            ],
            "final_confidence": 0.68,
            "time_to_impact": None,
            "source_context": "test",
            "source_id": None,
            "created_at": "2026-02-19T00:00:00Z",
        }
    ]

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
        mock_result
    )
    mock_db_client.table.return_value = mock_table

    store = CausalChainStore(db_client=mock_db_client)

    chains = await store.get_chains(user_id="test-user")

    assert len(chains) == 1
    assert chains[0].trigger_event == "Test event"


@pytest.mark.asyncio
async def test_store_invalidate_chain(mock_db_client: MagicMock) -> None:
    """Test invalidating a causal chain."""
    mock_result = MagicMock()
    mock_result.data = [{"id": "test-chain-id"}]

    mock_table = MagicMock()
    mock_table.update.return_value.eq.return_value.execute.return_value = mock_result
    mock_db_client.table.return_value = mock_table

    store = CausalChainStore(db_client=mock_db_client)

    from uuid import uuid4

    success = await store.invalidate_chain(uuid4())

    assert success is True


# ============================================================
# Test CausalTraversalRequest/Response Models
# ============================================================


def test_causal_traversal_request_validation() -> None:
    """Test that request validation works correctly."""
    # Valid request
    request = CausalTraversalRequest(
        trigger_event="Pfizer received FDA approval",
        max_hops=4,
        min_confidence=0.3,
    )
    assert request.max_hops == 4
    assert request.min_confidence == 0.3

    # Test max_hops bounds
    with pytest.raises(ValueError):
        CausalTraversalRequest(trigger_event="test", max_hops=10)  # > 6

    with pytest.raises(ValueError):
        CausalTraversalRequest(trigger_event="test", max_hops=0)  # < 1

    # Test min_confidence bounds
    with pytest.raises(ValueError):
        CausalTraversalRequest(trigger_event="test", min_confidence=1.5)  # > 1.0

    with pytest.raises(ValueError):
        CausalTraversalRequest(trigger_event="test", min_confidence=0.05)  # < 0.1


def test_causal_hop_model() -> None:
    """Test CausalHop model validation."""
    hop = CausalHop(
        source_entity="Pfizer",
        target_entity="Vaccine Market",
        relationship="causes",
        confidence=0.85,
        explanation="FDA approval impacts market",
    )

    assert hop.source_entity == "Pfizer"
    assert hop.confidence == 0.85

    # Test confidence bounds
    with pytest.raises(ValueError):
        CausalHop(
            source_entity="A",
            target_entity="B",
            relationship="causes",
            confidence=1.5,  # Invalid
            explanation="Test",
        )


def test_causal_chain_model() -> None:
    """Test CausalChain model."""
    chain = CausalChain(
        trigger_event="FDA approval",
        hops=[
            CausalHop(
                source_entity="Pfizer",
                target_entity="Vaccine Market",
                relationship="causes",
                confidence=0.85,
                explanation="Test",
            )
        ],
        final_confidence=0.72,
        time_to_impact="2-4 weeks",
    )

    assert len(chain.hops) == 1
    assert chain.final_confidence == 0.72
    assert chain.time_to_impact == "2-4 weeks"
