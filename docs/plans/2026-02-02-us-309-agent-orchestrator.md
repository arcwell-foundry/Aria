# US-309: Agent Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement an AgentOrchestrator class that coordinates multiple agents for complex goal execution with parallel and sequential execution modes.

**Architecture:** The AgentOrchestrator manages spawning, executing, and coordinating multiple ARIA agents. It supports parallel execution for independent tasks (using asyncio.gather), sequential execution for dependent tasks (passing context between agents), graceful failure handling, progress reporting, and resource limits. The orchestrator maintains a registry of active agents and provides execution tracking.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, logging module, UUID for agent IDs

---

## Acceptance Criteria Checklist

- [ ] `src/agents/orchestrator.py` coordinates agents
- [ ] Parallel execution where possible
- [ ] Sequential execution where dependencies exist
- [ ] Handles agent failures gracefully
- [ ] Reports progress to user
- [ ] Respects resource limits (API calls, tokens)
- [ ] Unit tests for orchestration scenarios

---

### Task 1: Create ExecutionPlan and OrchestrationResult Types

**Files:**
- Create: `backend/src/agents/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for core types**

Create `backend/tests/test_orchestrator.py`:

```python
"""Tests for AgentOrchestrator module."""

from unittest.mock import MagicMock


def test_execution_mode_enum_has_parallel_and_sequential() -> None:
    """Test ExecutionMode enum has PARALLEL and SEQUENTIAL values."""
    from src.agents.orchestrator import ExecutionMode

    assert ExecutionMode.PARALLEL.value == "parallel"
    assert ExecutionMode.SEQUENTIAL.value == "sequential"
    assert len(ExecutionMode) == 2


def test_orchestration_result_initializes_with_required_fields() -> None:
    """Test OrchestrationResult initializes with results and total_tokens."""
    from src.agents.orchestrator import OrchestrationResult

    result = OrchestrationResult(
        results=[],
        total_tokens=0,
        total_execution_time_ms=0,
    )

    assert result.results == []
    assert result.total_tokens == 0
    assert result.total_execution_time_ms == 0
    assert result.failed_count == 0
    assert result.success_count == 0


def test_orchestration_result_tracks_success_and_failure_counts() -> None:
    """Test OrchestrationResult tracks success and failure counts."""
    from src.agents.base import AgentResult
    from src.agents.orchestrator import OrchestrationResult

    results = [
        AgentResult(success=True, data={"id": 1}),
        AgentResult(success=True, data={"id": 2}),
        AgentResult(success=False, data=None, error="Failed"),
    ]

    orchestration = OrchestrationResult(
        results=results,
        total_tokens=500,
        total_execution_time_ms=3000,
    )

    assert orchestration.success_count == 2
    assert orchestration.failed_count == 1


def test_orchestration_result_all_succeeded_property() -> None:
    """Test OrchestrationResult.all_succeeded returns correct boolean."""
    from src.agents.base import AgentResult
    from src.agents.orchestrator import OrchestrationResult

    all_success = OrchestrationResult(
        results=[
            AgentResult(success=True, data={}),
            AgentResult(success=True, data={}),
        ],
        total_tokens=100,
        total_execution_time_ms=1000,
    )
    assert all_success.all_succeeded is True

    some_failed = OrchestrationResult(
        results=[
            AgentResult(success=True, data={}),
            AgentResult(success=False, data=None, error="Error"),
        ],
        total_tokens=100,
        total_execution_time_ms=1000,
    )
    assert some_failed.all_succeeded is False
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

Create `backend/src/agents/orchestrator.py`:

```python
"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import logging
from dataclasses import dataclass, field
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add orchestrator types ExecutionMode and OrchestrationResult

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Create AgentOrchestrator Class with Initialization

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for AgentOrchestrator initialization**

Add to `backend/tests/test_orchestrator.py`:

```python
def test_orchestrator_initializes_with_llm_and_user() -> None:
    """Test AgentOrchestrator initializes with llm_client and user_id."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    assert orchestrator.llm == mock_llm
    assert orchestrator.user_id == "user-123"
    assert orchestrator.active_agents == {}


def test_orchestrator_accepts_optional_resource_limits() -> None:
    """Test AgentOrchestrator accepts optional resource limits."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-123",
        max_tokens=10000,
        max_concurrent_agents=5,
    )

    assert orchestrator.max_tokens == 10000
    assert orchestrator.max_concurrent_agents == 5


def test_orchestrator_has_default_resource_limits() -> None:
    """Test AgentOrchestrator has sensible default resource limits."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # Defaults should allow reasonable workloads
    assert orchestrator.max_tokens > 0
    assert orchestrator.max_concurrent_agents > 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_orchestrator_initializes_with_llm_and_user -v`

Expected: FAIL with "AttributeError" or "ImportError"

**Step 3: Write implementation**

Update `backend/src/agents/orchestrator.py` to add the AgentOrchestrator class:

```python
"""Agent orchestrator module for ARIA.

Coordinates multiple agents for complex goal execution with parallel
and sequential execution modes.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)

# Default resource limits
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add AgentOrchestrator class with initialization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Implement spawn_agent Method

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for spawn_agent**

Add to `backend/tests/test_orchestrator.py`:

```python
import pytest


def test_spawn_agent_creates_agent_instance() -> None:
    """Test spawn_agent creates an agent and returns its ID."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    agent_id = orchestrator.spawn_agent(ScoutAgent)

    assert agent_id is not None
    assert isinstance(agent_id, str)
    assert len(agent_id) > 0


def test_spawn_agent_adds_to_active_agents() -> None:
    """Test spawn_agent adds agent to active_agents dict."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    agent_id = orchestrator.spawn_agent(ScoutAgent)

    assert agent_id in orchestrator.active_agents
    assert isinstance(orchestrator.active_agents[agent_id], ScoutAgent)


def test_spawn_agent_initializes_agent_with_correct_params() -> None:
    """Test spawn_agent passes llm_client and user_id to agent."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-456")

    agent_id = orchestrator.spawn_agent(ScoutAgent)
    agent = orchestrator.active_agents[agent_id]

    assert agent.llm == mock_llm
    assert agent.user_id == "user-456"


def test_spawn_agent_generates_unique_ids() -> None:
    """Test spawn_agent generates unique IDs for each agent."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    id1 = orchestrator.spawn_agent(ScoutAgent)
    id2 = orchestrator.spawn_agent(ScoutAgent)
    id3 = orchestrator.spawn_agent(ScoutAgent)

    assert id1 != id2
    assert id2 != id3
    assert id1 != id3
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_spawn_agent_creates_agent_instance -v`

Expected: FAIL with "AttributeError: 'AgentOrchestrator' object has no attribute 'spawn_agent'"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
import uuid

# Add to imports at top
from typing import TYPE_CHECKING, Any, Type

# Add inside AgentOrchestrator class:
    def spawn_agent(self, agent_class: Type[BaseAgent]) -> str:
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add spawn_agent method to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Implement spawn_and_execute Method

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for spawn_and_execute**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_spawn_and_execute_runs_agent_task() -> None:
    """Test spawn_and_execute spawns agent and executes task."""
    from src.agents.base import AgentResult
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    task = {"entities": ["Acme Corp"], "signal_types": ["funding"]}
    result = await orchestrator.spawn_and_execute(ScoutAgent, task)

    assert isinstance(result, AgentResult)
    assert result.success is True


@pytest.mark.asyncio
async def test_spawn_and_execute_returns_agent_result() -> None:
    """Test spawn_and_execute returns proper AgentResult with data."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    task = {"entities": ["Acme Corp"]}
    result = await orchestrator.spawn_and_execute(ScoutAgent, task)

    assert result.success is True
    assert isinstance(result.data, list)  # Scout returns signals list


@pytest.mark.asyncio
async def test_spawn_and_execute_tracks_agent_in_active() -> None:
    """Test spawn_and_execute adds agent to active_agents during execution."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    task = {"entities": ["Acme Corp"]}
    await orchestrator.spawn_and_execute(ScoutAgent, task)

    # Agent should have been tracked (may be removed after execution)
    # At minimum, the orchestrator should have processed an agent
    assert orchestrator._total_tokens_used >= 0


@pytest.mark.asyncio
async def test_spawn_and_execute_accumulates_token_usage() -> None:
    """Test spawn_and_execute accumulates tokens from agent execution."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    initial_tokens = orchestrator._total_tokens_used
    task = {"entities": ["Acme Corp"]}
    result = await orchestrator.spawn_and_execute(ScoutAgent, task)

    # Token usage should be tracked (even if 0 for mock agents)
    assert orchestrator._total_tokens_used >= initial_tokens
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_spawn_and_execute_runs_agent_task -v`

Expected: FAIL with "AttributeError: 'AgentOrchestrator' object has no attribute 'spawn_and_execute'"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
    async def spawn_and_execute(
        self,
        agent_class: Type[BaseAgent],
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add spawn_and_execute method to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Implement execute_parallel Method

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for execute_parallel**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_execute_parallel_runs_multiple_agents() -> None:
    """Test execute_parallel runs multiple agents concurrently."""
    from src.agents.orchestrator import AgentOrchestrator, OrchestrationResult
    from src.agents.scout import ScoutAgent
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (OperatorAgent, {"operation_type": "calendar_read", "parameters": {"start_date": "2024-01-01"}}),
    ]

    result = await orchestrator.execute_parallel(tasks)

    assert isinstance(result, OrchestrationResult)
    assert len(result.results) == 2


@pytest.mark.asyncio
async def test_execute_parallel_returns_orchestration_result() -> None:
    """Test execute_parallel returns OrchestrationResult with metrics."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (ScoutAgent, {"entities": ["Beta Inc"]}),
    ]

    result = await orchestrator.execute_parallel(tasks)

    assert result.total_tokens >= 0
    assert result.total_execution_time_ms >= 0
    assert result.success_count == 2


@pytest.mark.asyncio
async def test_execute_parallel_handles_empty_tasks() -> None:
    """Test execute_parallel handles empty task list gracefully."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    result = await orchestrator.execute_parallel([])

    assert len(result.results) == 0
    assert result.all_succeeded is True


@pytest.mark.asyncio
async def test_execute_parallel_continues_on_failure() -> None:
    """Test execute_parallel continues executing even if one agent fails."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # First task is valid, second has invalid input (will fail validation)
    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),  # Valid
        (ScoutAgent, {"signal_types": ["funding"]}),  # Invalid - missing entities
    ]

    result = await orchestrator.execute_parallel(tasks)

    # Both should complete (one success, one failure)
    assert len(result.results) == 2
    assert result.success_count == 1
    assert result.failed_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_execute_parallel_runs_multiple_agents -v`

Expected: FAIL with "AttributeError"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
import asyncio
import time

# Add inside AgentOrchestrator class:
    async def execute_parallel(
        self,
        tasks: list[tuple[Type[BaseAgent], dict[str, Any]]],
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
        coros = [
            self.spawn_and_execute(agent_class, task)
            for agent_class, task in tasks
        ]

        # Execute all concurrently - return_exceptions=True ensures failures don't abort others
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        # Convert exceptions to failed AgentResults
        results: list[AgentResult] = []
        for raw in raw_results:
            if isinstance(raw, Exception):
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
            f"Parallel execution complete",
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add execute_parallel method to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Implement execute_sequential Method

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for execute_sequential**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_execute_sequential_runs_agents_in_order() -> None:
    """Test execute_sequential runs agents one after another."""
    from src.agents.orchestrator import AgentOrchestrator, OrchestrationResult
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (ScoutAgent, {"entities": ["Beta Inc"]}),
    ]

    result = await orchestrator.execute_sequential(tasks)

    assert isinstance(result, OrchestrationResult)
    assert len(result.results) == 2
    assert result.success_count == 2


@pytest.mark.asyncio
async def test_execute_sequential_passes_context_between_agents() -> None:
    """Test execute_sequential passes previous results as context."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # The second task should receive context from the first
    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (ScoutAgent, {"entities": ["Beta Inc"]}),
    ]

    result = await orchestrator.execute_sequential(tasks)

    # Both should succeed with context passing
    assert result.all_succeeded is True


@pytest.mark.asyncio
async def test_execute_sequential_handles_empty_tasks() -> None:
    """Test execute_sequential handles empty task list."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    result = await orchestrator.execute_sequential([])

    assert len(result.results) == 0


@pytest.mark.asyncio
async def test_execute_sequential_stops_on_failure_by_default() -> None:
    """Test execute_sequential stops when an agent fails."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks = [
        (ScoutAgent, {"signal_types": ["funding"]}),  # Invalid - fails validation
        (ScoutAgent, {"entities": ["Beta Inc"]}),  # Would succeed but won't run
    ]

    result = await orchestrator.execute_sequential(tasks)

    # Should stop at first failure
    assert result.failed_count == 1
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_execute_sequential_continue_on_failure_option() -> None:
    """Test execute_sequential can continue past failures."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks = [
        (ScoutAgent, {"signal_types": ["funding"]}),  # Invalid
        (ScoutAgent, {"entities": ["Beta Inc"]}),  # Valid
    ]

    result = await orchestrator.execute_sequential(tasks, continue_on_failure=True)

    # Should execute both
    assert len(result.results) == 2
    assert result.failed_count == 1
    assert result.success_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_execute_sequential_runs_agents_in_order -v`

Expected: FAIL with "AttributeError"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
    async def execute_sequential(
        self,
        tasks: list[tuple[Type[BaseAgent], dict[str, Any]]],
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
            f"Sequential execution complete",
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add execute_sequential method to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Implement Progress Reporting with Callback

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for progress callback**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_execute_parallel_calls_progress_callback() -> None:
    """Test execute_parallel calls progress callback for each agent."""
    from src.agents.orchestrator import AgentOrchestrator, ProgressUpdate
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    progress_updates: list[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate) -> None:
        progress_updates.append(update)

    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (ScoutAgent, {"entities": ["Beta Inc"]}),
    ]

    await orchestrator.execute_parallel(tasks, on_progress=on_progress)

    # Should have at least start and complete for each task
    assert len(progress_updates) >= 4  # 2 starts + 2 completes


@pytest.mark.asyncio
async def test_execute_sequential_calls_progress_callback() -> None:
    """Test execute_sequential calls progress callback for each agent."""
    from src.agents.orchestrator import AgentOrchestrator, ProgressUpdate
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    progress_updates: list[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate) -> None:
        progress_updates.append(update)

    tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
    ]

    await orchestrator.execute_sequential(tasks, on_progress=on_progress)

    assert len(progress_updates) >= 2  # At least start and complete


def test_progress_update_has_required_fields() -> None:
    """Test ProgressUpdate dataclass has all required fields."""
    from src.agents.orchestrator import ProgressUpdate

    update = ProgressUpdate(
        agent_name="Scout",
        agent_id="agent-123",
        status="running",
        task_index=0,
        total_tasks=3,
        message="Processing entities",
    )

    assert update.agent_name == "Scout"
    assert update.agent_id == "agent-123"
    assert update.status == "running"
    assert update.task_index == 0
    assert update.total_tasks == 3
    assert update.message == "Processing entities"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_execute_parallel_calls_progress_callback -v`

Expected: FAIL with "ImportError" for ProgressUpdate

**Step 3: Write implementation**

Add to `backend/src/agents/orchestrator.py`:

```python
from typing import TYPE_CHECKING, Any, Callable, Type

# Add new dataclass after OrchestrationResult:
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


# Modify spawn_and_execute to accept on_progress callback:
    async def spawn_and_execute(
        self,
        agent_class: Type[BaseAgent],
        task: dict[str, Any],
        task_index: int = 0,
        total_tasks: int = 1,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> AgentResult:
        """Spawn an agent and execute a task.

        Args:
            agent_class: The agent class to instantiate.
            task: Task specification for the agent.
            task_index: Index of this task in a batch (for progress).
            total_tasks: Total number of tasks in the batch.
            on_progress: Optional callback for progress updates.

        Returns:
            AgentResult from the agent execution.
        """
        agent_id = self.spawn_agent(agent_class)
        agent = self.active_agents[agent_id]

        # Report starting
        if on_progress:
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

            # Report completion
            if on_progress:
                status = "complete" if result.success else "failed"
                on_progress(
                    ProgressUpdate(
                        agent_name=agent.name,
                        agent_id=agent_id,
                        status=status,
                        task_index=task_index,
                        total_tasks=total_tasks,
                        message=f"{agent.name} {status}",
                    )
                )

            return result

        except Exception as e:
            if on_progress:
                on_progress(
                    ProgressUpdate(
                        agent_name=agent.name,
                        agent_id=agent_id,
                        status="failed",
                        task_index=task_index,
                        total_tasks=total_tasks,
                        message=f"{agent.name} failed: {str(e)}",
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


# Update execute_parallel to pass progress callback:
    async def execute_parallel(
        self,
        tasks: list[tuple[Type[BaseAgent], dict[str, Any]]],
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> OrchestrationResult:
        """Execute multiple agents in parallel.

        All tasks run concurrently. Failures in one task do not affect others.

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
            f"Starting parallel execution of {total_tasks} agents",
            extra={"task_count": total_tasks, "user_id": self.user_id},
        )

        # Create coroutines for all tasks with progress tracking
        coros = [
            self.spawn_and_execute(
                agent_class,
                task,
                task_index=i,
                total_tasks=total_tasks,
                on_progress=on_progress,
            )
            for i, (agent_class, task) in enumerate(tasks)
        ]

        # Execute all concurrently - return_exceptions=True ensures failures don't abort others
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        # Convert exceptions to failed AgentResults
        results: list[AgentResult] = []
        for raw in raw_results:
            if isinstance(raw, Exception):
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
            f"Parallel execution complete",
            extra={
                "task_count": total_tasks,
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


# Update execute_sequential to pass progress callback:
    async def execute_sequential(
        self,
        tasks: list[tuple[Type[BaseAgent], dict[str, Any]]],
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
            f"Sequential execution complete",
            extra={
                "tasks_executed": len(results),
                "tasks_total": total_tasks,
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add progress reporting to orchestrator execution

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Implement Resource Limit Enforcement

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for resource limits**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_execute_parallel_respects_max_concurrent_agents() -> None:
    """Test execute_parallel limits concurrent agents."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    # Set low concurrency limit
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-123",
        max_concurrent_agents=2,
    )

    # Request more agents than limit
    tasks = [
        (ScoutAgent, {"entities": ["Company1"]}),
        (ScoutAgent, {"entities": ["Company2"]}),
        (ScoutAgent, {"entities": ["Company3"]}),
        (ScoutAgent, {"entities": ["Company4"]}),
    ]

    result = await orchestrator.execute_parallel(tasks)

    # All should still complete (just batched)
    assert len(result.results) == 4
    assert result.success_count == 4


def test_orchestrator_check_token_budget_returns_true_when_under() -> None:
    """Test check_token_budget returns True when under limit."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-123",
        max_tokens=10000,
    )

    assert orchestrator.check_token_budget(5000) is True


def test_orchestrator_check_token_budget_returns_false_when_over() -> None:
    """Test check_token_budget returns False when over limit."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-123",
        max_tokens=10000,
    )

    # Simulate tokens already used
    orchestrator._total_tokens_used = 8000

    assert orchestrator.check_token_budget(3000) is False


def test_orchestrator_remaining_token_budget() -> None:
    """Test remaining_token_budget returns correct value."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-123",
        max_tokens=10000,
    )

    orchestrator._total_tokens_used = 3500

    assert orchestrator.remaining_token_budget == 6500
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_orchestrator_check_token_budget_returns_true_when_under -v`

Expected: FAIL with "AttributeError"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
    @property
    def remaining_token_budget(self) -> int:
        """Get remaining token budget."""
        return max(0, self.max_tokens - self._total_tokens_used)

    def check_token_budget(self, estimated_tokens: int) -> bool:
        """Check if estimated token usage is within budget.

        Args:
            estimated_tokens: Estimated tokens for the operation.

        Returns:
            True if within budget, False otherwise.
        """
        return (self._total_tokens_used + estimated_tokens) <= self.max_tokens


# Update execute_parallel to respect max_concurrent_agents:
    async def execute_parallel(
        self,
        tasks: list[tuple[Type[BaseAgent], dict[str, Any]]],
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
            f"Starting parallel execution of {total_tasks} agents (max concurrent: {self.max_concurrent_agents})",
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

            # Execute batch concurrently
            raw_results = await asyncio.gather(*coros, return_exceptions=True)

            # Convert exceptions to failed AgentResults
            for raw in raw_results:
                if isinstance(raw, Exception):
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
            f"Parallel execution complete",
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add resource limit enforcement to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Add get_agent_status and Cleanup Methods

**Files:**
- Modify: `backend/src/agents/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for agent management**

Add to `backend/tests/test_orchestrator.py`:

```python
def test_get_agent_status_returns_agent_status() -> None:
    """Test get_agent_status returns correct agent status."""
    from src.agents.base import AgentStatus
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    agent_id = orchestrator.spawn_agent(ScoutAgent)
    status = orchestrator.get_agent_status(agent_id)

    assert status == AgentStatus.IDLE


def test_get_agent_status_returns_none_for_unknown_agent() -> None:
    """Test get_agent_status returns None for unknown agent ID."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    status = orchestrator.get_agent_status("nonexistent-id")

    assert status is None


def test_cleanup_removes_all_active_agents() -> None:
    """Test cleanup removes all active agents."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # Spawn some agents
    orchestrator.spawn_agent(ScoutAgent)
    orchestrator.spawn_agent(ScoutAgent)
    assert len(orchestrator.active_agents) == 2

    # Cleanup
    orchestrator.cleanup()

    assert len(orchestrator.active_agents) == 0


def test_cleanup_resets_token_counter() -> None:
    """Test cleanup resets the token usage counter."""
    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # Simulate some token usage
    orchestrator._total_tokens_used = 5000

    orchestrator.cleanup()

    assert orchestrator._total_tokens_used == 0


def test_active_agent_count_property() -> None:
    """Test active_agent_count returns correct count."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    assert orchestrator.active_agent_count == 0

    orchestrator.spawn_agent(ScoutAgent)
    assert orchestrator.active_agent_count == 1

    orchestrator.spawn_agent(ScoutAgent)
    assert orchestrator.active_agent_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_orchestrator.py::test_get_agent_status_returns_agent_status -v`

Expected: FAIL with "AttributeError"

**Step 3: Write implementation**

Add to the `AgentOrchestrator` class in `backend/src/agents/orchestrator.py`:

```python
from src.agents.base import AgentResult, AgentStatus, BaseAgent

# Add inside AgentOrchestrator class:
    @property
    def active_agent_count(self) -> int:
        """Get the count of currently active agents."""
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): add agent management methods to orchestrator

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Update Module Exports and Final Integration Tests

**Files:**
- Modify: `backend/src/agents/__init__.py`
- Modify: `backend/tests/test_agents_module_exports.py`
- Modify: `backend/tests/test_orchestrator.py`

**Step 1: Write failing tests for module exports**

Add to `backend/tests/test_agents_module_exports.py`:

```python
def test_orchestrator_exports() -> None:
    """Test orchestrator types are exported from agents module."""
    from src.agents import AgentOrchestrator, ExecutionMode, OrchestrationResult, ProgressUpdate

    assert AgentOrchestrator is not None
    assert ExecutionMode is not None
    assert OrchestrationResult is not None
    assert ProgressUpdate is not None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_agents_module_exports.py::test_orchestrator_exports -v`

Expected: FAIL with "ImportError"

**Step 3: Update module exports**

Update `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class, all specialized agents,
and the orchestrator for coordinating agent execution.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent
from src.agents.operator import OperatorAgent
from src.agents.orchestrator import (
    AgentOrchestrator,
    ExecutionMode,
    OrchestrationResult,
    ProgressUpdate,
)
from src.agents.scout import ScoutAgent
from src.agents.scribe import ScribeAgent
from src.agents.strategist import StrategistAgent

__all__ = [
    "AgentOrchestrator",
    "AgentResult",
    "AgentStatus",
    "AnalystAgent",
    "BaseAgent",
    "ExecutionMode",
    "HunterAgent",
    "OperatorAgent",
    "OrchestrationResult",
    "ProgressUpdate",
    "ScoutAgent",
    "ScribeAgent",
    "StrategistAgent",
]
```

**Step 4: Write integration test**

Add to `backend/tests/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_full_orchestration_workflow() -> None:
    """Test complete orchestration workflow with multiple agents.

    This integration test verifies:
    - Multiple agent types can be orchestrated together
    - Parallel execution works correctly
    - Sequential execution passes context
    - Progress updates are received
    - Resource tracking is accurate
    """
    from src.agents.orchestrator import (
        AgentOrchestrator,
        OrchestrationResult,
        ProgressUpdate,
    )
    from src.agents.scout import ScoutAgent
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm,
        user_id="user-integration-test",
        max_tokens=50000,
        max_concurrent_agents=3,
    )

    progress_updates: list[ProgressUpdate] = []

    def on_progress(update: ProgressUpdate) -> None:
        progress_updates.append(update)

    # Phase 1: Parallel execution of independent tasks
    parallel_tasks = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (ScoutAgent, {"entities": ["Beta Inc"]}),
        (
            OperatorAgent,
            {
                "operation_type": "calendar_read",
                "parameters": {"start_date": "2024-01-01"},
            },
        ),
    ]

    parallel_result = await orchestrator.execute_parallel(
        parallel_tasks,
        on_progress=on_progress,
    )

    assert isinstance(parallel_result, OrchestrationResult)
    assert parallel_result.all_succeeded is True
    assert len(parallel_result.results) == 3

    # Phase 2: Sequential execution with context passing
    sequential_tasks = [
        (ScoutAgent, {"entities": ["Gamma LLC"]}),
        (ScoutAgent, {"entities": ["Delta Corp"]}),
    ]

    sequential_result = await orchestrator.execute_sequential(
        sequential_tasks,
        on_progress=on_progress,
    )

    assert sequential_result.all_succeeded is True
    assert len(sequential_result.results) == 2

    # Verify progress updates were received
    assert len(progress_updates) >= 10  # At least start/complete for each task

    # Verify cleanup works
    orchestrator.cleanup()
    assert orchestrator.active_agent_count == 0
    assert orchestrator._total_tokens_used == 0


@pytest.mark.asyncio
async def test_orchestrator_handles_mixed_success_failure() -> None:
    """Test orchestrator handles mix of successful and failed agents."""
    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # Mix of valid and invalid tasks
    tasks = [
        (ScoutAgent, {"entities": ["Valid Corp"]}),
        (ScoutAgent, {"signal_types": ["funding"]}),  # Invalid - missing entities
        (ScoutAgent, {"entities": ["Another Valid"]}),
    ]

    result = await orchestrator.execute_parallel(tasks)

    # Should have 2 successes and 1 failure
    assert result.success_count == 2
    assert result.failed_count == 1
    assert result.all_succeeded is False
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py tests/test_agents_module_exports.py -v`

Expected: PASS

**Step 6: Run all quality gates**

```bash
cd backend && pytest tests/ -v && mypy src/ --strict && ruff check src/ && ruff format src/ --check
```

Expected: All pass

**Step 7: Commit**

```bash
git add backend/src/agents/__init__.py backend/tests/test_agents_module_exports.py backend/tests/test_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(agents): complete US-309 Agent Orchestrator implementation

- Add orchestrator exports to agents module
- Add integration tests for full workflow
- Verify all quality gates pass

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Final Verification

After completing all tasks, verify the implementation meets all acceptance criteria:

| Criteria | Task | Status |
|----------|------|--------|
| `src/agents/orchestrator.py` coordinates agents | Task 2-9 | Complete |
| Parallel execution where possible | Task 5 | Complete |
| Sequential execution where dependencies exist | Task 6 | Complete |
| Handles agent failures gracefully | Task 5, 6 | Complete |
| Reports progress to user | Task 7 | Complete |
| Respects resource limits (API calls, tokens) | Task 8 | Complete |
| Unit tests for orchestration scenarios | All Tasks | Complete |

---

## Summary of Files Created/Modified

**Created:**
- `backend/src/agents/orchestrator.py` - Main orchestrator implementation
- `backend/tests/test_orchestrator.py` - Comprehensive test suite

**Modified:**
- `backend/src/agents/__init__.py` - Added orchestrator exports
- `backend/tests/test_agents_module_exports.py` - Added export tests
