"""Skill orchestrator for multi-skill task execution.

Coordinates execution of multiple skills with:
- Dependency-aware execution ordering (DAG)
- Parallel execution of independent steps
- Working memory for inter-step context passing
- Progress callbacks for real-time updates
- Autonomy integration for approval checks
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.skills.autonomy import SkillAutonomyService
from src.skills.executor import SkillExecutor
from src.skills.index import SkillIndex

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
