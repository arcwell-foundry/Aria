"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.core.capability_tokens import DelegationCapabilityToken

if TYPE_CHECKING:
    from src.core.delegation_trace import DelegationTraceService
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


@dataclass
class ProgressUpdate:
    """Progress update for orchestration monitoring.

    Provides real-time status updates during agent execution.
    """

    agent_name: str
    agent_id: str
    status: str  # "starting", "running", "complete", "failed"
    task_index: int
    total_tasks: int
    message: str


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
        delegation_trace_service: "DelegationTraceService | None" = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            llm_client: LLM client for agent reasoning.
            user_id: ID of the user this orchestrator is working for.
            max_tokens: Maximum total tokens across all agent executions.
            max_concurrent_agents: Maximum agents to run in parallel.
            delegation_trace_service: Optional DelegationTraceService for audit trail.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.max_tokens = max_tokens
        self.max_concurrent_agents = max_concurrent_agents
        self.active_agents: dict[str, BaseAgent] = {}
        self._total_tokens_used = 0
        self._trace_service = delegation_trace_service

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

    @property
    def remaining_token_budget(self) -> int:
        """Get remaining token budget.

        Returns:
            Number of tokens remaining before reaching max_tokens limit.
        """
        return max(0, self.max_tokens - self._total_tokens_used)

    def check_token_budget(self, estimated_tokens: int) -> bool:
        """Check if estimated token usage is within budget.

        Args:
            estimated_tokens: Estimated tokens for the operation.

        Returns:
            True if within budget, False otherwise.
        """
        return (self._total_tokens_used + estimated_tokens) <= self.max_tokens

    @property
    def active_agent_count(self) -> int:
        """Get the count of currently active agents.

        Returns:
            Number of active agents.
        """
        return len(self.active_agents)

    def get_agent_status(self, agent_id: str) -> AgentStatus | None:
        """Get the status of an agent by ID.

        Args:
            agent_id: The unique identifier of the agent.

        Returns:
            AgentStatus if agent exists, None otherwise.
        """
        agent = self.active_agents.get(agent_id)
        if agent is None:
            return None
        return agent.status

    def cleanup(self) -> None:
        """Clean up all active agents and reset counters.

        Should be called when orchestration is complete or on error.
        """
        agent_count = len(self.active_agents)
        self.active_agents.clear()
        self._total_tokens_used = 0

        logger.info(
            f"Orchestrator cleanup: removed {agent_count} agents, reset token counter",
            extra={"agents_removed": agent_count, "user_id": self.user_id},
        )

    async def spawn_and_execute(
        self,
        agent_class: type[BaseAgent],
        task: dict[str, Any],
        task_index: int = 0,
        total_tasks: int = 1,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> AgentResult:
        """Spawn an agent and execute a task.

        Args:
            agent_class: The agent class to instantiate.
            task: Task specification for the agent.
            task_index: Index of this task in the overall execution (0-based).
            total_tasks: Total number of tasks being executed.
            on_progress: Optional callback for progress updates.

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

        # Report starting
        if on_progress is not None:
            on_progress(
                ProgressUpdate(
                    agent_name=agent.name,
                    agent_id=agent_id,
                    status="starting",
                    task_index=task_index,
                    total_tasks=total_tasks,
                    message=f"Starting {agent.name} agent",
                )
            )

        # --- DCT validation (fail-open) ---
        dct_dict = task.get("capability_token")
        if dct_dict:
            try:
                dct = DelegationCapabilityToken.from_dict(dct_dict)
                if not dct.is_valid():
                    logger.warning("DCT expired for agent %s", agent.name)
            except Exception as e:
                logger.warning("DCT validation failed: %s", e)

        # --- Start delegation trace ---
        trace_id: str | None = None
        if self._trace_service:
            try:
                trace_id = await self._trace_service.start_trace(
                    user_id=self.user_id,
                    goal_id=task.get("goal_id"),
                    parent_trace_id=task.get("parent_trace_id"),
                    delegator="orchestrator",
                    delegatee=agent.name,
                    task_description=task.get(
                        "description",
                        task.get("title", f"{agent.name} task"),
                    ),
                    task_characteristics=task.get("task_characteristics"),
                    capability_token=dct_dict,
                    inputs={
                        k: v
                        for k, v in task.items()
                        if k not in ("capability_token", "task_characteristics")
                    },
                )
            except Exception as e:
                logger.warning("Failed to start delegation trace: %s", e)

        try:
            result = await agent.run(task)

            # Accumulate token usage
            self._total_tokens_used += result.tokens_used

            # --- Complete delegation trace ---
            if self._trace_service and trace_id:
                try:
                    verification_result_dict = None
                    if isinstance(result.data, dict):
                        verification_result_dict = result.data.get(
                            "verification_result"
                        )
                    await self._trace_service.complete_trace(
                        trace_id=trace_id,
                        outputs=(
                            result.data
                            if result.data
                            else {"summary": str(result)[:500]}
                        ),
                        verification_result=verification_result_dict,
                        cost_usd=0.0,
                        status="completed" if result.success else "failed",
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to complete delegation trace %s: %s",
                        trace_id,
                        e,
                    )

            # Report complete or failed
            if on_progress is not None:
                status = "complete" if result.success else "failed"
                message = (
                    f"{agent.name} completed successfully"
                    if result.success
                    else f"{agent.name} failed: {result.error}"
                )
                on_progress(
                    ProgressUpdate(
                        agent_name=agent.name,
                        agent_id=agent_id,
                        status=status,
                        task_index=task_index,
                        total_tasks=total_tasks,
                        message=message,
                    )
                )

            return result

        except Exception as e:
            # --- Fail delegation trace ---
            if self._trace_service and trace_id:
                try:
                    await self._trace_service.fail_trace(
                        trace_id=trace_id,
                        error_message=str(e)[:500],
                    )
                except Exception as trace_err:
                    logger.warning(
                        "Failed to record trace failure: %s", trace_err
                    )

            # Report failure on exception
            if on_progress is not None:
                on_progress(
                    ProgressUpdate(
                        agent_name=agent.name,
                        agent_id=agent_id,
                        status="failed",
                        task_index=task_index,
                        total_tasks=total_tasks,
                        message=f"{agent.name} failed with exception: {e!s}",
                    )
                )
            raise

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
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> OrchestrationResult:
        """Execute multiple agents in parallel.

        All tasks run concurrently, respecting max_concurrent_agents limit.
        Failures in one task do not affect others.

        Args:
            tasks: List of (agent_class, task) tuples to execute.
            on_progress: Optional callback for progress updates.

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
        total_tasks = len(tasks)

        logger.info(
            f"Starting parallel execution of {total_tasks} agents "
            f"(max concurrent: {self.max_concurrent_agents})",
            extra={
                "task_count": total_tasks,
                "max_concurrent": self.max_concurrent_agents,
                "user_id": self.user_id,
            },
        )

        all_results: list[AgentResult] = []

        # Process in batches respecting max_concurrent_agents
        for batch_start in range(0, total_tasks, self.max_concurrent_agents):
            batch_end = min(batch_start + self.max_concurrent_agents, total_tasks)
            batch = tasks[batch_start:batch_end]

            # Create coroutines for batch
            coros = [
                self.spawn_and_execute(
                    agent_class,
                    task,
                    task_index=batch_start + i,
                    total_tasks=total_tasks,
                    on_progress=on_progress,
                )
                for i, (agent_class, task) in enumerate(batch)
            ]

            # Execute batch concurrently - return_exceptions=True ensures failures don't abort
            raw_results = await asyncio.gather(*coros, return_exceptions=True)

            # Convert exceptions to failed AgentResults
            for raw in raw_results:
                if isinstance(raw, BaseException):
                    all_results.append(
                        AgentResult(
                            success=False,
                            data=None,
                            error=str(raw),
                        )
                    )
                else:
                    all_results.append(raw)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        total_tokens = sum(r.tokens_used for r in all_results)

        logger.info(
            "Parallel execution complete",
            extra={
                "task_count": total_tasks,
                "success_count": sum(1 for r in all_results if r.success),
                "failed_count": sum(1 for r in all_results if not r.success),
                "total_tokens": total_tokens,
                "execution_time_ms": elapsed_ms,
            },
        )

        return OrchestrationResult(
            results=all_results,
            total_tokens=total_tokens,
            total_execution_time_ms=elapsed_ms,
        )

    async def execute_sequential(
        self,
        tasks: list[tuple[type[BaseAgent], dict[str, Any]]],
        continue_on_failure: bool = False,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> OrchestrationResult:
        """Execute agents sequentially, passing context between them.

        Each subsequent agent receives the results of previous agents in context.

        Args:
            tasks: List of (agent_class, task) tuples to execute in order.
            continue_on_failure: If True, continue executing even if an agent fails.
            on_progress: Optional callback for progress updates.

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
        total_tasks = len(tasks)

        logger.info(
            f"Starting sequential execution of {total_tasks} agents",
            extra={
                "task_count": total_tasks,
                "continue_on_failure": continue_on_failure,
                "user_id": self.user_id,
            },
        )

        for i, (agent_class, task) in enumerate(tasks):
            # Inject context from previous agents
            task_with_context = {**task, "context": context}

            try:
                result = await self.spawn_and_execute(
                    agent_class,
                    task_with_context,
                    task_index=i,
                    total_tasks=total_tasks,
                    on_progress=on_progress,
                )
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
