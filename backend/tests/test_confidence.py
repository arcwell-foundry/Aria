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


def test_apply_corroboration_boost_single_source() -> None:
    """Single corroborating source should add configured boost."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()

    result = scorer.apply_corroboration_boost(
        base_confidence=0.75,
        corroborating_source_count=1,
    )

    # 0.75 + 0.10 = 0.85
    assert result == pytest.approx(0.85)


def test_apply_corroboration_boost_multiple_sources() -> None:
    """Multiple corroborating sources should stack boosts."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()

    result = scorer.apply_corroboration_boost(
        base_confidence=0.70,
        corroborating_source_count=3,
    )

    # 0.70 + (3 * 0.10) = 1.00, capped at 0.99
    assert result == pytest.approx(0.99)


def test_apply_corroboration_boost_respects_max() -> None:
    """Boost should not exceed max confidence."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()

    result = scorer.apply_corroboration_boost(
        base_confidence=0.95,
        corroborating_source_count=2,
    )

    # 0.95 + 0.20 = 1.15, capped at 0.99
    assert result == pytest.approx(0.99)


def test_apply_corroboration_boost_zero_sources() -> None:
    """Zero corroborating sources should return base confidence unchanged."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()

    result = scorer.apply_corroboration_boost(
        base_confidence=0.75,
        corroborating_source_count=0,
    )

    assert result == pytest.approx(0.75)


def test_get_effective_confidence_combines_decay_and_boost() -> None:
    """Effective confidence should apply both decay and corroboration."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Fact: 60 days old, never confirmed, 2 corroborating sources
    result = scorer.get_effective_confidence(
        original_confidence=0.75,
        created_at=now - timedelta(days=60),
        last_confirmed_at=None,
        corroborating_source_count=2,
        as_of=now,
    )

    # Decay: 0.75 - ((60-7) * 0.05/30) = 0.75 - 0.0883 = 0.6617
    # Then boost: 0.6617 + 0.20 = 0.8617
    expected_after_decay = 0.75 - ((60 - 7) * 0.05 / 30)
    expected = expected_after_decay + 0.20
    assert result == pytest.approx(expected, rel=0.01)


def test_get_effective_confidence_decay_then_boost_order() -> None:
    """Decay should be applied before boost."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Old fact with high original confidence, boosted by corroboration
    result = scorer.get_effective_confidence(
        original_confidence=0.95,
        created_at=now - timedelta(days=180),
        last_confirmed_at=None,
        corroborating_source_count=1,
        as_of=now,
    )

    # Decay from 0.95 over 173 effective days, then +0.10 boost
    decay = (180 - 7) * 0.05 / 30
    decayed = max(0.3, 0.95 - decay)  # Floored at min
    boosted = min(0.99, decayed + 0.10)
    assert result == pytest.approx(boosted, rel=0.01)


def test_meets_threshold_returns_true_above_threshold() -> None:
    """Confidence above threshold should pass."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    result = scorer.meets_threshold(
        original_confidence=0.95,
        created_at=now - timedelta(days=7),
        last_confirmed_at=None,
        corroborating_source_count=0,
        threshold=0.5,
        as_of=now,
    )

    assert result is True


def test_meets_threshold_returns_false_below_threshold() -> None:
    """Confidence below threshold should fail."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    now = datetime.now(UTC)

    # Very old fact with low original confidence
    result = scorer.meets_threshold(
        original_confidence=0.40,
        created_at=now - timedelta(days=365),
        last_confirmed_at=None,
        corroborating_source_count=0,
        threshold=0.5,
        as_of=now,
    )

    # Should be at floor (0.3), which is below 0.5 threshold
    assert result is False


def test_meets_threshold_uses_default_threshold() -> None:
    """Default threshold should come from settings."""
    from src.memory.confidence import ConfidenceScorer

    scorer = ConfidenceScorer(min_threshold=0.4)
    now = datetime.now(UTC)

    # Fact at exactly the floor should pass default threshold check
    result = scorer.meets_threshold(
        original_confidence=0.45,
        created_at=now - timedelta(days=365),
        last_confirmed_at=None,
        corroborating_source_count=0,
        threshold=None,  # Use default (min_threshold)
        as_of=now,
    )

    # At floor of 0.4, equal to threshold, should pass
    assert result is True
