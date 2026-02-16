"""Time Horizon Analysis for ARIA Phase 7 Jarvis Intelligence.

This module provides temporal analysis capabilities, categorizing
implications by when they'll materialize so users know when to act.

Key components:
- TimeHorizonAnalyzer: Categorizes implications by time horizon
- TimeHorizon: Enum for immediate/short/medium/long term
- ActionTiming: Optimal timing recommendations
- TimelineView: API response for timeline endpoint
- MultiScaleTemporalReasoner: Reasoning across multiple time scales (US-709)
"""

from src.intelligence.temporal.models import (
    ActionTiming,
    CrossScaleImpact,
    ImplicationWithTiming,
    ScaleContext,
    ScaleRecommendation,
    TemporalAnalysis,
    TemporalAnalysisRequest,
    TemporalConflict,
    TimeHorizon,
    TimeHorizonCategorization,
    TimelineRequest,
    TimelineView,
    TimeScale,
)
from src.intelligence.temporal.multi_scale import MultiScaleTemporalReasoner
from src.intelligence.temporal.time_horizon import TimeHorizonAnalyzer

__all__ = [
    # Time horizon analysis
    "TimeHorizonAnalyzer",
    "TimeHorizon",
    "ActionTiming",
    "TimeHorizonCategorization",
    # Request/Response models
    "TimelineRequest",
    "TimelineView",
    "ImplicationWithTiming",
    # Multi-scale temporal reasoning (US-709)
    "MultiScaleTemporalReasoner",
    "TimeScale",
    "ScaleContext",
    "CrossScaleImpact",
    "ScaleRecommendation",
    "TemporalConflict",
    "TemporalAnalysis",
    "TemporalAnalysisRequest",
]
