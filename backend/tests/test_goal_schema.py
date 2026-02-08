"""Tests for goal Pydantic models.

These tests verify that the goal-related Pydantic models work correctly.
Following TDD: tests are written first, then implementation.
"""

from datetime import datetime

import pytest
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
        assert GoalType.MEETING_PREP == "meeting_prep"
        assert GoalType.COMPETITIVE_INTEL == "competitive_intel"
        assert GoalType.TERRITORY == "territory"
        assert GoalType.CUSTOM == "custom"

    def test_goal_type_count(self):
        """GoalType should have exactly 8 members."""
        from src.models.goal import GoalType

        assert len(GoalType) == 8

    def test_custom_is_last(self):
        """CUSTOM should be the last member of GoalType."""
        from src.models.goal import GoalType

        members = list(GoalType)
        assert members[-1] == GoalType.CUSTOM


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

        goal = GoalCreate(title="Test Goal", goal_type=GoalType.LEAD_GEN)

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
            config={"max_results": 10},
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
        from src.models.goal import GoalStatus, GoalUpdate

        update = GoalUpdate(
            title="Updated Title",
            description="Updated description",
            status=GoalStatus.ACTIVE,
            progress=50,
            config={"new_key": "new_value"},
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

    def test_update_goal_with_target_date(self):
        """GoalUpdate should accept target_date field."""
        from src.models.goal import GoalUpdate

        update = GoalUpdate(target_date="2026-03-15")
        assert update.target_date == "2026-03-15"

    def test_update_goal_with_health(self):
        """GoalUpdate should accept health field."""
        from src.models.goal import GoalHealth, GoalUpdate

        update = GoalUpdate(health=GoalHealth.AT_RISK)
        assert update.health == GoalHealth.AT_RISK

    def test_update_goal_new_fields_default_none(self):
        """GoalUpdate new fields should default to None."""
        from src.models.goal import GoalUpdate

        update = GoalUpdate()
        assert update.target_date is None
        assert update.health is None


class TestGoalResponse:
    """Test GoalResponse model."""

    def test_goal_response_with_all_fields(self):
        """GoalResponse should accept all fields."""
        from src.models.goal import GoalResponse, GoalStatus, GoalType

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
            updated_at=now,
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
        from src.models.goal import AgentStatus, GoalAgentResponse

        now = datetime.now()
        agent = GoalAgentResponse(
            id="agent-123",
            goal_id="goal-456",
            agent_type="hunter",
            agent_config={"priority": "high"},
            status=AgentStatus.RUNNING,
            created_at=now,
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
            completed_at=None,
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
            completed_at=now,
        )

        assert execution.status == "failed"
        assert execution.error == "Something went wrong"
        assert execution.output is None
        assert execution.execution_time_ms is None


class TestGoalHealth:
    """Test GoalHealth enum values."""

    def test_goal_health_values(self):
        """GoalHealth should have all required values."""
        from src.models.goal import GoalHealth

        assert GoalHealth.ON_TRACK == "on_track"
        assert GoalHealth.AT_RISK == "at_risk"
        assert GoalHealth.BEHIND == "behind"
        assert GoalHealth.BLOCKED == "blocked"

    def test_goal_health_count(self):
        """GoalHealth should have exactly 4 members."""
        from src.models.goal import GoalHealth

        assert len(GoalHealth) == 4


class TestMilestoneStatus:
    """Test MilestoneStatus enum values."""

    def test_milestone_status_values(self):
        """MilestoneStatus should have all required values."""
        from src.models.goal import MilestoneStatus

        assert MilestoneStatus.PENDING == "pending"
        assert MilestoneStatus.IN_PROGRESS == "in_progress"
        assert MilestoneStatus.COMPLETE == "complete"
        assert MilestoneStatus.SKIPPED == "skipped"

    def test_milestone_status_count(self):
        """MilestoneStatus should have exactly 4 members."""
        from src.models.goal import MilestoneStatus

        assert len(MilestoneStatus) == 4


class TestMilestoneCreate:
    """Test MilestoneCreate model."""

    def test_create_with_title_only(self):
        """MilestoneCreate should accept title only."""
        from src.models.goal import MilestoneCreate

        milestone = MilestoneCreate(title="First milestone")
        assert milestone.title == "First milestone"
        assert milestone.description is None
        assert milestone.due_date is None

    def test_create_with_all_fields(self):
        """MilestoneCreate should accept all fields."""
        from src.models.goal import MilestoneCreate

        milestone = MilestoneCreate(
            title="First milestone",
            description="Complete the first phase",
            due_date="2026-03-01",
        )
        assert milestone.title == "First milestone"
        assert milestone.description == "Complete the first phase"
        assert milestone.due_date == "2026-03-01"

    def test_create_requires_title(self):
        """MilestoneCreate should require title."""
        from src.models.goal import MilestoneCreate

        with pytest.raises(ValidationError):
            MilestoneCreate()


class TestMilestoneResponse:
    """Test MilestoneResponse model."""

    def test_milestone_response_with_all_fields(self):
        """MilestoneResponse should accept all fields."""
        from src.models.goal import MilestoneResponse, MilestoneStatus

        now = datetime.now()
        milestone = MilestoneResponse(
            id="ms-123",
            goal_id="goal-456",
            title="First milestone",
            description="Complete the first phase",
            due_date=now,
            completed_at=None,
            status=MilestoneStatus.IN_PROGRESS,
            sort_order=1,
            created_at=now,
        )
        assert milestone.id == "ms-123"
        assert milestone.goal_id == "goal-456"
        assert milestone.status == MilestoneStatus.IN_PROGRESS
        assert milestone.sort_order == 1


class TestCreateWithARIARequest:
    """Test CreateWithARIARequest model."""

    def test_create_with_title_only(self):
        """CreateWithARIARequest should accept title only."""
        from src.models.goal import CreateWithARIARequest

        request = CreateWithARIARequest(title="Increase territory coverage")
        assert request.title == "Increase territory coverage"
        assert request.description is None

    def test_create_with_all_fields(self):
        """CreateWithARIARequest should accept title and description."""
        from src.models.goal import CreateWithARIARequest

        request = CreateWithARIARequest(
            title="Increase territory coverage",
            description="Focus on northeast region",
        )
        assert request.title == "Increase territory coverage"
        assert request.description == "Focus on northeast region"

    def test_create_requires_title(self):
        """CreateWithARIARequest should require title."""
        from src.models.goal import CreateWithARIARequest

        with pytest.raises(ValidationError):
            CreateWithARIARequest()


class TestARIAGoalSuggestion:
    """Test ARIAGoalSuggestion model."""

    def test_valid_suggestion(self):
        """ARIAGoalSuggestion should accept valid data."""
        from src.models.goal import ARIAGoalSuggestion

        suggestion = ARIAGoalSuggestion(
            refined_title="Expand Northeast Territory by Q2",
            refined_description="Focus on key accounts in NY, NJ, CT",
            smart_score=85,
            sub_tasks=[
                {"title": "Identify top 20 accounts", "description": "Research phase"},
                {"title": "Schedule intro meetings", "description": "Outreach phase"},
            ],
            agent_assignments=["hunter", "strategist"],
            suggested_timeline_days=60,
            reasoning="Territory has high potential based on market data.",
        )
        assert suggestion.refined_title == "Expand Northeast Territory by Q2"
        assert suggestion.smart_score == 85
        assert len(suggestion.sub_tasks) == 2
        assert len(suggestion.agent_assignments) == 2
        assert suggestion.suggested_timeline_days == 60

    def test_smart_score_at_boundaries(self):
        """ARIAGoalSuggestion should accept smart_score at 0 and 100."""
        from src.models.goal import ARIAGoalSuggestion

        base = {
            "refined_title": "Title",
            "refined_description": "Desc",
            "sub_tasks": [],
            "agent_assignments": [],
            "suggested_timeline_days": 30,
            "reasoning": "Reason",
        }
        s0 = ARIAGoalSuggestion(smart_score=0, **base)
        assert s0.smart_score == 0

        s100 = ARIAGoalSuggestion(smart_score=100, **base)
        assert s100.smart_score == 100

    def test_smart_score_rejects_over_100(self):
        """ARIAGoalSuggestion should reject smart_score > 100."""
        from src.models.goal import ARIAGoalSuggestion

        with pytest.raises(ValidationError):
            ARIAGoalSuggestion(
                refined_title="Title",
                refined_description="Desc",
                smart_score=101,
                sub_tasks=[],
                agent_assignments=[],
                suggested_timeline_days=30,
                reasoning="Reason",
            )

    def test_smart_score_rejects_negative(self):
        """ARIAGoalSuggestion should reject smart_score < 0."""
        from src.models.goal import ARIAGoalSuggestion

        with pytest.raises(ValidationError):
            ARIAGoalSuggestion(
                refined_title="Title",
                refined_description="Desc",
                smart_score=-1,
                sub_tasks=[],
                agent_assignments=[],
                suggested_timeline_days=30,
                reasoning="Reason",
            )


class TestRetrospectiveResponse:
    """Test RetrospectiveResponse model."""

    def test_retrospective_response_with_all_fields(self):
        """RetrospectiveResponse should accept all fields."""
        from src.models.goal import RetrospectiveResponse

        now = datetime.now()
        retro = RetrospectiveResponse(
            id="retro-123",
            goal_id="goal-456",
            summary="Goal completed successfully",
            what_worked=["Clear milestones", "Good agent coordination"],
            what_didnt=["Initial timeline was too aggressive"],
            time_analysis={"planned_days": 30, "actual_days": 35},
            agent_effectiveness={"hunter": 0.9, "strategist": 0.85},
            learnings=["Allow buffer time for complex goals"],
            created_at=now,
            updated_at=now,
        )
        assert retro.id == "retro-123"
        assert retro.goal_id == "goal-456"
        assert retro.summary == "Goal completed successfully"
        assert len(retro.what_worked) == 2
        assert len(retro.what_didnt) == 1
        assert retro.time_analysis["actual_days"] == 35
        assert retro.agent_effectiveness["hunter"] == 0.9
        assert len(retro.learnings) == 1
