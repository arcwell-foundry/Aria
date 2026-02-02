"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from src.agents.base import AgentResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Mode for executing multiple agent tasks."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass
class OrchestrationResult:
    """Result of orchestrating multiple agent executions.

    Tracks aggregate metrics across all agent runs.
    """

    results: list[AgentResult]
    total_tokens: int
    total_execution_time_ms: int

    @property
    def success_count(self) -> int:
        """Count of successful agent executions."""
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        """Count of failed agent executions."""
        return sum(1 for r in self.results if not r.success)

    @property
    def all_succeeded(self) -> bool:
        """Check if all agent executions succeeded."""
        return all(r.success for r in self.results)
