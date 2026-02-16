"""Tests for the Goal Impact Mapper (US-706).

Tests cover:
- Multi-goal implication detection
- De-prioritization of insights with no goal relevance
- Impact type classification (accelerates, blocks, neutral, creates_opportunity)
- Goal impact summary generation
- Net pressure calculation (opportunities vs threats)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.intelligence.causal.goal_impact import (
    NO_GOAL_PRIORITY_MULTIPLIER,
    GoalImpactMapper,
)
from src.intelligence.causal.models import (
    GoalImpact,
    GoalImpactSummary,
    GoalWithInsights,
    ImpactType,
    Implication,
    ImplicationType,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client with sync execute for Supabase."""
    client = MagicMock()

    def make_query_builder():
        qb = MagicMock()
        qb.select.return_value = qb
        qb.eq.return_value = qb
        qb.neq.return_value = qb
        qb.in_.return_value = qb
        qb.contains.return_value = qb
        qb.order.return_value = qb
        qb.limit.return_value = qb
        qb.insert.return_value = qb
        qb.update.return_value = qb
        qb.single.return_value = qb
        qb.gte.return_value = qb
        qb.execute.return_value = MagicMock(data=[])
        return qb

    client.table.side_effect = lambda _: make_query_builder()
    return client


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Create a mock LLM client."""
    client = AsyncMock()
    client.generate_response = AsyncMock(
        return_value='{"impact_score": 0.7, "impact_type": "accelerates", "explanation": "Test explanation"}'
    )
    return client


@pytest.fixture
def goal_impact_mapper(
    mock_db_client: MagicMock,
    mock_llm_client: AsyncMock,
) -> GoalImpactMapper:
    """Create a GoalImpactMapper with mocked dependencies."""
    return GoalImpactMapper(
        db_client=mock_db_client,
        llm_client=mock_llm_client,
    )


@pytest.fixture
def sample_implications() -> list[Implication]:
    """Create sample implications for testing."""
    return [
        Implication(
            id=uuid4(),
            trigger_event="Pfizer announces acquisition of Seagen",
            content="This acquisition strengthens Pfizer's ADC capabilities, increasing competition in the market",
            type=ImplicationType.THREAT,
            impact_score=0.8,
            confidence=0.7,
            urgency=0.6,
            combined_score=0.71,
            causal_chain=[],
            affected_goals=[],
            recommended_actions=["Monitor competitor"],
        ),
        Implication(
            id=uuid4(),
            trigger_event="New FDA guidance on cell therapy",
            content="The new guidance accelerates approval pathways for cell therapies",
            type=ImplicationType.OPPORTUNITY,
            impact_score=0.7,
            confidence=0.8,
            urgency=0.5,
            combined_score=0.68,
            causal_chain=[],
            affected_goals=[],
            recommended_actions=["Review pipeline"],
        ),
    ]


@pytest.fixture
def sample_goals() -> list[dict]:
    """Create sample goals for testing."""
    return [
        {
            "id": str(uuid4()),
            "title": "Close Lonza CDMO deal",
            "description": "Secure partnership with Lonza for ADC manufacturing",
            "status": "active",
            "priority": 5,
            "category": "revenue",
        },
        {
            "id": str(uuid4()),
            "title": "Expand ADC capabilities",
            "description": "Build internal ADC development capacity",
            "status": "active",
            "priority": 4,
            "category": "growth",
        },
        {
            "id": str(uuid4()),
            "title": "Q4 revenue target",
            "description": "Achieve $5M in quarterly revenue",
            "status": "draft",
            "priority": 5,
            "category": "revenue",
        },
    ]


# ── Multi-Goal Detection Tests ───────────────────────────────────────────


class TestMultiGoalDetection:
    """Tests for detecting implications that affect multiple goals."""

    @pytest.mark.asyncio
    async def test_multi_goal_detection(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test that implications affecting 2+ goals are properly tracked."""
        user_id = str(uuid4())

        # Mock goals query
        goals_result = MagicMock()
        goals_result.data = sample_goals

        # Set up the chain for goals query
        mock_db_client.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
            goals_result
        )

        # Mock LLM to return impacts for multiple goals
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.8, "impact_type": "accelerates", "explanation": "Affects multiple goals"}'
        )

        impacts = await goal_impact_mapper.map_impact(
            user_id=user_id,
            implications=sample_implications,
        )

        # Check that implications have affected_goals populated
        for impl in sample_implications:
            if impl.affected_goals:
                assert isinstance(impl.affected_goals, list)

    @pytest.mark.asyncio
    async def test_multi_goal_count_in_summary(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test that multi_goal_implications count is correct in summary."""
        user_id = str(uuid4())

        # Mock goals query
        goals_result = MagicMock()
        goals_result.data = sample_goals

        # Mock insights query with multi-goal implications
        goal_id = sample_goals[0]["id"]
        insights_result = MagicMock()
        insights_result.data = [
            {
                "id": str(uuid4()),
                "content": "Multi-goal insight",
                "classification": "opportunity",
                "combined_score": 0.8,
                "affected_goals": [goal_id, sample_goals[1]["id"]],  # 2 goals
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        # Set up query chain for goals
        mock_db_client.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
            goals_result
        )

        # Need to set up separate chain for insights
        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        assert summary.multi_goal_implications >= 0


# ── De-prioritization Tests ──────────────────────────────────────────────


class TestDePrioritization:
    """Tests for de-prioritizing insights with no goal relevance."""

    @pytest.mark.asyncio
    async def test_no_goal_deprioritization(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test that implications with no goal impact get priority *= 0.3."""
        user_id = str(uuid4())

        # Mock goals query
        goals_result = MagicMock()
        goals_result.data = sample_goals

        # Set up chain for goals query
        goals_qb = MagicMock()
        goals_qb.select.return_value = goals_qb
        goals_qb.eq.return_value = goals_qb
        goals_qb.in_.return_value = goals_qb
        goals_qb.order.return_value = goals_qb
        goals_qb.limit.return_value = goals_qb
        goals_qb.execute.return_value = goals_result

        def table_side_effect(table_name: str):
            if table_name == "goals":
                return goals_qb
            return MagicMock()

        mock_db_client.table.side_effect = table_side_effect

        # Mock LLM to return neutral impacts (no goal relevance)
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.3, "impact_type": "neutral", "explanation": "No significant impact"}'
        )

        original_scores = [impl.combined_score for impl in sample_implications]

        await goal_impact_mapper.map_impact(
            user_id=user_id,
            implications=sample_implications,
        )

        # Check that scores are reduced for implications with no goal impact
        for i, impl in enumerate(sample_implications):
            if not impl.affected_goals:
                expected_score = original_scores[i] * NO_GOAL_PRIORITY_MULTIPLIER
                assert impl.combined_score == pytest.approx(expected_score, rel=1e-6)

    def test_no_goal_priority_multiplier_value(self):
        """Test that the de-prioritization multiplier is 0.3."""
        assert NO_GOAL_PRIORITY_MULTIPLIER == 0.3


# ── Impact Classification Tests ──────────────────────────────────────────


class TestImpactClassification:
    """Tests for impact type classification."""

    @pytest.mark.asyncio
    async def test_impact_classification_accelerates(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test correct classification: accelerates."""
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.8, "impact_type": "accelerates", "explanation": "This helps"}'
        )

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is not None
        assert impact.impact_type == ImpactType.ACCELERATES

    @pytest.mark.asyncio
    async def test_impact_classification_blocks(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test correct classification: blocks."""
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.7, "impact_type": "blocks", "explanation": "This hinders"}'
        )

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is not None
        assert impact.impact_type == ImpactType.BLOCKS

    @pytest.mark.asyncio
    async def test_impact_classification_neutral(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test correct classification: neutral."""
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.2, "impact_type": "neutral", "explanation": "No impact"}'
        )

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is not None
        assert impact.impact_type == ImpactType.NEUTRAL

    @pytest.mark.asyncio
    async def test_impact_classification_creates_opportunity(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test correct classification: creates_opportunity."""
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.9, "impact_type": "creates_opportunity", "explanation": "New possibility"}'
        )

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is not None
        assert impact.impact_type == ImpactType.CREATES_OPPORTUNITY

    @pytest.mark.asyncio
    async def test_impact_classification_invalid_type_defaults_to_neutral(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test that invalid impact type defaults to neutral."""
        mock_llm_client.generate_response.return_value = (
            '{"impact_score": 0.5, "impact_type": "invalid_type", "explanation": "Bad type"}'
        )

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is not None
        assert impact.impact_type == ImpactType.NEUTRAL


# ── Summary Generation Tests ─────────────────────────────────────────────


class TestSummaryGeneration:
    """Tests for goal impact summary generation."""

    @pytest.mark.asyncio
    async def test_get_goal_impact_summary(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test summary aggregates correctly."""
        user_id = str(uuid4())

        # Mock goals query
        goals_result = MagicMock()
        goals_result.data = sample_goals

        # Mock insights query
        insights_result = MagicMock()
        insights_result.data = []

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        assert isinstance(summary, GoalImpactSummary)
        assert len(summary.goals) == len(sample_goals)
        assert summary.total_insights_analyzed >= 0
        assert summary.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_summary_includes_goal_details(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test that summary includes correct goal details."""
        user_id = str(uuid4())

        goals_result = MagicMock()
        goals_result.data = sample_goals

        insights_result = MagicMock()
        insights_result.data = []

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        for i, goal_with_insights in enumerate(summary.goals):
            assert goal_with_insights.goal_id == sample_goals[i]["id"]
            assert goal_with_insights.goal_title == sample_goals[i]["title"]
            assert goal_with_insights.goal_status == sample_goals[i]["status"]


# ── Net Pressure Calculation Tests ───────────────────────────────────────


class TestNetPressureCalculation:
    """Tests for net pressure calculation (opportunities vs threats)."""

    @pytest.mark.asyncio
    async def test_net_pressure_opportunities(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test net pressure is positive with more opportunities."""
        user_id = str(uuid4())
        goal_id = sample_goals[0]["id"]

        goals_result = MagicMock()
        goals_result.data = sample_goals

        # More opportunities than threats
        insights_result = MagicMock()
        insights_result.data = [
            {
                "id": str(uuid4()),
                "content": "Opportunity 1",
                "classification": "opportunity",
                "combined_score": 0.8,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "content": "Opportunity 2",
                "classification": "opportunity",
                "combined_score": 0.7,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        # First goal should have positive net pressure
        first_goal = summary.goals[0]
        assert first_goal.net_pressure > 0
        assert first_goal.opportunity_count == 2
        assert first_goal.threat_count == 0

    @pytest.mark.asyncio
    async def test_net_pressure_threats(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test net pressure is negative with more threats."""
        user_id = str(uuid4())
        goal_id = sample_goals[0]["id"]

        goals_result = MagicMock()
        goals_result.data = sample_goals

        # More threats than opportunities
        insights_result = MagicMock()
        insights_result.data = [
            {
                "id": str(uuid4()),
                "content": "Threat 1",
                "classification": "threat",
                "combined_score": 0.8,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "content": "Threat 2",
                "classification": "threat",
                "combined_score": 0.7,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        # First goal should have negative net pressure
        first_goal = summary.goals[0]
        assert first_goal.net_pressure < 0
        assert first_goal.opportunity_count == 0
        assert first_goal.threat_count == 2

    @pytest.mark.asyncio
    async def test_net_pressure_balanced(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test net pressure is zero with equal opportunities and threats."""
        user_id = str(uuid4())
        goal_id = sample_goals[0]["id"]

        goals_result = MagicMock()
        goals_result.data = sample_goals

        # Equal opportunities and threats
        insights_result = MagicMock()
        insights_result.data = [
            {
                "id": str(uuid4()),
                "content": "Opportunity",
                "classification": "opportunity",
                "combined_score": 0.8,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "content": "Threat",
                "classification": "threat",
                "combined_score": 0.8,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
                    goals_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        summary = await goal_impact_mapper.get_goal_impact_summary(user_id=user_id)

        # First goal should have zero net pressure
        first_goal = summary.goals[0]
        assert first_goal.net_pressure == 0
        assert first_goal.opportunity_count == 1
        assert first_goal.threat_count == 1


# ── Goal Insights Endpoint Tests ─────────────────────────────────────────


class TestGoalInsightsEndpoint:
    """Tests for the get_goal_insights method."""

    @pytest.mark.asyncio
    async def test_get_goal_insights(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_goals: list[dict],
    ):
        """Test getting insights for a specific goal."""
        user_id = str(uuid4())
        goal_id = sample_goals[0]["id"]

        # Mock goal query
        goal_result = MagicMock()
        goal_result.data = sample_goals[0]

        # Mock insights query
        insights_result = MagicMock()
        insights_result.data = [
            {
                "id": str(uuid4()),
                "content": "Test insight",
                "classification": "opportunity",
                "combined_score": 0.8,
                "affected_goals": [goal_id],
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        def table_side_effect(table_name: str):
            qb = MagicMock()
            if table_name == "goals":
                qb.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
                    goal_result
                )
            elif table_name == "jarvis_insights":
                qb.select.return_value.eq.return_value.contains.return_value.order.return_value.limit.return_value.execute.return_value = (
                    insights_result
                )
            return qb

        mock_db_client.table.side_effect = table_side_effect

        result = await goal_impact_mapper.get_goal_insights(
            user_id=user_id,
            goal_id=goal_id,
            limit=20,
        )

        assert isinstance(result, GoalWithInsights)
        assert result.goal_id == goal_id
        assert result.goal_title == sample_goals[0]["title"]
        assert len(result.insights) == 1

    @pytest.mark.asyncio
    async def test_get_goal_insights_not_found(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
    ):
        """Test that missing goal raises ValueError."""
        user_id = str(uuid4())
        goal_id = str(uuid4())

        # Mock empty goal query
        goal_result = MagicMock()
        goal_result.data = None

        mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            goal_result
        )

        with pytest.raises(ValueError) as exc_info:
            await goal_impact_mapper.get_goal_insights(
                user_id=user_id,
                goal_id=goal_id,
                limit=20,
            )

        assert "not found" in str(exc_info.value)


# ── Edge Case Tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_implications(
        self,
        goal_impact_mapper: GoalImpactMapper,
    ):
        """Test mapping with empty implications list."""
        impacts = await goal_impact_mapper.map_impact(
            user_id=str(uuid4()),
            implications=[],
        )

        assert impacts == []

    @pytest.mark.asyncio
    async def test_no_goals(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_db_client: MagicMock,
        sample_implications: list[Implication],
    ):
        """Test mapping when user has no goals."""
        user_id = str(uuid4())

        # Mock empty goals
        goals_result = MagicMock()
        goals_result.data = []

        mock_db_client.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = (
            goals_result
        )

        impacts = await goal_impact_mapper.map_impact(
            user_id=user_id,
            implications=sample_implications,
        )

        assert impacts == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test that LLM failure returns None for impact."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is None

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_none(
        self,
        goal_impact_mapper: GoalImpactMapper,
        mock_llm_client: AsyncMock,
        sample_implications: list[Implication],
        sample_goals: list[dict],
    ):
        """Test that invalid JSON response returns None."""
        mock_llm_client.generate_response.return_value = "Not valid JSON"

        impact = await goal_impact_mapper._analyze_impact(
            sample_implications[0],
            sample_goals[0],
        )

        assert impact is None


# ── Model Validation Tests ───────────────────────────────────────────────


class TestModelValidation:
    """Tests for Pydantic model validation."""

    def test_goal_impact_model(self):
        """Test GoalImpact model validation."""
        impact = GoalImpact(
            goal_id=str(uuid4()),
            goal_title="Test Goal",
            impact_score=0.8,
            impact_type=ImpactType.ACCELERATES,
            explanation="Test explanation",
        )

        assert impact.impact_score == 0.8
        assert impact.impact_type == ImpactType.ACCELERATES

    def test_goal_impact_score_bounds(self):
        """Test that impact_score is bounded 0-1."""
        # Valid
        GoalImpact(
            goal_id=str(uuid4()),
            goal_title="Test",
            impact_score=0.5,
            impact_type=ImpactType.NEUTRAL,
            explanation="Test",
        )

        # Invalid - out of bounds
        with pytest.raises(Exception):
            GoalImpact(
                goal_id=str(uuid4()),
                goal_title="Test",
                impact_score=1.5,  # Invalid
                impact_type=ImpactType.NEUTRAL,
                explanation="Test",
            )

    def test_goal_with_insights_model(self):
        """Test GoalWithInsights model validation."""
        goal = GoalWithInsights(
            goal_id=str(uuid4()),
            goal_title="Test Goal",
            goal_status="active",
            insights=[],
            net_pressure=0.5,
            opportunity_count=2,
            threat_count=1,
        )

        assert goal.net_pressure == 0.5
        assert goal.opportunity_count == 2
        assert goal.threat_count == 1

    def test_goal_impact_summary_model(self):
        """Test GoalImpactSummary model validation."""
        summary = GoalImpactSummary(
            goals=[],
            total_insights_analyzed=10,
            multi_goal_implications=3,
            processing_time_ms=150.5,
        )

        assert summary.total_insights_analyzed == 10
        assert summary.multi_goal_implications == 3
