"""Deep Research workflow composition.

Conducts comprehensive research on a company or topic by scraping multiple
web sources, searching SEC filings and patents, synthesising findings with an
LLM, and producing a formatted research report.

Chain::

    web_intelligence.deep_scrape(multiple_urls)
    → web_intelligence.search_sec_filings()
    → web_intelligence.search_patents()
    → LLM synthesis
    → document_forge.generate("research_report")

Trigger: On-demand via chat.
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
# LLM prompt for research synthesis
# ---------------------------------------------------------------------------

_FALLBACK_SYNTHESIS_PROMPT = """\
You are ARIA's Research Analyst. Synthesise the following raw intelligence
into a structured research brief."""

_SYNTHESIS_TASK_INSTRUCTIONS = """\
Structure your output as valid JSON with these sections:
{
  "executive_summary": "2-3 sentence overview",
  "company_overview": "Key facts about the company",
  "financial_highlights": "Notable SEC filing findings",
  "innovation_pipeline": "Patent and R&D activity",
  "web_presence_analysis": "Key takeaways from web content",
  "competitive_implications": "What this means for our client",
  "recommended_actions": ["action 1", "action 2", "action 3"]
}
"""


class DeepResearchWorkflow(BaseWorkflow):
    """On-demand deep research pipeline.

    Unlike cron-triggered workflows, this is invoked directly from chat
    when a user requests research on a specific company or topic.

    Parameters:
        llm_client: Shared LLM client for synthesis and skill execution.
        skill_loader: Optional custom skill loader callable.
    """

    steps: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,  # noqa: ARG002
    ) -> WorkflowResult:
        """Execute the deep research pipeline.

        Args:
            task: Must contain ``company`` or ``topic``.  Optionally
                ``urls`` (list of URLs to scrape), ``user_id``.
            approval_callback: Reserved for future approval gates.

        Returns:
            :class:`WorkflowResult` with the synthesised research report.
        """
        company = task.get("company", task.get("topic", "unknown"))
        urls = task.get("urls", [])
        user_id = task.get("user_id", "")
        plan: list[WorkflowStep] = []
        accumulated: dict[str, Any] = {"company": company, "user_id": user_id}
        total_ms = 0

        # -- Step 1: Deep scrape multiple URLs ------------------------------
        step1 = WorkflowStep(
            step_number=1,
            skill_id="web_intelligence",
            config={
                "task_type": "deep_scrape",
                "urls": urls,
                "company": company,
            },
        )
        step1 = await self.execute_step(step1, accumulated)
        plan.append(step1)
        total_ms += step1.execution_time_ms

        if step1.status == "failed":
            logger.warning("Deep scrape failed, continuing with remaining sources")
            # Non-fatal: proceed with SEC and patent searches

        if step1.output_data:
            accumulated = self.chain_results(accumulated, step1)

        # -- Step 2: Search SEC filings -------------------------------------
        step2 = WorkflowStep(
            step_number=2,
            skill_id="web_intelligence",
            config={
                "task_type": "search_sec_filings",
                "company": company,
            },
        )
        step2 = await self.execute_step(step2, accumulated)
        plan.append(step2)
        total_ms += step2.execution_time_ms

        if step2.output_data:
            accumulated = self.chain_results(accumulated, step2)

        # -- Step 3: Search patents -----------------------------------------
        step3 = WorkflowStep(
            step_number=3,
            skill_id="web_intelligence",
            config={
                "task_type": "search_patents",
                "query": company,
            },
        )
        step3 = await self.execute_step(step3, accumulated)
        plan.append(step3)
        total_ms += step3.execution_time_ms

        if step3.output_data:
            accumulated = self.chain_results(accumulated, step3)

        # -- Step 4: LLM synthesis ------------------------------------------
        step4 = WorkflowStep(step_number=4, skill_id="llm_synthesis", config={})
        step4.status = "running"

        import json
        import time

        start = time.perf_counter()
        try:
            research_context = _build_synthesis_context(accumulated, company)

            # Primary: PersonaBuilder for system prompt
            synthesis_system_prompt = (
                _FALLBACK_SYNTHESIS_PROMPT + "\n\n" + _SYNTHESIS_TASK_INSTRUCTIONS
            )
            if user_id:
                try:
                    from src.core.persona import PersonaRequest, get_persona_builder

                    builder = get_persona_builder()
                    persona_ctx = await builder.build(PersonaRequest(
                        user_id=user_id,
                        agent_name="deep_research",
                        agent_role_description=(
                            "Research Analyst synthesising raw intelligence "
                            "into a structured research brief"
                        ),
                        task_description=f"Synthesise deep research findings for {company}",
                        output_format="json",
                    ))
                    synthesis_system_prompt = (
                        persona_ctx.to_system_prompt()
                        + "\n\n"
                        + _SYNTHESIS_TASK_INSTRUCTIONS
                    )
                except Exception as e:
                    logger.warning("PersonaBuilder unavailable, using fallback: %s", e)

            synthesis_text = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Research target: {company}\n\nRaw intelligence:\n{research_context}"
                        ),
                    }
                ],
                system_prompt=synthesis_system_prompt,
                max_tokens=4096,
                temperature=0.4,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="deep_research",
            )

            synthesis = json.loads(synthesis_text)
            step4.output_data = synthesis
            step4.status = "complete"
        except Exception as exc:
            step4.error = str(exc)
            step4.status = "failed"
            logger.error("Research synthesis failed", extra={"error": str(exc)})

        step4.execution_time_ms = int((time.perf_counter() - start) * 1000)
        plan.append(step4)
        total_ms += step4.execution_time_ms

        if step4.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step4.output_data:
            accumulated = self.chain_results(accumulated, step4)

        # -- Step 5: Generate research report document ----------------------
        step5 = WorkflowStep(
            step_number=5,
            skill_id="document_forge",
            config={
                "template": "research_report",
                "synthesis": accumulated.get("latest_output", {}),
                "company": company,
                "user_id": user_id,
            },
        )
        step5 = await self.execute_step(step5, accumulated)
        plan.append(step5)
        total_ms += step5.execution_time_ms

        if step5.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step5.output_data:
            accumulated = self.chain_results(accumulated, step5)

        return WorkflowResult(
            success=True,
            steps=plan,
            final_output=accumulated,
            total_execution_time_ms=total_ms,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_synthesis_context(accumulated: dict[str, Any], company: str) -> str:
    """Assemble all gathered intelligence into a structured prompt context."""
    import json

    sections: list[str] = []

    # Web scrape results
    web_data = accumulated.get("step_1_web_intelligence")
    if web_data:
        sections.append(f"## Web Content\n{json.dumps(web_data, indent=2, default=str)}")

    # SEC filings
    sec_data = accumulated.get("step_2_web_intelligence")
    if sec_data:
        sections.append(f"## SEC Filings\n{json.dumps(sec_data, indent=2, default=str)}")

    # Patents
    patent_data = accumulated.get("step_3_web_intelligence")
    if patent_data:
        sections.append(f"## Patents\n{json.dumps(patent_data, indent=2, default=str)}")

    if not sections:
        return f"No raw intelligence gathered for {company}. Provide a general overview."

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Declarative definition (for SkillRegistry / WorkflowEngine)
# ---------------------------------------------------------------------------


def get_deep_research_definition() -> UserWorkflowDefinition:
    """Return the declarative workflow definition for Deep Research.

    Registered as an on-demand (event-triggered) workflow so the
    orchestrator can invoke it when a user requests research via chat.
    """
    return UserWorkflowDefinition(
        name="Deep Research",
        description=(
            "Conducts comprehensive research on a company by scraping web "
            "sources, searching SEC filings and patents, synthesising "
            "findings with AI, and generating a formatted research report."
        ),
        trigger=WorkflowTrigger(
            type="event",
            event_type="research_requested",
        ),
        actions=[
            WorkflowAction(
                step_id="deep_scrape",
                action_type="run_skill",
                config={"skill_id": "web_intelligence", "task_type": "deep_scrape"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="sec_filings",
                action_type="run_skill",
                config={"skill_id": "web_intelligence", "task_type": "search_sec_filings"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="patents",
                action_type="run_skill",
                config={"skill_id": "web_intelligence", "task_type": "search_patents"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="synthesise",
                action_type="run_skill",
                config={"skill_id": "llm_synthesis"},
            ),
            WorkflowAction(
                step_id="generate_report",
                action_type="run_skill",
                config={"skill_id": "document_forge", "template": "research_report"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="microscope",
            color="#06B6D4",
            description=(
                "On-demand deep research: web scraping, SEC filings, "
                "patents, AI synthesis, and formatted report generation."
            ),
        ),
        is_shared=True,
    )
