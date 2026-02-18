"""AdaptiveCoordinator — retry/re-delegation decision engine.

Monitors agent execution results and decides whether to proceed, retry
with the same agent (different parameters), re-delegate to a different
agent, augment with a second agent for cross-verification, or escalate
to the user.

Design constraints:
  - Pure decision logic + delegation trace logging (no LLM calls)
  - No direct database access (callers handle I/O)
  - Fail-open: never crash if trace logging fails
  - All retry attempts gated by CostGovernor to prevent infinite loops
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.cost_governor import CostGovernor

if TYPE_CHECKING:
    from src.core.delegation_trace import DelegationTraceService
    from src.core.task_characteristics import TaskCharacteristics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOW_CONFIDENCE_THRESHOLD: float = 0.5
STALE_DATA_HOURS: int = 24
TIMEOUT_MULTIPLIER: float = 2.0
HIGH_RISK_THRESHOLD: float = 0.7

_EMPTY_RESULT_KEYS = ("items", "results", "data", "competitors", "prospects", "signals")

RE_DELEGATION_MAP: dict[str, list[str]] = {
    "scout": ["analyst", "hunter"],
    "analyst": ["scout", "strategist"],
    "hunter": ["scout", "analyst"],
    "strategist": ["analyst", "scribe"],
    "scribe": ["strategist"],
    "operator": [],
    "verifier": [],
    "executor": [],
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FailureTrigger(str, Enum):
    """Why the agent output was deemed unsatisfactory."""

    LOW_CONFIDENCE = "low_confidence"
    NO_RESULTS = "no_results"
    STALE_DATA = "stale_data"
    TIMEOUT = "timeout"
    VERIFICATION_FAILED = "verification_failed"


class AdaptiveDecisionType(str, Enum):
    """What the coordinator decides to do."""

    PROCEED = "proceed"
    RETRY_SAME = "retry_same"
    RE_DELEGATE = "re_delegate"
    AUGMENT = "augment"
    ESCALATE = "escalate"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FailureAnalysis:
    """Result of analyzing what went wrong with an agent output."""

    trigger: FailureTrigger
    severity: float
    details: str
    recoverable: bool


@dataclass
class AdaptiveDecision:
    """The coordinator's decision about how to handle an agent output."""

    decision_type: AdaptiveDecisionType
    failure_analysis: FailureAnalysis | None
    target_agent: str | None
    retry_params: dict[str, Any] = field(default_factory=dict)
    partial_results: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    retry_count: int = 0


@dataclass
class AgentOutputEvaluation:
    """Input structure wrapping agent output + metadata for evaluation."""

    agent_type: str
    goal_id: str
    output: dict[str, Any]
    confidence: float
    execution_time_ms: int
    expected_duration_ms: int
    verification_result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class AdaptiveCoordinator:
    """Monitors agent execution and decides on retry/re-delegation strategy."""

    def __init__(
        self,
        cost_governor: CostGovernor | None = None,
        trace_service: DelegationTraceService | None = None,
    ) -> None:
        self._cost_governor = cost_governor or CostGovernor()
        self._trace_service = trace_service

    def evaluate_output(
        self,
        evaluation: AgentOutputEvaluation,
        task_characteristics: TaskCharacteristics | None = None,
    ) -> AdaptiveDecision:
        """Evaluate an agent's output and decide what to do next."""
        failure = self._analyze_failure(evaluation)

        if failure is None:
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.PROCEED,
                failure_analysis=None,
                target_agent=None,
                partial_results=evaluation.output or {},
                reasoning="Output is acceptable",
                retry_count=0,
            )

        if not self._cost_governor.check_retry_budget(evaluation.goal_id):
            return self._make_escalation(
                failure=failure,
                evaluation=evaluation,
                reasoning=(
                    f"Retry budget exhausted for goal {evaluation.goal_id}. "
                    f"Failure: {failure.trigger.value} — {failure.details}"
                ),
            )

        retry_count = self._cost_governor.record_retry(evaluation.goal_id)

        return self._determine_decision(
            failure=failure,
            evaluation=evaluation,
            task_characteristics=task_characteristics,
            retry_count=retry_count,
        )

    def _analyze_failure(
        self,
        evaluation: AgentOutputEvaluation,
    ) -> FailureAnalysis | None:
        """Detect what (if anything) is wrong with the output.

        Priority: verification_failed > no_results > low_confidence > timeout > stale_data.
        Returns None if output is acceptable.
        """
        # 1. Verification failure (highest priority)
        vr = evaluation.verification_result
        if vr is not None and vr.get("passed") is False:
            reason = vr.get("reason", "Verification rejected output")
            return FailureAnalysis(
                trigger=FailureTrigger.VERIFICATION_FAILED,
                severity=0.7,
                details=f"Verifier rejected: {reason}",
                recoverable=True,
            )

        # 2. No results
        if self._is_empty_output(evaluation.output):
            return FailureAnalysis(
                trigger=FailureTrigger.NO_RESULTS,
                severity=0.8,
                details="Agent produced no meaningful results",
                recoverable=True,
            )

        # 3. Low confidence
        if evaluation.confidence < LOW_CONFIDENCE_THRESHOLD:
            return FailureAnalysis(
                trigger=FailureTrigger.LOW_CONFIDENCE,
                severity=round(1.0 - evaluation.confidence, 2),
                details=(
                    f"Confidence {evaluation.confidence:.2f} "
                    f"below threshold {LOW_CONFIDENCE_THRESHOLD}"
                ),
                recoverable=True,
            )

        # 4. Timeout
        threshold_ms = evaluation.expected_duration_ms * TIMEOUT_MULTIPLIER
        if evaluation.execution_time_ms > threshold_ms:
            return FailureAnalysis(
                trigger=FailureTrigger.TIMEOUT,
                severity=0.5,
                details=(
                    f"Execution took {evaluation.execution_time_ms}ms, "
                    f"expected <{threshold_ms:.0f}ms"
                ),
                recoverable=True,
            )

        # 5. Stale data
        if self._has_stale_data(evaluation.output):
            return FailureAnalysis(
                trigger=FailureTrigger.STALE_DATA,
                severity=0.4,
                details=f"Data older than {STALE_DATA_HOURS} hours",
                recoverable=True,
            )

        return None

    @staticmethod
    def _is_empty_output(output: dict[str, Any] | None) -> bool:
        """Check whether the output is effectively empty."""
        if output is None or len(output) == 0:
            return True
        for key in _EMPTY_RESULT_KEYS:
            if key in output:
                val = output[key]
                if val is not None and val != [] and val != {}:
                    return False
        has_content = any(
            v is not None and v != [] and v != {} and v != ""
            for k, v in output.items()
            if k not in _EMPTY_RESULT_KEYS
        )
        return not has_content

    @staticmethod
    def _has_stale_data(output: dict[str, Any] | None) -> bool:
        """Check if output metadata indicates stale data."""
        if output is None:
            return False
        from datetime import UTC, datetime, timedelta

        ts = output.get("data_timestamp") or output.get("fetched_at")
        if ts is None:
            return False
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                dt = ts
            else:
                return False
            threshold = datetime.now(UTC) - timedelta(hours=STALE_DATA_HOURS)
            return dt < threshold
        except (ValueError, TypeError):
            return False

    def get_re_delegation_target(
        self,
        failed_agent: str,
        already_tried: list[str] | None = None,
    ) -> str | None:
        """Find the best alternative agent for re-delegation."""
        candidates = RE_DELEGATION_MAP.get(failed_agent, [])
        tried = set(already_tried or [])
        for candidate in candidates:
            if candidate not in tried:
                return candidate
        return None

    # ------------------------------------------------------------------
    # Private decision helpers
    # ------------------------------------------------------------------

    def _determine_decision(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        task_characteristics: TaskCharacteristics | None,
        retry_count: int,
    ) -> AdaptiveDecision:
        """Dispatch to the appropriate per-trigger decision method."""
        is_high_risk = (
            task_characteristics is not None
            and task_characteristics.risk_score > HIGH_RISK_THRESHOLD
        )
        effective_count = retry_count + 1 if is_high_risk else retry_count

        dispatch = {
            FailureTrigger.LOW_CONFIDENCE: self._decide_low_confidence,
            FailureTrigger.NO_RESULTS: self._decide_no_results,
            FailureTrigger.STALE_DATA: self._decide_stale_data,
            FailureTrigger.TIMEOUT: self._decide_timeout,
            FailureTrigger.VERIFICATION_FAILED: self._decide_verification_failed,
        }
        handler = dispatch.get(failure.trigger, self._decide_fallback)
        return handler(
            failure=failure,
            evaluation=evaluation,
            effective_count=effective_count,
            retry_count=retry_count,
        )

    def _decide_low_confidence(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,
        retry_count: int,
    ) -> AdaptiveDecision:
        if effective_count <= 1:
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=failure,
                target_agent=None,
                retry_params={"refine_query": True, "increase_depth": True},
                partial_results=evaluation.output or {},
                reasoning=f"Low confidence ({failure.details}), retrying with refined query",
                retry_count=retry_count,
            )
        if effective_count <= 2:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RE_DELEGATE,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=f"Low confidence persists after retry, re-delegating to {target}",
                retry_count=retry_count,
            )
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _decide_no_results(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,
        retry_count: int,
    ) -> AdaptiveDecision:
        if effective_count <= 1:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RE_DELEGATE,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=f"No results from {evaluation.agent_type}, re-delegating to {target}",
                retry_count=retry_count,
            )
        if effective_count <= 2:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.AUGMENT,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=(
                    f"No results after re-delegation, augmenting with {target} "
                    "for cross-verification"
                ),
                retry_count=retry_count,
            )
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _decide_stale_data(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,
        retry_count: int,
    ) -> AdaptiveDecision:
        if effective_count <= 1:
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=failure,
                target_agent=None,
                retry_params={"force_refresh": True},
                partial_results=evaluation.output or {},
                reasoning="Data is stale, retrying with forced refresh",
                retry_count=retry_count,
            )
        if effective_count <= 2:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RE_DELEGATE,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=f"Stale data persists, re-delegating to {target}",
                retry_count=retry_count,
            )
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _decide_timeout(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,
        retry_count: int,
    ) -> AdaptiveDecision:
        if effective_count <= 1:
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=failure,
                target_agent=None,
                retry_params={"timeout_extended": True},
                partial_results=evaluation.output or {},
                reasoning="Agent timed out, retrying with extended timeout",
                retry_count=retry_count,
            )
        if effective_count <= 2:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RE_DELEGATE,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=f"Timeout persists, re-delegating to {target}",
                retry_count=retry_count,
            )
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _decide_verification_failed(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,
        retry_count: int,
    ) -> AdaptiveDecision:
        vr = evaluation.verification_result or {}
        reason = vr.get("reason", "")
        issues = vr.get("issues", [])
        if effective_count <= 1:
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RETRY_SAME,
                failure_analysis=failure,
                target_agent=None,
                retry_params={
                    "verification_feedback": reason,
                    "address_issues": issues,
                },
                partial_results=evaluation.output or {},
                reasoning=f"Verification failed ({reason}), retrying with feedback",
                retry_count=retry_count,
            )
        if effective_count <= 2:
            target = self.get_re_delegation_target(evaluation.agent_type)
            return AdaptiveDecision(
                decision_type=AdaptiveDecisionType.RE_DELEGATE,
                failure_analysis=failure,
                target_agent=target,
                partial_results=evaluation.output or {},
                reasoning=f"Verification still failing, re-delegating to {target}",
                retry_count=retry_count,
            )
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _decide_fallback(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        effective_count: int,  # noqa: ARG002
        retry_count: int,
    ) -> AdaptiveDecision:
        return self._make_escalation(failure, evaluation, retry_count=retry_count)

    def _make_escalation(
        self,
        failure: FailureAnalysis,
        evaluation: AgentOutputEvaluation,
        reasoning: str = "",
        retry_count: int = 0,
    ) -> AdaptiveDecision:
        return AdaptiveDecision(
            decision_type=AdaptiveDecisionType.ESCALATE,
            failure_analysis=failure,
            target_agent=None,
            partial_results=evaluation.output or {},
            reasoning=reasoning
            or (f"Escalating to user: {failure.trigger.value} — {failure.details}"),
            retry_count=retry_count or self._cost_governor._retry_counts.get(evaluation.goal_id, 0),
        )

    async def checkpoint_partial_results(
        self,
        goal_id: str,
        user_id: str,  # noqa: ARG002
        agent_type: str,
        partial_output: dict[str, Any],
        failure_analysis: FailureAnalysis,
        trace_id: str | None = None,
    ) -> None:
        """Save partial work before re-delegation (fail-open)."""
        if self._trace_service is None:
            logger.debug(
                "No trace service — skipping checkpoint for %s on goal %s",
                agent_type,
                goal_id,
            )
            return

        try:
            if trace_id:
                await self._trace_service.complete_trace(
                    trace_id=trace_id,
                    outputs={
                        "partial_results": partial_output,
                        "failure_trigger": failure_analysis.trigger.value,
                        "failure_details": failure_analysis.details,
                    },
                    verification_result=None,
                    cost_usd=0.0,
                    status="re_delegated",
                )
            logger.info(
                "Checkpointed partial results for %s on goal %s (trigger=%s)",
                agent_type,
                goal_id,
                failure_analysis.trigger.value,
            )
        except Exception:
            logger.warning(
                "Failed to checkpoint partial results (fail-open)",
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_coordinator: AdaptiveCoordinator | None = None


def get_adaptive_coordinator() -> AdaptiveCoordinator:
    """Get or create the module-level AdaptiveCoordinator singleton."""
    global _coordinator  # noqa: PLW0603
    if _coordinator is None:
        _coordinator = AdaptiveCoordinator()
    return _coordinator
