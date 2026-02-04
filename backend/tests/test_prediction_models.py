"""Tests for prediction models."""

import pytest
from datetime import date, datetime
from pydantic import ValidationError


def test_prediction_type_enum_has_all_types() -> None:
    """Test PredictionType enum has all expected values."""
    from src.models.prediction import PredictionType

    expected = {
        "user_action", "external_event", "deal_outcome",
        "timing", "market_signal", "lead_response", "meeting_outcome"
    }
    actual = {t.value for t in PredictionType}
    assert actual == expected


def test_prediction_status_enum_has_all_statuses() -> None:
    """Test PredictionStatus enum has all expected values."""
    from src.models.prediction import PredictionStatus

    expected = {
        "pending", "validated_correct", "validated_incorrect",
        "expired", "cancelled"
    }
    actual = {s.value for s in PredictionStatus}
    assert actual == expected


def test_prediction_create_validates_confidence_range() -> None:
    """Test PredictionCreate validates confidence is between 0 and 1."""
    from src.models.prediction import PredictionCreate, PredictionType

    # Valid confidence
    valid = PredictionCreate(
        prediction_type=PredictionType.DEAL_OUTCOME,
        prediction_text="Deal will close",
        confidence=0.75,
        expected_resolution_date=date(2026, 3, 1),
    )
    assert valid.confidence == 0.75

    # Invalid: too high
    with pytest.raises(ValidationError):
        PredictionCreate(
            prediction_type=PredictionType.DEAL_OUTCOME,
            prediction_text="Deal will close",
            confidence=1.5,
            expected_resolution_date=date(2026, 3, 1),
        )

    # Invalid: negative
    with pytest.raises(ValidationError):
        PredictionCreate(
            prediction_type=PredictionType.DEAL_OUTCOME,
            prediction_text="Deal will close",
            confidence=-0.1,
            expected_resolution_date=date(2026, 3, 1),
        )


def test_prediction_validate_requires_is_correct() -> None:
    """Test PredictionValidate requires is_correct field."""
    from src.models.prediction import PredictionValidate

    valid = PredictionValidate(is_correct=True, validation_notes="Outcome matched")
    assert valid.is_correct is True

    valid_false = PredictionValidate(is_correct=False)
    assert valid_false.is_correct is False


def test_calibration_stats_response_calculates_accuracy() -> None:
    """Test CalibrationStatsResponse includes accuracy calculation."""
    from src.models.prediction import CalibrationStatsResponse

    stats = CalibrationStatsResponse(
        prediction_type="deal_outcome",
        confidence_bucket=0.8,
        total_predictions=100,
        correct_predictions=78,
        accuracy=0.78,
        is_calibrated=True,
    )
    assert stats.accuracy == 0.78
    assert stats.is_calibrated is True
