"""Tests for base agent module."""


def test_agent_status_enum_has_four_states() -> None:
    """Test AgentStatus enum has idle, running, complete, failed."""
    from src.agents.base import AgentStatus

    assert AgentStatus.IDLE.value == "idle"
    assert AgentStatus.RUNNING.value == "running"
    assert AgentStatus.COMPLETE.value == "complete"
    assert AgentStatus.FAILED.value == "failed"
    assert len(AgentStatus) == 4


def test_agent_result_initializes_with_required_fields() -> None:
    """Test AgentResult initializes with success and data."""
    from src.agents.base import AgentResult

    result = AgentResult(success=True, data={"key": "value"})

    assert result.success is True
    assert result.data == {"key": "value"}
    assert result.error is None
    assert result.tokens_used == 0
    assert result.execution_time_ms == 0


def test_agent_result_initializes_with_all_fields() -> None:
    """Test AgentResult initializes with all optional fields."""
    from src.agents.base import AgentResult

    result = AgentResult(
        success=False,
        data=None,
        error="Something went wrong",
        tokens_used=150,
        execution_time_ms=1200,
    )

    assert result.success is False
    assert result.data is None
    assert result.error == "Something went wrong"
    assert result.tokens_used == 150
    assert result.execution_time_ms == 1200


def test_agent_result_to_dict_serializes_correctly() -> None:
    """Test AgentResult.to_dict produces valid dictionary."""
    from src.agents.base import AgentResult

    result = AgentResult(
        success=True,
        data={"results": ["item1", "item2"]},
        tokens_used=100,
        execution_time_ms=500,
    )

    serialized = result.to_dict()

    assert serialized["success"] is True
    assert serialized["data"] == {"results": ["item1", "item2"]}
    assert serialized["error"] is None
    assert serialized["tokens_used"] == 100
    assert serialized["execution_time_ms"] == 500
