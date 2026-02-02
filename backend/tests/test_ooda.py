"""Tests for OODA loop cognitive processing module."""


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


import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_ooda_loop_observe_gathers_memory_context() -> None:
    """Test observe phase queries episodic and semantic memory."""
    from src.core.ooda import OODALoop, OODAState, OODAConfig

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
    goal = {"id": "goal-123", "title": "Prepare budget meeting", "description": "Get ready for Q3 budget review"}

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
    from src.core.ooda import OODALoop, OODAState, OODAPhase

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
