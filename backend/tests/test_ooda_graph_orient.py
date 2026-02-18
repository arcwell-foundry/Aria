"""Tests for graph-enriched OODA Orient phase."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.ooda import OODALoop, OODAPhase, OODAState
from src.memory.cold_retrieval import ColdMemoryResult, EntityContext, MemorySource


def _make_working_memory(user_id: str = "user-123") -> MagicMock:
    wm = MagicMock()
    wm.user_id = user_id
    wm.get_context_for_llm.return_value = {"messages": []}
    return wm


def _make_entity_context(entity_id: str) -> EntityContext:
    return EntityContext(
        entity_id=entity_id,
        direct_facts=[
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content=f"{entity_id} has 500 employees",
                relevance_score=0.8,
            )
        ],
        relationships=[
            ColdMemoryResult(
                source=MemorySource.SEMANTIC,
                content=f"{entity_id} competes with Novartis in oncology",
                relevance_score=0.7,
            )
        ],
        recent_interactions=[
            ColdMemoryResult(
                source=MemorySource.EPISODIC,
                content=f"Met with {entity_id} VP Sales last Tuesday",
                relevance_score=0.9,
            )
        ],
    )


def _make_orient_response(
    patterns: list[str] | None = None,
    implication_chains: list[dict] | None = None,
) -> str:
    return json.dumps({
        "patterns": patterns or ["graph-derived pattern"],
        "opportunities": ["leverage relationship"],
        "threats": [],
        "recommended_focus": "capitalize on connection",
        "implication_chains": implication_chains or [],
    })


class TestOrientGraphEnrichment:
    """Tests that Orient phase queries graph context."""

    @pytest.mark.asyncio
    async def test_orient_calls_retrieve_for_entity(self) -> None:
        """Orient should call retrieve_for_entity for extracted entities."""
        llm = AsyncMock()
        llm.generate_response_with_thinking = AsyncMock(
            return_value=MagicMock(
                text=_make_orient_response(),
                thinking="deep analysis",
                usage=MagicMock(total_tokens=1000),
            )
        )
        llm.generate_response = AsyncMock(return_value=_make_orient_response())

        cold_retriever = AsyncMock()
        cold_retriever.retrieve = AsyncMock(return_value=[])
        cold_retriever.retrieve_for_entity = AsyncMock(
            return_value=_make_entity_context("BioGenix")
        )

        wm = _make_working_memory()
        loop = OODALoop(
            llm_client=llm,
            episodic_memory=AsyncMock(),
            semantic_memory=AsyncMock(),
            working_memory=wm,
            cold_memory_retriever=cold_retriever,
            user_id="user-123",
        )

        state = OODAState(goal_id="goal-1")
        state.observations = [
            {
                "source": "hot_context",
                "type": "hot",
                "data": "Active Goal: Close BioGenix deal",
            }
        ]
        state.current_phase = OODAPhase.ORIENT

        goal = {"title": "Close BioGenix deal", "description": "Q3 target"}

        result = await loop.orient(state, goal)

        # Verify graph traversal was attempted
        cold_retriever.retrieve_for_entity.assert_called()
        call_args = cold_retriever.retrieve_for_entity.call_args
        assert call_args.kwargs.get("hops", call_args.args[2] if len(call_args.args) > 2 else 2) >= 2

    @pytest.mark.asyncio
    async def test_orient_includes_graph_in_prompt(self) -> None:
        """Orient LLM call should include graph context in prompt."""
        llm = AsyncMock()
        response_text = _make_orient_response()
        llm.generate_response = AsyncMock(return_value=response_text)
        llm.generate_response_with_thinking = AsyncMock(
            return_value=MagicMock(
                text=response_text,
                thinking=None,
                usage=MagicMock(total_tokens=500),
            )
        )

        cold_retriever = AsyncMock()
        cold_retriever.retrieve = AsyncMock(return_value=[])
        cold_retriever.retrieve_for_entity = AsyncMock(
            return_value=_make_entity_context("BioGenix")
        )

        wm = _make_working_memory()
        loop = OODALoop(
            llm_client=llm,
            episodic_memory=AsyncMock(),
            semantic_memory=AsyncMock(),
            working_memory=wm,
            cold_memory_retriever=cold_retriever,
            user_id="user-123",
        )

        state = OODAState(goal_id="goal-1")
        state.observations = [
            {"source": "hot_context", "type": "hot", "data": "BioGenix opportunity active"},
        ]
        state.current_phase = OODAPhase.ORIENT

        await loop.orient(state, {"title": "Close BioGenix deal"})

        # Check the LLM was called and the prompt contains graph context
        call_made = (
            llm.generate_response_with_thinking.called or llm.generate_response.called
        )
        assert call_made

        # Get the user prompt from whichever LLM method was called
        if llm.generate_response_with_thinking.called:
            call_args = llm.generate_response_with_thinking.call_args
        else:
            call_args = llm.generate_response.call_args

        # Extract messages from kwargs or positional args
        if call_args.kwargs and "messages" in call_args.kwargs:
            messages = call_args.kwargs["messages"]
        elif call_args.args:
            messages = call_args.args[0]
        else:
            # Fallback: check all kwargs for any list containing dicts with "content"
            messages = None
            for v in (call_args.kwargs or {}).values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and "content" in v[0]:
                    messages = v
                    break
            assert messages is not None, f"Could not find messages in call_args: {call_args}"

        user_msg = messages[0]["content"]
        assert "Knowledge Graph Context" in user_msg

    @pytest.mark.asyncio
    async def test_orient_parses_implication_chains(self) -> None:
        """Orient should parse implication_chains from LLM response."""
        chains = [
            {
                "signal": "VP resigned",
                "chain": "leadership gap -> delay -> competitor opportunity",
                "implication": "Accelerate proposal",
                "urgency": "high",
            }
        ]
        response_text = _make_orient_response(implication_chains=chains)

        llm = AsyncMock()
        llm.generate_response = AsyncMock(return_value=response_text)

        wm = _make_working_memory()
        loop = OODALoop(
            llm_client=llm,
            episodic_memory=AsyncMock(),
            semantic_memory=AsyncMock(),
            working_memory=wm,
        )

        state = OODAState(goal_id="goal-1")
        state.observations = [{"source": "working", "type": "conversation", "data": "test"}]
        state.current_phase = OODAPhase.ORIENT

        result = await loop.orient(state, {"title": "Test"})
        assert "implication_chains" in result.orientation

    @pytest.mark.asyncio
    async def test_orient_gracefully_handles_graph_failure(self) -> None:
        """Orient should proceed even if graph retrieval fails."""
        response_text = _make_orient_response()
        llm = AsyncMock()
        llm.generate_response = AsyncMock(return_value=response_text)
        llm.generate_response_with_thinking = AsyncMock(
            return_value=MagicMock(
                text=response_text,
                thinking="analysis",
                usage=MagicMock(total_tokens=500),
            )
        )

        cold_retriever = AsyncMock()
        cold_retriever.retrieve = AsyncMock(return_value=[])
        cold_retriever.retrieve_for_entity = AsyncMock(
            side_effect=Exception("Neo4j connection timeout")
        )

        wm = _make_working_memory()
        loop = OODALoop(
            llm_client=llm,
            episodic_memory=AsyncMock(),
            semantic_memory=AsyncMock(),
            working_memory=wm,
            cold_memory_retriever=cold_retriever,
            user_id="user-123",
        )

        state = OODAState(goal_id="goal-1")
        state.observations = [
            {"source": "hot_context", "type": "hot", "data": "BioGenix deal"},
        ]
        state.current_phase = OODAPhase.ORIENT

        # Should not raise
        result = await loop.orient(state, {"title": "Close BioGenix deal"})
        assert result.orientation is not None
        assert result.current_phase == OODAPhase.DECIDE
