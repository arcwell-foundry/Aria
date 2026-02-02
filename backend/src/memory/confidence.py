"""Confidence scoring system for semantic facts.

Implements:
- Source-based initial confidence (via SOURCE_CONFIDENCE)
- Time-based confidence decay
- Corroboration boosts
- Configurable thresholds

Confidence is calculated dynamically at query time, not stored.
This allows retroactive changes to decay rates without data migration.
"""

import logging
from datetime import UTC, datetime

from src.core.config import settings

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Calculates current confidence scores for semantic facts.

    Confidence decays over time if not refreshed, but can be boosted
    by corroborating sources. All calculations use configurable
    parameters from settings.
    """

    def __init__(
        self,
        decay_rate_per_day: float | None = None,
        corroboration_boost: float | None = None,
        max_confidence: float | None = None,
        min_threshold: float | None = None,
        refresh_window_days: int | None = None,
    ) -> None:
        """Initialize scorer with optional parameter overrides.

        Args:
            decay_rate_per_day: Daily decay rate. Defaults to settings.
            corroboration_boost: Boost per corroborating source. Defaults to settings.
            max_confidence: Maximum confidence after boosts. Defaults to settings.
            min_threshold: Minimum threshold (floor). Defaults to settings.
            refresh_window_days: Days before decay starts. Defaults to settings.
        """
        self.decay_rate_per_day = (
            decay_rate_per_day
            if decay_rate_per_day is not None
            else settings.CONFIDENCE_DECAY_RATE_PER_DAY
        )
        self.corroboration_boost = (
            corroboration_boost
            if corroboration_boost is not None
            else settings.CONFIDENCE_CORROBORATION_BOOST
        )
        self.max_confidence = (
            max_confidence if max_confidence is not None else settings.CONFIDENCE_MAX
        )
        self.min_threshold = (
            min_threshold if min_threshold is not None else settings.CONFIDENCE_MIN_THRESHOLD
        )
        self.refresh_window_days = (
            refresh_window_days
            if refresh_window_days is not None
            else settings.CONFIDENCE_REFRESH_WINDOW_DAYS
        )

    def calculate_current_confidence(
        self,
        original_confidence: float,
        created_at: datetime,
        last_confirmed_at: datetime | None = None,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate current confidence with time-based decay.

        Decay starts after the refresh window period. If the fact was
        confirmed within the refresh window, no decay is applied.

        Args:
            original_confidence: The initial confidence score (0.0-1.0).
            created_at: When the fact was created.
            last_confirmed_at: When the fact was last confirmed/refreshed.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Current confidence score, floored at min_threshold.
        """
        check_time = as_of or datetime.now(UTC)

        # Determine the reference point for decay
        reference_time = last_confirmed_at or created_at

        # Calculate days since reference
        days_since_reference = (check_time - reference_time).total_seconds() / 86400

        # No decay within refresh window
        if days_since_reference <= self.refresh_window_days:
            return original_confidence

        # Calculate effective decay days (time beyond refresh window)
        effective_decay_days = days_since_reference - self.refresh_window_days

        # Apply decay
        decay = effective_decay_days * self.decay_rate_per_day
        current_confidence = original_confidence - decay

        # Floor at minimum threshold
        return max(self.min_threshold, current_confidence)

    def apply_corroboration_boost(
        self,
        base_confidence: float,
        corroborating_source_count: int,
    ) -> float:
        """Apply corroboration boost to confidence score.

        Each corroborating source adds a configurable boost to confidence,
        up to the maximum confidence ceiling.

        Args:
            base_confidence: Starting confidence score (0.0-1.0).
            corroborating_source_count: Number of independent corroborating sources.

        Returns:
            Boosted confidence, capped at max_confidence.
        """
        if corroborating_source_count <= 0:
            return base_confidence

        boost = corroborating_source_count * self.corroboration_boost
        boosted = base_confidence + boost

        return min(self.max_confidence, boosted)

    def get_effective_confidence(
        self,
        original_confidence: float,
        created_at: datetime,
        last_confirmed_at: datetime | None = None,
        corroborating_source_count: int = 0,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate effective confidence combining decay and corroboration.

        Order of operations:
        1. Apply time-based decay (with floor)
        2. Apply corroboration boost (with ceiling)

        This order ensures that old facts can be revived by corroboration.

        Args:
            original_confidence: Initial confidence score (0.0-1.0).
            created_at: When the fact was created.
            last_confirmed_at: When the fact was last confirmed/refreshed.
            corroborating_source_count: Number of independent corroborating sources.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Effective confidence score between min_threshold and max_confidence.
        """
        # Step 1: Apply decay
        decayed_confidence = self.calculate_current_confidence(
            original_confidence=original_confidence,
            created_at=created_at,
            last_confirmed_at=last_confirmed_at,
            as_of=as_of,
        )

        # Step 2: Apply corroboration boost
        return self.apply_corroboration_boost(
            base_confidence=decayed_confidence,
            corroborating_source_count=corroborating_source_count,
        )
