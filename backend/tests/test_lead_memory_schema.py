from datetime import datetime

import pytest

from src.models.lead_memory import (
    EventType,
    InsightCreate,
    InsightType,
    LeadEventCreate,
    LeadMemoryCreate,
    LeadMemoryUpdate,
    LifecycleStage,
    Sentiment,
    StakeholderCreate,
    StakeholderRole,
)


class TestLeadMemoryModels:
    def test_lifecycle_stage_enum(self):
        assert LifecycleStage.LEAD.value == "lead"
        assert LifecycleStage.OPPORTUNITY.value == "opportunity"
        assert LifecycleStage.ACCOUNT.value == "account"

    def test_lead_status_enum(self):
        from src.models.lead_memory import LeadStatus

        assert LeadStatus.ACTIVE.value == "active"
        assert LeadStatus.WON.value == "won"
        assert LeadStatus.LOST.value == "lost"
        assert LeadStatus.DORMANT.value == "dormant"

    def test_lead_memory_create(self):
        lead = LeadMemoryCreate(
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            tags=["pharma", "enterprise"],
        )
        assert lead.company_name == "Acme Corp"
        assert lead.lifecycle_stage == LifecycleStage.LEAD
        assert lead.tags == ["pharma", "enterprise"]

    def test_lead_memory_create_defaults(self):
        lead = LeadMemoryCreate(company_name="Test Co")
        assert lead.lifecycle_stage == LifecycleStage.LEAD
        assert lead.tags == []
        assert lead.metadata == {}

    def test_lead_memory_update_partial(self):
        update = LeadMemoryUpdate(health_score=75)
        assert update.health_score == 75
        assert update.company_name is None

    def test_lead_memory_update_health_score_validation(self):
        with pytest.raises(ValueError):
            LeadMemoryUpdate(health_score=101)
        with pytest.raises(ValueError):
            LeadMemoryUpdate(health_score=-1)

    def test_lead_event_create(self):
        event = LeadEventCreate(
            event_type=EventType.EMAIL_SENT,
            direction="outbound",
            subject="Follow up",
            occurred_at=datetime.now(),
            participants=["john@acme.com"],
        )
        assert event.event_type == EventType.EMAIL_SENT
        assert event.direction == "outbound"

    def test_stakeholder_create(self):
        stakeholder = StakeholderCreate(
            contact_email="john@acme.com",
            contact_name="John Smith",
            role=StakeholderRole.DECISION_MAKER,
            influence_level=8,
        )
        assert stakeholder.contact_email == "john@acme.com"
        assert stakeholder.role == StakeholderRole.DECISION_MAKER
        assert stakeholder.influence_level == 8

    def test_stakeholder_influence_level_validation(self):
        with pytest.raises(ValueError):
            StakeholderCreate(contact_email="test@test.com", influence_level=0)
        with pytest.raises(ValueError):
            StakeholderCreate(contact_email="test@test.com", influence_level=11)

    def test_stakeholder_defaults(self):
        stakeholder = StakeholderCreate(contact_email="test@test.com")
        assert stakeholder.influence_level == 5
        assert stakeholder.sentiment == Sentiment.NEUTRAL

    def test_insight_create(self):
        insight = InsightCreate(
            insight_type=InsightType.BUYING_SIGNAL,
            content="Mentioned budget approval",
            confidence=0.85,
        )
        assert insight.insight_type == InsightType.BUYING_SIGNAL
        assert insight.confidence == 0.85

    def test_insight_confidence_validation(self):
        with pytest.raises(ValueError):
            InsightCreate(insight_type=InsightType.RISK, content="Test", confidence=1.5)
        with pytest.raises(ValueError):
            InsightCreate(insight_type=InsightType.RISK, content="Test", confidence=-0.1)

    def test_all_event_types(self):
        for event_type in EventType:
            event = LeadEventCreate(
                event_type=event_type,
                occurred_at=datetime.now(),
            )
            assert event.event_type == event_type

    def test_all_insight_types(self):
        for insight_type in InsightType:
            insight = InsightCreate(
                insight_type=insight_type,
                content=f"Test {insight_type.value}",
            )
            assert insight.insight_type == insight_type
