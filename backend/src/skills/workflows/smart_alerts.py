"""Smart Alerts workflow composition.

Evaluates market signal implications, scores urgency via LLM, and dispatches
alerts through team messaging and in-app notifications.

Chain::

    signal_radar.detect_implications()
    → urgency_scoring (LLM)
    → team_messenger.send_alert() + notifications.create()

Trigger: Event-based — fires when signal_radar detects a high-relevance signal
(``signal_detected`` event with ``relevance_score >= 0.7``).
"""

from __future__ import annotations

import logging
from typing import Any

from src.skills.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt for urgency scoring
# ---------------------------------------------------------------------------

_FALLBACK_URGENCY_PROMPT = """\
You are ARIA's Urgency Scorer. Given a market signal and its implications,
assign an urgency level and recommended response window."""

_URGENCY_TASK_INSTRUCTIONS = """\
Urgency levels:
- CRITICAL: Requires immediate action (within 1 hour). Revenue at risk or
  competitive threat demanding same-day response.
- HIGH: Action needed today. Significant opportunity or risk that could
  affect active deals.
- MEDIUM: Action within 48 hours. Notable development worth monitoring
  and preparing for.
- LOW: Informational. File for reference, no immediate action needed.

Respond with valid JSON:
{
  "urgency": "CRITICAL|HIGH|MEDIUM|LOW",
  "response_window_hours": 1,
  "reasoning": "Brief explanation of urgency assessment",
  "recommended_action": "Specific next step for the rep",
  "affected_leads": ["lead names if identifiable"]
}
"""


class SmartAlertsWorkflow(BaseWorkflow):
    """Event-driven alert pipeline with LLM urgency scoring.

    Processes incoming high-relevance signals through implication detection,
    urgency scoring, and multi-channel alert dispatch.

    Parameters:
        llm_client: Shared LLM client for urgency scoring.
        skill_loader: Optional custom skill loader callable.
    """

    steps: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,
    ) -> WorkflowResult:
        """Execute the smart alerts pipeline.

        Args:
            task: Must contain ``signal`` (the detected signal dict) and
                ``user_id``.  Optionally ``knowledge_context`` for
                implication detection.
            approval_callback: Optional approval gate for critical alerts.

        Returns:
            :class:`WorkflowResult` with urgency assessment and
            notification delivery status.
        """
        user_id = task.get("user_id", "")
        signal = task.get("signal", {})
        knowledge_context = task.get("knowledge_context", {})
        plan: list[WorkflowStep] = []
        accumulated: dict[str, Any] = {"signal": signal, "user_id": user_id}
        total_ms = 0

        # -- Step 1: Detect implications ------------------------------------
        step1 = WorkflowStep(
            step_number=1,
            skill_id="signal_radar",
            config={
                "task_type": "detect_implications",
                "signal": signal,
                "knowledge_context": knowledge_context,
            },
        )
        step1 = await self.execute_step(step1, accumulated)
        plan.append(step1)
        total_ms += step1.execution_time_ms

        if step1.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step1.output_data:
            accumulated = self.chain_results(accumulated, step1)

        # -- Step 2: LLM urgency scoring ------------------------------------
        step2 = WorkflowStep(step_number=2, skill_id="urgency_scoring", config={})
        step2.status = "running"

        import json
        import time

        start = time.perf_counter()
        try:
            implications = accumulated.get("latest_output", {})
            signal_summary = json.dumps(signal, indent=2, default=str)
            implications_summary = json.dumps(implications, indent=2, default=str)

            # Primary: PersonaBuilder for system prompt
            urgency_system_prompt = (
                _FALLBACK_URGENCY_PROMPT + "\n\n" + _URGENCY_TASK_INSTRUCTIONS
            )
            if user_id:
                try:
                    from src.core.persona import PersonaRequest, get_persona_builder

                    builder = get_persona_builder()
                    persona_ctx = await builder.build(PersonaRequest(
                        user_id=user_id,
                        agent_name="smart_alerts",
                        agent_role_description=(
                            "Urgency Scorer assigning urgency levels and recommended "
                            "response windows to market signals and their implications"
                        ),
                        task_description="Score urgency of detected market signal",
                        output_format="json",
                    ))
                    urgency_system_prompt = (
                        persona_ctx.to_system_prompt()
                        + "\n\n"
                        + _URGENCY_TASK_INSTRUCTIONS
                    )
                except Exception as e:
                    logger.warning("PersonaBuilder unavailable, using fallback: %s", e)

            scoring_text = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Signal:\n{signal_summary}\n\nImplications:\n{implications_summary}"
                        ),
                    }
                ],
                system_prompt=urgency_system_prompt,
                max_tokens=1024,
                temperature=0.2,
            )

            urgency_result = json.loads(scoring_text)
            step2.output_data = urgency_result
            step2.status = "complete"
        except Exception as exc:
            step2.error = str(exc)
            step2.status = "failed"
            logger.error("Urgency scoring failed", extra={"error": str(exc)})

        step2.execution_time_ms = int((time.perf_counter() - start) * 1000)
        plan.append(step2)
        total_ms += step2.execution_time_ms

        if step2.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step2.output_data:
            accumulated = self.chain_results(accumulated, step2)

        urgency = step2.output_data.get("urgency", "MEDIUM") if step2.output_data else "MEDIUM"

        # -- Step 3: Send alert via team messenger --------------------------
        step3 = WorkflowStep(
            step_number=3,
            skill_id="team_messenger",
            config={
                "task_type": "send_alert",
                "user_id": user_id,
                "channel": "slack",
                "alert": {
                    "signal": signal,
                    "urgency": urgency,
                    "implications": accumulated.get("step_1_signal_radar", {}),
                    "scoring": accumulated.get("latest_output", {}),
                },
            },
        )

        # Critical alerts require approval before dispatch
        if urgency == "CRITICAL" and approval_callback is not None:
            step3.requiring_approval = True
            step3.status = "awaiting_approval"
            approved = await approval_callback(step3)
            if not approved:
                plan.append(step3)
                return WorkflowResult(
                    success=False,
                    steps=plan,
                    stopped_at_approval=3,
                    total_execution_time_ms=total_ms,
                )

        step3 = await self.execute_step(step3, accumulated)
        plan.append(step3)
        total_ms += step3.execution_time_ms

        # -- Step 4: Create in-app notification (parallel with messenger) ---
        step4 = WorkflowStep(
            step_number=4,
            skill_id="notifications",
            config={
                "user_id": user_id,
                "type": "signal_alert",
                "title": signal.get("headline", "Market Signal Alert"),
                "message": (f"[{urgency}] {signal.get('summary', 'New market signal detected')}"),
                "metadata": {
                    "urgency": urgency,
                    "signal_id": signal.get("id", ""),
                    "response_window_hours": step2.output_data.get("response_window_hours", 24)
                    if step2.output_data
                    else 24,
                },
            },
        )
        step4 = await self.execute_step(step4, accumulated)
        plan.append(step4)
        total_ms += step4.execution_time_ms

        # Notification failure is non-fatal
        if step4.output_data:
            accumulated = self.chain_results(accumulated, step4)

        success = step3.status == "complete"
        return WorkflowResult(
            success=success,
            steps=plan,
            final_output=accumulated,
            total_execution_time_ms=total_ms,
        )


# ---------------------------------------------------------------------------
# Declarative definition (for SkillRegistry / WorkflowEngine)
# ---------------------------------------------------------------------------


def get_smart_alerts_definition() -> UserWorkflowDefinition:
    """Return the declarative workflow definition for Smart Alerts.

    Fires on ``signal_detected`` events when the relevance score exceeds
    the threshold.
    """
    return UserWorkflowDefinition(
        name="Smart Alerts",
        description=(
            "Evaluates market signal implications, scores urgency with AI, "
            "and dispatches alerts via Slack and in-app notifications."
        ),
        trigger=WorkflowTrigger(
            type="event",
            event_type="signal_detected",
            event_filter={"min_relevance_score": 0.7},
        ),
        actions=[
            WorkflowAction(
                step_id="detect_implications",
                action_type="run_skill",
                config={"skill_id": "signal_radar", "task_type": "detect_implications"},
            ),
            WorkflowAction(
                step_id="score_urgency",
                action_type="run_skill",
                config={"skill_id": "urgency_scoring"},
            ),
            WorkflowAction(
                step_id="send_alert",
                action_type="send_notification",
                config={"channels": ["slack", "in-app"]},
            ),
        ],
        metadata=WorkflowMetadata(
            category="monitoring",
            icon="bell",
            color="#EF4444",
            description=(
                "AI-powered alert pipeline: implication detection, "
                "urgency scoring, and multi-channel notification dispatch."
            ),
        ),
        is_shared=True,
    )
