"""Background job for Hunter agent lead generation.

Runs every 30 minutes, finds active lead generation goals
and processes them.

Saves outbound email drafts to user's email client draft folder.

This job queries for all users with active email integrations,
runs the Hunter agent for each goal, creates discovered leads,
generates outbound email drafts, and saves drafts to the user's email client
(Gmail or Outlook) draft folders.

Updates goal progress incrementally after each lead batch.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.agents.hunter import HunterAgent
from src.agents.scribe import ScribeAgent
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.integrations.domain import IntegrationType
from src.integrations.service import IntegrationService
from src.services.email_client_writer import EmailClientWriter
from src.core.lead_generation import LeadGenerationService
from src.models.lead_generation import ICPDefinition

logger = logging.getLogger(__name__)


async def run_hunter_lead_generation_job() -> dict[str, Any]:
    """Run the Hunter agent lead generation job.

    This job queries for all active lead generation goals across all users,
    runs the Hunter agent for each goal, creates discovered leads,
    generates outbound email drafts, and saves drafts to the user's email client
    (Gmail or Outlook) draft folders.

    Updates goal progress incrementally after each lead batch.

    Returns:
        dict with summary stats.
    """
    logger.info("Hunter lead generation job starting")

    db = SupabaseClient.get_client()

    # Query lead generation goals: active or plan_ready
    goals_result = (
        db.table("goals")
        .select("id, user_id, title, description, progress, config, goal_type, status")
        .in_("status", ["active", "plan_ready"])
        .execute()
    )

    goals = _filter_lead_gen_goals(goals_result)

    if not goals:
        logger.info("No active/plan_ready lead generation goals found")
        return {
            "users_checked": 0,
            "goals_processed": 0,
            "leads_found": 0,
            "errors": 0,
        }

    logger.info("Found %d lead generation goals (active + plan_ready)", len(goals))

    goals_processed = 0
    leads_found = 0
    errors = 0

    for goal in goals:
        goal_id = goal["id"]
        user_id = goal["user_id"]

        try:
            # Activate plan_ready goals before processing
            if goal.get("status") == "plan_ready":
                db.table("goals").update({
                    "status": "active",
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", goal_id).execute()
                logger.info(
                    "Activated plan_ready goal %s for user %s",
                    goal_id,
                    user_id,
                )

            # Check if user has active email integrations
            integration_service = IntegrationService()
            gmail = await integration_service.get_integration(
                user_id=user_id,
                integration_type=IntegrationType.GMAIL,
            )
            outlook = await integration_service.get_integration(
                user_id=user_id,
                integration_type=IntegrationType.OUTLOOK,
            )

            has_email_integration = (
                (gmail and gmail.get("status") == "active")
                or (outlook and outlook.get("status") == "active")
            )

            if not has_email_integration:
                logger.debug(
                    "User %s has no active email integrations, skipping goal %s",
                    user_id,
                    goal_id,
                )
                continue

            # Get target count from goal metadata
            metadata = goal.get("config", {}) or {}
            target_count = metadata.get("target_count", 3)

            logger.info(
                "Processing goal %s: %s (user: %s)",
                goal_id,
                goal.get("title"),
                user_id,
            )

            # Get user's ICP via lead generation service
            lead_gen_service = LeadGenerationService()
            icp = await lead_gen_service.get_icp(user_id=user_id)

            if not icp:
                logger.warning("No ICP found for user %s, skipping", user_id)
                continue

            # Build hunter task from ICP
            icp_data = icp.icp_data
            hunter_task = {
                "icp": {
                    "industry": icp_data.industry[0] if icp_data.industry else "Biotechnology",
                    "size": _build_size_str(icp_data.company_size),
                    "geography": icp_data.geographies[0] if icp_data.geographies else "",
                },
                "target_count": target_count,
                "exclusions": icp_data.exclusions,
            }

            # Execute Hunter agent
            llm_client = LLMClient()
            hunter = HunterAgent(llm_client=llm_client, user_id=user_id)
            result = await hunter.execute(hunter_task)

            if not result.success or not result.data:
                logger.warning(
                    "Hunter returned no leads for goal %s",
                    goal_id,
                )
                continue

            # Get current lead count for this goal's ICP
            current_count_result = (
                db.table("discovered_leads")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("icp_id", icp.id)
                .execute()
            )
            current_lead_count = (
                current_count_result.count if hasattr(current_count_result, "count")
                else len(current_count_result.data or [])
            )

            # Process each discovered lead
            for lead_data in result.data:
                company = lead_data.get("company", {})
                contacts = lead_data.get("contacts", [])
                fit_score = lead_data.get("fit_score", 0)
                fit_reasons = lead_data.get("fit_reasons", [])
                gaps = lead_data.get("gaps", [])
                source = lead_data.get("source", "hunter_pro")

                # Create discovered lead record
                lead_id = str(uuid4())
                now = datetime.now(UTC)
                company_name = company.get("name", "Unknown")

                db.table("discovered_leads").insert({
                    "id": lead_id,
                    "user_id": user_id,
                    "icp_id": icp.id,
                    "company_name": company_name,
                    "company_data": company,
                    "contacts": contacts,
                    "fit_score": int(fit_score),
                    "score_breakdown": {},
                    "signals": [],
                    "review_status": "pending",
                    "source": source,
                    "lead_memory_id": None,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }).execute()

                logger.info(
                    "Created discovered lead: %s (%s) - fit: %d",
                    lead_id,
                    company_name,
                    int(fit_score),
                )

                # Generate outbound email draft using Scribe agent
                if contacts:
                    try:
                        scribe = ScribeAgent(llm_client=llm_client, user_id=user_id)
                        draft_result = await scribe.execute(
                            task={
                                "communication_type": "email",
                                "recipient": {
                                    "email": contacts[0].get("email", "contact@example.com"),
                                    "name": contacts[0].get("name", company_name),
                                },
                                "context": f"Outreach to {company_name} - ICP fit score: {fit_score:.0f}/100",
                                "goal": f"Initial outreach to {company_name}",
                                "tone": "friendly",
                                "is_proactive": True,
                                "related_goal_id": goal_id,
                            }
                        )

                        if draft_result.success and draft_result.data:
                            draft_id = draft_result.data.get("id")

                            # Save draft to email client (Outlook or Gmail)
                            try:
                                writer = EmailClientWriter()
                                await writer.save_draft_to_client(
                                    user_id=user_id,
                                    draft_id=draft_id,
                                )
                                logger.info(
                                    "Saved outbound draft for %s (draft_id: %s) to client",
                                    company_name,
                                    draft_id,
                                )
                            except Exception as e:
                                logger.warning(
                                    "Failed to save draft to email client for %s: %s",
                                    company_name,
                                    e,
                                )
                    except Exception as e:
                        logger.warning(
                            "Failed to generate draft for %s: %s",
                            company_name,
                            e,
                        )

                # Update goal progress incrementally
                progress_delta = int((1 / target_count) * 100)
                current_progress = goal.get("progress", 0) or 0
                new_progress = min(100, current_progress + progress_delta)

                db.table("goals").update({
                    "progress": new_progress,
                    "updated_at": now.isoformat(),
                }).eq("id", goal_id).execute()

                logger.debug(
                    "Updated goal %s progress: %d -> %d%%",
                    goal_id,
                    current_progress,
                    new_progress,
                )

                leads_found += 1

            goals_processed += 1
            logger.info(
                "Discovered %d leads for goal %s",
                len(result.data),
                goal_id,
            )

        except Exception as e:
            logger.warning(
                "Hunter execution failed for goal %s: %s",
                goal_id,
                e,
                exc_info=True,
            )
            errors += 1

    result = {
        "users_checked": len(goals),
        "goals_processed": goals_processed,
        "leads_found": leads_found,
        "errors": errors,
    }

    logger.info(
        "Hunter lead generation job complete: users=%d, goals=%d, leads=%d, errors=%d",
        len(goals),
        goals_processed,
        leads_found,
        errors,
    )

    return result


def _filter_lead_gen_goals(query_result: Any) -> list[dict[str, Any]]:
    """Filter query result to only lead generation goals.

    Args:
        query_result: Raw query result from Supabase.

    Returns:
        List of goal dicts that are lead generation goals.
    """
    goals: list[dict[str, Any]] = []

    rows = query_result.data or []
    if not rows:
        return []

    for row in rows:
        # Check if it's a lead generation goal
        title = row.get("title", "").lower()
        description = row.get("description", "") or ""
        metadata = row.get("config", {}) or {}
        goal_type = row.get("goal_type", "") or ""

        is_lead_gen = (
            "lead" in title
            or "find" in title
            or "prospect" in title
            or "outreach" in title
            or goal_type in ("lead_gen", "prospecting", "outreach")
            or metadata.get("goal_type") in ("lead_gen", "prospecting", "outreach")
        )

        if is_lead_gen:
            goals.append(row)

    return goals


def _build_size_str(size: dict[str, Any] | str) -> str:
    """Build size string from ICP size dict.

    Args:
        size: ICP size dict with min/max employees.

    Returns:
        Size string like "51-200" or "Enterprise (500+)".
    """
    if not size:
        return ""

    min_emp = size.get("min")
    max_emp = size.get("max")

    if min_emp and max_emp:
        return f"{min_emp}-{max_emp}"
    elif max_emp:
        if max_emp >= 500:
            return "Enterprise (500+)"
        elif max_emp >= 100:
            return "Mid-market (100-500)"
        else:
            return "Startup (1-50)"
    return ""
