"""Pydantic models for the Predictive Processing Engine (US-707).

This module defines data structures for ARIA's predictive processing system,
enabling constant prediction generation, error detection, and learning from
prediction errors (surprises) following predictive processing cognitive theory.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PredictionCategory(str, Enum):
    """Category of prediction for the predictive processing engine.

    These are the types of predictions ARIA makes to anticipate user needs
    and external events.
    """

    USER_ACTION = "user_action"  # User will do something
    USER_NEED = "user_need"  # User will need something
    EXTERNAL_EVENT = "external_event"  # External world event
    TOPIC_SHIFT = "topic_shift"  # Conversation topic change
    DEAL_OUTCOME = "deal_outcome"  # Deal will close/fail
    MEETING_OUTCOME = "meeting_outcome"  # Meeting outcome prediction
    TIMING = "timing"  # When something will happen


class PredictionStatus(str, Enum):
    """Current status of a prediction in the predictive processing system.

    Tracks the lifecycle from active prediction through validation.
    """

    ACTIVE = "active"  # Currently being tracked
    VALIDATED_CORRECT = "validated_correct"  # Confirmed correct
    VALIDATED_INCORRECT = "validated_incorrect"  # Confirmed wrong
    EXPIRED = "expired"  # Time passed without resolution
    SUPERSEDED = "superseded"  # Replaced by newer prediction


# ==============================================================================
# CORE PREDICTION MODELS
# ==============================================================================


class Prediction(BaseModel):
    """A prediction made by ARIA's predictive processing system.

    Represents a single prediction about what will happen, including
    confidence, context, and tracking for validation.
    """

    id: UUID | None = Field(None, description="Unique identifier for this prediction")
    user_id: UUID | str = Field(..., description="User this prediction belongs to")
    prediction_type: PredictionCategory = Field(
        ...,
        description="Category of prediction (user_action, deal_outcome, etc.)",
    )
    prediction_text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language prediction statement",
    )
    predicted_outcome: str | None = Field(
        None,
        description="Expected outcome if prediction is correct",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence level (0-1)",
    )
    context: dict[str, Any] | None = Field(
        None,
        description="Context when prediction was made",
    )
    source_conversation_id: UUID | str | None = Field(
        None,
        description="Conversation where prediction originated",
    )
    expected_resolution_date: datetime | None = Field(
        None,
        description="When we expect to know if prediction was correct",
    )
    status: PredictionStatus = Field(
        default=PredictionStatus.ACTIVE,
        description="Current status of the prediction",
    )
    surprise_level: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="How surprising the prediction error was (0-1)",
    )
    learning_signal: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Signal for learning (-1 = ignore, +1 = attend)",
    )
    created_at: datetime | None = Field(None, description="When prediction was created")
    validated_at: datetime | None = Field(None, description="When prediction was validated")


class PredictionError(BaseModel):
    """A detected prediction error (surprise).

    When a prediction fails to match reality, this captures the error
    for learning and attention allocation.
    """

    prediction_id: UUID | str = Field(..., description="ID of the failed prediction")
    prediction_type: PredictionCategory = Field(
        ...,
        description="Type of the failed prediction",
    )
    predicted_value: str = Field(
        ...,
        description="What was predicted to happen",
    )
    actual_value: str = Field(
        ...,
        description="What actually happened",
    )
    surprise_level: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How surprising this error was (0-1)",
    )
    learning_signal: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Learning signal for attention (-1 to +1)",
    )
    affected_entities: list[str] = Field(
        default_factory=list,
        description="Entities involved in the prediction error",
    )
    related_goal_ids: list[str] = Field(
        default_factory=list,
        description="Goals that may be affected by this error",
    )
    created_at: datetime | None = Field(
        None,
        description="When this error was detected",
    )


class CalibrationData(BaseModel):
    """Calibration statistics for a prediction type.

    Tracks how well-calibrated ARIA's confidence is for a given
    prediction type and confidence bucket.
    """

    prediction_type: PredictionCategory = Field(
        ...,
        description="Type of prediction",
    )
    confidence_bucket: float = Field(
        ...,
        ge=0.1,
        le=1.0,
        description="Confidence bucket (0.1, 0.2, ..., 1.0)",
    )
    total_predictions: int = Field(
        ...,
        ge=0,
        description="Total predictions in this bucket",
    )
    correct_predictions: int = Field(
        ...,
        ge=0,
        description="Correct predictions in this bucket",
    )
    accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Actual accuracy rate",
    )
    is_calibrated: bool = Field(
        ...,
        description="Whether accuracy is within 10% of confidence bucket",
    )


# ==============================================================================
# CONTEXT GATHERING MODELS
# ==============================================================================


class RecentConversation(BaseModel):
    """Summary of a recent conversation for prediction context."""

    id: UUID | str = Field(..., description="Conversation ID")
    summary: str = Field(..., description="Brief summary of conversation")
    topics: list[str] = Field(default_factory=list, description="Topics discussed")
    entities: list[str] = Field(default_factory=list, description="Entities mentioned")
    created_at: datetime | None = Field(None, description="When conversation occurred")


class UpcomingMeeting(BaseModel):
    """Upcoming meeting for prediction context."""

    id: UUID | str = Field(..., description="Meeting ID")
    title: str = Field(..., description="Meeting title")
    start_time: datetime = Field(..., description="When meeting starts")
    attendees: list[str] = Field(default_factory=list, description="Attendee names/emails")
    related_goal_id: str | None = Field(None, description="Related goal if any")


class RecentSignal(BaseModel):
    """Recent market or intelligence signal for prediction context."""

    id: UUID | str = Field(..., description="Signal ID")
    signal_type: str = Field(..., description="Type of signal")
    content: str = Field(..., description="Signal content")
    entities: list[str] = Field(default_factory=list, description="Related entities")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to user")
    created_at: datetime | None = Field(None, description="When signal was detected")


class RecentLeadActivity(BaseModel):
    """Recent lead activity for prediction context."""

    lead_id: str = Field(..., description="Lead ID")
    lead_name: str = Field(..., description="Lead name")
    activity_type: str = Field(..., description="Type of activity")
    activity_description: str = Field(..., description="Description of activity")
    created_at: datetime | None = Field(None, description="When activity occurred")


class EpisodicMemory(BaseModel):
    """Recent episodic memory for prediction context."""

    id: UUID | str = Field(..., description="Memory ID")
    content: str = Field(..., description="Memory content")
    entities: list[str] = Field(default_factory=list, description="Entities in memory")
    importance: float = Field(..., ge=0.0, le=1.0, description="Memory importance")
    created_at: datetime | None = Field(None, description="When memory was created")


class PredictionContext(BaseModel):
    """Aggregated context for generating predictions.

    Gathers all relevant context from multiple sources to enable
    informed prediction generation.
    """

    recent_conversations: list[RecentConversation] = Field(
        default_factory=list,
        description="Recent conversation summaries",
    )
    active_goals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="User's active goals",
    )
    upcoming_meetings: list[UpcomingMeeting] = Field(
        default_factory=list,
        description="Upcoming meetings (next 48h)",
    )
    recent_market_signals: list[RecentSignal] = Field(
        default_factory=list,
        description="Recent intelligence signals (7 days)",
    )
    recent_lead_activity: list[RecentLeadActivity] = Field(
        default_factory=list,
        description="Recent lead activities",
    )
    recent_episodic_memories: list[EpisodicMemory] = Field(
        default_factory=list,
        description="Recent episodic memories",
    )


# ==============================================================================
# REQUEST/RESPONSE MODELS
# ==============================================================================


class ActivePredictionsResponse(BaseModel):
    """Response containing active predictions for a user."""

    predictions: list[Prediction] = Field(
        default_factory=list,
        description="Active predictions sorted by expected resolution",
    )
    total_count: int = Field(
        ...,
        ge=0,
        description="Total number of active predictions",
    )
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count of predictions by type",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to retrieve predictions in milliseconds",
    )


class CalibrationResponse(BaseModel):
    """Response containing calibration statistics."""

    calibration_data: list[CalibrationData] = Field(
        default_factory=list,
        description="Calibration statistics by type and confidence bucket",
    )
    overall_accuracy: float | None = Field(
        None,
        description="Overall prediction accuracy across all types",
    )
    total_predictions: int = Field(
        ...,
        ge=0,
        description="Total validated predictions",
    )
    is_well_calibrated: bool = Field(
        ...,
        description="Whether overall calibration is within acceptable range",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to compute calibration in milliseconds",
    )


class PredictionErrorDetectionResponse(BaseModel):
    """Response from prediction error detection."""

    errors_detected: list[PredictionError] = Field(
        default_factory=list,
        description="Prediction errors (surprises) detected",
    )
    predictions_validated: int = Field(
        ...,
        ge=0,
        description="Number of predictions validated (correct or incorrect)",
    )
    predictions_expired: int = Field(
        ...,
        ge=0,
        description="Number of predictions that expired without resolution",
    )
    salience_boosted_entities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Entities that had salience boosted due to surprises",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken for error detection in milliseconds",
    )


class GeneratePredictionsRequest(BaseModel):
    """Request to generate new predictions."""

    context: PredictionContext | None = Field(
        None,
        description="Optional pre-gathered context",
    )
    prediction_types: list[PredictionCategory] | None = Field(
        None,
        description="Specific types to generate (all if None)",
    )
    max_predictions: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum predictions to generate",
    )


class GeneratePredictionsResponse(BaseModel):
    """Response from prediction generation."""

    predictions: list[Prediction] = Field(
        default_factory=list,
        description="Generated predictions",
    )
    context_used: PredictionContext | None = Field(
        None,
        description="Context used for generation",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to generate predictions in milliseconds",
    )
