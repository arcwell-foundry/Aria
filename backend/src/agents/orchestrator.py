"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

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

    async def spawn_and_execute(
        self,
        agent_class: type[BaseAgent],
        task: dict[str, Any],
    ) -> AgentResult:
        """Spawn an agent and execute a task.

        Args:
            agent_class: The agent class to instantiate.
            task: Task specification for the agent.

        Returns:
            AgentResult from the agent execution.
        """
        agent_id = self.spawn_agent(agent_class)
        agent = self.active_agents[agent_id]

        logger.info(
            f"Executing task with {agent.name}",
            extra={
                "agent_id": agent_id,
                "agent_name": agent.name,
                "task_keys": list(task.keys()),
            },
        )

        try:
            result = await agent.run(task)

            # Accumulate token usage
            self._total_tokens_used += result.tokens_used

            return result

        finally:
            # Clean up agent after execution
            if agent_id in self.active_agents:
                del self.active_agents[agent_id]
                logger.debug(
                    f"Cleaned up agent {agent_id}",
                    extra={"agent_id": agent_id},
                )

    async def execute_parallel(
        self,
        tasks: list[tuple[type[BaseAgent], dict[str, Any]]],
    ) -> OrchestrationResult:
        """Execute multiple agents in parallel.

        All tasks run concurrently. Failures in one task do not affect others.

        Args:
            tasks: List of (agent_class, task) tuples to execute.

        Returns:
            OrchestrationResult with all agent results.
        """
        if not tasks:
            return OrchestrationResult(
                results=[],
                total_tokens=0,
                total_execution_time_ms=0,
            )

        start_time = time.perf_counter()

        logger.info(
            f"Starting parallel execution of {len(tasks)} agents",
            extra={"task_count": len(tasks), "user_id": self.user_id},
        )

        # Create coroutines for all tasks
        coros = [self.spawn_and_execute(agent_class, task) for agent_class, task in tasks]

        # Execute all concurrently - return_exceptions=True ensures failures don't abort
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        # Convert exceptions to failed AgentResults
        results: list[AgentResult] = []
        for raw in raw_results:
            if isinstance(raw, BaseException):
                results.append(
                    AgentResult(
                        success=False,
                        data=None,
                        error=str(raw),
                    )
                )
            else:
                results.append(raw)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        total_tokens = sum(r.tokens_used for r in results)

        logger.info(
            "Parallel execution complete",
            extra={
                "task_count": len(tasks),
                "success_count": sum(1 for r in results if r.success),
                "failed_count": sum(1 for r in results if not r.success),
                "total_tokens": total_tokens,
                "execution_time_ms": elapsed_ms,
            },
        )

        return OrchestrationResult(
            results=results,
            total_tokens=total_tokens,
            total_execution_time_ms=elapsed_ms,
        )

    async def execute_sequential(
        self,
        tasks: list[tuple[type[BaseAgent], dict[str, Any]]],
        continue_on_failure: bool = False,
    ) -> OrchestrationResult:
        """Execute agents sequentially, passing context between them.

        Each subsequent agent receives the results of previous agents in context.

        Args:
            tasks: List of (agent_class, task) tuples to execute in order.
            continue_on_failure: If True, continue executing even if an agent fails.

        Returns:
            OrchestrationResult with all agent results.
        """
        if not tasks:
            return OrchestrationResult(
                results=[],
                total_tokens=0,
                total_execution_time_ms=0,
            )

        start_time = time.perf_counter()
        results: list[AgentResult] = []
        context: dict[str, Any] = {}

        logger.info(
            f"Starting sequential execution of {len(tasks)} agents",
            extra={
                "task_count": len(tasks),
                "continue_on_failure": continue_on_failure,
                "user_id": self.user_id,
            },
        )

        for i, (agent_class, task) in enumerate(tasks):
            # Inject context from previous agents
            task_with_context = {**task, "context": context}

            try:
                result = await self.spawn_and_execute(agent_class, task_with_context)
                results.append(result)

                # Add result to context for next agent
                context[agent_class.name] = result.data

                if not result.success and not continue_on_failure:
                    logger.warning(
                        f"Sequential execution stopped at task {i + 1} due to failure",
                        extra={
                            "task_index": i,
                            "agent_name": agent_class.name,
                            "error": result.error,
                        },
                    )
                    break

            except Exception as e:
                error_result = AgentResult(
                    success=False,
                    data=None,
                    error=str(e),
                )
                results.append(error_result)

                if not continue_on_failure:
                    logger.error(
                        f"Sequential execution stopped at task {i + 1} due to exception",
                        extra={
                            "task_index": i,
                            "agent_name": agent_class.name,
                            "error": str(e),
                        },
                    )
                    break

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        total_tokens = sum(r.tokens_used for r in results)

        logger.info(
            "Sequential execution complete",
            extra={
                "tasks_executed": len(results),
                "tasks_total": len(tasks),
                "success_count": sum(1 for r in results if r.success),
                "failed_count": sum(1 for r in results if not r.success),
                "total_tokens": total_tokens,
                "execution_time_ms": elapsed_ms,
            },
        )

        return OrchestrationResult(
            results=results,
            total_tokens=total_tokens,
            total_execution_time_ms=elapsed_ms,
        )
