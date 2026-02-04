"""Tests for Lead Memory module."""

from datetime import UTC, datetime
from decimal import Decimal


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
