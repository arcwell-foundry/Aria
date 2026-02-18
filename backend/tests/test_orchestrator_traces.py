"""Tests for DelegationTrace + DCT wiring in AgentOrchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.orchestrator import AgentOrchestrator
from src.agents.base import AgentResult


class TestOrchestratorTraces:
    """Verify traces are created around agent dispatch."""

    @pytest.mark.asyncio
    async def test_trace_started_and_completed_on_success(self):
        """Delegation trace wraps successful agent execution."""
        trace_svc = MagicMock()
        trace_svc.start_trace = AsyncMock(return_value="trace-123")
        trace_svc.complete_trace = AsyncMock()

        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
            delegation_trace_service=trace_svc,
        )

        mock_agent = MagicMock()
        mock_agent.name = "analyst"
        mock_agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                data={"answer": "test"},
                error=None,
                tokens_used=100,
                execution_time_ms=50,
            )
        )

        with patch.object(orch, "spawn_agent", return_value="agent-1"):
            orch.active_agents["agent-1"] = mock_agent
            result = await orch.spawn_and_execute(
                MagicMock(), {"goal_id": "g1", "title": "Test"}
            )

        trace_svc.start_trace.assert_called_once()
        trace_svc.complete_trace.assert_called_once()
        call_kwargs = trace_svc.complete_trace.call_args
        assert call_kwargs.kwargs["trace_id"] == "trace-123"
        assert call_kwargs.kwargs["status"] == "completed"
        assert result.success

    @pytest.mark.asyncio
    async def test_trace_failed_on_agent_exception(self):
        """Delegation trace marked failed when agent raises."""
        trace_svc = MagicMock()
        trace_svc.start_trace = AsyncMock(return_value="trace-456")
        trace_svc.fail_trace = AsyncMock()

        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
            delegation_trace_service=trace_svc,
        )

        mock_agent = MagicMock()
        mock_agent.name = "scout"
        mock_agent.run = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(orch, "spawn_agent", return_value="agent-2"):
            orch.active_agents["agent-2"] = mock_agent
            with pytest.raises(RuntimeError, match="boom"):
                await orch.spawn_and_execute(
                    MagicMock(), {"goal_id": "g2", "title": "Fail test"}
                )

        trace_svc.fail_trace.assert_called_once()
        call_kwargs = trace_svc.fail_trace.call_args
        assert call_kwargs.kwargs["trace_id"] == "trace-456"
        assert "boom" in call_kwargs.kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_trace_error_does_not_block_execution(self):
        """If trace service fails, agent still executes."""
        trace_svc = MagicMock()
        trace_svc.start_trace = AsyncMock(side_effect=RuntimeError("db down"))

        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
            delegation_trace_service=trace_svc,
        )

        mock_agent = MagicMock()
        mock_agent.name = "analyst"
        mock_agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                data={"answer": "ok"},
                error=None,
                tokens_used=50,
                execution_time_ms=10,
            )
        )

        with patch.object(orch, "spawn_agent", return_value="agent-3"):
            orch.active_agents["agent-3"] = mock_agent
            result = await orch.spawn_and_execute(
                MagicMock(), {"goal_id": "g3", "title": "Resilient test"}
            )

        assert result.success  # Agent ran despite trace failure

    @pytest.mark.asyncio
    async def test_no_trace_service_works_fine(self):
        """Without trace service, orchestrator works normally."""
        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
        )

        mock_agent = MagicMock()
        mock_agent.name = "analyst"
        mock_agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                data={"answer": "ok"},
                error=None,
                tokens_used=50,
                execution_time_ms=10,
            )
        )

        with patch.object(orch, "spawn_agent", return_value="agent-4"):
            orch.active_agents["agent-4"] = mock_agent
            result = await orch.spawn_and_execute(
                MagicMock(), {"goal_id": "g4", "title": "No trace test"}
            )

        assert result.success

    @pytest.mark.asyncio
    async def test_dct_validation_logged(self):
        """DCT in task dict is validated before agent runs."""
        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
        )

        mock_agent = MagicMock()
        mock_agent.name = "analyst"
        mock_agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                data={},
                error=None,
                tokens_used=10,
                execution_time_ms=5,
            )
        )

        # Include a DCT in the task
        task = {
            "goal_id": "g5",
            "title": "DCT test",
            "capability_token": {
                "token_id": "t1",
                "delegatee": "analyst",
                "allowed_actions": ["read_pubmed"],
                "denied_actions": ["send_email"],
            },
        }

        with patch.object(orch, "spawn_agent", return_value="agent-5"):
            orch.active_agents["agent-5"] = mock_agent
            result = await orch.spawn_and_execute(MagicMock(), task)

        assert result.success
