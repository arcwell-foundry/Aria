"""Predictive Processing Engine module for ARIA (US-707).

This module implements predictive processing cognitive theory where ARIA
constantly predicts what will happen next and learns from prediction errors
(surprises). Surprise drives attention allocation.

Key components:
- PredictiveEngine: Main engine for prediction generation and error detection
- PredictionContextGatherer: Aggregates context from multiple sources
- PredictionErrorDetector: Detects prediction errors and generates learning signals

Usage:
    from src.intelligence.predictive import PredictiveEngine, PredictionCategory

    engine = PredictiveEngine()
    predictions = await engine.generate_predictions(user_id="123")
    errors = await engine.detect_prediction_errors(user_id="123")
"""

from src.intelligence.predictive.context_gatherer import PredictionContextGatherer
from src.intelligence.predictive.engine import PredictiveEngine
from src.intelligence.predictive.error_detector import PredictionErrorDetector
from src.intelligence.predictive.models import (
    ActivePredictionsResponse,
    CalibrationData,
    CalibrationResponse,
    EpisodicMemory,
    GeneratePredictionsResponse,
    Prediction,
    PredictionCategory,
    PredictionContext,
    PredictionError,
    PredictionErrorDetectionResponse,
    PredictionStatus,
    RecentConversation,
    RecentLeadActivity,
    RecentSignal,
    UpcomingMeeting,
)

__all__ = [
    # Main engine
    "PredictiveEngine",
    "PredictionContextGatherer",
    "PredictionErrorDetector",
    # Models
    "Prediction",
    "PredictionCategory",
    "PredictionStatus",
    "PredictionError",
    "PredictionContext",
    "CalibrationData",
    # Context models
    "RecentConversation",
    "UpcomingMeeting",
    "RecentSignal",
    "RecentLeadActivity",
    "EpisodicMemory",
    # Response models
    "ActivePredictionsResponse",
    "CalibrationResponse",
    "PredictionErrorDetectionResponse",
    "GeneratePredictionsResponse",
]
