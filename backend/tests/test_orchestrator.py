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
