"""Tests for goal Pydantic models.

These tests verify that the goal-related Pydantic models work correctly.
Following TDD: tests are written first, then implementation.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

# These imports will fail initially - this is expected in TDD
# We'll create the models after writing the tests


class TestGoalType:
    """Test GoalType enum values."""

    def test_goal_type_values(self):
        """GoalType should have all required values."""
        from src.models.goal import GoalType

        assert GoalType.LEAD_GEN == "lead_gen"
        assert GoalType.RESEARCH == "research"
        assert GoalType.OUTREACH == "outreach"
        assert GoalType.ANALYSIS == "analysis"
        assert GoalType.CUSTOM == "custom"


class TestGoalStatus:
    """Test GoalStatus enum values."""

    def test_goal_status_values(self):
        """GoalStatus should have all required values."""
        from src.models.goal import GoalStatus

        assert GoalStatus.DRAFT == "draft"
        assert GoalStatus.ACTIVE == "active"
        assert GoalStatus.PAUSED == "paused"
        assert GoalStatus.COMPLETE == "complete"
        assert GoalStatus.FAILED == "failed"


class TestAgentStatus:
    """Test AgentStatus enum values."""

    def test_agent_status_values(self):
        """AgentStatus should have all required values."""
        from src.models.goal import AgentStatus

        assert AgentStatus.PENDING == "pending"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETE == "complete"
        assert AgentStatus.FAILED == "failed"


class TestGoalCreate:
    """Test GoalCreate model."""

    def test_create_goal_with_required_fields(self):
        """GoalCreate should accept title and goal_type."""
        from src.models.goal import GoalCreate, GoalType

        goal = GoalCreate(
            title="Test Goal",
            goal_type=GoalType.LEAD_GEN
        )

        assert goal.title == "Test Goal"
        assert goal.goal_type == GoalType.LEAD_GEN
        assert goal.description is None
        assert goal.config == {}

    def test_create_goal_with_all_fields(self):
        """GoalCreate should accept all optional fields."""
        from src.models.goal import GoalCreate, GoalType

        goal = GoalCreate(
            title="Test Goal",
            description="A detailed description",
            goal_type=GoalType.RESEARCH,
            config={"max_results": 10}
        )

        assert goal.title == "Test Goal"
        assert goal.description == "A detailed description"
        assert goal.goal_type == GoalType.RESEARCH
        assert goal.config == {"max_results": 10}

    def test_create_goal_requires_title(self):
        """GoalCreate should require title field."""
        from src.models.goal import GoalCreate, GoalType

        with pytest.raises(ValidationError):
            GoalCreate(goal_type=GoalType.LEAD_GEN)

    def test_create_goal_requires_goal_type(self):
        """GoalCreate should require goal_type field."""
        from src.models.goal import GoalCreate

        with pytest.raises(ValidationError):
            GoalCreate(title="Test Goal")


class TestGoalUpdate:
    """Test GoalUpdate model."""

    def test_update_goal_with_no_fields(self):
        """GoalUpdate should accept empty model (all optional)."""
        from src.models.goal import GoalUpdate

        update = GoalUpdate()
        assert update.title is None
        assert update.description is None
        assert update.status is None
        assert update.progress is None
        assert update.config is None

    def test_update_goal_with_single_field(self):
        """GoalUpdate should accept single field update."""
        from src.models.goal import GoalUpdate

        update = GoalUpdate(title="Updated Title")
        assert update.title == "Updated Title"
        assert update.description is None
        assert update.status is None

    def test_update_goal_with_all_fields(self):
        """GoalUpdate should accept all fields."""
        from src.models.goal import GoalUpdate, GoalStatus

        update = GoalUpdate(
            title="Updated Title",
            description="Updated description",
            status=GoalStatus.ACTIVE,
            progress=50,
            config={"new_key": "new_value"}
        )

        assert update.title == "Updated Title"
        assert update.description == "Updated description"
        assert update.status == GoalStatus.ACTIVE
        assert update.progress == 50
        assert update.config == {"new_key": "new_value"}

    def test_update_goal_rejects_invalid_progress(self):
        """GoalUpdate should reject progress values outside 0-100."""
        from src.models.goal import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(progress=150)

        with pytest.raises(ValidationError):
            GoalUpdate(progress=-10)


class TestGoalResponse:
    """Test GoalResponse model."""

    def test_goal_response_with_all_fields(self):
        """GoalResponse should accept all fields."""
        from src.models.goal import GoalResponse, GoalType, GoalStatus

        now = datetime.now()
        goal = GoalResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            user_id="user-123",
            title="Test Goal",
            description="Test description",
            goal_type=GoalType.LEAD_GEN,
            status=GoalStatus.ACTIVE,
            strategy={"steps": ["step1", "step2"]},
            config={"key": "value"},
            progress=75,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now
        )

        assert goal.id == "123e4567-e89b-12d3-a456-426614174000"
        assert goal.user_id == "user-123"
        assert goal.title == "Test Goal"
        assert goal.description == "Test description"
        assert goal.goal_type == GoalType.LEAD_GEN
        assert goal.status == GoalStatus.ACTIVE
        assert goal.strategy == {"steps": ["step1", "step2"]}
        assert goal.config == {"key": "value"}
        assert goal.progress == 75
        assert goal.started_at == now
        assert goal.completed_at is None
        assert goal.created_at == now
        assert goal.updated_at == now


class TestGoalAgentResponse:
    """Test GoalAgentResponse model."""

    def test_goal_agent_response_with_all_fields(self):
        """GoalAgentResponse should accept all fields."""
        from src.models.goal import GoalAgentResponse, AgentStatus

        now = datetime.now()
        agent = GoalAgentResponse(
            id="agent-123",
            goal_id="goal-456",
            agent_type="hunter",
            agent_config={"priority": "high"},
            status=AgentStatus.RUNNING,
            created_at=now
        )

        assert agent.id == "agent-123"
        assert agent.goal_id == "goal-456"
        assert agent.agent_type == "hunter"
        assert agent.agent_config == {"priority": "high"}
        assert agent.status == AgentStatus.RUNNING
        assert agent.created_at == now


class TestAgentExecutionResponse:
    """Test AgentExecutionResponse model."""

    def test_agent_execution_response_with_all_fields(self):
        """AgentExecutionResponse should accept all fields."""
        from src.models.goal import AgentExecutionResponse

        now = datetime.now()
        execution = AgentExecutionResponse(
            id="exec-123",
            goal_agent_id="agent-456",
            input={"query": "test"},
            output={"result": "success"},
            status="running",
            tokens_used=1000,
            execution_time_ms=500,
            error=None,
            started_at=now,
            completed_at=None
        )

        assert execution.id == "exec-123"
        assert execution.goal_agent_id == "agent-456"
        assert execution.input == {"query": "test"}
        assert execution.output == {"result": "success"}
        assert execution.status == "running"
        assert execution.tokens_used == 1000
        assert execution.execution_time_ms == 500
        assert execution.error is None
        assert execution.started_at == now
        assert execution.completed_at is None

    def test_agent_execution_with_error(self):
        """AgentExecutionResponse should handle error state."""
        from src.models.goal import AgentExecutionResponse

        now = datetime.now()
        execution = AgentExecutionResponse(
            id="exec-123",
            goal_agent_id="agent-456",
            input={"query": "test"},
            output=None,
            status="failed",
            tokens_used=500,
            execution_time_ms=None,
            error="Something went wrong",
            started_at=now,
            completed_at=now
        )

        assert execution.status == "failed"
        assert execution.error == "Something went wrong"
        assert execution.output is None
        assert execution.execution_time_ms is None
