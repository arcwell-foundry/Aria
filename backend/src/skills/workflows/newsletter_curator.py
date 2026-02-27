"""Newsletter Curator workflow composition.

Curates a weekly intelligence newsletter by scanning market signals, selecting
the most relevant items via LLM, generating a polished newsletter document, and
distributing it to the user's prospect list.

Chain::

    signal_radar.scan_all_sources()
    → LLM curation (select top 5 signals)
    → document_forge.generate("newsletter")
    → email_intelligence.send_to_prospects()

Trigger: Weekly cron — Monday 7 AM (user timezone).
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.task_types import TaskType
from src.skills.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt for signal curation
# ---------------------------------------------------------------------------

_FALLBACK_CURATION_PROMPT = """\
You are ARIA's Newsletter Curator. Given a list of market signals, select the
top 5 most relevant and impactful for a life-sciences commercial team."""

_CURATION_TASK_INSTRUCTIONS = """\
For each selected signal, provide:
- A concise headline (max 12 words)
- A 2-sentence summary of why it matters
- An action suggestion for the sales rep

Respond with valid JSON: {"curated_signals": [{"headline": "...", "summary": "...", "action": "...", "original_signal_id": "..."}]}
"""


class NewsletterCuratorWorkflow(BaseWorkflow):
    """Weekly newsletter curation pipeline.

    Overrides the default step-based execution to implement custom logic
    for LLM curation between the scan and document generation phases.

    Parameters:
        llm_client: Shared LLM client for curation and skill execution.
        skill_loader: Optional custom skill loader callable.
    """

    # Not using class-level ``steps`` because the curation step is
    # inline LLM logic, not a registered skill.
    steps: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,
    ) -> WorkflowResult:
        """Execute the full newsletter curation pipeline.

        Args:
            task: Must contain ``user_id``.  Optionally ``max_signals``
                (default 5) and ``prospect_list_id``.
            approval_callback: Optional approval gate callback.

        Returns:
            :class:`WorkflowResult` with the generated newsletter and
            distribution status.
        """
        user_id = task.get("user_id", "")
        max_signals = task.get("max_signals", 5)
        plan: list[WorkflowStep] = []
        accumulated: dict[str, Any] = {}
        total_ms = 0

        # -- Step 1: Scan all signal sources --------------------------------
        step1 = WorkflowStep(
            step_number=1,
            skill_id="signal_radar",
            config={"task_type": "scan_all_sources", "user_id": user_id},
        )
        step1 = await self.execute_step(step1, accumulated)
        plan.append(step1)
        total_ms += step1.execution_time_ms

        if step1.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step1.output_data:
            accumulated = self.chain_results(accumulated, step1)

        # -- Step 2: LLM curation (select top N signals) --------------------
        step2 = WorkflowStep(step_number=2, skill_id="llm_curation", config={})
        step2.status = "running"

        import time

        start = time.perf_counter()
        try:
            signals_raw = accumulated.get("latest_output", {})
            signals_json = _format_signals_for_prompt(signals_raw)

            # Primary: PersonaBuilder for system prompt
            curation_system_prompt = (
                _FALLBACK_CURATION_PROMPT + "\n\n" + _CURATION_TASK_INSTRUCTIONS
            )
            if user_id:
                try:
                    from src.core.persona import PersonaRequest, get_persona_builder

                    builder = get_persona_builder()
                    persona_ctx = await builder.build(PersonaRequest(
                        user_id=user_id,
                        agent_name="newsletter_curator",
                        agent_role_description=(
                            "Newsletter Curator selecting the most relevant and "
                            "impactful market signals for a life-sciences commercial team"
                        ),
                        task_description="Curate top market signals for weekly newsletter",
                        output_format="json",
                    ))
                    curation_system_prompt = (
                        persona_ctx.to_system_prompt()
                        + "\n\n"
                        + _CURATION_TASK_INSTRUCTIONS
                    )
                except Exception as e:
                    logger.warning("PersonaBuilder unavailable, using fallback: %s", e)

            curated_text = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Here are the latest market signals:\n\n{signals_json}\n\n"
                            f"Select the top {max_signals} most relevant signals."
                        ),
                    }
                ],
                system_prompt=curation_system_prompt,
                max_tokens=2048,
                temperature=0.3,
                task=TaskType.SCOUT_SUMMARIZE,
                agent_id="newsletter_curator",
            )

            import json

            curated = json.loads(curated_text)
            step2.output_data = curated
            step2.status = "complete"
        except Exception as exc:
            step2.error = str(exc)
            step2.status = "failed"
            logger.error("Newsletter curation failed", extra={"error": str(exc)})

        step2.execution_time_ms = int((time.perf_counter() - start) * 1000)
        plan.append(step2)
        total_ms += step2.execution_time_ms

        if step2.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step2.output_data:
            accumulated = self.chain_results(accumulated, step2)

        # -- Step 3: Generate newsletter document ---------------------------
        step3 = WorkflowStep(
            step_number=3,
            skill_id="document_forge",
            config={
                "template": "newsletter",
                "curated_signals": accumulated.get("latest_output", {}),
                "user_id": user_id,
            },
        )
        step3 = await self.execute_step(step3, accumulated)
        plan.append(step3)
        total_ms += step3.execution_time_ms

        if step3.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step3.output_data:
            accumulated = self.chain_results(accumulated, step3)

        # -- Step 4: Distribute to prospects --------------------------------
        step4 = WorkflowStep(
            step_number=4,
            skill_id="email_intelligence",
            config={
                "task_type": "send_email",
                "user_id": user_id,
                "newsletter_content": accumulated.get("latest_output", {}),
                "prospect_list_id": task.get("prospect_list_id", ""),
            },
        )

        if approval_callback is not None:
            step4.requiring_approval = True
            step4.status = "awaiting_approval"
            approved = await approval_callback(step4)
            if not approved:
                plan.append(step4)
                return WorkflowResult(
                    success=False,
                    steps=plan,
                    stopped_at_approval=4,
                    total_execution_time_ms=total_ms,
                )

        step4 = await self.execute_step(step4, accumulated)
        plan.append(step4)
        total_ms += step4.execution_time_ms

        if step4.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step4.output_data:
            accumulated = self.chain_results(accumulated, step4)

        return WorkflowResult(
            success=True,
            steps=plan,
            final_output=accumulated,
            total_execution_time_ms=total_ms,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_signals_for_prompt(signals_data: dict[str, Any]) -> str:
    """Format signal scan output into a readable string for the LLM."""
    import json

    if isinstance(signals_data, dict) and "signals" in signals_data:
        return json.dumps(signals_data["signals"], indent=2, default=str)
    return json.dumps(signals_data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Declarative definition (for SkillRegistry / WorkflowEngine)
# ---------------------------------------------------------------------------


def get_newsletter_curator_definition() -> UserWorkflowDefinition:
    """Return the declarative workflow definition for Newsletter Curator.

    This allows the workflow to be discovered by the SkillRegistry and
    invoked by the WorkflowEngine alongside user-created workflows.
    """
    return UserWorkflowDefinition(
        name="Newsletter Curator",
        description=(
            "Curates a weekly intelligence newsletter from market signals, "
            "selects the top insights via AI, generates a polished newsletter, "
            "and distributes it to your prospect list."
        ),
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 7 * * 1",  # Monday 7 AM
        ),
        actions=[
            WorkflowAction(
                step_id="scan_signals",
                action_type="run_skill",
                config={"skill_id": "signal_radar", "task_type": "scan_all_sources"},
            ),
            WorkflowAction(
                step_id="curate",
                action_type="run_skill",
                config={"skill_id": "llm_curation", "max_signals": 5},
            ),
            WorkflowAction(
                step_id="generate_newsletter",
                action_type="run_skill",
                config={"skill_id": "document_forge", "template": "newsletter"},
            ),
            WorkflowAction(
                step_id="distribute",
                action_type="run_skill",
                config={"skill_id": "email_intelligence", "task_type": "send_email"},
                requires_approval=True,
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="newspaper",
            color="#8B5CF6",
            description=(
                "Weekly AI-curated newsletter from market signals, "
                "delivered to your prospect list every Monday at 7 AM."
            ),
        ),
        is_shared=True,
    )
