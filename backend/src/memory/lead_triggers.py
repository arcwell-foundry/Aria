"""Lead memory creation triggers service.

Detects and creates Lead Memories from various trigger sources:
- Email approval: User approves outbound email to prospect
- Manual tracking: User clicks "track this company"
- CRM import: Bulk import from Salesforce/HubSpot
- Inbound response: Reply from prospect

Handles deduplication and retroactive history scanning.
"""

import logging
from typing import Any

from src.memory.lead_memory import LeadMemory, LeadMemoryService, TriggerType

logger = logging.getLogger(__name__)


class LeadTriggerService:
    """Service for creating Lead Memories from various trigger sources.

    Automatically detects when a lead should be tracked, prevents duplicates,
    and retroactively populates history for late-detected leads.
    """

    def __init__(
        self,
        lead_memory_service: LeadMemoryService,
        event_service: Any,  # LeadEventService
        conversation_service: Any,  # ConversationService
    ) -> None:
        """Initialize the trigger service with dependencies.

        Args:
            lead_memory_service: Service for creating/updating leads.
            event_service: Service for querying lead events.
            conversation_service: Service for querying conversation history.
        """
        self.lead_memory_service = lead_memory_service
        self.event_service = event_service
        self.conversation_service = conversation_service

    async def find_or_create(
        self,
        user_id: str,
        company_name: str,
        trigger: TriggerType,
        company_id: str | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: Any = None,
        expected_value: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LeadMemory:
        """Find existing lead or create new one for company.

        Checks for existing leads with matching company name (case-insensitive).
        Returns existing lead if found, otherwise creates new one.

        Args:
            user_id: The user's ID.
            company_name: Name of the company to track.
            trigger: Source that triggered lead creation.
            company_id: Optional company UUID reference.
            crm_id: Optional CRM record ID.
            crm_provider: Optional CRM provider.
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional list of tags.
            metadata: Optional additional metadata.

        Returns:
            The existing or newly created LeadMemory.
        """
        try:
            # Query existing leads for user
            existing_leads = await self.lead_memory_service.list_by_user(
                user_id=user_id,
                limit=1000,  # Get all leads for deduplication check
            )

            # Check for matching company name (case-insensitive)
            company_name_normalized = company_name.strip().lower()
            for lead in existing_leads:
                if lead.company_name.strip().lower() == company_name_normalized:
                    logger.info(
                        "Found existing lead for company",
                        extra={
                            "user_id": user_id,
                            "company_name": company_name,
                            "existing_lead_id": lead.id,
                        },
                    )
                    return lead

            # No match found - create new lead
            logger.info(
                "Creating new lead for company",
                extra={
                    "user_id": user_id,
                    "company_name": company_name,
                    "trigger": trigger.value,
                },
            )

            return await self.lead_memory_service.create(
                user_id=user_id,
                company_name=company_name,
                trigger=trigger,
                company_id=company_id,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_close_date=expected_close_date,
                expected_value=expected_value,
                tags=tags,
                metadata=metadata,
            )

        except Exception:
            logger.exception(
                "Failed to find or create lead",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise
