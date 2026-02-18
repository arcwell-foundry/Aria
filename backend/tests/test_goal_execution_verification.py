"""Tests for Verifier + AdaptiveCoordinator wiring in GoalExecutionService."""

from unittest.mock import AsyncMock, MagicMock, patch

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
    # Mock prompt builders to avoid needing real context data
    svc._build_analyst_prompt = MagicMock(return_value="analyze this")
    svc._build_scout_prompt = MagicMock(return_value="scout this")
    svc._build_hunter_prompt = MagicMock(return_value="hunt this")
    svc._build_strategist_prompt = MagicMock(return_value="strategize this")
    svc._build_scribe_prompt = MagicMock(return_value="write this")
    svc._build_operator_prompt = MagicMock(return_value="operate this")
    return svc


def _make_passed_verification_result():
    """Create a mock VerificationResult that passes."""
    from src.agents.verifier import VerificationResult

    return VerificationResult(
        passed=True,
        issues=[],
        confidence=0.95,
        suggestions=[],
    )


def _make_failed_verification_result(issues=None):
    """Create a mock VerificationResult that fails."""
    from src.agents.verifier import VerificationResult

    return VerificationResult(
        passed=False,
        issues=issues or ["Unsupported claim detected", "Data source not verifiable"],
        confidence=0.3,
        suggestions=["Add citation for claim", "Verify data source"],
    )


class TestVerificationPasses:
    """Happy path: verification passes on first attempt."""

    @pytest.mark.asyncio
    async def test_analyst_output_verified_with_research_brief_policy(self):
        """Analyst output is verified with RESEARCH_BRIEF policy, trust updated on success."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.35)
        svc._trust_service = mock_trust

        passed_result = _make_passed_verification_result()
        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=passed_result)

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        assert result.get("verification_result") is not None
        assert result["verification_result"]["passed"] is True
        assert "escalated" not in result
        mock_trust.update_on_success.assert_called_once_with("u1", "research")
        mock_verifier.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_operator_skips_verification(self):
        """Operator agent has no verification policy, so verification is skipped."""
        svc = _make_goal_execution_service()

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "config": {}},
            agent_type="operator",
            context={},
        )

        assert result["success"]
        assert result.get("verification_result") is None

    @pytest.mark.asyncio
    async def test_verification_passes_on_skill_aware_path(self):
        """Skill-aware path also runs verification."""
        svc = _make_goal_execution_service()
        svc._try_skill_execution = AsyncMock(
            return_value={"summary": "skill result"}
        )

        passed_result = _make_passed_verification_result()
        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=passed_result)

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="scout",
                context={},
            )

        assert result["success"]
        assert result["execution_mode"] == "skill_aware"
        assert result.get("verification_result") is not None
        assert result["verification_result"]["passed"] is True
        mock_verifier.verify.assert_called_once()


class TestVerificationRetrySucceeds:
    """Verification fails initially, retry succeeds."""

    @pytest.mark.asyncio
    async def test_retry_on_verification_failure_then_passes(self):
        """First verify fails, retry content passes verification."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_success = AsyncMock(return_value=0.35)
        svc._trust_service = mock_trust

        failed_result = _make_failed_verification_result()
        passed_result = _make_passed_verification_result()

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(side_effect=[failed_result, passed_result])

        from src.core.adaptive_coordinator import (
            AdaptiveDecision,
            AdaptiveDecisionType,
            FailureAnalysis,
            FailureTrigger,
        )

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate_output = MagicMock(
            return_value=AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=FailureAnalysis(
                    trigger=FailureTrigger.VERIFICATION_FAILED,
                    severity=0.7,
                    details="Verification rejected output",
                    recoverable=True,
                ),
                target_agent=None,
                retry_params={"verification_feedback": "issues found"},
                partial_results={},
                reasoning="Retrying",
                retry_count=1,
            )
        )
        svc._adaptive_coordinator = mock_coordinator

        # Mock the retry path to return new content
        svc._retry_agent_execution = AsyncMock(
            return_value={"summary": "improved content"}
        )

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        assert result.get("verification_result") is not None
        assert result["verification_result"]["passed"] is True
        assert "escalated" not in result
        mock_trust.update_on_success.assert_called_once_with("u1", "research")
        # Verify was called twice: original + retry
        assert mock_verifier.verify.call_count == 2

    @pytest.mark.asyncio
    async def test_verification_feedback_injected_into_retry(self):
        """Retry execution receives verification issues in context."""
        svc = _make_goal_execution_service()

        failed_result = _make_failed_verification_result(
            issues=["Missing citation for claim X"]
        )
        passed_result = _make_passed_verification_result()

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(side_effect=[failed_result, passed_result])

        from src.core.adaptive_coordinator import (
            AdaptiveDecision,
            AdaptiveDecisionType,
            FailureAnalysis,
            FailureTrigger,
        )

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate_output = MagicMock(
            return_value=AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=FailureAnalysis(
                    trigger=FailureTrigger.VERIFICATION_FAILED,
                    severity=0.7,
                    details="Verification rejected",
                    recoverable=True,
                ),
                target_agent=None,
                retry_params={
                    "verification_feedback": "Missing citation for claim X",
                    "address_issues": ["Missing citation for claim X"],
                },
                partial_results={},
                reasoning="Retrying with feedback",
                retry_count=1,
            )
        )
        svc._adaptive_coordinator = mock_coordinator
        svc._retry_agent_execution = AsyncMock(
            return_value={"summary": "fixed content"}
        )

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        # Check that _retry_agent_execution was called with verification feedback in context
        retry_call = svc._retry_agent_execution.call_args
        retry_ctx = retry_call.kwargs.get("context", {})
        assert "verification_feedback" in retry_ctx
        assert "Missing citation for claim X" in retry_ctx["verification_feedback"]


class TestVerificationEscalates:
    """Verification fails and retries are exhausted."""

    @pytest.mark.asyncio
    async def test_escalation_when_coordinator_says_escalate(self):
        """Coordinator returns ESCALATE → result has escalated=True, trust updated on failure."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_failure = AsyncMock(return_value=0.21)
        svc._trust_service = mock_trust

        failed_result = _make_failed_verification_result()
        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=failed_result)

        from src.core.adaptive_coordinator import (
            AdaptiveDecision,
            AdaptiveDecisionType,
            FailureAnalysis,
            FailureTrigger,
        )

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate_output = MagicMock(
            return_value=AdaptiveDecision(
                decision_type=AdaptiveDecisionType.ESCALATE,
                failure_analysis=FailureAnalysis(
                    trigger=FailureTrigger.VERIFICATION_FAILED,
                    severity=0.7,
                    details="Verification rejected output",
                    recoverable=False,
                ),
                target_agent=None,
                partial_results={},
                reasoning="Retry budget exhausted",
                retry_count=3,
            )
        )
        svc._adaptive_coordinator = mock_coordinator

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]  # Execution still "succeeds" but escalated
        assert result.get("escalated") is True
        assert "escalation_reason" in result
        mock_trust.update_on_failure.assert_called_once_with("u1", "research")

    @pytest.mark.asyncio
    async def test_escalation_after_retry_still_fails(self):
        """First verify fails, retry content also fails → escalation."""
        svc = _make_goal_execution_service()

        mock_trust = MagicMock()
        mock_trust.update_on_failure = AsyncMock(return_value=0.21)
        svc._trust_service = mock_trust

        failed_result_1 = _make_failed_verification_result(
            issues=["Issue A"]
        )
        failed_result_2 = _make_failed_verification_result(
            issues=["Issue B persists"]
        )

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(
            side_effect=[failed_result_1, failed_result_2]
        )

        from src.core.adaptive_coordinator import (
            AdaptiveDecision,
            AdaptiveDecisionType,
            FailureAnalysis,
            FailureTrigger,
        )

        mock_coordinator = MagicMock()
        mock_coordinator.evaluate_output = MagicMock(
            return_value=AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=FailureAnalysis(
                    trigger=FailureTrigger.VERIFICATION_FAILED,
                    severity=0.7,
                    details="Verification rejected",
                    recoverable=True,
                ),
                target_agent=None,
                retry_params={},
                partial_results={},
                reasoning="Retrying",
                retry_count=1,
            )
        )
        svc._adaptive_coordinator = mock_coordinator
        svc._retry_agent_execution = AsyncMock(
            return_value={"summary": "still bad content"}
        )

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]  # Execution completes but escalated
        assert result.get("escalated") is True
        mock_trust.update_on_failure.assert_called_once_with("u1", "research")


class TestVerificationFailOpen:
    """Verification infrastructure errors should not block execution."""

    @pytest.mark.asyncio
    async def test_verifier_import_error_skips_verification(self):
        """If VerifierAgent import fails, content passes through unverified."""
        svc = _make_goal_execution_service()

        with patch(
            "src.services.goal_execution.VerifierAgent",
            side_effect=ImportError("module not found"),
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        assert result.get("verification_result") is None

    @pytest.mark.asyncio
    async def test_verify_exception_skips_verification(self):
        """If verify() raises, content passes through unverified."""
        svc = _make_goal_execution_service()

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        assert result.get("verification_result") is None

    @pytest.mark.asyncio
    async def test_no_coordinator_returns_content_on_failure(self):
        """If coordinator is None and verification fails, content passes through escalated."""
        svc = _make_goal_execution_service()
        svc._adaptive_coordinator = None

        failed_result = _make_failed_verification_result()
        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=failed_result)

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        # With no coordinator, verification failure should escalate
        assert result.get("escalated") is True


class TestTraceIncludesVerification:
    """Delegation traces should include verification_result."""

    @pytest.mark.asyncio
    async def test_complete_trace_receives_verification_result(self):
        """complete_trace() is called with verification_result dict."""
        svc = _make_goal_execution_service()

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-v1")
        mock_traces.complete_trace = AsyncMock()
        svc._trace_service = mock_traces

        passed_result = _make_passed_verification_result()
        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=passed_result)

        with patch(
            "src.services.goal_execution.VerifierAgent",
            return_value=mock_verifier,
        ):
            result = await svc._execute_agent(
                user_id="u1",
                goal={"id": "g1", "title": "Test", "config": {}},
                agent_type="analyst",
                context={},
            )

        assert result["success"]
        mock_traces.complete_trace.assert_called_once()
        call_kwargs = mock_traces.complete_trace.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-v1"
        assert call_kwargs["verification_result"] is not None
        assert call_kwargs["verification_result"]["passed"] is True

    @pytest.mark.asyncio
    async def test_trace_receives_none_when_verification_skipped(self):
        """Trace receives verification_result=None for agents without policies."""
        svc = _make_goal_execution_service()

        mock_traces = MagicMock()
        mock_traces.start_trace = AsyncMock(return_value="trace-op1")
        mock_traces.complete_trace = AsyncMock()
        svc._trace_service = mock_traces

        result = await svc._execute_agent(
            user_id="u1",
            goal={"id": "g1", "title": "Test", "config": {}},
            agent_type="operator",
            context={},
        )

        assert result["success"]
        mock_traces.complete_trace.assert_called_once()
        call_kwargs = mock_traces.complete_trace.call_args.kwargs
        assert call_kwargs.get("verification_result") is None
