# US-420: Cognitive Load Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a CognitiveLoadMonitor service that detects when users are stressed/overwhelmed and adapts ARIA's communication style automatically.

**Architecture:** A new `src/intelligence/` module containing the cognitive load service. The service analyzes message patterns (brevity, velocity, typos), calendar density, and time of day to compute a weighted load score (0-1). Snapshots persist to Supabase for trend analysis. The ChatService integrates load state to adapt response style.

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic / Supabase (PostgreSQL) / pytest

---

## Task 1: Create Database Migration

**Files:**
- Create: `backend/supabase/migrations/009_cognitive_load_snapshots.sql`

**Step 1: Write the migration file**

```sql
-- Migration: US-420 Cognitive Load Monitor
-- Creates cognitive_load_snapshots table for tracking user cognitive state

-- =============================================================================
-- Cognitive Load Snapshots Table
-- =============================================================================

CREATE TABLE cognitive_load_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,

    -- Load indicators
    load_level TEXT NOT NULL CHECK (load_level IN ('low', 'medium', 'high', 'critical')),
    load_score FLOAT NOT NULL CHECK (load_score >= 0 AND load_score <= 1),

    -- Contributing factors (JSONB for flexibility)
    -- Example: {
    --   "message_brevity": 0.8,
    --   "typo_rate": 0.3,
    --   "message_velocity": 0.6,
    --   "calendar_density": 0.9,
    --   "time_of_day": 0.4
    -- }
    factors JSONB NOT NULL DEFAULT '{}',

    -- Context
    session_id UUID,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX idx_cognitive_load_user ON cognitive_load_snapshots(user_id, measured_at DESC);
CREATE INDEX idx_cognitive_load_level ON cognitive_load_snapshots(user_id, load_level);
CREATE INDEX idx_cognitive_load_session ON cognitive_load_snapshots(session_id) WHERE session_id IS NOT NULL;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE cognitive_load_snapshots ENABLE ROW LEVEL SECURITY;

-- Users can only access their own load data
CREATE POLICY "Users can view own cognitive load data" ON cognitive_load_snapshots
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own cognitive load data" ON cognitive_load_snapshots
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to cognitive load" ON cognitive_load_snapshots
    FOR ALL USING (auth.role() = 'service_role');
```

**Step 2: Verify migration file exists**

Run: `ls -la backend/supabase/migrations/009_cognitive_load_snapshots.sql`
Expected: File exists with correct content

**Step 3: Commit**

```bash
git add backend/supabase/migrations/009_cognitive_load_snapshots.sql
git commit -m "feat(db): add cognitive_load_snapshots migration for US-420"
```

---

## Task 2: Create Pydantic Models

**Files:**
- Create: `backend/src/models/cognitive_load.py`

**Step 1: Write the failing test**

Create `backend/tests/test_cognitive_load_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cognitive_load_models.py -v`
Expected: FAIL with ModuleNotFoundError (module doesn't exist yet)

**Step 3: Write minimal implementation**

Create `backend/src/models/cognitive_load.py`:

```python
"""Pydantic models for cognitive load monitoring."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LoadLevel(str, Enum):
    """Cognitive load level categories."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CognitiveLoadState(BaseModel):
    """Current cognitive load state with factors and recommendation."""

    level: LoadLevel
    score: float = Field(..., ge=0.0, le=1.0, description="Load score 0.0 to 1.0")
    factors: dict[str, float] = Field(
        default_factory=dict, description="Individual factor scores"
    )
    recommendation: str = Field(
        ..., description="Response style recommendation: detailed, balanced, concise, concise_urgent"
    )


class CognitiveLoadSnapshotResponse(BaseModel):
    """Response model for cognitive load snapshot (matches DB schema)."""

    id: str
    user_id: str
    load_level: str
    load_score: float = Field(..., ge=0.0, le=1.0)
    factors: dict[str, float]
    session_id: str | None = None
    measured_at: datetime


class CognitiveLoadRequest(BaseModel):
    """Request model for cognitive load estimation."""

    session_id: str | None = Field(None, description="Optional session ID for tracking")


class CognitiveLoadHistoryResponse(BaseModel):
    """Response for cognitive load history."""

    snapshots: list[CognitiveLoadSnapshotResponse]
    average_score: float | None = None
    trend: str | None = Field(
        None, description="Trend direction: improving, stable, worsening"
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cognitive_load_models.py -v`
Expected: PASS

**Step 5: Run type check**

Run: `cd backend && mypy src/models/cognitive_load.py --strict`
Expected: Success, no errors

**Step 6: Commit**

```bash
git add backend/src/models/cognitive_load.py backend/tests/test_cognitive_load_models.py
git commit -m "feat(models): add cognitive load Pydantic models for US-420"
```

---

## Task 3: Create CognitiveLoadMonitor Service - Core Calculations

**Files:**
- Create: `backend/src/intelligence/__init__.py`
- Create: `backend/src/intelligence/cognitive_load.py`

**Step 1: Write the failing test for core calculations**

Create `backend/tests/test_cognitive_load_service.py`:

```python
"""Tests for CognitiveLoadMonitor service."""

import pytest
from unittest.mock import MagicMock


class TestMessageBrevityCalculation:
    """Tests for message brevity factor calculation."""

    def test_very_short_message_high_brevity(self) -> None:
        """Messages under 20 chars should score 1.0 (high load indicator)."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._normalize_brevity(avg_length=10)
        assert score == 1.0

    def test_long_message_low_brevity(self) -> None:
        """Messages over 200 chars should score 0.0 (low load indicator)."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._normalize_brevity(avg_length=250)
        assert score == 0.0

    def test_medium_message_proportional_brevity(self) -> None:
        """Messages of 110 chars (midpoint) should score ~0.5."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        # Midpoint: (20 + 200) / 2 = 110
        score = monitor._normalize_brevity(avg_length=110)
        assert 0.45 <= score <= 0.55


class TestTypoRateCalculation:
    """Tests for typo rate factor calculation."""

    def test_no_messages_zero_typo_rate(self) -> None:
        """Empty message list should return 0.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._calculate_typo_rate(messages=[])
        assert score == 0.0

    def test_correction_marker_increases_typo_rate(self) -> None:
        """Messages starting with * (correction) should increase typo rate."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "I need help"},
            {"content": "*I meant help with"},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score > 0.0

    def test_repeated_chars_increases_typo_rate(self) -> None:
        """Repeated characters (like 'helllp') indicate rushed typing."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "helllp me please"},
            {"content": "I'm stresssed"},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score > 0.0

    def test_clean_messages_low_typo_rate(self) -> None:
        """Clean messages without errors should score low."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Can you help me with a sales report?"},
            {"content": "I need data for Q4 performance."},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score == 0.0


class TestMessageVelocityCalculation:
    """Tests for message velocity factor calculation."""

    def test_single_message_zero_velocity(self) -> None:
        """Single message cannot have velocity."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [{"content": "Hello", "created_at": "2026-02-03T12:00:00Z"}]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 0.0

    def test_rapid_messages_high_velocity(self) -> None:
        """Messages < 5 seconds apart should score 1.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Help", "created_at": "2026-02-03T12:00:00Z"},
            {"content": "Now", "created_at": "2026-02-03T12:00:02Z"},
            {"content": "Please", "created_at": "2026-02-03T12:00:04Z"},
        ]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 1.0

    def test_relaxed_messages_low_velocity(self) -> None:
        """Messages > 60 seconds apart should score 0.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Hello", "created_at": "2026-02-03T12:00:00Z"},
            {"content": "World", "created_at": "2026-02-03T12:02:00Z"},
        ]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 0.0


class TestTimeOfDayFactor:
    """Tests for time of day factor calculation."""

    def test_late_night_high_factor(self) -> None:
        """Late night (10pm-6am) should score 0.8."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from unittest.mock import patch
        from datetime import datetime

        monitor = CognitiveLoadMonitor(db_client=MagicMock())

        with patch("src.intelligence.cognitive_load.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 0)  # 11pm
            score = monitor._time_of_day_factor()

        assert score == 0.8

    def test_core_hours_low_factor(self) -> None:
        """Core hours (8am-6pm) should score 0.2."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from unittest.mock import patch
        from datetime import datetime

        monitor = CognitiveLoadMonitor(db_client=MagicMock())

        with patch("src.intelligence.cognitive_load.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 14, 0)  # 2pm
            score = monitor._time_of_day_factor()

        assert score == 0.2


class TestWeightedScoreCalculation:
    """Tests for the weighted score formula."""

    def test_all_zeros_gives_zero(self) -> None:
        """All factors at 0 should give score near 0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        factors = {
            "message_brevity": 0.0,
            "typo_rate": 0.0,
            "message_velocity": 0.0,
            "calendar_density": 0.0,
            "time_of_day": 0.0,
        }
        score = monitor._calculate_weighted_score(factors)
        assert score == 0.0

    def test_all_ones_gives_one(self) -> None:
        """All factors at 1 should give score of 1."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        factors = {
            "message_brevity": 1.0,
            "typo_rate": 1.0,
            "message_velocity": 1.0,
            "calendar_density": 1.0,
            "time_of_day": 1.0,
        }
        score = monitor._calculate_weighted_score(factors)
        assert score == 1.0

    def test_weights_sum_to_one(self) -> None:
        """WEIGHTS should sum to 1.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        total = sum(monitor.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestLoadLevelDetermination:
    """Tests for determining load level from score."""

    def test_low_threshold(self) -> None:
        """Score < 0.3 should be LOW."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.25)
        assert level == LoadLevel.LOW

    def test_medium_threshold(self) -> None:
        """Score 0.3-0.5 should be MEDIUM."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.4)
        assert level == LoadLevel.MEDIUM

    def test_high_threshold(self) -> None:
        """Score 0.5-0.7 should be HIGH."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.6)
        assert level == LoadLevel.HIGH

    def test_critical_threshold(self) -> None:
        """Score > 0.85 should be CRITICAL."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.9)
        assert level == LoadLevel.CRITICAL


class TestRecommendationGeneration:
    """Tests for response style recommendations."""

    def test_low_load_detailed_recommendation(self) -> None:
        """LOW load should recommend detailed responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.LOW, factors={})
        assert rec == "detailed"

    def test_high_load_concise_recommendation(self) -> None:
        """HIGH load should recommend concise responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.HIGH, factors={})
        assert rec == "concise"

    def test_critical_load_urgent_recommendation(self) -> None:
        """CRITICAL load should recommend concise_urgent responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.CRITICAL, factors={})
        assert rec == "concise_urgent"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cognitive_load_service.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

Create `backend/src/intelligence/__init__.py`:

```python
"""Intelligence modules for ARIA's cognitive capabilities."""

from src.intelligence.cognitive_load import CognitiveLoadMonitor

__all__ = ["CognitiveLoadMonitor"]
```

Create `backend/src/intelligence/cognitive_load.py`:

```python
"""Cognitive Load Monitor service.

Detects when users are stressed/overwhelmed based on message patterns,
calendar density, and time of day. Adapts ARIA's response style accordingly.
"""

import logging
from datetime import datetime, UTC
from typing import Any

from src.models.cognitive_load import CognitiveLoadState, LoadLevel

logger = logging.getLogger(__name__)


class CognitiveLoadMonitor:
    """Service for estimating and tracking user cognitive load."""

    # Weights for different factors (must sum to 1.0)
    WEIGHTS: dict[str, float] = {
        "message_brevity": 0.25,
        "typo_rate": 0.15,
        "message_velocity": 0.20,
        "calendar_density": 0.25,
        "time_of_day": 0.15,
    }

    # Thresholds for load levels
    THRESHOLDS: dict[str, float] = {
        "low": 0.3,
        "medium": 0.5,
        "high": 0.7,
        "critical": 0.85,
    }

    def __init__(self, db_client: Any) -> None:
        """Initialize cognitive load monitor.

        Args:
            db_client: Supabase database client.
        """
        self._db = db_client

    def _normalize_brevity(self, avg_length: float) -> float:
        """Normalize message length to 0-1 (short = high load).

        Args:
            avg_length: Average message length in characters.

        Returns:
            Brevity score from 0.0 (long messages) to 1.0 (short messages).
        """
        # Under 20 chars = very brief = 1.0 (high load indicator)
        # Over 200 chars = detailed = 0.0 (low load indicator)
        if avg_length < 20:
            return 1.0
        elif avg_length > 200:
            return 0.0
        else:
            return 1.0 - (avg_length - 20) / 180

    def _calculate_typo_rate(self, messages: list[dict[str, Any]]) -> float:
        """Detect typos and errors in messages.

        Args:
            messages: List of message dicts with 'content' key.

        Returns:
            Typo rate score from 0.0 to 1.0.
        """
        if not messages:
            return 0.0

        error_indicators = 0
        for msg in messages:
            text = msg.get("content", "")
            # Check for repeated letters (typing fast/stressed)
            for char in "abcdefghijklmnopqrstuvwxyz":
                if char * 3 in text.lower():
                    error_indicators += 1
                    break
            # Check for correction markers (*meant, *I meant)
            if text.startswith("*") and len(text) < 20:
                error_indicators += 2

        # Normalize: max 2 indicators per message = 1.0
        return min(error_indicators / (len(messages) * 2), 1.0)

    def _calculate_velocity(self, messages: list[dict[str, Any]]) -> float:
        """Calculate message sending velocity.

        Args:
            messages: List of message dicts with 'created_at' key.

        Returns:
            Velocity score from 0.0 (relaxed) to 1.0 (rapid).
        """
        if len(messages) < 2:
            return 0.0

        # Get timestamps
        timestamps: list[datetime] = []
        for msg in messages:
            created_at = msg.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    # Parse ISO format
                    ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    ts = created_at
                timestamps.append(ts)

        if len(timestamps) < 2:
            return 0.0

        # Calculate average gap between messages
        gaps: list[float] = []
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
            gaps.append(abs(gap))  # abs in case of ordering issues

        avg_gap = sum(gaps) / len(gaps)

        # Under 5 seconds = rapid = 1.0
        # Over 60 seconds = relaxed = 0.0
        if avg_gap < 5:
            return 1.0
        elif avg_gap > 60:
            return 0.0
        else:
            return 1.0 - (avg_gap - 5) / 55

    def _time_of_day_factor(self) -> float:
        """Calculate factor based on time of day.

        Returns:
            Time factor from 0.2 (core hours) to 0.8 (late night).
        """
        hour = datetime.now().hour

        # Late night (10pm-6am) = high
        if hour >= 22 or hour < 6:
            return 0.8
        # Early morning (6-8am) or evening (6-10pm) = medium
        elif hour < 8 or hour >= 18:
            return 0.4
        # Core hours (8am-6pm) = low
        else:
            return 0.2

    def _calculate_weighted_score(self, factors: dict[str, float]) -> float:
        """Calculate weighted score from individual factors.

        Args:
            factors: Dict of factor names to scores (0-1).

        Returns:
            Weighted score from 0.0 to 1.0.
        """
        score = 0.0
        for factor_name, weight in self.WEIGHTS.items():
            factor_value = factors.get(factor_name, 0.0)
            score += factor_value * weight
        return score

    def _determine_level(self, score: float) -> LoadLevel:
        """Determine load level from score.

        Args:
            score: Weighted score from 0.0 to 1.0.

        Returns:
            LoadLevel enum value.
        """
        if score >= self.THRESHOLDS["critical"]:
            return LoadLevel.CRITICAL
        elif score >= self.THRESHOLDS["high"]:
            return LoadLevel.HIGH
        elif score >= self.THRESHOLDS["medium"]:
            return LoadLevel.MEDIUM
        else:
            return LoadLevel.LOW

    def _get_recommendation(
        self, level: LoadLevel, factors: dict[str, float]
    ) -> str:
        """Generate response style recommendation based on load.

        Args:
            level: Current load level.
            factors: Factor scores (for potential factor-specific recommendations).

        Returns:
            Recommendation string: detailed, balanced, concise, or concise_urgent.
        """
        if level == LoadLevel.CRITICAL:
            return "concise_urgent"
        elif level == LoadLevel.HIGH:
            return "concise"
        elif level == LoadLevel.MEDIUM:
            return "balanced"
        else:
            return "detailed"

    async def estimate_load(
        self,
        user_id: str,
        recent_messages: list[dict[str, Any]],
        session_id: str | None = None,
        calendar_density: float | None = None,
    ) -> CognitiveLoadState:
        """Estimate user's current cognitive load.

        Args:
            user_id: User ID for persistence.
            recent_messages: Recent messages from the conversation.
            session_id: Optional session ID for tracking.
            calendar_density: Pre-computed calendar density (0-1), or None to skip.

        Returns:
            CognitiveLoadState with level, score, factors, and recommendation.
        """
        factors: dict[str, float] = {}

        # 1. Message brevity (short messages = higher load)
        if recent_messages:
            avg_length = sum(
                len(m.get("content", "")) for m in recent_messages
            ) / len(recent_messages)
            factors["message_brevity"] = self._normalize_brevity(avg_length)
        else:
            factors["message_brevity"] = 0.5  # Default neutral

        # 2. Typo rate (more typos = higher load)
        factors["typo_rate"] = self._calculate_typo_rate(recent_messages)

        # 3. Message velocity (rapid messages = higher load)
        factors["message_velocity"] = self._calculate_velocity(recent_messages)

        # 4. Calendar density (busy calendar = higher load)
        # Use provided value or default to 0.0 if calendar integration unavailable
        factors["calendar_density"] = calendar_density if calendar_density is not None else 0.0

        # 5. Time of day (late hours = higher load)
        factors["time_of_day"] = self._time_of_day_factor()

        # Calculate weighted score
        score = self._calculate_weighted_score(factors)

        # Determine level
        level = self._determine_level(score)

        # Generate recommendation
        recommendation = self._get_recommendation(level, factors)

        state = CognitiveLoadState(
            level=level,
            score=score,
            factors=factors,
            recommendation=recommendation,
        )

        # Store snapshot
        await self._store_snapshot(user_id, state, session_id)

        logger.info(
            "Cognitive load estimated",
            extra={
                "user_id": user_id,
                "load_level": level.value,
                "load_score": round(score, 3),
                "session_id": session_id,
            },
        )

        return state

    async def _store_snapshot(
        self,
        user_id: str,
        state: CognitiveLoadState,
        session_id: str | None,
    ) -> None:
        """Store cognitive load snapshot to database.

        Args:
            user_id: User ID.
            state: Current cognitive load state.
            session_id: Optional session ID.
        """
        try:
            self._db.table("cognitive_load_snapshots").insert(
                {
                    "user_id": user_id,
                    "load_level": state.level.value,
                    "load_score": state.score,
                    "factors": state.factors,
                    "session_id": session_id,
                    "measured_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "Failed to store cognitive load snapshot",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def get_current_load(
        self, user_id: str
    ) -> CognitiveLoadState | None:
        """Get the most recent cognitive load state for a user.

        Args:
            user_id: User ID.

        Returns:
            Most recent CognitiveLoadState or None if no snapshots exist.
        """
        try:
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("*")
                .eq("user_id", user_id)
                .order("measured_at", desc=True)
                .limit(1)
                .execute()
            )

            if result.data:
                row = result.data[0]
                return CognitiveLoadState(
                    level=LoadLevel(row["load_level"]),
                    score=row["load_score"],
                    factors=row["factors"],
                    recommendation=self._get_recommendation(
                        LoadLevel(row["load_level"]), row["factors"]
                    ),
                )
            return None
        except Exception as e:
            logger.warning(
                "Failed to get current cognitive load",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def get_load_history(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get cognitive load history for a user.

        Args:
            user_id: User ID.
            limit: Maximum number of snapshots to return.

        Returns:
            List of snapshot dicts ordered by measured_at descending.
        """
        try:
            result = (
                self._db.table("cognitive_load_snapshots")
                .select("*")
                .eq("user_id", user_id)
                .order("measured_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data if result.data else []
        except Exception as e:
            logger.warning(
                "Failed to get cognitive load history",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cognitive_load_service.py -v`
Expected: All tests PASS

**Step 5: Run type check**

Run: `cd backend && mypy src/intelligence/ --strict`
Expected: Success, no errors

**Step 6: Commit**

```bash
git add backend/src/intelligence/ backend/tests/test_cognitive_load_service.py
git commit -m "feat(intelligence): add CognitiveLoadMonitor service for US-420"
```

---

## Task 4: Create API Route

**Files:**
- Create: `backend/src/api/routes/cognitive_load.py`
- Modify: `backend/src/main.py:13-23,84-93`

**Step 1: Write the failing test**

Create `backend/tests/test_api_cognitive_load.py`:

```python
"""Tests for cognitive load API routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_cognitive_load_requires_auth() -> None:
    """GET /api/v1/user/cognitive-load should require authentication."""
    from fastapi.testclient import TestClient
    from src.main import app

    client = TestClient(app)
    response = client.get("/api/v1/user/cognitive-load")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_cognitive_load_returns_state() -> None:
    """GET /api/v1/user/cognitive-load should return current load state."""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_state = CognitiveLoadState(
        level=LoadLevel.MEDIUM,
        score=0.45,
        factors={
            "message_brevity": 0.5,
            "typo_rate": 0.2,
            "message_velocity": 0.3,
            "calendar_density": 0.6,
            "time_of_day": 0.4,
        },
        recommendation="balanced",
    )

    with patch("src.api.routes.cognitive_load.CognitiveLoadMonitor") as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor.get_current_load = AsyncMock(return_value=mock_state)
        mock_monitor_class.return_value = mock_monitor

        with patch("src.api.deps.get_current_user") as mock_auth:
            mock_user = MagicMock()
            mock_user.id = "user-123"
            mock_auth.return_value = mock_user

            client = TestClient(app)
            response = client.get(
                "/api/v1/user/cognitive-load",
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["level"] == "medium"
    assert data["score"] == 0.45
    assert data["recommendation"] == "balanced"


@pytest.mark.asyncio
async def test_get_cognitive_load_history() -> None:
    """GET /api/v1/user/cognitive-load/history should return snapshots."""
    from fastapi.testclient import TestClient
    from src.main import app

    mock_history = [
        {
            "id": "snap-1",
            "user_id": "user-123",
            "load_level": "high",
            "load_score": 0.65,
            "factors": {},
            "measured_at": "2026-02-03T12:00:00Z",
        },
        {
            "id": "snap-2",
            "user_id": "user-123",
            "load_level": "medium",
            "load_score": 0.45,
            "factors": {},
            "measured_at": "2026-02-03T11:00:00Z",
        },
    ]

    with patch("src.api.routes.cognitive_load.CognitiveLoadMonitor") as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor.get_load_history = AsyncMock(return_value=mock_history)
        mock_monitor_class.return_value = mock_monitor

        with patch("src.api.deps.get_current_user") as mock_auth:
            mock_user = MagicMock()
            mock_user.id = "user-123"
            mock_auth.return_value = mock_user

            client = TestClient(app)
            response = client.get(
                "/api/v1/user/cognitive-load/history",
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data["snapshots"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_cognitive_load.py -v`
Expected: FAIL (route doesn't exist)

**Step 3: Write minimal implementation**

Create `backend/src/api/routes/cognitive_load.py`:

```python
"""Cognitive load API routes."""

import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.models.cognitive_load import (
    CognitiveLoadHistoryResponse,
    CognitiveLoadSnapshotResponse,
    CognitiveLoadState,
    LoadLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/cognitive-load", response_model=CognitiveLoadState)
async def get_cognitive_load(
    current_user: CurrentUser,
) -> CognitiveLoadState:
    """Get current cognitive load state for the authenticated user.

    Args:
        current_user: Authenticated user from dependency.

    Returns:
        Current cognitive load state with level, score, factors, recommendation.
    """
    db = get_supabase_client()
    monitor = CognitiveLoadMonitor(db_client=db)

    try:
        state = await monitor.get_current_load(user_id=current_user.id)

        if state is None:
            # Return default low state if no history
            return CognitiveLoadState(
                level=LoadLevel.LOW,
                score=0.0,
                factors={},
                recommendation="detailed",
            )

        logger.info(
            "Cognitive load retrieved",
            extra={
                "user_id": current_user.id,
                "load_level": state.level.value,
            },
        )

        return state

    except Exception:
        logger.exception(
            "Failed to get cognitive load",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=503,
            detail="Cognitive load service temporarily unavailable",
        ) from None


@router.get("/cognitive-load/history", response_model=CognitiveLoadHistoryResponse)
async def get_cognitive_load_history(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum snapshots to return"),
) -> CognitiveLoadHistoryResponse:
    """Get cognitive load history for the authenticated user.

    Args:
        current_user: Authenticated user from dependency.
        limit: Maximum number of snapshots to return.

    Returns:
        List of cognitive load snapshots with optional trend analysis.
    """
    db = get_supabase_client()
    monitor = CognitiveLoadMonitor(db_client=db)

    try:
        history = await monitor.get_load_history(
            user_id=current_user.id,
            limit=limit,
        )

        snapshots = [
            CognitiveLoadSnapshotResponse(
                id=snap["id"],
                user_id=snap["user_id"],
                load_level=snap["load_level"],
                load_score=snap["load_score"],
                factors=snap["factors"],
                session_id=snap.get("session_id"),
                measured_at=snap["measured_at"],
            )
            for snap in history
        ]

        # Calculate average score
        average_score = None
        if snapshots:
            average_score = sum(s.load_score for s in snapshots) / len(snapshots)

        # Determine trend (compare first half to second half)
        trend = None
        if len(snapshots) >= 4:
            mid = len(snapshots) // 2
            recent_avg = sum(s.load_score for s in snapshots[:mid]) / mid
            older_avg = sum(s.load_score for s in snapshots[mid:]) / (len(snapshots) - mid)
            if recent_avg < older_avg - 0.1:
                trend = "improving"
            elif recent_avg > older_avg + 0.1:
                trend = "worsening"
            else:
                trend = "stable"

        logger.info(
            "Cognitive load history retrieved",
            extra={
                "user_id": current_user.id,
                "snapshot_count": len(snapshots),
                "trend": trend,
            },
        )

        return CognitiveLoadHistoryResponse(
            snapshots=snapshots,
            average_score=average_score,
            trend=trend,
        )

    except Exception:
        logger.exception(
            "Failed to get cognitive load history",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=503,
            detail="Cognitive load service temporarily unavailable",
        ) from None
```

**Step 4: Register the router in main.py**

Modify `backend/src/main.py` to import and register the router.

Add to imports (around line 13):
```python
from src.api.routes import (
    auth,
    battle_cards,
    briefings,
    chat,
    cognitive_load,  # Add this line
    debriefs,
    goals,
    integrations,
    memory,
    signals,
)
```

Add router registration (around line 93):
```python
app.include_router(signals.router, prefix="/api/v1")
app.include_router(cognitive_load.router, prefix="/api/v1")  # Add this line
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api_cognitive_load.py -v`
Expected: PASS

**Step 6: Run type check**

Run: `cd backend && mypy src/api/routes/cognitive_load.py --strict`
Expected: Success, no errors

**Step 7: Commit**

```bash
git add backend/src/api/routes/cognitive_load.py backend/src/main.py backend/tests/test_api_cognitive_load.py
git commit -m "feat(api): add cognitive load endpoint for US-420"
```

---

## Task 5: Integrate with Chat Service

**Files:**
- Modify: `backend/src/services/chat.py:42-51,181-282`

**Step 1: Write the failing test**

Create `backend/tests/test_chat_cognitive_load_integration.py`:

```python
"""Tests for chat service cognitive load integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_chat_includes_cognitive_load_in_response() -> None:
    """ChatService should include cognitive load state in response."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.HIGH,
        score=0.65,
        factors={"message_brevity": 0.8},
        recommendation="concise",
    )

    with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
        mock_monitor_class.return_value = mock_monitor

        with patch("src.services.chat.LLMClient") as mock_llm:
            mock_llm.return_value.generate_response = AsyncMock(return_value="Test response")

            with patch("src.services.chat.MemoryQueryService") as mock_memory:
                mock_memory.return_value.query = AsyncMock(return_value=[])

                with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                    mock_wm = MagicMock()
                    mock_wm.get_context_for_llm.return_value = []
                    mock_working.return_value.get_or_create.return_value = mock_wm

                    with patch("src.services.chat.ExtractionService"):
                        with patch.object(
                            ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                        ):
                            with patch.object(
                                ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                            ):
                                service = ChatService()
                                result = await service.process_message(
                                    user_id="user-123",
                                    conversation_id="conv-123",
                                    message="Help me quick",
                                )

    assert "cognitive_load" in result
    assert result["cognitive_load"]["level"] == "high"
    assert result["cognitive_load"]["recommendation"] == "concise"


@pytest.mark.asyncio
async def test_high_load_modifies_system_prompt() -> None:
    """When load is high, system prompt should instruct concise responses."""
    from src.services.chat import ChatService
    from src.models.cognitive_load import CognitiveLoadState, LoadLevel

    mock_load_state = CognitiveLoadState(
        level=LoadLevel.HIGH,
        score=0.72,
        factors={},
        recommendation="concise",
    )

    captured_system_prompt = None

    with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
        mock_monitor_class.return_value = mock_monitor

        with patch("src.services.chat.LLMClient") as mock_llm:
            async def capture_prompt(*args, **kwargs):
                nonlocal captured_system_prompt
                captured_system_prompt = kwargs.get("system_prompt", "")
                return "Response"

            mock_llm.return_value.generate_response = capture_prompt

            with patch("src.services.chat.MemoryQueryService") as mock_memory:
                mock_memory.return_value.query = AsyncMock(return_value=[])

                with patch("src.services.chat.WorkingMemoryManager") as mock_working:
                    mock_wm = MagicMock()
                    mock_wm.get_context_for_llm.return_value = []
                    mock_working.return_value.get_or_create.return_value = mock_wm

                    with patch("src.services.chat.ExtractionService"):
                        with patch.object(
                            ChatService, "_ensure_conversation_record", new_callable=AsyncMock
                        ):
                            with patch.object(
                                ChatService, "_update_conversation_metadata", new_callable=AsyncMock
                            ):
                                service = ChatService()
                                await service.process_message(
                                    user_id="user-123",
                                    conversation_id="conv-123",
                                    message="Need help",
                                )

    assert captured_system_prompt is not None
    assert "concise" in captured_system_prompt.lower() or "brief" in captured_system_prompt.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_chat_cognitive_load_integration.py -v`
Expected: FAIL (cognitive_load not in response)

**Step 3: Modify ChatService implementation**

Update `backend/src/services/chat.py`:

Add import at top of file:
```python
from src.db.supabase import get_supabase_client
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.models.cognitive_load import LoadLevel
```

Add to `__init__`:
```python
def __init__(self) -> None:
    """Initialize chat service with dependencies."""
    self._memory_service = MemoryQueryService()
    self._llm_client = LLMClient()
    self._working_memory_manager = WorkingMemoryManager()
    self._extraction_service = ExtractionService()
    self._cognitive_monitor = CognitiveLoadMonitor(db_client=get_supabase_client())
```

Add new constant for high load system instruction (after existing prompts):
```python
HIGH_LOAD_INSTRUCTION = """
IMPORTANT: The user appears to be under high cognitive load right now. Adapt your response:
- Be extremely concise and direct
- Lead with the most important information
- Avoid asking multiple questions
- Offer to handle tasks independently
- Use bullet points for clarity
"""
```

Modify `process_message` method to estimate load and include in response:

```python
async def process_message(
    self,
    user_id: str,
    conversation_id: str,
    message: str,
    memory_types: list[str] | None = None,
) -> dict[str, Any]:
    """Process a user message and generate a response.

    Args:
        user_id: The user's ID.
        conversation_id: Unique conversation identifier.
        message: The user's message.
        memory_types: Memory types to query (default: episodic, semantic).

    Returns:
        Dict containing response message, citations, timing, and cognitive_load.
    """
    total_start = time.perf_counter()

    if memory_types is None:
        memory_types = ["episodic", "semantic"]

    # Get or create working memory for this conversation
    working_memory = self._working_memory_manager.get_or_create(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    # Ensure conversation record exists for sidebar
    await self._ensure_conversation_record(user_id, conversation_id)

    # Add user message to working memory
    working_memory.add_message("user", message)

    # Estimate cognitive load from recent messages
    recent_messages = working_memory.get_context_for_llm()[-5:]  # Last 5 messages
    load_state = await self._cognitive_monitor.estimate_load(
        user_id=user_id,
        recent_messages=recent_messages,
        session_id=conversation_id,
    )

    # Query relevant memories with timing
    memory_start = time.perf_counter()
    memories = await self._query_relevant_memories(
        user_id=user_id,
        query=message,
        memory_types=memory_types,
    )
    memory_ms = (time.perf_counter() - memory_start) * 1000

    # Build system prompt with memory context and cognitive load adaptation
    system_prompt = self._build_system_prompt(memories, load_state)

    # Get conversation history
    conversation_messages = working_memory.get_context_for_llm()

    logger.info(
        "Processing chat message",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "memory_count": len(memories),
            "message_count": len(conversation_messages),
            "memory_query_ms": memory_ms,
            "cognitive_load_level": load_state.level.value,
        },
    )

    # Generate response from LLM with timing
    llm_start = time.perf_counter()
    response_text = await self._llm_client.generate_response(
        messages=conversation_messages,
        system_prompt=system_prompt,
    )
    llm_ms = (time.perf_counter() - llm_start) * 1000

    # Add assistant response to working memory
    working_memory.add_message("assistant", response_text)

    # Build citations from used memories
    citations = self._build_citations(memories)

    # Extract and store new information (fire and forget)
    try:
        await self._extraction_service.extract_and_store(
            conversation=conversation_messages[-2:],
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(
            "Information extraction failed",
            extra={"user_id": user_id, "error": str(e)},
        )

    # Update conversation metadata for sidebar
    await self._update_conversation_metadata(user_id, conversation_id, message, response_text)

    total_ms = (time.perf_counter() - total_start) * 1000

    return {
        "message": response_text,
        "citations": citations,
        "conversation_id": conversation_id,
        "timing": {
            "memory_query_ms": round(memory_ms, 2),
            "llm_response_ms": round(llm_ms, 2),
            "total_ms": round(total_ms, 2),
        },
        "cognitive_load": {
            "level": load_state.level.value,
            "score": round(load_state.score, 3),
            "recommendation": load_state.recommendation,
        },
    }
```

Update `_build_system_prompt` to accept load_state:

```python
def _build_system_prompt(
    self,
    memories: list[dict[str, Any]],
    load_state: Any = None,
) -> str:
    """Build system prompt with memory context and load adaptation.

    Args:
        memories: List of relevant memories.
        load_state: Optional cognitive load state for adaptation.

    Returns:
        Complete system prompt string.
    """
    memory_context = ""
    if memories:
        memory_lines = []
        for mem in memories:
            confidence_str = ""
            if mem.get("confidence") is not None:
                confidence_str = f" (confidence: {mem['confidence']:.0%})"
            memory_lines.append(f"- [{mem['memory_type']}] {mem['content']}{confidence_str}")

        memory_context = MEMORY_CONTEXT_TEMPLATE.format(memories="\n".join(memory_lines))

    base_prompt = ARIA_SYSTEM_PROMPT.format(memory_context=memory_context)

    # Add high load instruction if needed
    if load_state and load_state.level in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
        base_prompt = HIGH_LOAD_INSTRUCTION + "\n\n" + base_prompt

    return base_prompt
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_chat_cognitive_load_integration.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/services/chat.py backend/tests/test_chat_cognitive_load_integration.py
git commit -m "feat(chat): integrate cognitive load monitor into chat service for US-420"
```

---

## Task 6: Update Chat API Response Model

**Files:**
- Modify: `backend/src/api/routes/chat.py:49-56,121-126`

**Step 1: Write the failing test**

Add to `backend/tests/test_api_chat.py`:

```python
@pytest.mark.asyncio
async def test_chat_response_includes_cognitive_load() -> None:
    """Chat response should include cognitive_load field."""
    from fastapi.testclient import TestClient
    from src.main import app
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_result = {
        "message": "Test response",
        "citations": [],
        "conversation_id": "conv-123",
        "timing": {
            "memory_query_ms": 10.0,
            "llm_response_ms": 100.0,
            "total_ms": 110.0,
        },
        "cognitive_load": {
            "level": "medium",
            "score": 0.45,
            "recommendation": "balanced",
        },
    }

    with patch("src.api.routes.chat.ChatService") as mock_service_class:
        mock_service = MagicMock()
        mock_service.process_message = AsyncMock(return_value=mock_result)
        mock_service_class.return_value = mock_service

        with patch("src.api.deps.get_current_user") as mock_auth:
            mock_user = MagicMock()
            mock_user.id = "user-123"
            mock_auth.return_value = mock_user

            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "Hello"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "cognitive_load" in data
    assert data["cognitive_load"]["level"] == "medium"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_chat.py::test_chat_response_includes_cognitive_load -v`
Expected: FAIL (cognitive_load not in response model)

**Step 3: Modify chat route response model**

Update `backend/src/api/routes/chat.py`:

Add new model class:
```python
class CognitiveLoadInfo(BaseModel):
    """Cognitive load information in chat response."""

    level: str
    score: float
    recommendation: str
```

Update ChatResponse:
```python
class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: str
    citations: list[Citation]
    conversation_id: str
    timing: Timing | None = None
    cognitive_load: CognitiveLoadInfo | None = None
```

Update the chat endpoint return:
```python
return ChatResponse(
    message=result["message"],
    citations=[Citation(**c) for c in result.get("citations", [])],
    conversation_id=result["conversation_id"],
    timing=Timing(**result["timing"]) if result.get("timing") else None,
    cognitive_load=CognitiveLoadInfo(**result["cognitive_load"]) if result.get("cognitive_load") else None,
)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api_chat.py::test_chat_response_includes_cognitive_load -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/chat.py backend/tests/test_api_chat.py
git commit -m "feat(api): include cognitive load in chat response for US-420"
```

---

## Task 7: Run Full Test Suite and Verify

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd backend && mypy src/ --strict`
Expected: Success or only pre-existing issues

**Step 3: Run linting**

Run: `cd backend && ruff check src/`
Expected: No new errors

**Step 4: Run formatting**

Run: `cd backend && ruff format src/`
Expected: Formatting applied

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: format and lint cognitive load implementation"
```

---

## Summary

This plan implements US-420 Cognitive Load Monitor with:

1. **Database migration** - `cognitive_load_snapshots` table with RLS
2. **Pydantic models** - Type-safe request/response models
3. **CognitiveLoadMonitor service** - Core analysis logic with weighted factors
4. **API endpoint** - `GET /api/v1/user/cognitive-load` and history endpoint
5. **Chat integration** - Automatic load estimation and response adaptation
6. **Tests** - Comprehensive unit tests for all components

**Load factors analyzed:**
- Message brevity (0.25 weight)
- Typo rate (0.15 weight)
- Message velocity (0.20 weight)
- Calendar density (0.25 weight)
- Time of day (0.15 weight)

**Load thresholds:**
- Low: < 0.3
- Medium: 0.3 - 0.5
- High: 0.5 - 0.7
- Critical: > 0.85

**Response adaptations:**
- Low: detailed responses
- Medium: balanced responses
- High: concise responses
- Critical: concise_urgent (very brief, offer to handle tasks)
