"""Lead memory creation triggers service.

Detects and creates Lead Memories from various trigger sources:
- Email approval: User approves outbound email to prospect
- Manual tracking: User clicks "track this company"
- CRM import: Bulk import from Salesforce/HubSpot
- Inbound response: Reply from prospect

Handles deduplication and retroactive history scanning.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
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

    async def on_email_approved(
        self,
        user_id: str,
        company_name: str,
        email_subject: str,
        email_content: str,
        recipient_email: str,
        occurred_at: datetime,
    ) -> LeadMemory:
        """Create lead when user approves outbound email to prospect.

        Args:
            user_id: The user who approved the email.
            company_name: Name of prospect's company (extracted from email).
            email_subject: Subject line of approved email.
            email_content: Body content of approved email.
            recipient_email: Email address of prospect.
            occurred_at: When the email was sent.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Find or create lead
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.EMAIL_APPROVED,
            )

            # Add email event to lead timeline
            from src.models.lead_memory import Direction, EventType, LeadEventCreate

            event_data = LeadEventCreate(
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject=email_subject,
                content=email_content,
                participants=[recipient_email],
                occurred_at=occurred_at,
                source="gmail",
            )

            await self.event_service.add_event(
                user_id=user_id,
                lead_memory_id=lead.id,
                event_data=event_data,
            )

            logger.info(
                "Created lead from approved email",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                    "recipient": recipient_email,
                },
            )

            return lead

        except Exception:
            logger.exception(
                "Failed to process email approval trigger",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise

    async def on_manual_track(
        self,
        user_id: str,
        company_name: str,
        notes: str | None = None,
    ) -> LeadMemory:
        """Create lead when user manually clicks 'track this'.

        Args:
            user_id: The user tracking the company.
            company_name: Name of the company to track.
            notes: Optional notes about why they're tracking.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Build metadata if notes provided
            metadata = {"notes": notes} if notes else None

            # Find or create lead
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.MANUAL,
                metadata=metadata,
            )

            # If new lead and notes provided, add as note event
            if notes and lead.trigger == TriggerType.MANUAL:
                from src.models.lead_memory import EventType, LeadEventCreate

                event_data = LeadEventCreate(
                    event_type=EventType.NOTE,
                    content=notes,
                    occurred_at=datetime.now(),
                    source="manual",
                )

                await self.event_service.add_event(
                    user_id=user_id,
                    lead_memory_id=lead.id,
                    event_data=event_data,
                )

            logger.info(
                "Manual track lead created/found",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                },
            )

            return lead

        except Exception:
            logger.exception(
                "Failed to process manual track trigger",
                extra={"user_id": user_id, "company_name": company_name},
            )
            raise

    async def on_crm_import(
        self,
        user_id: str,
        company_name: str,
        crm_id: str,
        crm_provider: str,
        expected_value: Decimal | None = None,
        expected_close_date: date | None = None,
    ) -> LeadMemory:
        """Create lead from CRM import (Salesforce, HubSpot, etc.).

        Args:
            user_id: The user importing from CRM.
            company_name: Name of the company from CRM.
            crm_id: External CRM record ID.
            crm_provider: CRM provider name (salesforce, hubspot).
            expected_value: Optional deal value from CRM.
            expected_close_date: Optional close date from CRM.

        Returns:
            The created or existing LeadMemory.
        """
        try:
            # Find or create lead with CRM fields
            lead = await self.find_or_create(
                user_id=user_id,
                company_name=company_name,
                trigger=TriggerType.CRM_IMPORT,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_value=expected_value,
                expected_close_date=expected_close_date,
            )

            logger.info(
                "CRM import lead created/found",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "company_name": company_name,
                    "crm_provider": crm_provider,
                    "crm_id": crm_id,
                },
            )

            return lead

        except Exception:
            logger.exception(
                "Failed to process CRM import trigger",
                extra={
                    "user_id": user_id,
                    "company_name": company_name,
                    "crm_provider": crm_provider,
                },
            )
            raise
