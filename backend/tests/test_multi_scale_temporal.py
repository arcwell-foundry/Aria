"""Tests for Multi-Scale Temporal Reasoner (US-709).

Tests cover:
- Conflict detection between time scales
- Context gathering per scale
- Reconciliation advice generation
- API endpoint integration
"""

import pytest

from src.intelligence.temporal.models import (
    CrossScaleImpact,
    ScaleContext,
    ScaleRecommendation,
    TemporalAnalysis,
    TemporalAnalysisRequest,
    TemporalConflict,
    TimeScale,
)
from src.intelligence.temporal.multi_scale import (
    MultiScaleTemporalReasoner,
    SCALE_INDICATORS,
    TIME_SCALE_CONFIG,
)


class TestTimeScaleModels:
    """Tests for TimeScale enum and related models."""

    def test_time_scale_values(self):
        """Test that TimeScale has expected values."""
        assert TimeScale.IMMEDIATE.value == "immediate"
        assert TimeScale.TACTICAL.value == "tactical"
        assert TimeScale.STRATEGIC.value == "strategic"
        assert TimeScale.VISIONARY.value == "visionary"

    def test_scale_context_creation(self):
        """Test ScaleContext model creation."""
        context = ScaleContext(
            scale=TimeScale.TACTICAL,
            active_concerns=["Meeting with Lonza", "Proposal deadline"],
            decisions_pending=["Approve budget"],
            goals=["Close Q1 deals"],
            constraints=["Limited bandwidth"],
            calendar_events=[{"title": "Meeting"}],
        )

        assert context.scale == TimeScale.TACTICAL
        assert len(context.active_concerns) == 2
        assert len(context.decisions_pending) == 1
        assert context.calendar_events is not None

    def test_cross_scale_impact_creation(self):
        """Test CrossScaleImpact model creation."""
        impact = CrossScaleImpact(
            source_scale=TimeScale.IMMEDIATE,
            target_scale=TimeScale.VISIONARY,
            source_decision="Accept quick deal",
            impact_on_target="May limit long-term strategic options",
            alignment="conflicts",
            explanation="Immediate revenue comes at cost of flexibility",
            confidence=0.8,
        )

        assert impact.source_scale == TimeScale.IMMEDIATE
        assert impact.target_scale == TimeScale.VISIONARY
        assert impact.alignment == "conflicts"
        assert 0.0 <= impact.confidence <= 1.0

    def test_temporal_conflict_creation(self):
        """Test TemporalConflict model creation."""
        conflict = TemporalConflict(
            conflict_type="short_vs_long",
            scales_involved=[TimeScale.IMMEDIATE, TimeScale.VISIONARY],
            description="Short-term gain conflicts with long-term strategy",
            severity=0.7,
            potential_resolutions=["Phased approach", "Modified terms"],
        )

        assert conflict.conflict_type == "short_vs_long"
        assert len(conflict.scales_involved) == 2
        assert 0.0 <= conflict.severity <= 1.0
        assert len(conflict.potential_resolutions) == 2

    def test_scale_recommendation_creation(self):
        """Test ScaleRecommendation model creation."""
        rec = ScaleRecommendation(
            scale=TimeScale.STRATEGIC,
            recommendation="Negotiate flexibility clauses",
            rationale="Preserves options for quarterly objectives",
            priority=0.8,
        )

        assert rec.scale == TimeScale.STRATEGIC
        assert rec.priority >= 0.0 and rec.priority <= 1.0

    def test_temporal_analysis_request_validation(self):
        """Test TemporalAnalysisRequest validation."""
        # Valid request
        request = TemporalAnalysisRequest(
            decision="Should I accept the Lonza deal now or wait?",
            context_hint="Budget is tight this quarter",
            include_reconciliation=True,
        )
        assert request.decision is not None
        assert len(request.decision) >= 10

        # Test min length validation
        with pytest.raises(Exception):  # Pydantic ValidationError
            TemporalAnalysisRequest(decision="Too short")

    def test_temporal_analysis_creation(self):
        """Test TemporalAnalysis model creation."""
        analysis = TemporalAnalysis(
            decision="Accept the deal",
            primary_scale=TimeScale.TACTICAL,
            scale_contexts={"tactical": ScaleContext(scale=TimeScale.TACTICAL)},
            cross_scale_impacts=[],
            conflicts=[],
            recommendations={},
            reconciliation_advice=None,
            overall_alignment="aligned",
            confidence=0.8,
            processing_time_ms=150.0,
        )

        assert analysis.primary_scale == TimeScale.TACTICAL
        assert analysis.overall_alignment == "aligned"
        assert len(analysis.conflicts) == 0


class TestMultiScaleTemporalReasoner:
    """Tests for MultiScaleTemporalReasoner class."""

    @pytest.fixture
    def reasoner(self):
        """Create a reasoner instance for testing."""
        # Use mock LLM and DB clients
        return MultiScaleTemporalReasoner(
            llm_client=None,  # Will use default
            db_client=None,  # Will use default
        )

    def test_scale_config_exists(self):
        """Test that scale configuration is defined."""
        assert TimeScale.IMMEDIATE in TIME_SCALE_CONFIG
        assert TimeScale.TACTICAL in TIME_SCALE_CONFIG
        assert TimeScale.STRATEGIC in TIME_SCALE_CONFIG
        assert TimeScale.VISIONARY in TIME_SCALE_CONFIG

        # Check config structure
        for scale, config in TIME_SCALE_CONFIG.items():
            assert "days" in config
            assert "description" in config
            assert "context_sources" in config

    def test_scale_indicators_exist(self):
        """Test that scale indicators are defined."""
        for scale in TimeScale:
            assert scale in SCALE_INDICATORS
            assert len(SCALE_INDICATORS[scale]) > 0

    @pytest.mark.asyncio
    async def test_determine_primary_scale_immediate(self, reasoner):
        """Test detection of immediate scale decisions."""
        # These should be detected as immediate
        immediate_decisions = [
            "Should I call them right now?",
            "I need to decide by end of day",
            "This is urgent, what should I do?",
        ]

        for decision in immediate_decisions:
            scale = await reasoner._determine_primary_scale(decision)
            assert scale == TimeScale.IMMEDIATE, f"Failed for: {decision}"

    @pytest.mark.asyncio
    async def test_determine_primary_scale_tactical(self, reasoner):
        """Test detection of tactical scale decisions."""
        tactical_decisions = [
            "Should I schedule this for next week?",
            "I need to plan for this week",
            "What should I do before the meeting on Friday?",
        ]

        for decision in tactical_decisions:
            scale = await reasoner._determine_primary_scale(decision)
            assert scale == TimeScale.TACTICAL, f"Failed for: {decision}"

    @pytest.mark.asyncio
    async def test_determine_primary_scale_strategic(self, reasoner):
        """Test detection of strategic scale decisions."""
        strategic_decisions = [
            "What's our Q3 strategy?",
            "Should I commit to this quarterly target?",
            "How does this affect our pipeline this quarter?",
        ]

        for decision in strategic_decisions:
            scale = await reasoner._determine_primary_scale(decision)
            assert scale == TimeScale.STRATEGIC, f"Failed for: {decision}"

    @pytest.mark.asyncio
    async def test_determine_primary_scale_visionary(self, reasoner):
        """Test detection of visionary scale decisions."""
        visionary_decisions = [
            "What's our long term vision?",
            "How should we position for next year?",
            "What are the market trends we should consider?",
        ]

        for decision in visionary_decisions:
            scale = await reasoner._determine_primary_scale(decision)
            assert scale == TimeScale.VISIONARY, f"Failed for: {decision}"

    def test_detect_conflicts_short_vs_long(self, reasoner):
        """Test detection of short-term vs long-term conflicts."""
        # Create impacts with short-term support and long-term conflict
        impacts = [
            CrossScaleImpact(
                source_scale=TimeScale.IMMEDIATE,
                target_scale=TimeScale.IMMEDIATE,
                source_decision="Accept deal",
                impact_on_target="Quick revenue",
                alignment="supports",
                explanation="Immediate cash flow",
                confidence=0.8,
            ),
            CrossScaleImpact(
                source_scale=TimeScale.IMMEDIATE,
                target_scale=TimeScale.VISIONARY,
                source_decision="Accept deal",
                impact_on_target="Limits future options",
                alignment="conflicts",
                explanation="Locks in terms that prevent future pivots",
                confidence=0.7,
            ),
        ]

        conflicts = reasoner._detect_conflicts(impacts)

        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "short_vs_long"
        assert conflicts[0].severity >= 0.5

    def test_detect_conflicts_aligned(self, reasoner):
        """Test that aligned decisions have no conflicts."""
        # Create impacts that are all supportive
        impacts = [
            CrossScaleImpact(
                source_scale=TimeScale.TACTICAL,
                target_scale=TimeScale.IMMEDIATE,
                source_decision="Invest in training",
                impact_on_target="Better skills",
                alignment="supports",
                explanation="Immediate skill improvement",
                confidence=0.8,
            ),
            CrossScaleImpact(
                source_scale=TimeScale.TACTICAL,
                target_scale=TimeScale.STRATEGIC,
                source_decision="Invest in training",
                impact_on_target="Stronger team",
                alignment="supports",
                explanation="Long-term capability building",
                confidence=0.8,
            ),
        ]

        conflicts = reasoner._detect_conflicts(impacts)

        # No conflicts should be detected for aligned impacts
        assert len(conflicts) == 0

    def test_determine_alignment(self, reasoner):
        """Test overall alignment determination."""
        # No conflicts = aligned
        assert reasoner._determine_alignment([]) == "aligned"

        # Low severity = needs reconciliation
        low_severity = [
            TemporalConflict(
                conflict_type="minor",
                scales_involved=[TimeScale.TACTICAL],
                description="Minor tension",
                severity=0.3,
            )
        ]
        assert reasoner._determine_alignment(low_severity) == "needs_reconciliation"

        # High severity = conflicted
        high_severity = [
            TemporalConflict(
                conflict_type="major",
                scales_involved=[TimeScale.IMMEDIATE, TimeScale.VISIONARY],
                description="Major conflict",
                severity=0.8,
            )
        ]
        assert reasoner._determine_alignment(high_severity) == "conflicted"

    def test_build_context_summary(self, reasoner):
        """Test context summary building for LLM."""
        contexts = {
            TimeScale.IMMEDIATE: ScaleContext(
                scale=TimeScale.IMMEDIATE,
                active_concerns=["Meeting at 2pm", "Urgent email"],
                goals=["Clear inbox"],
                constraints=["Limited time"],
            ),
            TimeScale.TACTICAL: ScaleContext(
                scale=TimeScale.TACTICAL,
                active_concerns=["Weekly planning"],
                goals=["Close 2 deals"],
                constraints=["Team capacity"],
            ),
        }

        summary = reasoner._build_context_summary(contexts)

        assert "IMMEDIATE" in summary
        assert "TACTICAL" in summary
        assert "Meeting at 2pm" in summary

    def test_calculate_confidence(self, reasoner):
        """Test confidence calculation."""
        # High confidence with rich context
        rich_contexts = {
            TimeScale.IMMEDIATE: ScaleContext(
                scale=TimeScale.IMMEDIATE,
                active_concerns=["A", "B", "C"],
                goals=["Goal 1"],
                constraints=["Constraint"],
            ),
            TimeScale.TACTICAL: ScaleContext(
                scale=TimeScale.TACTICAL,
                active_concerns=["D", "E"],
                goals=["Goal 2"],
                constraints=["Constraint 2"],
            ),
        }

        high_confidence = reasoner._calculate_confidence(
            scale_contexts=rich_contexts,
            impacts=[
                CrossScaleImpact(
                    source_scale=TimeScale.IMMEDIATE,
                    target_scale=TimeScale.TACTICAL,
                    source_decision="Test",
                    impact_on_target="Test",
                    alignment="supports",
                    explanation="Test",
                    confidence=0.9,
                )
            ],
            conflicts=[],
        )

        # Low confidence with sparse context
        sparse_contexts = {
            TimeScale.IMMEDIATE: ScaleContext(
                scale=TimeScale.IMMEDIATE,
                active_concerns=[],
                goals=[],
                constraints=[],
            ),
        }

        low_confidence = reasoner._calculate_confidence(
            scale_contexts=sparse_contexts,
            impacts=[],
            conflicts=[
                TemporalConflict(
                    conflict_type="test",
                    scales_involved=[TimeScale.IMMEDIATE],
                    description="Test",
                    severity=0.9,
                )
            ],
        )

        assert high_confidence > low_confidence
        assert 0.0 <= high_confidence <= 1.0
        assert 0.0 <= low_confidence <= 1.0


class TestTemporalAnalysisRequest:
    """Tests for TemporalAnalysisRequest model."""

    def test_valid_request(self):
        """Test creating a valid request."""
        request = TemporalAnalysisRequest(
            decision="Should I accept the Lonza deal now or wait for better terms?",
            context_hint="We need revenue this quarter",
            include_reconciliation=True,
        )

        assert request.decision == "Should I accept the Lonza deal now or wait for better terms?"
        assert request.context_hint == "We need revenue this quarter"
        assert request.include_reconciliation is True

    def test_min_decision_length(self):
        """Test that decision must be at least 10 characters."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            TemporalAnalysisRequest(decision="Too short")

    def test_max_decision_length(self):
        """Test that decision must be at most 2000 characters."""
        long_decision = "x" * 2001
        with pytest.raises(Exception):  # Pydantic ValidationError
            TemporalAnalysisRequest(decision=long_decision)

    def test_default_values(self):
        """Test default values for optional fields."""
        request = TemporalAnalysisRequest(
            decision="This is a valid decision text"
        )

        assert request.context_hint is None
        assert request.include_reconciliation is True


class TestIntegrationPatterns:
    """Tests for integration patterns and edge cases."""

    @pytest.fixture
    def reasoner(self):
        """Create a reasoner instance for testing."""
        return MultiScaleTemporalReasoner()

    def test_scale_context_can_have_empty_lists(self):
        """Test that ScaleContext handles empty lists gracefully."""
        context = ScaleContext(
            scale=TimeScale.VISIONARY,
            active_concerns=[],
            decisions_pending=[],
            goals=[],
            constraints=[],
        )

        assert context.active_concerns == []
        assert context.calendar_events is None

    def test_impact_alignment_values(self):
        """Test that alignment has expected values."""
        valid_alignments = ["supports", "conflicts", "neutral"]

        for alignment in valid_alignments:
            impact = CrossScaleImpact(
                source_scale=TimeScale.IMMEDIATE,
                target_scale=TimeScale.TACTICAL,
                source_decision="Test",
                impact_on_target="Test",
                alignment=alignment,
                explanation="Test",
            )
            assert impact.alignment == alignment

    def test_conflict_can_have_multiple_scales(self):
        """Test that conflicts can involve multiple scales."""
        conflict = TemporalConflict(
            conflict_type="multi_scale",
            scales_involved=[
                TimeScale.IMMEDIATE,
                TimeScale.TACTICAL,
                TimeScale.STRATEGIC,
            ],
            description="Complex multi-scale conflict",
            severity=0.6,
        )

        assert len(conflict.scales_involved) == 3

    def test_temporal_analysis_can_have_multiple_recommendations(self):
        """Test that analysis can have recommendations for all scales."""
        recommendations = {
            TimeScale.IMMEDIATE.value: ScaleRecommendation(
                scale=TimeScale.IMMEDIATE,
                recommendation="Act now",
                rationale="Time-sensitive",
                priority=0.9,
            ),
            TimeScale.TACTICAL.value: ScaleRecommendation(
                scale=TimeScale.TACTICAL,
                recommendation="Plan for week",
                rationale="Weekly goal",
                priority=0.7,
            ),
            TimeScale.STRATEGIC.value: ScaleRecommendation(
                scale=TimeScale.STRATEGIC,
                recommendation="Align with quarter",
                rationale="Quarterly objective",
                priority=0.5,
            ),
            TimeScale.VISIONARY.value: ScaleRecommendation(
                scale=TimeScale.VISIONARY,
                recommendation="Consider long-term",
                rationale="Annual vision",
                priority=0.3,
            ),
        }

        analysis = TemporalAnalysis(
            decision="Complex decision",
            primary_scale=TimeScale.TACTICAL,
            scale_contexts={},
            cross_scale_impacts=[],
            conflicts=[],
            recommendations=recommendations,
            overall_alignment="aligned",
            confidence=0.8,
            processing_time_ms=100.0,
        )

        assert len(analysis.recommendations) == 4


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def reasoner(self):
        """Create a reasoner instance for testing."""
        return MultiScaleTemporalReasoner()

    def test_empty_cross_scale_impacts_no_conflicts(self, reasoner):
        """Test that empty impacts produce no conflicts."""
        conflicts = reasoner._detect_conflicts([])
        assert conflicts == []

    def test_neutral_impacts_no_conflicts(self, reasoner):
        """Test that neutral impacts produce no conflicts."""
        impacts = [
            CrossScaleImpact(
                source_scale=TimeScale.IMMEDIATE,
                target_scale=TimeScale.VISIONARY,
                source_decision="Test",
                impact_on_target="No significant impact",
                alignment="neutral",
                explanation="Neither helps nor hurts",
                confidence=0.5,
            )
        ]

        conflicts = reasoner._detect_conflicts(impacts)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_determine_scale_for_ambiguous_decision(self, reasoner):
        """Test scale determination for ambiguous decisions."""
        # Ambiguous decision should default to tactical via LLM fallback
        # or pattern matching
        scale = await reasoner._determine_primary_scale(
            "I'm thinking about something"
        )
        assert isinstance(scale, TimeScale)

    def test_confidence_bounds(self, reasoner):
        """Test that confidence is always within bounds."""
        # Test with extreme inputs
        confidence = reasoner._calculate_confidence(
            scale_contexts={},
            impacts=[
                CrossScaleImpact(
                    source_scale=TimeScale.IMMEDIATE,
                    target_scale=TimeScale.TACTICAL,
                    source_decision="Test",
                    impact_on_target="Test",
                    alignment="supports",
                    explanation="Test",
                    confidence=0.0,  # Minimum
                )
            ],
            conflicts=[
                TemporalConflict(
                    conflict_type="test",
                    scales_involved=[TimeScale.IMMEDIATE],
                    description="Test",
                    severity=1.0,  # Maximum severity
                )
            ],
        )

        # Should still be within bounds
        assert 0.0 <= confidence <= 1.0
