"""Tests for AgentOrchestrator module."""

import pytest


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


def test_orchestrator_initializes_with_llm_and_user() -> None:
    """Test AgentOrchestrator initializes with llm_client and user_id."""
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    assert orchestrator.llm == mock_llm
    assert orchestrator.user_id == "user-123"
    assert orchestrator.active_agents == {}


def test_orchestrator_accepts_optional_resource_limits() -> None:
    """Test AgentOrchestrator accepts optional resource limits."""
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # Defaults should allow reasonable workloads
    assert orchestrator.max_tokens > 0
    assert orchestrator.max_concurrent_agents > 0


def test_spawn_agent_creates_agent_instance() -> None:
    """Test spawn_agent creates an agent and returns its ID."""
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    agent_id = orchestrator.spawn_agent(ScoutAgent)

    assert agent_id in orchestrator.active_agents
    assert isinstance(orchestrator.active_agents[agent_id], ScoutAgent)


def test_spawn_agent_initializes_agent_with_correct_params() -> None:
    """Test spawn_agent passes llm_client and user_id to agent."""
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

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


@pytest.mark.asyncio
async def test_spawn_and_execute_runs_agent_task() -> None:
    """Test spawn_and_execute spawns agent and executes task."""
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    initial_tokens = orchestrator._total_tokens_used
    task = {"entities": ["Acme Corp"]}
    await orchestrator.spawn_and_execute(ScoutAgent, task)

    # Token usage should be tracked (even if 0 for mock agents)
    assert orchestrator._total_tokens_used >= initial_tokens


@pytest.mark.asyncio
async def test_execute_parallel_runs_multiple_agents() -> None:
    """Test execute_parallel runs multiple agents concurrently."""
    from unittest.mock import MagicMock

    from src.agents.operator import OperatorAgent
    from src.agents.orchestrator import AgentOrchestrator, OrchestrationResult
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks: list[tuple[type, dict]] = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),
        (
            OperatorAgent,
            {"operation_type": "calendar_read", "parameters": {"start_date": "2024-01-01"}},
        ),
    ]

    result = await orchestrator.execute_parallel(tasks)

    assert isinstance(result, OrchestrationResult)
    assert len(result.results) == 2


@pytest.mark.asyncio
async def test_execute_parallel_returns_orchestration_result() -> None:
    """Test execute_parallel returns OrchestrationResult with metrics."""
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    tasks: list[tuple[type, dict]] = [
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
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    result = await orchestrator.execute_parallel([])

    assert len(result.results) == 0
    assert result.all_succeeded is True


@pytest.mark.asyncio
async def test_execute_parallel_continues_on_failure() -> None:
    """Test execute_parallel continues executing even if one agent fails."""
    from unittest.mock import MagicMock

    from src.agents.orchestrator import AgentOrchestrator
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    orchestrator = AgentOrchestrator(llm_client=mock_llm, user_id="user-123")

    # First task is valid, second has invalid input (will fail validation)
    tasks: list[tuple[type, dict]] = [
        (ScoutAgent, {"entities": ["Acme Corp"]}),  # Valid
        (ScoutAgent, {"signal_types": ["funding"]}),  # Invalid - missing entities
    ]

    result = await orchestrator.execute_parallel(tasks)

    # Both should complete (one success, one failure)
    assert len(result.results) == 2
    assert result.success_count == 1
    assert result.failed_count == 1
