"""Integration test: signal -> graph traversal -> implication detection -> WebSocket."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.memory.cold_retrieval import ColdMemoryResult, EntityContext, MemorySource
from src.services.signal_orient import analyze_signal_with_graph


def _make_realistic_entity_context() -> EntityContext:
    """Build a realistic BioGenix entity context for integration testing."""
    return EntityContext(
        entity_id="BioGenix",
        direct_facts=[
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="BioGenix capacity project targeting Q3 FDA filing",
                relevance_score=0.85,
            ),
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="BioGenix annual revenue $450M with 30% growth",
                relevance_score=0.7,
            ),
        ],
        relationships=[
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="BioGenix competes with WuXi in CDMO manufacturing",
                relevance_score=0.8,
            ),
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content="BioGenix partners with Meridian Pharma on oncology pipeline",
                relevance_score=0.75,
            ),
        ],
        recent_interactions=[
            ColdMemoryResult(
                source=MemorySource.EPISODIC,
                content="Sent proposal to BioGenix VP Procurement last week",
                relevance_score=0.9,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_end_to_end_signal_graph_implication() -> None:
    """Full pipeline: signal detected -> graph queried -> implications found -> alert sent."""
    signal = {
        "company_name": "BioGenix",
        "signal_type": "leadership_change",
        "headline": "BioGenix VP Manufacturing resigned amid capacity expansion",
        "summary": "Key departure during critical manufacturing scale-up",
        "relevance_score": 0.9,
    }

    # ColdMemoryRetriever returns rich graph context
    cold_retriever = AsyncMock()
    cold_retriever.retrieve_for_entity = AsyncMock(
        return_value=_make_realistic_entity_context()
    )

    # ImplicationEngine returns a high-score implication
    mock_implication = MagicMock()
    mock_implication.combined_score = 0.82
    mock_implication.type = MagicMock(value="threat")
    mock_implication.content = (
        "Leadership departure + capacity project delay + WuXi competition = "
        "risk to your active BioGenix proposal"
    )
    mock_implication.trigger_event = signal["headline"]
    mock_implication.recommended_actions = [
        "Accelerate BioGenix proposal before WuXi approaches them",
        "Schedule call with BioGenix VP Procurement to discuss timeline",
    ]
    mock_implication.causal_chain = [
        {
            "source_entity": "BioGenix VP Manufacturing",
            "target_entity": "capacity_project",
            "relationship": "delays",
        },
        {
            "source_entity": "capacity_project",
            "target_entity": "Q3_filing",
            "relationship": "delays",
        },
        {
            "source_entity": "WuXi",
            "target_entity": "BioGenix",
            "relationship": "may_approach",
        },
    ]

    implication_engine = AsyncMock()
    implication_engine.analyze_event = AsyncMock(return_value=[mock_implication])

    ws_manager = AsyncMock()
    proactive_router = AsyncMock()
    proactive_router.route = AsyncMock(return_value={"channel": "websocket"})

    # Execute
    result = await analyze_signal_with_graph(
        user_id="user-456",
        signal=signal,
        cold_retriever=cold_retriever,
        implication_engine=implication_engine,
        ws_manager=ws_manager,
        proactive_router=proactive_router,
    )

    # Verify graph was queried
    cold_retriever.retrieve_for_entity.assert_called_once_with(
        user_id="user-456",
        entity_id="BioGenix",
        hops=3,
    )

    # Verify implication engine received graph-enriched event description
    event_arg = implication_engine.analyze_event.call_args.kwargs.get(
        "event",
        implication_engine.analyze_event.call_args.args[1]
        if len(implication_engine.analyze_event.call_args.args) > 1
        else "",
    )
    assert "capacity project" in event_arg or "BioGenix" in event_arg

    # Verify WebSocket alert was sent with high severity
    ws_manager.send_signal.assert_called_once()
    ws_call = ws_manager.send_signal.call_args.kwargs
    assert ws_call["severity"] == "high"
    assert "BioGenix" in ws_call["title"]
    assert ws_call["data"]["combined_score"] >= 0.6

    # Verify ProactiveRouter was called for offline delivery
    proactive_router.route.assert_called_once()

    # Verify result contains the implication
    assert len(result) == 1
    assert result[0].combined_score >= 0.6
