"""Tests for Lead Memory module."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestLifecycleStageEnum:
    """Tests for LifecycleStage enum."""

    def test_lifecycle_stage_values(self) -> None:
        """Test LifecycleStage enum has correct values."""
        from src.memory.lead_memory import LifecycleStage

        assert LifecycleStage.LEAD.value == "lead"
        assert LifecycleStage.OPPORTUNITY.value == "opportunity"
        assert LifecycleStage.ACCOUNT.value == "account"

    def test_lifecycle_stage_ordering(self) -> None:
        """Test lifecycle stages can be compared for progression."""
        from src.memory.lead_memory import LifecycleStage

        stages = [LifecycleStage.LEAD, LifecycleStage.OPPORTUNITY, LifecycleStage.ACCOUNT]
        assert stages == sorted(stages, key=lambda s: list(LifecycleStage).index(s))


class TestLeadStatusEnum:
    """Tests for LeadStatus enum."""

    def test_lead_status_values(self) -> None:
        """Test LeadStatus enum has correct values."""
        from src.memory.lead_memory import LeadStatus

        assert LeadStatus.ACTIVE.value == "active"
        assert LeadStatus.WON.value == "won"
        assert LeadStatus.LOST.value == "lost"
        assert LeadStatus.DORMANT.value == "dormant"


class TestTriggerTypeEnum:
    """Tests for TriggerType enum."""

    def test_trigger_type_values(self) -> None:
        """Test TriggerType enum has correct values."""
        from src.memory.lead_memory import TriggerType

        assert TriggerType.EMAIL_APPROVED.value == "email_approved"
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.CRM_IMPORT.value == "crm_import"
        assert TriggerType.INBOUND.value == "inbound"


class TestLeadMemoryDataclass:
    """Tests for LeadMemory dataclass."""

    def test_lead_memory_initialization(self) -> None:
        """Test LeadMemory initializes with required fields."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=75,
            trigger=TriggerType.MANUAL,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        assert lead.id == "lead-123"
        assert lead.user_id == "user-456"
        assert lead.company_name == "Acme Corp"
        assert lead.lifecycle_stage == LifecycleStage.LEAD
        assert lead.status == LeadStatus.ACTIVE
        assert lead.health_score == 75
        assert lead.trigger == TriggerType.MANUAL

    def test_lead_memory_optional_fields(self) -> None:
        """Test LeadMemory optional fields default correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        assert lead.company_id is None
        assert lead.crm_id is None
        assert lead.crm_provider is None
        assert lead.expected_close_date is None
        assert lead.expected_value is None
        assert lead.tags == []
        assert lead.metadata == {}

    def test_lead_memory_to_dict(self) -> None:
        """Test LeadMemory.to_dict serializes correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        lead = LeadMemory(
            id="lead-123",
            user_id="user-456",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=80,
            trigger=TriggerType.CRM_IMPORT,
            first_touch_at=now,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
            tags=["enterprise", "healthcare"],
            expected_value=Decimal("100000.00"),
        )

        data = lead.to_dict()

        assert data["id"] == "lead-123"
        assert data["lifecycle_stage"] == "opportunity"
        assert data["status"] == "active"
        assert data["tags"] == ["enterprise", "healthcare"]
        assert data["expected_value"] == "100000.00"

    def test_lead_memory_from_dict(self) -> None:
        """Test LeadMemory.from_dict deserializes correctly."""
        from src.memory.lead_memory import (
            LeadMemory,
            LeadStatus,
            LifecycleStage,
            TriggerType,
        )

        now = datetime.now(UTC)
        data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 80,
            "trigger": "crm_import",
            "crm_id": "sf-opp-123",
            "crm_provider": "salesforce",
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": "100000.00",
            "tags": ["enterprise"],
            "metadata": {"source": "website"},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        lead = LeadMemory.from_dict(data)

        assert lead.id == "lead-123"
        assert lead.lifecycle_stage == LifecycleStage.OPPORTUNITY
        assert lead.status == LeadStatus.ACTIVE
        assert lead.trigger == TriggerType.CRM_IMPORT
        assert lead.crm_id == "sf-opp-123"
        assert lead.expected_value == Decimal("100000.00")


class TestLeadMemoryServiceCreate:
    """Tests for LeadMemoryService.create()."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "generated-uuid"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_create_lead_with_minimal_fields(self, mock_supabase: MagicMock) -> None:
        """Test creating a lead with only required fields."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Acme Corp",
                    trigger=TriggerType.MANUAL,
                )

        assert lead.user_id == "user-123"
        assert lead.company_name == "Acme Corp"
        assert lead.trigger == TriggerType.MANUAL
        assert lead.lifecycle_stage.value == "lead"
        assert lead.status.value == "active"
        assert lead.health_score == 50  # Default health score

    @pytest.mark.asyncio
    async def test_create_lead_with_all_fields(self, mock_supabase: MagicMock) -> None:
        """Test creating a lead with all optional fields."""
        from datetime import date
        from decimal import Decimal
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Enterprise Inc",
                    trigger=TriggerType.CRM_IMPORT,
                    company_id="company-456",
                    crm_id="sf-lead-789",
                    crm_provider="salesforce",
                    expected_close_date=date(2025, 6, 30),
                    expected_value=Decimal("250000.00"),
                    tags=["enterprise", "healthcare"],
                    metadata={"source": "conference"},
                )

        assert lead.company_name == "Enterprise Inc"
        assert lead.trigger == TriggerType.CRM_IMPORT
        assert lead.company_id == "company-456"
        assert lead.crm_id == "sf-lead-789"
        assert lead.crm_provider == "salesforce"
        assert lead.expected_value == Decimal("250000.00")
        assert "enterprise" in lead.tags

    @pytest.mark.asyncio
    async def test_create_lead_sets_timestamps(self, mock_supabase: MagicMock) -> None:
        """Test that create sets first_touch_at and last_activity_at."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation"):
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Test Corp",
                    trigger=TriggerType.INBOUND,
                )

        assert lead.first_touch_at is not None
        assert lead.last_activity_at is not None
        assert lead.created_at is not None
        assert lead.first_touch_at == lead.last_activity_at

    @pytest.mark.asyncio
    async def test_create_lead_logs_audit(self, mock_supabase: MagicMock) -> None:
        """Test that create logs to audit trail."""
        from src.memory.lead_memory import LeadMemoryService, TriggerType

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase):
            with patch("src.memory.lead_memory.log_memory_operation") as mock_audit:
                service = LeadMemoryService()
                lead = await service.create(
                    user_id="user-123",
                    company_name="Test Corp",
                    trigger=TriggerType.MANUAL,
                )

                mock_audit.assert_called_once()
                call_kwargs = mock_audit.call_args.kwargs
                assert call_kwargs["user_id"] == "user-123"
                assert call_kwargs["memory_id"] == lead.id


class TestLeadMemoryServiceGetById:
    """Tests for LeadMemoryService.get_by_id()."""

    @pytest.fixture
    def mock_supabase_with_lead(self) -> MagicMock:
        """Create a mocked Supabase client with lead data."""
        mock_client = MagicMock()
        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = {
            "id": "lead-123",
            "user_id": "user-456",
            "company_id": None,
            "company_name": "Acme Corp",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 75,
            "crm_id": None,
            "crm_provider": None,
            "first_touch_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expected_close_date": None,
            "expected_value": None,
            "tags": ["enterprise"],
            "metadata": {"trigger": "manual"},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_get_by_id_returns_lead(self, mock_supabase_with_lead: MagicMock) -> None:
        """Test get_by_id returns the correct lead."""
        from src.memory.lead_memory import LeadMemoryService, LifecycleStage

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_supabase_with_lead):
            service = LeadMemoryService()
            lead = await service.get_by_id(user_id="user-456", lead_id="lead-123")

        assert lead.id == "lead-123"
        assert lead.company_name == "Acme Corp"
        assert lead.lifecycle_stage == LifecycleStage.LEAD

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_raises_error(self) -> None:
        """Test get_by_id raises LeadNotFoundError when lead doesn't exist."""
        from src.core.exceptions import LeadNotFoundError
        from src.memory.lead_memory import LeadMemoryService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = None
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response

        with patch("src.memory.lead_memory.SupabaseClient.get_client", return_value=mock_client):
            service = LeadMemoryService()
            with pytest.raises(LeadNotFoundError) as exc_info:
                await service.get_by_id(user_id="user-456", lead_id="nonexistent")

            assert "nonexistent" in str(exc_info.value)
