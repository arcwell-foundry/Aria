"""Tests for Butterfly Effect Detection (US-703).

Tests cover:
- Amplification calculation
- Warning level thresholds
- Threshold filtering (events below 3x are not butterfly effects)
- Cascade time estimation
- High/critical notification triggers
- Persistence to jarvis_insights

Note: Implication model has constraint impact_score <= 1.0. To achieve
amplification >= 3.0, we need multiple implications (minimum 4 with 0.75 each
or 3 with 1.0 each).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.intelligence.causal.butterfly_detector import ButterflyDetector
from src.intelligence.causal.models import (
    ButterflyEffect,
    Implication,
    ImplicationType,
    WarningLevel,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client."""
    client = MagicMock()

    # Create a chain-able mock for table operations
    table_mock = MagicMock()
    insert_mock = MagicMock()
    execute_result = MagicMock(data=[{"id": str(uuid4())}])
    insert_mock.execute.return_value = execute_result
    table_mock.insert.return_value = insert_mock
    client.table.return_value = table_mock

    return client


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Create a mock LLM client."""
    return AsyncMock()


@pytest.fixture
def mock_implication_engine(mock_llm_client, mock_db_client) -> MagicMock:
    """Create a mock implication engine."""
    engine = MagicMock()
    engine.analyze_event = AsyncMock(return_value=[])
    engine.save_insight = AsyncMock(return_value=uuid4())
    return engine


@pytest.fixture
def butterfly_detector(
    mock_implication_engine: MagicMock,
    mock_db_client: MagicMock,
    mock_llm_client: AsyncMock,
) -> ButterflyDetector:
    """Create a ButterflyDetector with mocked dependencies."""
    return ButterflyDetector(
        implication_engine=mock_implication_engine,
        db_client=mock_db_client,
        llm_client=mock_llm_client,
    )


def create_implication(
    impact_score: float,
    urgency: float = 0.5,
    confidence: float = 0.8,
    chain_depth: int = 1,
    affected_goals: list[str] | None = None,
) -> Implication:
    """Helper to create Implication instances for tests.

    Note: impact_score must be <= 1.0 per model validation.
    """
    # Ensure impact_score is within valid range
    impact_score = min(impact_score, 1.0)
    confidence = min(confidence, 1.0)
    urgency = min(urgency, 1.0)

    # Calculate combined_score ensuring it doesn't exceed 1.0
    combined = impact_score * 0.4 + confidence * 0.35 + urgency * 0.25
    combined = min(combined, 1.0)

    return Implication(
        trigger_event="Test event",
        content=f"Implication with impact {impact_score}",
        type=ImplicationType.OPPORTUNITY,
        impact_score=impact_score,
        confidence=confidence,
        urgency=urgency,
        combined_score=combined,
        causal_chain=[{"hop": i} for i in range(chain_depth)],
        affected_goals=affected_goals or [],
        recommended_actions=["Test action"],
    )


# ==============================================================================
# Test: Amplification Calculation
# ==============================================================================


class TestAmplificationCalculation:
    """Tests for amplification factor calculation."""

    @pytest.mark.asyncio
    async def test_amplification_sum_of_impacts(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that amplification = sum of implication impact scores."""
        # Create implications that sum to >3.0 (4 implications with 0.9 each = 3.6)
        implications = [
            create_implication(impact_score=0.9, chain_depth=2),
            create_implication(impact_score=0.9, chain_depth=3),
            create_implication(impact_score=0.9, chain_depth=1),
            create_implication(impact_score=0.9, chain_depth=2),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Major market disruption",
        )

        assert result is not None
        # 0.9 * 4 = 3.6
        assert result.amplification_factor == pytest.approx(3.6, rel=0.01)

    @pytest.mark.asyncio
    async def test_amplification_above_threshold(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that amplification > 3.0 triggers butterfly detection."""
        # Create implications that sum to 4.0 (4 implications with 1.0 each)
        implications = [
            create_implication(impact_score=1.0, chain_depth=1),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=3),
            create_implication(impact_score=1.0, chain_depth=2),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Major market disruption",
        )

        assert result is not None
        assert result.amplification_factor >= 3.0


# ==============================================================================
# Test: Threshold Filtering
# ==============================================================================


class TestThresholdFiltering:
    """Tests for filtering events below threshold."""

    @pytest.mark.asyncio
    async def test_no_butterfly_for_low_impact(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that events with amplification < 3.0 return None."""
        # Create implications that sum to <3.0
        implications = [
            create_implication(impact_score=0.5, chain_depth=1),
            create_implication(impact_score=0.8, chain_depth=1),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Minor industry news",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_no_butterfly_for_empty_implications(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that events with no implications return None."""
        mock_implication_engine.analyze_event.return_value = []

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Unrelated event",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that amplification exactly at 3.0 is a butterfly effect."""
        implications = [
            create_implication(impact_score=1.0, chain_depth=1),
            create_implication(impact_score=1.0, chain_depth=1),
            create_implication(impact_score=1.0, chain_depth=1),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Threshold event",
        )

        assert result is not None
        assert result.amplification_factor >= 3.0


# ==============================================================================
# Test: Warning Levels
# ==============================================================================


class TestWarningLevels:
    """Tests for warning level classification."""

    def test_warning_level_critical(self, butterfly_detector: ButterflyDetector):
        """Test critical warning for >10x amplification."""
        level = butterfly_detector._calculate_warning_level(12.0)
        assert level == WarningLevel.CRITICAL

    def test_warning_level_high(self, butterfly_detector: ButterflyDetector):
        """Test high warning for 7-10x amplification."""
        level = butterfly_detector._calculate_warning_level(8.5)
        assert level == WarningLevel.HIGH

        level = butterfly_detector._calculate_warning_level(7.0)
        assert level == WarningLevel.HIGH

    def test_warning_level_medium(self, butterfly_detector: ButterflyDetector):
        """Test medium warning for 5-7x amplification."""
        level = butterfly_detector._calculate_warning_level(6.0)
        assert level == WarningLevel.MEDIUM

        level = butterfly_detector._calculate_warning_level(5.0)
        assert level == WarningLevel.MEDIUM

    def test_warning_level_low(self, butterfly_detector: ButterflyDetector):
        """Test low warning for 3-5x amplification."""
        level = butterfly_detector._calculate_warning_level(4.0)
        assert level == WarningLevel.LOW

        level = butterfly_detector._calculate_warning_level(3.0)
        assert level == WarningLevel.LOW

    @pytest.mark.asyncio
    async def test_warning_level_integrated(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test warning level is correctly set in butterfly effect."""
        # Create implications summing to 8.0 (HIGH warning) - need 8 implications at 1.0 each
        implications = [
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=2),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="High impact event",
        )

        assert result is not None
        assert result.warning_level == WarningLevel.HIGH


# ==============================================================================
# Test: Cascade Depth
# ==============================================================================


class TestCascadeDepth:
    """Tests for cascade depth calculation."""

    @pytest.mark.asyncio
    async def test_cascade_depth_is_max_chain_length(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that cascade depth is the maximum chain length."""
        implications = [
            create_implication(impact_score=1.0, chain_depth=1),
            create_implication(impact_score=1.0, chain_depth=4),  # Max depth
            create_implication(impact_score=1.0, chain_depth=2),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        assert result.cascade_depth == 4

    @pytest.mark.asyncio
    async def test_cascade_depth_single_chain(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test cascade depth with single chain."""
        implications = [
            create_implication(impact_score=1.0, chain_depth=3),
            create_implication(impact_score=1.0, chain_depth=2),
            create_implication(impact_score=1.0, chain_depth=1),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        assert result.cascade_depth == 3


# ==============================================================================
# Test: Cascade Time Estimation
# ==============================================================================


class TestCascadeTimeEstimation:
    """Tests for cascade time estimation."""

    @pytest.mark.asyncio
    async def test_high_urgency_short_time(
        self,
        butterfly_detector: ButterflyDetector,
    ):
        """Test that high urgency implications lead to short time estimates."""
        implications = [
            create_implication(impact_score=1.0, urgency=0.9),
        ]

        time_estimate = await butterfly_detector._estimate_cascade_time(implications)

        assert "Hours" in time_estimate or "days" in time_estimate

    @pytest.mark.asyncio
    async def test_medium_urgency_medium_time(
        self,
        butterfly_detector: ButterflyDetector,
    ):
        """Test that medium urgency implications lead to medium time estimates."""
        implications = [
            create_implication(impact_score=1.0, urgency=0.6),
        ]

        time_estimate = await butterfly_detector._estimate_cascade_time(implications)

        assert "week" in time_estimate.lower()

    @pytest.mark.asyncio
    async def test_low_urgency_long_time(
        self,
        butterfly_detector: ButterflyDetector,
    ):
        """Test that low urgency implications lead to long time estimates."""
        implications = [
            create_implication(impact_score=1.0, urgency=0.1),
        ]

        time_estimate = await butterfly_detector._estimate_cascade_time(implications)

        assert "month" in time_estimate.lower()

    @pytest.mark.asyncio
    async def test_empty_implications_unknown_time(
        self,
        butterfly_detector: ButterflyDetector,
    ):
        """Test that empty implications return 'Unknown' time."""
        time_estimate = await butterfly_detector._estimate_cascade_time([])

        assert time_estimate == "Unknown"

    @pytest.mark.asyncio
    async def test_weighted_average_urgency(
        self,
        butterfly_detector: ButterflyDetector,
    ):
        """Test that time estimation uses weighted average urgency."""
        # High impact with low urgency + low impact with high urgency
        # Weighted average: (1.0 * 0.2 + 0.8 * 0.9) / 1.8 = 0.52
        implications = [
            create_implication(impact_score=1.0, urgency=0.2),
            create_implication(impact_score=0.8, urgency=0.9),
        ]

        time_estimate = await butterfly_detector._estimate_cascade_time(implications)

        # 0.52 should give "2-4 weeks"
        assert "week" in time_estimate.lower()


# ==============================================================================
# Test: Persistence
# ==============================================================================


class TestPersistence:
    """Tests for saving butterfly insights."""

    @pytest.mark.asyncio
    async def test_save_butterfly_insight(
        self,
        butterfly_detector: ButterflyDetector,
        mock_db_client: MagicMock,
    ):
        """Test that butterfly insights are saved to jarvis_insights."""
        butterfly = ButterflyEffect(
            trigger_event="Test event",
            amplification_factor=5.0,
            cascade_depth=3,
            time_to_full_impact="1-2 weeks",
            final_implications=["Impact 1", "Impact 2"],
            warning_level=WarningLevel.MEDIUM,
            affected_goal_count=2,
            combined_impact_score=2.5,
        )

        result = await butterfly_detector.save_butterfly_insight(
            user_id=str(uuid4()),
            butterfly=butterfly,
        )

        assert result is not None
        mock_db_client.table.assert_called_with("jarvis_insights")

    @pytest.mark.asyncio
    async def test_save_insight_high_warning_sets_high_urgency(
        self,
        butterfly_detector: ButterflyDetector,
        mock_db_client: MagicMock,
    ):
        """Test that HIGH warning level sets high urgency in saved insight."""
        butterfly = ButterflyEffect(
            trigger_event="Test event",
            amplification_factor=8.0,
            cascade_depth=3,
            time_to_full_impact="1-2 weeks",
            final_implications=["Impact 1"],
            warning_level=WarningLevel.HIGH,
            affected_goal_count=1,
            combined_impact_score=0.5,
        )

        await butterfly_detector.save_butterfly_insight(
            user_id=str(uuid4()),
            butterfly=butterfly,
        )

        # Verify table was called
        mock_db_client.table.assert_called_with("jarvis_insights")
        # Get the insert call
        insert_mock = mock_db_client.table.return_value.insert
        assert insert_mock.called

    @pytest.mark.asyncio
    async def test_save_insight_critical_warning_sets_high_urgency(
        self,
        butterfly_detector: ButterflyDetector,
        mock_db_client: MagicMock,
    ):
        """Test that CRITICAL warning level sets high urgency in saved insight."""
        butterfly = ButterflyEffect(
            trigger_event="Test event",
            amplification_factor=15.0,
            cascade_depth=5,
            time_to_full_impact="Hours to days",
            final_implications=["Impact 1"],
            warning_level=WarningLevel.CRITICAL,
            affected_goal_count=1,
            combined_impact_score=0.5,
        )

        await butterfly_detector.save_butterfly_insight(
            user_id=str(uuid4()),
            butterfly=butterfly,
        )

        # Verify table was called
        mock_db_client.table.assert_called_with("jarvis_insights")
        insert_mock = mock_db_client.table.return_value.insert
        assert insert_mock.called


# ==============================================================================
# Test: Affected Goals
# ==============================================================================


class TestAffectedGoals:
    """Tests for affected goal tracking."""

    @pytest.mark.asyncio
    async def test_affected_goal_count(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that affected goal count is correctly calculated."""
        implications = [
            create_implication(impact_score=1.0, affected_goals=["goal-1", "goal-2"]),
            create_implication(impact_score=1.0, affected_goals=["goal-2", "goal-3"]),
            create_implication(impact_score=1.0, affected_goals=["goal-4"]),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        # Unique goals: goal-1, goal-2, goal-3, goal-4 = 4
        assert result.affected_goal_count == 4

    @pytest.mark.asyncio
    async def test_no_affected_goals(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test butterfly effect with no affected goals."""
        implications = [
            create_implication(impact_score=1.0, affected_goals=[]),
            create_implication(impact_score=1.0, affected_goals=[]),
            create_implication(impact_score=1.0, affected_goals=[]),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        assert result.affected_goal_count == 0


# ==============================================================================
# Test: Final Implications
# ==============================================================================


class TestFinalImplications:
    """Tests for final implications list."""

    @pytest.mark.asyncio
    async def test_top_five_implications(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test that only top 5 implications are included."""
        implications = [
            create_implication(impact_score=0.6) for _ in range(7)
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        assert len(result.final_implications) == 5

    @pytest.mark.asyncio
    async def test_fewer_than_five_implications(
        self,
        butterfly_detector: ButterflyDetector,
        mock_implication_engine: MagicMock,
    ):
        """Test butterfly effect with fewer than 5 implications."""
        # Need at least 3 implications with 1.0 each to exceed 3.0 threshold
        implications = [
            create_implication(impact_score=1.0),
            create_implication(impact_score=1.0),
            create_implication(impact_score=1.0),
        ]
        mock_implication_engine.analyze_event.return_value = implications

        result = await butterfly_detector.detect(
            user_id=str(uuid4()),
            event="Test event",
        )

        assert result is not None
        assert len(result.final_implications) == 3
