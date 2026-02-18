"""Tests for AdaptiveCoordinator — retry/re-delegation decision engine."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.adaptive_coordinator import (
    LOW_CONFIDENCE_THRESHOLD,
    RE_DELEGATION_MAP,
    STALE_DATA_HOURS,
    TIMEOUT_MULTIPLIER,
    AdaptiveCoordinator,
    AdaptiveDecision,
    AdaptiveDecisionType,
    AgentOutputEvaluation,
    FailureAnalysis,
    FailureTrigger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evaluation(
    agent_type: str = "scout",
    goal_id: str = "goal-1",
    output: dict[str, Any] | None = None,
    confidence: float = 0.8,
    execution_time_ms: int = 5000,
    expected_duration_ms: int = 10000,
    verification_result: dict[str, Any] | None = None,
) -> AgentOutputEvaluation:
    """Build a test AgentOutputEvaluation."""
    return AgentOutputEvaluation(
        agent_type=agent_type,
        goal_id=goal_id,
        output=output if output is not None else {"summary": "Found 3 competitors", "items": [1, 2, 3]},
        confidence=confidence,
        execution_time_ms=execution_time_ms,
        expected_duration_ms=expected_duration_ms,
        verification_result=verification_result,
    )


def _make_coordinator(
    max_retries: int = 3,
    retry_counts: dict[str, int] | None = None,
    trace_service: Any = None,
) -> AdaptiveCoordinator:
    """Build a coordinator with a real CostGovernor (mocked settings)."""
    mock_settings = SimpleNamespace(COST_GOVERNOR_MAX_RETRIES_PER_GOAL=max_retries)
    with patch("src.core.cost_governor._get_settings", return_value=mock_settings):
        from src.core.cost_governor import CostGovernor

        governor = CostGovernor()
        if retry_counts:
            governor._retry_counts = dict(retry_counts)
        coordinator = AdaptiveCoordinator(
            cost_governor=governor,
            trace_service=trace_service,
        )
    return coordinator


# ---------------------------------------------------------------------------
# Enum / dataclass tests
# ---------------------------------------------------------------------------


class TestFailureTrigger:
    """Tests for the FailureTrigger enum."""

    def test_all_triggers_are_strings(self) -> None:
        for trigger in FailureTrigger:
            assert isinstance(trigger.value, str)

    def test_expected_triggers_exist(self) -> None:
        assert FailureTrigger.LOW_CONFIDENCE.value == "low_confidence"
        assert FailureTrigger.NO_RESULTS.value == "no_results"
        assert FailureTrigger.STALE_DATA.value == "stale_data"
        assert FailureTrigger.TIMEOUT.value == "timeout"
        assert FailureTrigger.VERIFICATION_FAILED.value == "verification_failed"


class TestAdaptiveDecisionType:
    """Tests for the AdaptiveDecisionType enum."""

    def test_all_decision_types_exist(self) -> None:
        assert AdaptiveDecisionType.PROCEED.value == "proceed"
        assert AdaptiveDecisionType.RETRY_SAME.value == "retry_same"
        assert AdaptiveDecisionType.RE_DELEGATE.value == "re_delegate"
        assert AdaptiveDecisionType.AUGMENT.value == "augment"
        assert AdaptiveDecisionType.ESCALATE.value == "escalate"


class TestFailureAnalysis:
    """Tests for the FailureAnalysis dataclass."""

    def test_creation(self) -> None:
        fa = FailureAnalysis(
            trigger=FailureTrigger.LOW_CONFIDENCE,
            severity=0.6,
            details="Confidence 0.3 below threshold",
            recoverable=True,
        )
        assert fa.trigger == FailureTrigger.LOW_CONFIDENCE
        assert fa.severity == 0.6
        assert fa.recoverable is True


class TestAdaptiveDecision:
    """Tests for the AdaptiveDecision dataclass."""

    def test_proceed_decision_has_no_failure(self) -> None:
        decision = AdaptiveDecision(
            decision_type=AdaptiveDecisionType.PROCEED,
            failure_analysis=None,
            target_agent=None,
            retry_params={},
            partial_results={"summary": "ok"},
            reasoning="Output is acceptable",
            retry_count=0,
        )
        assert decision.decision_type == AdaptiveDecisionType.PROCEED
        assert decision.failure_analysis is None


class TestAgentOutputEvaluation:
    """Tests for the AgentOutputEvaluation dataclass."""

    def test_creation(self) -> None:
        ev = _make_evaluation()
        assert ev.agent_type == "scout"
        assert ev.goal_id == "goal-1"
        assert ev.confidence == 0.8


class TestConstants:
    """Tests for module-level constants."""

    def test_low_confidence_threshold(self) -> None:
        assert LOW_CONFIDENCE_THRESHOLD == 0.5

    def test_stale_data_hours(self) -> None:
        assert STALE_DATA_HOURS == 24

    def test_timeout_multiplier(self) -> None:
        assert TIMEOUT_MULTIPLIER == 2.0

    def test_re_delegation_map_has_all_agents(self) -> None:
        expected = {"scout", "analyst", "hunter", "strategist", "scribe", "operator", "verifier", "executor"}
        assert set(RE_DELEGATION_MAP.keys()) == expected

    def test_re_delegation_map_operator_has_no_fallback(self) -> None:
        assert RE_DELEGATION_MAP["operator"] == []

    def test_re_delegation_map_scout_fallbacks(self) -> None:
        assert "analyst" in RE_DELEGATION_MAP["scout"]
        assert "hunter" in RE_DELEGATION_MAP["scout"]


# ---------------------------------------------------------------------------
# Failure analysis tests
# ---------------------------------------------------------------------------


class TestAnalyzeFailure:
    """Tests for AdaptiveCoordinator._analyze_failure()."""

    def test_no_failure_for_good_output(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.8)
        result = coordinator._analyze_failure(ev)
        assert result is None

    def test_low_confidence_detected(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.3)
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.LOW_CONFIDENCE
        assert result.recoverable is True

    def test_no_results_detected_empty_output(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(output={}, confidence=0.8)
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.NO_RESULTS

    def test_no_results_detected_none_values(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(
            output={"items": [], "results": [], "data": None},
            confidence=0.8,
        )
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.NO_RESULTS

    def test_timeout_detected(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(execution_time_ms=25000, expected_duration_ms=10000)
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.TIMEOUT

    def test_timeout_not_triggered_at_boundary(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(execution_time_ms=20000, expected_duration_ms=10000)
        result = coordinator._analyze_failure(ev)
        assert result is None

    def test_verification_failed_detected(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(
            verification_result={"passed": False, "reason": "Data inconsistency"},
        )
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.VERIFICATION_FAILED
        assert result.recoverable is True

    def test_verification_passed_is_not_failure(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(verification_result={"passed": True})
        result = coordinator._analyze_failure(ev)
        assert result is None

    def test_verification_failure_takes_priority(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(
            confidence=0.3,
            verification_result={"passed": False, "reason": "Bad data"},
        )
        result = coordinator._analyze_failure(ev)
        assert result is not None
        assert result.trigger == FailureTrigger.VERIFICATION_FAILED


# ---------------------------------------------------------------------------
# Decision logic tests
# ---------------------------------------------------------------------------


class TestEvaluateOutput:
    """Tests for AdaptiveCoordinator.evaluate_output()."""

    def test_proceed_for_good_output(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.8)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.PROCEED
        assert decision.failure_analysis is None

    def test_retry_same_for_low_confidence_first_attempt(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.RETRY_SAME
        assert decision.failure_analysis is not None
        assert decision.failure_analysis.trigger == FailureTrigger.LOW_CONFIDENCE
        assert "refine_query" in decision.retry_params

    def test_re_delegate_for_no_results_first_attempt(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(output={}, confidence=0.8)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.RE_DELEGATE
        assert decision.target_agent is not None
        assert decision.target_agent in RE_DELEGATION_MAP["scout"]

    def test_re_delegate_for_low_confidence_after_one_retry(self) -> None:
        coordinator = _make_coordinator(retry_counts={"goal-1": 1})
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.RE_DELEGATE

    def test_escalate_after_max_retries(self) -> None:
        coordinator = _make_coordinator(max_retries=3, retry_counts={"goal-1": 3})
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.ESCALATE

    def test_escalate_for_high_risk_one_step_earlier(self) -> None:
        from src.core.task_characteristics import TaskCharacteristics

        high_risk = TaskCharacteristics(
            criticality=0.9,
            reversibility=0.1,
            uncertainty=0.8,
            complexity=0.8,
            contextuality=0.7,
        )
        coordinator = _make_coordinator(retry_counts={"goal-1": 1})
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev, task_characteristics=high_risk)
        assert decision.decision_type == AdaptiveDecisionType.ESCALATE

    def test_retry_same_for_verification_failed_first_attempt(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(
            verification_result={"passed": False, "reason": "Missing sources"},
        )
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.RETRY_SAME
        assert "verification_feedback" in decision.retry_params

    def test_retry_same_for_timeout_first_attempt(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(execution_time_ms=25000, expected_duration_ms=10000)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.RETRY_SAME
        assert decision.retry_params.get("timeout_extended") is True

    def test_partial_results_preserved_in_decision(self) -> None:
        coordinator = _make_coordinator()
        partial = {"summary": "Found 1 of 3", "items": [{"name": "Novartis"}]}
        ev = _make_evaluation(output=partial, confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.partial_results == partial

    def test_augment_for_no_results_after_one_retry(self) -> None:
        coordinator = _make_coordinator(retry_counts={"goal-1": 1})
        ev = _make_evaluation(output={}, confidence=0.8)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.AUGMENT

    def test_retry_increments_cost_governor_count(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.3)
        coordinator.evaluate_output(ev)
        assert coordinator._cost_governor._retry_counts.get("goal-1", 0) >= 1


# ---------------------------------------------------------------------------
# Re-delegation mapping tests
# ---------------------------------------------------------------------------


class TestGetReDelegationTarget:
    """Tests for get_re_delegation_target()."""

    def test_scout_falls_back_to_analyst(self) -> None:
        coordinator = _make_coordinator()
        target = coordinator.get_re_delegation_target("scout")
        assert target == "analyst"

    def test_scout_skips_already_tried(self) -> None:
        coordinator = _make_coordinator()
        target = coordinator.get_re_delegation_target("scout", already_tried=["analyst"])
        assert target == "hunter"

    def test_returns_none_when_all_tried(self) -> None:
        coordinator = _make_coordinator()
        target = coordinator.get_re_delegation_target("scout", already_tried=["analyst", "hunter"])
        assert target is None

    def test_operator_has_no_fallback(self) -> None:
        coordinator = _make_coordinator()
        target = coordinator.get_re_delegation_target("operator")
        assert target is None

    def test_unknown_agent_returns_none(self) -> None:
        coordinator = _make_coordinator()
        target = coordinator.get_re_delegation_target("nonexistent_agent")
        assert target is None

    def test_re_delegate_decision_uses_mapping(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(agent_type="analyst", output={}, confidence=0.8)
        decision = coordinator.evaluate_output(ev)
        if decision.decision_type == AdaptiveDecisionType.RE_DELEGATE:
            assert decision.target_agent in RE_DELEGATION_MAP["analyst"]


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------


class TestCheckpointPartialResults:
    """Tests for checkpoint_partial_results()."""

    @pytest.mark.asyncio
    async def test_checkpoint_logs_to_trace_service(self) -> None:
        mock_trace = AsyncMock()
        coordinator = _make_coordinator(trace_service=mock_trace)

        await coordinator.checkpoint_partial_results(
            goal_id="goal-1",
            user_id="user-1",
            agent_type="scout",
            partial_output={"items": [1]},
            failure_analysis=FailureAnalysis(
                trigger=FailureTrigger.LOW_CONFIDENCE,
                severity=0.6,
                details="Low confidence",
                recoverable=True,
            ),
            trace_id="trace-abc",
        )

        mock_trace.complete_trace.assert_awaited_once()
        call_kwargs = mock_trace.complete_trace.call_args[1]
        assert call_kwargs["trace_id"] == "trace-abc"
        assert call_kwargs["status"] == "re_delegated"
        assert call_kwargs["outputs"]["partial_results"] == {"items": [1]}

    @pytest.mark.asyncio
    async def test_checkpoint_without_trace_service_is_noop(self) -> None:
        coordinator = _make_coordinator(trace_service=None)

        await coordinator.checkpoint_partial_results(
            goal_id="goal-1",
            user_id="user-1",
            agent_type="scout",
            partial_output={"items": [1]},
            failure_analysis=FailureAnalysis(
                trigger=FailureTrigger.LOW_CONFIDENCE,
                severity=0.6,
                details="test",
                recoverable=True,
            ),
        )

    @pytest.mark.asyncio
    async def test_checkpoint_swallows_trace_exceptions(self) -> None:
        mock_trace = AsyncMock()
        mock_trace.complete_trace.side_effect = RuntimeError("DB down")
        coordinator = _make_coordinator(trace_service=mock_trace)

        await coordinator.checkpoint_partial_results(
            goal_id="goal-1",
            user_id="user-1",
            agent_type="scout",
            partial_output={},
            failure_analysis=FailureAnalysis(
                trigger=FailureTrigger.TIMEOUT,
                severity=0.5,
                details="Timed out",
                recoverable=True,
            ),
            trace_id="trace-xyz",
        )


# ---------------------------------------------------------------------------
# CostGovernor budget enforcement tests
# ---------------------------------------------------------------------------


class TestCostGovernorEnforcement:
    """Tests that CostGovernor prevents infinite retry loops."""

    def test_budget_exhausted_forces_escalation(self) -> None:
        coordinator = _make_coordinator(max_retries=2, retry_counts={"goal-1": 2})
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type == AdaptiveDecisionType.ESCALATE

    def test_budget_allows_retry_within_limit(self) -> None:
        coordinator = _make_coordinator(max_retries=3, retry_counts={"goal-1": 0})
        ev = _make_evaluation(confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type != AdaptiveDecisionType.ESCALATE

    def test_different_goals_have_independent_budgets(self) -> None:
        coordinator = _make_coordinator(max_retries=2, retry_counts={"goal-1": 2})
        ev = _make_evaluation(goal_id="goal-2", confidence=0.3)
        decision = coordinator.evaluate_output(ev)
        assert decision.decision_type != AdaptiveDecisionType.ESCALATE

    def test_proceed_does_not_consume_retry_budget(self) -> None:
        coordinator = _make_coordinator()
        ev = _make_evaluation(confidence=0.8)
        coordinator.evaluate_output(ev)
        assert coordinator._cost_governor._retry_counts.get("goal-1", 0) == 0


# ---------------------------------------------------------------------------
# Singleton / module-level tests
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Tests for module-level exports and singleton."""

    def test_get_adaptive_coordinator_returns_instance(self) -> None:
        from src.core.adaptive_coordinator import get_adaptive_coordinator

        coordinator = get_adaptive_coordinator()
        assert isinstance(coordinator, AdaptiveCoordinator)
