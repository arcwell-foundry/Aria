"""Tests for skill orchestrator service."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.skills.orchestrator import (
    ExecutionPlan,
    ExecutionStep,
    SkillOrchestrator,
    WorkingMemoryEntry,
)


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


class TestCanExecute:
    """Tests for SkillOrchestrator._can_execute method."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        return SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=MagicMock(),
        )

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


class TestBuildWorkingMemorySummary:
    """Tests for SkillOrchestrator._build_working_memory_summary method."""

    def _make_orchestrator(self) -> SkillOrchestrator:
        """Create orchestrator with mocked dependencies."""
        return SkillOrchestrator(
            executor=MagicMock(),
            index=MagicMock(),
            autonomy=MagicMock(),
        )

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
        return SkillOrchestrator(
            executor=executor or MagicMock(),
            index=MagicMock(),
            autonomy=autonomy or MagicMock(),
        )

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

        return SkillOrchestrator(
            executor=mock_executor,
            index=MagicMock(),
            autonomy=mock_autonomy,
        )

    async def test_execute_plan_single_step(self) -> None:
        """Execute a plan with a single step."""
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

        results = await orch.execute_plan(user_id="user-123", plan=plan)
        assert len(results) == 1
        assert results[0].status == "completed"
        assert results[0].step_number == 1

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

        results = await orch.execute_plan(user_id="user-123", plan=plan)
        assert len(results) == 2
        assert results[0].step_number == 1
        assert results[1].step_number == 2

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

        results = await orch.execute_plan(user_id="user-123", plan=plan)
        assert len(results) == 3
        step_3_entry = [r for r in results if r.step_number == 3][0]
        assert step_3_entry.status == "completed"

    async def test_execute_plan_empty_plan(self) -> None:
        """Empty plan returns empty results."""
        orch = self._make_orchestrator()
        plan = ExecutionPlan(
            task_description="Empty",
            steps=[],
            parallel_groups=[],
            estimated_duration_ms=0,
            risk_level="low",
            approval_required=False,
        )

        results = await orch.execute_plan(user_id="user-123", plan=plan)
        assert results == []

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

        results = await orch.execute_plan(user_id="user-123", plan=plan)
        assert len(results) == 2
        statuses = {r.step_number: r.status for r in results}
        assert statuses[1] == "failed"
        assert statuses[2] == "completed"
