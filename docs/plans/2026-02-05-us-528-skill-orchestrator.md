# US-528: Skill Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a skill orchestrator that plans and executes multi-skill tasks with dependency awareness, parallel execution, working memory, and progress callbacks.

**Architecture:** SkillOrchestrator coordinates between SkillExecutor (runs individual skills through security pipeline), SkillIndex (looks up skill metadata/summaries), and SkillAutonomyService (checks if approval is needed). It uses the LLM to analyze a task and build a dependency DAG as an ExecutionPlan, then executes steps respecting that DAG — running independent steps in parallel via `asyncio.gather` and feeding prior step summaries as working memory to subsequent steps.

**Tech Stack:** Python 3.11+, dataclasses, asyncio, uuid, LLMClient (from `src.core.llm`), existing skills infrastructure

---

## Task 1: Create ExecutionStep and ExecutionPlan Dataclasses

**Files:**
- Create: `backend/src/skills/orchestrator.py`
- Test: `backend/tests/test_skill_orchestrator.py`

**Step 1: Write the failing tests for ExecutionStep**

```python
# backend/tests/test_skill_orchestrator.py
"""Tests for skill orchestrator service."""

from datetime import UTC, datetime

import pytest

from src.skills.orchestrator import ExecutionStep


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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestExecutionStep -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.skills.orchestrator'`

**Step 3: Write minimal implementation**

```python
# backend/src/skills/orchestrator.py
"""Skill orchestrator for multi-skill task execution.

Coordinates execution of multiple skills with:
- Dependency-aware execution ordering (DAG)
- Parallel execution of independent steps
- Working memory for inter-step context passing
- Progress callbacks for real-time updates
- Autonomy integration for approval checks
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionStep:
    """A single step in a multi-skill execution plan.

    Attributes:
        step_number: Position in the plan (1-based).
        skill_id: UUID of the skill to execute.
        skill_path: Path identifier (e.g., "anthropics/skills/pdf").
        depends_on: Step numbers that must complete before this step.
        status: Current status ("pending", "running", "completed", "failed", "skipped").
        input_data: Data to pass to the skill.
        output_data: Result from skill execution (None until completed).
        started_at: When execution started (None until running).
        completed_at: When execution finished (None until completed/failed).
    """

    step_number: int
    skill_id: str
    skill_path: str
    depends_on: list[int]
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestExecutionStep -v`
Expected: PASS (3 passed)

**Step 5: Write the failing tests for ExecutionPlan**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
from src.skills.orchestrator import ExecutionPlan, ExecutionStep


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
        # plan_id should be auto-generated UUID string
        assert len(plan.plan_id) == 36  # UUID format: 8-4-4-4-12

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
```

**Step 6: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestExecutionPlan -v`
Expected: FAIL with `ImportError: cannot import name 'ExecutionPlan'`

**Step 7: Write minimal implementation**

Add to `backend/src/skills/orchestrator.py` after `ExecutionStep`:

```python
import uuid


@dataclass
class ExecutionPlan:
    """A plan for executing multiple skills in sequence/parallel.

    Attributes:
        plan_id: Unique identifier for this plan (auto-generated UUID).
        task_description: Human-readable description of the overall task.
        steps: Ordered list of execution steps.
        parallel_groups: Groups of step numbers that can run concurrently.
            E.g., [[1, 2], [3]] means steps 1 & 2 run in parallel, then step 3.
        estimated_duration_ms: Estimated total execution time in milliseconds.
        risk_level: Overall risk level ("low", "medium", "high", "critical").
        approval_required: Whether user approval is needed before execution.
    """

    task_description: str
    steps: list[ExecutionStep]
    parallel_groups: list[list[int]]
    estimated_duration_ms: int
    risk_level: str
    approval_required: bool
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

Note: `import uuid` goes at the top of the file with the other imports.

**Step 8: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (6 passed)

**Step 9: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add ExecutionStep and ExecutionPlan dataclasses for orchestrator"
```

---

## Task 2: Create WorkingMemoryEntry Dataclass

**Files:**
- Modify: `backend/src/skills/orchestrator.py`
- Modify: `backend/tests/test_skill_orchestrator.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
from src.skills.orchestrator import WorkingMemoryEntry


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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestWorkingMemoryEntry -v`
Expected: FAIL with `ImportError: cannot import name 'WorkingMemoryEntry'`

**Step 3: Write minimal implementation**

Add to `backend/src/skills/orchestrator.py` after `ExecutionPlan`:

```python
@dataclass
class WorkingMemoryEntry:
    """Summary of a completed step for passing context to subsequent steps.

    Kept compact (~200 tokens per entry) so orchestrator context stays within budget.

    Attributes:
        step_number: Which step this summarizes.
        skill_id: The skill that was executed.
        status: Outcome status ("completed", "failed", "skipped").
        summary: Human-readable summary of what happened (~1-2 sentences).
        artifacts: List of artifact identifiers produced by the step.
        extracted_facts: Key facts extracted from the output (structured).
        next_step_hints: Suggestions for what the next step should do with this data.
    """

    step_number: int
    skill_id: str
    status: str
    summary: str
    artifacts: list[str]
    extracted_facts: dict[str, Any]
    next_step_hints: list[str]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (8 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add WorkingMemoryEntry dataclass for inter-step context"
```

---

## Task 3: Create SkillOrchestrator with _can_execute and _build_working_memory_summary

**Files:**
- Modify: `backend/src/skills/orchestrator.py`
- Modify: `backend/tests/test_skill_orchestrator.py`

These are pure logic methods with no external dependencies, so they're easiest to test first.

**Step 1: Write the failing tests**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from src.skills.orchestrator import (
    ExecutionPlan,
    ExecutionStep,
    SkillOrchestrator,
    WorkingMemoryEntry,
)


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
        completed = {1: True}  # step 2 not done
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestCanExecute tests/test_skill_orchestrator.py::TestBuildWorkingMemorySummary -v`
Expected: FAIL with `ImportError: cannot import name 'SkillOrchestrator'`

**Step 3: Write minimal implementation**

Add to `backend/src/skills/orchestrator.py`:

```python
from typing import Callable, Awaitable

from src.skills.executor import SkillExecutor
from src.skills.index import SkillIndex
from src.skills.autonomy import SkillAutonomyService

# Type alias for progress callbacks
ProgressCallback = Callable[[int, str, str], Awaitable[None]]
# Arguments: (step_number, status, message)


class SkillOrchestrator:
    """Orchestrates multi-skill task execution.

    Plans and executes multi-step skill workflows with:
    - LLM-powered task analysis and dependency DAG construction
    - Parallel execution of independent steps
    - Working memory for inter-step context
    - Autonomy integration for approval checks
    - Progress callbacks for real-time updates

    Args:
        executor: SkillExecutor for running individual skills.
        index: SkillIndex for skill metadata and summaries.
        autonomy: SkillAutonomyService for approval checks.
    """

    def __init__(
        self,
        executor: SkillExecutor,
        index: SkillIndex,
        autonomy: SkillAutonomyService,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            executor: SkillExecutor for running individual skills.
            index: SkillIndex for skill metadata and summaries.
            autonomy: SkillAutonomyService for approval checks.
        """
        self._executor = executor
        self._index = index
        self._autonomy = autonomy

    def _can_execute(
        self, step: ExecutionStep, completed_steps: dict[int, bool]
    ) -> bool:
        """Check if a step's dependencies are satisfied.

        Args:
            step: The step to check.
            completed_steps: Map of step_number -> completion status.

        Returns:
            True if all dependencies are in completed_steps, False otherwise.
        """
        return all(dep in completed_steps for dep in step.depends_on)

    def _build_working_memory_summary(self, entries: list[WorkingMemoryEntry]) -> str:
        """Build a compact text summary from working memory entries.

        Produces a structured summary suitable for inclusion in LLM context
        or for passing to subsequent skill steps.

        Args:
            entries: List of WorkingMemoryEntry from completed steps.

        Returns:
            Formatted string summary. Empty string if no entries.
        """
        if not entries:
            return ""

        parts: list[str] = []
        for entry in entries:
            section = f"Step {entry.step_number} ({entry.skill_id}) [{entry.status}]: {entry.summary}"
            if entry.extracted_facts:
                facts_str = ", ".join(f"{k}={v}" for k, v in entry.extracted_facts.items())
                section += f"\n  Facts: {facts_str}"
            if entry.next_step_hints:
                hints_str = "; ".join(entry.next_step_hints)
                section += f"\n  Hints: {hints_str}"
            parts.append(section)

        return "\n".join(parts)
```

Note: The imports `from src.skills.executor import SkillExecutor`, `from src.skills.index import SkillIndex`, and `from src.skills.autonomy import SkillAutonomyService` go at the top of the file. The `ProgressCallback` type alias and class go after the dataclasses.

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (17 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add SkillOrchestrator with _can_execute and working memory summary"
```

---

## Task 4: Implement _execute_step Method

**Files:**
- Modify: `backend/src/skills/orchestrator.py`
- Modify: `backend/tests/test_skill_orchestrator.py`

This method executes a single step via SkillExecutor and produces a WorkingMemoryEntry.

**Step 1: Write the failing tests**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
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
        assert "summary" in entry.extracted_facts or len(entry.summary) > 0
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

        # Verify context was passed to executor
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

        # Should have at least "running" and "completed" callbacks
        statuses = [c[1] for c in callback_calls]
        assert "running" in statuses
        assert "completed" in statuses
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestExecuteStep -v`
Expected: FAIL with `TypeError` (method doesn't exist)

**Step 3: Write minimal implementation**

Add to the `SkillOrchestrator` class in `backend/src/skills/orchestrator.py`:

```python
    async def _execute_step(
        self,
        user_id: str,
        step: ExecutionStep,
        working_memory: list[WorkingMemoryEntry],
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> WorkingMemoryEntry:
        """Execute a single step and produce a WorkingMemoryEntry.

        Checks autonomy approval, executes via SkillExecutor, records outcome,
        and builds a working memory entry from the result.

        Args:
            user_id: ID of the user requesting execution.
            step: The step to execute.
            working_memory: Prior step summaries for context.
            progress_callback: Optional callback for status updates.

        Returns:
            A WorkingMemoryEntry summarizing the step outcome.
        """
        from datetime import UTC, datetime

        from src.skills.autonomy import SkillRiskLevel

        # Check if approval is required
        needs_approval = await self._autonomy.should_request_approval(
            user_id, step.skill_id, SkillRiskLevel.LOW
        )

        if needs_approval:
            if progress_callback:
                await progress_callback(step.step_number, "skipped", "Approval required")
            return WorkingMemoryEntry(
                step_number=step.step_number,
                skill_id=step.skill_id,
                status="skipped",
                summary=f"Step skipped: approval required for skill {step.skill_id}.",
                artifacts=[],
                extracted_facts={},
                next_step_hints=[],
            )

        # Notify running
        if progress_callback:
            await progress_callback(
                step.step_number, "running", f"Executing {step.skill_path}"
            )

        step.status = "running"
        step.started_at = datetime.now(UTC)

        # Build context with working memory
        memory_summary = self._build_working_memory_summary(working_memory)
        context: dict[str, Any] = {}
        if memory_summary:
            context["working_memory"] = memory_summary

        # Execute via SkillExecutor
        execution = await self._executor.execute(
            user_id=user_id,
            skill_id=step.skill_id,
            input_data=step.input_data,
            context=context,
        )

        # Record outcome in autonomy system
        await self._autonomy.record_execution_outcome(
            user_id, step.skill_id, success=execution.success
        )

        step.completed_at = datetime.now(UTC)

        if execution.success:
            step.status = "completed"
            step.output_data = execution.result if isinstance(execution.result, dict) else {"result": execution.result}

            # Build working memory entry
            extracted = step.output_data if step.output_data else {}
            entry = WorkingMemoryEntry(
                step_number=step.step_number,
                skill_id=step.skill_id,
                status="completed",
                summary=f"Executed {step.skill_path} successfully in {execution.execution_time_ms}ms.",
                artifacts=[],
                extracted_facts=extracted,
                next_step_hints=[],
            )

            if progress_callback:
                await progress_callback(step.step_number, "completed", entry.summary)

            return entry

        # Failed execution
        step.status = "failed"
        error_msg = execution.error or "Unknown error"
        entry = WorkingMemoryEntry(
            step_number=step.step_number,
            skill_id=step.skill_id,
            status="failed",
            summary=f"Step failed: {error_msg}",
            artifacts=[],
            extracted_facts={},
            next_step_hints=[],
        )

        if progress_callback:
            await progress_callback(step.step_number, "failed", entry.summary)

        return entry
```

Also add to the top-level imports:

```python
from datetime import UTC, datetime
```

(Replace the existing `from datetime import datetime` if present.)

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (22 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add _execute_step with autonomy check and progress callbacks"
```

---

## Task 5: Implement execute_plan Method

**Files:**
- Modify: `backend/src/skills/orchestrator.py`
- Modify: `backend/tests/test_skill_orchestrator.py`

This is the main orchestration loop that executes plan steps respecting the dependency DAG and running independent steps in parallel.

**Step 1: Write the failing tests**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
import asyncio


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
        execution_order: list[int] = []

        mock_executor = MagicMock()

        async def mock_execute(**kwargs: Any) -> MagicMock:
            skill_id = kwargs.get("skill_id", "")
            step_num = int(skill_id.replace("s", ""))
            execution_order.append(step_num)
            result = MagicMock()
            result.success = True
            result.result = {"step": step_num}
            result.execution_time_ms = 100
            return result

        mock_executor.execute = mock_execute

        mock_autonomy = MagicMock()
        mock_autonomy.should_request_approval = AsyncMock(return_value=False)
        mock_autonomy.record_execution_outcome = AsyncMock(return_value=None)

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

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
        # Steps 1 and 2 should complete before step 3
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

        assert len(callback_calls) >= 2  # at least "running" and "completed"

    async def test_execute_plan_continues_after_step_failure(self) -> None:
        """Plan continues executing independent steps even if one fails."""
        call_count = 0
        mock_executor = MagicMock()

        async def mock_execute(**kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
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

        orch = self._make_orchestrator(executor=mock_executor, autonomy=mock_autonomy)

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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestExecutePlan -v`
Expected: FAIL with `AttributeError: 'SkillOrchestrator' object has no attribute 'execute_plan'`

**Step 3: Write minimal implementation**

Add to the `SkillOrchestrator` class in `backend/src/skills/orchestrator.py`:

```python
    async def execute_plan(
        self,
        user_id: str,
        plan: ExecutionPlan,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> list[WorkingMemoryEntry]:
        """Execute a full plan respecting dependency order and parallelism.

        Iterates through parallel_groups in order. Within each group,
        executes all steps concurrently via asyncio.gather. Accumulates
        working memory entries to pass context to subsequent steps.

        Args:
            user_id: ID of the user requesting execution.
            plan: The execution plan to run.
            progress_callback: Optional callback for real-time status updates.

        Returns:
            List of WorkingMemoryEntry, one per step (in execution order).
        """
        import asyncio

        if not plan.steps:
            return []

        # Build step lookup
        step_map: dict[int, ExecutionStep] = {s.step_number: s for s in plan.steps}
        working_memory: list[WorkingMemoryEntry] = []
        completed_steps: dict[int, bool] = {}

        for group in plan.parallel_groups:
            # Filter to steps that are actually executable in this group
            group_steps = [step_map[num] for num in group if num in step_map]

            if len(group_steps) == 1:
                # Single step - execute directly
                step = group_steps[0]
                entry = await self._execute_step(
                    user_id=user_id,
                    step=step,
                    working_memory=working_memory,
                    progress_callback=progress_callback,
                )
                working_memory.append(entry)
                completed_steps[step.step_number] = True
            elif len(group_steps) > 1:
                # Multiple steps - execute in parallel
                tasks = [
                    self._execute_step(
                        user_id=user_id,
                        step=step,
                        working_memory=working_memory,
                        progress_callback=progress_callback,
                    )
                    for step in group_steps
                ]
                entries = await asyncio.gather(*tasks)
                for entry in entries:
                    working_memory.append(entry)
                    completed_steps[entry.step_number] = True

        return working_memory
```

Also add `import asyncio` at the top of the file (with the other imports).

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (28 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add execute_plan with parallel group execution and progress callbacks"
```

---

## Task 6: Implement create_execution_plan Method

**Files:**
- Modify: `backend/src/skills/orchestrator.py`
- Modify: `backend/tests/test_skill_orchestrator.py`

This uses the LLM to analyze a task and available skills to build an ExecutionPlan.

**Step 1: Write the failing tests**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
import json


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

        # Mock the LLM client
        mock_llm = MagicMock()
        default_response = llm_response or json.dumps({
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
        # The task should be in the messages
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestCreateExecutionPlan -v`
Expected: FAIL with `AttributeError: 'SkillOrchestrator' object has no attribute 'create_execution_plan'`

**Step 3: Write minimal implementation**

Add to the `SkillOrchestrator` class in `backend/src/skills/orchestrator.py`:

First add at the top-level imports:

```python
import json
from src.core.llm import LLMClient
```

Then modify `__init__` to also create an LLM client:

```python
    def __init__(
        self,
        executor: SkillExecutor,
        index: SkillIndex,
        autonomy: SkillAutonomyService,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            executor: SkillExecutor for running individual skills.
            index: SkillIndex for skill metadata and summaries.
            autonomy: SkillAutonomyService for approval checks.
        """
        self._executor = executor
        self._index = index
        self._autonomy = autonomy
        self._llm = LLMClient()
```

Then add the method:

```python
    async def create_execution_plan(
        self,
        task: str,
        available_skills: list[Any],
    ) -> ExecutionPlan:
        """Use LLM to analyze a task and build an execution plan.

        Fetches skill summaries, sends them with the task to the LLM,
        and parses the response into an ExecutionPlan with a dependency DAG.

        Args:
            task: Natural language description of the task to accomplish.
            available_skills: List of skill objects (must have .id attribute).

        Returns:
            An ExecutionPlan with steps, dependencies, and parallel groups.

        Raises:
            ValueError: If the LLM response cannot be parsed into a valid plan.
        """
        # Get compact summaries for context
        skill_ids = [s.id for s in available_skills]
        summaries = await self._index.get_summaries(skill_ids)

        # Build summaries text for LLM
        summaries_text = "\n".join(
            f"- {sid}: {summary}" for sid, summary in summaries.items()
        )

        system_prompt = (
            "You are a skill orchestration planner. Given a task and available skills, "
            "create an execution plan as a JSON object.\n\n"
            "Output ONLY valid JSON with this structure:\n"
            "{\n"
            '  "steps": [{"step_number": int, "skill_id": str, "skill_path": str, '
            '"depends_on": [int], "input_data": {}}],\n'
            '  "parallel_groups": [[int]] (groups of step numbers that can run concurrently),\n'
            '  "estimated_duration_ms": int,\n'
            '  "risk_level": "low"|"medium"|"high"|"critical",\n'
            '  "approval_required": bool\n'
            "}\n\n"
            "Rules:\n"
            "- Steps that depend on output from other steps must list those in depends_on\n"
            "- Independent steps should be grouped together in parallel_groups\n"
            "- parallel_groups must be ordered: dependencies must come in earlier groups\n"
            "- Every step must appear in exactly one parallel group\n"
            "- risk_level is the highest risk among all steps\n"
            "- approval_required is true if any step has medium or higher risk"
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Task: {task}\n\n"
                    f"Available skills:\n{summaries_text}\n\n"
                    "Create the execution plan."
                ),
            }
        ]

        response = await self._llm.generate_response(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2048,
        )

        # Parse LLM response
        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}") from e

        # Build ExecutionPlan from parsed data
        steps = [
            ExecutionStep(
                step_number=s["step_number"],
                skill_id=s["skill_id"],
                skill_path=s.get("skill_path", ""),
                depends_on=s.get("depends_on", []),
                status="pending",
                input_data=s.get("input_data", {}),
            )
            for s in plan_data.get("steps", [])
        ]

        return ExecutionPlan(
            task_description=task,
            steps=steps,
            parallel_groups=plan_data.get("parallel_groups", []),
            estimated_duration_ms=plan_data.get("estimated_duration_ms", 0),
            risk_level=plan_data.get("risk_level", "low"),
            approval_required=plan_data.get("approval_required", False),
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (33 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/orchestrator.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): add create_execution_plan with LLM-powered task analysis"
```

---

## Task 7: Update Module Exports

**Files:**
- Modify: `backend/src/skills/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_orchestrator.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py::TestModuleExports -v`
Expected: FAIL with `ImportError: cannot import name 'ExecutionStep' from 'src.skills'`

**Step 3: Write minimal implementation**

Edit `backend/src/skills/__init__.py` to add the orchestrator imports. The final file should be:

```python
"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Installation and lifecycle management
- Security-aware execution
- Multi-skill orchestration
- Autonomy and trust management
"""

from src.skills.autonomy import (
    SKILL_RISK_THRESHOLDS,
    SkillAutonomyService,
    SkillRiskLevel,
    TrustHistory,
)
from src.skills.executor import SkillExecution, SkillExecutionError, SkillExecutor
from src.skills.index import (
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
    SkillIndex,
    SkillIndexEntry,
)
from src.skills.installer import InstalledSkill, SkillInstaller, SkillNotFoundError
from src.skills.orchestrator import (
    ExecutionPlan,
    ExecutionStep,
    SkillOrchestrator,
    WorkingMemoryEntry,
)

__all__ = [
    # Autonomy
    "SKILL_RISK_THRESHOLDS",
    "SkillAutonomyService",
    "SkillRiskLevel",
    "TrustHistory",
    # Index
    "SkillIndex",
    "SkillIndexEntry",
    "TIER_1_CORE_SKILLS",
    "TIER_2_RELEVANT_TAG",
    "TIER_3_DISCOVERY_ALL",
    # Installer
    "SkillInstaller",
    "InstalledSkill",
    "SkillNotFoundError",
    # Executor
    "SkillExecutor",
    "SkillExecution",
    "SkillExecutionError",
    # Orchestrator
    "SkillOrchestrator",
    "ExecutionPlan",
    "ExecutionStep",
    "WorkingMemoryEntry",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (37 passed)

**Step 5: Commit**

```bash
cd backend
git add src/skills/__init__.py tests/test_skill_orchestrator.py
git commit -m "feat(skills): export orchestrator types from skills module"
```

---

## Task 8: Run Full Test Suite and Final Verification

**Files:**
- No modifications

**Step 1: Run all orchestrator tests**

Run: `cd backend && python3 -m pytest tests/test_skill_orchestrator.py -v`
Expected: PASS (37 tests)

**Step 2: Run all skills tests to check for regressions**

Run: `cd backend && python3 -m pytest tests/test_skill_executor.py tests/test_skill_index.py tests/test_skill_installer.py tests/test_skill_autonomy.py tests/test_skill_orchestrator.py -v`
Expected: All PASS, no regressions

**Step 3: Run type checking**

Run: `cd backend && python3 -m mypy src/skills/orchestrator.py --strict`
Expected: No errors (or only pre-existing warnings from dependencies)

**Step 4: Run linting**

Run: `cd backend && ruff check src/skills/orchestrator.py && ruff format --check src/skills/orchestrator.py`
Expected: No issues

**Step 5: Fix any issues found in steps 3-4, then commit**

```bash
cd backend
git add -A
git commit -m "chore(skills): fix lint and type issues in orchestrator"
```

---

## Summary of Final File Structure

After all tasks, these files will exist:

```
backend/src/skills/orchestrator.py    (new - ~250 lines)
backend/src/skills/__init__.py        (modified - added orchestrator exports)
backend/tests/test_skill_orchestrator.py (new - ~400 lines)
```

The orchestrator.py file will contain:
- `ExecutionStep` dataclass
- `ExecutionPlan` dataclass (with auto-generated UUID)
- `WorkingMemoryEntry` dataclass
- `ProgressCallback` type alias
- `SkillOrchestrator` class with:
  - `__init__(executor, index, autonomy)`
  - `create_execution_plan(task, available_skills) -> ExecutionPlan`
  - `execute_plan(user_id, plan, progress_callback?) -> list[WorkingMemoryEntry]`
  - `_execute_step(user_id, step, working_memory, progress_callback?) -> WorkingMemoryEntry`
  - `_can_execute(step, completed_steps) -> bool`
  - `_build_working_memory_summary(entries) -> str`
