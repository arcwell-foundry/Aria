"""Tests for skill orchestrator service."""

from datetime import UTC, datetime

import pytest

from src.skills.orchestrator import ExecutionPlan, ExecutionStep, WorkingMemoryEntry


class TestExecutionStep:
    """Tests for ExecutionStep dataclass."""

    def test_create_execution_step(self) -> None:
        """Test creating an ExecutionStep with required fields."""
        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="anthropics/skills/pdf",
            depends_on=[],
            status="pending",
            input_data={"file": "report.pdf"},
        )
        assert step.step_number == 1
        assert step.skill_id == "skill-abc"
        assert step.skill_path == "anthropics/skills/pdf"
        assert step.depends_on == []
        assert step.status == "pending"
        assert step.input_data == {"file": "report.pdf"}
        assert step.output_data is None
        assert step.started_at is None
        assert step.completed_at is None

    def test_execution_step_with_optional_fields(self) -> None:
        """Test ExecutionStep with all optional fields populated."""
        now = datetime.now(UTC)
        step = ExecutionStep(
            step_number=2,
            skill_id="skill-def",
            skill_path="community/skills/csv-parser",
            depends_on=[1],
            status="completed",
            input_data={"data": "raw"},
            output_data={"parsed": True},
            started_at=now,
            completed_at=now,
        )
        assert step.output_data == {"parsed": True}
        assert step.started_at == now
        assert step.completed_at == now
        assert step.depends_on == [1]

    def test_execution_step_with_multiple_dependencies(self) -> None:
        """Test ExecutionStep can depend on multiple prior steps."""
        step = ExecutionStep(
            step_number=3,
            skill_id="skill-ghi",
            skill_path="anthropics/skills/merge",
            depends_on=[1, 2],
            status="pending",
            input_data={},
        )
        assert step.depends_on == [1, 2]


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_create_execution_plan(self) -> None:
        """Test creating an ExecutionPlan with required fields."""
        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="anthropics/skills/pdf",
            depends_on=[],
            status="pending",
            input_data={"file": "report.pdf"},
        )
        plan = ExecutionPlan(
            task_description="Parse and summarize report",
            steps=[step],
            parallel_groups=[[1]],
            estimated_duration_ms=5000,
            risk_level="low",
            approval_required=False,
        )
        assert plan.task_description == "Parse and summarize report"
        assert len(plan.steps) == 1
        assert plan.parallel_groups == [[1]]
        assert plan.estimated_duration_ms == 5000
        assert plan.risk_level == "low"
        assert plan.approval_required is False
        assert len(plan.plan_id) == 36

    def test_execution_plan_auto_generates_uuid(self) -> None:
        """Test that plan_id is auto-generated and unique."""
        plan1 = ExecutionPlan(
            task_description="Task 1",
            steps=[],
            parallel_groups=[],
            estimated_duration_ms=0,
            risk_level="low",
            approval_required=False,
        )
        plan2 = ExecutionPlan(
            task_description="Task 2",
            steps=[],
            parallel_groups=[],
            estimated_duration_ms=0,
            risk_level="low",
            approval_required=False,
        )
        assert plan1.plan_id != plan2.plan_id

    def test_execution_plan_with_parallel_groups(self) -> None:
        """Test plan with multiple parallel groups."""
        steps = [
            ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
            ExecutionStep(step_number=2, skill_id="s2", skill_path="d/e/f", depends_on=[], status="pending", input_data={}),
            ExecutionStep(step_number=3, skill_id="s3", skill_path="g/h/i", depends_on=[1, 2], status="pending", input_data={}),
        ]
        plan = ExecutionPlan(
            task_description="Multi-step task",
            steps=steps,
            parallel_groups=[[1, 2], [3]],
            estimated_duration_ms=10000,
            risk_level="medium",
            approval_required=True,
        )
        assert plan.parallel_groups == [[1, 2], [3]]
        assert plan.approval_required is True


class TestWorkingMemoryEntry:
    """Tests for WorkingMemoryEntry dataclass."""

    def test_create_working_memory_entry(self) -> None:
        """Test creating a WorkingMemoryEntry with required fields."""
        entry = WorkingMemoryEntry(
            step_number=1,
            skill_id="skill-abc",
            status="completed",
            summary="Parsed PDF report, extracted 3 tables and 12 figures.",
            artifacts=["table_1.csv", "table_2.csv"],
            extracted_facts={"total_patients": 500, "drug_name": "Pembrolizumab"},
            next_step_hints=["Use extracted tables for analysis"],
        )
        assert entry.step_number == 1
        assert entry.skill_id == "skill-abc"
        assert entry.status == "completed"
        assert entry.summary == "Parsed PDF report, extracted 3 tables and 12 figures."
        assert len(entry.artifacts) == 2
        assert entry.extracted_facts["total_patients"] == 500
        assert entry.next_step_hints == ["Use extracted tables for analysis"]

    def test_working_memory_entry_empty_collections(self) -> None:
        """Test WorkingMemoryEntry with empty collections."""
        entry = WorkingMemoryEntry(
            step_number=1,
            skill_id="skill-abc",
            status="failed",
            summary="Execution failed: timeout",
            artifacts=[],
            extracted_facts={},
            next_step_hints=[],
        )
        assert entry.artifacts == []
        assert entry.extracted_facts == {}
        assert entry.next_step_hints == []
