"""Tests for OODA loop single iteration and scheduler integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.ooda import OODAConfig, OODALoop, OODAState


@pytest.mark.asyncio
async def test_run_single_iteration_observe_orient_decide_act():
    """run_single_iteration should execute all four OODA phases."""
    llm = MagicMock()
    llm.generate_response = AsyncMock(
        return_value='{"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "test"}'
    )
    episodic = MagicMock()
    episodic.semantic_search = AsyncMock(return_value=[])
    semantic = MagicMock()
    semantic.search_facts = AsyncMock(return_value=[])
    working = MagicMock()
    working.user_id = "user-1"
    working.get_context_for_llm = MagicMock(return_value="test context")

    config = OODAConfig(max_iterations=1)
    ooda = OODALoop(
        llm_client=llm,
        episodic_memory=episodic,
        semantic_memory=semantic,
        working_memory=working,
        config=config,
    )

    # Mock the decide phase to return a non-terminal action
    original_decide = ooda.decide

    async def mock_decide(state, goal):
        state = await original_decide(state, goal)
        # Override with a specific action to avoid JSON parse issues
        if state.decision and state.decision.get("action") == "blocked":
            state.decision = {
                "action": "research",
                "agent": "analyst",
                "parameters": {},
                "reasoning": "Need more info",
            }
            state.is_blocked = False
            state.current_phase = __import__("src.core.ooda", fromlist=["OODAPhase"]).OODAPhase.ACT
        return state

    state = OODAState(goal_id="goal-1")
    goal = {"id": "goal-1", "title": "Test Goal", "description": "Testing"}

    # Run with mocked LLM responses for all phases
    llm.generate_response = AsyncMock(
        side_effect=[
            # Orient phase response
            '{"patterns": ["p1"], "opportunities": ["o1"], "threats": [], "recommended_focus": "research"}',
            # Decide phase response
            '{"action": "research", "agent": "analyst", "parameters": {}, "reasoning": "need data"}',
        ]
    )

    state = await ooda.run_single_iteration(state, goal)

    # Should have completed one full cycle
    assert state.iteration == 1  # Act increments iteration
    assert len(state.phase_logs) == 4  # observe, orient, decide, act


@pytest.mark.asyncio
async def test_run_single_iteration_detects_complete():
    """run_single_iteration should stop at decide if action is 'complete'."""
    llm = MagicMock()
    episodic = MagicMock()
    episodic.semantic_search = AsyncMock(return_value=[])
    semantic = MagicMock()
    semantic.search_facts = AsyncMock(return_value=[])
    working = MagicMock()
    working.user_id = "user-1"
    working.get_context_for_llm = MagicMock(return_value="")

    ooda = OODALoop(
        llm_client=llm,
        episodic_memory=episodic,
        semantic_memory=semantic,
        working_memory=working,
    )

    llm.generate_response = AsyncMock(
        side_effect=[
            '{"patterns": [], "opportunities": [], "threats": [], "recommended_focus": "done"}',
            '{"action": "complete", "agent": null, "parameters": {}, "reasoning": "goal achieved"}',
        ]
    )

    state = OODAState(goal_id="goal-1")
    goal = {"id": "goal-1", "title": "Test", "description": ""}

    state = await ooda.run_single_iteration(state, goal)

    assert state.is_complete
    # Should have 3 phases (observe, orient, decide) — no act since complete
    assert len(state.phase_logs) == 3


@pytest.mark.asyncio
async def test_ooda_loop_accepts_agent_executor():
    """OODALoop should accept and store agent_executor parameter."""
    llm = MagicMock()
    episodic = MagicMock()
    semantic = MagicMock()
    working = MagicMock()

    executor = AsyncMock()

    ooda = OODALoop(
        llm_client=llm,
        episodic_memory=episodic,
        semantic_memory=semantic,
        working_memory=working,
        agent_executor=executor,
    )

    assert ooda.agent_executor is executor


@pytest.mark.asyncio
async def test_scheduler_ooda_function_exists():
    """The _run_ooda_goal_checks function should be importable."""
    from src.services.scheduler import _run_ooda_goal_checks

    assert callable(_run_ooda_goal_checks)
