"""Pre-Meeting Pipeline workflow composition.

Prepares intelligence briefings for upcoming meetings by enriching attendee
profiles, researching their companies, and generating concise one-pager
documents.

Chain::

    calendar_intelligence.get_upcoming(24h)
    → for each meeting:
        contact_enricher.enrich_attendees()
        + web_intelligence.search_company()
        → document_forge.generate("meeting_one_pager")

Trigger: Daily cron (6 AM) + extensible via "and then..." in chat.
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


class PreMeetingPipelineWorkflow(BaseWorkflow):
    """Daily pre-meeting intelligence preparation pipeline.

    Fetches upcoming meetings within a configurable lookahead window,
    enriches attendee information, researches their companies, and
    generates a meeting one-pager for each.

    The workflow supports extension via chat — additional steps can be
    appended at runtime by passing ``extra_steps`` in the task dict.

    Parameters:
        llm_client: Shared LLM client for skill execution.
        skill_loader: Optional custom skill loader callable.
    """

    steps: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self,
        task: dict[str, Any],
        *,
        approval_callback: Any | None = None,
    ) -> WorkflowResult:
        """Execute the pre-meeting pipeline.

        Args:
            task: Must contain ``user_id``.  Optionally ``lookahead_hours``
                (default 24), ``extra_steps`` (list of additional
                ``(skill_id, config)`` tuples appended after document
                generation), and ``meeting_ids`` to target specific meetings.
            approval_callback: Optional approval gate callback.

        Returns:
            :class:`WorkflowResult` with generated one-pagers and
            enrichment data for each upcoming meeting.
        """
        user_id = task.get("user_id", "")
        lookahead_hours = task.get("lookahead_hours", 24)
        extra_steps = task.get("extra_steps", [])
        target_meeting_ids = task.get("meeting_ids")
        plan: list[WorkflowStep] = []
        accumulated: dict[str, Any] = {"user_id": user_id}
        total_ms = 0

        # -- Step 1: Get upcoming meetings ----------------------------------
        step1 = WorkflowStep(
            step_number=1,
            skill_id="calendar_intelligence",
            config={
                "task_type": "get_upcoming",
                "user_id": user_id,
                "hours": lookahead_hours,
            },
        )
        step1 = await self.execute_step(step1, accumulated)
        plan.append(step1)
        total_ms += step1.execution_time_ms

        if step1.status == "failed":
            return WorkflowResult(success=False, steps=plan, total_execution_time_ms=total_ms)

        if step1.output_data:
            accumulated = self.chain_results(accumulated, step1)

        meetings = _extract_meetings(step1.output_data or {})

        # Filter to specific meetings if requested
        if target_meeting_ids is not None:
            meetings = [m for m in meetings if m.get("id") in target_meeting_ids]

        if not meetings:
            logger.info("No upcoming meetings in the next %d hours", lookahead_hours)
            return WorkflowResult(
                success=True,
                steps=plan,
                final_output={"meetings_processed": 0, "one_pagers_generated": 0},
                total_execution_time_ms=total_ms,
            )

        # -- Steps 2-N: Process each meeting --------------------------------
        meeting_results: list[dict[str, Any]] = []
        step_number = 2

        for meeting in meetings:
            meeting_title = meeting.get("title", "Untitled Meeting")
            attendees = meeting.get("attendees", [])
            companies = _extract_companies_from_attendees(attendees)

            logger.info(
                "Processing meeting: %s (%d attendees)",
                meeting_title,
                len(attendees),
            )

            meeting_context: dict[str, Any] = {
                "meeting": meeting,
                "user_id": user_id,
            }

            # -- Enrich attendees -------------------------------------------
            if attendees:
                step_enrich = WorkflowStep(
                    step_number=step_number,
                    skill_id="contact_enricher",
                    config={
                        "task_type": "enrich_contact",
                        "contacts": [
                            {
                                "name": a.get("name", a.get("email", "")),
                                "company": a.get("company", ""),
                                "email": a.get("email", ""),
                            }
                            for a in attendees
                            if a.get("email")
                        ],
                    },
                )
                step_enrich = await self.execute_step(
                    step_enrich, {**accumulated, **meeting_context}
                )
                plan.append(step_enrich)
                total_ms += step_enrich.execution_time_ms
                step_number += 1

                if step_enrich.output_data:
                    meeting_context["enriched_attendees"] = step_enrich.output_data

            # -- Research companies -----------------------------------------
            for company in companies:
                step_company = WorkflowStep(
                    step_number=step_number,
                    skill_id="web_intelligence",
                    config={
                        "task_type": "deep_scrape",
                        "company": company,
                        "urls": [],  # Let the capability discover URLs
                    },
                )
                step_company = await self.execute_step(
                    step_company, {**accumulated, **meeting_context}
                )
                plan.append(step_company)
                total_ms += step_company.execution_time_ms
                step_number += 1

                if step_company.output_data:
                    meeting_context.setdefault("company_research", {})[company] = (
                        step_company.output_data
                    )

            # -- Generate meeting one-pager ---------------------------------
            step_doc = WorkflowStep(
                step_number=step_number,
                skill_id="document_forge",
                config={
                    "template": "meeting_one_pager",
                    "meeting": meeting,
                    "enriched_attendees": meeting_context.get("enriched_attendees", {}),
                    "company_research": meeting_context.get("company_research", {}),
                    "user_id": user_id,
                },
            )
            step_doc = await self.execute_step(step_doc, {**accumulated, **meeting_context})
            plan.append(step_doc)
            total_ms += step_doc.execution_time_ms
            step_number += 1

            meeting_result = {
                "meeting_title": meeting_title,
                "meeting_id": meeting.get("id", ""),
                "attendees_enriched": len(attendees),
                "companies_researched": len(companies),
                "one_pager_generated": step_doc.status == "complete",
                "one_pager": step_doc.output_data,
            }
            meeting_results.append(meeting_result)

        # -- Extra steps ("and then..." extension) --------------------------
        for skill_id, config in extra_steps:
            step_extra = WorkflowStep(
                step_number=step_number,
                skill_id=skill_id,
                config={**config, "meeting_results": meeting_results},
            )

            if config.get("requiring_approval") and approval_callback is not None:
                step_extra.requiring_approval = True
                step_extra.status = "awaiting_approval"
                approved = await approval_callback(step_extra)
                if not approved:
                    plan.append(step_extra)
                    return WorkflowResult(
                        success=False,
                        steps=plan,
                        stopped_at_approval=step_number,
                        total_execution_time_ms=total_ms,
                    )

            step_extra = await self.execute_step(step_extra, accumulated)
            plan.append(step_extra)
            total_ms += step_extra.execution_time_ms
            step_number += 1

            if step_extra.output_data:
                accumulated = self.chain_results(accumulated, step_extra)

        accumulated["meetings_processed"] = len(meetings)
        accumulated["one_pagers_generated"] = sum(
            1 for r in meeting_results if r["one_pager_generated"]
        )
        accumulated["meeting_results"] = meeting_results

        return WorkflowResult(
            success=True,
            steps=plan,
            final_output=accumulated,
            total_execution_time_ms=total_ms,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_meetings(calendar_output: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract meeting list from calendar intelligence output."""
    if isinstance(calendar_output, dict):
        if "events" in calendar_output:
            return calendar_output["events"]
        if "meetings" in calendar_output:
            return calendar_output["meetings"]
    if isinstance(calendar_output, list):
        return calendar_output
    return []


def _extract_companies_from_attendees(attendees: list[dict[str, Any]]) -> list[str]:
    """Derive unique company names from attendee email domains and metadata."""
    companies: set[str] = set()
    for attendee in attendees:
        company = attendee.get("company", "")
        if company:
            companies.add(company)
            continue
        # Fall back to email domain heuristic
        email = attendee.get("email", "")
        if "@" in email:
            domain = email.split("@")[1]
            # Skip common personal email domains
            if domain not in {
                "gmail.com",
                "yahoo.com",
                "hotmail.com",
                "outlook.com",
                "icloud.com",
                "aol.com",
            }:
                companies.add(domain.split(".")[0].capitalize())
    return sorted(companies)


# ---------------------------------------------------------------------------
# Declarative definition (for SkillRegistry / WorkflowEngine)
# ---------------------------------------------------------------------------


def get_pre_meeting_pipeline_definition() -> UserWorkflowDefinition:
    """Return the declarative workflow definition for Pre-Meeting Pipeline.

    Runs daily at 6 AM to prepare intelligence for the day's meetings.
    Can also be triggered on-demand via ``meeting_prep_requested`` event.
    """
    return UserWorkflowDefinition(
        name="Pre-Meeting Pipeline",
        description=(
            "Prepares intelligence briefings for upcoming meetings: "
            "enriches attendee profiles, researches their companies, "
            "and generates concise one-pager documents."
        ),
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 6 * * *",  # 6 AM daily
        ),
        actions=[
            WorkflowAction(
                step_id="get_meetings",
                action_type="run_skill",
                config={
                    "skill_id": "calendar_intelligence",
                    "task_type": "get_upcoming",
                    "hours": 24,
                },
            ),
            WorkflowAction(
                step_id="enrich_attendees",
                action_type="run_skill",
                config={"skill_id": "contact_enricher", "task_type": "enrich_contact"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="research_companies",
                action_type="run_skill",
                config={"skill_id": "web_intelligence", "task_type": "deep_scrape"},
                on_failure="skip",
            ),
            WorkflowAction(
                step_id="generate_one_pagers",
                action_type="run_skill",
                config={"skill_id": "document_forge", "template": "meeting_one_pager"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="briefcase",
            color="#F59E0B",
            description=(
                "Daily pre-meeting intelligence: attendee enrichment, "
                "company research, and one-pager generation at 6 AM."
            ),
        ),
        is_shared=True,
    )
