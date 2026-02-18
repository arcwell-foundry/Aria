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
        raise NotImplementedError

    def _analyze_failure(
        self,
        evaluation: AgentOutputEvaluation,
    ) -> FailureAnalysis | None:
        raise NotImplementedError

    def get_re_delegation_target(
        self,
        failed_agent: str,
        already_tried: list[str] | None = None,
    ) -> str | None:
        raise NotImplementedError

    async def checkpoint_partial_results(
        self,
        goal_id: str,
        user_id: str,
        agent_type: str,
        partial_output: dict[str, Any],
        failure_analysis: FailureAnalysis,
        trace_id: str | None = None,
    ) -> None:
        raise NotImplementedError


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
