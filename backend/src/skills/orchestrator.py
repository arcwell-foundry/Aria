"""Skill orchestrator for multi-skill task execution.

Coordinates execution of multiple skills with:
- Dependency-aware execution ordering (DAG)
- Parallel execution of independent steps
- Working memory for inter-step context passing
- Progress callbacks for real-time updates
- Autonomy integration for approval checks
"""

import logging
import uuid
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
