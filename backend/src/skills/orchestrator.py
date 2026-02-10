"""Skill orchestrator for multi-skill task execution.

Coordinates execution of multiple skills with:
- Dependency-aware execution ordering (DAG)
- Parallel execution of independent steps
- Working memory for inter-step context passing
- Progress callbacks for real-time updates
- Autonomy integration for approval checks
- Database persistence for plans and working memory
- Dynamic agent delegation with scoring
- Performance tracking and learning
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.skill_aware_agent import AGENT_SKILLS
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.security.skill_audit import SkillAuditService
from src.skills.autonomy import SkillAutonomyService, SkillRiskLevel
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
        agent_id: Agent assigned to execute this step (None until delegated).
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
    agent_id: str | None = None


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
        reasoning: LLM reasoning trace explaining skill selection and ordering.
    """

    task_description: str
    steps: list[ExecutionStep]
    parallel_groups: list[list[int]]
    estimated_duration_ms: int
    risk_level: str
    approval_required: bool
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reasoning: str = ""
    parent_plan_id: str | None = None


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


@dataclass
class PlanResult:
    """Aggregate result from executing a full plan.

    Attributes:
        plan_id: ID of the executed plan.
        status: Overall outcome ("completed", "failed", "partial").
        steps_completed: Number of steps that succeeded.
        steps_failed: Number of steps that failed.
        steps_skipped: Number of steps skipped (approval required or dep failed).
        total_execution_ms: Total wall-clock time in milliseconds.
        working_memory: Full list of WorkingMemoryEntry from all steps.
    """

    plan_id: str
    status: str
    steps_completed: int
    steps_failed: int
    steps_skipped: int
    total_execution_ms: int
    working_memory: list[WorkingMemoryEntry]


# Type alias for progress callbacks
ProgressCallback = Callable[[int, str, str], Awaitable[None]]
# Arguments: (step_number, status, message)

# Risk level ordering for calculating plan-level risk
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class SkillOrchestrator:
    """Orchestrates multi-skill task execution.

    Plans and executes multi-step skill workflows with:
    - LLM-powered task analysis and dependency DAG construction
    - Parallel execution of independent steps
    - Working memory for inter-step context
    - Autonomy integration for approval checks
    - Progress callbacks for real-time updates
    - Database persistence of plans and working memory
    - Dynamic agent delegation (Enhancement 10)
    - Performance tracking and learning (Enhancement 4)
    """

    def __init__(
        self,
        executor: SkillExecutor,
        index: SkillIndex,
        autonomy: SkillAutonomyService,
        audit: SkillAuditService | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            executor: SkillExecutor for running individual skills.
            index: SkillIndex for skill metadata and summaries.
            autonomy: SkillAutonomyService for approval checks.
            audit: Optional SkillAuditService for audit logging.
        """
        self._executor = executor
        self._index = index
        self._autonomy = autonomy
        self._audit = audit
        self._llm = LLMClient()

    def _get_db(self) -> Any:
        """Get Supabase client, lazily initialized.

        Returns:
            Supabase client instance.
        """
        return SupabaseClient.get_client()

    # -------------------------------------------------------------------------
    # analyze_task: Enhancement 1 — Skill Reasoning
    # -------------------------------------------------------------------------

    async def analyze_task(
        self,
        task: dict[str, Any],
        user_id: str,
    ) -> ExecutionPlan:
        """Analyze a task and build a persisted execution plan.

        Queries the SkillIndex for matching capabilities, uses the LLM to
        generate a reasoning trace explaining skill selection and ordering,
        builds a DAG with parallel branches, and persists the plan to the
        skill_execution_plans table.

        Args:
            task: Task specification dict. Should contain a 'description' key.
            user_id: ID of the user requesting the analysis.

        Returns:
            An ExecutionPlan persisted to the database with status 'pending_approval'
            (or 'approved' if no approval needed).

        Raises:
            ValueError: If the LLM response cannot be parsed.
        """
        task_description = task.get("description", json.dumps(task, default=str))

        # Step 1: Query SkillIndex for matching capabilities
        matching_skills = await self._index.search(task_description, limit=20)

        if not matching_skills:
            logger.warning(
                "No matching skills found for task",
                extra={"user_id": user_id, "task": task_description[:200]},
            )
            # Return an empty plan
            plan = ExecutionPlan(
                task_description=task_description,
                steps=[],
                parallel_groups=[],
                estimated_duration_ms=0,
                risk_level="low",
                approval_required=False,
                reasoning="No matching skills found in the index for this task.",
            )
            await self._persist_plan(plan, user_id)
            return plan

        # Step 2: Get compact summaries for LLM context
        skill_ids = [s.id for s in matching_skills]
        summaries = await self._index.get_summaries(skill_ids)

        # Build skill metadata for the LLM
        skill_info_lines: list[str] = []
        for skill in matching_skills:
            summary = summaries.get(skill.id, skill.skill_name)
            permissions = (
                ", ".join(skill.declared_permissions) if skill.declared_permissions else "none"
            )
            skill_info_lines.append(
                f"- id={skill.id} path={skill.skill_path} "
                f"trust={skill.trust_level.value} "
                f"permissions=[{permissions}] "
                f"summary: {summary}"
            )
        skill_info_text = "\n".join(skill_info_lines)

        # Step 3: Use LLM with reasoning trace prompt
        system_prompt = (
            "You are ARIA's skill orchestration planner. Given a task and available "
            "skills, create an execution plan.\n\n"
            "You MUST output ONLY valid JSON with this structure:\n"
            "{\n"
            '  "reasoning": "A detailed explanation of WHY you chose these skills, '
            "in WHAT order, and WHAT data each skill needs access to. "
            'Explain dependency relationships.",\n'
            '  "steps": [\n'
            "    {\n"
            '      "step_number": 1,\n'
            '      "skill_id": "uuid-from-available-list",\n'
            '      "skill_path": "path/from/available/list",\n'
            '      "depends_on": [],\n'
            '      "input_data": {"key": "value"},\n'
            '      "data_classes_accessed": ["PUBLIC", "INTERNAL"]\n'
            "    }\n"
            "  ],\n"
            '  "parallel_groups": [[1, 2], [3]],\n'
            '  "estimated_duration_ms": 8000,\n'
            '  "risk_level": "low"|"medium"|"high"|"critical",\n'
            '  "approval_required": true|false\n'
            "}\n\n"
            "Rules:\n"
            "- Steps that depend on output from other steps must list those in depends_on\n"
            "- Independent steps should be grouped together in parallel_groups\n"
            "- parallel_groups must be ordered: dependencies come in earlier groups\n"
            "- Every step must appear in exactly one parallel group\n"
            "- risk_level is the highest risk among all steps based on data_classes_accessed:\n"
            "  PUBLIC=low, INTERNAL=medium, CONFIDENTIAL=high, RESTRICTED/REGULATED=critical\n"
            "- approval_required is true if risk_level is medium or higher\n"
            "- Only use skills from the available list below\n"
            "- Prefer fewer steps; don't add skills that don't contribute to the task"
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Task: {task_description}\n\n"
                    f"Available skills:\n{skill_info_text}\n\n"
                    "Create the execution plan with reasoning."
                ),
            }
        ]

        response = await self._llm.generate_response(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=3000,
        )

        # Step 4: Parse LLM response
        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}") from e

        if not isinstance(plan_data, dict) or "steps" not in plan_data:
            raise ValueError("Failed to parse LLM plan: response missing required 'steps' field")

        reasoning = plan_data.get("reasoning", "")

        # Step 5: Calculate risk_level from data classes accessed across all steps
        max_risk = "low"
        for step_data in plan_data.get("steps", []):
            data_classes = step_data.get("data_classes_accessed", [])
            step_risk = self._risk_from_data_classes(data_classes)
            if _RISK_ORDER.get(step_risk, 0) > _RISK_ORDER.get(max_risk, 0):
                max_risk = step_risk

        # Step 6: Build ExecutionPlan
        try:
            steps = [
                ExecutionStep(
                    step_number=s["step_number"],
                    skill_id=s["skill_id"],
                    skill_path=s.get("skill_path", ""),
                    depends_on=s.get("depends_on", []),
                    status="pending",
                    input_data=s.get("input_data", {}),
                )
                for s in plan_data["steps"]
            ]
        except (KeyError, TypeError) as e:
            raise ValueError(f"Failed to parse LLM plan: invalid step structure: {e}") from e

        # Estimate execution time from skill definitions
        estimated_ms = plan_data.get("estimated_duration_ms", 0)
        if not estimated_ms:
            estimated_ms = self._estimate_duration(steps, matching_skills)

        approval_required = plan_data.get("approval_required", max_risk != "low")

        plan = ExecutionPlan(
            task_description=task_description,
            steps=steps,
            parallel_groups=plan_data.get("parallel_groups", []),
            estimated_duration_ms=estimated_ms,
            risk_level=max_risk,
            approval_required=approval_required,
            reasoning=reasoning,
        )

        # Step 7: Persist plan to database
        await self._persist_plan(plan, user_id)

        logger.info(
            "Task analyzed and plan created",
            extra={
                "plan_id": plan.plan_id,
                "user_id": user_id,
                "step_count": len(steps),
                "risk_level": max_risk,
                "approval_required": approval_required,
            },
        )

        return plan

    # -------------------------------------------------------------------------
    # extend_plan: continue from a completed plan
    # -------------------------------------------------------------------------

    async def extend_plan(
        self,
        completed_plan_id: str,
        new_request: str,
        user_id: str,
    ) -> ExecutionPlan:
        """Create a new plan that extends a completed plan.

        Loads working memory from the completed plan and passes it as
        starting context to analyze_task(), so the new plan inherits all
        prior results. The returned plan is linked via parent_plan_id.

        Args:
            completed_plan_id: UUID of the completed plan to extend.
            new_request: The user's follow-on request.
            user_id: ID of the user requesting the extension.

        Returns:
            A new ExecutionPlan linked to the original via parent_plan_id.

        Raises:
            ValueError: If the plan is not found or not completed.
        """
        db = self._get_db()

        # Load the completed plan
        try:
            plan_response = (
                db.table("skill_execution_plans")
                .select("*")
                .eq("id", completed_plan_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        except Exception as e:
            raise ValueError(f"Plan not found: {completed_plan_id}") from e

        if not plan_response.data:
            raise ValueError(f"Plan not found: {completed_plan_id}")

        plan_row = plan_response.data
        if plan_row.get("status") not in ("completed", "failed"):
            raise ValueError(
                f"Can only extend completed/failed plans, "
                f"but plan {completed_plan_id} has status '{plan_row.get('status')}'"
            )

        # Load working memory entries from the completed plan
        try:
            wm_response = (
                db.table("skill_working_memory")
                .select("*")
                .eq("plan_id", completed_plan_id)
                .order("step_number")
                .execute()
            )
            wm_rows = wm_response.data or []
        except Exception as e:
            logger.warning("Failed to load working memory for plan %s: %s", completed_plan_id, e)
            wm_rows = []

        # Build context summary from prior working memory
        prior_context_parts: list[str] = []
        prior_context_parts.append(f"Previous task: {plan_row.get('task_description', 'unknown')}")
        prior_context_parts.append(f"Previous plan status: {plan_row.get('status', 'unknown')}")
        for row in wm_rows:
            step_num = row.get("step_number", "?")
            skill_id = row.get("skill_id", "?")
            status = row.get("status", "?")
            summary = row.get("output_summary", "")
            facts = row.get("extracted_facts", [])
            hints = row.get("next_step_hints", [])
            entry_str = f"Step {step_num} ({skill_id}) [{status}]: {summary}"
            if facts:
                facts_data = json.loads(facts) if isinstance(facts, str) else facts
                if isinstance(facts_data, dict):
                    facts_str = ", ".join(f"{k}={v}" for k, v in facts_data.items())
                    entry_str += f"\n  Facts: {facts_str}"
            if hints:
                hints_data = json.loads(hints) if isinstance(hints, str) else hints
                if isinstance(hints_data, list) and hints_data:
                    entry_str += f"\n  Hints: {'; '.join(str(h) for h in hints_data)}"
            prior_context_parts.append(entry_str)

        prior_context = "\n".join(prior_context_parts)

        # Build extended task description with prior context
        extended_task = {
            "description": (
                f"Follow-on request: {new_request}\n\n"
                f"Context from prior plan ({completed_plan_id}):\n{prior_context}"
            ),
        }

        # Use analyze_task to create the new plan
        new_plan = await self.analyze_task(extended_task, user_id)
        new_plan.parent_plan_id = completed_plan_id

        # Update persisted plan with parent link
        try:
            db.table("skill_execution_plans").update({"parent_plan_id": completed_plan_id}).eq(
                "id", new_plan.plan_id
            ).execute()
        except Exception as e:
            logger.warning("Failed to set parent_plan_id on plan %s: %s", new_plan.plan_id, e)

        logger.info(
            "Extended plan %s from parent %s",
            new_plan.plan_id,
            completed_plan_id,
            extra={
                "new_plan_id": new_plan.plan_id,
                "parent_plan_id": completed_plan_id,
                "user_id": user_id,
                "step_count": len(new_plan.steps),
            },
        )

        return new_plan

    # -------------------------------------------------------------------------
    # execute_plan: with DB persistence
    # -------------------------------------------------------------------------

    async def execute_plan_by_id(
        self,
        plan_id: str,
        user_id: str,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> PlanResult:
        """Load a plan from the database and execute it.

        Loads the plan from skill_execution_plans, reconstructs the
        ExecutionPlan, then delegates to execute_plan.

        Args:
            plan_id: UUID of the plan in skill_execution_plans.
            user_id: ID of the user requesting execution.
            progress_callback: Optional callback for real-time status updates.

        Returns:
            PlanResult with execution outcome and working memory.

        Raises:
            ValueError: If the plan is not found or doesn't belong to user.
        """
        db = self._get_db()

        try:
            response = (
                db.table("skill_execution_plans")
                .select("*")
                .eq("id", plan_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        except Exception as e:
            raise ValueError(f"Plan not found: {plan_id}") from e

        if not response.data:
            raise ValueError(f"Plan not found: {plan_id}")

        row = response.data
        plan_status = row.get("status", "draft")

        if plan_status in ("completed", "failed", "cancelled"):
            raise ValueError(f"Plan {plan_id} has already been executed (status={plan_status})")

        # Reconstruct ExecutionPlan from stored DAG
        plan_dag = row.get("plan_dag", {})
        steps = [
            ExecutionStep(
                step_number=s["step_number"],
                skill_id=s["skill_id"],
                skill_path=s.get("skill_path", ""),
                depends_on=s.get("depends_on", []),
                status="pending",
                input_data=s.get("input_data", {}),
            )
            for s in plan_dag.get("steps", [])
        ]

        plan = ExecutionPlan(
            task_description=row.get("task_description", ""),
            steps=steps,
            parallel_groups=plan_dag.get("parallel_groups", []),
            estimated_duration_ms=(row.get("estimated_seconds") or 0) * 1000,
            risk_level=row.get("risk_level", "low"),
            approval_required=False,  # Already approved if we're executing
            plan_id=plan_id,
            reasoning=row.get("reasoning", ""),
        )

        return await self.execute_plan(
            user_id=user_id,
            plan=plan,
            progress_callback=progress_callback,
        )

    async def execute_plan(
        self,
        user_id: str,
        plan: ExecutionPlan,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> PlanResult:
        """Execute a full plan respecting dependency order and parallelism.

        Iterates through parallel_groups in order. Within each group,
        executes all steps concurrently via asyncio.gather. Persists
        working memory entries and plan status to the database.

        Args:
            user_id: ID of the user requesting execution.
            plan: The execution plan to run.
            progress_callback: Optional callback for real-time status updates.

        Returns:
            PlanResult with execution outcome, timing, and working memory.
        """
        if not plan.steps:
            return PlanResult(
                plan_id=plan.plan_id,
                status="completed",
                steps_completed=0,
                steps_failed=0,
                steps_skipped=0,
                total_execution_ms=0,
                working_memory=[],
            )

        logger.info(
            "Executing plan %s: %d steps, %d groups",
            plan.plan_id,
            len(plan.steps),
            len(plan.parallel_groups),
            extra={"plan_id": plan.plan_id, "task": plan.task_description},
        )

        # Update plan status to executing
        await self._update_plan_status(plan.plan_id, "executing")

        plan_start = time.perf_counter()

        # Build step lookup
        step_map: dict[int, ExecutionStep] = {s.step_number: s for s in plan.steps}
        working_memory: list[WorkingMemoryEntry] = []
        completed_steps: dict[int, bool] = {}
        failed_steps: set[int] = set()

        for group in plan.parallel_groups:
            # Filter to steps whose dependencies are satisfied
            # Skip steps that depend on a failed step
            group_steps: list[ExecutionStep] = []
            for num in group:
                if num not in step_map:
                    continue
                step = step_map[num]
                if self._depends_on_failed(step, failed_steps):
                    # Skip — a dependency failed
                    step.status = "skipped"
                    entry = WorkingMemoryEntry(
                        step_number=step.step_number,
                        skill_id=step.skill_id,
                        status="skipped",
                        summary="Skipped: dependency failed.",
                        artifacts=[],
                        extracted_facts={},
                        next_step_hints=[],
                    )
                    working_memory.append(entry)
                    await self._persist_working_memory(plan.plan_id, entry, 0)
                    continue
                if self._can_execute(step, completed_steps):
                    group_steps.append(step)

            if len(group_steps) == 1:
                step = group_steps[0]
                entry = await self._execute_step(
                    user_id=user_id,
                    step=step,
                    working_memory=working_memory,
                    risk_level=plan.risk_level,
                    progress_callback=progress_callback,
                )
                working_memory.append(entry)
                exec_ms = self._step_duration_ms(step)
                await self._persist_working_memory(plan.plan_id, entry, exec_ms)
                if entry.status == "completed":
                    completed_steps[step.step_number] = True
                elif entry.status == "failed":
                    failed_steps.add(step.step_number)
            elif len(group_steps) > 1:
                tasks = [
                    self._execute_step(
                        user_id=user_id,
                        step=step,
                        working_memory=working_memory,
                        risk_level=plan.risk_level,
                        progress_callback=progress_callback,
                    )
                    for step in group_steps
                ]
                entries = await asyncio.gather(*tasks)
                for i, entry in enumerate(entries):
                    working_memory.append(entry)
                    exec_ms = self._step_duration_ms(group_steps[i])
                    await self._persist_working_memory(plan.plan_id, entry, exec_ms)
                    if entry.status == "completed":
                        completed_steps[entry.step_number] = True
                    elif entry.status == "failed":
                        failed_steps.add(entry.step_number)

        total_ms = int((time.perf_counter() - plan_start) * 1000)

        # Tally results
        steps_completed = sum(1 for e in working_memory if e.status == "completed")
        steps_failed = sum(1 for e in working_memory if e.status == "failed")
        steps_skipped = sum(1 for e in working_memory if e.status == "skipped")

        if steps_failed == 0 and steps_skipped == 0:
            plan_status = "completed"
        elif steps_completed == 0:
            plan_status = "failed"
        else:
            plan_status = "partial"

        # Update plan in database
        db_status = "completed" if plan_status in ("completed", "partial") else "failed"
        await self._update_plan_status(
            plan.plan_id,
            db_status,
            actual_seconds=total_ms // 1000,
        )

        logger.info(
            "Plan %s finished: %s (%d completed, %d failed, %d skipped) in %dms",
            plan.plan_id,
            plan_status,
            steps_completed,
            steps_failed,
            steps_skipped,
            total_ms,
            extra={"plan_id": plan.plan_id},
        )

        return PlanResult(
            plan_id=plan.plan_id,
            status=plan_status,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            steps_skipped=steps_skipped,
            total_execution_ms=total_ms,
            working_memory=working_memory,
        )

    # -------------------------------------------------------------------------
    # select_agent_for_step: Enhancement 10 — Dynamic Agent Delegation
    # -------------------------------------------------------------------------

    async def select_agent_for_step(
        self,
        step: ExecutionStep,
        available_agents: list[str],
    ) -> str:
        """Select the best agent for a step using a scoring function.

        Considers three factors:
        1. Skill-agent authorization match (does this agent's skill list
           include the step's skill path?)
        2. Historical success rate for this skill from trust history.
        3. Current agent workload (number of steps already assigned in
           this plan).

        Args:
            step: The execution step to assign.
            available_agents: List of agent IDs to choose from
                (e.g., ["hunter", "analyst", "scribe"]).

        Returns:
            The agent_id with the highest composite score.
            Falls back to the first available agent if no scores can be computed.
        """
        if not available_agents:
            return "operator"  # Sensible default

        scores: dict[str, float] = {}

        for agent_id in available_agents:
            score = 0.0

            # Factor 1: Skill authorization match (0-50 points)
            agent_skills = AGENT_SKILLS.get(agent_id, [])
            skill_path_parts = step.skill_path.lower().split("/")
            skill_name = skill_path_parts[-1] if skill_path_parts else ""

            if any(s.lower() in step.skill_path.lower() for s in agent_skills) or any(
                s.lower() == skill_name for s in agent_skills
            ):
                score += 50.0
            elif any(
                any(keyword in s.lower() for keyword in skill_path_parts) for s in agent_skills
            ):
                score += 25.0

            # Factor 2: Historical success rate (0-30 points)
            trust = await self._autonomy.get_trust_history(agent_id, step.skill_id)
            if trust is not None:
                total = trust.successful_executions + trust.failed_executions
                if total > 0:
                    success_rate = trust.successful_executions / total
                    score += success_rate * 30.0

            # Factor 3: Workload penalty (-20 to 0 points)
            # Count how many steps in the current plan are assigned to this agent
            # (fewer assignments = higher score)
            # This is approximate — we check the step's agent_id field
            # which gets set during delegation
            # No penalty for now since we don't track live workload here;
            # but the agent_id field on steps can be used by callers
            # to apply a workload bonus/penalty.

            scores[agent_id] = score

        # Select agent with highest score
        best_agent = max(scores, key=lambda a: scores[a])

        logger.debug(
            "Agent delegation scores for step %d: %s -> selected %s",
            step.step_number,
            {a: f"{s:.1f}" for a, s in scores.items()},
            best_agent,
            extra={"skill_id": step.skill_id, "skill_path": step.skill_path},
        )

        return best_agent

    # -------------------------------------------------------------------------
    # record_outcome: Enhancement 4 — Performance Tracking
    # -------------------------------------------------------------------------

    async def record_outcome(
        self,
        plan_id: str,
        user_feedback: dict[str, Any] | None = None,
    ) -> None:
        """Record execution outcome for learning and performance tracking.

        Updates multiple systems:
        1. skill_trust_history — success/failure per skill used.
        2. custom_skills.performance_metrics — if any custom skill was used.
        3. conversation_episodes — stores the execution as an episode.
        4. procedural_memories — if this was a successful new pattern.

        Also integrates with skill_audit_log via the existing audit service.

        Args:
            plan_id: UUID of the executed plan.
            user_feedback: Optional feedback dict with keys like
                'satisfaction' (1-5), 'corrections' (str), 'useful' (bool).
        """
        db = self._get_db()

        # Load plan
        try:
            plan_response = (
                db.table("skill_execution_plans").select("*").eq("id", plan_id).single().execute()
            )
        except Exception as e:
            logger.error("Failed to load plan for outcome recording: %s", e)
            return

        if not plan_response.data:
            logger.warning("Plan not found for outcome recording: %s", plan_id)
            return

        plan_row = plan_response.data
        user_id = plan_row["user_id"]
        plan_dag = plan_row.get("plan_dag", {})
        plan_status = plan_row.get("status", "unknown")

        # Load working memory entries for this plan
        try:
            wm_response = (
                db.table("skill_working_memory")
                .select("*")
                .eq("plan_id", plan_id)
                .order("step_number")
                .execute()
            )
            wm_entries = wm_response.data or []
        except Exception as e:
            logger.error("Failed to load working memory for plan %s: %s", plan_id, e)
            wm_entries = []

        # 1. Update skill_trust_history for each skill used
        for entry in wm_entries:
            skill_id = entry.get("skill_id", "")
            status = entry.get("status", "")
            if status in ("completed", "failed"):
                await self._autonomy.record_execution_outcome(
                    user_id, skill_id, success=(status == "completed")
                )

        # 2. Update custom_skills.performance_metrics if custom skill was used
        skill_ids_used = [e.get("skill_id", "") for e in wm_entries]
        if skill_ids_used:
            await self._update_custom_skill_metrics(db, skill_ids_used, wm_entries, user_feedback)

        # 3. Store as episode in conversation_episodes
        await self._store_execution_episode(
            db, plan_id, user_id, plan_row, wm_entries, user_feedback
        )

        # 4. Feed into procedural_memories if successful pattern
        if plan_status == "completed":
            await self._store_procedural_memory(db, user_id, plan_row, plan_dag, wm_entries)

        logger.info(
            "Recorded outcome for plan %s",
            plan_id,
            extra={
                "plan_id": plan_id,
                "user_id": user_id,
                "plan_status": plan_status,
                "feedback_provided": user_feedback is not None,
            },
        )

    # -------------------------------------------------------------------------
    # create_execution_plan: backward-compatible LLM planner
    # -------------------------------------------------------------------------

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
        summaries_text = "\n".join(f"- {sid}: {summary}" for sid, summary in summaries.items())

        system_prompt = (
            "You are a skill orchestration planner. Given a task and available skills, "
            "create an execution plan as a JSON object.\n\n"
            "Output ONLY valid JSON with this structure:\n"
            "{\n"
            '  "reasoning": "Explain WHY these skills in this order with this data access.",\n'
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

        # Validate required structure
        if not isinstance(plan_data, dict) or "steps" not in plan_data:
            raise ValueError("Failed to parse LLM plan: response missing required 'steps' field")

        # Build ExecutionPlan from parsed data
        try:
            steps = [
                ExecutionStep(
                    step_number=s["step_number"],
                    skill_id=s["skill_id"],
                    skill_path=s.get("skill_path", ""),
                    depends_on=s.get("depends_on", []),
                    status="pending",
                    input_data=s.get("input_data", {}),
                )
                for s in plan_data["steps"]
            ]
        except (KeyError, TypeError) as e:
            raise ValueError(f"Failed to parse LLM plan: invalid step structure: {e}") from e

        return ExecutionPlan(
            task_description=task,
            steps=steps,
            parallel_groups=plan_data.get("parallel_groups", []),
            estimated_duration_ms=plan_data.get("estimated_duration_ms", 0),
            risk_level=plan_data.get("risk_level", "low"),
            approval_required=plan_data.get("approval_required", False),
            reasoning=plan_data.get("reasoning", ""),
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _can_execute(self, step: ExecutionStep, completed_steps: dict[int, bool]) -> bool:
        """Check if a step's dependencies are satisfied.

        Args:
            step: The step to check.
            completed_steps: Map of step_number -> completion status.

        Returns:
            True if all dependencies are in completed_steps, False otherwise.
        """
        return all(dep in completed_steps for dep in step.depends_on)

    def _depends_on_failed(self, step: ExecutionStep, failed_steps: set[int]) -> bool:
        """Check if any of a step's dependencies have failed.

        Args:
            step: The step to check.
            failed_steps: Set of step numbers that failed.

        Returns:
            True if any dependency has failed, False otherwise.
        """
        return any(dep in failed_steps for dep in step.depends_on)

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
            section = (
                f"Step {entry.step_number} ({entry.skill_id}) [{entry.status}]: {entry.summary}"
            )
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
        risk_level: str = "low",
        progress_callback: ProgressCallback | None = None,
    ) -> WorkingMemoryEntry:
        """Execute a single step and produce a WorkingMemoryEntry.

        Checks autonomy approval, executes via SkillExecutor, records outcome,
        and builds a working memory entry from the result.

        Args:
            user_id: ID of the user requesting execution.
            step: The step to execute.
            working_memory: Prior step summaries for context.
            risk_level: Risk level for autonomy approval check.
            progress_callback: Optional callback for status updates.

        Returns:
            A WorkingMemoryEntry summarizing the step outcome.
        """
        # Map risk level string to enum
        risk_enum_map: dict[str, SkillRiskLevel] = {
            "low": SkillRiskLevel.LOW,
            "medium": SkillRiskLevel.MEDIUM,
            "high": SkillRiskLevel.HIGH,
            "critical": SkillRiskLevel.CRITICAL,
        }
        skill_risk = risk_enum_map.get(risk_level, SkillRiskLevel.LOW)

        # Check if approval is required
        needs_approval = await self._autonomy.should_request_approval(
            user_id, step.skill_id, skill_risk
        )

        if needs_approval:
            logger.info(
                "Step %d skipped: approval required",
                step.step_number,
                extra={"skill_id": step.skill_id, "user_id": user_id},
            )
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
        logger.debug(
            "Executing step %d (%s)",
            step.step_number,
            step.skill_path,
            extra={"skill_id": step.skill_id, "user_id": user_id},
        )
        if progress_callback:
            await progress_callback(step.step_number, "running", f"Executing {step.skill_path}")

        step.status = "running"
        step.started_at = datetime.now(UTC)

        # Build context with working memory
        memory_summary = self._build_working_memory_summary(working_memory)
        context: dict[str, Any] = {}
        if memory_summary:
            context["working_memory"] = memory_summary

        try:
            # Execute via SkillExecutor
            execution = await self._executor.execute(
                user_id=user_id,
                skill_id=step.skill_id,
                input_data=step.input_data,
                context=context,
                agent_id=step.agent_id,
            )

            # Record outcome in autonomy system
            await self._autonomy.record_execution_outcome(
                user_id, step.skill_id, success=execution.success
            )
        except Exception as e:
            logger.exception(
                "Unexpected error executing step %d",
                step.step_number,
                extra={"skill_id": step.skill_id, "user_id": user_id},
            )
            step.status = "failed"
            step.completed_at = datetime.now(UTC)
            entry = WorkingMemoryEntry(
                step_number=step.step_number,
                skill_id=step.skill_id,
                status="failed",
                summary=f"Step failed: {e}",
                artifacts=[],
                extracted_facts={},
                next_step_hints=[],
            )
            if progress_callback:
                await progress_callback(step.step_number, "failed", entry.summary)
            return entry

        step.completed_at = datetime.now(UTC)

        if execution.success:
            step.status = "completed"
            step.output_data = (
                execution.result
                if isinstance(execution.result, dict)
                else {"result": execution.result}
            )

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

            logger.debug(
                "Step %d completed in %dms",
                step.step_number,
                execution.execution_time_ms,
                extra={"skill_id": step.skill_id, "user_id": user_id},
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

        logger.warning(
            "Step %d failed: %s",
            step.step_number,
            error_msg,
            extra={"skill_id": step.skill_id, "user_id": user_id},
        )
        if progress_callback:
            await progress_callback(step.step_number, "failed", entry.summary)

        return entry

    # -------------------------------------------------------------------------
    # Database persistence helpers
    # -------------------------------------------------------------------------

    async def _persist_plan(self, plan: ExecutionPlan, user_id: str) -> None:
        """Persist an execution plan to skill_execution_plans.

        Args:
            plan: The execution plan to persist.
            user_id: ID of the user who owns this plan.
        """
        db = self._get_db()

        plan_dag = {
            "steps": [
                {
                    "step_number": s.step_number,
                    "skill_id": s.skill_id,
                    "skill_path": s.skill_path,
                    "depends_on": s.depends_on,
                    "input_data": s.input_data,
                }
                for s in plan.steps
            ],
            "parallel_groups": plan.parallel_groups,
        }

        status = "pending_approval" if plan.approval_required else "approved"

        record: dict[str, Any] = {
            "id": plan.plan_id,
            "user_id": user_id,
            "task_description": plan.task_description,
            "plan_dag": json.dumps(plan_dag),
            "status": status,
            "risk_level": plan.risk_level,
            "reasoning": plan.reasoning,
            "estimated_seconds": plan.estimated_duration_ms // 1000,
        }
        if plan.parent_plan_id:
            record["parent_plan_id"] = plan.parent_plan_id

        try:
            db.table("skill_execution_plans").upsert(record).execute()
            logger.debug(
                "Persisted plan %s with status %s",
                plan.plan_id,
                status,
                extra={"plan_id": plan.plan_id, "user_id": user_id},
            )
        except Exception as e:
            logger.error(
                "Failed to persist plan %s: %s",
                plan.plan_id,
                e,
                extra={"plan_id": plan.plan_id, "user_id": user_id},
            )

    async def _update_plan_status(
        self,
        plan_id: str,
        status: str,
        *,
        actual_seconds: int | None = None,
    ) -> None:
        """Update plan status in the database.

        Args:
            plan_id: UUID of the plan.
            status: New status value.
            actual_seconds: Optional actual execution time in seconds.
        """
        db = self._get_db()

        update_data: dict[str, Any] = {"status": status}

        if status == "approved":
            update_data["approved_at"] = datetime.now(UTC).isoformat()
        elif status in ("completed", "failed"):
            update_data["completed_at"] = datetime.now(UTC).isoformat()

        if actual_seconds is not None:
            update_data["actual_seconds"] = actual_seconds

        try:
            db.table("skill_execution_plans").update(update_data).eq("id", plan_id).execute()
        except Exception as e:
            logger.error(
                "Failed to update plan status: %s",
                e,
                extra={"plan_id": plan_id, "status": status},
            )

    async def _persist_working_memory(
        self,
        plan_id: str,
        entry: WorkingMemoryEntry,
        execution_time_ms: int,
    ) -> None:
        """Persist a working memory entry to skill_working_memory.

        Args:
            plan_id: UUID of the parent plan.
            entry: The working memory entry to persist.
            execution_time_ms: Execution duration for this step.
        """
        db = self._get_db()

        record = {
            "plan_id": plan_id,
            "step_number": entry.step_number,
            "skill_id": entry.skill_id,
            "input_summary": None,
            "output_summary": entry.summary,
            "artifacts": json.dumps(entry.artifacts),
            "extracted_facts": json.dumps(entry.extracted_facts),
            "next_step_hints": json.dumps(entry.next_step_hints),
            "status": entry.status,
            "execution_time_ms": execution_time_ms,
        }

        try:
            db.table("skill_working_memory").insert(record).execute()
        except Exception as e:
            logger.error(
                "Failed to persist working memory for step %d: %s",
                entry.step_number,
                e,
                extra={"plan_id": plan_id, "skill_id": entry.skill_id},
            )

    # -------------------------------------------------------------------------
    # Risk and duration estimation helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _risk_from_data_classes(data_classes: list[str]) -> str:
        """Calculate risk level from data classes accessed.

        Args:
            data_classes: List of data class names (e.g., ["PUBLIC", "INTERNAL"]).

        Returns:
            Risk level string: "low", "medium", "high", or "critical".
        """
        class_risk = {
            "PUBLIC": "low",
            "INTERNAL": "medium",
            "CONFIDENTIAL": "high",
            "RESTRICTED": "critical",
            "REGULATED": "critical",
        }
        max_risk = "low"
        for dc in data_classes:
            risk = class_risk.get(dc.upper(), "low")
            if _RISK_ORDER.get(risk, 0) > _RISK_ORDER.get(max_risk, 0):
                max_risk = risk
        return max_risk

    @staticmethod
    def _estimate_duration(steps: list[ExecutionStep], skills: list[Any]) -> int:
        """Estimate total execution duration from skill definitions.

        Uses estimated_seconds from skill definitions when available,
        falls back to 30 seconds per step.

        Args:
            steps: List of execution steps.
            skills: List of skill index entries with estimated_seconds.

        Returns:
            Estimated duration in milliseconds.
        """
        skill_map: dict[str, int] = {}
        for skill in skills:
            est = getattr(skill, "estimated_seconds", None)
            if est:
                skill_map[skill.id] = est

        total_seconds = 0
        for step in steps:
            total_seconds += skill_map.get(step.skill_id, 30)

        return total_seconds * 1000

    @staticmethod
    def _step_duration_ms(step: ExecutionStep) -> int:
        """Calculate execution duration for a step from timestamps.

        Args:
            step: The step with started_at and completed_at timestamps.

        Returns:
            Duration in milliseconds, or 0 if timestamps unavailable.
        """
        if step.started_at and step.completed_at:
            delta = step.completed_at - step.started_at
            return int(delta.total_seconds() * 1000)
        return 0

    # -------------------------------------------------------------------------
    # record_outcome persistence helpers
    # -------------------------------------------------------------------------

    async def _update_custom_skill_metrics(
        self,
        db: Any,
        skill_ids: list[str],
        wm_entries: list[dict[str, Any]],
        user_feedback: dict[str, Any] | None,
    ) -> None:
        """Update performance_metrics on custom_skills if any were used.

        Args:
            db: Supabase client.
            skill_ids: List of skill IDs used in the plan.
            wm_entries: Working memory entries from the database.
            user_feedback: Optional user feedback dict.
        """
        try:
            response = (
                db.table("custom_skills")
                .select("id, performance_metrics")
                .in_("id", skill_ids)
                .execute()
            )

            for row in response.data or []:
                custom_id = row["id"]
                metrics = row.get("performance_metrics") or {
                    "success_rate": 0,
                    "executions": 0,
                    "avg_satisfaction": 0,
                }

                # Find matching working memory entries
                matching = [e for e in wm_entries if e.get("skill_id") == custom_id]
                successes = sum(1 for e in matching if e.get("status") == "completed")
                total_new = len(matching)

                if total_new == 0:
                    continue

                old_execs = metrics.get("executions", 0)
                new_execs = old_execs + total_new
                old_rate = metrics.get("success_rate", 0)
                new_rate = (old_rate * old_execs + successes) / new_execs if new_execs > 0 else 0

                # Update satisfaction if feedback provided
                avg_sat = metrics.get("avg_satisfaction", 0)
                if user_feedback and "satisfaction" in user_feedback:
                    sat = user_feedback["satisfaction"]
                    avg_sat = (avg_sat * old_execs + sat) / new_execs

                updated_metrics = {
                    "success_rate": round(new_rate, 3),
                    "executions": new_execs,
                    "avg_satisfaction": round(avg_sat, 2),
                }

                db.table("custom_skills").update(
                    {"performance_metrics": json.dumps(updated_metrics)}
                ).eq("id", custom_id).execute()

        except Exception as e:
            logger.error("Failed to update custom skill metrics: %s", e)

    async def _store_execution_episode(
        self,
        db: Any,
        plan_id: str,
        user_id: str,
        plan_row: dict[str, Any],
        wm_entries: list[dict[str, Any]],
        user_feedback: dict[str, Any] | None,
    ) -> None:
        """Store the plan execution as a conversation episode.

        Args:
            db: Supabase client.
            plan_id: UUID of the plan.
            user_id: UUID of the user.
            plan_row: Plan row from database.
            wm_entries: Working memory entries.
            user_feedback: Optional user feedback.
        """
        try:
            task_desc = plan_row.get("task_description", "")
            status = plan_row.get("status", "unknown")
            skill_ids = [e.get("skill_id", "") for e in wm_entries]
            step_summaries = [
                e.get("output_summary", "") for e in wm_entries if e.get("output_summary")
            ]

            summary = (
                f"Skill execution plan '{task_desc[:100]}' {status}. "
                f"Steps: {len(wm_entries)}. " + (" | ".join(step_summaries[:3]))
            )

            outcomes: list[dict[str, Any]] = [
                {
                    "type": "skill_execution",
                    "plan_id": plan_id,
                    "status": status,
                    "skills_used": skill_ids,
                }
            ]

            if user_feedback:
                outcomes.append(
                    {
                        "type": "user_feedback",
                        "feedback": user_feedback,
                    }
                )

            now = datetime.now(UTC)
            record = {
                "user_id": user_id,
                "conversation_id": str(uuid.uuid4()),  # Standalone episode
                "summary": summary[:2000],
                "key_topics": ["skill_execution", status],
                "entities_discussed": skill_ids[:10],
                "outcomes": json.dumps(outcomes),
                "open_threads": json.dumps([]),
                "message_count": len(wm_entries),
                "started_at": plan_row.get("created_at", now.isoformat()),
                "ended_at": plan_row.get("completed_at", now.isoformat()),
            }

            db.table("conversation_episodes").insert(record).execute()

        except Exception as e:
            logger.error("Failed to store execution episode: %s", e)

    async def _store_procedural_memory(
        self,
        db: Any,
        user_id: str,
        plan_row: dict[str, Any],
        plan_dag: dict[str, Any],
        wm_entries: list[dict[str, Any]],
    ) -> None:
        """Store a successful execution pattern as procedural memory.

        Only creates a new memory if no similar workflow already exists.

        Args:
            db: Supabase client.
            user_id: UUID of the user.
            plan_row: Plan row from database.
            plan_dag: The plan DAG structure.
            wm_entries: Working memory entries.
        """
        try:
            task_desc = plan_row.get("task_description", "")

            # Build the trigger conditions from the task
            trigger_conditions = {
                "task_keywords": task_desc.split()[:10],
                "skill_count": len(wm_entries),
            }

            # Build steps from the plan DAG
            dag_steps = plan_dag.get("steps", [])
            workflow_steps = [
                {
                    "skill_id": s.get("skill_id", ""),
                    "skill_path": s.get("skill_path", ""),
                    "input_template": s.get("input_data", {}),
                    "depends_on": s.get("depends_on", []),
                }
                for s in dag_steps
            ]

            # Check if a similar workflow already exists (by skill combination)
            skill_ids = sorted(s.get("skill_id", "") for s in dag_steps)
            existing = (
                db.table("procedural_memories")
                .select("id, success_count")
                .eq("user_id", user_id)
                .eq("workflow_name", f"auto:{'-'.join(skill_ids[:5])}")
                .execute()
            )

            if existing.data:
                # Increment success_count on existing
                row = existing.data[0]
                db.table("procedural_memories").update(
                    {"success_count": row["success_count"] + 1}
                ).eq("id", row["id"]).execute()
                return

            # Create new procedural memory
            record = {
                "user_id": user_id,
                "workflow_name": f"auto:{'-'.join(skill_ids[:5])}",
                "description": f"Learned from successful plan: {task_desc[:200]}",
                "trigger_conditions": json.dumps(trigger_conditions),
                "steps": json.dumps(workflow_steps),
                "success_count": 1,
                "failure_count": 0,
                "is_shared": False,
            }

            db.table("procedural_memories").insert(record).execute()

        except Exception as e:
            logger.error("Failed to store procedural memory: %s", e)
