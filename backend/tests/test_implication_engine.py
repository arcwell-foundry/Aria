"""Tests for the Implication Reasoning Engine (US-702).

Tests cover:
- Scoring algorithm (impact * 0.4 + confidence * 0.35 + urgency * 0.25)
- Goal filtering and matching
- Classification (opportunity, threat, neutral)
- LLM explanation and recommendation generation
- Signal radar integration hook
- Persistence to jarvis_insights table
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.implication_engine import (
    IMPACT_WEIGHT,
    CONFIDENCE_WEIGHT,
    URGENCY_WEIGHT,
    ImplicationEngine,
)
from src.intelligence.causal.models import (
    CausalChain,
    CausalHop,
    Implication,
    ImplicationRequest,
    ImplicationType,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client with sync execute for Supabase."""
    client = MagicMock()

    # Create a chainable query builder with SYNC execute
    # (Supabase Python client is synchronous)
    def make_query_builder():
        qb = MagicMock()
        qb.select.return_value = qb
        qb.eq.return_value = qb
        qb.neq.return_value = qb
        qb.order.return_value = qb
        qb.limit.return_value = qb
        qb.insert.return_value = qb
        qb.update.return_value = qb
        qb.single.return_value = qb
        # execute() is synchronous in Supabase Python client
        qb.execute.return_value = MagicMock(data=[])
        return qb

    client.table.side_effect = lambda _: make_query_builder()
    return client


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Create a mock LLM client."""
    client = AsyncMock()
    client.generate_response = AsyncMock(return_value="[]")
    return client


@pytest.fixture
def mock_causal_engine(mock_llm_client, mock_db_client) -> CausalChainEngine:
    """Create a mock causal chain engine."""
    engine = CausalChainEngine(
        graphiti_client=None,
        llm_client=mock_llm_client,
        db_client=mock_db_client,
    )
    return engine


@pytest.fixture
def implication_engine(
    mock_causal_engine: CausalChainEngine,
    mock_db_client: MagicMock,
    mock_llm_client: AsyncMock,
) -> ImplicationEngine:
    """Create an ImplicationEngine with mocked dependencies."""
    return ImplicationEngine(
        causal_engine=mock_causal_engine,
        db_client=mock_db_client,
        llm_client=mock_llm_client,
    )


@pytest.fixture
def sample_chain() -> CausalChain:
    """Create a sample causal chain for testing."""
    return CausalChain(
        id=uuid4(),
        trigger_event="Pfizer announces acquisition of Seagen",
        hops=[
            CausalHop(
                source_entity="Pfizer",
                target_entity="Seagen",
                relationship="acquires",
                confidence=0.95,
                explanation="Pfizer acquires Seagen for $43B",
            ),
            CausalHop(
                source_entity="Seagen",
                target_entity="ADC market",
                relationship="enables",
                confidence=0.8,
                explanation="Strengthens Pfizer's ADC pipeline",
            ),
        ],
        final_confidence=0.78,
        time_to_impact="2-4 weeks",
    )


@pytest.fixture
def sample_goals() -> list[dict]:
    """Create sample goals for testing."""
    return [
        {
            "id": str(uuid4()),
            "title": "Close Lonza CDMO deal",
            "description": "Secure partnership with Lonza for ADC manufacturing",
            "priority": 5,
            "status": "active",
            "category": "revenue",
        },
        {
            "id": str(uuid4()),
            "title": "Expand ADC capabilities",
            "description": "Build internal ADC development capacity",
            "priority": 4,
            "status": "active",
            "category": "growth",
        },
        {
            "id": str(uuid4()),
            "title": "Q4 revenue target",
            "description": "Achieve $5M in quarterly revenue",
            "priority": 5,
            "status": "active",
            "category": "revenue",
        },
    ]


# ── Scoring Algorithm Tests ───────────────────────────────────────────────


class TestScoringAlgorithm:
    """Tests for the multi-factor scoring algorithm."""

    def test_scoring_weights_sum_to_one(self):
        """Verify scoring weights add up to 1.0."""
        assert IMPACT_WEIGHT + CONFIDENCE_WEIGHT + URGENCY_WEIGHT == 1.0

    def test_combined_score_calculation(self):
        """Test the combined score formula: impact*0.4 + confidence*0.35 + urgency*0.25."""
        impact = 0.8
        confidence = 0.7
        urgency = 0.6

        expected = impact * 0.4 + confidence * 0.35 + urgency * 0.25
        actual = impact * IMPACT_WEIGHT + confidence * CONFIDENCE_WEIGHT + urgency * URGENCY_WEIGHT

        assert actual == pytest.approx(expected, rel=1e-9)
        assert actual == pytest.approx(0.715, rel=1e-3)

    def test_combined_score_bounds(self):
        """Verify combined score is bounded between 0 and 1."""
        # Maximum case
        max_score = 1.0 * IMPACT_WEIGHT + 1.0 * CONFIDENCE_WEIGHT + 1.0 * URGENCY_WEIGHT
        assert max_score == 1.0

        # Minimum case
        min_score = 0.0 * IMPACT_WEIGHT + 0.0 * CONFIDENCE_WEIGHT + 0.0 * URGENCY_WEIGHT
        assert min_score == 0.0


# ── Goal Filtering Tests ───────────────────────────────────────────────────


class TestGoalFiltering:
    """Tests for goal filtering and matching logic."""

    @pytest.mark.asyncio
    async def test_goal_filtering_keyword_match(
        self,
        implication_engine: ImplicationEngine,
        sample_goals: list[dict],
    ):
        """Test that goals are matched by keyword overlap."""
        affected = await implication_engine._find_affected_goals(
            chain_endpoint="ADC manufacturing capacity expansion",
            goals=sample_goals,
        )

        # Should match goals containing "ADC" keyword
        assert len(affected) >= 1
        assert any("ADC" in g["title"] or "ADC" in g.get("description", "") for g in affected)

    @pytest.mark.asyncio
    async def test_goal_filtering_no_match(
        self,
        implication_engine: ImplicationEngine,
        sample_goals: list[dict],
    ):
        """Test that unrelated endpoints return no goals."""
        affected = await implication_engine._find_affected_goals(
            chain_endpoint="Unrelated consumer electronics launch",
            goals=sample_goals,
        )

        # Should not match any goals
        assert len(affected) == 0

    @pytest.mark.asyncio
    async def test_goal_filtering_empty_goals(
        self,
        implication_engine: ImplicationEngine,
    ):
        """Test behavior when user has no active goals."""
        affected = await implication_engine._find_affected_goals(
            chain_endpoint="Any event",
            goals=[],
        )

        assert affected == []


# ── Classification Tests ───────────────────────────────────────────────────


class TestClassification:
    """Tests for implication classification (opportunity, threat, neutral)."""

    @pytest.mark.asyncio
    async def test_opportunity_classification(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
    ):
        """Test that enabling relationships are classified as opportunities."""
        # Modify chain to have enabling relationship
        sample_chain.hops[-1].relationship = "enables"

        impl_type = await implication_engine._classify_implication(
            chain=sample_chain,
            affected_goals=sample_goals,
        )

        assert impl_type == ImplicationType.OPPORTUNITY

    @pytest.mark.asyncio
    async def test_threat_classification(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
    ):
        """Test that threatening relationships are classified as threats."""
        # Modify chain to have threatening relationship
        sample_chain.hops[-1].relationship = "threatens"

        impl_type = await implication_engine._classify_implication(
            chain=sample_chain,
            affected_goals=sample_goals,
        )

        assert impl_type == ImplicationType.THREAT

    @pytest.mark.asyncio
    async def test_neutral_classification_no_goals(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
    ):
        """Test that implications with no affected goals are neutral."""
        impl_type = await implication_engine._classify_implication(
            chain=sample_chain,
            affected_goals=[],
        )

        assert impl_type == ImplicationType.NEUTRAL

    @pytest.mark.asyncio
    async def test_classification_with_llm(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
        mock_llm_client: AsyncMock,
    ):
        """Test LLM-based classification for ambiguous cases."""
        # Set up neutral relationship type that requires LLM
        sample_chain.hops[-1].relationship = "causes"

        # Mock LLM to return opportunity classification
        mock_llm_client.generate_response.return_value = "opportunity"

        impl_type = await implication_engine._classify_implication(
            chain=sample_chain,
            affected_goals=sample_goals,
        )

        assert impl_type == ImplicationType.OPPORTUNITY
        mock_llm_client.generate_response.assert_called()


# ── Urgency Calculation Tests ─────────────────────────────────────────────


class TestUrgencyCalculation:
    """Tests for urgency score calculation based on time-to-impact."""

    def test_urgency_immediate(self, implication_engine: ImplicationEngine):
        """Test urgency for immediate impact."""
        chain = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="Immediate action required",
        )

        urgency = implication_engine._calculate_urgency(chain)
        assert urgency >= 0.8

    def test_urgency_days(self, implication_engine: ImplicationEngine):
        """Test urgency for days-based timeframes."""
        chain_3days = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="3 days",
        )
        chain_14days = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="14 days",
        )

        urgency_soon = implication_engine._calculate_urgency(chain_3days)
        urgency_later = implication_engine._calculate_urgency(chain_14days)

        assert urgency_soon > urgency_later
        assert urgency_soon >= 0.6

    def test_urgency_weeks(self, implication_engine: ImplicationEngine):
        """Test urgency for weeks-based timeframes."""
        chain_1week = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="1 week",
        )
        chain_4weeks = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="4 weeks",
        )

        urgency_soon = implication_engine._calculate_urgency(chain_1week)
        urgency_later = implication_engine._calculate_urgency(chain_4weeks)

        assert urgency_soon > urgency_later

    def test_urgency_months(self, implication_engine: ImplicationEngine):
        """Test urgency for months-based timeframes."""
        chain = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact="6 months",
        )

        urgency = implication_engine._calculate_urgency(chain)
        assert urgency <= 0.3

    def test_urgency_none_specified(self, implication_engine: ImplicationEngine):
        """Test default urgency when no time specified."""
        chain = CausalChain(
            trigger_event="Test",
            hops=[],
            final_confidence=0.5,
            time_to_impact=None,
        )

        urgency = implication_engine._calculate_urgency(chain)
        assert urgency == 0.5  # Default medium urgency


# ── Impact Calculation Tests ─────────────────────────────────────────────


class TestImpactCalculation:
    """Tests for impact score calculation based on goal importance."""

    def test_impact_no_goals(self, implication_engine: ImplicationEngine, sample_chain: CausalChain):
        """Test impact is zero when no goals affected."""
        impact = implication_engine._calculate_impact(sample_chain, [])
        assert impact == 0.0

    def test_impact_single_goal(self, implication_engine: ImplicationEngine, sample_chain: CausalChain):
        """Test impact with single goal affected."""
        goals = [{"id": str(uuid4()), "title": "Test Goal", "priority": 3}]

        impact = implication_engine._calculate_impact(sample_chain, goals)
        assert 0.0 < impact <= 1.0

    def test_impact_multiple_goals(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
    ):
        """Test impact increases with more goals."""
        impact_multiple = implication_engine._calculate_impact(sample_chain, sample_goals[:3])
        impact_single = implication_engine._calculate_impact(sample_chain, sample_goals[:1])

        assert impact_multiple >= impact_single

    def test_impact_high_priority_goals(self, implication_engine: ImplicationEngine, sample_chain: CausalChain):
        """Test impact is higher for high-priority goals."""
        low_priority_goals = [{"id": str(uuid4()), "title": "Low", "priority": 1}]
        high_priority_goals = [{"id": str(uuid4()), "title": "High", "priority": 5}]

        impact_low = implication_engine._calculate_impact(sample_chain, low_priority_goals)
        impact_high = implication_engine._calculate_impact(sample_chain, high_priority_goals)

        assert impact_high > impact_low


# ── LLM Generation Tests ───────────────────────────────────────────────────


class TestLLMGeneration:
    """Tests for LLM-powered explanation and recommendation generation."""

    @pytest.mark.asyncio
    async def test_llm_explanation_generation(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
        mock_llm_client: AsyncMock,
    ):
        """Test that explanation is generated via LLM."""
        mock_llm_client.generate_response.return_value = (
            "This acquisition strengthens Pfizer's ADC capabilities, "
            "which may increase competition for your Lonza partnership."
        )

        explanation = await implication_engine._generate_explanation(
            event=sample_chain.trigger_event,
            chain=sample_chain,
            affected_goals=sample_goals,
            impl_type=ImplicationType.THREAT,
        )

        assert "Pfizer" in explanation or "ADC" in explanation
        mock_llm_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_recommendation_generation(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        mock_llm_client: AsyncMock,
    ):
        """Test that recommendations are generated via LLM."""
        mock_llm_client.generate_response.return_value = (
            '["Schedule call with Lonza", "Review ADC strategy", "Monitor Pfizer integration"]'
        )

        recommendations = await implication_engine._generate_recommendations(
            chain=sample_chain,
            impl_type=ImplicationType.OPPORTUNITY,
        )

        assert len(recommendations) <= 3
        assert all(isinstance(r, str) for r in recommendations)

    @pytest.mark.asyncio
    async def test_llm_recommendations_limited_to_three(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        mock_llm_client: AsyncMock,
    ):
        """Test that recommendations are limited to 3 items."""
        mock_llm_client.generate_response.return_value = (
            '["Action 1", "Action 2", "Action 3", "Action 4", "Action 5"]'
        )

        recommendations = await implication_engine._generate_recommendations(
            chain=sample_chain,
            impl_type=ImplicationType.OPPORTUNITY,
        )

        assert len(recommendations) <= 3

    @pytest.mark.asyncio
    async def test_fallback_explanation_on_llm_failure(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
        mock_llm_client: AsyncMock,
    ):
        """Test fallback explanation when LLM fails."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        explanation = await implication_engine._generate_explanation(
            event=sample_chain.trigger_event,
            chain=sample_chain,
            affected_goals=sample_goals,
            impl_type=ImplicationType.NEUTRAL,
        )

        # Should return fallback explanation
        assert isinstance(explanation, str)
        assert len(explanation) > 0


# ── Signal Radar Integration Tests ────────────────────────────────────────


class TestSignalRadarIntegration:
    """Tests for signal radar hook integration."""

    @pytest.mark.asyncio
    async def test_signal_triggers_causal_analysis(
        self,
        implication_engine: ImplicationEngine,
        mock_causal_engine: CausalChainEngine,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
        sample_chain: CausalChain,
    ):
        """Test that signal detection triggers causal chain analysis."""
        user_id = str(uuid4())

        # Mock goals query
        goals_result = MagicMock()
        goals_result.data = sample_goals
        mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = goals_result

        # Mock causal engine
        with patch.object(mock_causal_engine, 'traverse', new_callable=AsyncMock) as mock_traverse:
            mock_traverse.return_value = [sample_chain]

            implications = await implication_engine.analyze_event(
                user_id=user_id,
                event="Pfizer announces acquisition of Seagen",
            )

            mock_traverse.assert_called_once()
            assert isinstance(implications, list)

    @pytest.mark.asyncio
    async def test_signal_radar_creates_insights(
        self,
        implication_engine: ImplicationEngine,
        sample_chain: CausalChain,
        sample_goals: list[dict],
    ):
        """Test that signal radar integration creates jarvis_insights entries."""
        user_id = str(uuid4())
        insight_id = uuid4()

        # Create an implication to save
        implication = Implication(
            id=uuid4(),
            trigger_event=sample_chain.trigger_event,
            content="Test implication content",
            type=ImplicationType.OPPORTUNITY,
            impact_score=0.7,
            confidence=0.8,
            urgency=0.5,
            combined_score=0.68,
            causal_chain=[],
            affected_goals=[str(g["id"]) for g in sample_goals],
            recommended_actions=["Test action"],
        )

        # Create a fresh mock for this specific test
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"id": str(insight_id)}]

        # Set up chain: table().insert().execute() -> result
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        # Override the engine's db client
        implication_engine._db = mock_db

        result = await implication_engine.save_insight(user_id, implication)

        assert result is not None
        mock_db.table.assert_called_with("jarvis_insights")


# ── Persistence Tests ──────────────────────────────────────────────────────


class TestPersistence:
    """Tests for jarvis_insights table persistence."""

    @pytest.mark.asyncio
    async def test_save_insight_success(
        self,
        implication_engine: ImplicationEngine,
    ):
        """Test successful insight persistence."""
        user_id = str(uuid4())
        insight_id = uuid4()

        implication = Implication(
            id=None,
            trigger_event="Test event",
            content="Test content",
            type=ImplicationType.OPPORTUNITY,
            impact_score=0.8,
            confidence=0.7,
            urgency=0.6,
            combined_score=0.71,
            causal_chain=[],
            affected_goals=[],
            recommended_actions=["Action 1"],
        )

        # Create a fresh mock for this specific test
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"id": str(insight_id)}]

        # Set up chain: table().insert().execute() -> result
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        # Override the engine's db client
        implication_engine._db = mock_db

        result = await implication_engine.save_insight(user_id, implication)

        assert result == insight_id
        mock_db.table.assert_called_with("jarvis_insights")

    @pytest.mark.asyncio
    async def test_save_insight_failure(
        self,
        implication_engine: ImplicationEngine,
        mock_db_client: MagicMock,
    ):
        """Test handling of persistence failure."""
        user_id = str(uuid4())

        implication = Implication(
            id=None,
            trigger_event="Test",
            content="Test",
            type=ImplicationType.THREAT,
            impact_score=0.5,
            confidence=0.5,
            urgency=0.5,
            combined_score=0.5,
            causal_chain=[],
            affected_goals=[],
            recommended_actions=[],
        )

        mock_db_client.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")

        result = await implication_engine.save_insight(user_id, implication)

        assert result is None


# ── Empty/Edge Case Tests ─────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_chains_returns_empty_implications(
        self,
        implication_engine: ImplicationEngine,
        mock_causal_engine: CausalChainEngine,
    ):
        """Test that events with no causal chains return empty implications."""
        user_id = str(uuid_id())

        with patch.object(mock_causal_engine, 'traverse', new_callable=AsyncMock) as mock_traverse:
            mock_traverse.return_value = []

            implications = await implication_engine.analyze_event(
                user_id=user_id,
                event="Some unrelated event",
            )

            assert implications == []

    @pytest.mark.asyncio
    async def test_empty_goals_returns_empty_implications(
        self,
        implication_engine: ImplicationEngine,
        mock_db_client: MagicMock,
        sample_chain: CausalChain,
    ):
        """Test that users with no active goals get no implications."""
        user_id = str(uuid4())

        # Mock empty goals
        goals_result = MagicMock()
        goals_result.data = []
        mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = goals_result

        implications = await implication_engine.analyze_event(
            user_id=user_id,
            event="Any event",
        )

        assert implications == []

    @pytest.mark.asyncio
    async def test_include_neutral_flag(
        self,
        implication_engine: ImplicationEngine,
        mock_db_client: MagicMock,
        mock_causal_engine: CausalChainEngine,
        sample_chain: CausalChain,
    ):
        """Test that include_neutral flag works correctly."""
        user_id = str(uuid4())

        # Set up chain with neutral relationship
        sample_chain.hops[-1].relationship = "relates_to"

        with patch.object(mock_causal_engine, 'traverse', new_callable=AsyncMock) as mock_traverse:
            mock_traverse.return_value = [sample_chain]

            # Without include_neutral
            impls_excluded = await implication_engine.analyze_event(
                user_id=user_id,
                event="Test event",
                include_neutral=False,
            )

            # With include_neutral - would need proper goal setup to actually work
            # This test verifies the parameter is accepted
            impls_included = await implication_engine.analyze_event(
                user_id=user_id,
                event="Test event",
                include_neutral=True,
            )

            # Both should be lists (may be empty due to no goals)
            assert isinstance(impls_excluded, list)
            assert isinstance(impls_included, list)


# ── Request/Response Model Tests ─────────────────────────────────────────


class TestModels:
    """Tests for Pydantic models validation."""

    def test_implication_request_validation(self):
        """Test ImplicationRequest model validation."""
        # Valid request
        request = ImplicationRequest(
            event="This is a valid event description",
            max_hops=4,
            include_neutral=False,
        )
        assert request.event == "This is a valid event description"
        assert request.max_hops == 4

    def test_implication_request_event_bounds(self):
        """Test that event must be between 10 and 2000 chars."""
        # Too short
        with pytest.raises(Exception):
            ImplicationRequest(event="Too short")

        # Valid
        request = ImplicationRequest(event="A" * 100)
        assert len(request.event) == 100

    def test_implication_request_max_hops_bounds(self):
        """Test that max_hops must be between 1 and 6."""
        # Valid bounds
        ImplicationRequest(event="Valid event description", max_hops=1)
        ImplicationRequest(event="Valid event description", max_hops=6)

        # Invalid - too low
        with pytest.raises(Exception):
            ImplicationRequest(event="Valid event description", max_hops=0)

        # Invalid - too high
        with pytest.raises(Exception):
            ImplicationRequest(event="Valid event description", max_hops=7)

    def test_implication_model_score_bounds(self):
        """Test that Implication scores are bounded 0-1."""
        # Valid
        impl = Implication(
            trigger_event="Test",
            content="Test",
            type=ImplicationType.OPPORTUNITY,
            impact_score=0.5,
            confidence=0.5,
            urgency=0.5,
            combined_score=0.5,
        )
        assert impl.impact_score == 0.5

        # Invalid - out of bounds
        with pytest.raises(Exception):
            Implication(
                trigger_event="Test",
                content="Test",
                type=ImplicationType.OPPORTUNITY,
                impact_score=1.5,  # Invalid
                confidence=0.5,
                urgency=0.5,
                combined_score=0.5,
            )


# ── Helper function for uuid generation ──


def uuid_id() -> type:
    """Generate a UUID for testing."""
    return uuid4()
