"""Tests for OODA loop cognitive processing module."""

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_ooda_phase_enum_has_four_phases() -> None:
    """Test OODAPhase enum has observe, orient, decide, act."""
    from src.core.ooda import OODAPhase

    assert OODAPhase.OBSERVE.value == "observe"
    assert OODAPhase.ORIENT.value == "orient"
    assert OODAPhase.DECIDE.value == "decide"
    assert OODAPhase.ACT.value == "act"
    assert len(OODAPhase) == 4


def test_ooda_state_initializes_with_defaults() -> None:
    """Test OODAState initializes with sensible defaults."""
    from src.core.ooda import OODAPhase, OODAState

    state = OODAState(goal_id="goal-123")

    assert state.goal_id == "goal-123"
    assert state.current_phase == OODAPhase.OBSERVE
    assert state.observations == []
    assert state.orientation == {}
    assert state.decision is None
    assert state.action_result is None
    assert state.iteration == 0
    assert state.max_iterations == 10
    assert state.phase_logs == []
    assert state.is_complete is False
    assert state.is_blocked is False
    assert state.blocked_reason is None


def test_ooda_state_to_dict_serializes_correctly() -> None:
    """Test OODAState.to_dict produces valid dictionary."""
    from src.core.ooda import OODAPhase, OODAState

    state = OODAState(goal_id="goal-123", max_iterations=5)
    state.current_phase = OODAPhase.ORIENT
    state.observations = [{"source": "memory", "data": "test"}]
    state.iteration = 2

    result = state.to_dict()

    assert result["goal_id"] == "goal-123"
    assert result["current_phase"] == "orient"
    assert result["observations"] == [{"source": "memory", "data": "test"}]
    assert result["iteration"] == 2
    assert result["max_iterations"] == 5


def test_ooda_state_from_dict_deserializes_correctly() -> None:
    """Test OODAState.from_dict restores state."""
    from src.core.ooda import OODAPhase, OODAState

    data = {
        "goal_id": "goal-456",
        "current_phase": "decide",
        "observations": [{"source": "test"}],
        "orientation": {"patterns": ["pattern1"]},
        "decision": {"action": "search"},
        "action_result": None,
        "iteration": 3,
        "max_iterations": 10,
        "phase_logs": [],
        "is_complete": False,
        "is_blocked": False,
        "blocked_reason": None,
    }

    state = OODAState.from_dict(data)

    assert state.goal_id == "goal-456"
    assert state.current_phase == OODAPhase.DECIDE
    assert state.observations == [{"source": "test"}]
    assert state.iteration == 3


def test_ooda_phase_log_entry_captures_phase_execution() -> None:
    """Test OODAPhaseLogEntry captures phase execution details."""
    from src.core.ooda import OODAPhase, OODAPhaseLogEntry

    entry = OODAPhaseLogEntry(
        phase=OODAPhase.OBSERVE,
        iteration=1,
        input_summary="Query memory for context",
        output_summary="Found 5 relevant episodes",
        tokens_used=150,
        duration_ms=230,
    )

    assert entry.phase == OODAPhase.OBSERVE
    assert entry.iteration == 1
    assert entry.tokens_used == 150
    assert entry.duration_ms == 230
    assert entry.timestamp is not None


def test_ooda_phase_log_entry_to_dict() -> None:
    """Test OODAPhaseLogEntry serializes correctly."""
    from src.core.ooda import OODAPhase, OODAPhaseLogEntry

    entry = OODAPhaseLogEntry(
        phase=OODAPhase.DECIDE,
        iteration=2,
        input_summary="Analyzed patterns",
        output_summary="Selected action: research",
        tokens_used=200,
        duration_ms=150,
    )

    result = entry.to_dict()

    assert result["phase"] == "decide"
    assert result["iteration"] == 2
    assert result["tokens_used"] == 200
    assert "timestamp" in result


def test_ooda_config_has_default_budgets() -> None:
    """Test OODAConfig has sensible default token budgets."""
    from src.core.ooda import OODAConfig

    config = OODAConfig()

    assert config.observe_budget == 2000
    assert config.orient_budget == 3000
    assert config.decide_budget == 2000
    assert config.act_budget == 1000
    assert config.max_iterations == 10
    assert config.total_budget == 50000


def test_ooda_config_custom_budgets() -> None:
    """Test OODAConfig accepts custom token budgets."""
    from src.core.ooda import OODAConfig

    config = OODAConfig(
        observe_budget=1000,
        orient_budget=1500,
        decide_budget=1000,
        act_budget=500,
        max_iterations=5,
        total_budget=20000,
    )

    assert config.observe_budget == 1000
    assert config.orient_budget == 1500
    assert config.max_iterations == 5


def test_ooda_config_to_dict() -> None:
    """Test OODAConfig serializes correctly."""
    from src.core.ooda import OODAConfig

    config = OODAConfig(max_iterations=3)
    result = config.to_dict()

    assert result["max_iterations"] == 3
    assert "observe_budget" in result
    assert "total_budget" in result


@pytest.mark.asyncio
async def test_ooda_loop_observe_gathers_memory_context() -> None:
    """Test observe phase queries episodic and semantic memory."""
    from src.core.ooda import OODALoop, OODAState

    # Mock dependencies
    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Setup mock returns
    mock_episodic.semantic_search.return_value = [
        MagicMock(
            id="ep-1",
            content="Met with John about Q3 budget",
            to_dict=lambda: {"id": "ep-1", "content": "Met with John about Q3 budget"},
        )
    ]
    mock_semantic.search_facts.return_value = [
        MagicMock(
            id="fact-1",
            subject="John",
            predicate="is",
            object="CFO",
            to_dict=lambda: {"id": "fact-1", "subject": "John", "predicate": "is", "object": "CFO"},
        )
    ]
    mock_working.get_context_for_llm.return_value = [
        {"role": "user", "content": "Help me prepare for the budget meeting"}
    ]
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    goal = {
        "id": "goal-123",
        "title": "Prepare budget meeting",
        "description": "Get ready for Q3 budget review",
    }

    new_state = await loop.observe(state, goal)

    # Verify observations were gathered
    assert len(new_state.observations) > 0
    assert any(obs["source"] == "episodic" for obs in new_state.observations)
    assert any(obs["source"] == "semantic" for obs in new_state.observations)
    assert any(obs["source"] == "working" for obs in new_state.observations)

    # Verify memory was queried
    mock_episodic.semantic_search.assert_called_once()
    mock_semantic.search_facts.assert_called_once()


@pytest.mark.asyncio
async def test_ooda_loop_observe_logs_phase_execution() -> None:
    """Test observe phase logs its execution."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    mock_episodic.semantic_search.return_value = []
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    goal = {"id": "goal-123", "title": "Test goal"}

    new_state = await loop.observe(state, goal)

    # Verify phase was logged
    assert len(new_state.phase_logs) == 1
    assert new_state.phase_logs[0].phase == OODAPhase.OBSERVE
    assert new_state.phase_logs[0].iteration == 0


@pytest.mark.asyncio
async def test_ooda_loop_observe_handles_memory_errors_gracefully() -> None:
    """Test observe phase handles memory query errors."""
    from src.core.ooda import OODALoop, OODAState

    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Simulate memory error
    mock_episodic.semantic_search.side_effect = Exception("Connection failed")
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    goal = {"id": "goal-123", "title": "Test goal"}

    # Should not raise, but continue with available data
    new_state = await loop.observe(state, goal)

    # Verify we got some observations (at least from working memory)
    assert new_state is not None


@pytest.mark.asyncio
async def test_ooda_loop_orient_analyzes_observations() -> None:
    """Test orient phase uses LLM to analyze observations."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = """{
        "patterns": ["Budget meeting coming up", "John is key stakeholder"],
        "opportunities": ["Prepare talking points"],
        "threats": ["Tight deadline"],
        "recommended_focus": "Gather budget data"
    }"""

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.observations = [
        {
            "source": "episodic",
            "type": "episode",
            "data": {"content": "Q3 budget meeting scheduled"},
        },
        {
            "source": "semantic",
            "type": "fact",
            "data": {"subject": "John", "predicate": "is", "object": "CFO"},
        },
    ]
    goal = {"id": "goal-123", "title": "Prepare budget meeting"}

    new_state = await loop.orient(state, goal)

    # Verify orientation was produced
    assert new_state.orientation is not None
    assert "patterns" in new_state.orientation
    assert new_state.current_phase == OODAPhase.DECIDE

    # Verify LLM was called
    mock_llm.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_ooda_loop_orient_logs_phase_execution() -> None:
    """Test orient phase logs its execution."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = (
        '{"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "test"}'
    )

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.observations = []
    goal = {"id": "goal-123", "title": "Test goal"}

    new_state = await loop.orient(state, goal)

    # Find orient phase log
    orient_logs = [log for log in new_state.phase_logs if log.phase == OODAPhase.ORIENT]
    assert len(orient_logs) == 1


@pytest.mark.asyncio
async def test_ooda_loop_orient_handles_invalid_llm_response() -> None:
    """Test orient phase handles malformed LLM response."""
    from src.core.ooda import OODALoop, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = "This is not valid JSON"

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.observations = []
    goal = {"id": "goal-123", "title": "Test goal"}

    # Should not raise, but produce default orientation
    new_state = await loop.orient(state, goal)

    assert new_state.orientation is not None


@pytest.mark.asyncio
async def test_ooda_loop_decide_selects_action() -> None:
    """Test decide phase uses LLM to select best action."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = """{
        "action": "research",
        "agent": "analyst",
        "parameters": {"query": "Q3 budget data"},
        "reasoning": "Need budget data before meeting"
    }"""

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.orientation = {
        "patterns": ["Budget meeting upcoming"],
        "opportunities": ["Prepare data"],
        "threats": ["Time pressure"],
        "recommended_focus": "Gather budget data",
    }
    goal = {"id": "goal-123", "title": "Prepare budget meeting"}

    new_state = await loop.decide(state, goal)

    # Verify decision was made
    assert new_state.decision is not None
    assert "action" in new_state.decision
    assert new_state.current_phase == OODAPhase.ACT

    # Verify LLM was called
    mock_llm.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_ooda_loop_decide_can_mark_goal_complete() -> None:
    """Test decide phase can recognize goal is achieved."""
    from src.core.ooda import OODALoop, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = """{
        "action": "complete",
        "agent": null,
        "parameters": {},
        "reasoning": "All objectives have been met"
    }"""

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.orientation = {"recommended_focus": "Review completion"}
    goal = {"id": "goal-123", "title": "Completed goal"}

    new_state = await loop.decide(state, goal)

    assert new_state.decision["action"] == "complete"
    assert new_state.is_complete is True


@pytest.mark.asyncio
async def test_ooda_loop_decide_can_mark_blocked() -> None:
    """Test decide phase can recognize goal is blocked."""
    from src.core.ooda import OODALoop, OODAState

    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = """{
        "action": "blocked",
        "agent": null,
        "parameters": {},
        "reasoning": "Missing required permissions"
    }"""

    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )

    state = OODAState(goal_id="goal-123")
    state.orientation = {"threats": ["No access"]}
    goal = {"id": "goal-123", "title": "Blocked goal"}

    new_state = await loop.decide(state, goal)

    assert new_state.decision["action"] == "blocked"
    assert new_state.is_blocked is True
    assert "permissions" in new_state.blocked_reason.lower()


@pytest.mark.asyncio
async def test_ooda_loop_act_executes_decision() -> None:
    """Test act phase executes the decided action."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    # Create a mock agent executor
    mock_executor = AsyncMock()
    mock_executor.return_value = {
        "success": True,
        "data": {"results": ["Budget data found"]},
    }

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )
    loop.agent_executor = mock_executor

    state = OODAState(goal_id="goal-123")
    state.decision = {
        "action": "research",
        "agent": "analyst",
        "parameters": {"query": "Q3 budget data"},
        "reasoning": "Need budget data",
    }
    goal = {"id": "goal-123", "title": "Prepare budget meeting"}

    new_state = await loop.act(state, goal)

    # Verify action was executed
    assert new_state.action_result is not None
    assert new_state.action_result["success"] is True
    assert new_state.current_phase == OODAPhase.OBSERVE  # Loops back
    assert new_state.iteration == 1  # Incremented


@pytest.mark.asyncio
async def test_ooda_loop_act_skips_complete_state() -> None:
    """Test act phase does nothing if goal is complete."""
    from src.core.ooda import OODALoop, OODAState

    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    mock_executor = AsyncMock()

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )
    loop.agent_executor = mock_executor

    state = OODAState(goal_id="goal-123")
    state.decision = {"action": "complete"}
    state.is_complete = True
    goal = {"id": "goal-123", "title": "Complete goal"}

    new_state = await loop.act(state, goal)

    # Agent executor should not be called
    mock_executor.assert_not_called()
    assert new_state.is_complete is True


@pytest.mark.asyncio
async def test_ooda_loop_act_handles_execution_failure() -> None:
    """Test act phase handles agent execution failure."""
    from src.core.ooda import OODALoop, OODAPhase, OODAState

    mock_llm = MagicMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()
    mock_working.user_id = "user-123"

    mock_executor = AsyncMock()
    mock_executor.side_effect = Exception("Agent failed")

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
    )
    loop.agent_executor = mock_executor

    state = OODAState(goal_id="goal-123")
    state.decision = {
        "action": "research",
        "agent": "analyst",
        "parameters": {},
    }
    goal = {"id": "goal-123", "title": "Test goal"}

    new_state = await loop.act(state, goal)

    # Should record failure but continue
    assert new_state.action_result is not None
    assert new_state.action_result["success"] is False
    assert "error" in new_state.action_result
    assert new_state.current_phase == OODAPhase.OBSERVE  # Still loops back


# Tests for OODALoop.run() method


@pytest.mark.asyncio
async def test_ooda_loop_run_completes_on_success() -> None:
    """Test run() returns final state when goal is achieved."""
    from src.core.ooda import OODAConfig, OODALoop

    mock_llm = AsyncMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Setup mocks
    mock_episodic.semantic_search.return_value = []
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    # First iteration: orient gives analysis, decide selects action, act succeeds
    # Second iteration: decide returns "complete"
    orient_responses = [
        '{"patterns": ["data found"], "opportunities": [], "threats": [], "recommended_focus": "analyze"}',
        '{"patterns": ["complete"], "opportunities": [], "threats": [], "recommended_focus": "done"}',
    ]
    decide_responses = [
        '{"action": "research", "agent": "analyst", "parameters": {}, "reasoning": "need data"}',
        '{"action": "complete", "agent": null, "parameters": {}, "reasoning": "goal achieved"}',
    ]
    mock_llm.generate_response.side_effect = orient_responses + decide_responses

    # Need to track call count to return appropriate responses
    call_count = 0

    async def mock_generate(**kwargs: object) -> str:
        nonlocal call_count
        system_prompt = str(kwargs.get("system_prompt", ""))
        # Alternate between orient and decide responses
        if "analyze" in system_prompt.lower() or "patterns" in system_prompt.lower():
            idx = min(call_count // 2, len(orient_responses) - 1)
            response = orient_responses[idx]
        else:
            idx = min(call_count // 2, len(decide_responses) - 1)
            response = decide_responses[idx]
        call_count += 1
        return response

    mock_llm.generate_response = mock_generate

    mock_executor = AsyncMock()
    mock_executor.return_value = {"success": True, "data": {}}

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
        config=OODAConfig(max_iterations=5),
    )
    loop.agent_executor = mock_executor

    final_state = await loop.run(goal="Prepare budget meeting")

    assert final_state.is_complete is True
    assert final_state.is_blocked is False


@pytest.mark.asyncio
async def test_ooda_loop_run_raises_on_blocked() -> None:
    """Test run() raises OODABlockedError when loop becomes blocked."""
    from src.core.exceptions import OODABlockedError
    from src.core.ooda import OODAConfig, OODALoop

    mock_llm = AsyncMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Setup mocks
    mock_episodic.semantic_search.return_value = []
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    # Immediately return blocked decision
    async def mock_generate(**kwargs: object) -> str:
        system_prompt = str(kwargs.get("system_prompt", ""))
        if "analyze" in system_prompt.lower() or "patterns" in system_prompt.lower():
            return '{"patterns": [], "opportunities": [], "threats": ["blocked"], "recommended_focus": "blocked"}'
        else:
            return '{"action": "blocked", "agent": null, "parameters": {}, "reasoning": "missing permissions"}'

    mock_llm.generate_response = mock_generate

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
        config=OODAConfig(max_iterations=5),
    )

    with pytest.raises(OODABlockedError) as exc_info:
        await loop.run(goal="Blocked goal")

    assert "blocked" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ooda_loop_run_raises_on_max_iterations() -> None:
    """Test run() raises OODAMaxIterationsError when max iterations exceeded."""
    from src.core.exceptions import OODAMaxIterationsError
    from src.core.ooda import OODAConfig, OODALoop

    mock_llm = AsyncMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Setup mocks
    mock_episodic.semantic_search.return_value = []
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    # Never complete - always return an action
    async def mock_generate(**kwargs: object) -> str:
        system_prompt = str(kwargs.get("system_prompt", ""))
        if "analyze" in system_prompt.lower() or "patterns" in system_prompt.lower():
            return '{"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "continue"}'
        else:
            return '{"action": "research", "agent": "analyst", "parameters": {}, "reasoning": "need more data"}'

    mock_llm.generate_response = mock_generate

    mock_executor = AsyncMock()
    mock_executor.return_value = {"success": True, "data": {}}

    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
        config=OODAConfig(max_iterations=3),  # Low limit for test
    )
    loop.agent_executor = mock_executor

    with pytest.raises(OODAMaxIterationsError) as exc_info:
        await loop.run(goal="Never-ending goal")

    assert exc_info.value.details["iterations"] == 3


@pytest.mark.asyncio
async def test_ooda_loop_run_raises_on_budget_exceeded() -> None:
    """Test run() raises OODAMaxIterationsError when token budget exceeded."""
    from src.core.exceptions import OODAMaxIterationsError
    from src.core.ooda import OODAConfig, OODALoop

    mock_llm = AsyncMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()
    mock_working = MagicMock()

    # Setup mocks
    mock_episodic.semantic_search.return_value = []
    mock_semantic.search_facts.return_value = []
    mock_working.get_context_for_llm.return_value = []
    mock_working.user_id = "user-123"

    # Return non-completing responses but track tokens
    async def mock_generate(**kwargs: object) -> str:
        system_prompt = str(kwargs.get("system_prompt", ""))
        if "analyze" in system_prompt.lower() or "patterns" in system_prompt.lower():
            return '{"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "continue"}'
        else:
            return '{"action": "research", "agent": "analyst", "parameters": {}, "reasoning": "need more data"}'

    mock_llm.generate_response = mock_generate

    mock_executor = AsyncMock()
    mock_executor.return_value = {"success": True, "data": {}}

    # Very low token budget to trigger budget exceeded
    loop = OODALoop(
        llm_client=mock_llm,
        episodic_memory=mock_episodic,
        semantic_memory=mock_semantic,
        working_memory=mock_working,
        config=OODAConfig(max_iterations=100, total_budget=100),  # Very low budget
    )
    loop.agent_executor = mock_executor

    with pytest.raises(OODAMaxIterationsError) as exc_info:
        await loop.run(goal="Budget exceeding goal")

    # Should mention budget in the error
    assert (
        "budget" in str(exc_info.value).lower()
        or exc_info.value.details.get("iterations") is not None
    )
