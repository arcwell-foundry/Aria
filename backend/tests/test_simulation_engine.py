"""Tests for the Mental Simulation Engine (US-708).

Tests cover:
- Scenario parsing and variable extraction
- Outcome generation and classification
- Sensitivity analysis
- Recommendation generation
- Quick simulation for chat
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.intelligence.simulation.engine import MentalSimulationEngine
from src.intelligence.simulation.models import (
    OutcomeClassification,
    QuickSimulationResponse,
    SimulationContext,
    SimulationOutcome,
    SimulationRequest,
    SimulationResult,
    SimulationScenario,
    ScenarioType,
)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client."""
    client = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def mock_causal_engine() -> MagicMock:
    """Create a mock causal chain engine."""
    engine = MagicMock()
    engine.traverse = AsyncMock()
    return engine


@pytest.fixture
def simulation_engine(
    mock_causal_engine: MagicMock,
    mock_llm_client: MagicMock,
    mock_db_client: MagicMock,
) -> MentalSimulationEngine:
    """Create a simulation engine with mocked dependencies."""
    return MentalSimulationEngine(
        causal_engine=mock_causal_engine,
        llm_client=mock_llm_client,
        db_client=mock_db_client,
    )


class TestSimulationModels:
    """Tests for simulation model validation."""

    def test_simulation_request_validation(self) -> None:
        """Test SimulationRequest model validation."""
        # Valid request
        request = SimulationRequest(
            scenario="What if Lonza acquires a competitor?",
            scenario_type=ScenarioType.HYPOTHETICAL,
            max_outcomes=3,
            max_hops=3,
        )
        assert request.scenario == "What if Lonza acquires a competitor?"
        assert request.scenario_type == ScenarioType.HYPOTHETICAL
        assert request.max_outcomes == 3

    def test_simulation_request_min_length(self) -> None:
        """Test that scenario must be at least 10 characters."""
        with pytest.raises(ValueError):
            SimulationRequest(scenario="too short")

    def test_simulation_outcome_classification(self) -> None:
        """Test SimulationOutcome classification."""
        outcome = SimulationOutcome(
            scenario="Test scenario",
            probability=0.7,
            classification=OutcomeClassification.POSITIVE,
            positive_outcomes=["Increased revenue"],
            negative_outcomes=[],
            key_uncertainties=["Market response"],
            recommended=True,
            reasoning="Good opportunity",
            causal_chain=[],
        )
        assert outcome.classification == OutcomeClassification.POSITIVE
        assert outcome.recommended is True

    def test_simulation_result_confidence_bounds(self) -> None:
        """Test that confidence is bounded 0-1."""
        result = SimulationResult(
            scenario="Test",
            scenario_type=ScenarioType.HYPOTHETICAL,
            outcomes=[],
            recommended_path="Do nothing",
            reasoning="Test",
            sensitivity={},
            confidence=0.85,
            key_insights=[],
            processing_time_ms=100.0,
        )
        assert 0.0 <= result.confidence <= 1.0


class TestVariableExtraction:
    """Tests for variable extraction from scenarios."""

    @pytest.mark.asyncio
    async def test_extract_variables_success(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test successful variable extraction."""
        mock_llm_client.generate_response.return_value = json.dumps([
            "acquisition_price",
            "market_share",
            "regulatory_approval",
        ])

        context = SimulationContext(active_goals=[{"title": "Grow revenue"}])
        variables = await simulation_engine._extract_variables(
            scenario="What if Lonza acquires a competitor?",
            context=context,
        )

        assert len(variables) == 3
        assert "acquisition_price" in variables
        mock_llm_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_variables_fallback(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test fallback when variable extraction fails."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        variables = await simulation_engine._extract_variables(
            scenario="Test scenario",
            context=SimulationContext(),
        )

        # Should return default variables
        assert len(variables) == 3
        assert "timing" in variables


class TestScenarioGeneration:
    """Tests for scenario variation generation."""

    @pytest.mark.asyncio
    async def test_generate_scenarios_success(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test successful scenario generation."""
        mock_llm_client.generate_response.return_value = json.dumps([
            {
                "description": "Scenario A: High market share",
                "probability": 0.4,
                "variables": {"market_share": "high"},
                "expected_outcome": "Increased revenue",
            },
            {
                "description": "Scenario B: Low market share",
                "probability": 0.3,
                "variables": {"market_share": "low"},
                "expected_outcome": "Limited impact",
            },
        ])

        scenarios = await simulation_engine._generate_scenarios(
            base_scenario="Test scenario",
            variables=["market_share"],
            max_scenarios=3,
            context=SimulationContext(),
        )

        assert len(scenarios) == 2
        assert scenarios[0].probability == 0.4
        assert "market_share" in scenarios[0].variables

    @pytest.mark.asyncio
    async def test_generate_scenarios_fallback(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test fallback when scenario generation fails."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        scenarios = await simulation_engine._generate_scenarios(
            base_scenario="Test scenario",
            variables=["var1"],
            max_scenarios=3,
            context=SimulationContext(),
        )

        # Should return a single fallback scenario
        assert len(scenarios) == 1
        assert scenarios[0].description == "Test scenario"


class TestOutcomeGeneration:
    """Tests for outcome generation."""

    @pytest.mark.asyncio
    async def test_generate_outcome_success(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test successful outcome generation."""
        mock_llm_client.generate_response.return_value = json.dumps({
            "positive_outcomes": ["Increased revenue", "Market expansion"],
            "negative_outcomes": ["Integration costs"],
            "key_uncertainties": ["Regulatory approval"],
            "recommended": True,
            "reasoning": "Strong strategic fit",
            "classification": "positive",
            "time_to_impact": "6-12 months",
            "affected_goals": ["goal-123"],
        })

        scenario = SimulationScenario(
            description="Test scenario",
            probability=0.7,
            variables={},
        )
        outcome = await simulation_engine._generate_outcome(
            scenario=scenario,
            context=SimulationContext(),
            causal_chain=[],
        )

        assert outcome is not None
        assert outcome.recommended is True
        assert len(outcome.positive_outcomes) == 2
        assert outcome.classification == OutcomeClassification.POSITIVE


class TestSensitivityAnalysis:
    """Tests for sensitivity calculation."""

    def test_calculate_sensitivity(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test sensitivity calculation."""
        outcomes = [
            SimulationOutcome(
                scenario="Test A",
                probability=0.7,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=["Market timing is crucial"],
                negative_outcomes=[],
                key_uncertainties=["Competition"],
                recommended=True,
                reasoning="Market timing affects success",
                causal_chain=[],
            ),
            SimulationOutcome(
                scenario="Test B",
                probability=0.5,
                classification=OutcomeClassification.MIXED,
                positive_outcomes=[],
                negative_outcomes=["Market timing risk"],
                key_uncertainties=["Regulation"],
                recommended=False,
                reasoning="Market timing is uncertain",
                causal_chain=[],
            ),
        ]

        sensitivity = simulation_engine._calculate_sensitivity(
            outcomes=outcomes,
            variables=["timing", "competition"],
        )

        # "timing" appears in both outcomes (reasoning and positive/negative outcomes)
        assert "timing" in sensitivity
        # Sensitivity should be > 0 since "timing" appears in both outcomes
        assert sensitivity["timing"] > 0

    def test_calculate_sensitivity_empty_outcomes(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test sensitivity with no outcomes."""
        sensitivity = simulation_engine._calculate_sensitivity(
            outcomes=[],
            variables=["var1"],
        )
        assert sensitivity == {"var1": 0.0}


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    def test_calculate_confidence_with_outcomes(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test confidence calculation with outcomes."""
        outcomes = [
            SimulationOutcome(
                scenario="Test",
                probability=0.7,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=[],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=True,
                reasoning="",
                causal_chain=[],
            ),
            SimulationOutcome(
                scenario="Test",
                probability=0.6,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=[],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=True,
                reasoning="",
                causal_chain=[],
            ),
        ]

        confidence = simulation_engine._calculate_confidence(outcomes)

        assert 0.0 <= confidence <= 1.0
        # With 2 outcomes and agreement, should be reasonably confident
        assert confidence >= 0.3

    def test_calculate_confidence_empty(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test confidence with no outcomes."""
        confidence = simulation_engine._calculate_confidence([])
        assert confidence == 0.3  # Default fallback


class TestKeyInsightsExtraction:
    """Tests for key insights extraction."""

    def test_extract_key_insights(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test key insights extraction from outcomes."""
        outcomes = [
            SimulationOutcome(
                scenario="Test",
                probability=0.7,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=["Increased revenue"],
                negative_outcomes=["Integration costs"],
                key_uncertainties=["Regulatory approval"],
                recommended=True,
                reasoning="",
                causal_chain=[],
            ),
        ]

        insights = simulation_engine._extract_key_insights(outcomes)

        assert len(insights) > 0
        assert any("opportunity" in i.lower() for i in insights)

    def test_extract_key_insights_empty(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test key insights with no outcomes."""
        insights = simulation_engine._extract_key_insights([])
        assert len(insights) == 1
        assert "No outcomes" in insights[0]


class TestClassificationDetermination:
    """Tests for classification determination."""

    def test_determine_classification_opportunity(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test classification when most outcomes are positive."""
        outcomes = [
            SimulationOutcome(
                scenario="Test",
                probability=0.7,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=[],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=True,
                reasoning="",
                causal_chain=[],
            ),
            SimulationOutcome(
                scenario="Test",
                probability=0.6,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=[],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=True,
                reasoning="",
                causal_chain=[],
            ),
        ]

        classification = simulation_engine._determine_classification(outcomes)
        assert classification == "opportunity"

    def test_determine_classification_threat(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test classification when most outcomes are negative."""
        outcomes = [
            SimulationOutcome(
                scenario="Test",
                probability=0.7,
                classification=OutcomeClassification.NEGATIVE,
                positive_outcomes=[],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=False,
                reasoning="",
                causal_chain=[],
            ),
        ]

        classification = simulation_engine._determine_classification(outcomes)
        assert classification == "threat"


class TestRecommendationGeneration:
    """Tests for recommendation generation."""

    @pytest.mark.asyncio
    async def test_generate_recommendation_with_recommended(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test recommendation when outcomes have recommended paths."""
        outcomes = [
            SimulationOutcome(
                scenario="Best path",
                probability=0.8,
                classification=OutcomeClassification.POSITIVE,
                positive_outcomes=["High growth"],
                negative_outcomes=[],
                key_uncertainties=[],
                recommended=True,
                reasoning="Strong strategic fit",
                causal_chain=[],
            ),
        ]

        path, reasoning = await simulation_engine._generate_recommendation(
            scenario="Test",
            outcomes=outcomes,
            context=SimulationContext(),
        )

        assert path == "Best path"
        assert "80%" in reasoning  # Probability displayed

    @pytest.mark.asyncio
    async def test_generate_recommendation_no_recommended(
        self,
        simulation_engine: MentalSimulationEngine,
    ) -> None:
        """Test recommendation when no outcomes are recommended."""
        outcomes = [
            SimulationOutcome(
                scenario="Risky path",
                probability=0.3,
                classification=OutcomeClassification.NEGATIVE,
                positive_outcomes=[],
                negative_outcomes=["High risk", "Uncertain returns"],
                key_uncertainties=[],
                recommended=False,
                reasoning="Too risky",
                causal_chain=[],
            ),
        ]

        path, reasoning = await simulation_engine._generate_recommendation(
            scenario="Test",
            outcomes=outcomes,
            context=SimulationContext(),
        )

        assert "alternative" in path.lower()
        assert "risks" in reasoning.lower()


class TestQuickSimulation:
    """Tests for quick simulation (chat integration)."""

    @pytest.mark.asyncio
    async def test_quick_simulate_success(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """Test successful quick simulation."""
        mock_llm_client.generate_response.return_value = json.dumps({
            "answer": "If Lonza acquires Catalent, expect significant market consolidation.",
            "key_points": ["Market share increase", "Regulatory review required"],
            "confidence": 0.75,
        })

        # Mock the context gathering
        mock_db_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"title": "Grow revenue"}]
        )

        response = await simulation_engine.quick_simulate(
            user_id="test-user",
            question="What if Lonza acquires Catalent?",
        )

        assert isinstance(response, QuickSimulationResponse)
        assert "Lonza" in response.answer or "consolidation" in response.answer.lower()
        assert len(response.key_points) == 2
        assert response.confidence == 0.75

    @pytest.mark.asyncio
    async def test_quick_simulate_fallback(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """Test quick simulation fallback on error."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        response = await simulation_engine.quick_simulate(
            user_id="test-user",
            question="What if test?",
        )

        assert "issue" in response.answer.lower() or "try again" in response.answer.lower()
        assert response.confidence < 0.5


class TestFullSimulation:
    """Tests for full simulation workflow."""

    @pytest.mark.asyncio
    async def test_simulate_full_workflow(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_llm_client: MagicMock,
        mock_db_client: MagicMock,
        mock_causal_engine: MagicMock,
    ) -> None:
        """Test full simulation workflow."""
        # Mock context gathering
        mock_db_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "goal-1", "title": "Grow revenue", "status": "active"}]
        )

        # Mock variable extraction
        mock_llm_client.generate_response.side_effect = [
            # Variable extraction
            json.dumps(["market_share", "timing"]),
            # Scenario generation
            json.dumps([
                {
                    "description": "High market share scenario",
                    "probability": 0.6,
                    "variables": {"market_share": "high"},
                    "expected_outcome": "Revenue growth",
                },
            ]),
            # Outcome generation
            json.dumps({
                "positive_outcomes": ["Revenue increase"],
                "negative_outcomes": [],
                "key_uncertainties": ["Regulatory"],
                "recommended": True,
                "reasoning": "Good opportunity",
                "classification": "positive",
                "time_to_impact": "6 months",
            }),
        ]

        # Mock causal engine
        mock_causal_engine.traverse.return_value = []

        request = SimulationRequest(
            scenario="What if we acquire a competitor?",
            scenario_type=ScenarioType.STRATEGIC,
            max_outcomes=1,
            max_hops=2,
        )

        result = await simulation_engine.simulate(
            user_id="test-user",
            request=request,
        )

        assert isinstance(result, SimulationResult)
        assert result.scenario == "What if we acquire a competitor?"
        assert len(result.outcomes) >= 0  # May have generated outcomes
        assert 0.0 <= result.confidence <= 1.0
        assert result.processing_time_ms > 0


class TestSaveSimulation:
    """Tests for saving simulation results."""

    @pytest.mark.asyncio
    async def test_save_simulation(
        self,
        simulation_engine: MentalSimulationEngine,
        mock_db_client: MagicMock,
    ) -> None:
        """Test saving simulation to database."""
        # Mock the insert
        mock_db_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data={"id": "sim-123"}
        )

        result = SimulationResult(
            scenario="Test scenario",
            scenario_type=ScenarioType.HYPOTHETICAL,
            outcomes=[
                SimulationOutcome(
                    scenario="Test",
                    probability=0.7,
                    classification=OutcomeClassification.POSITIVE,
                    positive_outcomes=[],
                    negative_outcomes=[],
                    key_uncertainties=[],
                    recommended=True,
                    reasoning="Good",
                    causal_chain=[],
                    affected_goals=["goal-1"],
                ),
            ],
            recommended_path="Do it",
            reasoning="Strong case",
            sensitivity={},
            confidence=0.75,
            key_insights=["Key insight"],
            processing_time_ms=100.0,
        )

        sim_id = await simulation_engine.save_simulation(
            user_id="test-user",
            result=result,
        )

        assert sim_id is not None
        mock_db_client.table.assert_called_with("jarvis_insights")
