# US-210: Confidence Scoring System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a confidence scoring system for semantic facts that includes source-based initial confidence, time-based decay, corroboration boosts, and configurable thresholds.

**Architecture:** Create a dedicated `ConfidenceScorer` class that encapsulates all confidence calculation logic. This class will be used by `SemanticMemory` to calculate current confidence when retrieving facts, and by the API to filter results by confidence thresholds. Confidence decay is calculated dynamically at query time (not stored), while corroboration is tracked in the fact's metadata.

**Tech Stack:** Python 3.11+, Pydantic Settings, pytest, mypy --strict

---

## Acceptance Criteria from US-210

- [ ] Confidence calculation based on source reliability
- [ ] Confidence decay over time (configurable)
- [ ] Confidence boost from corroboration
- [ ] Threshold for including facts in responses
- [ ] Display confidence to user when relevant
- [ ] Configuration for confidence parameters
- [ ] Unit tests for scoring calculations

---

## Task 1: Add Confidence Configuration to Settings

**Files:**
- Modify: `backend/src/core/config.py`
- Test: `backend/tests/test_config.py`

**Step 1: Write the failing test**

Create test file if it doesn't exist, or add to existing.

```python
# backend/tests/test_config.py

def test_confidence_settings_defaults() -> None:
    """Test confidence configuration has correct default values."""
    from src.core.config import Settings

    settings = Settings()

    # Decay: 5% per month = 0.05/30 per day
    assert settings.CONFIDENCE_DECAY_RATE_PER_DAY == pytest.approx(0.05 / 30)
    # Boost per corroboration
    assert settings.CONFIDENCE_CORROBORATION_BOOST == 0.10
    # Maximum confidence
    assert settings.CONFIDENCE_MAX == 0.99
    # Minimum threshold for including facts in responses
    assert settings.CONFIDENCE_MIN_THRESHOLD == 0.3
    # Refresh window (days) - facts confirmed within this period don't decay
    assert settings.CONFIDENCE_REFRESH_WINDOW_DAYS == 7
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_config.py::test_confidence_settings_defaults -v`
Expected: FAIL with AttributeError (settings don't exist yet)

**Step 3: Write minimal implementation**

```python
# Add to backend/src/core/config.py, in the Settings class, after line 53:

    # Confidence Scoring Configuration
    CONFIDENCE_DECAY_RATE_PER_DAY: float = 0.05 / 30  # 5% per month
    CONFIDENCE_CORROBORATION_BOOST: float = 0.10  # +10% per corroborating source
    CONFIDENCE_MAX: float = 0.99  # Maximum confidence after boosts
    CONFIDENCE_MIN_THRESHOLD: float = 0.3  # Minimum for inclusion in responses
    CONFIDENCE_REFRESH_WINDOW_DAYS: int = 7  # Days before decay starts after refresh
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_config.py::test_confidence_settings_defaults -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/config.py backend/tests/test_config.py
git commit -m "feat(confidence): add confidence scoring configuration settings"
```

---

## Task 2: Create ConfidenceScorer Class

**Files:**
- Create: `backend/src/memory/confidence.py`
- Test: `backend/tests/test_confidence.py`

**Step 1: Write the failing test for calculate_current_confidence**

```python
# backend/tests/test_confidence.py
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_confidence.py -v`
Expected: FAIL with ModuleNotFoundError (module doesn't exist yet)

**Step 3: Write minimal implementation**

```python
# backend/src/memory/confidence.py
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
            max_confidence
            if max_confidence is not None
            else settings.CONFIDENCE_MAX
        )
        self.min_threshold = (
            min_threshold
            if min_threshold is not None
            else settings.CONFIDENCE_MIN_THRESHOLD
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_confidence.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/confidence.py backend/tests/test_confidence.py
git commit -m "feat(confidence): add ConfidenceScorer with time decay"
```

---

## Task 3: Add Corroboration Boost to ConfidenceScorer

**Files:**
- Modify: `backend/src/memory/confidence.py`
- Modify: `backend/tests/test_confidence.py`

**Step 1: Write the failing test for apply_corroboration_boost**

```python
# Add to backend/tests/test_confidence.py

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_confidence.py::test_apply_corroboration_boost_single_source -v`
Expected: FAIL with AttributeError (method doesn't exist)

**Step 3: Write minimal implementation**

```python
# Add to backend/src/memory/confidence.py, in ConfidenceScorer class:

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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_confidence.py -v -k corroboration`
Expected: PASS (all 4 corroboration tests)

**Step 5: Commit**

```bash
git add backend/src/memory/confidence.py backend/tests/test_confidence.py
git commit -m "feat(confidence): add corroboration boost calculation"
```

---

## Task 4: Add Full Confidence Calculation Method

**Files:**
- Modify: `backend/src/memory/confidence.py`
- Modify: `backend/tests/test_confidence.py`

**Step 1: Write the failing test for get_effective_confidence**

```python
# Add to backend/tests/test_confidence.py

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_confidence.py::test_get_effective_confidence_combines_decay_and_boost -v`
Expected: FAIL with AttributeError (method doesn't exist)

**Step 3: Write minimal implementation**

```python
# Add to backend/src/memory/confidence.py, in ConfidenceScorer class:

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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_confidence.py -v -k effective`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/confidence.py backend/tests/test_confidence.py
git commit -m "feat(confidence): add get_effective_confidence combining decay and boost"
```

---

## Task 5: Add meets_threshold Method

**Files:**
- Modify: `backend/src/memory/confidence.py`
- Modify: `backend/tests/test_confidence.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_confidence.py

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_confidence.py::test_meets_threshold_returns_true_above_threshold -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

```python
# Add to backend/src/memory/confidence.py, in ConfidenceScorer class:

    def meets_threshold(
        self,
        original_confidence: float,
        created_at: datetime,
        last_confirmed_at: datetime | None = None,
        corroborating_source_count: int = 0,
        threshold: float | None = None,
        as_of: datetime | None = None,
    ) -> bool:
        """Check if a fact meets the confidence threshold.

        Useful for filtering facts before including them in responses.

        Args:
            original_confidence: Initial confidence score (0.0-1.0).
            created_at: When the fact was created.
            last_confirmed_at: When the fact was last confirmed/refreshed.
            corroborating_source_count: Number of independent corroborating sources.
            threshold: Minimum confidence required. Defaults to min_threshold.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            True if effective confidence meets or exceeds threshold.
        """
        effective_threshold = threshold if threshold is not None else self.min_threshold

        effective_confidence = self.get_effective_confidence(
            original_confidence=original_confidence,
            created_at=created_at,
            last_confirmed_at=last_confirmed_at,
            corroborating_source_count=corroborating_source_count,
            as_of=as_of,
        )

        return effective_confidence >= effective_threshold
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_confidence.py -v -k threshold`
Expected: PASS (all 3 threshold tests)

**Step 5: Commit**

```bash
git add backend/src/memory/confidence.py backend/tests/test_confidence.py
git commit -m "feat(confidence): add meets_threshold method for filtering"
```

---

## Task 6: Add Corroboration Tracking Fields to SemanticFact

**Files:**
- Modify: `backend/src/memory/semantic.py`
- Modify: `backend/tests/test_semantic_memory.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_semantic_memory.py

def test_semantic_fact_with_corroboration_fields() -> None:
    """Test SemanticFact includes corroboration tracking fields."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
        last_confirmed_at=now,
        corroborating_sources=["crm_import:123", "user_stated:456"],
    )

    assert fact.last_confirmed_at == now
    assert len(fact.corroborating_sources) == 2
    assert "crm_import:123" in fact.corroborating_sources


def test_semantic_fact_to_dict_includes_corroboration() -> None:
    """Test to_dict includes corroboration fields."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="title",
        object="CEO",
        confidence=0.90,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
        last_confirmed_at=now,
        corroborating_sources=["source:1"],
    )

    data = fact.to_dict()

    assert data["last_confirmed_at"] == now.isoformat()
    assert data["corroborating_sources"] == ["source:1"]


def test_semantic_fact_from_dict_restores_corroboration() -> None:
    """Test from_dict restores corroboration fields."""
    now = datetime.now(UTC)
    data = {
        "id": "fact-123",
        "user_id": "user-456",
        "subject": "Jane",
        "predicate": "department",
        "object": "Sales",
        "confidence": 0.85,
        "source": "extracted",
        "valid_from": now.isoformat(),
        "valid_to": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "last_confirmed_at": now.isoformat(),
        "corroborating_sources": ["source:a", "source:b"],
    }

    fact = SemanticFact.from_dict(data)

    assert fact.last_confirmed_at == now
    assert fact.corroborating_sources == ["source:a", "source:b"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_semantic_fact_with_corroboration_fields -v`
Expected: FAIL with TypeError (unexpected keyword arguments)

**Step 3: Write minimal implementation**

Modify `backend/src/memory/semantic.py`:

```python
# Update SemanticFact dataclass (around line 51-70)
# Add these two fields after invalidation_reason:

@dataclass
class SemanticFact:
    """A semantic fact representing knowledge about an entity.

    Uses subject-predicate-object triple structure (e.g., "John works_at Acme").
    Tracks confidence, source, and temporal validity.
    """

    id: str
    user_id: str
    subject: str  # Entity the fact is about
    predicate: str  # Relationship type
    object: str  # Value or related entity
    confidence: float  # 0.0 to 1.0
    source: FactSource
    valid_from: datetime
    valid_to: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    last_confirmed_at: datetime | None = None  # NEW: When fact was last confirmed
    corroborating_sources: list[str] | None = None  # NEW: List of source IDs that corroborate

    def __post_init__(self) -> None:
        """Initialize mutable defaults."""
        if self.corroborating_sources is None:
            self.corroborating_sources = []
```

Update `to_dict` method (around line 71-89):

```python
    def to_dict(self) -> dict[str, Any]:
        """Serialize fact to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
            "invalidation_reason": self.invalidation_reason,
            "last_confirmed_at": self.last_confirmed_at.isoformat() if self.last_confirmed_at else None,
            "corroborating_sources": self.corroborating_sources or [],
        }
```

Update `from_dict` method (around line 91-115):

```python
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticFact":
        """Create a SemanticFact instance from a dictionary.

        Args:
            data: Dictionary containing fact data.

        Returns:
            SemanticFact instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            confidence=data["confidence"],
            source=FactSource(data["source"]),
            valid_from=datetime.fromisoformat(data["valid_from"]),
            valid_to=datetime.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
            invalidated_at=datetime.fromisoformat(data["invalidated_at"])
            if data.get("invalidated_at")
            else None,
            invalidation_reason=data.get("invalidation_reason"),
            last_confirmed_at=datetime.fromisoformat(data["last_confirmed_at"])
            if data.get("last_confirmed_at")
            else None,
            corroborating_sources=data.get("corroborating_sources") or [],
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_semantic_memory.py -v -k corroboration`
Expected: PASS (3 new tests)

**Step 5: Commit**

```bash
git add backend/src/memory/semantic.py backend/tests/test_semantic_memory.py
git commit -m "feat(semantic): add corroboration tracking fields to SemanticFact"
```

---

## Task 7: Update Storage Format for New Fields

**Files:**
- Modify: `backend/src/memory/semantic.py`
- Modify: `backend/tests/test_semantic_memory.py`

**Step 1: Write the failing test for _build_fact_body with new fields**

```python
# Add to backend/tests/test_semantic_memory.py

def test_build_fact_body_includes_corroboration_fields() -> None:
    """Test _build_fact_body includes last_confirmed_at and corroborating_sources."""
    now = datetime.now(UTC)
    confirmed = now - timedelta(days=5)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
        last_confirmed_at=confirmed,
        corroborating_sources=["source:abc", "source:def"],
    )

    memory = SemanticMemory()
    body = memory._build_fact_body(fact)

    assert f"Last Confirmed At: {confirmed.isoformat()}" in body
    assert "Corroborating Sources: source:abc,source:def" in body


def test_parse_content_to_fact_handles_corroboration_fields() -> None:
    """Test _parse_content_to_fact parses new fields correctly."""
    now = datetime.now(UTC)
    confirmed = now - timedelta(days=3)

    content = f"""Subject: Jane
Predicate: title
Object: CEO
Confidence: 0.90
Source: crm_import
Valid From: {now.isoformat()}
Last Confirmed At: {confirmed.isoformat()}
Corroborating Sources: source:1,source:2"""

    memory = SemanticMemory()
    fact = memory._parse_content_to_fact(
        fact_id="fact-123",
        content=content,
        user_id="user-456",
        created_at=now,
    )

    assert fact is not None
    assert fact.last_confirmed_at == confirmed
    assert fact.corroborating_sources == ["source:1", "source:2"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_build_fact_body_includes_corroboration_fields -v`
Expected: FAIL (field not in body)

**Step 3: Write minimal implementation**

Update `_build_fact_body` method in `backend/src/memory/semantic.py` (around line 182-203):

```python
    def _build_fact_body(self, fact: SemanticFact) -> str:
        """Build a structured fact body string for storage.

        Args:
            fact: The SemanticFact instance to serialize.

        Returns:
            Structured text representation of the fact.
        """
        parts = [
            f"Subject: {fact.subject}",
            f"Predicate: {fact.predicate}",
            f"Object: {fact.object}",
            f"Confidence: {fact.confidence}",
            f"Source: {fact.source.value}",
            f"Valid From: {fact.valid_from.isoformat()}",
        ]

        if fact.valid_to:
            parts.append(f"Valid To: {fact.valid_to.isoformat()}")

        if fact.last_confirmed_at:
            parts.append(f"Last Confirmed At: {fact.last_confirmed_at.isoformat()}")

        if fact.corroborating_sources:
            parts.append(f"Corroborating Sources: {','.join(fact.corroborating_sources)}")

        return "\n".join(parts)
```

Update `_parse_content_to_fact` method (around line 230-296). Add parsing for new fields in the for loop:

```python
    def _parse_content_to_fact(
        self,
        fact_id: str,
        content: str,
        user_id: str,
        created_at: datetime,
    ) -> SemanticFact | None:
        """Parse fact content string into SemanticFact object.

        Args:
            fact_id: The fact ID.
            content: The raw content string.
            user_id: The user ID.
            created_at: When the fact was created.

        Returns:
            SemanticFact if parsing succeeds, None otherwise.
        """
        try:
            lines = content.split("\n")
            subject = ""
            predicate = ""
            obj = ""
            confidence = 0.5
            source = FactSource.EXTRACTED
            valid_from = created_at
            valid_to = None
            invalidated_at = None
            invalidation_reason = None
            last_confirmed_at = None
            corroborating_sources: list[str] = []

            for line in lines:
                if line.startswith("Subject:"):
                    subject = line.replace("Subject:", "").strip()
                elif line.startswith("Predicate:"):
                    predicate = line.replace("Predicate:", "").strip()
                elif line.startswith("Object:"):
                    obj = line.replace("Object:", "").strip()
                elif line.startswith("Confidence:"):
                    with contextlib.suppress(ValueError):
                        confidence = float(line.replace("Confidence:", "").strip())
                elif line.startswith("Source:"):
                    source_str = line.replace("Source:", "").strip()
                    with contextlib.suppress(ValueError):
                        source = FactSource(source_str)
                elif line.startswith("Valid From:"):
                    with contextlib.suppress(ValueError):
                        valid_from = datetime.fromisoformat(line.replace("Valid From:", "").strip())
                elif line.startswith("Valid To:"):
                    with contextlib.suppress(ValueError):
                        valid_to = datetime.fromisoformat(line.replace("Valid To:", "").strip())
                elif line.startswith("Last Confirmed At:"):
                    with contextlib.suppress(ValueError):
                        last_confirmed_at = datetime.fromisoformat(
                            line.replace("Last Confirmed At:", "").strip()
                        )
                elif line.startswith("Corroborating Sources:"):
                    sources_str = line.replace("Corroborating Sources:", "").strip()
                    if sources_str:
                        corroborating_sources = [s.strip() for s in sources_str.split(",") if s.strip()]

            if not subject or not predicate or not obj:
                return None

            return SemanticFact(
                id=fact_id,
                user_id=user_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=confidence,
                source=source,
                valid_from=valid_from,
                valid_to=valid_to,
                invalidated_at=invalidated_at,
                invalidation_reason=invalidation_reason,
                last_confirmed_at=last_confirmed_at,
                corroborating_sources=corroborating_sources,
            )
        except Exception as e:
            logger.warning(f"Failed to parse fact content: {e}")
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_semantic_memory.py -v -k "build_fact_body or parse_content"`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/semantic.py backend/tests/test_semantic_memory.py
git commit -m "feat(semantic): update storage format for corroboration fields"
```

---

## Task 8: Add confirm_fact Method to SemanticMemory

**Files:**
- Modify: `backend/src/memory/semantic.py`
- Modify: `backend/tests/test_semantic_memory.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_semantic_memory.py

@pytest.mark.asyncio
async def test_confirm_fact_updates_last_confirmed_at() -> None:
    """Test confirm_fact updates the last_confirmed_at timestamp."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Setup mock to return a fact
    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = f"Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: {now.isoformat()}"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-fact"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await memory.confirm_fact(
            user_id="user-456",
            fact_id="fact-123",
            confirming_source="crm_import:789",
        )

        # Should have called add_episode to update the fact
        assert mock_client.add_episode.called


@pytest.mark.asyncio
async def test_confirm_fact_adds_corroborating_source() -> None:
    """Test confirm_fact adds the confirming source to corroborating_sources."""
    now = datetime.now(UTC)
    memory = SemanticMemory()
    mock_client = MagicMock()

    # Existing fact with one corroborating source
    existing_sources = "Corroborating Sources: source:existing"
    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = f"Subject: John\nPredicate: works_at\nObject: Acme\nConfidence: 0.95\nSource: user_stated\nValid From: {now.isoformat()}\n{existing_sources}"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-fact"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await memory.confirm_fact(
            user_id="user-456",
            fact_id="fact-123",
            confirming_source="crm_import:new",
        )

        # Verify the episode body contains both sources
        call_args = mock_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "source:existing" in episode_body
        assert "crm_import:new" in episode_body
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_confirm_fact_updates_last_confirmed_at -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

Add to `backend/src/memory/semantic.py`, in SemanticMemory class (after `delete_fact` method):

```python
    async def confirm_fact(
        self,
        user_id: str,
        fact_id: str,
        confirming_source: str,
    ) -> None:
        """Confirm a fact, updating last_confirmed_at and adding corroboration.

        This method is used when an external source corroborates an existing fact.
        It refreshes the decay clock and adds the source to corroborating_sources.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to confirm.
            confirming_source: Identifier for the confirming source (e.g., "crm_import:123").

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If confirmation fails.
        """
        try:
            # Get existing fact
            fact = await self.get_fact(user_id, fact_id)

            # Update confirmation timestamp
            fact.last_confirmed_at = datetime.now(UTC)

            # Add corroborating source if not already present
            if fact.corroborating_sources is None:
                fact.corroborating_sources = []
            if confirming_source not in fact.corroborating_sources:
                fact.corroborating_sources.append(confirming_source)

            # Re-store the updated fact
            client = await self._get_graphiti_client()

            # Delete old version
            await self._delete_episode(client, fact_id)

            # Store updated version
            fact_body = self._build_fact_body(fact)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=f"fact:{fact_id}",
                episode_body=fact_body,
                source=EpisodeType.text,
                source_description=f"semantic_memory:{user_id}:{fact.predicate}:confirmed",
                reference_time=fact.valid_from,
            )

            logger.info(
                "Confirmed fact",
                extra={
                    "fact_id": fact_id,
                    "user_id": user_id,
                    "confirming_source": confirming_source,
                },
            )

        except FactNotFoundError:
            raise
        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to confirm fact", extra={"fact_id": fact_id})
            raise SemanticMemoryError(f"Failed to confirm fact: {e}") from e

    async def _delete_episode(self, client: "Graphiti", fact_id: str) -> None:
        """Delete an episode by fact ID (helper for updates).

        Args:
            client: The Graphiti client.
            fact_id: The fact ID to delete.
        """
        query = """
        MATCH (e:Episode)
        WHERE e.name = $fact_name
        DETACH DELETE e
        """
        await client.driver.execute_query(
            query,
            fact_name=f"fact:{fact_id}",
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_semantic_memory.py -v -k confirm_fact`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/semantic.py backend/tests/test_semantic_memory.py
git commit -m "feat(semantic): add confirm_fact method for corroboration"
```

---

## Task 9: Add get_effective_confidence Method to SemanticMemory

**Files:**
- Modify: `backend/src/memory/semantic.py`
- Modify: `backend/tests/test_semantic_memory.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_semantic_memory.py

def test_get_effective_confidence_for_fact() -> None:
    """Test get_effective_confidence returns scorer result for a fact."""
    from src.memory.semantic import SemanticMemory

    now = datetime.now(UTC)
    confirmed = now - timedelta(days=3)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        last_confirmed_at=confirmed,
        corroborating_sources=["source:1", "source:2"],
    )

    memory = SemanticMemory()
    result = memory.get_effective_confidence(fact, as_of=now)

    # Should be original confidence (confirmed within 7 days) + 2 boosts
    # 0.95 + 0.20 = 1.15, capped at 0.99
    assert result == pytest.approx(0.99)


def test_get_effective_confidence_with_decay() -> None:
    """Test get_effective_confidence applies decay for old facts."""
    from src.memory.semantic import SemanticMemory

    now = datetime.now(UTC)

    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.75,
        source=FactSource.EXTRACTED,
        valid_from=now - timedelta(days=60),
        last_confirmed_at=None,
        corroborating_sources=[],
    )

    memory = SemanticMemory()
    result = memory.get_effective_confidence(fact, as_of=now)

    # 0.75 - ((60-7) * 0.05/30) = 0.75 - 0.0883 = 0.6617
    expected = 0.75 - ((60 - 7) * 0.05 / 30)
    assert result == pytest.approx(expected, rel=0.01)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_get_effective_confidence_for_fact -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

Add to `backend/src/memory/semantic.py`:

First, add import at top of file (around line 15):

```python
from src.memory.confidence import ConfidenceScorer
```

Then add method to SemanticMemory class:

```python
    def get_effective_confidence(
        self,
        fact: SemanticFact,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate the effective confidence for a fact.

        Applies time-based decay and corroboration boosts to get the
        current confidence value for the fact.

        Args:
            fact: The SemanticFact to calculate confidence for.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Effective confidence score between 0.3 and 0.99.
        """
        scorer = ConfidenceScorer()

        return scorer.get_effective_confidence(
            original_confidence=fact.confidence,
            created_at=fact.valid_from,
            last_confirmed_at=fact.last_confirmed_at,
            corroborating_source_count=len(fact.corroborating_sources or []),
            as_of=as_of,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_semantic_memory.py -v -k get_effective_confidence`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add backend/src/memory/semantic.py backend/tests/test_semantic_memory.py
git commit -m "feat(semantic): add get_effective_confidence method"
```

---

## Task 10: Update Memory Query API to Use Effective Confidence

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Test: `backend/tests/test_api_memory.py` (create or add to)

**Step 1: Write the failing test**

```python
# backend/tests/test_api_memory.py (create if doesn't exist, or add to existing)
"""Tests for memory API routes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def test_client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


def test_memory_query_returns_effective_confidence(
    test_client: TestClient,
    mock_current_user: MagicMock,
) -> None:
    """Test that memory query returns effective (decayed) confidence."""
    from src.memory.semantic import FactSource, SemanticFact, SemanticMemory

    now = datetime.now(UTC)

    # Old fact with decay
    fact = SemanticFact(
        id="fact-123",
        user_id="test-user-123",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.75,
        source=FactSource.EXTRACTED,
        valid_from=now - timedelta(days=60),
        last_confirmed_at=None,
        corroborating_sources=[],
    )

    with patch("src.api.deps.get_current_user", return_value=mock_current_user):
        with patch.object(SemanticMemory, "search_facts", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [fact]

            response = test_client.get(
                "/api/v1/memory/query",
                params={"q": "Acme", "types": ["semantic"]},
            )

    assert response.status_code == 200
    data = response.json()

    # Confidence should be decayed from 0.75
    # Expected: 0.75 - ((60-7) * 0.05/30) ≈ 0.66
    expected = 0.75 - ((60 - 7) * 0.05 / 30)
    assert len(data["items"]) == 1
    assert data["items"][0]["confidence"] == pytest.approx(expected, rel=0.05)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_memory.py::test_memory_query_returns_effective_confidence -v`
Expected: FAIL (confidence not adjusted)

**Step 3: Write minimal implementation**

Modify `_query_semantic` method in `backend/src/api/routes/memory.py` (around line 302-330):

```python
    async def _query_semantic(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query semantic memory."""
        from src.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        facts = await memory.search_facts(user_id, query, min_confidence=0.0, limit=limit)

        results = []
        for fact in facts:
            relevance = self._calculate_text_relevance(
                query, f"{fact.subject} {fact.predicate} {fact.object}"
            )
            # Use effective confidence (with decay and boosts) instead of stored confidence
            effective_confidence = memory.get_effective_confidence(fact)
            results.append(
                {
                    "id": fact.id,
                    "memory_type": "semantic",
                    "content": f"{fact.subject} {fact.predicate} {fact.object}",
                    "relevance_score": relevance,
                    "confidence": effective_confidence,
                    "timestamp": fact.valid_from,
                }
            )

        return results
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api_memory.py::test_memory_query_returns_effective_confidence -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/test_api_memory.py
git commit -m "feat(api): use effective confidence in memory query results"
```

---

## Task 11: Add Confidence Filter to Memory Query

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/test_api_memory.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_api_memory.py

def test_memory_query_filters_by_min_confidence(
    test_client: TestClient,
    mock_current_user: MagicMock,
) -> None:
    """Test that memory query filters out low-confidence facts."""
    from src.memory.semantic import FactSource, SemanticFact, SemanticMemory

    now = datetime.now(UTC)

    # High confidence fact
    high_conf_fact = SemanticFact(
        id="fact-high",
        user_id="test-user-123",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=5),
        last_confirmed_at=now,
        corroborating_sources=[],
    )

    # Low confidence fact (will decay below threshold)
    low_conf_fact = SemanticFact(
        id="fact-low",
        user_id="test-user-123",
        subject="Jane",
        predicate="works_at",
        object="Other Corp",
        confidence=0.40,
        source=FactSource.INFERRED,
        valid_from=now - timedelta(days=365),
        last_confirmed_at=None,
        corroborating_sources=[],
    )

    with patch("src.api.deps.get_current_user", return_value=mock_current_user):
        with patch.object(SemanticMemory, "search_facts", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [high_conf_fact, low_conf_fact]

            response = test_client.get(
                "/api/v1/memory/query",
                params={"q": "works", "types": ["semantic"], "min_confidence": 0.5},
            )

    assert response.status_code == 200
    data = response.json()

    # Only high confidence fact should be returned
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "fact-high"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_memory.py::test_memory_query_filters_by_min_confidence -v`
Expected: FAIL (min_confidence parameter not recognized)

**Step 3: Write minimal implementation**

Modify `query_memory` endpoint in `backend/src/api/routes/memory.py` (around line 419-512):

Add the parameter (after `end_date`):

```python
@router.get("/query", response_model=MemoryQueryResponse)
async def query_memory(
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search query string"),
    types: list[str] = Query(
        default=["episodic", "semantic"],
        description="Memory types to search",
    ),
    start_date: datetime | None = Query(None, description="Start of time range filter"),
    end_date: datetime | None = Query(None, description="End of time range filter"),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
) -> MemoryQueryResponse:
```

Update the service query call to pass min_confidence:

```python
    # Query memories
    service = MemoryQueryService()
    # Request extra to determine has_more
    results = await service.query(
        user_id=current_user.id,
        query=q,
        memory_types=requested_types,
        start_date=start_date,
        end_date=end_date,
        min_confidence=min_confidence,
        limit=page_size + 1,  # Get one extra to check has_more
        offset=offset,
    )
```

Update `MemoryQueryService.query` method signature and implementation:

```python
    async def query(
        self,
        user_id: str,
        query: str,
        memory_types: list[str],
        start_date: datetime | None,
        end_date: datetime | None,
        min_confidence: float | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """Query across specified memory types.

        Args:
            user_id: The user ID to query memories for.
            query: The search query string.
            memory_types: List of memory types to search.
            start_date: Optional start of time range filter.
            end_date: Optional end of time range filter.
            min_confidence: Minimum confidence threshold for semantic results.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of memory results sorted by relevance.
        """
        tasks = []

        if "episodic" in memory_types:
            tasks.append(self._query_episodic(user_id, query, start_date, end_date, limit))
        if "semantic" in memory_types:
            tasks.append(self._query_semantic(user_id, query, limit, min_confidence))
        if "procedural" in memory_types:
            tasks.append(self._query_procedural(user_id, query, limit))
        if "prospective" in memory_types:
            tasks.append(self._query_prospective(user_id, query, limit))

        # ... rest of method unchanged
```

Update `_query_semantic` to filter by confidence:

```python
    async def _query_semantic(
        self,
        user_id: str,
        query: str,
        limit: int,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """Query semantic memory."""
        from src.memory.semantic import SemanticMemory

        memory = SemanticMemory()
        facts = await memory.search_facts(user_id, query, min_confidence=0.0, limit=limit)

        results = []
        for fact in facts:
            # Calculate effective confidence with decay and boosts
            effective_confidence = memory.get_effective_confidence(fact)

            # Filter by minimum confidence threshold
            if min_confidence is not None and effective_confidence < min_confidence:
                continue

            relevance = self._calculate_text_relevance(
                query, f"{fact.subject} {fact.predicate} {fact.object}"
            )
            results.append(
                {
                    "id": fact.id,
                    "memory_type": "semantic",
                    "content": f"{fact.subject} {fact.predicate} {fact.object}",
                    "relevance_score": relevance,
                    "confidence": effective_confidence,
                    "timestamp": fact.valid_from,
                }
            )

        return results
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api_memory.py -v -k min_confidence`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/test_api_memory.py
git commit -m "feat(api): add min_confidence filter to memory query endpoint"
```

---

## Task 12: Export ConfidenceScorer from Memory Module

**Files:**
- Modify: `backend/src/memory/__init__.py`
- Test: Verify imports work

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_confidence.py

def test_confidence_scorer_exportable_from_memory_module() -> None:
    """Test ConfidenceScorer can be imported from memory module."""
    from src.memory import ConfidenceScorer

    scorer = ConfidenceScorer()
    assert scorer is not None
    assert hasattr(scorer, "get_effective_confidence")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_confidence.py::test_confidence_scorer_exportable_from_memory_module -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Modify `backend/src/memory/__init__.py`:

Add import (around line 13):

```python
from src.memory.confidence import ConfidenceScorer
```

Add to `__all__` list (around line 34):

```python
__all__ = [
    # Working Memory
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    # Semantic Memory
    "FactSource",
    "SemanticFact",
    "SemanticMemory",
    # Procedural Memory
    "ProceduralMemory",
    "Workflow",
    # Prospective Memory
    "ProspectiveMemory",
    "ProspectiveTask",
    "TriggerType",
    "TaskStatus",
    "TaskPriority",
    # Digital Twin
    "DigitalTwin",
    "TextStyleAnalyzer",
    "WritingStyleFingerprint",
    # Confidence Scoring
    "ConfidenceScorer",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_confidence.py::test_confidence_scorer_exportable_from_memory_module -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_confidence.py
git commit -m "feat(memory): export ConfidenceScorer from memory module"
```

---

## Task 13: Run Full Quality Gates

**Files:**
- All modified files

**Step 1: Run all tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run mypy type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No errors

**Step 3: Run ruff linting**

Run: `cd backend && ruff check src/`
Expected: No warnings

**Step 4: Run ruff formatting check**

Run: `cd backend && ruff format src/ --check`
Expected: No formatting issues

**Step 5: Fix any issues and commit**

If any issues found, fix them and commit:

```bash
git add -A
git commit -m "style: fix linting and type issues"
```

---

## Task 14: Final Commit and Summary

**Step 1: Verify all acceptance criteria**

- [x] Confidence calculation based on source reliability (SOURCE_CONFIDENCE in semantic.py)
- [x] Confidence decay over time (ConfidenceScorer.calculate_current_confidence)
- [x] Confidence boost from corroboration (ConfidenceScorer.apply_corroboration_boost)
- [x] Threshold for including facts in responses (min_confidence parameter in API)
- [x] Display confidence to user when relevant (effective confidence in query results)
- [x] Configuration for confidence parameters (Settings class)
- [x] Unit tests for scoring calculations (test_confidence.py)

**Step 2: Create final summary commit if needed**

```bash
git status
# If all clean, no action needed
```

---

## Files Changed Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/core/config.py` | Modify | Add confidence configuration settings |
| `backend/src/memory/confidence.py` | Create | ConfidenceScorer class with decay/boost logic |
| `backend/src/memory/semantic.py` | Modify | Add corroboration fields, confirm_fact, get_effective_confidence |
| `backend/src/memory/__init__.py` | Modify | Export ConfidenceScorer |
| `backend/src/api/routes/memory.py` | Modify | Use effective confidence, add min_confidence filter |
| `backend/tests/test_config.py` | Create/Modify | Test confidence settings |
| `backend/tests/test_confidence.py` | Create | Test ConfidenceScorer |
| `backend/tests/test_semantic_memory.py` | Modify | Test new SemanticFact fields and methods |
| `backend/tests/test_api_memory.py` | Create/Modify | Test API confidence behavior |

---

## Execution Notes

- Each task is designed to be 2-5 minutes
- Follow TDD strictly: test → fail → implement → pass → commit
- Quality gates must pass before any commit
- If tests are flaky, debug before proceeding
