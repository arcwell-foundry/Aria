"""Tests for Time Horizon Analysis (US-705).

Tests cover:
- Correct categorization of FDA regulatory events (BLA, 510(k), PDUFA)
- Correct categorization of budget cycle events
- Correct categorization of clinical trial phase events
- Closing window detection for time-sensitive implications
- LLM fallback for ambiguous timing
"""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.intelligence.temporal import (
    ActionTiming,
    ImplicationWithTiming,
    TimeHorizon,
    TimeHorizonAnalyzer,
    TimeHorizonCategorization,
    TimelineView,
)
from src.intelligence.temporal.time_horizon import (
    DEFAULT_CONFIDENCE,
    HORIZON_THRESHOLDS,
)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def time_horizon_analyzer(mock_llm_client: MagicMock) -> TimeHorizonAnalyzer:
    """Create a TimeHorizonAnalyzer with mock LLM client."""
    return TimeHorizonAnalyzer(llm_client=mock_llm_client)


class TestTimeHorizonEnum:
    """Tests for TimeHorizon enum values."""

    def test_time_horizon_values(self) -> None:
        """Test that TimeHorizon has expected values."""
        assert TimeHorizon.IMMEDIATE.value == "immediate"
        assert TimeHorizon.SHORT_TERM.value == "short_term"
        assert TimeHorizon.MEDIUM_TERM.value == "medium_term"
        assert TimeHorizon.LONG_TERM.value == "long_term"


class TestTimeHorizonCategorization:
    """Tests for TimeHorizonCategorization model."""

    def test_categorization_defaults(self) -> None:
        """Test default values for categorization."""
        cat = TimeHorizonCategorization(
            time_horizon=TimeHorizon.MEDIUM_TERM,
            time_to_impact="2-3 months",
        )
        assert cat.is_closing_window is False
        assert cat.closing_window_reason is None
        assert cat.confidence == 0.7

    def test_categorization_with_closing_window(self) -> None:
        """Test categorization with closing window flag."""
        cat = TimeHorizonCategorization(
            time_horizon=TimeHorizon.IMMEDIATE,
            time_to_impact="2 days",
            is_closing_window=True,
            closing_window_reason="Deadline approaching",
            confidence=0.9,
        )
        assert cat.is_closing_window is True
        assert cat.closing_window_reason == "Deadline approaching"


class TestActionTiming:
    """Tests for ActionTiming model."""

    def test_action_timing_creation(self) -> None:
        """Test creating an ActionTiming instance."""
        today = date.today()
        timing = ActionTiming(
            optimal_action_date=today + timedelta(days=7),
            window_opens=today,
            window_closes=today + timedelta(days=14),
            reason="Test reason",
            confidence=0.8,
        )
        assert timing.confidence == 0.8
        assert "Test reason" in timing.reason


class TestPatternMatching:
    """Tests for pattern matching of life sciences events."""

    @pytest.mark.asyncio
    async def test_fda_bla_submission(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of BLA submission events."""
        implication = {
            "content": "Company plans to submit BLA for their new oncology drug",
            "trigger_event": "BLA submission announced",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.MEDIUM_TERM
        assert "3-6 months" in result.time_to_impact
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_fda_510k_clearance(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of 510(k) clearance events."""
        implication = {
            "content": "The 510(k) submission for the diagnostic device is under review",
            "trigger_event": "510(k) submitted to FDA",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.MEDIUM_TERM
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_pdufa_date(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of PDUFA date events as time-sensitive."""
        implication = {
            "content": "PDUFA date is approaching for the drug approval decision",
            "trigger_event": "PDUFA date announced",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.SHORT_TERM
        assert result.is_closing_window is True
        assert "PDUFA" in result.closing_window_reason

    @pytest.mark.asyncio
    async def test_clinical_trial_phase_3(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of Phase 3 clinical trial events."""
        implication = {
            "content": "The company initiated a phase 3 pivotal trial for their lead asset",
            "trigger_event": "Phase 3 trial started",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.LONG_TERM
        assert "3-4 years" in result.time_to_impact

    @pytest.mark.asyncio
    async def test_clinical_trial_phase_1(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of Phase 1 clinical trial events."""
        implication = {
            "content": "First-in-human phase 1 study has begun enrollment",
            "trigger_event": "Phase 1 trial initiated",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.LONG_TERM
        assert "1-2 years" in result.time_to_impact

    @pytest.mark.asyncio
    async def test_budget_planning_cycle(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test categorization of budget planning events."""
        implication = {
            "content": "Q3 budget planning cycle is starting for next fiscal year",
            "trigger_event": "Budget planning announcement",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.MEDIUM_TERM

    @pytest.mark.asyncio
    async def test_asco_conference_deadline(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test categorization of ASCO conference deadline events."""
        implication = {
            "content": "ASCO abstract deadline is approaching for the conference presentation",
            "trigger_event": "ASCO abstract deadline reminder",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.SHORT_TERM
        assert result.is_closing_window is True

    @pytest.mark.asyncio
    async def test_competitor_response_window(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test categorization of competitor response events."""
        implication = {
            "content": "Competitor market entry expected soon, need competitive response",
            "trigger_event": "Competitor launched new product",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.SHORT_TERM
        assert result.is_closing_window is True


class TestTimeExpressionParsing:
    """Tests for parsing explicit time expressions."""

    @pytest.mark.asyncio
    async def test_days_expression(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test parsing of day-based time expressions."""
        implication = {
            "content": "The decision is expected in 3 days",
            "trigger_event": "Event happened",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.IMMEDIATE
        assert result.is_closing_window is True

    @pytest.mark.asyncio
    async def test_weeks_expression(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test parsing of week-based time expressions."""
        implication = {
            "content": "Impact expected within 2 weeks",
            "trigger_event": "Event happened",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.SHORT_TERM
        assert result.is_closing_window is True

    @pytest.mark.asyncio
    async def test_months_expression(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test parsing of month-based time expressions."""
        implication = {
            "content": "Results expected in 4 months",
            "trigger_event": "Event happened",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.MEDIUM_TERM

    @pytest.mark.asyncio
    async def test_urgent_keywords(self, time_horizon_analyzer: TimeHorizonAnalyzer) -> None:
        """Test parsing of urgent keywords."""
        implication = {
            "content": "This requires immediate attention",
            "trigger_event": "Urgent event",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.IMMEDIATE
        assert result.is_closing_window is True


class TestCategorizeMethod:
    """Tests for the categorize method."""

    @pytest.mark.asyncio
    async def test_categorize_multiple_implications(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test categorizing multiple implications at once."""
        implications = [
            {
                "content": "PDUFA date next week",
                "trigger_event": "PDUFA announced",
                "causal_chain": [],
            },
            {
                "content": "Phase 3 trial started",
                "trigger_event": "Trial initiated",
                "causal_chain": [],
            },
            {
                "content": "Budget planning for next year",
                "trigger_event": "Budget cycle started",
                "causal_chain": [],
            },
        ]

        result = await time_horizon_analyzer.categorize(implications)

        assert TimeHorizon.SHORT_TERM in result
        assert TimeHorizon.LONG_TERM in result
        assert TimeHorizon.MEDIUM_TERM in result

        # Check that all implications are assigned
        total = sum(len(v) for v in result.values())
        assert total == 3

    @pytest.mark.asyncio
    async def test_categorize_empty_list(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test categorizing an empty list."""
        result = await time_horizon_analyzer.categorize([])

        assert len(result[TimeHorizon.IMMEDIATE]) == 0
        assert len(result[TimeHorizon.SHORT_TERM]) == 0
        assert len(result[TimeHorizon.MEDIUM_TERM]) == 0
        assert len(result[TimeHorizon.LONG_TERM]) == 0


class TestRecommendTiming:
    """Tests for the recommend_timing method."""

    @pytest.mark.asyncio
    async def test_recommend_timing_immediate(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test timing recommendation for immediate horizon."""
        implication = {
            "time_horizon": TimeHorizon.IMMEDIATE.value,
            "time_to_impact": "2 days",
        }

        result = await time_horizon_analyzer.recommend_timing(
            user_id="test-user",
            implication=implication,
        )

        assert isinstance(result, ActionTiming)
        assert result.optimal_action_date <= date.today() + timedelta(days=3)
        assert result.confidence >= 0.5

    @pytest.mark.asyncio
    async def test_recommend_timing_with_goal_deadlines(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test timing recommendation respects goal deadlines."""
        today = date.today()
        implication = {
            "time_horizon": TimeHorizon.SHORT_TERM.value,
            "time_to_impact": "1 week",
        }

        # Set deadline within the short-term window (1-2 weeks)
        goal_deadlines = [
            {
                "title": "Sprint Goal",
                "deadline": (today + timedelta(days=7)).isoformat(),
            }
        ]

        result = await time_horizon_analyzer.recommend_timing(
            user_id="test-user",
            implication=implication,
            goal_deadlines=goal_deadlines,
        )

        # Should be scheduled before the deadline (within window)
        # SHORT_TERM window: opens day 3, closes day 14
        # Deadline at day 7, so action should be before day 7
        assert result.optimal_action_date <= today + timedelta(days=7)

    @pytest.mark.asyncio
    async def test_recommend_timing_avoids_busy_days(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test timing recommendation avoids calendar conflicts."""
        today = date.today()
        implication = {
            "time_horizon": TimeHorizon.SHORT_TERM.value,
            "time_to_impact": "1 week",
        }

        # Mark the optimal day as busy
        calendar_events = [
            {"date": (today + timedelta(days=7)).isoformat()}
        ]

        result = await time_horizon_analyzer.recommend_timing(
            user_id="test-user",
            implication=implication,
            calendar_events=calendar_events,
        )

        # Should not be on the busy day
        assert result.optimal_action_date != today + timedelta(days=7)


class TestLLMFallback:
    """Tests for LLM fallback categorization."""

    @pytest.mark.asyncio
    async def test_llm_categorize_ambiguous_event(
        self, time_horizon_analyzer: TimeHorizonAnalyzer, mock_llm_client: MagicMock
    ) -> None:
        """Test LLM categorization for ambiguous events."""
        # Mock LLM response
        mock_llm_client.generate_response.return_value = '''
        {
            "time_horizon": "short_term",
            "time_to_impact": "2-3 weeks",
            "is_closing_window": false,
            "closing_window_reason": null,
            "confidence": 0.75
        }
        '''

        implication = {
            "content": "A new market opportunity has emerged in the APAC region",
            "trigger_event": "Market development announced",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        # Should have called LLM since no pattern matched
        assert mock_llm_client.generate_response.called
        assert result.time_horizon == TimeHorizon.SHORT_TERM

    @pytest.mark.asyncio
    async def test_llm_categorize_failure_fallback(
        self, time_horizon_analyzer: TimeHorizonAnalyzer, mock_llm_client: MagicMock
    ) -> None:
        """Test fallback when LLM categorization fails."""
        # Mock LLM failure
        mock_llm_client.generate_response.side_effect = Exception("API Error")

        implication = {
            "content": "Some ambiguous event with no clear timing indicators",
            "trigger_event": "Event happened",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        # Should fallback to medium_term
        assert result.time_horizon == TimeHorizon.MEDIUM_TERM
        assert result.confidence == DEFAULT_CONFIDENCE

    @pytest.mark.asyncio
    async def test_llm_invalid_json_fallback(
        self, time_horizon_analyzer: TimeHorizonAnalyzer, mock_llm_client: MagicMock
    ) -> None:
        """Test fallback when LLM returns invalid JSON."""
        # Mock invalid JSON response
        mock_llm_client.generate_response.return_value = "This is not valid JSON"

        implication = {
            "content": "Ambiguous content requiring LLM analysis",
            "trigger_event": "Event happened",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon == TimeHorizon.MEDIUM_TERM


class TestTimelineView:
    """Tests for TimelineView model."""

    def test_timeline_view_creation(self) -> None:
        """Test creating a TimelineView instance."""
        view = TimelineView(
            immediate=[],
            short_term=[],
            medium_term=[],
            long_term=[],
            closing_windows=[],
            total_count=0,
            processing_time_ms=100.0,
        )

        assert view.total_count == 0
        assert len(view.immediate) == 0
        assert len(view.closing_windows) == 0

    def test_timeline_view_with_implications(self) -> None:
        """Test TimelineView with implications."""
        impl = ImplicationWithTiming(
            id=None,
            trigger_event="Test event",
            content="Test content",
            classification="opportunity",
            impact_score=0.8,
            confidence=0.9,
            urgency=0.7,
            combined_score=0.8,
            time_horizon=TimeHorizon.SHORT_TERM,
            time_to_impact="2 weeks",
            is_closing_window=True,
        )

        view = TimelineView(
            immediate=[],
            short_term=[impl],
            medium_term=[],
            long_term=[],
            closing_windows=[impl],
            total_count=1,
            processing_time_ms=50.0,
        )

        assert view.total_count == 1
        assert len(view.short_term) == 1
        assert len(view.closing_windows) == 1


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_causal_chain(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test handling of empty causal chain."""
        implication = {
            "content": "PDUFA date next week",
            "trigger_event": "PDUFA announced",
            "causal_chain": [],  # Empty chain
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        # Should still work based on content
        assert result.time_horizon in TimeHorizon

    @pytest.mark.asyncio
    async def test_missing_fields(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test handling of missing fields."""
        implication = {
            "content": "PDUFA date announcement",
            # Missing trigger_event and causal_chain
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        assert result.time_horizon in TimeHorizon

    @pytest.mark.asyncio
    async def test_very_long_content(
        self, time_horizon_analyzer: TimeHorizonAnalyzer
    ) -> None:
        """Test handling of very long content."""
        implication = {
            "content": "PDUFA " + "very long content " * 100,
            "trigger_event": "Event",
            "causal_chain": [],
        }

        result = await time_horizon_analyzer._categorize_single(implication)

        # Should still categorize correctly
        assert result.time_horizon == TimeHorizon.SHORT_TERM

    def test_invalid_time_horizon_value(self) -> None:
        """Test handling of invalid time horizon string."""
        with pytest.raises(ValueError):
            TimeHorizon("invalid_horizon")
