"""Tests for confidence scoring module."""

from datetime import UTC, datetime, timedelta

import pytest


def test_calculate_current_confidence_no_decay_within_refresh_window() -> None:
    """Confidence should not decay if last confirmed within refresh window."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact created 60 days ago but confirmed 3 days ago
    result = scorer.calculate_current_confidence(
        original_confidence=0.95,
        created_at=now - timedelta(days=60),
        last_confirmed_at=now - timedelta(days=3),
        as_of=now,
    )

    # Should not decay because confirmation was within 7-day window
    assert result == pytest.approx(0.95)


def test_calculate_current_confidence_decays_over_time() -> None:
    """Confidence should decay based on time since creation/confirmation."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact created 30 days ago, never confirmed
    result = scorer.calculate_current_confidence(
        original_confidence=0.95,
        created_at=now - timedelta(days=30),
        last_confirmed_at=None,
        as_of=now,
    )

    # Should decay: 0.95 - (30 * 0.05/30) = 0.95 - 0.05 = 0.90
    # But decay starts after refresh window (7 days), so effective decay days = 30 - 7 = 23
    expected = 0.95 - (23 * 0.05 / 30)
    assert result == pytest.approx(expected, rel=0.01)


def test_calculate_current_confidence_has_floor() -> None:
    """Confidence should not decay below the minimum threshold."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact created 1 year ago, never confirmed - would decay to negative
    result = scorer.calculate_current_confidence(
        original_confidence=0.60,
        created_at=now - timedelta(days=365),
        last_confirmed_at=None,
        as_of=now,
    )

    # Should be floored at minimum threshold (0.3)
    assert result == pytest.approx(0.3)


def test_calculate_current_confidence_defaults_to_now() -> None:
    """When as_of is not provided, should use current time."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact created just now, should have no decay
    result = scorer.calculate_current_confidence(
        original_confidence=0.90,
        created_at=now,
        last_confirmed_at=None,
    )

    # Within refresh window, no decay
    assert result == pytest.approx(0.90)


def test_calculate_current_confidence_uses_last_confirmed_over_created() -> None:
    """Should use last_confirmed_at as reference when provided."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact created 100 days ago, confirmed 10 days ago
    result = scorer.calculate_current_confidence(
        original_confidence=0.85,
        created_at=now - timedelta(days=100),
        last_confirmed_at=now - timedelta(days=10),
        as_of=now,
    )

    # Decay from 10 days ago, minus 7-day window = 3 effective decay days
    expected = 0.85 - (3 * 0.05 / 30)
    assert result == pytest.approx(expected, rel=0.01)


def test_scorer_custom_parameters() -> None:
    """Scorer should accept custom parameters that override defaults."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer(
        decay_rate_per_day=0.01,  # 1% per day
        min_threshold=0.1,
        refresh_window_days=3,
    )
    now = datetime.now(UTC)

    # Fact created 10 days ago
    result = scorer.calculate_current_confidence(
        original_confidence=0.80,
        created_at=now - timedelta(days=10),
        last_confirmed_at=None,
        as_of=now,
    )

    # 10 days - 3 day window = 7 effective decay days at 1% per day
    expected = 0.80 - (7 * 0.01)
    assert result == pytest.approx(expected, rel=0.01)


def test_scorer_uses_settings_defaults() -> None:
    """Scorer should use settings values when no parameters provided."""
    from src.core.config import settings
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()

    assert scorer.decay_rate_per_day == settings.CONFIDENCE_DECAY_RATE_PER_DAY
    assert scorer.corroboration_boost == settings.CONFIDENCE_CORROBORATION_BOOST
    assert scorer.max_confidence == settings.CONFIDENCE_MAX
    assert scorer.min_threshold == settings.CONFIDENCE_MIN_THRESHOLD
    assert scorer.refresh_window_days == settings.CONFIDENCE_REFRESH_WINDOW_DAYS
