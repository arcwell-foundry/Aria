"""Tests for the Background Memory Construction Orchestrator (US-911)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.memory_constructor import (
    SOURCE_PRIORITY,
    MemoryConstructionOrchestrator,
)


# --- Helpers ---


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


def _make_fact(
    source: str = "enrichment_website",
    confidence: float = 0.7,
    metadata: dict[str, Any] | None = None,
    category: str = "company_info",
) -> dict[str, Any]:
    """Build a mock semantic fact row."""
    return {
        "id": "fact-1",
        "user_id": "user-123",
        "content": "Acme Corp is a pharma company",
        "source": source,
        "confidence": confidence,
        "category": category,
        "metadata": metadata or {},
    }


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def constructor(mock_db: MagicMock) -> MemoryConstructionOrchestrator:
    """Create a MemoryConstructionOrchestrator with mocked DB."""
    with patch("src.onboarding.memory_constructor.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        c = MemoryConstructionOrchestrator()
    return c


# --- Source priority ---


def test_source_priority_user_stated_highest() -> None:
    """user_stated has the highest priority."""
    max_source = max(SOURCE_PRIORITY, key=SOURCE_PRIORITY.get)  # type: ignore[arg-type]
    assert max_source == "user_stated"


def test_source_priority_inferred_lowest() -> None:
    """inferred_during_onboarding has the lowest priority."""
    min_source = min(SOURCE_PRIORITY, key=SOURCE_PRIORITY.get)  # type: ignore[arg-type]
    assert min_source == "inferred_during_onboarding"


def test_source_priority_ordering() -> None:
    """Source priorities follow expected hierarchy."""
    assert SOURCE_PRIORITY["user_stated"] > SOURCE_PRIORITY["crm_import"]
    assert SOURCE_PRIORITY["crm_import"] > SOURCE_PRIORITY["document_upload"]
    assert SOURCE_PRIORITY["document_upload"] > SOURCE_PRIORITY["email_bootstrap"]
    assert SOURCE_PRIORITY["email_bootstrap"] > SOURCE_PRIORITY["enrichment_website"]
    assert SOURCE_PRIORITY["enrichment_website"] > SOURCE_PRIORITY["enrichment_news"]
    assert SOURCE_PRIORITY["enrichment_news"] > SOURCE_PRIORITY["inferred_during_onboarding"]


# --- Fact gathering ---


@pytest.mark.asyncio()
async def test_gather_all_facts(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Gathers facts from memory_semantic table for the user."""
    facts = [_make_fact(), _make_fact(source="crm_import")]
    chain = _build_chain(facts)
    mock_db.table.return_value = chain

    result = await constructor._gather_all_facts("user-123")

    mock_db.table.assert_called_with("memory_semantic")
    chain.select.assert_called_with("*")
    chain.eq.assert_called_with("user_id", "user-123")
    assert len(result) == 2


@pytest.mark.asyncio()
async def test_gather_all_facts_empty(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Returns empty list when no facts exist."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    result = await constructor._gather_all_facts("user-123")
    assert result == []


# --- Conflict resolution ---


@pytest.mark.asyncio()
async def test_resolve_conflicts_user_stated_gets_highest_confidence(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """User-stated facts get the highest adjusted confidence."""
    facts = [
        _make_fact(source="user_stated", confidence=0.8),
        _make_fact(source="enrichment_website", confidence=0.8),
        _make_fact(source="inferred_during_onboarding", confidence=0.8),
    ]

    resolved = await constructor._resolve_conflicts(facts)

    user_conf = resolved[0]["adjusted_confidence"]
    enrich_conf = resolved[1]["adjusted_confidence"]
    inferred_conf = resolved[2]["adjusted_confidence"]

    assert user_conf > enrich_conf > inferred_conf


@pytest.mark.asyncio()
async def test_resolve_conflicts_caps_at_099(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Adjusted confidence never exceeds 0.99."""
    facts = [_make_fact(source="user_stated", confidence=0.99)]
    resolved = await constructor._resolve_conflicts(facts)
    assert resolved[0]["adjusted_confidence"] <= 0.99


@pytest.mark.asyncio()
async def test_resolve_conflicts_unknown_source_gets_base(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Unknown sources get the base priority of 1.0."""
    facts = [
        _make_fact(source="unknown_source", confidence=0.7),
        _make_fact(source="inferred_during_onboarding", confidence=0.7),
    ]
    resolved = await constructor._resolve_conflicts(facts)
    # Both have priority 1.0 so should have same adjusted confidence
    assert resolved[0]["adjusted_confidence"] == resolved[1]["adjusted_confidence"]


@pytest.mark.asyncio()
async def test_resolve_conflicts_preserves_original_fields(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Conflict resolution preserves all original fact fields."""
    fact = _make_fact(source="crm_import", confidence=0.85)
    resolved = await constructor._resolve_conflicts([fact])

    assert resolved[0]["source"] == "crm_import"
    assert resolved[0]["confidence"] == 0.85
    assert "adjusted_confidence" in resolved[0]


# --- Entity graph construction ---


@pytest.mark.asyncio()
async def test_build_entity_graph_extracts_entities(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Extracts entities from fact metadata."""
    facts = [
        _make_fact(metadata={
            "entities": [
                {"name": "Acme Corp", "type": "company"},
                {"name": "Dr. Smith", "type": "person"},
            ],
        }),
        _make_fact(metadata={
            "entities": [
                {"name": "Acme Corp", "type": "company"},  # duplicate
                {"name": "Oncology", "type": "therapeutic_area"},
            ],
        }),
    ]

    with patch("src.db.graphiti.GraphitiClient") as mock_graphiti_cls:
        mock_graphiti = MagicMock()
        mock_graphiti.add_entity = AsyncMock()
        mock_graphiti_cls.return_value = mock_graphiti

        entities = await constructor._build_entity_graph("user-123", facts)

    # 3 unique entities (Acme Corp deduplicated)
    assert len(entities) == 3
    names = {e["name"] for e in entities}
    assert "Acme Corp" in names
    assert "Dr. Smith" in names
    assert "Oncology" in names


@pytest.mark.asyncio()
async def test_build_entity_graph_handles_string_entities(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Handles entities stored as plain strings."""
    facts = [
        _make_fact(metadata={"entities": ["Acme Corp", "Dr. Smith"]}),
    ]

    entities = await constructor._build_entity_graph("user-123", facts)

    assert len(entities) == 2
    assert entities[0]["type"] == "unknown"


@pytest.mark.asyncio()
async def test_build_entity_graph_counts_facts(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Tracks fact_count per entity across multiple facts."""
    facts = [
        _make_fact(metadata={"entities": [{"name": "Acme", "type": "company"}]}),
        _make_fact(metadata={"entities": [{"name": "Acme", "type": "company"}]}),
        _make_fact(metadata={"entities": [{"name": "Acme", "type": "company"}]}),
    ]

    entities = await constructor._build_entity_graph("user-123", facts)

    assert len(entities) == 1
    assert entities[0]["fact_count"] == 3


@pytest.mark.asyncio()
async def test_build_entity_graph_graphiti_failure_nonfatal(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """Graphiti storage failure doesn't crash the pipeline."""
    facts = [
        _make_fact(metadata={"entities": [{"name": "Acme", "type": "company"}]}),
    ]

    with patch(
        "src.db.graphiti.GraphitiClient",
        side_effect=ImportError("no graphiti"),
    ):
        entities = await constructor._build_entity_graph("user-123", facts)

    assert len(entities) == 1


@pytest.mark.asyncio()
async def test_build_entity_graph_empty_facts(
    constructor: MemoryConstructionOrchestrator,
) -> None:
    """No entities from facts without entity metadata."""
    facts = [_make_fact(metadata={})]
    entities = await constructor._build_entity_graph("user-123", facts)
    assert len(entities) == 0


# --- Final readiness calculation ---


@pytest.mark.asyncio()
async def test_calculate_final_readiness_weighted(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Calculates overall readiness using correct weights."""
    scores = {
        "corporate_memory": 80.0,
        "digital_twin": 60.0,
        "relationship_graph": 40.0,
        "integrations": 100.0,
        "goal_clarity": 50.0,
    }
    select_chain = _build_chain({"readiness_scores": scores})
    update_chain = _build_chain([{}])
    mock_db.table.side_effect = [select_chain, update_chain]

    result = await constructor._calculate_final_readiness("user-123")

    # 80*0.25 + 60*0.25 + 40*0.20 + 100*0.15 + 50*0.15
    # = 20 + 15 + 8 + 15 + 7.5 = 65.5
    assert result["overall"] == 65.5
    assert result["corporate_memory"] == 80.0


@pytest.mark.asyncio()
async def test_calculate_final_readiness_no_state(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Returns empty dict when no onboarding state exists."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    result = await constructor._calculate_final_readiness("user-123")
    assert result == {}


@pytest.mark.asyncio()
async def test_calculate_final_readiness_updates_db(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Stores computed readiness scores back to DB."""
    scores = {
        "corporate_memory": 50.0,
        "digital_twin": 50.0,
        "relationship_graph": 50.0,
        "integrations": 50.0,
        "goal_clarity": 50.0,
    }
    select_chain = _build_chain({"readiness_scores": scores})
    update_chain = _build_chain([{}])
    mock_db.table.side_effect = [select_chain, update_chain]

    await constructor._calculate_final_readiness("user-123")

    # Verify update was called
    update_chain.update.assert_called_once()
    call_args = update_chain.update.call_args[0][0]
    assert "readiness_scores" in call_args
    assert call_args["readiness_scores"]["overall"] == 50.0


# --- Full pipeline ---


@pytest.mark.asyncio()
async def test_run_construction_full_pipeline(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Full pipeline gathers, resolves, builds graph, and calculates readiness."""
    facts = [
        _make_fact(
            source="user_stated",
            confidence=0.9,
            metadata={"entities": [{"name": "Acme", "type": "company"}]},
        ),
        _make_fact(
            source="enrichment_website",
            confidence=0.7,
        ),
    ]
    readiness_scores = {
        "corporate_memory": 70.0,
        "digital_twin": 60.0,
        "relationship_graph": 50.0,
        "integrations": 40.0,
        "goal_clarity": 30.0,
    }

    # _gather_all_facts query
    facts_chain = _build_chain(facts)
    # _calculate_final_readiness select
    readiness_select_chain = _build_chain({"readiness_scores": readiness_scores})
    # _calculate_final_readiness update
    readiness_update_chain = _build_chain([{}])

    mock_db.table.side_effect = [
        facts_chain,
        readiness_select_chain,
        readiness_update_chain,
    ]

    with patch.object(constructor, "_record_episodic_event", new_callable=AsyncMock):
        with patch.object(constructor, "_log_audit", new_callable=AsyncMock):
            summary = await constructor.run_construction("user-123")

    assert summary["total_facts"] == 2
    assert summary["entities_mapped"] == 1
    assert "readiness" in summary
    assert "constructed_at" in summary


@pytest.mark.asyncio()
async def test_run_construction_records_episodic_event(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Pipeline records an episodic memory event on completion."""
    facts_chain = _build_chain([])
    readiness_chain = _build_chain({"readiness_scores": {}})
    readiness_update_chain = _build_chain([{}])
    mock_db.table.side_effect = [facts_chain, readiness_chain, readiness_update_chain]

    mock_record = AsyncMock()
    mock_audit = AsyncMock()

    with patch.object(constructor, "_record_episodic_event", mock_record):
        with patch.object(constructor, "_log_audit", mock_audit):
            await constructor.run_construction("user-123")

    mock_record.assert_called_once()
    call_args = mock_record.call_args
    assert call_args[0][0] == "user-123"
    assert "memory_construction_complete" in call_args[0][1]


@pytest.mark.asyncio()
async def test_run_construction_logs_audit(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Pipeline creates an audit log entry."""
    facts_chain = _build_chain([])
    readiness_chain = _build_chain({"readiness_scores": {}})
    readiness_update_chain = _build_chain([{}])
    mock_db.table.side_effect = [facts_chain, readiness_chain, readiness_update_chain]

    mock_record = AsyncMock()
    mock_audit = AsyncMock()

    with patch.object(constructor, "_record_episodic_event", mock_record):
        with patch.object(constructor, "_log_audit", mock_audit):
            await constructor.run_construction("user-123")

    mock_audit.assert_called_once()


@pytest.mark.asyncio()
async def test_run_construction_episodic_failure_nonfatal(
    constructor: MemoryConstructionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Episodic recording failure doesn't crash the pipeline."""
    facts_chain = _build_chain([])
    readiness_chain = _build_chain({"readiness_scores": {}})
    readiness_update_chain = _build_chain([{}])
    mock_db.table.side_effect = [facts_chain, readiness_chain, readiness_update_chain]

    with patch.object(
        constructor,
        "_record_episodic_event",
        new_callable=AsyncMock,
        side_effect=Exception("episodic down"),
    ):
        with patch.object(constructor, "_log_audit", new_callable=AsyncMock):
            # Should not raise
            summary = await constructor.run_construction("user-123")

    assert summary["total_facts"] == 0
