"""Domain Intelligence workflow composition.

Monitors competitor websites for changes, detects meaningful differences, and
creates alerts when significant changes are found.

Chain::

    web_intelligence.monitor_competitor()
    → diff detection
    → signal_radar.create_alerts()

Trigger: Daily cron — runs at midnight to check competitor sites for changes.
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
# LLM prompt for change significance assessment
# ---------------------------------------------------------------------------

_DIFF_ANALYSIS_PROMPT = """\
You are ARIA's Competitive Intelligence Analyst. Given a list of detected
changes on a competitor's website, assess the business significance of each
change.

For each change, determine:
- Whether it's significant (ignore minor CSS/layout changes)
- The type: product_launch, pricing_change, leadership_change,
  partnership_announcement, regulatory_update, hiring_signal, or other
- A brief impact assessment

Respond with valid JSON:
{
  "significant_changes": [
    {
      "page_url": "...",
      "change_type": "product_launch",
      "summary": "Brief description of what changed",
      "impact_assessment": "What this means competitively",
      "relevance_score": 0.85
    }
  ],
  "total_changes_reviewed": 5,
  "significant_count": 2
}
"""


class DomainIntelligenceWorkflow(BaseWorkflow):
    """Daily competitor website monitoring pipeline.

    Checks configured competitor domains for changes, filters noise through
    LLM-based diff analysis, and creates signal alerts for significant
    competitive developments.

    Parameters:
        llm_client: Shared LLM client for diff significance analysis.
        skill_loader: Optional custom skill loader callable.
    """

    steps: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,  # noqa: ARG002
    ) -> WorkflowResult:
        """Execute the domain intelligence pipeline.

        Args:
            task: Must contain ``competitors`` (list of domain strings) and
                ``user_id``.
            approval_callback: Reserved for future approval gates.

        Returns:
            :class:`WorkflowResult` with detected changes and created alerts.
        """
        user_id = task.get("user_id", "")
        competitors = task.get("competitors", [])
        plan: list[WorkflowStep] = []
        accumulated: dict[str, Any] = {"user_id": user_id}
        total_ms = 0
        all_changes: list[dict[str, Any]] = []

        if not competitors:
            logger.warning("Domain intelligence workflow called with no competitors")
            return WorkflowResult(
                success=True,
                steps=[],
                final_output={"message": "No competitors configured"},
                total_execution_time_ms=0,
            )

        # -- Step 1: Monitor each competitor domain -------------------------
        for domain in competitors:
            step = WorkflowStep(
                step_number=len(plan) + 1,
                skill_id="web_intelligence",
                config={
                    "task_type": "monitor_competitor",
                    "domain": domain,
                },
            )
            step = await self.execute_step(step, accumulated)
            plan.append(step)
            total_ms += step.execution_time_ms

            if step.status == "complete" and step.output_data:
                changes = step.output_data.get("changes", [])
                for change in changes:
                    change["domain"] = domain
                all_changes.extend(changes)
                accumulated = self.chain_results(accumulated, step)

        if not all_changes:
            logger.info("No competitor changes detected across %d domains", len(competitors))
            return WorkflowResult(
                success=True,
                steps=plan,
                final_output={"changes_detected": 0, "alerts_created": 0},
                total_execution_time_ms=total_ms,
            )

        # -- Step 2: LLM diff significance analysis -------------------------
        step_diff = WorkflowStep(
            step_number=len(plan) + 1,
            skill_id="diff_analysis",
            config={},
        )
        step_diff.status = "running"

        import json
        import time

        start = time.perf_counter()
        try:
            changes_json = json.dumps(all_changes, indent=2, default=str)

            analysis_text = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": (f"Competitor website changes detected:\n\n{changes_json}"),
                    }
                ],
                system_prompt=_DIFF_ANALYSIS_PROMPT,
                max_tokens=2048,
                temperature=0.3,
                task=TaskType.SCOUT_SUMMARIZE,
                agent_id="domain_intelligence",
            )

            analysis = json.loads(analysis_text)
            step_diff.output_data = analysis
            step_diff.status = "complete"
        except Exception as exc:
            step_diff.error = str(exc)
            step_diff.status = "failed"
            logger.error("Diff analysis failed", extra={"error": str(exc)})

        step_diff.execution_time_ms = int((time.perf_counter() - start) * 1000)
        plan.append(step_diff)
        total_ms += step_diff.execution_time_ms

        if step_diff.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step_diff.output_data:
            accumulated = self.chain_results(accumulated, step_diff)

        # -- Step 3: Create alerts for significant changes ------------------
        significant = (
            step_diff.output_data.get("significant_changes", []) if step_diff.output_data else []
        )

        if not significant:
            return WorkflowResult(
                success=True,
                steps=plan,
                final_output={
                    "changes_detected": len(all_changes),
                    "significant_changes": 0,
                    "alerts_created": 0,
                },
                total_execution_time_ms=total_ms,
            )

        # Build signals from significant changes for alert creation
        signals = [
            {
                "company_name": change.get("domain", ""),
                "signal_type": "competitor_" + change.get("change_type", "website_change"),
                "headline": change.get("summary", "Competitor website change detected"),
                "summary": change.get("impact_assessment", ""),
                "source_url": change.get("page_url", ""),
                "relevance_score": change.get("relevance_score", 0.7),
            }
            for change in significant
        ]

        step_alert = WorkflowStep(
            step_number=len(plan) + 1,
            skill_id="signal_radar",
            config={
                "task_type": "create_alerts",
                "signals": signals,
                "user_id": user_id,
            },
        )
        step_alert = await self.execute_step(step_alert, accumulated)
        plan.append(step_alert)
        total_ms += step_alert.execution_time_ms

        if step_alert.output_data:
            accumulated = self.chain_results(accumulated, step_alert)

        accumulated["changes_detected"] = len(all_changes)
        accumulated["significant_changes"] = len(significant)
        accumulated["alerts_created"] = len(signals)

        return WorkflowResult(
            success=True,
            steps=plan,
            final_output=accumulated,
            total_execution_time_ms=total_ms,
        )


# ---------------------------------------------------------------------------
# Declarative definition (for SkillRegistry / WorkflowEngine)
# ---------------------------------------------------------------------------


def get_domain_intelligence_definition() -> UserWorkflowDefinition:
    """Return the declarative workflow definition for Domain Intelligence.

    Runs daily at midnight to check competitor websites for changes.
    """
    return UserWorkflowDefinition(
        name="Domain Intelligence",
        description=(
            "Monitors competitor websites daily for changes, filters noise "
            "with AI-powered diff analysis, and creates alerts for "
            "significant competitive developments."
        ),
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 0 * * *",  # Midnight daily
        ),
        actions=[
            WorkflowAction(
                step_id="monitor_competitors",
                action_type="run_skill",
                config={"skill_id": "web_intelligence", "task_type": "monitor_competitor"},
            ),
            WorkflowAction(
                step_id="analyse_diffs",
                action_type="run_skill",
                config={"skill_id": "diff_analysis"},
            ),
            WorkflowAction(
                step_id="create_alerts",
                action_type="run_skill",
                config={"skill_id": "signal_radar", "task_type": "create_alerts"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="monitoring",
            icon="globe",
            color="#10B981",
            description=(
                "Daily competitor website monitoring with AI diff analysis "
                "and automatic alert creation for significant changes."
            ),
        ),
        is_shared=True,
    )
