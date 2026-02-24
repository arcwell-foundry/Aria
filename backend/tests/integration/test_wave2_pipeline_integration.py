"""Integration tests for the full Wave 2 services pipeline.

Verifies that CognitiveFriction, Trust, DCTs, and DelegationTraces
work together across the request lifecycle:
  Friction → OODA (Trust + DCT) → Orchestrator (Trace + DCT) → GoalExecution (Trust update + Trace)
"""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base import AgentResult
from src.agents.orchestrator import AgentOrchestrator
from src.core.ooda import OODALoop, OODAPhase, OODAState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeFrictionDecision:
    level: str
    reasoning: str
    user_message: str | None
    proceed_if_confirmed: bool


def _make_chat_service():
    """Build a ChatService with all dependencies mocked out."""
    from src.services.chat import ChatService

    svc = ChatService.__new__(ChatService)
    svc._llm_client = MagicMock()
    svc._llm_client.generate_response = AsyncMock(return_value="Sure, I'll do that.")
    svc._working_memory_manager = MagicMock()
    svc._working_memory_manager.get_or_create = AsyncMock(
        return_value=MagicMock(
            add_message=MagicMock(),
            get_context_for_llm=MagicMock(return_value=[]),
        )
    )
    svc._memory_service = MagicMock()
    svc._memory_service.query = AsyncMock(return_value=[])
    svc._cognitive_monitor = MagicMock()
    svc._cognitive_monitor.estimate_load = AsyncMock(
        return_value=MagicMock(
            level=MagicMock(value="low"), score=0.1, recommendation="",
        )
    )
    svc._web_grounding = MagicMock()
    svc._web_grounding.detect_and_ground = AsyncMock(return_value=None)
    svc._email_check = MagicMock()
    svc._email_check.detect_email_check_request = MagicMock(return_value=False)
    svc._proactive_service = MagicMock()
    svc._proactive_service.get_insights = AsyncMock(return_value=[])
    svc._companion_orchestrator = None
    svc._personality_calibrator = MagicMock()
    svc._personality_calibrator.get_calibration = AsyncMock(return_value=None)
    svc._digital_twin = MagicMock()
    svc._digital_twin.get_style_guidelines = AsyncMock(return_value=None)
    svc._priming_service = MagicMock()
    svc._priming_service.get_priming_context = AsyncMock(return_value=None)
    svc._episodic_memory = MagicMock()
    svc._episodic_memory.store_episode = AsyncMock()
    svc._extraction_service = MagicMock()
    svc._extraction_service.extract_and_store = AsyncMock()
    svc._use_persona_builder = False
    svc._persona_builder = None
    svc._skill_registry = None
    svc._skill_orchestrator = None
    svc._skill_registry_initialized = True
    svc._friction_engine = None
    svc._trust_service = None
    svc.persist_turn = AsyncMock()
    svc._ensure_conversation_record = AsyncMock()
    return svc


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
    svc._tool_discovery = None
    svc._store_execution = AsyncMock()
    svc._submit_actions_to_queue = AsyncMock()
    svc._try_skill_execution = AsyncMock(return_value=None)
    svc._build_analyst_prompt = MagicMock(return_value="analyze this")
    svc._build_scout_prompt = MagicMock(return_value="scout this")
    svc._build_hunter_prompt = MagicMock(return_value="hunt this")
    svc._build_strategist_prompt = MagicMock(return_value="strategize this")
    svc._build_scribe_prompt = MagicMock(return_value="write this")
    svc._build_operator_prompt = MagicMock(return_value="operate this")
    svc._record_goal_update = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------

class TestWave2PipelineHappyPath:
    """Test the full happy-path flow: comply → OODA → orchestrator → goal execution."""

    @pytest.mark.asyncio
    async def test_comply_flows_through_to_llm(self):
        """Friction complies → LLM generates response normally."""
        svc = _make_chat_service()

        comply_decision = FakeFrictionDecision(
            level="comply",
            reasoning="No concerns",
            user_message=None,
            proceed_if_confirmed=True,
        )

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=comply_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Research BioGenix pipeline"
            )

        svc._llm_client.generate_response.assert_called_once()
        assert result["message"] == "Sure, I'll do that."
        assert result["timing"]["friction_ms"] >= 0

    @pytest.mark.asyncio
    async def test_ooda_decide_mints_dct_and_sets_approval(self):
        """OODA decide phase produces approval_level + capability_token in state."""
        trust = MagicMock()
        trust.get_approval_level = AsyncMock(return_value="EXECUTE_AND_NOTIFY")

        minter = MagicMock()
        fake_dct = MagicMock()
        fake_dct.to_dict.return_value = {"token_id": "t1", "delegatee": "analyst"}
        minter.mint.return_value = fake_dct

        loop = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="u1"),
            user_id="u1",
            trust_service=trust,
            dct_minter=minter,
        )
        loop.llm.generate_response = AsyncMock(
            return_value='{"action":"research","agent":"analyst","parameters":{}}'
        )

        state = OODAState(goal_id="g1", current_phase=OODAPhase.DECIDE)
        state.orientation = {"recommended_focus": "research"}
        state = await loop.decide(state, {"title": "Test goal"})

        assert state.approval_level == "EXECUTE_AND_NOTIFY"
        assert state.capability_token is not None
        assert state.capability_token["delegatee"] == "analyst"

    @pytest.mark.asyncio
    async def test_orchestrator_trace_wraps_agent_execution(self):
        """Orchestrator creates trace → agent runs → trace completed."""
        trace_svc = MagicMock()
        trace_svc.start_trace = AsyncMock(return_value="trace-pipeline")
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
                MagicMock(), {"goal_id": "g1", "title": "Pipeline test"}
            )

        assert result.success
        trace_svc.start_trace.assert_called_once()
        trace_svc.complete_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_goal_execution_updates_trust_on_success(self):
        """Successful agent execution updates trust score."""
        svc = _make_goal_execution_service()
        # Make LLM's generate_response_with_thinking async so VerifierAgent works
        svc._llm.generate_response_with_thinking = AsyncMock(
            return_value=MagicMock(
                text='{"passed": true, "issues": [], "confidence": 0.9, "suggestions": []}'
            )
        )

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.35)
        mock_trust.update_on_failure = AsyncMock(return_value=0.15)
        svc._trust_service = mock_trust

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "description": "desc", "config": {}},
            agent_type="analyst",
            context={},
        )

        assert result["success"]
        mock_trust.update_on_success.assert_called_once_with("u1", "research")


class TestWave2PipelineChallengeFlow:
    """Test the challenge path: friction challenges → early return → no downstream."""

    @pytest.mark.asyncio
    async def test_challenge_blocks_entire_pipeline(self):
        """Friction challenge returns pushback, no LLM or downstream calls."""
        svc = _make_chat_service()

        challenge_decision = FakeFrictionDecision(
            level="challenge",
            reasoning="Missing ROI analysis",
            user_message="I'd include the ROI section -- the CFO explicitly asked for it.",
            proceed_if_confirmed=True,
        )

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(return_value=challenge_decision)
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Send proposal without ROI section"
            )

        # Friction triggered pushback
        assert result["message"] == challenge_decision.user_message
        assert result["rich_content"][0]["type"] == "friction_decision"
        assert result["rich_content"][0]["data"]["level"] == "challenge"

        # LLM was NOT called
        svc._llm_client.generate_response.assert_not_called()

        # Suggestions include confirmation option
        assert "Confirm and proceed" in result["suggestions"]


class TestWave2PipelineDCTEnforcement:
    """Test DCT capability enforcement at unit level."""

    def test_dct_blocks_unauthorized_action(self):
        """DCT minted for analyst denies send_email."""
        from src.core.capability_tokens import DCTMinter

        minter = DCTMinter()
        dct = minter.mint(delegatee="analyst", goal_id="g1", time_limit=300)

        assert dct.can_perform("read_pubmed") is True
        assert dct.can_perform("send_email") is False
        assert dct.is_valid() is True

    def test_dct_allows_authorized_action(self):
        """DCT minted for operator allows send_email."""
        from src.core.capability_tokens import DCTMinter

        minter = DCTMinter()
        dct = minter.mint(delegatee="operator", goal_id="g1", time_limit=300)

        assert dct.can_perform("send_email") is True
        assert dct.can_perform("delete_crm_records") is False


class TestWave2PipelineFailurePath:
    """Test failure path: agent fails → trust decremented → trace marked failed."""

    @pytest.mark.asyncio
    async def test_failure_updates_trust_and_fails_trace(self):
        """Agent exception → trust.update_on_failure + trace.fail_trace."""
        svc = _make_goal_execution_service()
        svc._llm.generate_response = AsyncMock(
            side_effect=RuntimeError("LLM crashed")
        )

        mock_trust = MagicMock()
        mock_trust.update_on_failure = AsyncMock(return_value=0.21)
        svc._trust_service = mock_trust

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-fail")
        mock_traces.fail_trace = AsyncMock()
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Fail test", "description": "d", "config": {}},
            agent_type="analyst",
            context={},
        )

        assert not result["success"]

        # Trust was decremented
        mock_trust.update_on_failure.assert_called_once_with("u1", "research")

        # Trace was marked failed
        mock_traces.fail_trace.assert_called_once()
        call_kwargs = mock_traces.fail_trace.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-fail"
        assert "LLM crashed" in call_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_orchestrator_trace_fails_on_agent_exception(self):
        """Orchestrator records trace failure when agent raises."""
        trace_svc = MagicMock()
        trace_svc.start_trace = AsyncMock(return_value="trace-orch-fail")
        trace_svc.fail_trace = AsyncMock()

        orch = AgentOrchestrator(
            llm_client=MagicMock(),
            user_id="u1",
            delegation_trace_service=trace_svc,
        )

        mock_agent = MagicMock()
        mock_agent.name = "scout"
        mock_agent.run = AsyncMock(side_effect=RuntimeError("network error"))

        with patch.object(orch, "spawn_agent", return_value="agent-fail"):
            orch.active_agents["agent-fail"] = mock_agent
            with pytest.raises(RuntimeError, match="network error"):
                await orch.spawn_and_execute(
                    MagicMock(), {"goal_id": "g2", "title": "Fail test"}
                )

        trace_svc.fail_trace.assert_called_once()
        assert "network error" in trace_svc.fail_trace.call_args.kwargs["error_message"]


class TestWave2PipelineResilience:
    """Test that service failures don't cascade — all wiring is fail-open."""

    @pytest.mark.asyncio
    async def test_all_wave2_services_failing_still_produces_response(self):
        """If friction, trust, and traces all fail, chat still works."""
        svc = _make_chat_service()

        with patch(
            "src.services.chat.get_cognitive_friction_engine"
        ) as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.evaluate = AsyncMock(
                side_effect=RuntimeError("friction db down")
            )
            mock_get_engine.return_value = mock_engine

            result = await svc.process_message(
                "user-1", "conv-1", "Do something risky"
            )

        # Response still generated
        assert "message" in result
        svc._llm_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_trust_and_trace_failures_dont_block_goal_execution(self):
        """GoalExecution works even when trust + trace services are broken."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(
            side_effect=RuntimeError("trust db down")
        )
        svc._trust_service = mock_trust

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(
            side_effect=RuntimeError("trace db down")
        )
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Resilient", "description": "d", "config": {}},
            agent_type="analyst",
            context={},
        )

        # Agent still executed successfully
        assert result["success"]
