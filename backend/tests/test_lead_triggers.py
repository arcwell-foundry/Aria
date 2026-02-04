"""Tests for LeadTriggerService - lead memory creation from trigger sources."""

import pytest
from src.memory.lead_triggers import LeadTriggerService


class TestLeadTriggerServiceInit:
    """Tests for LeadTriggerService initialization."""

    def test_service_initialization_with_dependencies(self):
        """Test service can be initialized with required dependencies."""
        from unittest.mock import MagicMock

        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conversation_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conversation_service,
        )

        assert service is not None
        assert service.lead_memory_service == mock_lead_service
        assert service.event_service == mock_event_service
        assert service.conversation_service == mock_conversation_service
