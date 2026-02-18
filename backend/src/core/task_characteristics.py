"""TaskCharacteristics — dynamic risk scoring for OODA decisions.

Replaces static risk classification with a computed 7-dimension risk profile.
Each dimension is 0.0–1.0, and the weighted ``risk_score`` property drives
thinking effort, approval level, and risk label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Token budgets for extended thinking at each effort level
THINKING_BUDGETS: dict[str, int] = {
    "routine": 4096,
    "complex": 16384,
    "critical": 32768,
}

# Default dimension values keyed by action type
_ACTION_DEFAULTS: dict[str, dict[str, float]] = {
    "research": {
        "complexity": 0.3,
        "criticality": 0.2,
        "uncertainty": 0.4,
        "reversibility": 1.0,
        "verifiability": 0.8,
        "subjectivity": 0.2,
        "contextuality": 0.3,
    },
    "search": {
        "complexity": 0.2,
        "criticality": 0.2,
        "uncertainty": 0.3,
        "reversibility": 1.0,
        "verifiability": 0.9,
        "subjectivity": 0.1,
        "contextuality": 0.2,
    },
    "communicate": {
        "complexity": 0.5,
        "criticality": 0.7,
        "uncertainty": 0.4,
        "reversibility": 0.1,
        "verifiability": 0.5,
        "subjectivity": 0.7,
        "contextuality": 0.8,
    },
    "schedule": {
        "complexity": 0.3,
        "criticality": 0.5,
        "uncertainty": 0.2,
        "reversibility": 0.6,
        "verifiability": 0.9,
        "subjectivity": 0.1,
        "contextuality": 0.4,
    },
    "monitor": {
        "complexity": 0.2,
        "criticality": 0.2,
        "uncertainty": 0.3,
        "reversibility": 1.0,
        "verifiability": 0.7,
        "subjectivity": 0.2,
        "contextuality": 0.3,
    },
    "plan": {
        "complexity": 0.6,
        "criticality": 0.4,
        "uncertainty": 0.5,
        "reversibility": 0.9,
        "verifiability": 0.4,
        "subjectivity": 0.6,
        "contextuality": 0.7,
    },
}

_DEFAULT_DIMS: dict[str, float] = {
    "complexity": 0.5,
    "criticality": 0.5,
    "uncertainty": 0.5,
    "reversibility": 0.5,
    "verifiability": 0.5,
    "subjectivity": 0.5,
    "contextuality": 0.5,
}


@dataclass
class TaskCharacteristics:
    """Seven-dimension risk profile for a task.

    Each dimension is 0.0–1.0. Higher means more of that quality.
    ``reversibility`` is inverted in the risk formula: 1.0 = fully reversible
    (low risk), 0.0 = irreversible (high risk).
    """

    complexity: float = 0.5
    criticality: float = 0.5
    uncertainty: float = 0.5
    reversibility: float = 0.5
    verifiability: float = 0.5
    subjectivity: float = 0.5
    contextuality: float = 0.5

    @property
    def risk_score(self) -> float:
        """Weighted risk score (0.0–1.0) per CLAUDE.md formula."""
        return (
            self.criticality * 0.3
            + (1 - self.reversibility) * 0.25
            + self.uncertainty * 0.2
            + self.complexity * 0.15
            + self.contextuality * 0.1
        )

    @property
    def thinking_effort(self) -> str:
        """Map risk_score to thinking effort level."""
        score = self.risk_score
        if score > 0.7:
            return "critical"
        if score > 0.4:
            return "complex"
        return "routine"

    @property
    def approval_level(self) -> str:
        """Map risk_score to approval level."""
        score = self.risk_score
        if score > 0.75:
            return "APPROVE_EACH"
        if score > 0.5:
            return "APPROVE_PLAN"
        if score >= 0.2:
            return "EXECUTE_AND_NOTIFY"
        return "AUTO_EXECUTE"

    @property
    def risk_level(self) -> str:
        """Map risk_score to categorical risk level."""
        score = self.risk_score
        if score > 0.75:
            return "critical"
        if score > 0.5:
            return "high"
        if score >= 0.2:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary including computed properties."""
        return {
            "complexity": self.complexity,
            "criticality": self.criticality,
            "uncertainty": self.uncertainty,
            "reversibility": self.reversibility,
            "verifiability": self.verifiability,
            "subjectivity": self.subjectivity,
            "contextuality": self.contextuality,
            "risk_score": round(self.risk_score, 4),
            "thinking_effort": self.thinking_effort,
            "approval_level": self.approval_level,
            "risk_level": self.risk_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskCharacteristics:
        """Create from dictionary, ignoring computed properties."""
        dims = (
            "complexity",
            "criticality",
            "uncertainty",
            "reversibility",
            "verifiability",
            "subjectivity",
            "contextuality",
        )
        kwargs = {k: float(data[k]) for k in dims if k in data}
        return cls(**kwargs)

    @classmethod
    def default_for_action(cls, action: str) -> TaskCharacteristics:
        """Return sensible baseline defaults for a known action type.

        Falls back to neutral 0.5 values for unknown actions.
        """
        dims = _ACTION_DEFAULTS.get(action, _DEFAULT_DIMS)
        return cls(**dims)
