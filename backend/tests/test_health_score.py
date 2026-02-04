"""Tests for HealthScoreCalculator.

Tests health score calculation across 5 factors:
- Communication frequency (weight: 0.25)
- Response time (weight: 0.20)
- Sentiment (weight: 0.20)
- Stakeholder breadth (weight: 0.20)
- Stage velocity (weight: 0.15)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.memory.health_score import (
    HealthScoreCalculator,
    HealthScoreHistory,
)
from src.memory.lead_memory import LeadMemory, LifecycleStage, LeadStatus, TriggerType
from src.memory.lead_memory_events import LeadEvent
from src.models.lead_memory import Direction, EventType, Sentiment


class TestHealthScoreCalculatorWeights:
    """Test that calculator has correct weights."""

    def test_weights_sum_to_one(self):
        """Test weights sum to 1.0."""
        calculator = HealthScoreCalculator()
        total = sum(calculator.WEIGHTS.values())
        assert total == pytest.approx(1.0)


class TestCommunicationFrequencyScore:
    """Test communication frequency scoring."""

    def test_no_events_zero_score(self):
        """Test lead with no events gets 0 frequency score."""
        calculator = HealthScoreCalculator()
        events = []
        score = calculator._score_frequency(events)
        assert score == 0.0

    def test_daily_events_high_score(self):
        """Test daily events produce high score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        # Create 30 events over 30 days (one per day)
        events = [
            LeadEvent(
                id=f"evt_{i}",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Follow up",
                content="Checking in",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(days=i),
                source="manual",
                source_id=None,
                created_at=now,
            )
            for i in range(30)
        ]

        score = calculator._score_frequency(events)
        assert score > 0.8  # High score for consistent contact

    def test_no_recent_activity_low_score(self):
        """Test no recent events produce low score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        # Events from 90 days ago
        events = [
            LeadEvent(
                id="evt_old",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Old contact",
                content="Ancient history",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(days=90),
                source="manual",
                source_id=None,
                created_at=now,
            )
        ]

        score = calculator._score_frequency(events)
        assert score < 0.3  # Low score for stale lead


class TestResponseTimeScore:
    """Test response time scoring."""

    def test_no_inbound_events_default_score(self):
        """Test no inbound events returns neutral score."""
        calculator = HealthScoreCalculator()
        events = []
        score = calculator._score_response_time(events)
        assert score == 0.5  # Neutral default

    def test_fast_response_high_score(self):
        """Test same-day response gets high score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        events = [
            # Inbound email
            LeadEvent(
                id="evt_in",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_RECEIVED,
                direction=Direction.INBOUND,
                subject="Question",
                content="Can you help?",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(hours=2),
                source="gmail",
                source_id="msg_1",
                created_at=now,
            ),
            # Outbound response within 2 hours
            LeadEvent(
                id="evt_out",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Re: Question",
                content="Happy to help!",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(hours=1),
                source="gmail",
                source_id="msg_2",
                created_at=now,
            ),
        ]

        score = calculator._score_response_time(events)
        assert score > 0.8  # High score for fast response

    def test_slow_response_low_score(self):
        """Test week-long response gets low score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        events = [
            # Inbound email
            LeadEvent(
                id="evt_in",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_RECEIVED,
                direction=Direction.INBOUND,
                subject="Question",
                content="Can you help?",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(days=14),
                source="gmail",
                source_id="msg_1",
                created_at=now,
            ),
            # Outbound response after 7 days
            LeadEvent(
                id="evt_out",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Re: Question",
                content="Sorry for delay",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(days=7),
                source="gmail",
                source_id="msg_2",
                created_at=now,
            ),
        ]

        score = calculator._score_response_time(events)
        assert score < 0.4  # Low score for slow response


class TestSentimentScore:
    """Test sentiment scoring."""

    def test_no_insights_neutral_score(self):
        """Test no insights returns neutral score."""
        calculator = HealthScoreCalculator()
        insights = []
        score = calculator._score_sentiment(insights)
        assert score == 0.5  # Neutral default

    def test_mostly_positive_high_score(self):
        """Test mostly positive sentiment gets high score."""
        calculator = HealthScoreCalculator()

        insights = [
            MagicMock(sentiment=Sentiment.POSITIVE),
            MagicMock(sentiment=Sentiment.POSITIVE),
            MagicMock(sentiment=Sentiment.NEUTRAL),
        ]

        score = calculator._score_sentiment(insights)
        assert score > 0.7  # High score for positive sentiment

    def test_mostly_negative_low_score(self):
        """Test mostly negative sentiment gets low score."""
        calculator = HealthScoreCalculator()

        insights = [
            MagicMock(sentiment=Sentiment.NEGATIVE),
            MagicMock(sentiment=Sentiment.NEGATIVE),
            MagicMock(sentiment=Sentiment.NEUTRAL),
        ]

        score = calculator._score_sentiment(insights)
        assert score < 0.4  # Low score for negative sentiment


class TestStakeholderBreadthScore:
    """Test stakeholder breadth scoring."""

    def test_no_stakeholders_zero_score(self):
        """Test no stakeholders returns 0 score."""
        calculator = HealthScoreCalculator()
        stakeholders = []
        score = calculator._score_breadth(stakeholders)
        assert score == 0.0

    def test_multiple_roles_high_score(self):
        """Test diverse stakeholder roles gets high score."""
        calculator = HealthScoreCalculator()

        stakeholders = [
            MagicMock(role="decision_maker", contact_email="ceo@acme.com"),
            MagicMock(role="champion", contact_email="champion@acme.com"),
            MagicMock(role="user", contact_email="user@acme.com"),
            MagicMock(role="influencer", contact_email="influencer@acme.com"),
        ]

        score = calculator._score_breadth(stakeholders)
        assert score > 0.7  # High score for diverse engagement

    def test_single_stakeholder_low_score(self):
        """Test single stakeholder gets low score."""
        calculator = HealthScoreCalculator()

        stakeholders = [
            MagicMock(role="user", contact_email="user@acme.com"),
        ]

        score = calculator._score_breadth(stakeholders)
        assert score < 0.4  # Low score for limited engagement


class TestStageVelocityScore:
    """Test stage velocity scoring."""

    def test_new_lead_neutral_score(self):
        """Test new lead gets neutral score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        lead = LeadMemory(
            id="lead_123",
            user_id="user_1",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now - timedelta(days=1),
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        score = calculator._score_velocity(lead, stage_history=[])
        assert score == 0.5  # Neutral for new lead

    def test_fast_progression_high_score(self):
        """Test fast stage progression gets high score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        lead = LeadMemory(
            id="lead_123",
            user_id="user_1",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now - timedelta(days=14),
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        # Progressed from lead to opportunity in 14 days
        stage_history = [
            {
                "from_stage": "lead",
                "to_stage": "opportunity",
                "transitioned_at": (now - timedelta(days=7)).isoformat(),
            }
        ]

        score = calculator._score_velocity(lead, stage_history)
        assert score > 0.7  # High score for fast progression

    def test_stalled_low_score(self):
        """Test stalled lead gets low score."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        lead = LeadMemory(
            id="lead_123",
            user_id="user_1",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.LEAD,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now - timedelta(days=90),
            last_activity_at=now - timedelta(days=30),
            created_at=now,
            updated_at=now,
        )

        score = calculator._score_velocity(lead, stage_history=[])
        assert score < 0.4  # Low score for stalled lead


class TestCalculateOverallScore:
    """Test overall score calculation."""

    def test_calculate_returns_0_to_100(self):
        """Test calculate returns value between 0-100."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        lead = LeadMemory(
            id="lead_123",
            user_id="user_1",
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

        score = calculator.calculate(
            lead=lead,
            events=[],
            insights=[],
            stakeholders=[],
            stage_history=[],
        )

        assert 0 <= score <= 100

    def test_calculate_with_perfect_inputs(self):
        """Test calculate returns high score with good inputs."""
        calculator = HealthScoreCalculator()
        now = datetime.now(UTC)

        lead = LeadMemory(
            id="lead_123",
            user_id="user_1",
            company_name="Acme Corp",
            lifecycle_stage=LifecycleStage.OPPORTUNITY,
            status=LeadStatus.ACTIVE,
            health_score=50,
            trigger=TriggerType.MANUAL,
            first_touch_at=now - timedelta(days=30),
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )

        # High frequency events
        events = [
            LeadEvent(
                id=f"evt_{i}",
                lead_memory_id="lead_123",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Follow up",
                content="Checking in",
                participants=["john@acme.com"],
                occurred_at=now - timedelta(days=i),
                source="manual",
                source_id=None,
                created_at=now,
            )
            for i in range(30)
        ]

        # Positive sentiment
        insights = [
            MagicMock(sentiment=Sentiment.POSITIVE),
            MagicMock(sentiment=Sentiment.POSITIVE),
        ]

        # Diverse stakeholders
        stakeholders = [
            MagicMock(role="decision_maker", contact_email="ceo@acme.com"),
            MagicMock(role="champion", contact_email="champ@acme.com"),
        ]

        stage_history = [
            {
                "from_stage": "lead",
                "to_stage": "opportunity",
                "transitioned_at": (now - timedelta(days=14)).isoformat(),
            }
        ]

        score = calculator.calculate(
            lead=lead,
            events=events,
            insights=insights,
            stakeholders=stakeholders,
            stage_history=stage_history,
        )

        assert score > 70  # High score for healthy lead


class TestScoreHistory:
    """Test score history tracking."""

    def test_should_alert_on_large_drop(self):
        """Test alert on 20+ point drop."""
        calculator = HealthScoreCalculator()

        history = [
            HealthScoreHistory(score=85, calculated_at=datetime.now(UTC)),
        ]

        should_alert = calculator._should_alert(
            current_score=60,
            history=history,
            threshold=20,
        )

        assert should_alert is True

    def test_no_alert_on_small_drop(self):
        """Test no alert on small drop."""
        calculator = HealthScoreCalculator()

        history = [
            HealthScoreHistory(score=85, calculated_at=datetime.now(UTC)),
        ]

        should_alert = calculator._should_alert(
            current_score=75,
            history=history,
            threshold=20,
        )

        assert should_alert is False

    def test_no_alert_on_increase(self):
        """Test no alert on score increase."""
        calculator = HealthScoreCalculator()

        history = [
            HealthScoreHistory(score=60, calculated_at=datetime.now(UTC)),
        ]

        should_alert = calculator._should_alert(
            current_score=85,
            history=history,
            threshold=20,
        )

        assert should_alert is False

    def test_no_alert_with_no_history(self):
        """Test no alert when no history exists."""
        calculator = HealthScoreCalculator()

        should_alert = calculator._should_alert(
            current_score=50,
            history=[],
            threshold=20,
        )

        assert should_alert is False
