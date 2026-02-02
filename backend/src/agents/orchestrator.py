"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)

# Default resource limits for orchestration
DEFAULT_MAX_TOKENS = 100000
DEFAULT_MAX_CONCURRENT_AGENTS = 10


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


class AgentOrchestrator:
    """Coordinates multiple agents for complex goal execution.

    Supports parallel and sequential execution modes, graceful failure
    handling, progress reporting, and resource limit enforcement.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_concurrent_agents: int = DEFAULT_MAX_CONCURRENT_AGENTS,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            llm_client: LLM client for agent reasoning.
            user_id: ID of the user this orchestrator is working for.
            max_tokens: Maximum total tokens across all agent executions.
            max_concurrent_agents: Maximum agents to run in parallel.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.max_tokens = max_tokens
        self.max_concurrent_agents = max_concurrent_agents
        self.active_agents: dict[str, BaseAgent] = {}
        self._total_tokens_used = 0

    def spawn_agent(self, agent_class: type[BaseAgent]) -> str:
        """Spawn an agent and return its ID.

        Args:
            agent_class: The agent class to instantiate.

        Returns:
            Unique identifier for the spawned agent.
        """
        agent = agent_class(llm_client=self.llm, user_id=self.user_id)
        agent_id = str(uuid.uuid4())
        self.active_agents[agent_id] = agent

        logger.info(
            f"Spawned {agent.name} agent",
            extra={
                "agent_id": agent_id,
                "agent_name": agent.name,
                "user_id": self.user_id,
            },
        )

        return agent_id
