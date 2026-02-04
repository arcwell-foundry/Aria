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

from src.memory.lead_memory import LeadMemoryService

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
