"""Tests for AgentOrchestrator module."""


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
