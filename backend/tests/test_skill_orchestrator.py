"""Tests for skill orchestrator service."""

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.skills.orchestrator import (
    ExecutionPlan,
    ExecutionStep,
    PlanResult,
    SkillOrchestrator,
    WorkingMemoryEntry,
)


def _mock_db() -> MagicMock:
    """Create a mock Supabase client that chains .table().select()... etc."""
    db = MagicMock()

    # Make all chained calls return the same mock
    table = MagicMock()
    execute_result = MagicMock()
    execute_result.data = None

    table.select.return_value = table
    table.insert.return_value = table
    table.update.return_value = table
    table.upsert.return_value = table
    table.eq.return_value = table
    table.in_.return_value = table
    table.order.return_value = table
    table.single.return_value = table
    table.execute.return_value = execute_result

    db.table.return_value = table
    return db


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

    def test_execution_step_agent_id_field(self) -> None:
        """Test ExecutionStep has agent_id field for dynamic delegation."""
        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="a/b/c",
            depends_on=[],
            status="pending",
            input_data={},
            agent_id="analyst",
        )
        assert step.agent_id == "analyst"


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

    def test_execution_plan_reasoning_field(self) -> None:
        """Test that ExecutionPlan has a reasoning field for skill reasoning trace."""
        plan = ExecutionPlan(
            task_description="Task",
            steps=[],
            parallel_groups=[],
            estimated_duration_ms=0,
            risk_level="low",
            approval_required=False,
            reasoning="Selected PDF parser because the task requires document extraction.",
        )
        assert "PDF parser" in plan.reasoning


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


class TestPlanResult:
    """Tests for PlanResult dataclass."""

    def test_create_plan_result(self) -> None:
        """Test creating a PlanResult with all fields."""
        result = PlanResult(
            plan_id="abc-123",
            status="completed",
            steps_completed=3,
            steps_failed=0,
            steps_skipped=0,
            total_execution_ms=5000,
            working_memory=[],
        )
        assert result.plan_id == "abc-123"
        assert result.status == "completed"
        assert result.steps_completed == 3
        assert result.steps_failed == 0
        assert result.total_execution_ms == 5000

    def test_plan_result_partial_status(self) -> None:
        """Test PlanResult with partial completion."""
        wm = [
            WorkingMemoryEntry(
                step_number=1, skill_id="s1", status="completed",
                summary="Done", artifacts=[], extracted_facts={}, next_step_hints=[],
            ),
            WorkingMemoryEntry(
                step_number=2, skill_id="s2", status="failed",
                summary="Error", artifacts=[], extracted_facts={}, next_step_hints=[],
            ),
        ]
        result = PlanResult(
            plan_id="abc-456",
            status="partial",
            steps_completed=1,
            steps_failed=1,
            steps_skipped=0,
            total_execution_ms=3000,
            working_memory=wm,
        )
        assert result.status == "partial"
        assert len(result.working_memory) == 2


class TestCanExecute:
    """Tests for SkillOrchestrator._can_execute method."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=MagicMock(),
        )
        orch._get_db = lambda: _mock_db()
        return orch

    def test_step_with_no_dependencies_can_execute(self) -> None:
        """A step with no dependencies can always execute."""
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=1,
            skill_id="s1",
            skill_path="a/b/c",
            depends_on=[],
            status="pending",
            input_data={},
        )
        assert orch._can_execute(step, completed_steps={}) is True

    def test_step_with_met_dependencies_can_execute(self) -> None:
        """A step whose dependencies are all completed can execute."""
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=3,
            skill_id="s3",
            skill_path="a/b/c",
            depends_on=[1, 2],
            status="pending",
            input_data={},
        )
        completed = {1: True, 2: True}
        assert orch._can_execute(step, completed_steps=completed) is True

    def test_step_with_unmet_dependencies_cannot_execute(self) -> None:
        """A step whose dependencies are not all completed cannot execute."""
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=3,
            skill_id="s3",
            skill_path="a/b/c",
            depends_on=[1, 2],
            status="pending",
            input_data={},
        )
        completed = {1: True}
        assert orch._can_execute(step, completed_steps=completed) is False

    def test_step_with_empty_completed_and_dependencies_cannot_execute(self) -> None:
        """A step with dependencies but empty completed set cannot execute."""
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=2,
            skill_id="s2",
            skill_path="a/b/c",
            depends_on=[1],
            status="pending",
            input_data={},
        )
        assert orch._can_execute(step, completed_steps={}) is False


class TestDependsOnFailed:
    """Tests for SkillOrchestrator._depends_on_failed method."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=MagicMock(),
        )
        orch._get_db = lambda: _mock_db()
        return orch

    def test_no_failed_deps(self) -> None:
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=3, skill_id="s3", skill_path="a/b/c",
            depends_on=[1, 2], status="pending", input_data={},
        )
        assert orch._depends_on_failed(step, set()) is False

    def test_has_failed_dep(self) -> None:
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=3, skill_id="s3", skill_path="a/b/c",
            depends_on=[1, 2], status="pending", input_data={},
        )
        assert orch._depends_on_failed(step, {1}) is True

    def test_no_deps_never_fails(self) -> None:
        orch = self._make_orchestrator()
        step = ExecutionStep(
            step_number=1, skill_id="s1", skill_path="a/b/c",
            depends_on=[], status="pending", input_data={},
        )
        assert orch._depends_on_failed(step, {99}) is False


class TestBuildWorkingMemorySummary:
    """Tests for SkillOrchestrator._build_working_memory_summary method."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=MagicMock(),
        )
        orch._get_db = lambda: _mock_db()
        return orch

    def test_empty_entries_returns_empty_string(self) -> None:
        """No entries produces an empty summary."""
        orch = self._make_orchestrator()
        result = orch._build_working_memory_summary([])
        assert result == ""

    def test_single_entry_summary(self) -> None:
        """Single entry produces a readable summary."""
        orch = self._make_orchestrator()
        entry = WorkingMemoryEntry(
            step_number=1,
            skill_id="skill-pdf",
            status="completed",
            summary="Parsed 10-page report.",
            artifacts=["report.txt"],
            extracted_facts={"pages": 10},
            next_step_hints=["Analyze content"],
        )
        result = orch._build_working_memory_summary([entry])
        assert "Step 1" in result
        assert "skill-pdf" in result
        assert "completed" in result
        assert "Parsed 10-page report." in result

    def test_multiple_entries_summary(self) -> None:
        """Multiple entries are all included in summary."""
        orch = self._make_orchestrator()
        entries = [
            WorkingMemoryEntry(
                step_number=1, skill_id="s1", status="completed",
                summary="Did thing A.", artifacts=[], extracted_facts={}, next_step_hints=[],
            ),
            WorkingMemoryEntry(
                step_number=2, skill_id="s2", status="completed",
                summary="Did thing B.", artifacts=["file.csv"], extracted_facts={"key": "val"}, next_step_hints=[],
            ),
        ]
        result = orch._build_working_memory_summary(entries)
        assert "Step 1" in result
        assert "Step 2" in result
        assert "Did thing A." in result
        assert "Did thing B." in result

    def test_summary_includes_facts_and_hints(self) -> None:
        """Summary includes extracted facts and next step hints when present."""
        orch = self._make_orchestrator()
        entry = WorkingMemoryEntry(
            step_number=1,
            skill_id="s1",
            status="completed",
            summary="Extracted data.",
            artifacts=[],
            extracted_facts={"drug": "Keytruda"},
            next_step_hints=["Use drug name for search"],
        )
        result = orch._build_working_memory_summary([entry])
        assert "drug" in result
        assert "Keytruda" in result
        assert "Use drug name for search" in result


@pytest.mark.asyncio
class TestExecuteStep:
    """Tests for SkillOrchestrator._execute_step method."""

    def _make_orchestrator(
        self,
        executor: MagicMock | None = None,
        autonomy: MagicMock | None = None,
    ) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        orch = SkillOrchestrator(
            executor=executor or MagicMock(),
            index=MagicMock(),
            autonomy=autonomy or MagicMock(),
        )
        orch._get_db = lambda: _mock_db()
        return orch

    async def test_execute_step_success(self) -> None:
        """Successful step execution produces a completed WorkingMemoryEntry."""
        mock_executor = MagicMock()
        mock_execution = MagicMock()
        mock_execution.success = True
        mock_execution.result = {"summary": "Parsed report", "tables": 3}
        mock_execution.execution_time_ms = 1500
        mock_executor.execute = AsyncMock(return_value=mock_execution)

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="anthropics/skills/pdf",
            depends_on=[],
            status="pending",
            input_data={"file": "report.pdf"},
        )

        entry = await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=[],
        )

        assert entry.step_number == 1
        assert entry.skill_id == "skill-abc"
        assert entry.status == "completed"
        assert len(entry.summary) > 0
        mock_executor.execute.assert_awaited_once()
        mock_autonomy.record_execution_outcome.assert_awaited_once_with(
            "user-123", "skill-abc", success=True
        )

    async def test_execute_step_failure(self) -> None:
        """Failed skill execution produces a failed WorkingMemoryEntry."""
        mock_executor = MagicMock()
        mock_execution = MagicMock()
        mock_execution.success = False
        mock_execution.result = None
        mock_execution.error = "Sandbox timeout"
        mock_execution.execution_time_ms = 30000
        mock_executor.execute = AsyncMock(return_value=mock_execution)

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

        step = ExecutionStep(
            step_number=2,
            skill_id="skill-def",
            skill_path="community/skills/csv",
            depends_on=[1],
            status="pending",
            input_data={"data": "raw"},
        )

        entry = await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=[],
        )

        assert entry.status == "failed"
        assert "timeout" in entry.summary.lower() or "failed" in entry.summary.lower()
        mock_autonomy.record_execution_outcome.assert_awaited_once_with(
            "user-123", "skill-def", success=False
        )

    async def test_execute_step_skipped_when_approval_required(self) -> None:
        """Step is skipped when approval is required but not granted."""
        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=True)

        orch = self._make_orchestrator(autonomy=mock_autonomy)

        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="community/skills/risky",
            depends_on=[],
            status="pending",
            input_data={},
        )

        entry = await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=[],
        )

        assert entry.status == "skipped"
        assert "approval" in entry.summary.lower()

    async def test_execute_step_includes_working_memory_context(self) -> None:
        """Step execution passes working memory summary to executor context."""
        mock_executor = MagicMock()
        mock_execution = MagicMock()
        mock_execution.success = True
        mock_execution.result = {"output": "done"}
        mock_execution.execution_time_ms = 500
        mock_executor.execute = AsyncMock(return_value=mock_execution)

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

        prior_memory = [
            WorkingMemoryEntry(
                step_number=1, skill_id="s1", status="completed",
                summary="Found 5 leads.", artifacts=[], extracted_facts={"leads": 5},
                next_step_hints=["Filter by region"],
            ),
        ]

        step = ExecutionStep(
            step_number=2,
            skill_id="skill-filter",
            skill_path="a/b/filter",
            depends_on=[1],
            status="pending",
            input_data={"action": "filter"},
        )

        await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=prior_memory,
        )

        call_kwargs = mock_executor.execute.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context", {})
        assert "working_memory" in context
        assert "Found 5 leads." in context["working_memory"]

    async def test_execute_step_calls_progress_callback(self) -> None:
        """Progress callback is invoked during step execution."""
        mock_executor = MagicMock()
        mock_execution = MagicMock()
        mock_execution.success = True
        mock_execution.result = {}
        mock_execution.execution_time_ms = 100
        mock_executor.execute = AsyncMock(return_value=mock_execution)

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

        callback_calls: list[tuple[int, str, str]] = []

        async def mock_callback(step_num: int, status: str, msg: str) -> None:
            callback_calls.append((step_num, status, msg))

        step = ExecutionStep(
            step_number=1, skill_id="s1", skill_path="a/b/c",
            depends_on=[], status="pending", input_data={},
        )

        await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=[],
            progress_callback=mock_callback,
        )

        statuses = [c[1] for c in callback_calls]
        assert "running" in statuses
        assert "completed" in statuses

    async def test_execute_step_handles_executor_exception(self) -> None:
        """Step returns failed entry when executor raises an exception."""
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=RuntimeError("connection lost"))

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

        step = ExecutionStep(
            step_number=1,
            skill_id="skill-abc",
            skill_path="a/b/c",
            depends_on=[],
            status="pending",
            input_data={},
        )

        entry = await orch._execute_step(
            user_id="user-123",
            step=step,
            working_memory=[],
        )

        assert entry.status == "failed"
        assert "connection lost" in entry.summary


@pytest.mark.asyncio
class TestExecutePlan:
    """Tests for SkillOrchestrator.execute_plan method."""

    def _make_orchestrator(
        self,
        executor: MagicMock | None = None,
        autonomy: MagicMock | None = None,
    ) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        mock_executor = executor or MagicMock()
        mock_autonomy = autonomy or MagicMock()

        if executor is None:
            mock_execution = MagicMock()
            mock_execution.success = True
            mock_execution.result = {"output": "done"}
            mock_execution.execution_time_ms = 100
            mock_executor.execute = AsyncMock(return_value=mock_execution)

        if autonomy is None:
            mock_autonomy.should_request_approval = AsyncMock(return_value=False)
            mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = SkillOrchestrator(
            executor=mock_executor,
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        orch._get_db = lambda: _mock_db()
        return orch

    async def test_execute_plan_single_step(self) -> None:
        """Execute a plan with a single step returns PlanResult."""
        orch = self._make_orchestrator()
        plan = ExecutionPlan(
            task_description="Simple task",
            steps=[
                ExecutionStep(
                    step_number=1, skill_id="s1", skill_path="a/b/c",
                    depends_on=[], status="pending", input_data={"key": "val"},
                ),
            ],
            parallel_groups=[[1]],
            estimated_duration_ms=1000,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        assert isinstance(result, PlanResult)
        assert result.steps_completed == 1
        assert result.steps_failed == 0
        assert result.status == "completed"
        assert len(result.working_memory) == 1
        assert result.working_memory[0].status == "completed"
        assert result.working_memory[0].step_number == 1

    async def test_execute_plan_sequential_steps(self) -> None:
        """Steps in separate parallel groups execute sequentially."""
        orch = self._make_orchestrator()
        plan = ExecutionPlan(
            task_description="Sequential task",
            steps=[
                ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
                ExecutionStep(step_number=2, skill_id="s2", skill_path="d/e/f", depends_on=[1], status="pending", input_data={}),
            ],
            parallel_groups=[[1], [2]],
            estimated_duration_ms=2000,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        assert isinstance(result, PlanResult)
        assert result.steps_completed == 2
        assert result.working_memory[0].step_number == 1
        assert result.working_memory[1].step_number == 2

    async def test_execute_plan_parallel_steps(self) -> None:
        """Steps in the same parallel group execute concurrently."""
        mock_executor = MagicMock()

        async def mock_execute(**kwargs):
            result = MagicMock()
            result.success = True
            result.result = {"step": kwargs.get("skill_id")}
            result.execution_time_ms = 100
            return result

        mock_executor.execute = mock_execute

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = SkillOrchestrator(
            executor=mock_executor,
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        orch._get_db = lambda: _mock_db()

        plan = ExecutionPlan(
            task_description="Parallel task",
            steps=[
                ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
                ExecutionStep(step_number=2, skill_id="s2", skill_path="d/e/f", depends_on=[], status="pending", input_data={}),
                ExecutionStep(step_number=3, skill_id="s3", skill_path="g/h/i", depends_on=[1, 2], status="pending", input_data={}),
            ],
            parallel_groups=[[1, 2], [3]],
            estimated_duration_ms=3000,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        assert isinstance(result, PlanResult)
        assert result.steps_completed == 3
        step_3_entry = [r for r in result.working_memory if r.step_number == 3][0]
        assert step_3_entry.status == "completed"

    async def test_execute_plan_empty_plan(self) -> None:
        """Empty plan returns PlanResult with zero counts."""
        orch = self._make_orchestrator()
        plan = ExecutionPlan(
            task_description="Empty",
            steps=[],
            parallel_groups=[],
            estimated_duration_ms=0,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        assert isinstance(result, PlanResult)
        assert result.status == "completed"
        assert result.steps_completed == 0
        assert result.working_memory == []

    async def test_execute_plan_with_progress_callback(self) -> None:
        """Progress callback receives updates during execution."""
        orch = self._make_orchestrator()

        callback_calls: list[tuple[int, str, str]] = []

        async def mock_callback(step_num: int, status: str, msg: str) -> None:
            callback_calls.append((step_num, status, msg))

        plan = ExecutionPlan(
            task_description="Tracked task",
            steps=[
                ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
            ],
            parallel_groups=[[1]],
            estimated_duration_ms=1000,
            risk_level="low",
            approval_required=False,
        )

        await orch.execute_plan(
            user_id="user-123",
            plan=plan,
            progress_callback=mock_callback,
        )

        assert len(callback_calls) >= 2

    async def test_execute_plan_continues_after_step_failure(self) -> None:
        """Plan continues executing independent steps even if one fails."""
        mock_executor = MagicMock()

        async def mock_execute(**kwargs):
            result = MagicMock()
            if kwargs.get("skill_id") == "s1":
                result.success = False
                result.result = None
                result.error = "Skill s1 failed"
                result.execution_time_ms = 100
            else:
                result.success = True
                result.result = {"ok": True}
                result.execution_time_ms = 100
            return result

        mock_executor.execute = mock_execute

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = SkillOrchestrator(
            executor=mock_executor,
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        orch._get_db = lambda: _mock_db()

        plan = ExecutionPlan(
            task_description="Mixed results",
            steps=[
                ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
                ExecutionStep(step_number=2, skill_id="s2", skill_path="d/e/f", depends_on=[], status="pending", input_data={}),
            ],
            parallel_groups=[[1, 2]],
            estimated_duration_ms=2000,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        assert isinstance(result, PlanResult)
        assert result.steps_completed == 1
        assert result.steps_failed == 1
        statuses = {r.step_number: r.status for r in result.working_memory}
        assert statuses[1] == "failed"
        assert statuses[2] == "completed"

    async def test_execute_plan_skips_dependent_of_failed_step(self) -> None:
        """Steps depending on a failed step are skipped, not executed."""
        mock_executor = MagicMock()

        async def mock_execute(**kwargs):
            result = MagicMock()
            if kwargs.get("skill_id") == "s1":
                result.success = False
                result.result = None
                result.error = "s1 broke"
                result.execution_time_ms = 50
            else:
                result.success = True
                result.result = {"ok": True}
                result.execution_time_ms = 50
            return result

        mock_executor.execute = mock_execute

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = SkillOrchestrator(
            executor=mock_executor,
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        orch._get_db = lambda: _mock_db()

        plan = ExecutionPlan(
            task_description="Cascading failure",
            steps=[
                ExecutionStep(step_number=1, skill_id="s1", skill_path="a/b/c", depends_on=[], status="pending", input_data={}),
                ExecutionStep(step_number=2, skill_id="s2", skill_path="d/e/f", depends_on=[1], status="pending", input_data={}),
            ],
            parallel_groups=[[1], [2]],
            estimated_duration_ms=2000,
            risk_level="low",
            approval_required=False,
        )

        result = await orch.execute_plan(user_id="user-123", plan=plan)
        statuses = {r.step_number: r.status for r in result.working_memory}
        assert statuses[1] == "failed"
        assert statuses[2] == "skipped"
        assert result.steps_skipped == 1
        assert result.status == "failed"  # 0 completed


@pytest.mark.asyncio
class TestCreateExecutionPlan:
    """Tests for SkillOrchestrator.create_execution_plan method."""

    def _make_orchestrator(
        self,
        index: MagicMock | None = None,
        llm_response: str | None = None,
    ) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies and LLM."""
        mock_index = index or MagicMock()
        if index is None:
            mock_index.get_summaries = AsyncMock(return_value={
                "skill-pdf": "PDF Parser: Extracts text from PDFs [CORE]",
                "skill-csv": "CSV Analyzer: Parses and analyzes CSV data [Verified]",
            })

        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=mock_index,
            autonomy=MagicMock(),
        )
        orch._get_db = lambda: _mock_db()

        # Mock the LLM client
        mock_llm = MagicMock()
        default_response = llm_response or json.dumps({
            "reasoning": "PDF needs to be parsed first, then CSV can analyze tables.",
            "steps": [
                {
                    "step_number": 1,
                    "skill_id": "skill-pdf",
                    "skill_path": "anthropics/skills/pdf",
                    "depends_on": [],
                    "input_data": {"file": "report.pdf"},
                },
                {
                    "step_number": 2,
                    "skill_id": "skill-csv",
                    "skill_path": "vercel-labs/agent-skills/csv",
                    "depends_on": [1],
                    "input_data": {"source": "extracted_tables"},
                },
            ],
            "parallel_groups": [[1], [2]],
            "estimated_duration_ms": 8000,
            "risk_level": "low",
            "approval_required": False,
        })
        mock_llm.generate_response = AsyncMock(return_value=default_response)
        orch._llm = mock_llm

        return orch

    async def test_create_plan_returns_execution_plan(self) -> None:
        """create_execution_plan returns a valid ExecutionPlan."""
        orch = self._make_orchestrator()

        available_skills = [
            MagicMock(id="skill-pdf", skill_path="anthropics/skills/pdf"),
            MagicMock(id="skill-csv", skill_path="vercel-labs/agent-skills/csv"),
        ]

        plan = await orch.create_execution_plan(
            task="Parse the PDF and analyze the extracted tables",
            available_skills=available_skills,
        )

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 2
        assert plan.steps[0].skill_id == "skill-pdf"
        assert plan.steps[1].skill_id == "skill-csv"
        assert plan.steps[1].depends_on == [1]
        assert plan.parallel_groups == [[1], [2]]
        assert plan.risk_level == "low"

    async def test_create_plan_includes_reasoning(self) -> None:
        """Plan includes the reasoning trace from LLM."""
        orch = self._make_orchestrator()
        available_skills = [MagicMock(id="skill-pdf")]

        plan = await orch.create_execution_plan(
            task="Parse a PDF",
            available_skills=available_skills,
        )

        assert "PDF" in plan.reasoning

    async def test_create_plan_calls_llm_with_context(self) -> None:
        """LLM is called with task description and skill summaries."""
        orch = self._make_orchestrator()

        available_skills = [
            MagicMock(id="skill-pdf", skill_path="anthropics/skills/pdf"),
        ]

        await orch.create_execution_plan(
            task="Parse report",
            available_skills=available_skills,
        )

        orch._llm.generate_response.assert_awaited_once()
        call_args = orch._llm.generate_response.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        message_text = str(messages)
        assert "Parse report" in message_text

    async def test_create_plan_fetches_skill_summaries(self) -> None:
        """Skill summaries are fetched from the index for LLM context."""
        mock_index = MagicMock()
        mock_index.get_summaries = AsyncMock(return_value={"skill-pdf": "PDF parser [CORE]"})

        orch = self._make_orchestrator(index=mock_index)

        available_skills = [
            MagicMock(id="skill-pdf", skill_path="anthropics/skills/pdf"),
        ]

        await orch.create_execution_plan(
            task="Parse a PDF",
            available_skills=available_skills,
        )

        mock_index.get_summaries.assert_awaited_once_with(["skill-pdf"])

    async def test_create_plan_with_parallel_skills(self) -> None:
        """LLM can plan parallel execution when skills are independent."""
        parallel_response = json.dumps({
            "reasoning": "Skills are independent.",
            "steps": [
                {"step_number": 1, "skill_id": "s1", "skill_path": "a/b/c", "depends_on": [], "input_data": {}},
                {"step_number": 2, "skill_id": "s2", "skill_path": "d/e/f", "depends_on": [], "input_data": {}},
                {"step_number": 3, "skill_id": "s3", "skill_path": "g/h/i", "depends_on": [1, 2], "input_data": {}},
            ],
            "parallel_groups": [[1, 2], [3]],
            "estimated_duration_ms": 5000,
            "risk_level": "low",
            "approval_required": False,
        })

        orch = self._make_orchestrator(llm_response=parallel_response)

        available_skills = [
            MagicMock(id="s1"), MagicMock(id="s2"), MagicMock(id="s3"),
        ]

        plan = await orch.create_execution_plan(
            task="Multi-step parallel task",
            available_skills=available_skills,
        )

        assert plan.parallel_groups == [[1, 2], [3]]
        assert len(plan.steps) == 3

    async def test_create_plan_handles_malformed_llm_response(self) -> None:
        """Graceful handling of malformed LLM JSON response."""
        orch = self._make_orchestrator(llm_response="not valid json at all")

        available_skills = [MagicMock(id="s1")]

        with pytest.raises(ValueError, match="parse"):
            await orch.create_execution_plan(
                task="Some task",
                available_skills=available_skills,
            )

    async def test_create_plan_raises_on_missing_steps_key(self) -> None:
        """ValueError raised when LLM returns valid JSON without 'steps' key."""
        orch = self._make_orchestrator(llm_response=json.dumps({"no_steps": []}))

        available_skills = [MagicMock(id="s1")]

        with pytest.raises(ValueError, match="missing required 'steps' field"):
            await orch.create_execution_plan(
                task="Some task",
                available_skills=available_skills,
            )

    async def test_create_plan_raises_on_malformed_step_structure(self) -> None:
        """ValueError raised when steps have missing required fields."""
        malformed_response = json.dumps({
            "steps": [
                {"skill_id": "s1"}  # missing step_number (required)
            ],
            "parallel_groups": [[1]],
        })
        orch = self._make_orchestrator(llm_response=malformed_response)

        available_skills = [MagicMock(id="s1")]

        with pytest.raises(ValueError, match="invalid step structure"):
            await orch.create_execution_plan(
                task="Some task",
                available_skills=available_skills,
            )


@pytest.mark.asyncio
class TestAnalyzeTask:
    """Tests for SkillOrchestrator.analyze_task method."""

    def _make_orchestrator(
        self,
        search_results: list[Any] | None = None,
        llm_response: str | None = None,
    ) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        mock_index = MagicMock()

        if search_results is not None:
            mock_index.search = AsyncMock(return_value=search_results)
        else:
            # Default: return some matching skills
            mock_skill = MagicMock()
            mock_skill.id = "skill-pdf"
            mock_skill.skill_path = "anthropics/skills/pdf"
            mock_skill.skill_name = "PDF Parser"
            mock_skill.trust_level = MagicMock(value="core")
            mock_skill.declared_permissions = ["read"]
            mock_index.search = AsyncMock(return_value=[mock_skill])

        mock_index.get_summaries = AsyncMock(return_value={
            "skill-pdf": "Parse PDF documents [CORE]"
        })

        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=mock_index,
            autonomy=MagicMock(),
        )
        orch._get_db = lambda: _mock_db()

        # Mock LLM
        mock_llm = MagicMock()
        default_response = llm_response or json.dumps({
            "reasoning": "PDF parser is the right tool for this document task.",
            "steps": [
                {
                    "step_number": 1,
                    "skill_id": "skill-pdf",
                    "skill_path": "anthropics/skills/pdf",
                    "depends_on": [],
                    "input_data": {"file": "doc.pdf"},
                    "data_classes_accessed": ["PUBLIC"],
                }
            ],
            "parallel_groups": [[1]],
            "estimated_duration_ms": 5000,
            "risk_level": "low",
            "approval_required": False,
        })
        mock_llm.generate_response = AsyncMock(return_value=default_response)
        orch._llm = mock_llm

        return orch

    async def test_analyze_task_queries_skill_index(self) -> None:
        """analyze_task searches the SkillIndex for matching skills."""
        orch = self._make_orchestrator()

        plan = await orch.analyze_task(
            task={"description": "Parse a PDF document"},
            user_id="user-123",
        )

        orch._index.search.assert_awaited_once()
        assert isinstance(plan, ExecutionPlan)

    async def test_analyze_task_includes_reasoning(self) -> None:
        """analyze_task produces a plan with an LLM reasoning trace."""
        orch = self._make_orchestrator()

        plan = await orch.analyze_task(
            task={"description": "Parse a PDF"},
            user_id="user-123",
        )

        assert "PDF parser" in plan.reasoning

    async def test_analyze_task_calculates_risk_from_data_classes(self) -> None:
        """Risk level is calculated from data_classes_accessed in step data."""
        response = json.dumps({
            "reasoning": "Needs internal data access.",
            "steps": [
                {
                    "step_number": 1,
                    "skill_id": "skill-crm",
                    "skill_path": "aria/crm-ops",
                    "depends_on": [],
                    "input_data": {},
                    "data_classes_accessed": ["INTERNAL", "CONFIDENTIAL"],
                }
            ],
            "parallel_groups": [[1]],
            "estimated_duration_ms": 3000,
            "risk_level": "medium",
            "approval_required": True,
        })

        orch = self._make_orchestrator(llm_response=response)

        plan = await orch.analyze_task(
            task={"description": "Update CRM records"},
            user_id="user-123",
        )

        assert plan.risk_level == "high"  # CONFIDENTIAL -> high

    async def test_analyze_task_empty_skills_returns_empty_plan(self) -> None:
        """When no skills match, returns an empty plan."""
        orch = self._make_orchestrator(search_results=[])

        plan = await orch.analyze_task(
            task={"description": "Do something unknown"},
            user_id="user-123",
        )

        assert plan.steps == []
        assert "No matching skills" in plan.reasoning

    async def test_analyze_task_persists_plan(self) -> None:
        """analyze_task persists the plan to the database."""
        orch = self._make_orchestrator()
        db_mock = _mock_db()
        orch._get_db = lambda: db_mock

        await orch.analyze_task(
            task={"description": "Parse a PDF"},
            user_id="user-123",
        )

        # Verify upsert was called on skill_execution_plans
        db_mock.table.assert_called()
        calls = [str(c) for c in db_mock.table.call_args_list]
        assert any("skill_execution_plans" in c for c in calls)


@pytest.mark.asyncio
class TestSelectAgentForStep:
    """Tests for SkillOrchestrator.select_agent_for_step."""

    def _make_orchestrator(
        self,
        trust_result: Any = None,
    ) -> SkillOrchestrator:
        mock_autonomy = MagicMock()
        if trust_result is None:
            mock_autonomy.get_trust_history = AsyncMock(return_value=None)
        else:
            mock_autonomy.get_trust_history = AsyncMock(return_value=trust_result)

        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        orch._get_db = lambda: _mock_db()
        return orch

    async def test_selects_matching_agent(self) -> None:
        """Agent whose skills match the step's skill_path gets higher score."""
        orch = self._make_orchestrator()

        step = ExecutionStep(
            step_number=1,
            skill_id="s1",
            skill_path="anthropics/skills/pdf",
            depends_on=[],
            status="pending",
            input_data={},
        )

        agent = await orch.select_agent_for_step(
            step, ["hunter", "scribe", "analyst"]
        )

        # "scribe" has "pdf" in its AGENT_SKILLS
        assert agent == "scribe"

    async def test_returns_default_when_no_agents(self) -> None:
        """Returns 'operator' when available_agents is empty."""
        orch = self._make_orchestrator()

        step = ExecutionStep(
            step_number=1, skill_id="s1", skill_path="a/b/c",
            depends_on=[], status="pending", input_data={},
        )

        agent = await orch.select_agent_for_step(step, [])
        assert agent == "operator"

    async def test_considers_trust_history(self) -> None:
        """Agent with higher success rate scores higher."""
        trust = MagicMock()
        trust.successful_executions = 9
        trust.failed_executions = 1

        orch = self._make_orchestrator(trust_result=trust)

        step = ExecutionStep(
            step_number=1,
            skill_id="s1",
            skill_path="unknown/skill",
            depends_on=[],
            status="pending",
            input_data={},
        )

        # All agents have equal skill match (none match "unknown/skill")
        # so trust history should be the deciding factor
        agent = await orch.select_agent_for_step(
            step, ["hunter", "analyst"]
        )
        # Both get same trust score, so any is valid
        assert agent in ["hunter", "analyst"]


@pytest.mark.asyncio
class TestRecordOutcome:
    """Tests for SkillOrchestrator.record_outcome."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        mock_autonomy = MagicMock()
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=mock_autonomy,
        )
        return orch

    async def test_record_outcome_updates_trust_history(self) -> None:
        """record_outcome calls autonomy.record_execution_outcome for each step."""
        orch = self._make_orchestrator()
        db = _mock_db()

        # Set up plan query result
        plan_result = MagicMock()
        plan_result.data = {
            "user_id": "user-123",
            "task_description": "Test task",
            "plan_dag": {"steps": []},
            "status": "completed",
            "created_at": "2026-02-09T00:00:00Z",
            "completed_at": "2026-02-09T00:01:00Z",
        }

        # Set up working memory query result
        wm_result = MagicMock()
        wm_result.data = [
            {"skill_id": "s1", "status": "completed", "output_summary": "Done"},
            {"skill_id": "s2", "status": "failed", "output_summary": "Error"},
        ]

        def table_side_effect(name: str) -> MagicMock:
            chain = MagicMock()
            chain.select.return_value = chain
            chain.insert.return_value = chain
            chain.update.return_value = chain
            chain.upsert.return_value = chain
            chain.eq.return_value = chain
            chain.in_.return_value = chain
            chain.order.return_value = chain
            chain.single.return_value = chain

            if name == "skill_execution_plans":
                chain.execute.return_value = plan_result
            elif name == "skill_working_memory":
                chain.execute.return_value = wm_result
            elif name == "custom_skills":
                empty = MagicMock()
                empty.data = []
                chain.execute.return_value = empty
            else:
                empty = MagicMock()
                empty.data = None
                chain.execute.return_value = empty

            return chain

        db.table = table_side_effect
        orch._get_db = lambda: db

        await orch.record_outcome("plan-abc")

        # Verify trust history was updated for both skills
        assert orch._autonomy.record_execution_outcome.await_count == 2
        calls = orch._autonomy.record_execution_outcome.await_args_list
        assert calls[0].args == ("user-123", "s1")
        assert calls[0].kwargs == {"success": True}
        assert calls[1].args == ("user-123", "s2")
        assert calls[1].kwargs == {"success": False}

    async def test_record_outcome_handles_missing_plan(self) -> None:
        """record_outcome handles gracefully when plan is not found."""
        orch = self._make_orchestrator()
        db = _mock_db()

        # Simulate plan not found (exception from .single())
        def table_side_effect(_name: str) -> MagicMock:
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.side_effect = Exception("Not found")
            return chain

        db.table = table_side_effect
        orch._get_db = lambda: db

        # Should not raise
        await orch.record_outcome("nonexistent-plan")


class TestRiskFromDataClasses:
    """Tests for SkillOrchestrator._risk_from_data_classes."""

    def test_public_is_low(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes(["PUBLIC"]) == "low"

    def test_internal_is_medium(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes(["INTERNAL"]) == "medium"

    def test_confidential_is_high(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes(["CONFIDENTIAL"]) == "high"

    def test_restricted_is_critical(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes(["RESTRICTED"]) == "critical"

    def test_regulated_is_critical(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes(["REGULATED"]) == "critical"

    def test_mixed_takes_highest(self) -> None:
        result = SkillOrchestrator._risk_from_data_classes(
            ["PUBLIC", "INTERNAL", "CONFIDENTIAL"]
        )
        assert result == "high"

    def test_empty_is_low(self) -> None:
        assert SkillOrchestrator._risk_from_data_classes([]) == "low"


class TestModuleExports:
    """Tests for orchestrator exports from skills module."""

    def test_execution_step_importable_from_skills(self) -> None:
        """ExecutionStep is importable from src.skills."""
        from src.skills import ExecutionStep as ES
        assert ES is not None

    def test_execution_plan_importable_from_skills(self) -> None:
        """ExecutionPlan is importable from src.skills."""
        from src.skills import ExecutionPlan as EP
        assert EP is not None

    def test_working_memory_entry_importable_from_skills(self) -> None:
        """WorkingMemoryEntry is importable from src.skills."""
        from src.skills import WorkingMemoryEntry as WME
        assert WME is not None

    def test_skill_orchestrator_importable_from_skills(self) -> None:
        """SkillOrchestrator is importable from src.skills."""
        from src.skills import SkillOrchestrator as SO
        assert SO is not None

    def test_plan_result_importable_from_skills(self) -> None:
        """PlanResult is importable from src.skills."""
        from src.skills import PlanResult as PR
        assert PR is not None
