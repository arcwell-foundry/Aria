"""Prediction-related Pydantic models for ARIA.

This module contains models for prediction tracking, validation, and calibration.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PredictionType(str, Enum):
    """Type of prediction for categorization and calibration tracking."""

    USER_ACTION = "user_action"
    EXTERNAL_EVENT = "external_event"
    DEAL_OUTCOME = "deal_outcome"
    TIMING = "timing"
    MARKET_SIGNAL = "market_signal"
    LEAD_RESPONSE = "lead_response"
    MEETING_OUTCOME = "meeting_outcome"


class PredictionStatus(str, Enum):
    """Current status of a prediction."""

    PENDING = "pending"
    VALIDATED_CORRECT = "validated_correct"
    VALIDATED_INCORRECT = "validated_incorrect"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PredictionCreate(BaseModel):
    """Request model for creating a new prediction."""

    prediction_type: PredictionType = Field(..., description="Category of the prediction")
    prediction_text: str = Field(
        ..., min_length=1, max_length=2000, description="What is being predicted"
    )
    predicted_outcome: str | None = Field(
        None, max_length=1000, description="Expected result of the prediction"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level (0.0-1.0)")
    context: dict[str, Any] | None = Field(
        None, description="Additional context about the prediction"
    )
    source_conversation_id: str | None = Field(
        None, description="ID of the conversation where prediction was made"
    )
    source_message_id: str | None = Field(
        None, description="ID of the message containing the prediction"
    )
    validation_criteria: str | None = Field(
        None, max_length=1000, description="Criteria for validating the prediction"
    )
    expected_resolution_date: date = Field(
        ..., description="When the prediction should be resolved"
    )


class PredictionUpdate(BaseModel):
    """Request model for updating a prediction."""

    prediction_text: str | None = Field(None, min_length=1, max_length=2000)
    predicted_outcome: str | None = None
    validation_criteria: str | None = Field(None, max_length=1000)
    expected_resolution_date: date | None = None
    status: PredictionStatus | None = None


class PredictionValidate(BaseModel):
    """Request model for validating a prediction outcome."""

    is_correct: bool = Field(..., description="Whether the prediction was correct")
    validation_notes: str | None = Field(
        None, max_length=2000, description="Notes about the validation"
    )


class PredictionResponse(BaseModel):
    """Response model for prediction data."""

    id: str
    user_id: str
    prediction_type: PredictionType
    prediction_text: str
    predicted_outcome: str | None
    confidence: float
    context: dict[str, Any] | None
    source_conversation_id: str | None
    source_message_id: str | None
    validation_criteria: str | None
    expected_resolution_date: date | None
    status: PredictionStatus
    validated_at: datetime | None
    validation_notes: str | None
    created_at: datetime


class CalibrationStatsResponse(BaseModel):
    """Response model for calibration statistics."""

    prediction_type: str = Field(..., description="Type of prediction")
    confidence_bucket: float = Field(..., description="Confidence bucket (0.1, 0.2, ..., 1.0)")
    total_predictions: int = Field(..., description="Total predictions in this bucket")
    correct_predictions: int = Field(..., description="Correct predictions in this bucket")
    accuracy: float = Field(..., description="Actual accuracy (correct/total)")
    is_calibrated: bool = Field(..., description="Whether accuracy is within 10% of confidence")


class AccuracySummaryResponse(BaseModel):
    """Response model for overall prediction accuracy summary."""

    overall_accuracy: float | None = Field(
        None, description="Overall accuracy across all predictions"
    )
    total_predictions: int = Field(..., description="Total validated predictions")
    correct_predictions: int = Field(..., description="Total correct predictions")
    by_type: dict[str, float | None] = Field(..., description="Accuracy by prediction type")


class ExtractedPrediction(BaseModel):
    """Model for a prediction extracted from ARIA's response."""

    content: str = Field(..., description="What is being predicted")
    predicted_outcome: str | None = Field(None, description="Expected result")
    prediction_type: PredictionType = Field(..., description="Category of prediction")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    timeframe_days: int = Field(30, ge=1, le=365, description="Days until expected resolution")
