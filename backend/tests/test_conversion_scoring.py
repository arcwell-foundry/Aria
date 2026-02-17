"""Tests for ConversionScoringService."""

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.services.conversion_scoring import (
    BatchScoreResult,
    ConversionScore,
    ConversionScoringService,
    FeatureDriver,
    LeadNotFoundError,
    ScoreExplanation,
    ScoringError,
    FEATURE_WEIGHTS,
)


@pytest.fixture
def mock_db():
    """Create a mock database client.

    Note: Supabase client is synchronous, so we use MagicMock (not AsyncMock).
    """
    db = MagicMock()
    # Chain methods for fluent interface - execute returns MagicMock, not coroutine
    db.table.return_value.select.return_value.eq.return_value.execute = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create a ConversionScoringService with mocked database."""
    with patch("src.services.conversion_scoring.SupabaseClient.get_client", return_value=mock_db):
        yield ConversionScoringService()


@pytest.fixture
def sample_lead():
    """Create a sample lead for testing."""
    return {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "company_name": "Acme Pharma",
        "lifecycle_stage": "opportunity",
        "status": "active",
        "health_score": 75,
        "created_at": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
        "updated_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
        "metadata": {},
    }


@pytest.fixture
def new_lead():
    """Create a new lead (<7 days old) for testing."""
    return {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "company_name": "NewCo Biotech",
        "lifecycle_stage": "lead",
        "status": "active",
        "health_score": 50,
        "created_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
        "updated_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
        "metadata": {},
    }


@pytest.fixture
def won_lead():
    """Create a won lead for testing."""
    return {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "company_name": "Won Customer",
        "lifecycle_stage": "account",
        "status": "won",
        "health_score": 100,
        "created_at": (datetime.now(UTC) - timedelta(days=90)).isoformat(),
        "metadata": {},
    }


# === Unit Tests for Feature Calculations ===


class TestFeatureCalculations:
    """Tests for individual feature calculation methods."""

    @pytest.mark.asyncio
    async def test_calculate_engagement_frequency_high(self, service, mock_db):
        """Test engagement frequency with many interactions."""
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=25, data=[]
        )

        result = await service._calculate_engagement_frequency("lead-123", datetime.now(UTC))

        assert result == 1.0  # Capped at 1.0 for 25+ interactions

    @pytest.mark.asyncio
    async def test_calculate_engagement_frequency_low(self, service, mock_db):
        """Test engagement frequency with few interactions."""
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=5, data=[]
        )

        result = await service._calculate_engagement_frequency("lead-123", datetime.now(UTC))

        assert result == 0.25  # 5/20

    @pytest.mark.asyncio
    async def test_calculate_stakeholder_depth_with_champion(self, service, mock_db):
        """Test stakeholder depth with decision makers and champions."""
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"role": "decision_maker", "influence_level": 9},
                {"role": "champion", "influence_level": 8},
                {"role": "influencer", "influence_level": 6},
            ]
        )

        result = await service._calculate_stakeholder_depth("lead-123")

        # (9 + 8 + 6) / (3 * 10) = 23/30 = 0.767
        assert abs(result - 0.767) < 0.01

    @pytest.mark.asyncio
    async def test_calculate_stakeholder_depth_empty(self, service, mock_db):
        """Test stakeholder depth with no stakeholders."""
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        result = await service._calculate_stakeholder_depth("lead-123")

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculate_avg_response_time_fast(self, service, mock_db):
        """Test response time calculation with fast responses."""
        now = datetime.now(UTC)
        events = [
            {
                "event_type": "email_sent",
                "direction": "outbound",
                "occurred_at": (now - timedelta(hours=5)).isoformat(),
            },
            {
                "event_type": "email_received",
                "direction": "inbound",
                "occurred_at": (now - timedelta(hours=4)).isoformat(),
            },
            {
                "event_type": "email_sent",
                "direction": "outbound",
                "occurred_at": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "event_type": "email_received",
                "direction": "inbound",
                "occurred_at": (now - timedelta(hours=2)).isoformat(),
            },
        ]

        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=events
        )

        result = await service._calculate_avg_response_time("lead-123", now)

        # ~1 hour average response → should be high (close to 1.0)
        assert result > 0.9

    @pytest.mark.asyncio
    async def test_calculate_avg_response_time_slow(self, service, mock_db):
        """Test response time calculation with slow responses."""
        now = datetime.now(UTC)
        events = [
            {
                "event_type": "email_sent",
                "direction": "outbound",
                "occurred_at": (now - timedelta(hours=100)).isoformat(),
            },
            {
                "event_type": "email_received",
                "direction": "inbound",
                "occurred_at": (now - timedelta(hours=20)).isoformat(),
            },
        ]

        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=events
        )

        result = await service._calculate_avg_response_time("lead-123", now)

        # 80 hours response time → 1 - 80/72 = negative, clamped to 0
        assert result >= 0.0

    @pytest.mark.asyncio
    async def test_calculate_sentiment_trend_positive(self, service, mock_db):
        """Test sentiment trend with mostly positive stakeholders."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(
                data=[
                    {"sentiment": "positive"},
                    {"sentiment": "positive"},
                    {"sentiment": "positive"},
                    {"sentiment": "neutral"},
                ]
            )
        )

        result = await service._calculate_sentiment_trend("lead-123", datetime.now(UTC))

        # 3 positive, 0 negative, 4 total → (3-0)/4 = 0.75 net → (0.75+1)/2 = 0.875
        assert abs(result - 0.875) < 0.01

    @pytest.mark.asyncio
    async def test_calculate_sentiment_trend_negative(self, service, mock_db):
        """Test sentiment trend with mostly negative stakeholders."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(
                data=[
                    {"sentiment": "negative"},
                    {"sentiment": "negative"},
                    {"sentiment": "neutral"},
                ]
            )
        )

        result = await service._calculate_sentiment_trend("lead-123", datetime.now(UTC))

        # 0 positive, 2 negative, 3 total → (0-2)/3 = -0.67 net → (-0.67+1)/2 = 0.165
        assert abs(result - 0.165) < 0.02

    def test_calculate_stage_velocity_on_track(self, service, sample_lead):
        """Test stage velocity for a lead moving at expected pace."""
        sample_lead["updated_at"] = (datetime.now(UTC) - timedelta(days=20)).isoformat()
        sample_lead["lifecycle_stage"] = "opportunity"  # Expected 60 days

        result = service._calculate_stage_velocity(sample_lead)

        # 20/60 = 0.33 ratio → 1 - 0.33/1.5 = 0.78
        assert result > 0.7

    def test_calculate_stage_velocity_stalled(self, service, sample_lead):
        """Test stage velocity for a stalled lead."""
        sample_lead["updated_at"] = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        sample_lead["lifecycle_stage"] = "opportunity"  # Expected 60 days

        result = service._calculate_stage_velocity(sample_lead)

        # 90/60 = 1.5 ratio → 1 - 1.5/1.5 = 0
        assert result >= 0.0

    @pytest.mark.asyncio
    async def test_calculate_health_score_trend_improving(self, service, mock_db):
        """Test health score trend when improving."""
        now = datetime.now(UTC)
        history = [
            {"score": 50, "calculated_at": (now - timedelta(days=20)).isoformat()},
            {"score": 60, "calculated_at": (now - timedelta(days=10)).isoformat()},
            {"score": 70, "calculated_at": now.isoformat()},
        ]

        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=history
        )

        result = await service._calculate_health_score_trend("lead-123", now)

        # Positive slope should give > 0.5
        assert result > 0.5

    @pytest.mark.asyncio
    async def test_calculate_meeting_frequency_high(self, service, mock_db):
        """Test meeting frequency with many meetings."""
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=6, data=[]
        )

        result = await service._calculate_meeting_frequency("lead-123", datetime.now(UTC))

        assert result == 1.0  # Capped at 1.0 for 4+ meetings

    @pytest.mark.asyncio
    async def test_calculate_commitment_fulfillment_theirs(self, service, mock_db):
        """Test commitment fulfillment for their commitments."""
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"metadata": {"direction": "theirs"}, "addressed_at": "2024-01-01"},
                {"metadata": {"direction": "theirs"}, "addressed_at": "2024-01-02"},
                {"metadata": {"direction": "theirs"}, "addressed_at": None},  # Not fulfilled
            ]
        )

        theirs, ours = await service._calculate_commitment_fulfillment("lead-123")

        assert theirs == 2 / 3  # 2 of 3 fulfilled
        assert ours == 0.5  # No "ours" commitments, neutral default

    @pytest.mark.asyncio
    async def test_calculate_commitment_fulfillment_no_data(self, service, mock_db):
        """Test commitment fulfillment with no data returns neutral."""
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        theirs, ours = await service._calculate_commitment_fulfillment("lead-123")

        assert theirs == 0.5  # Neutral default
        assert ours == 0.5  # Neutral default


# === Unit Tests for Score Calculation ===


class TestScoreCalculation:
    """Tests for the main score calculation logic."""

    def test_calculate_weighted_score(self, service):
        """Test weighted score calculation."""
        feature_values = {
            "engagement_frequency": 0.8,
            "stakeholder_depth": 0.6,
            "avg_response_time": 0.7,
            "sentiment_trend": 0.5,
            "stage_velocity": 0.4,
            "health_score_trend": 0.6,
            "meeting_frequency": 0.5,
            "commitment_fulfillment_theirs": 0.7,
            "commitment_fulfillment_ours": 0.5,
        }

        result = service._calculate_weighted_score(feature_values)

        # Should be between 0 and 1
        assert 0 <= result <= 1

        # Manual calculation for verification
        expected = sum(feature_values[name] * FEATURE_WEIGHTS[name] for name in FEATURE_WEIGHTS)
        assert abs(result - expected) < 0.001

    def test_logistic_transform_middle(self, service):
        """Test logistic transformation at middle point."""
        result = service._logistic_transform(0.5)

        # At 0.5, should give 50%
        assert abs(result - 50) < 0.1

    def test_logistic_transform_high(self, service):
        """Test logistic transformation with high input."""
        result = service._logistic_transform(0.8)

        # High input should give high probability
        assert result > 80

    def test_logistic_transform_low(self, service):
        """Test logistic transformation with low input."""
        result = service._logistic_transform(0.2)

        # Low input should give low probability
        assert result < 20

    def test_logistic_transform_boundaries(self, service):
        """Test logistic transformation at boundaries."""
        assert 0 < service._logistic_transform(0) < 50
        assert 50 < service._logistic_transform(1) <= 100


# === Integration Tests ===


class TestCalculateConversionScore:
    """Integration tests for calculate_conversion_score."""

    @pytest.mark.asyncio
    async def test_score_lead_with_full_data(self, service, mock_db, sample_lead):
        """Test scoring a lead with complete data."""
        lead_id = sample_lead["id"]

        # Mock lead fetch - need 2 responses: initial fetch + cache_score fetch
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=sample_lead),  # Initial lead fetch
            MagicMock(data=sample_lead),  # _cache_score fetch
        ]

        # Mock feature queries
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=10, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"role": "champion", "influence_level": 8}]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )

        # Mock cache and prediction writes
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[sample_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        score = await service.calculate_conversion_score(lead_id)

        assert isinstance(score, ConversionScore)
        assert score.lead_memory_id == UUID(lead_id)  # Compare as UUID
        assert 0 <= score.conversion_probability <= 100
        assert 0 <= score.confidence <= 1
        assert len(score.feature_values) == 9
        assert len(score.feature_importance) == 9

    @pytest.mark.asyncio
    async def test_score_lead_not_found(self, service, mock_db):
        """Test scoring a non-existent lead."""
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        with pytest.raises(LeadNotFoundError):
            await service.calculate_conversion_score(uuid4())

    @pytest.mark.asyncio
    async def test_score_won_lead_returns_error(self, service, mock_db, won_lead):
        """Test scoring a won lead raises error if no cache."""
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=won_lead
        )

        with pytest.raises(ScoringError) as exc_info:
            await service.calculate_conversion_score(won_lead["id"])

        assert "won" in str(exc_info.value).lower() or "status" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_score_new_lead_confidence_penalty(self, service, mock_db, new_lead):
        """Test that new leads get confidence penalty."""
        # Need 2 responses: initial fetch + cache_score fetch
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=new_lead),  # Initial fetch
            MagicMock(data=new_lead),  # _cache_score fetch
        ]

        # Mock feature queries with minimal data
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=1, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[new_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        score = await service.calculate_conversion_score(new_lead["id"])

        # Confidence should be reduced for new lead
        assert score.confidence < 0.5  # Already penalized by 0.5


class TestExplainScore:
    """Tests for explain_score method."""

    @pytest.mark.asyncio
    async def test_explain_score_generates_readable_output(self, service, mock_db, sample_lead):
        """Test that explain_score generates human-readable output."""
        lead_id = sample_lead["id"]

        # Setup mocks similar to score calculation
        # Need multiple responses: calculate_conversion_score (2) + explain_score fetch (1)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=sample_lead),  # calculate_conversion_score initial fetch
            MagicMock(data=sample_lead),  # _cache_score fetch
            MagicMock(data=sample_lead),  # explain_score fetch
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=15, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"role": "champion", "influence_level": 9},
                {"role": "decision_maker", "influence_level": 8},
            ]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[sample_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        explanation = await service.explain_score(lead_id)

        assert isinstance(explanation, ScoreExplanation)
        assert explanation.lead_memory_id == UUID(lead_id)  # Compare as UUID
        assert len(explanation.summary) > 20
        assert len(explanation.recommendation) > 10
        assert isinstance(explanation.key_drivers, list)
        assert isinstance(explanation.key_risks, list)


class TestBatchScoreAllLeads:
    """Tests for batch_score_all_leads method."""

    @pytest.mark.asyncio
    async def test_batch_score_processes_all_active_leads(self, service, mock_db, sample_lead):
        """Test that batch scoring processes all active leads."""
        user_id = uuid4()

        # Mock active leads list
        leads = [
            {"id": str(uuid4())},
            {"id": str(uuid4())},
            {"id": str(uuid4())},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=leads
        )

        # Mock individual lead fetches and scoring
        for lead in leads:
            lead_data = {**sample_lead, "id": lead["id"]}
            mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
                MagicMock(data=lead_data),
            ]

        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=5, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"role": "champion", "influence_level": 7}]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[sample_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        # Reset side_effect and set up for each lead
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = None
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=sample_lead
        )

        result = await service.batch_score_all_leads(user_id)

        assert isinstance(result, BatchScoreResult)
        assert result.scored >= 0
        assert isinstance(result.errors, list)
        assert result.duration_seconds >= 0


# === Edge Case Tests ===


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_staleness_check_triggers_recalculation(self, service, mock_db, sample_lead):
        """Test that stale cached scores trigger recalculation."""
        lead_id = sample_lead["id"]

        # Create a stale cached score
        stale_score = ConversionScore(
            lead_memory_id=lead_id,
            conversion_probability=50.0,
            confidence=0.5,
            feature_values={},
            feature_importance={},
            calculated_at=datetime.now(UTC) - timedelta(hours=25),  # Stale
        )

        sample_lead["metadata"] = {"conversion_score": stale_score.model_dump()}
        sample_lead["metadata"]["conversion_score"]["calculated_at"] = (
            stale_score.calculated_at.isoformat()
        )

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=sample_lead
        )
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=5, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[sample_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        score = await service.calculate_conversion_score(lead_id)

        # Should have recalculated (fresh timestamp)
        assert score.calculated_at > stale_score.calculated_at

    def test_is_new_lead_true(self, service, new_lead):
        """Test new lead detection for leads <7 days old."""
        assert service._is_new_lead(new_lead) is True

    def test_is_new_lead_false(self, service, sample_lead):
        """Test new lead detection for older leads."""
        assert service._is_new_lead(sample_lead) is False

    @pytest.mark.asyncio
    async def test_score_lead_with_partial_data(self, service, mock_db, sample_lead):
        """Test scoring when some features have no data."""
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=sample_lead
        )

        # All feature queries return empty/minimal data
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            count=0, data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[sample_lead])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1"}]
        )

        score = await service.calculate_conversion_score(sample_lead["id"])

        # Should still produce a valid score
        assert 0 <= score.conversion_probability <= 100
        # Confidence should be lower due to missing data
        assert score.confidence < 0.7

    def test_confidence_calculation_with_missing_data(self, service, sample_lead):
        """Test confidence calculation penalizes missing data."""
        # Features at default values (0.5) indicate missing data
        feature_values = {name: 0.5 for name in FEATURE_WEIGHTS}

        confidence = service._calculate_confidence(feature_values, sample_lead)

        # Should be moderate confidence due to all defaults
        assert 0.3 < confidence < 0.7
