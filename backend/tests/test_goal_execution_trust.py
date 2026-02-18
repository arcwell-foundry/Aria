"""Tests for Trust update wiring in GoalExecutionService."""

from unittest.mock import AsyncMock, MagicMock

import pytest


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
    svc._adaptive_coordinator = None
    svc._store_execution = AsyncMock()
    svc._submit_actions_to_queue = AsyncMock()
    svc._try_skill_execution = AsyncMock(return_value=None)

    # Skip verification (these tests focus on trust, not verification)
    async def _passthrough_verify(**kwargs):
        return (kwargs["content"], None, False)

    svc._verify_and_adapt = _passthrough_verify
    # Mock prompt builders to avoid needing real context data
    svc._build_analyst_prompt = MagicMock(return_value="analyze this")
    svc._build_scout_prompt = MagicMock(return_value="scout this")
    svc._build_hunter_prompt = MagicMock(return_value="hunt this")
    svc._build_strategist_prompt = MagicMock(return_value="strategize this")
    svc._build_scribe_prompt = MagicMock(return_value="write this")
    svc._build_operator_prompt = MagicMock(return_value="operate this")
    return svc


class TestGoalExecutionTrustUpdates:
    """Verify trust service is called on agent success/failure."""

    @pytest.mark.asyncio
    async def test_success_updates_trust_prompt_path(self):
        """Successful prompt-based agent execution calls update_on_success."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.35)
        svc._trust_service = mock_trust

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="analyst",
            context={},
        )

        assert result["success"]
        mock_trust.update_on_success.assert_called_once_with("u1", "research")

    @pytest.mark.asyncio
    async def test_success_updates_trust_skill_path(self):
        """Successful skill-aware agent execution calls update_on_success."""
        svc = _make_goal_execution_service()
        svc._try_skill_execution = AsyncMock(
            return_value={"summary": "skill result"}
        )

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.4)
        svc._trust_service = mock_trust

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="scout",
            context={},
        )

        assert result["success"]
        mock_trust.update_on_success.assert_called_once_with("u1", "market_monitoring")

    @pytest.mark.asyncio
    async def test_failure_updates_trust(self):
        """Failed agent execution calls update_on_failure."""
        svc = _make_goal_execution_service()
        svc._llm.generate_response = AsyncMock(side_effect=RuntimeError("LLM down"))

        mock_trust = MagicMock()
        mock_trust.update_on_failure = AsyncMock(return_value=0.21)
        svc._trust_service = mock_trust

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="analyst",
            context={},
        )

        assert not result["success"]
        mock_trust.update_on_failure.assert_called_once_with("u1", "research")

    @pytest.mark.asyncio
    async def test_trust_error_does_not_block_execution(self):
        """Trust update failure doesn't prevent agent result from returning."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(side_effect=RuntimeError("db error"))
        svc._trust_service = mock_trust

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="analyst",
            context={},
        )

        # Should still succeed despite trust update failure
        assert result["success"]

    @pytest.mark.asyncio
    async def test_no_trust_service_works_fine(self):
        """Without trust service, execution works normally."""
        svc = _make_goal_execution_service()

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="analyst",
            context={},
        )

        assert result["success"]
