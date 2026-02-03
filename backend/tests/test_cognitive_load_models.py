"""Tests for cognitive load Pydantic models."""

import pytest
from pydantic import ValidationError


def test_load_level_enum_values() -> None:
    """LoadLevel should have low, medium, high, critical values."""
    from src.models.cognitive_load import LoadLevel

    assert LoadLevel.LOW.value == "low"
    assert LoadLevel.MEDIUM.value == "medium"
    assert LoadLevel.HIGH.value == "high"
    assert LoadLevel.CRITICAL.value == "critical"


def test_cognitive_load_state_creation() -> None:
    """CognitiveLoadState should be creatable with valid data."""
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    state = CognitiveLoadState(
        level=LoadLevel.MEDIUM,
        score=0.45,
        factors={
            "message_brevity": 0.5,
            "typo_rate": 0.3,
            "message_velocity": 0.4,
            "calendar_density": 0.6,
            "time_of_day": 0.3,
        },
        recommendation="balanced",
    )

    assert state.level == LoadLevel.MEDIUM
    assert state.score == 0.45
    assert state.recommendation == "balanced"


def test_cognitive_load_state_score_validation() -> None:
    """Score must be between 0 and 1."""
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    with pytest.raises(ValidationError):
        CognitiveLoadState(
            level=LoadLevel.LOW,
            score=1.5,  # Invalid: > 1
            factors={},
            recommendation="detailed",
        )

    with pytest.raises(ValidationError):
        CognitiveLoadState(
            level=LoadLevel.LOW,
            score=-0.1,  # Invalid: < 0
            factors={},
            recommendation="detailed",
        )


def test_cognitive_load_snapshot_response() -> None:
    """CognitiveLoadSnapshotResponse should match DB schema."""
    from datetime import datetime, UTC
    from src.models.cognitive_load import CognitiveLoadSnapshotResponse

    snapshot = CognitiveLoadSnapshotResponse(
        id="123e4567-e89b-12d3-a456-426614174000",
        user_id="user-123",
        load_level="high",
        load_score=0.72,
        factors={"message_brevity": 0.8},
        session_id=None,
        measured_at=datetime.now(UTC),
    )

    assert snapshot.load_level == "high"
    assert snapshot.load_score == 0.72
