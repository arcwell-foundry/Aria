"""Base workflow for multi-step skill orchestration.

A workflow is an ordered sequence of skill invocations — each described by
a ``(skill_id, config)`` tuple — that together accomplish a larger task.

Workflows support:
- **Dependency chaining**: output from step *N* is available to step *N+1*.
- **Approval gates**: individual steps can be marked ``requiring_approval``
  so the orchestrator pauses for user confirmation before proceeding.
- **Result chaining**: the ``chain_results`` helper merges a prior step's
  output into the next step's input context.

Usage::

    class DealReviewWorkflow(BaseWorkflow):
        steps = [
            ("company_research", {"depth": "deep"}),
            ("stakeholder_mapping", {"include_org_chart": True}),
            ("competitive_analysis", {"requiring_approval": True}),
            ("deal_memo_generation", {}),
        ]
"""

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from src.core.llm import LLMClient
from src.skills.definitions.base import BaseSkillDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WorkflowStep(BaseModel):
    """A single step inside a workflow execution plan.

    Attributes:
        step_number: 1-based position in the workflow.
        skill_id: Identifier of the skill to invoke.
        config: Step-specific configuration dict.
        requiring_approval: If ``True``, execution pauses before this step
            and waits for an explicit user approval.
        status: Current lifecycle state.
        input_context: Merged context that will be passed to the skill.
        output_data: Result returned by the skill (``None`` until complete).
        error: Error message if the step failed.
        execution_time_ms: Wall-clock time for this step.
    """

    step_number: int
    skill_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    requiring_approval: bool = False
    status: str = "pending"  # pending | awaiting_approval | running | complete | failed
    input_context: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: int = 0


class WorkflowResult(BaseModel):
    """Aggregate result for a completed workflow."""

    success: bool
    steps: list[WorkflowStep]
    final_output: dict[str, Any] = Field(default_factory=dict)
    total_execution_time_ms: int = 0
    stopped_at_approval: int | None = Field(
        None,
        description="Step number where execution paused for approval (None if fully complete)",
    )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class BaseWorkflow:
    """Abstract base for multi-step skill workflows.

    Subclasses declare their step sequence by setting the ``steps`` class
    attribute — a list of ``(skill_id, config)`` tuples.

    Parameters:
        llm_client: Shared :class:`LLMClient` for skill execution.
        skill_loader: Callable that returns a :class:`BaseSkillDefinition`
            given a ``skill_id``.  Allows the workflow to remain decoupled
            from the specific skill registry.
    """

    steps: list[tuple[str, dict[str, Any]]] = []
    """Ordered ``(skill_id, config)`` pairs. Override in subclasses."""

    def __init__(
        self,
        llm_client: LLMClient,
        skill_loader: Any = None,
    ) -> None:
        self._llm = llm_client
        self._skill_loader = skill_loader or self._default_skill_loader

    # -- Plan building ---------------------------------------------------------

    def build_plan(self, task: dict[str, Any]) -> list[WorkflowStep]:
        """Build an execution plan from the declared ``steps``.

        The *task* dict is merged into every step's ``input_context`` so
        that each skill has access to the original user request.

        Args:
            task: Top-level task specification.

        Returns:
            List of :class:`WorkflowStep` instances ready for execution.
        """
        plan: list[WorkflowStep] = []

        for idx, (skill_id, config) in enumerate(self.steps, start=1):
            requiring_approval = config.pop("requiring_approval", False)

            step = WorkflowStep(
                step_number=idx,
                skill_id=skill_id,
                config=config,
                requiring_approval=bool(requiring_approval),
                input_context={**task},
            )
            plan.append(step)

        logger.info(
            "Workflow plan built",
            extra={
                "workflow": self.__class__.__name__,
                "total_steps": len(plan),
                "approval_gates": [s.step_number for s in plan if s.requiring_approval],
            },
        )
        return plan

    # -- Execution -------------------------------------------------------------

    async def execute_step(
        self,
        step: WorkflowStep,
        context: dict[str, Any],
    ) -> WorkflowStep:
        """Execute a single workflow step.

        Loads the skill definition, merges *context* into the step's
        ``input_context``, runs the skill, and populates ``output_data``.

        Args:
            step: The :class:`WorkflowStep` to execute.
            context: Additional runtime context (e.g. prior step outputs).

        Returns:
            The same step instance, mutated with results.
        """
        step.status = "running"
        step.input_context.update(context)
        step.input_context.update(step.config)

        start = time.perf_counter()
        try:
            skill: BaseSkillDefinition = self._skill_loader(step.skill_id)
            result = await skill.run(step.input_context)

            step.output_data = result
            step.status = "complete"

        except Exception as exc:
            step.error = str(exc)
            step.status = "failed"
            logger.error(
                "Workflow step failed",
                extra={
                    "workflow": self.__class__.__name__,
                    "step": step.step_number,
                    "skill": step.skill_id,
                    "error": step.error,
                },
            )

        step.execution_time_ms = int((time.perf_counter() - start) * 1000)
        return step

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,
    ) -> WorkflowResult:
        """Execute the full workflow sequentially.

        If a step is marked ``requiring_approval``, the workflow calls
        *approval_callback* (if provided).  When the callback returns
        ``False`` (or is ``None``), execution stops and the result
        indicates which step is awaiting approval.

        Args:
            task: Top-level task specification.
            approval_callback: ``async (step) -> bool`` that returns ``True``
                to proceed or ``False`` to pause.

        Returns:
            :class:`WorkflowResult` summarising execution.
        """
        plan = self.build_plan(task)
        accumulated_context: dict[str, Any] = {}
        total_ms = 0

        for step in plan:
            # -- Approval gate --
            if step.requiring_approval:
                step.status = "awaiting_approval"

                approved = False
                if approval_callback is not None:
                    approved = await approval_callback(step)

                if not approved:
                    return WorkflowResult(
                        success=False,
                        steps=plan,
                        stopped_at_approval=step.step_number,
                        total_execution_time_ms=total_ms,
                    )

            # -- Execute --
            step = await self.execute_step(step, accumulated_context)
            total_ms += step.execution_time_ms

            if step.status == "failed":
                return WorkflowResult(
                    success=False,
                    steps=plan,
                    total_execution_time_ms=total_ms,
                )

            # -- Chain results for next step --
            if step.output_data:
                accumulated_context = self.chain_results(accumulated_context, step)

        final_output = accumulated_context
        return WorkflowResult(
            success=True,
            steps=plan,
            final_output=final_output,
            total_execution_time_ms=total_ms,
        )

    # -- Result chaining -------------------------------------------------------

    def chain_results(
        self,
        prev_result: dict[str, Any],
        next_step: WorkflowStep,
    ) -> dict[str, Any]:
        """Merge the output of a completed step into the accumulated context.

        The default implementation namespaces each step's output under
        ``step_{N}_{skill_id}`` to avoid key collisions, and also provides
        a flat ``latest_output`` key for convenience.

        Subclasses may override this to implement custom chaining logic
        (e.g. extracting specific fields, transforming formats).

        Args:
            prev_result: Previously accumulated context dict.
            next_step: The just-completed step whose ``output_data`` should
                be folded in.

        Returns:
            Updated accumulated context dict.
        """
        merged = {**prev_result}

        if next_step.output_data:
            namespace = f"step_{next_step.step_number}_{next_step.skill_id}"
            merged[namespace] = next_step.output_data
            merged["latest_output"] = next_step.output_data

        return merged

    # -- Default skill loader --------------------------------------------------

    def _default_skill_loader(self, skill_id: str) -> BaseSkillDefinition:
        """Load a skill definition from the standard definitions directory.

        Args:
            skill_id: Skill directory name.

        Returns:
            Initialised :class:`BaseSkillDefinition`.
        """
        return BaseSkillDefinition(skill_id, self._llm)
