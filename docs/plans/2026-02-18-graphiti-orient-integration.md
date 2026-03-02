# Graphiti Knowledge Graph in OODA Orient — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire Graphiti knowledge graph traversal into OODA Orient for multi-hop implication reasoning, proactive signal analysis, and meeting prep intelligence.

**Architecture:** Three-layer integration: (1) Orient always gets entity graph context via ColdMemoryRetriever before its LLM call; (2) Scout signals flow through ImplicationEngine for full causal chain reasoning then push via WebSocket; (3) Meeting briefs query Graphiti for attendee relationship intelligence. Each layer is independently testable.

**Tech Stack:** Python 3.11+ / FastAPI / asyncio / Graphiti (Neo4j) / Supabase / WebSocket ConnectionManager

---

## Task 1: Extract Entities from OODA Observations

**Files:**
- Create: `backend/src/core/entity_extractor.py`
- Test: `backend/tests/test_entity_extractor.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_entity_extractor.py
"""Tests for entity extraction from OODA observations."""

import pytest

from src.core.entity_extractor import extract_entities_from_observations


class TestExtractEntities:
    """Tests for extract_entities_from_observations."""

    def test_extracts_company_from_hot_context(self) -> None:
        observations = [
            {
                "source": "hot_context",
                "type": "hot",
                "data": "User: Sarah Chen, VP Sales at Meridian Pharma\nActive Goal: Close BioGenix deal",
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "BioGenix" in entities
        assert "Meridian Pharma" in entities

    def test_extracts_company_from_cold_memory(self) -> None:
        observations = [
            {
                "source": "semantic",
                "type": "cold",
                "data": {
                    "content": "Novartis acquired GenMark Diagnostics for $1.8B",
                    "relevance_score": 0.85,
                },
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "Novartis" in entities

    def test_extracts_from_goal_text(self) -> None:
        observations = [
            {
                "source": "working",
                "type": "conversation",
                "data": {"messages": [{"content": "Update on the WuXi proposal"}]},
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "WuXi" in entities

    def test_deduplicates_entities(self) -> None:
        observations = [
            {"source": "hot_context", "type": "hot", "data": "BioGenix deal update"},
            {"source": "semantic", "type": "cold", "data": {"content": "BioGenix pipeline review"}},
        ]
        entities = extract_entities_from_observations(observations)
        assert entities.count("BioGenix") == 1

    def test_limits_to_max_entities(self) -> None:
        observations = [
            {
                "source": "hot_context",
                "type": "hot",
                "data": "Companies: Alpha Corp, Beta Inc, Gamma Ltd, Delta Co, Epsilon Pharma, Zeta Bio, Eta Labs, Theta Med",
            }
        ]
        entities = extract_entities_from_observations(observations, max_entities=5)
        assert len(entities) <= 5

    def test_returns_empty_for_no_observations(self) -> None:
        assert extract_entities_from_observations([]) == []

    def test_handles_malformed_observations(self) -> None:
        observations = [
            {"source": "hot_context", "type": "hot", "data": None},
            {"source": "cold", "type": "cold", "data": 42},
        ]
        # Should not raise
        entities = extract_entities_from_observations(observations)
        assert isinstance(entities, list)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_entity_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.entity_extractor'`

**Step 3: Write minimal implementation**

```python
# backend/src/core/entity_extractor.py
"""Extract entity names from OODA observations for graph traversal.

Uses regex-based extraction to identify company and person names
from structured observation data without LLM calls.
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Patterns for company name suffixes
_COMPANY_SUFFIXES = r"(?:Inc|Corp|Ltd|Co|Pharma|Bio|Labs|Med|Therapeutics|Sciences|Diagnostics|Healthcare)"

# Pattern: Capitalized multi-word phrases that look like entity names
# Matches "BioGenix", "Meridian Pharma", "WuXi AppTec", etc.
_ENTITY_PATTERN = re.compile(
    rf"\b([A-Z][a-zA-Z]*(?:\s+(?:[A-Z][a-zA-Z]*|{_COMPANY_SUFFIXES})){{0,3}})\b"
)

# Words to exclude (common English words that match the pattern)
_STOP_WORDS = frozenset({
    "The", "This", "That", "These", "Those", "With", "From", "Into",
    "About", "After", "Before", "Between", "Under", "Over", "Through",
    "During", "Without", "Within", "Along", "Among", "Upon", "Since",
    "Until", "Against", "Toward", "Active", "Goal", "User", "Status",
    "Type", "Data", "Source", "None", "True", "False", "Note", "Update",
    "Recent", "Current", "New", "Other", "First", "Last", "Next",
    "Meeting", "Email", "Call", "Task", "Plan", "Report", "Summary",
    "Description", "Title", "Priority", "High", "Medium", "Low",
    "Unknown", "Analyzed", "Gathered", "Focus", "Observations",
    "Output", "JSON", "ARIA", "Claude",
})


def extract_entities_from_observations(
    observations: list[dict[str, Any]],
    max_entities: int = 5,
) -> list[str]:
    """Extract entity names from OODA observations.

    Scans observation text for company and person names using
    regex patterns. No LLM calls — purely pattern-based.

    Args:
        observations: List of observation dicts from OODA Observe phase.
        max_entities: Maximum entities to return (bounds graph queries).

    Returns:
        Deduplicated list of entity name strings, most-mentioned first.
    """
    if not observations:
        return []

    # Collect all text from observations
    text_parts: list[str] = []
    for obs in observations:
        _collect_text(obs.get("data"), text_parts)

    if not text_parts:
        return []

    combined_text = " ".join(text_parts)

    # Extract candidates
    candidates: dict[str, int] = {}
    for match in _ENTITY_PATTERN.finditer(combined_text):
        name = match.group(1).strip()
        if name in _STOP_WORDS or len(name) < 3:
            continue
        # Skip single common words (must be multi-word OR have special casing like "BioGenix")
        if " " not in name and name[0].isupper() and name[1:].islower() and len(name) < 6:
            continue
        candidates[name] = candidates.get(name, 0) + 1

    # Sort by frequency (most-mentioned first), then alphabetically
    sorted_entities = sorted(candidates.keys(), key=lambda e: (-candidates[e], e))

    return sorted_entities[:max_entities]


def _collect_text(data: Any, parts: list[str]) -> None:
    """Recursively extract text strings from observation data."""
    if data is None:
        return
    if isinstance(data, str):
        parts.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            _collect_text(value, parts)
    elif isinstance(data, list):
        for item in data:
            _collect_text(item, parts)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_entity_extractor.py -v`
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add backend/src/core/entity_extractor.py backend/tests/test_entity_extractor.py
git commit -m "feat: add entity extractor for OODA graph traversal"
```

---

## Task 2: Wire Graph Context into OODA Orient

**Files:**
- Modify: `backend/src/core/ooda.py` (Orient phase, lines ~393-563)
- Test: `backend/tests/test_ooda_graph_orient.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_ooda_graph_orient.py
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
        messages = call_args.kwargs.get("messages", call_args.args[0])
        user_msg = messages[0]["content"]
        assert "Knowledge Graph Context" in user_msg or "Graph" in user_msg

    @pytest.mark.asyncio
    async def test_orient_parses_implication_chains(self) -> None:
        """Orient should parse implication_chains from LLM response."""
        chains = [
            {
                "signal": "VP resigned",
                "chain": "leadership gap → delay → competitor opportunity",
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
        llm = AsyncMock()
        llm.generate_response = AsyncMock(
            return_value=_make_orient_response()
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_ooda_graph_orient.py -v`
Expected: FAIL — tests expecting graph behavior that doesn't exist yet in orient()

**Step 3: Modify ooda.py Orient phase**

In `backend/src/core/ooda.py`, modify the `orient` method. Insert graph context retrieval between the observation summary construction (line 415) and the LLM call (line 468).

Changes to make:

1. **After line 415** (`observations_summary = json.dumps(...)`), add graph context retrieval:

```python
        # --- Graph context enrichment ---
        graph_context_str = ""
        if self._cold_memory_retriever is not None:
            try:
                graph_context_str = await self._get_graph_context_for_orient(
                    state.observations, user_id
                )
            except Exception as e:
                logger.warning("Graph context retrieval failed in orient: %s", e)
```

2. **Modify the hardcoded system prompt** (line 417) to include graph reasoning instructions:

Replace the existing hardcoded_system_prompt with:

```python
        hardcoded_system_prompt = """You are ARIA's cognitive analysis module. Analyze the observations and produce a structured analysis.

When Knowledge Graph Context is provided, look for non-obvious connections between entities.
If Company A just lost a key executive AND Company B is expanding in that space AND
we have an active opportunity with Company A — that's an implication chain the user needs to know about.

Output ONLY valid JSON with this structure:
{
    "patterns": ["list of patterns identified"],
    "opportunities": ["list of opportunities to pursue the goal"],
    "threats": ["list of obstacles or risks"],
    "recommended_focus": "single most important area to focus on",
    "implication_chains": [
        {
            "signal": "what triggered this chain",
            "chain": "A → B → C causal connection",
            "implication": "what this means for the user",
            "urgency": "high | medium | low"
        }
    ]
}

The implication_chains array can be empty if no multi-hop connections are found."""
```

3. **Modify the user prompt** (line 446) to include graph context:

```python
        user_prompt = f"""Goal: {goal.get("title", "Unknown")}
Description: {goal.get("description", "No description")}

Observations:
{observations_summary}
"""
        if graph_context_str:
            user_prompt += f"""
Knowledge Graph Context (entity relationships and history):
{graph_context_str}
"""
        user_prompt += """
Analyze these observations and identify patterns, opportunities, and threats relevant to achieving the goal.
If graph context is available, identify implication chains — non-obvious multi-hop connections between entities."""
```

4. **Add the helper method** to the OODALoop class (after the orient method):

```python
    async def _get_graph_context_for_orient(
        self,
        observations: list[dict[str, Any]],
        user_id: str,
    ) -> str:
        """Extract entities from observations and retrieve graph context.

        Args:
            observations: OODA observations from Observe phase.
            user_id: User ID for scoped graph queries.

        Returns:
            Formatted string of graph context for the Orient prompt.
        """
        if self._cold_memory_retriever is None:
            return ""

        from src.core.entity_extractor import extract_entities_from_observations

        entities = extract_entities_from_observations(observations, max_entities=5)
        if not entities:
            return ""

        # Query graph for each entity in parallel
        import asyncio

        tasks = [
            self._cold_memory_retriever.retrieve_for_entity(
                user_id=user_id,
                entity_id=entity,
                hops=3,
            )
            for entity in entities
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        parts: list[str] = []
        for entity, result in zip(entities, results):
            if isinstance(result, BaseException):
                logger.warning("Graph retrieval failed for %s: %s", entity, result)
                continue

            section_lines: list[str] = [f"### {entity}"]
            if result.direct_facts:
                section_lines.append("Facts:")
                for fact in result.direct_facts[:3]:
                    section_lines.append(f"  - {fact.content}")
            if result.relationships:
                section_lines.append("Relationships:")
                for rel in result.relationships[:3]:
                    section_lines.append(f"  - {rel.content}")
            if result.recent_interactions:
                section_lines.append("Recent Interactions:")
                for interaction in result.recent_interactions[:3]:
                    section_lines.append(f"  - {interaction.content}")

            if len(section_lines) > 1:  # More than just the header
                parts.append("\n".join(section_lines))

        return "\n\n".join(parts) if parts else ""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_ooda_graph_orient.py -v`
Expected: PASS (all 4 tests)

**Step 5: Run existing OODA tests to confirm no regression**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_ooda.py backend/tests/test_ooda_enhanced.py -v`
Expected: PASS (all existing tests still pass)

**Step 6: Commit**

```bash
git add backend/src/core/ooda.py backend/tests/test_ooda_graph_orient.py
git commit -m "feat: wire graph context into OODA Orient for multi-hop reasoning"
```

---

## Task 3: Proactive Signal Analysis Service

**Files:**
- Create: `backend/src/services/signal_orient.py`
- Test: `backend/tests/test_signal_orient.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_signal_orient.py
"""Tests for signal-to-orient graph analysis pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
        {"source_entity": "BioGenix", "target_entity": "capacity_project", "relationship": "delays"},
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
        cold_retriever.retrieve_for_entity = AsyncMock(
            side_effect=Exception("Neo4j down")
        )

        implication_engine = AsyncMock()
        implication_engine.analyze_event = AsyncMock(return_value=[_make_implication()])

        ws_manager = AsyncMock()
        proactive_router = AsyncMock()
        proactive_router.route = AsyncMock(return_value={"channel": "notification"})

        # Should still work — graph failure is non-fatal
        result = await analyze_signal_with_graph(
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_signal_orient.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.signal_orient'`

**Step 3: Write minimal implementation**

```python
# backend/src/services/signal_orient.py
"""Signal-to-Orient graph analysis pipeline.

Enriches detected signals with knowledge graph context and
runs implication analysis to surface proactive intelligence.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum combined_score for an implication to be routed to the user
ALERT_THRESHOLD = 0.6


def _score_to_severity(score: float) -> str:
    """Map combined_score to WebSocket severity level."""
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


async def analyze_signal_with_graph(
    user_id: str,
    signal: dict[str, Any],
    cold_retriever: Any,
    implication_engine: Any,
    ws_manager: Any,
    proactive_router: Any,
) -> list[Any]:
    """Analyze a signal with graph context and route implications.

    Pipeline:
    1. Extract entity from signal (company_name)
    2. Query graph neighborhood via ColdMemoryRetriever
    3. Run ImplicationEngine.analyze_event() for causal chain reasoning
    4. Filter by score threshold
    5. Push high-score implications via WebSocket + ProactiveRouter

    Args:
        user_id: The user to analyze for.
        signal: Signal dict with company_name, signal_type, headline, etc.
        cold_retriever: ColdMemoryRetriever instance.
        implication_engine: ImplicationEngine instance.
        ws_manager: WebSocket ConnectionManager for real-time alerts.
        proactive_router: ProactiveRouter for offline delivery.

    Returns:
        List of implications that met the alert threshold.
    """
    company = signal.get("company_name", "")
    headline = signal.get("headline", "")
    signal_type = signal.get("signal_type", "unknown")

    # Step 1: Get graph context for the signal's company
    graph_context_str = ""
    try:
        entity_ctx = await cold_retriever.retrieve_for_entity(
            user_id=user_id,
            entity_id=company,
            hops=3,
        )
        if entity_ctx:
            parts: list[str] = []
            for fact in getattr(entity_ctx, "direct_facts", [])[:5]:
                parts.append(f"Fact: {fact.content}")
            for rel in getattr(entity_ctx, "relationships", [])[:5]:
                parts.append(f"Relationship: {rel.content}")
            for interaction in getattr(entity_ctx, "recent_interactions", [])[:3]:
                parts.append(f"Recent: {interaction.content}")
            graph_context_str = "\n".join(parts)
    except Exception as e:
        logger.warning("Graph retrieval failed for signal company %s: %s", company, e)

    # Step 2: Run implication analysis
    event_description = f"{headline}"
    if graph_context_str:
        event_description += f"\n\nGraph context:\n{graph_context_str}"

    try:
        implications = await implication_engine.analyze_event(
            user_id=user_id,
            event=event_description,
            max_hops=4,
        )
    except Exception as e:
        logger.error("Implication analysis failed for signal: %s", e)
        return []

    # Step 3: Filter by threshold
    actionable = [impl for impl in implications if impl.combined_score >= ALERT_THRESHOLD]

    if not actionable:
        return []

    # Step 4: Route the top implication
    top = actionable[0]
    severity = _score_to_severity(top.combined_score)

    # WebSocket push
    try:
        await ws_manager.send_signal(
            user_id=user_id,
            signal_type=f"implication.{signal_type}",
            title=f"{headline}: {top.content[:100]}",
            severity=severity,
            data={
                "original_signal": signal,
                "implication": top.content,
                "causal_chain": top.causal_chain,
                "recommended_actions": top.recommended_actions,
                "combined_score": top.combined_score,
                "graph_context_available": bool(graph_context_str),
            },
        )
    except Exception as e:
        logger.warning("WebSocket signal push failed: %s", e)

    # ProactiveRouter for offline delivery
    try:
        from src.services.proactive_router import InsightCategory, InsightPriority

        priority = InsightPriority.HIGH if severity == "high" else InsightPriority.MEDIUM

        await proactive_router.route(
            user_id=user_id,
            priority=priority,
            category=InsightCategory.MARKET_SIGNAL,
            title=headline,
            message=top.content,
            metadata={
                "signal_type": signal_type,
                "company": company,
                "combined_score": top.combined_score,
                "recommended_actions": top.recommended_actions,
            },
        )
    except Exception as e:
        logger.warning("ProactiveRouter delivery failed: %s", e)

    return actionable
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_signal_orient.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add backend/src/services/signal_orient.py backend/tests/test_signal_orient.py
git commit -m "feat: add signal-to-orient graph analysis pipeline"
```

---

## Task 4: Meeting Brief Graph Intelligence

**Files:**
- Modify: `backend/src/services/meeting_brief.py`
- Test: `backend/tests/test_meeting_brief_graph.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_meeting_brief_graph.py
"""Tests for graph-enriched meeting briefs."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.meeting_brief import MeetingBriefService


def _mock_db_chain(data: list | dict | None = None) -> MagicMock:
    """Build a chainable Supabase mock."""
    chain = MagicMock()
    for method in ("select", "eq", "gte", "lte", "order", "limit", "single", "insert", "update", "upsert"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = MagicMock(data=data)
    return chain


def _make_entity_context(entity_id: str) -> MagicMock:
    ctx = MagicMock()
    ctx.entity_id = entity_id
    ctx.direct_facts = [MagicMock(content=f"{entity_id} is expanding in oncology")]
    ctx.relationships = [MagicMock(content=f"{entity_id} partners with Roche")]
    ctx.recent_interactions = [MagicMock(content=f"Called {entity_id} VP last week")]
    return ctx


class TestMeetingBriefGraphIntelligence:
    """Tests that meeting briefs include graph context."""

    @pytest.mark.asyncio
    async def test_build_brief_context_includes_relationship_intelligence(self) -> None:
        """Brief context should include graph relationship data when available."""
        with patch("src.services.meeting_brief.SupabaseClient") as mock_db_cls:
            mock_db = MagicMock()
            mock_db.table.return_value = _mock_db_chain()
            mock_db_cls.get_client.return_value = mock_db

            service = MeetingBriefService()

            brief = {
                "meeting_title": "Q3 Pipeline Review",
                "meeting_time": "2026-02-20T14:00:00Z",
                "attendees": ["john@biogenix.com"],
            }
            attendee_profiles = {
                "john@biogenix.com": {
                    "name": "John Smith",
                    "title": "VP Sales",
                    "company": "BioGenix",
                },
            }
            company_signals = [
                {"company_name": "BioGenix", "headline": "New funding round"},
            ]
            graph_contexts = {
                "BioGenix": _make_entity_context("BioGenix"),
                "John Smith": _make_entity_context("John Smith"),
            }

            context = service._build_brief_context(
                brief, attendee_profiles, company_signals, graph_contexts
            )

            assert "Relationship Intelligence" in context
            assert "BioGenix" in context
            assert "partners with Roche" in context or "expanding in oncology" in context

    @pytest.mark.asyncio
    async def test_build_brief_context_works_without_graph(self) -> None:
        """Brief context should work when no graph data is available."""
        with patch("src.services.meeting_brief.SupabaseClient") as mock_db_cls:
            mock_db = MagicMock()
            mock_db.table.return_value = _mock_db_chain()
            mock_db_cls.get_client.return_value = mock_db

            service = MeetingBriefService()

            brief = {
                "meeting_title": "Sync",
                "meeting_time": "2026-02-20T14:00:00Z",
                "attendees": [],
            }

            context = service._build_brief_context(brief, {}, [], {})

            assert "Meeting Title: Sync" in context
            # Should not have graph section when no graph data
            assert "Relationship Intelligence" not in context
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_meeting_brief_graph.py -v`
Expected: FAIL — `_build_brief_context()` doesn't accept `graph_contexts` parameter yet

**Step 3: Modify meeting_brief.py**

Two changes:

**A. Update `_build_brief_context` signature and body** (line 370):

Replace the existing `_build_brief_context` method with:

```python
    def _build_brief_context(
        self,
        brief: dict[str, Any],
        attendee_profiles: dict[str, dict[str, Any]],
        company_signals: list[dict[str, Any]],
        graph_contexts: dict[str, Any] | None = None,
    ) -> str:
        """Build context string for Claude to generate the brief.

        Args:
            brief: The meeting brief data.
            attendee_profiles: Dict of attendee email to profile data.
            company_signals: List of company signals from Scout.
            graph_contexts: Optional dict of entity_id to EntityContext from Graphiti.

        Returns:
            Formatted context string for the LLM.
        """
        context_parts = [
            "Generate a pre-meeting brief for the following meeting.",
            "Return a JSON object with 'summary', 'suggested_agenda', 'risks_opportunities', and 'hidden_connections'.",
            "The 'hidden_connections' field should contain non-obvious relationships between attendees,",
            "companies, and the user's current deals that might be relevant.",
            "",
            f"Meeting Title: {brief.get('meeting_title', 'Unknown')}",
            f"Meeting Time: {brief.get('meeting_time', 'Unknown')}",
            "",
            "Attendees:",
        ]

        for email, profile in attendee_profiles.items():
            name = profile.get("name", email)
            title = profile.get("title", "Unknown")
            company = profile.get("company", "Unknown")
            context_parts.append(f"- {name} ({title} at {company})")

        if not attendee_profiles:
            for email in brief.get("attendees", []):
                context_parts.append(f"- {email}")

        if company_signals:
            context_parts.append("")
            context_parts.append("Recent Company News/Signals:")
            for signal in company_signals[:5]:
                headline = signal.get("headline", "")
                company_name = signal.get("company_name", "")
                context_parts.append(f"- {company_name}: {headline}")

        # Graph relationship intelligence
        if graph_contexts:
            has_content = False
            graph_parts: list[str] = ["", "Relationship Intelligence (from knowledge graph):"]
            for entity_id, ctx in graph_contexts.items():
                entity_lines: list[str] = []
                for fact in getattr(ctx, "direct_facts", [])[:3]:
                    entity_lines.append(f"  - {fact.content}")
                for rel in getattr(ctx, "relationships", [])[:3]:
                    entity_lines.append(f"  - {rel.content}")
                for interaction in getattr(ctx, "recent_interactions", [])[:2]:
                    entity_lines.append(f"  - {interaction.content}")
                if entity_lines:
                    has_content = True
                    graph_parts.append(f"  {entity_id}:")
                    graph_parts.extend(entity_lines)
            if has_content:
                context_parts.extend(graph_parts)

        return "\n".join(context_parts)
```

**B. Update `generate_brief_content`** to query Graphiti before calling Claude.

After the Scout agent research (line 290), add graph retrieval:

```python
            # Step 4b: Get graph context for attendees and companies
            graph_contexts: dict[str, Any] = {}
            if self._cold_retriever is not None:
                entities_to_query = list(companies)
                for profile in attendee_profiles.values():
                    name = profile.get("name")
                    if name:
                        entities_to_query.append(name)

                import asyncio

                graph_tasks = [
                    self._cold_retriever.retrieve_for_entity(
                        user_id=user_id, entity_id=entity, hops=3,
                    )
                    for entity in entities_to_query[:8]  # Limit to 8 entities
                ]
                results = await asyncio.gather(*graph_tasks, return_exceptions=True)
                for entity, result in zip(entities_to_query[:8], results):
                    if not isinstance(result, BaseException):
                        graph_contexts[entity] = result
```

Also update the `__init__` to accept an optional cold_retriever:

```python
    def __init__(self, cold_retriever: Any | None = None) -> None:
        """Initialize meeting brief service.

        Args:
            cold_retriever: Optional ColdMemoryRetriever for graph intelligence.
        """
        self._db = SupabaseClient.get_client()
        self._cold_retriever = cold_retriever
```

And update the `_build_brief_context` call (line 293):

```python
            context = self._build_brief_context(brief, attendee_profiles, company_signals, graph_contexts)
```

Update the brief_content dict to include hidden_connections:

```python
            brief_content: dict[str, Any] = {
                "summary": llm_output.get("summary", ""),
                "suggested_agenda": llm_output.get("suggested_agenda", []),
                "risks_opportunities": llm_output.get("risks_opportunities", []),
                "hidden_connections": llm_output.get("hidden_connections", []),
                "attendee_profiles": attendee_profiles,
                "company_signals": company_signals,
            }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_meeting_brief_graph.py -v`
Expected: PASS (both tests)

**Step 5: Run existing meeting brief tests for regression**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_meeting_brief_service.py backend/tests/test_models_meeting_brief.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/services/meeting_brief.py backend/tests/test_meeting_brief_graph.py
git commit -m "feat: add graph relationship intelligence to meeting briefs"
```

---

## Task 5: Integration Test — Signal Triggers Graph Traversal + Implication Detection

**Files:**
- Create: `backend/tests/integration/test_signal_graph_integration.py`

**Step 1: Write the integration test**

```python
# backend/tests/integration/test_signal_graph_integration.py
"""Integration test: signal → graph traversal → implication detection → WebSocket."""

import pytest
from unittest.mock import AsyncMock, MagicMock

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
    """Full pipeline: signal detected → graph queried → implications found → alert sent."""
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
        "event", implication_engine.analyze_event.call_args.args[1] if len(implication_engine.analyze_event.call_args.args) > 1 else ""
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
```

**Step 2: Run the integration test**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/integration/test_signal_graph_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/integration/test_signal_graph_integration.py
git commit -m "test: add integration test for signal → graph → implication pipeline"
```

---

## Task 6: Run Full Test Suite and Fix Any Regressions

**Files:**
- May modify: any files with test failures

**Step 1: Run the full relevant test suite**

```bash
cd /Users/dhruv/aria && python -m pytest \
  backend/tests/test_entity_extractor.py \
  backend/tests/test_ooda_graph_orient.py \
  backend/tests/test_signal_orient.py \
  backend/tests/test_meeting_brief_graph.py \
  backend/tests/integration/test_signal_graph_integration.py \
  backend/tests/test_ooda.py \
  backend/tests/test_ooda_enhanced.py \
  backend/tests/test_cold_retrieval.py \
  backend/tests/test_meeting_brief_service.py \
  -v --tb=short 2>&1 | head -100
```

Expected: All tests PASS

**Step 2: Run ruff check on new/modified files**

```bash
cd /Users/dhruv/aria && python -m ruff check \
  backend/src/core/entity_extractor.py \
  backend/src/core/ooda.py \
  backend/src/services/signal_orient.py \
  backend/src/services/meeting_brief.py
```

Fix any linting errors.

**Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address test regressions and lint errors from graph integration"
```
