"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    """Current execution status of an agent."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result of an agent execution.

    Captures success/failure status, output data, error information,
    and execution metrics.
    """

    success: bool
    data: Any
    error: str | None = None
    tokens_used: int = 0
    execution_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "execution_time_ms": self.execution_time_ms,
        }
