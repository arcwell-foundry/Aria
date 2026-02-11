"""Tests for goal execution Pydantic models."""

from src.models.goal_execution import (
    ExecutionPlan,
    GoalPhase,
    GoalProposal,
    GoalTask,
    GoalTaskStatus,
    ProposeGoalsResponse,
)


def test_goal_task_default_status():
    task = GoalTask(
        title="Find leads",
        description="Search for CDMOs",
        agent_type="hunter",
    )
    assert task.status == GoalTaskStatus.PENDING
    assert task.id  # auto-generated UUID


def test_execution_plan_serialization():
    plan = ExecutionPlan(
        goal_id="goal-1",
        tasks=[
            GoalTask(
                title="Research",
                description="Analyze market",
                agent_type="analyst",
            )
        ],
        reasoning="Market analysis needed first",
    )
    d = plan.model_dump()
    assert d["goal_id"] == "goal-1"
    assert len(d["tasks"]) == 1
    assert d["tasks"][0]["agent_type"] == "analyst"


def test_goal_proposal_fields():
    p = GoalProposal(
        title="Build CDMO Pipeline",
        description="Identify top CDMOs",
        goal_type="lead_gen",
        rationale="No CDMO leads in pipeline",
        priority="high",
        estimated_days=7,
        agent_assignments=["hunter", "analyst"],
    )
    assert p.priority == "high"
    assert "hunter" in p.agent_assignments


def test_goal_phase_enum():
    assert GoalPhase.PROPOSED == "proposed"
    assert GoalPhase.EXECUTING == "executing"


def test_goal_task_status_enum():
    assert GoalTaskStatus.RUNNING == "running"
    assert GoalTaskStatus.FAILED == "failed"


def test_propose_goals_response():
    resp = ProposeGoalsResponse(
        proposals=[
            GoalProposal(
                title="Test",
                description="Desc",
                goal_type="research",
                rationale="Needed",
                priority="medium",
                estimated_days=3,
                agent_assignments=["analyst"],
            )
        ],
        context_summary="Based on pipeline gaps",
    )
    assert len(resp.proposals) == 1
    assert resp.context_summary == "Based on pipeline gaps"


def test_goal_task_with_dependencies():
    t1 = GoalTask(
        title="Research",
        description="Gather data",
        agent_type="analyst",
    )
    t2 = GoalTask(
        title="Outreach",
        description="Draft emails",
        agent_type="scribe",
        depends_on=[t1.id],
    )
    assert t1.id in t2.depends_on
