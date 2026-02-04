"""Tests for LeadTriggerService - lead memory creation from trigger sources."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.memory.lead_memory import LeadMemory, LeadStatus, LifecycleStage, TriggerType
from src.memory.lead_triggers import LeadTriggerService


class TestLeadTriggerServiceInit:
    """Tests for LeadTriggerService initialization."""

    def test_service_initialization_with_dependencies(self):
        """Test service can be initialized with required dependencies."""
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


class TestFindOrCreate:
    """Tests for find_or_create deduplication logic."""

    @pytest.mark.asyncio
    async def test_find_existing_lead_by_company_name(self):
        """Test find_or_create returns existing lead for same company."""
        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-123",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=65,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime(2025, 1, 15, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 1, tzinfo=UTC),
            created_at=datetime(2025, 1, 15, tzinfo=UTC),
            updated_at=datetime(2025, 2, 1, tzinfo=UTC),
        )

        # Mock list_by_user to return existing lead
        mock_lead_service.list_by_user = AsyncMock(return_value=[existing_lead])

        # Call find_or_create
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="Acme Corp",
            trigger=TriggerType.MANUAL,
        )

        # Should return existing lead, not create new one
        assert result.id == "lead-123"
        assert result.company_name == "Acme Corp"
        mock_lead_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_new_lead_when_no_match(self):
        """Test find_or_create creates new lead for unknown company."""
        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock no existing leads
        mock_lead_service.list_by_user = AsyncMock(return_value=[])

        # Mock create response
        new_lead = LeadMemory(
            id="lead-new",
            user_id="user-abc",
            company_name="New Company LLC",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create = AsyncMock(return_value=new_lead)

        # Call find_or_create
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="New Company LLC",
            trigger=TriggerType.MANUAL,
        )

        # Should create new lead
        assert result.id == "lead-new"
        mock_lead_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_company_matching(self):
        """Test find_or_create matches company names case-insensitively."""
        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead with different case
        existing_lead = LeadMemory(
            id="lead-123",
            user_id="user-abc",
            company_name="ACME CORPORATION",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=65,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.list_by_user = AsyncMock(return_value=[existing_lead])

        # Call with different case
        result = await service.find_or_create(
            user_id="user-abc",
            company_name="acme corporation",
            trigger=TriggerType.INBOUND,
        )

        # Should find existing match
        assert result.id == "lead-123"
        mock_lead_service.create.assert_not_called()


class TestOnEmailApproved:
    """Tests for on_email_approved trigger."""

    @pytest.mark.asyncio
    async def test_creates_lead_from_approved_outbound_email(self):
        """Test creating lead when user approves outbound email."""
        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_event_service.add_event = AsyncMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock create response
        new_lead = LeadMemory(
            id="lead-new",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.EMAIL_APPROVED,
            first_touch_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_lead_service.create = AsyncMock(return_value=new_lead)
        mock_lead_service.list_by_user = AsyncMock(return_value=[])

        # Call on_email_approved
        result = await service.on_email_approved(
            user_id="user-abc",
            company_name="Acme Corp",
            email_subject="Introduction to ARIA",
            email_content="Hi John, wanted to introduce you to ARIA...",
            recipient_email="john@acmecorp.com",
            occurred_at=datetime(2025, 2, 4, 10, 0, tzinfo=UTC),
        )

        # Verify lead created
        assert result.id == "lead-new"
        mock_lead_service.create.assert_called_once()
        # Check that the key parameters match
        call_kwargs = mock_lead_service.create.call_args.kwargs
        assert call_kwargs["user_id"] == "user-abc"
        assert call_kwargs["company_name"] == "Acme Corp"
        assert call_kwargs["trigger"] == TriggerType.EMAIL_APPROVED

        # Verify email event added
        mock_event_service.add_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_existing_lead_for_same_company(self):
        """Test on_email_approved reuses existing lead."""
        # Setup services
        mock_lead_service = MagicMock()
        mock_event_service = MagicMock()
        mock_event_service.add_event = AsyncMock()
        mock_conv_service = MagicMock()

        service = LeadTriggerService(
            lead_memory_service=mock_lead_service,
            event_service=mock_event_service,
            conversation_service=mock_conv_service,
        )

        # Mock existing lead
        existing_lead = LeadMemory(
            id="lead-existing",
            user_id="user-abc",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=60,
            trigger=TriggerType.MANUAL,
            first_touch_at=datetime(2025, 1, 1, tzinfo=UTC),
            last_activity_at=datetime(2025, 2, 1, tzinfo=UTC),
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            updated_at=datetime(2025, 2, 1, tzinfo=UTC),
        )
        mock_lead_service.list_by_user = AsyncMock(return_value=[existing_lead])

        # Call on_email_approved
        result = await service.on_email_approved(
            user_id="user-abc",
            company_name="Acme Corp",
            email_subject="Follow up",
            email_content="Checking in...",
            recipient_email="john@acmecorp.com",
            occurred_at=datetime.now(UTC),
        )

        # Should reuse existing lead
        assert result.id == "lead-existing"
        mock_lead_service.create.assert_not_called()

        # But still add the event
        mock_event_service.add_event.assert_called_once()
