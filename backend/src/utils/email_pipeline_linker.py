"""Email-to-pipeline entity linking service.

This module provides dynamic, data-driven pipeline context resolution for email contacts.
It checks multiple data sources to determine if a contact is associated with a lead,
account, or monitored company, providing context for the communications UI.

100% DYNAMIC - no hardcoded emails, names, or companies.
Everything derived from each user's live data at query time.
"""

import logging
from dataclasses import dataclass
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Structured pipeline context for an email contact."""

    company_name: str | None = None
    lead_name: str | None = None
    lead_id: str | None = None
    lifecycle_stage: str | None = None  # lead, opportunity, account
    health_score: int | None = None  # 0-100
    relationship_type: str | None = None  # partner, investor, customer, etc.
    source: str = "unknown"  # Which source provided the match


def _extract_domain(email: str) -> str:
    """Extract domain from email address.

    Args:
        email: Email address (e.g., "user@example.com")

    Returns:
        Domain (e.g., "example.com") or empty string if invalid
    """
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower().strip()


async def get_pipeline_context_for_email(
    db: Client,
    user_id: str,
    contact_email: str,
) -> dict[str, Any] | None:
    """Get pipeline context for an email contact.

    Resolves contact to pipeline entities by checking multiple data sources:
    1. lead_memory_stakeholders - match contact email to stakeholder
    2. monitored_entities - match email domain to entity domains
    3. memory_semantic - check for relationship mentions

    Args:
        db: Supabase client instance
        user_id: The user's UUID
        contact_email: The contact's email address

    Returns:
        Dict with pipeline context if found, None if completely unknown.
        Keys: company_name, lead_name, lead_id, lifecycle_stage, health_score,
              relationship_type, source
    """
    if not contact_email:
        return None

    contact_email_lower = contact_email.lower().strip()
    contact_domain = _extract_domain(contact_email_lower)

    # 1. Check lead_memory_stakeholders for direct email match
    try:
        stakeholder_result = (
            db.table("lead_memory_stakeholders")
            .select(
                "lead_memory_id, contact_name, role, sentiment, "
                "lead_memories(id, company_name, lifecycle_stage, status, health_score)"
            )
            .eq("contact_email", contact_email_lower)
            .eq("lead_memories.status", "active")
            .limit(1)
            .execute()
        )

        if stakeholder_result.data:
            stakeholder = stakeholder_result.data[0]
            lead_data = stakeholder.get("lead_memories")

            if lead_data and isinstance(lead_data, dict):
                return {
                    "company_name": lead_data.get("company_name"),
                    "lead_name": lead_data.get("company_name"),
                    "lead_id": lead_data.get("id"),
                    "lifecycle_stage": lead_data.get("lifecycle_stage"),
                    "health_score": lead_data.get("health_score"),
                    "relationship_type": _map_stakeholder_role(stakeholder.get("role")),
                    "contact_role": stakeholder.get("role"),
                    "source": "lead_memory_stakeholders",
                }

    except Exception as e:
        logger.warning(
            "PIPELINE_LINKER: lead_memory_stakeholders query failed for %s: %s",
            contact_email,
            e,
        )

    # 2. Check monitored_entities via domain match
    if contact_domain:
        try:
            entity_result = (
                db.table("monitored_entities")
                .select("entity_name, entity_type, monitoring_config")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .contains("domains", [contact_domain])
                .limit(1)
                .execute()
            )

            if entity_result.data:
                entity = entity_result.data[0]
                entity_name = entity.get("entity_name")
                entity_type = entity.get("entity_type", "company")

                # Try to find a lead_memory for this company
                lead_result = (
                    db.table("lead_memories")
                    .select("id, company_name, lifecycle_stage, health_score")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .ilike("company_name", entity_name)
                    .limit(1)
                    .execute()
                )

                lead_data = lead_result.data[0] if lead_result.data else None

                return {
                    "company_name": entity_name,
                    "lead_name": lead_data.get("company_name") if lead_data else entity_name,
                    "lead_id": lead_data.get("id") if lead_data else None,
                    "lifecycle_stage": lead_data.get("lifecycle_stage") if lead_data else None,
                    "health_score": lead_data.get("health_score") if lead_data else None,
                    "relationship_type": entity_type,
                    "source": "monitored_entities",
                }

        except Exception as e:
            logger.warning(
                "PIPELINE_LINKER: monitored_entities query failed for domain %s: %s",
                contact_domain,
                e,
            )

    # 3. Check memory_semantic for email references (fallback)
    try:
        memory_result = (
            db.table("memory_semantic")
            .select("fact, confidence")
            .eq("user_id", user_id)
            .ilike("fact", f"%{contact_email_lower}%")
            .limit(3)
            .execute()
        )

        if memory_result.data:
            # Extract any company names or relationship info from facts
            for row in memory_result.data:
                fact = row.get("fact", "")
                # This is a lightweight extraction - just indicate known contact
                if "investor" in fact.lower():
                    return {
                        "relationship_type": "investor",
                        "source": "memory_semantic",
                    }
                elif "partner" in fact.lower():
                    return {
                        "relationship_type": "partner",
                        "source": "memory_semantic",
                    }
                elif "customer" in fact.lower():
                    return {
                        "relationship_type": "customer",
                        "source": "memory_semantic",
                    }

    except Exception as e:
        logger.warning(
            "PIPELINE_LINKER: memory_semantic query failed for %s: %s",
            contact_email,
            e,
        )

    # No pipeline context found
    return None


def _map_stakeholder_role(role: str | None) -> str:
    """Map stakeholder role to a user-friendly relationship type.

    Args:
        role: The stakeholder role (decision_maker, influencer, champion, etc.)

    Returns:
        User-friendly relationship type string.
    """
    if not role:
        return "contact"

    role_mapping = {
        "decision_maker": "prospect",
        "influencer": "prospect",
        "champion": "prospect",
        "blocker": "prospect",
        "user": "prospect",
    }

    return role_mapping.get(role.lower(), "contact")


def format_pipeline_context_for_display(context: dict[str, Any] | None) -> str | None:
    """Format pipeline context for inline display in UI.

    Args:
        context: Pipeline context dict from get_pipeline_context_for_email

    Returns:
        Formatted string like "Silicon Valley Bank (Partner)" or None
    """
    if not context:
        return None

    company = context.get("company_name")
    rel_type = context.get("relationship_type")

    if not company:
        return None

    # Capitalize relationship type for display
    rel_display = rel_type.replace("_", " ").title() if rel_type else None

    if rel_display:
        return f"{company} ({rel_display})"

    return company
