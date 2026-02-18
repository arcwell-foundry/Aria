"""Tests for OODA loop enhanced with extended thinking and TaskCharacteristics."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.ooda import OODALoop, OODAPhase, OODAState


def _make_working_memory(user_id: str = "user-123") -> MagicMock:
    """Create a mock working memory."""
    wm = MagicMock()
    wm.user_id = user_id
    wm.get_context_for_llm.return_value = {"messages": []}
    return wm


def _make_loop(
    *,
    user_id: str | None = None,
    hot_context_builder: MagicMock | None = None,
    cold_memory_retriever: MagicMock | None = None,
    cost_governor: MagicMock | None = None,
    llm_response_text: str = '{"patterns":[],"opportunities":[],"threats":[],"recommended_focus":"test"}',
) -> tuple[OODALoop, MagicMock]:
    """Create an OODALoop with mocked dependencies."""
    llm = MagicMock()
    llm.generate_response = AsyncMock(return_value=llm_response_text)

    # Mock generate_response_with_thinking
    from src.core.cost_governor import LLMUsage
    from src.core.llm import LLMResponse

    thinking_resp = LLMResponse(
        text=llm_response_text,
        thinking="Extended thinking trace",
        usage=LLMUsage(input_tokens=100, output_tokens=50, thinking_tokens=200),
    )
    llm.generate_response_with_thinking = AsyncMock(return_value=thinking_resp)

    episodic = MagicMock()
    episodic.semantic_search = AsyncMock(return_value=[])

    semantic = MagicMock()
    semantic.search_facts = AsyncMock(return_value=[])

    working = _make_working_memory()

    loop = OODALoop(
        llm_client=llm,
        episodic_memory=episodic,
        semantic_memory=semantic,
        working_memory=working,
        hot_context_builder=hot_context_builder,
        cold_memory_retriever=cold_memory_retriever,
        cost_governor=cost_governor,
        user_id=user_id,
    )

    return loop, llm


def _make_goal() -> dict:
    return {"id": "goal-1", "title": "Test goal", "description": "Test description"}


# --- OODAState serialization ---


def test_state_serialization_roundtrip() -> None:
    """thinking_traces and task_characteristics survive to_dict/from_dict."""
    state = OODAState(goal_id="g-1")
    state.thinking_traces = {"orient": "thought about it", "decide": "decided carefully"}
    state.task_characteristics = {
        "complexity": 0.5,
        "risk_score": 0.42,
        "thinking_effort": "complex",
    }

    d = state.to_dict()
    assert d["thinking_traces"] == state.thinking_traces
    assert d["task_characteristics"] == state.task_characteristics

    restored = OODAState.from_dict(d)
    assert restored.thinking_traces == state.thinking_traces
    assert restored.task_characteristics == state.task_characteristics


def test_state_defaults_for_new_fields() -> None:
    """New fields default to empty dict and None."""
    state = OODAState(goal_id="g-2")
    assert state.thinking_traces == {}
    assert state.task_characteristics is None


def test_state_from_dict_missing_new_fields() -> None:
    """from_dict gracefully handles missing new fields (backward compat)."""
    data = {
        "goal_id": "g-3",
        "current_phase": "observe",
        "observations": [],
        "orientation": {},
        "iteration": 0,
        "max_iterations": 10,
        "phase_logs": [],
        "is_complete": False,
        "is_blocked": False,
        "total_tokens_used": 0,
    }
    state = OODAState.from_dict(data)
    assert state.thinking_traces == {}
    assert state.task_characteristics is None


# --- OBSERVE phase ---


@pytest.mark.asyncio
async def test_observe_uses_hot_context_when_available() -> None:
    """Hot context builder is called when provided."""
    hot_builder = MagicMock()
    hot_result = MagicMock()
    hot_result.formatted = "hot context data"
    hot_builder.build = AsyncMock(return_value=hot_result)

    loop, _ = _make_loop(hot_context_builder=hot_builder)
    state = OODAState(goal_id="g-1")
    goal = _make_goal()

    state = await loop.observe(state, goal)

    hot_builder.build.assert_called_once()
    hot_obs = [o for o in state.observations if o["type"] == "hot"]
    assert len(hot_obs) == 1
    assert hot_obs[0]["data"] == "hot context data"


@pytest.mark.asyncio
async def test_observe_uses_cold_memory_when_available() -> None:
    """Cold memory retriever is called when provided."""
    cold_retriever = MagicMock()
    cold_result = MagicMock()
    cold_result.source = MagicMock()
    cold_result.source.value = "semantic"
    cold_result.to_dict.return_value = {"fact": "important"}
    cold_retriever.retrieve = AsyncMock(return_value=[cold_result])

    loop, _ = _make_loop(cold_memory_retriever=cold_retriever)
    state = OODAState(goal_id="g-1")
    goal = _make_goal()

    state = await loop.observe(state, goal)

    cold_retriever.retrieve.assert_called_once()
    cold_obs = [o for o in state.observations if o["type"] == "cold"]
    assert len(cold_obs) == 1


@pytest.mark.asyncio
async def test_observe_falls_back_without_builders() -> None:
    """Without hot/cold builders, episodic and semantic memory are used."""
    loop, _ = _make_loop()
    state = OODAState(goal_id="g-1")
    goal = _make_goal()

    state = await loop.observe(state, goal)

    # Should have used episodic and semantic (both return empty in our mock)
    # and working memory context
    working_obs = [o for o in state.observations if o["type"] == "conversation"]
    assert len(working_obs) == 1
    assert state.current_phase == OODAPhase.ORIENT


# --- ORIENT phase ---


@pytest.mark.asyncio
async def test_orient_uses_extended_thinking() -> None:
    """When user_id is set, generate_response_with_thinking is called."""
    loop, llm = _make_loop(user_id="user-123")
    state = OODAState(goal_id="g-1")
    state.observations = [{"source": "test", "type": "test", "data": "data"}]
    goal = _make_goal()

    state = await loop.orient(state, goal)

    llm.generate_response_with_thinking.assert_called_once()
    llm.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_orient_stores_thinking_trace() -> None:
    """state.thinking_traces['orient'] is populated with thinking output."""
    loop, llm = _make_loop(user_id="user-123")
    state = OODAState(goal_id="g-1")
    state.observations = []
    goal = _make_goal()

    state = await loop.orient(state, goal)

    assert "orient" in state.thinking_traces
    assert "Extended thinking trace" in state.thinking_traces["orient"]


@pytest.mark.asyncio
async def test_orient_falls_back_without_user_id() -> None:
    """Without user_id, generate_response with temperature is used."""
    loop, llm = _make_loop(user_id=None)
    state = OODAState(goal_id="g-1")
    state.observations = []
    goal = _make_goal()

    state = await loop.orient(state, goal)

    llm.generate_response.assert_called_once()
    llm.generate_response_with_thinking.assert_not_called()
    # Verify temperature was passed
    call_kwargs = llm.generate_response.call_args.kwargs
    assert call_kwargs.get("temperature") == 0.3


@pytest.mark.asyncio
async def test_orient_cost_governor_downgrades_effort() -> None:
    """Cost governor can downgrade thinking effort in orient."""
    governor = MagicMock()
    budget_status = MagicMock()
    budget_status.can_proceed = True
    budget_status.should_reduce_effort = True
    governor.check_budget = AsyncMock(return_value=budget_status)
    governor.get_thinking_budget.return_value = "routine"

    loop, llm = _make_loop(user_id="user-123", cost_governor=governor)
    state = OODAState(goal_id="g-1")
    state.observations = []
    goal = _make_goal()

    state = await loop.orient(state, goal)

    governor.get_thinking_budget.assert_called()
    call_kwargs = llm.generate_response_with_thinking.call_args.kwargs
    assert call_kwargs["thinking_effort"] == "routine"


# --- DECIDE phase ---


@pytest.mark.asyncio
async def test_decide_produces_task_characteristics() -> None:
    """state.task_characteristics is populated after decide."""
    decide_text = json.dumps({
        "action": "research",
        "agent": "analyst",
        "parameters": {},
        "reasoning": "Need more data",
        "task_characteristics": {
            "complexity": 0.3,
            "criticality": 0.2,
            "uncertainty": 0.4,
            "reversibility": 1.0,
            "verifiability": 0.8,
            "subjectivity": 0.2,
            "contextuality": 0.3,
        },
    })

    from src.core.cost_governor import LLMUsage
    from src.core.llm import LLMResponse

    loop, llm = _make_loop(user_id="user-123")
    # Override decide response
    llm.generate_response_with_thinking = AsyncMock(
        return_value=LLMResponse(
            text=decide_text,
            thinking="Deciding...",
            usage=LLMUsage(input_tokens=100, output_tokens=50),
        )
    )

    state = OODAState(goal_id="g-1")
    state.orientation = {"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "test"}
    goal = _make_goal()

    state = await loop.decide(state, goal)

    assert state.task_characteristics is not None
    assert "risk_score" in state.task_characteristics
    assert "thinking_effort" in state.task_characteristics
    assert state.decision is not None
    assert state.decision["risk_level"] == state.task_characteristics["risk_level"]


@pytest.mark.asyncio
async def test_decide_falls_back_to_defaults() -> None:
    """When LLM doesn't include task_characteristics, defaults are used."""
    decide_text = json.dumps({
        "action": "research",
        "agent": "analyst",
        "parameters": {},
        "reasoning": "Need more data",
    })

    from src.core.cost_governor import LLMUsage
    from src.core.llm import LLMResponse

    loop, llm = _make_loop(user_id="user-123")
    llm.generate_response_with_thinking = AsyncMock(
        return_value=LLMResponse(
            text=decide_text,
            thinking="",
            usage=LLMUsage(input_tokens=100, output_tokens=50),
        )
    )

    state = OODAState(goal_id="g-1")
    state.orientation = {"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "test"}
    goal = _make_goal()

    state = await loop.decide(state, goal)

    assert state.task_characteristics is not None
    # Should have used default_for_action("research")
    assert state.task_characteristics["complexity"] == 0.3  # research default


@pytest.mark.asyncio
async def test_decide_dynamic_thinking_effort() -> None:
    """When orient found threats, decide thinking effort is upgraded to complex."""
    loop, llm = _make_loop(user_id="user-123")
    state = OODAState(goal_id="g-1")
    state.orientation = {
        "patterns": [],
        "opportunities": [],
        "threats": ["competitor launching similar product"],
        "recommended_focus": "competitive response",
    }
    goal = _make_goal()

    await loop.decide(state, goal)

    call_kwargs = llm.generate_response_with_thinking.call_args.kwargs
    assert call_kwargs["thinking_effort"] == "complex"


@pytest.mark.asyncio
async def test_decide_without_user_id_uses_standard_llm() -> None:
    """Without user_id, decide uses generate_response with temperature."""
    decide_text = json.dumps({
        "action": "monitor",
        "agent": "scout",
        "parameters": {},
        "reasoning": "Keep watching",
    })

    loop, llm = _make_loop(user_id=None)
    llm.generate_response = AsyncMock(return_value=decide_text)

    state = OODAState(goal_id="g-1")
    state.orientation = {"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "test"}
    goal = _make_goal()

    state = await loop.decide(state, goal)

    llm.generate_response.assert_called_once()
    llm.generate_response_with_thinking.assert_not_called()
    call_kwargs = llm.generate_response.call_args.kwargs
    assert call_kwargs.get("temperature") == 0.2


# --- Full cycle integration test ---


@pytest.mark.asyncio
async def test_full_ooda_cycle_with_thinking() -> None:
    """Integration: observe -> orient -> decide -> act with all mocks."""
    orient_text = json.dumps({
        "patterns": ["pattern1"],
        "opportunities": ["opportunity1"],
        "threats": [],
        "recommended_focus": "research first",
    })
    decide_text = json.dumps({
        "action": "research",
        "agent": "analyst",
        "parameters": {"query": "test"},
        "reasoning": "Need data",
        "task_characteristics": {
            "complexity": 0.3,
            "criticality": 0.2,
            "uncertainty": 0.4,
            "reversibility": 1.0,
            "verifiability": 0.8,
            "subjectivity": 0.2,
            "contextuality": 0.3,
        },
    })

    from src.core.cost_governor import LLMUsage
    from src.core.llm import LLMResponse

    loop, llm = _make_loop(user_id="user-123")

    # Make orient and decide return different responses
    call_count = 0
    async def mock_thinking(**_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMResponse(text=orient_text, thinking="Orient thinking", usage=LLMUsage())
        else:
            return LLMResponse(text=decide_text, thinking="Decide thinking", usage=LLMUsage())

    llm.generate_response_with_thinking = mock_thinking

    state = OODAState(goal_id="g-1")
    goal = _make_goal()

    # Observe
    state = await loop.observe(state, goal)
    assert state.current_phase == OODAPhase.ORIENT

    # Orient
    state = await loop.orient(state, goal)
    assert state.current_phase == OODAPhase.DECIDE
    assert "orient" in state.thinking_traces

    # Decide
    state = await loop.decide(state, goal)
    assert state.current_phase == OODAPhase.ACT
    assert state.task_characteristics is not None
    assert state.decision is not None
    assert state.decision["action"] == "research"
    assert "decide" in state.thinking_traces

    # Act
    state = await loop.act(state, goal)
    assert state.current_phase == OODAPhase.OBSERVE
    assert state.iteration == 1
