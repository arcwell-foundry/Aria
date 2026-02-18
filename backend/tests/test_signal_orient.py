"""Tests for signal-to-orient graph analysis pipeline."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.signal_orient import analyze_signal_with_graph


def _make_signal() -> dict:
    return {
        "company_name": "BioGenix",
        "signal_type": "leadership_change",
        "headline": "BioGenix VP Manufacturing Resigns",
        "summary": "Key leadership departure amid capacity expansion",
        "relevance_score": 0.85,
        "detected_at": "2026-02-18T10:00:00Z",
    }


def _make_entity_context() -> MagicMock:
    ctx = MagicMock()
    ctx.direct_facts = [
        MagicMock(content="BioGenix has capacity project targeting Q3"),
    ]
    ctx.relationships = [
        MagicMock(content="BioGenix competes with WuXi in CDMO space"),
    ]
    ctx.recent_interactions = [
        MagicMock(content="Proposal sent to BioGenix last week"),
    ]
    ctx.to_dict.return_value = {
        "entity_id": "BioGenix",
        "direct_facts": [{"content": "BioGenix has capacity project targeting Q3"}],
        "relationships": [{"content": "BioGenix competes with WuXi in CDMO space"}],
        "recent_interactions": [{"content": "Proposal sent to BioGenix last week"}],
    }
    return ctx


def _make_implication() -> MagicMock:
    impl = MagicMock()
    impl.combined_score = 0.75
    impl.type = MagicMock(value="threat")
    impl.content = "Leadership gap may delay capacity project"
    impl.trigger_event = "BioGenix VP Manufacturing Resigns"
    impl.recommended_actions = ["Accelerate proposal"]
    impl.causal_chain = [
        {
            "source_entity": "BioGenix",
            "target_entity": "capacity_project",
            "relationship": "delays",
        },
    ]
    return impl


class TestAnalyzeSignalWithGraph:
    """Tests for the signal analysis pipeline."""

    @pytest.mark.asyncio
    async def test_queries_graph_for_signal_company(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(return_value=_make_entity_context())

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[_make_implication()])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()
        proactive_router.route = AsyncMock(return_value={"channel": "websocket"})

        result = await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        cold_retriever.retrieve_for_entity.assert_called_once_with(
            user_id="user-123",
            entity_id="BioGenix",
            hops=3,
        )
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_sends_websocket_for_high_score_implications(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(return_value=_make_entity_context())

        high_score_impl = _make_implication()
        high_score_impl.combined_score = 0.8

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[high_score_impl])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()
        proactive_router.route = AsyncMock(return_value={"channel": "websocket"})

        await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        ws_manager.send_signal.assert_called_once()
        call_kwargs = ws_manager.send_signal.call_args.kwargs
        assert call_kwargs["severity"] == "high"

    @pytest.mark.asyncio
    async def test_routes_through_proactive_router(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(return_value=_make_entity_context())

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[_make_implication()])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()
        proactive_router.route = AsyncMock(return_value={"channel": "websocket"})

        await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        proactive_router.route.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_low_score_implications(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(return_value=_make_entity_context())

        low_impl = _make_implication()
        low_impl.combined_score = 0.3

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[low_impl])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()

        result = await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        ws_manager.send_signal.assert_not_called()
        proactive_router.route.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_graph_failure_gracefully(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(side_effect=Exception("Neo4j down"))

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[_make_implication()])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()
        proactive_router.route = AsyncMock(return_value={"channel": "notification"})

        # Should still work --- graph failure is non-fatal
        await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        # ImplicationEngine should still be called even without graph context
        implication_engine.analyze_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_implications_returns_empty(self) -> None:
        cold_retriever = AsyncMock()
        cold_retriever.retrieve_for_entity = AsyncMock(return_value=_make_entity_context())

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()

        result = await analyze_signal_with_graph(
            user_id="user-123",
            signal=_make_signal(),
            cold_retriever=cold_retriever,
            implication_engine=implication_engine,
            ws_manager=ws_manager,
            proactive_router=proactive_router,
        )

        assert result == []
        ws_manager.send_signal.assert_not_called()
