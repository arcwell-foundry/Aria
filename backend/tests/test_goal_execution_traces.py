"""Tests for DelegationTrace wiring in GoalExecutionService."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_goal_execution_service():
    """Build a GoalExecutionService with all dependencies mocked."""
    from src.services.goal_execution import GoalExecutionService

    svc = GoalExecutionService.__new__(GoalExecutionService)
    svc._db = MagicMock()
    svc._llm = MagicMock()
    svc._llm.generate_response = AsyncMock(return_value='{"summary":"done"}')
    svc._activity = MagicMock()
    svc._activity.record = AsyncMock()
    svc._dynamic_agents = {}
    svc._active_tasks = {}
    svc._trust_service = None
    svc._trace_service = None
    svc._store_execution = AsyncMock()
    svc._submit_actions_to_queue = AsyncMock()
    svc._try_skill_execution = AsyncMock(return_value=None)
    # Mock prompt builders to avoid needing real context data
    svc._build_analyst_prompt = MagicMock(return_value="analyze this")
    svc._build_scout_prompt = MagicMock(return_value="scout this")
    svc._build_hunter_prompt = MagicMock(return_value="hunt this")
    svc._build_strategist_prompt = MagicMock(return_value="strategize this")
    svc._build_scribe_prompt = MagicMock(return_value="write this")
    svc._build_operator_prompt = MagicMock(return_value="operate this")
    return svc


class TestGoalExecutionTraces:
    """Verify delegation traces wrap agent execution."""

    @pytest.mark.asyncio
    async def test_trace_started_and_completed_on_success(self):
        """Delegation trace wraps successful prompt-based execution."""
        svc = _make_goal_execution_service()

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-789")
        mock_traces.complete_trace = AsyncMock()
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test goal"},
            agent_type="analyst",
            context={},
        )

        assert result["success"]
        mock_traces.start_trace.assert_called_once()
        mock_traces.complete_trace.assert_called_once()
        call_kwargs = mock_traces.complete_trace.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-789"
        assert call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_trace_started_and_completed_on_skill_path(self):
        """Delegation trace wraps successful skill-aware execution."""
        svc = _make_goal_execution_service()
        svc._try_skill_execution = AsyncMock(
            return_value={"summary": "skill output"}
        )

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-skill")
        mock_traces.complete_trace = AsyncMock()
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Skill test"},
            agent_type="scout",
            context={},
        )

        assert result["success"]
        mock_traces.start_trace.assert_called_once()
        mock_traces.complete_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_trace_failed_on_agent_error(self):
        """Delegation trace marked failed when agent raises."""
        svc = _make_goal_execution_service()
        svc._llm.generate_response = AsyncMock(side_effect=RuntimeError("boom"))

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-fail")
        mock_traces.fail_trace = AsyncMock()
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Fail test"},
            agent_type="analyst",
            context={},
        )

        assert not result["success"]
        mock_traces.fail_trace.assert_called_once()
        call_kwargs = mock_traces.fail_trace.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-fail"
        assert "boom" in call_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_trace_error_does_not_block_execution(self):
        """If trace service fails, agent still executes."""
        svc = _make_goal_execution_service()

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(side_effect=RuntimeError("db down"))
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Resilient test"},
            agent_type="analyst",
            context={},
        )

        assert result["success"]  # Agent ran despite trace failure
