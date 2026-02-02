"""OODA loop cognitive processing module.

Implements the Observe-Orient-Decide-Act loop for systematic
reasoning about tasks. The OODA loop is ARIA's core cognitive
processing framework that iterates until goals are achieved.

Phases:
- Observe: Gather context from memory and environment
- Orient: Analyze situation, identify patterns
- Decide: Select best action from options
- Act: Execute chosen action

Each phase is logged for transparency and debugging.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OODAPhase(Enum):
    """Phases of the OODA loop cognitive cycle."""

    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"


@dataclass
class OODAPhaseLogEntry:
    """Log entry for a single OODA phase execution.

    Captures execution details for transparency and debugging.
    """

    phase: OODAPhase
    iteration: int
    input_summary: str
    output_summary: str
    tokens_used: int = 0
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "phase": self.phase.value,
            "iteration": self.iteration,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OODAState:
    """State of an OODA loop execution.

    Tracks the current phase, observations, analysis results,
    decisions, and action outcomes across iterations.
    """

    goal_id: str
    current_phase: OODAPhase = OODAPhase.OBSERVE
    observations: list[dict[str, Any]] = field(default_factory=list)
    orientation: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    action_result: Any = None
    iteration: int = 0
    max_iterations: int = 10
    phase_logs: list[OODAPhaseLogEntry] = field(default_factory=list)
    is_complete: bool = False
    is_blocked: bool = False
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "goal_id": self.goal_id,
            "current_phase": self.current_phase.value,
            "observations": self.observations,
            "orientation": self.orientation,
            "decision": self.decision,
            "action_result": self.action_result,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "phase_logs": [log.to_dict() for log in self.phase_logs],
            "is_complete": self.is_complete,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OODAState":
        """Create OODAState from dictionary.

        Args:
            data: Dictionary containing state data.

        Returns:
            OODAState instance with restored state.
        """
        state = cls(
            goal_id=data["goal_id"],
            current_phase=OODAPhase(data["current_phase"]),
            observations=data.get("observations", []),
            orientation=data.get("orientation", {}),
            decision=data.get("decision"),
            action_result=data.get("action_result"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 10),
            is_complete=data.get("is_complete", False),
            is_blocked=data.get("is_blocked", False),
            blocked_reason=data.get("blocked_reason"),
        )

        # Restore phase logs
        for log_data in data.get("phase_logs", []):
            state.phase_logs.append(
                OODAPhaseLogEntry(
                    phase=OODAPhase(log_data["phase"]),
                    iteration=log_data["iteration"],
                    input_summary=log_data["input_summary"],
                    output_summary=log_data["output_summary"],
                    tokens_used=log_data.get("tokens_used", 0),
                    duration_ms=log_data.get("duration_ms", 0),
                    timestamp=datetime.fromisoformat(log_data["timestamp"]),
                )
            )

        return state
