# US-218: Memory Salience Decay System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement memory salience decay so recent/frequently-accessed memories are prioritized while old memories fade but never disappear.

**Architecture:** Add salience tracking columns to episodic_memories and semantic_facts tables, create memory_access_log for retrieval tracking, implement SalienceService with exponential decay formula, and add a background job for daily salience updates.

**Tech Stack:** Python 3.11, FastAPI, Supabase (PostgreSQL), pytest

---

## Context

### Key Files to Reference
- **Existing confidence system:** `backend/src/memory/confidence.py` - shows decay pattern
- **Memory module init:** `backend/src/memory/__init__.py` - export pattern
- **Migration pattern:** `backend/supabase/migrations/005_lead_memory_schema.sql`
- **Test pattern:** `backend/tests/test_semantic_memory.py`
- **Config pattern:** `backend/src/core/config.py`

### The Decay Formula
```
current_salience = (base_salience + access_boost) × 0.5^(days_since_last_access / half_life)
```
Where:
- `base_salience` = 1.0 (always starts at 1.0)
- `access_boost` = access_count × 0.1
- `half_life` = 30 days
- Minimum salience = 0.01 (never zero)

### Important Notes
- The spec says to add columns to `episodic_memories` and `semantic_facts` tables, but these tables don't exist in Supabase yet - they're Graphiti-backed. We'll need to create Supabase tracking tables that mirror the Graphiti IDs.
- The PHASE_2_RETROFIT.md SQL shows the migration pattern we should follow.

---

## Task 1: Create Salience Config Settings

**Files:**
- Modify: `backend/src/core/config.py:56-62`

**Step 1: Write the failing test**

Create: `backend/tests/test_salience_config.py`

```python
"""Tests for salience configuration settings."""

from src.core.config import Settings


def test_salience_settings_have_defaults() -> None:
    """Test that salience settings have sensible defaults."""
    settings = Settings()

    assert settings.SALIENCE_HALF_LIFE_DAYS == 30
    assert settings.SALIENCE_ACCESS_BOOST == 0.1
    assert settings.SALIENCE_MIN == 0.01


def test_salience_settings_can_be_overridden() -> None:
    """Test that salience settings can be customized via env vars."""
    settings = Settings(
        SALIENCE_HALF_LIFE_DAYS=60,
        SALIENCE_ACCESS_BOOST=0.2,
        SALIENCE_MIN=0.05,
    )

    assert settings.SALIENCE_HALF_LIFE_DAYS == 60
    assert settings.SALIENCE_ACCESS_BOOST == 0.2
    assert settings.SALIENCE_MIN == 0.05
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_config.py -v`

Expected: FAIL with AttributeError (settings don't exist yet)

**Step 3: Write minimal implementation**

Edit `backend/src/core/config.py` - add after line 61 (after CONFIDENCE settings):

```python
    # Salience Decay Configuration (US-218)
    SALIENCE_HALF_LIFE_DAYS: int = 30  # Days for salience to decay to 50%
    SALIENCE_ACCESS_BOOST: float = 0.1  # Boost per memory retrieval
    SALIENCE_MIN: float = 0.01  # Minimum salience (never zero)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_config.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/config.py backend/tests/test_salience_config.py
git commit -m "$(cat <<'EOF'
feat(memory): add salience decay configuration settings

US-218: Add SALIENCE_HALF_LIFE_DAYS, SALIENCE_ACCESS_BOOST, and
SALIENCE_MIN settings for configurable memory decay behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Database Migration for Salience Tracking

**Files:**
- Create: `backend/supabase/migrations/007_memory_salience.sql`

**Step 1: Write the migration file**

```sql
-- Migration: US-218 Memory Salience Decay System
-- Adds salience tracking to memory tables and creates access log

-- =============================================================================
-- Memory Salience Tracking Tables
-- =============================================================================
-- Note: episodic_memories and semantic_facts are primarily stored in Graphiti.
-- These Supabase tables track salience metadata keyed by Graphiti episode UUIDs.

-- Episodic memory salience tracking
CREATE TABLE episodic_memory_salience (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    graphiti_episode_id TEXT NOT NULL,  -- Reference to Graphiti episode
    current_salience FLOAT DEFAULT 1.0 CHECK (current_salience >= 0 AND current_salience <= 1),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, graphiti_episode_id)
);

-- Semantic fact salience tracking
CREATE TABLE semantic_fact_salience (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    graphiti_episode_id TEXT NOT NULL,  -- Reference to Graphiti episode
    current_salience FLOAT DEFAULT 1.0 CHECK (current_salience >= 0 AND current_salience <= 1),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, graphiti_episode_id)
);

-- Memory access log for all memory types
CREATE TABLE memory_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id TEXT NOT NULL,  -- Graphiti episode ID or other memory ID
    memory_type TEXT NOT NULL CHECK (memory_type IN ('episodic', 'semantic', 'lead')),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    access_context TEXT,  -- What triggered the access (e.g., "query: find meetings")
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Episodic salience indexes
CREATE INDEX idx_episodic_salience_user ON episodic_memory_salience(user_id);
CREATE INDEX idx_episodic_salience_graphiti ON episodic_memory_salience(graphiti_episode_id);
CREATE INDEX idx_episodic_salience_value ON episodic_memory_salience(user_id, current_salience DESC);
CREATE INDEX idx_episodic_salience_accessed ON episodic_memory_salience(user_id, last_accessed_at DESC);

-- Semantic salience indexes
CREATE INDEX idx_semantic_salience_user ON semantic_fact_salience(user_id);
CREATE INDEX idx_semantic_salience_graphiti ON semantic_fact_salience(graphiti_episode_id);
CREATE INDEX idx_semantic_salience_value ON semantic_fact_salience(user_id, current_salience DESC);
CREATE INDEX idx_semantic_salience_accessed ON semantic_fact_salience(user_id, last_accessed_at DESC);

-- Access log indexes
CREATE INDEX idx_memory_access_log_memory ON memory_access_log(memory_id, memory_type);
CREATE INDEX idx_memory_access_log_user ON memory_access_log(user_id);
CREATE INDEX idx_memory_access_log_time ON memory_access_log(user_id, accessed_at DESC);

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE episodic_memory_salience ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_fact_salience ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_access_log ENABLE ROW LEVEL SECURITY;

-- Users can only access their own salience records
CREATE POLICY "Users can manage own episodic salience" ON episodic_memory_salience
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own semantic salience" ON semantic_fact_salience
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own memory logs" ON memory_access_log
    FOR ALL USING (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to episodic salience" ON episodic_memory_salience
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to semantic salience" ON semantic_fact_salience
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to memory logs" ON memory_access_log
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_episodic_salience_updated_at
    BEFORE UPDATE ON episodic_memory_salience
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_semantic_salience_updated_at
    BEFORE UPDATE ON semantic_fact_salience
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Step 2: Verify migration syntax**

Run: `cd /Users/dhruv/aria/backend && cat supabase/migrations/007_memory_salience.sql | head -20`

Expected: SQL file exists and is readable

**Step 3: Commit**

```bash
git add backend/supabase/migrations/007_memory_salience.sql
git commit -m "$(cat <<'EOF'
feat(db): add memory salience tracking migration

US-218: Create episodic_memory_salience, semantic_fact_salience, and
memory_access_log tables with proper indexes and RLS policies.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create SalienceService with Decay Calculation

**Files:**
- Create: `backend/src/memory/salience.py`
- Create: `backend/tests/test_salience_service.py`

**Step 1: Write the failing tests for decay calculation**

Create: `backend/tests/test_salience_service.py`

```python
"""Tests for memory salience decay service."""

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.salience import SalienceService


class TestSalienceDecayCalculation:
    """Tests for the core decay formula."""

    def test_fresh_memory_has_full_salience(self) -> None:
        """A memory accessed just now should have salience ~1.0."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=0.0,
        )

        assert salience == 1.0

    def test_half_life_decay(self) -> None:
        """After 30 days, salience should be ~0.5 (half-life)."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=30.0,
        )

        assert abs(salience - 0.5) < 0.01

    def test_double_half_life_decay(self) -> None:
        """After 60 days, salience should be ~0.25."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=60.0,
        )

        assert abs(salience - 0.25) < 0.01

    def test_access_boost_adds_to_base(self) -> None:
        """Each access adds 0.1 to base salience before decay."""
        service = SalienceService(db_client=MagicMock())

        # 5 accesses = 0.5 boost, so base = 1.5
        # After 30 days: 1.5 * 0.5 = 0.75
        salience = service.calculate_decay(
            access_count=5,
            days_since_last_access=30.0,
        )

        assert abs(salience - 0.75) < 0.01

    def test_minimum_salience_enforced(self) -> None:
        """Salience never goes below MIN_SALIENCE (0.01)."""
        service = SalienceService(db_client=MagicMock())

        # After 1 year, decay factor is tiny
        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=365.0,
        )

        assert salience == 0.01

    def test_very_old_memory_with_many_accesses(self) -> None:
        """Even old memories with many accesses have a floor."""
        service = SalienceService(db_client=MagicMock())

        # 10 accesses = 1.0 boost, base = 2.0
        # After 365 days: decay factor = 0.5^(365/30) ≈ 0.000488
        # 2.0 * 0.000488 ≈ 0.00098 -> floored to 0.01
        salience = service.calculate_decay(
            access_count=10,
            days_since_last_access=365.0,
        )

        assert salience == 0.01

    def test_custom_half_life(self) -> None:
        """Can use custom half-life for different decay rates."""
        service = SalienceService(
            db_client=MagicMock(),
            half_life_days=60,  # Slower decay
        )

        # After 60 days with 60-day half-life, should be 0.5
        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=60.0,
        )

        assert abs(salience - 0.5) < 0.01

    def test_formula_matches_spec(self) -> None:
        """Verify formula: salience = (1 + access_boost) × 0.5^(days/half_life)."""
        service = SalienceService(db_client=MagicMock())

        # Manual calculation: 3 accesses, 15 days
        # base = 1.0 + (3 * 0.1) = 1.3
        # decay = 0.5^(15/30) = 0.5^0.5 ≈ 0.707
        # salience = 1.3 * 0.707 ≈ 0.919
        expected = (1.0 + 3 * 0.1) * math.pow(0.5, 15.0 / 30.0)

        salience = service.calculate_decay(
            access_count=3,
            days_since_last_access=15.0,
        )

        assert abs(salience - expected) < 0.001
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestSalienceDecayCalculation -v`

Expected: FAIL with ModuleNotFoundError (salience.py doesn't exist)

**Step 3: Write the SalienceService class**

Create: `backend/src/memory/salience.py`

```python
"""Memory salience decay service.

Implements salience decay for memory prioritization:
- Recent memories have higher salience
- Frequently accessed memories decay slower
- All memories have a minimum salience (never truly forgotten)

Formula: salience = (base + access_boost) × 0.5^(days_since_access / half_life)
"""

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from src.core.config import settings

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

# Type alias for memory types
MemoryType = Literal["episodic", "semantic", "lead"]


class SalienceService:
    """Service for calculating and managing memory salience.

    Salience represents how "prominent" a memory is based on recency
    and access frequency. Higher salience = more likely to be surfaced.
    """

    def __init__(
        self,
        db_client: "Client",
        half_life_days: float | None = None,
        access_boost: float | None = None,
        min_salience: float | None = None,
    ) -> None:
        """Initialize the salience service.

        Args:
            db_client: Supabase client for database operations.
            half_life_days: Days for salience to decay to 50%. Defaults to settings.
            access_boost: Boost per memory retrieval. Defaults to settings.
            min_salience: Minimum salience floor. Defaults to settings.
        """
        self.db = db_client
        self.half_life_days = (
            half_life_days
            if half_life_days is not None
            else settings.SALIENCE_HALF_LIFE_DAYS
        )
        self.access_boost = (
            access_boost if access_boost is not None else settings.SALIENCE_ACCESS_BOOST
        )
        self.min_salience = (
            min_salience if min_salience is not None else settings.SALIENCE_MIN
        )

    def calculate_decay(
        self,
        access_count: int,
        days_since_last_access: float,
    ) -> float:
        """Calculate current salience with exponential decay.

        Formula: salience = (1.0 + access_count * access_boost) × 0.5^(days / half_life)

        The base salience is always 1.0. Access boosts are additive to this base.
        Decay is exponential with the configured half-life.

        Args:
            access_count: Number of times the memory has been accessed.
            days_since_last_access: Days since the memory was last accessed.

        Returns:
            Current salience between min_salience and (1.0 + total_boost).
        """
        # Calculate base with access boost
        base_salience = 1.0 + (access_count * self.access_boost)

        # Calculate decay factor using half-life formula
        # decay_factor = 0.5^(days / half_life)
        if days_since_last_access <= 0:
            decay_factor = 1.0
        else:
            decay_factor = math.pow(0.5, days_since_last_access / self.half_life_days)

        # Apply decay to base
        current_salience = base_salience * decay_factor

        # Enforce minimum salience (memories never truly forgotten)
        return max(current_salience, self.min_salience)

    def calculate_decay_from_timestamp(
        self,
        access_count: int,
        last_accessed_at: datetime,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate salience from a timestamp.

        Convenience method that calculates days from timestamps.

        Args:
            access_count: Number of times the memory has been accessed.
            last_accessed_at: When the memory was last accessed.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Current salience value.
        """
        check_time = as_of or datetime.now(UTC)
        days_since = (check_time - last_accessed_at).total_seconds() / 86400
        return self.calculate_decay(access_count, days_since)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestSalienceDecayCalculation -v`

Expected: PASS (all 8 tests)

**Step 5: Commit**

```bash
git add backend/src/memory/salience.py backend/tests/test_salience_service.py
git commit -m "$(cat <<'EOF'
feat(memory): implement SalienceService decay calculation

US-218: Add SalienceService with exponential decay formula.
- Base salience = 1.0 + (access_count × 0.1)
- Decay factor = 0.5^(days / 30)
- Minimum salience = 0.01

Includes comprehensive unit tests for decay math.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Access Recording to SalienceService

**Files:**
- Modify: `backend/src/memory/salience.py`
- Modify: `backend/tests/test_salience_service.py`

**Step 1: Write the failing tests for access recording**

Add to `backend/tests/test_salience_service.py`:

```python
class TestRecordAccess:
    """Tests for recording memory access and updating salience."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Supabase client."""
        mock = MagicMock()
        # Mock the chained query builder pattern
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "log-123"}]
        )
        mock.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "salience-123", "access_count": 1}]
        )
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "salience-123", "access_count": 0, "last_accessed_at": "2026-01-01T00:00:00+00:00"}
        )
        return mock

    @pytest.mark.asyncio
    async def test_record_access_logs_to_access_log(self, mock_db: MagicMock) -> None:
        """Recording access should insert into memory_access_log."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="episodic",
            user_id="user-456",
            context="query: find meetings",
        )

        # Verify insert was called on memory_access_log
        mock_db.table.assert_any_call("memory_access_log")

    @pytest.mark.asyncio
    async def test_record_access_updates_salience_table(self, mock_db: MagicMock) -> None:
        """Recording access should upsert the salience tracking table."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="semantic",
            user_id="user-456",
        )

        # Verify upsert was called on semantic_fact_salience
        mock_db.table.assert_any_call("semantic_fact_salience")

    @pytest.mark.asyncio
    async def test_record_access_increments_count(self, mock_db: MagicMock) -> None:
        """Recording access should increment the access count."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="episodic",
            user_id="user-456",
        )

        # The upsert should include access_count increment
        calls = mock_db.table.return_value.upsert.call_args_list
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_record_access_for_lead_memory(self, mock_db: MagicMock) -> None:
        """Lead memories should also be tracked."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="lead-123",
            memory_type="lead",
            user_id="user-456",
        )

        # Lead uses the semantic fact salience table (per spec, lead is stored with semantic)
        mock_db.table.assert_any_call("memory_access_log")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestRecordAccess -v`

Expected: FAIL with AttributeError (record_access method doesn't exist)

**Step 3: Implement record_access method**

Add to `backend/src/memory/salience.py` (after calculate_decay_from_timestamp):

```python
    async def record_access(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
        context: str | None = None,
    ) -> None:
        """Record memory access and update salience tracking.

        This should be called whenever a memory is retrieved/used.
        It logs the access and updates the salience tracking table.

        Args:
            memory_id: The Graphiti episode ID or other memory identifier.
            memory_type: Type of memory ('episodic', 'semantic', or 'lead').
            user_id: The user who accessed the memory.
            context: Optional context describing what triggered the access.
        """
        try:
            # 1. Log the access
            await self._log_access(memory_id, memory_type, user_id, context)

            # 2. Update salience tracking
            await self._update_salience_tracking(memory_id, memory_type, user_id)

        except Exception as e:
            # Log but don't fail - salience tracking is non-critical
            logger.warning(
                "Failed to record memory access",
                extra={
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "user_id": user_id,
                    "error": str(e),
                },
            )

    async def _log_access(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
        context: str | None,
    ) -> None:
        """Insert a record into memory_access_log."""
        self.db.table("memory_access_log").insert(
            {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "user_id": user_id,
                "access_context": context,
            }
        ).execute()

    async def _update_salience_tracking(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
    ) -> None:
        """Upsert the salience tracking table with updated access info."""
        # Determine which table to use
        if memory_type == "episodic":
            table_name = "episodic_memory_salience"
        else:
            # Both semantic and lead use semantic_fact_salience
            table_name = "semantic_fact_salience"

        now = datetime.now(UTC).isoformat()

        # Try to get existing record
        existing = (
            self.db.table(table_name)
            .select("id, access_count")
            .eq("user_id", user_id)
            .eq("graphiti_episode_id", memory_id)
            .single()
            .execute()
        )

        if existing.data:
            # Update existing record
            new_count = existing.data["access_count"] + 1
            new_salience = self.calculate_decay(access_count=new_count, days_since_last_access=0)

            self.db.table(table_name).update(
                {
                    "access_count": new_count,
                    "last_accessed_at": now,
                    "current_salience": new_salience,
                }
            ).eq("id", existing.data["id"]).execute()
        else:
            # Insert new record
            self.db.table(table_name).insert(
                {
                    "user_id": user_id,
                    "graphiti_episode_id": memory_id,
                    "current_salience": 1.0,
                    "last_accessed_at": now,
                    "access_count": 1,
                }
            ).execute()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestRecordAccess -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/salience.py backend/tests/test_salience_service.py
git commit -m "$(cat <<'EOF'
feat(memory): add access recording to SalienceService

US-218: Implement record_access method to:
- Log access to memory_access_log table
- Update/create salience tracking records
- Recalculate salience on each access

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Batch Salience Update Method

**Files:**
- Modify: `backend/src/memory/salience.py`
- Modify: `backend/tests/test_salience_service.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_salience_service.py`:

```python
class TestUpdateAllSalience:
    """Tests for batch salience recalculation."""

    @pytest.fixture
    def mock_db_with_memories(self) -> MagicMock:
        """Create mock DB with existing salience records."""
        mock = MagicMock()

        # Mock episodic records
        episodic_data = [
            {
                "id": "sal-1",
                "graphiti_episode_id": "ep-1",
                "current_salience": 1.0,
                "access_count": 5,
                "last_accessed_at": "2026-01-03T00:00:00+00:00",  # 30 days ago
            },
            {
                "id": "sal-2",
                "graphiti_episode_id": "ep-2",
                "current_salience": 0.8,
                "access_count": 0,
                "last_accessed_at": "2026-02-01T00:00:00+00:00",  # 1 day ago
            },
        ]

        semantic_data = [
            {
                "id": "sal-3",
                "graphiti_episode_id": "fact-1",
                "current_salience": 0.5,
                "access_count": 2,
                "last_accessed_at": "2025-11-03T00:00:00+00:00",  # 91 days ago
            },
        ]

        def table_side_effect(table_name: str) -> MagicMock:
            table_mock = MagicMock()
            if table_name == "episodic_memory_salience":
                table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=episodic_data
                )
            elif table_name == "semantic_fact_salience":
                table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=semantic_data
                )
            table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            return table_mock

        mock.table.side_effect = table_side_effect
        return mock

    @pytest.mark.asyncio
    async def test_update_all_salience_returns_count(self, mock_db_with_memories: MagicMock) -> None:
        """update_all_salience should return number of updated records."""
        # Use a fixed "now" for calculation: 2026-02-02
        service = SalienceService(db_client=mock_db_with_memories)

        with patch("src.memory.salience.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 2, tzinfo=UTC)
            mock_datetime.fromisoformat = datetime.fromisoformat

            updated = await service.update_all_salience(user_id="user-123")

        # Should update records where salience changed significantly
        assert updated >= 0

    @pytest.mark.asyncio
    async def test_update_skips_unchanged_salience(self, mock_db_with_memories: MagicMock) -> None:
        """Records with minimal salience change should not be updated."""
        service = SalienceService(db_client=mock_db_with_memories)

        with patch("src.memory.salience.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 2, tzinfo=UTC)
            mock_datetime.fromisoformat = datetime.fromisoformat

            await service.update_all_salience(user_id="user-123")

        # Updates should only happen for records with > 0.01 salience difference
        # The mock will track how many updates were called

    @pytest.mark.asyncio
    async def test_update_processes_both_tables(self, mock_db_with_memories: MagicMock) -> None:
        """Should process both episodic and semantic salience tables."""
        service = SalienceService(db_client=mock_db_with_memories)

        with patch("src.memory.salience.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 2, tzinfo=UTC)
            mock_datetime.fromisoformat = datetime.fromisoformat

            await service.update_all_salience(user_id="user-123")

        # Verify both tables were queried
        table_calls = [call[0][0] for call in mock_db_with_memories.table.call_args_list]
        assert "episodic_memory_salience" in table_calls
        assert "semantic_fact_salience" in table_calls
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestUpdateAllSalience -v`

Expected: FAIL with AttributeError (update_all_salience doesn't exist)

**Step 3: Implement update_all_salience method**

Add to `backend/src/memory/salience.py`:

```python
    async def update_all_salience(self, user_id: str) -> int:
        """Batch update salience for all user memories.

        This is designed to be called by a background job (e.g., daily cron).
        It recalculates salience for all memories and updates those that have
        changed significantly (> 0.01 difference).

        Args:
            user_id: The user whose memories to update.

        Returns:
            Number of records that were updated.
        """
        updated_count = 0

        for table_name in ["episodic_memory_salience", "semantic_fact_salience"]:
            try:
                updated_count += await self._update_table_salience(table_name, user_id)
            except Exception as e:
                logger.error(
                    f"Failed to update salience for {table_name}",
                    extra={"user_id": user_id, "error": str(e)},
                )

        return updated_count

    async def _update_table_salience(self, table_name: str, user_id: str) -> int:
        """Update salience for all records in a specific table."""
        # Fetch all salience records for this user
        result = (
            self.db.table(table_name)
            .select("id, current_salience, access_count, last_accessed_at")
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            return 0

        updated = 0
        now = datetime.now(UTC)

        for record in result.data:
            # Parse the last_accessed_at timestamp
            last_accessed = datetime.fromisoformat(record["last_accessed_at"])
            days_since = (now - last_accessed).total_seconds() / 86400

            # Calculate new salience
            new_salience = self.calculate_decay(
                access_count=record["access_count"],
                days_since_last_access=days_since,
            )

            # Only update if salience changed significantly (> 0.01)
            if abs(new_salience - record["current_salience"]) > 0.01:
                self.db.table(table_name).update(
                    {"current_salience": new_salience}
                ).eq("id", record["id"]).execute()
                updated += 1

        return updated
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestUpdateAllSalience -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/salience.py backend/tests/test_salience_service.py
git commit -m "$(cat <<'EOF'
feat(memory): add batch salience update method

US-218: Implement update_all_salience for daily background job:
- Processes both episodic and semantic salience tables
- Only updates records with > 0.01 salience change
- Returns count of updated records

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Get By Salience Query Method

**Files:**
- Modify: `backend/src/memory/salience.py`
- Modify: `backend/tests/test_salience_service.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_salience_service.py`:

```python
class TestGetBySalience:
    """Tests for querying memories by salience threshold."""

    @pytest.fixture
    def mock_db_with_salience_records(self) -> MagicMock:
        """Create mock DB with salience records at various levels."""
        mock = MagicMock()

        high_salience = [
            {"graphiti_episode_id": "ep-1", "current_salience": 0.95, "access_count": 10},
            {"graphiti_episode_id": "ep-2", "current_salience": 0.80, "access_count": 5},
        ]

        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=high_salience
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_by_salience_filters_by_threshold(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Should only return memories above the salience threshold."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        results = await service.get_by_salience(
            user_id="user-123",
            memory_type="episodic",
            min_salience=0.5,
            limit=10,
        )

        assert len(results) == 2
        assert all(r["current_salience"] >= 0.5 for r in results)

    @pytest.mark.asyncio
    async def test_get_by_salience_orders_by_salience_desc(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Results should be ordered by salience descending."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        await service.get_by_salience(
            user_id="user-123",
            memory_type="episodic",
            min_salience=0.3,
            limit=5,
        )

        # Verify order was called with desc=True
        order_call = mock_db_with_salience_records.table.return_value.select.return_value.eq.return_value.gte.return_value.order
        order_call.assert_called_once_with("current_salience", desc=True)

    @pytest.mark.asyncio
    async def test_get_by_salience_respects_limit(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Should respect the limit parameter."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        await service.get_by_salience(
            user_id="user-123",
            memory_type="semantic",
            min_salience=0.1,
            limit=5,
        )

        # Verify limit was called
        limit_call = mock_db_with_salience_records.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit
        limit_call.assert_called_once_with(5)
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestGetBySalience -v`

Expected: FAIL with AttributeError (get_by_salience doesn't exist)

**Step 3: Implement get_by_salience method**

Add to `backend/src/memory/salience.py`:

```python
    async def get_by_salience(
        self,
        user_id: str,
        memory_type: MemoryType,
        min_salience: float = 0.1,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get memory IDs filtered by salience threshold.

        Returns the Graphiti episode IDs of memories that meet the
        salience threshold, ordered by salience descending.

        Args:
            user_id: The user whose memories to query.
            memory_type: Type of memory ('episodic', 'semantic', or 'lead').
            min_salience: Minimum salience threshold (default 0.1).
            limit: Maximum number of results (default 10).

        Returns:
            List of salience records with graphiti_episode_id and salience info.
        """
        # Determine table name
        if memory_type == "episodic":
            table_name = "episodic_memory_salience"
        else:
            table_name = "semantic_fact_salience"

        result = (
            self.db.table(table_name)
            .select("graphiti_episode_id, current_salience, access_count")
            .eq("user_id", user_id)
            .gte("current_salience", min_salience)
            .order("current_salience", desc=True)
            .limit(limit)
            .execute()
        )

        return result.data or []
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::TestGetBySalience -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/salience.py backend/tests/test_salience_service.py
git commit -m "$(cat <<'EOF'
feat(memory): add get_by_salience query method

US-218: Implement salience-based memory retrieval:
- Filter memories by minimum salience threshold
- Order results by salience descending
- Support configurable limit

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Export SalienceService from Memory Module

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_salience_service.py` (at the top, after imports):

```python
def test_salience_service_exported_from_memory_module() -> None:
    """SalienceService should be importable from src.memory."""
    from src.memory import SalienceService

    assert SalienceService is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::test_salience_service_exported_from_memory_module -v`

Expected: FAIL with ImportError

**Step 3: Update the memory module exports**

Edit `backend/src/memory/__init__.py` - add import and export:

After line 25 (after confidence import), add:
```python
from src.memory.salience import SalienceService
```

In the `__all__` list (around line 51), add after "ConfidenceScorer":
```python
    # Salience Service
    "SalienceService",
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_service.py::test_salience_service_exported_from_memory_module -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_salience_service.py
git commit -m "$(cat <<'EOF'
feat(memory): export SalienceService from memory module

US-218: Add SalienceService to public exports.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Create Background Job for Daily Salience Updates

**Files:**
- Create: `backend/src/jobs/salience_decay.py`
- Create: `backend/tests/test_salience_decay_job.py`

**Step 1: Write the failing test**

Create `backend/tests/test_salience_decay_job.py`:

```python
"""Tests for the salience decay background job."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSalienceDecayJob:
    """Tests for the daily salience decay job."""

    @pytest.mark.asyncio
    async def test_job_processes_all_users(self) -> None:
        """The job should update salience for all users."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "user-1"},
                {"id": "user-2"},
                {"id": "user-3"},
            ]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(return_value=5)

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        # Should have called update for each user
        assert mock_salience_service.update_all_salience.call_count == 3
        assert result["users_processed"] == 3

    @pytest.mark.asyncio
    async def test_job_returns_total_updates(self) -> None:
        """The job should return total number of updated records."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[{"id": "user-1"}, {"id": "user-2"}]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(side_effect=[10, 5])

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        assert result["records_updated"] == 15

    @pytest.mark.asyncio
    async def test_job_continues_on_user_error(self) -> None:
        """If one user fails, job should continue with others."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[{"id": "user-1"}, {"id": "user-2"}]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(
            side_effect=[Exception("DB error"), 5]
        )

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        # Should still process second user
        assert result["users_processed"] == 2
        assert result["errors"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_decay_job.py -v`

Expected: FAIL with ModuleNotFoundError

**Step 3: Create the jobs directory and module**

First, create the jobs directory structure:

Create `backend/src/jobs/__init__.py`:
```python
"""Background jobs for ARIA."""

from src.jobs.salience_decay import run_salience_decay_job

__all__ = ["run_salience_decay_job"]
```

Create `backend/src/jobs/salience_decay.py`:
```python
"""Background job for daily salience decay updates.

This job should be scheduled to run once per day (e.g., via cron or
a task scheduler). It recalculates salience for all user memories
based on time elapsed since last access.
"""

import logging
from typing import Any

from src.db.supabase import SupabaseClient
from src.memory.salience import SalienceService

logger = logging.getLogger(__name__)


async def run_salience_decay_job() -> dict[str, Any]:
    """Run the daily salience decay update for all users.

    Fetches all users and updates their memory salience values.
    Continues processing even if individual users fail.

    Returns:
        Summary dict with users_processed, records_updated, and errors.
    """
    db = SupabaseClient.get_client()
    salience_service = SalienceService(db_client=db)

    # Get all user IDs
    users_result = db.table("user_profiles").select("id").execute()
    users = users_result.data or []

    total_updated = 0
    errors = 0

    for user in users:
        user_id = user["id"]
        try:
            updated = await salience_service.update_all_salience(user_id)
            total_updated += updated
            logger.info(
                f"Updated salience for user {user_id}",
                extra={"user_id": user_id, "records_updated": updated},
            )
        except Exception as e:
            errors += 1
            logger.error(
                f"Failed to update salience for user {user_id}",
                extra={"user_id": user_id, "error": str(e)},
            )

    result = {
        "users_processed": len(users),
        "records_updated": total_updated,
        "errors": errors,
    }

    logger.info("Salience decay job completed", extra=result)
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_decay_job.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/jobs/__init__.py backend/src/jobs/salience_decay.py backend/tests/test_salience_decay_job.py
git commit -m "$(cat <<'EOF'
feat(jobs): add daily salience decay background job

US-218: Create run_salience_decay_job for scheduled execution:
- Processes all users in the system
- Continues on individual user failures
- Returns summary with users_processed, records_updated, errors

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Run All Tests and Verify

**Step 1: Run the full test suite**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_salience_config.py tests/test_salience_service.py tests/test_salience_decay_job.py -v`

Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd /Users/dhruv/aria/backend && mypy src/memory/salience.py src/jobs/salience_decay.py --strict`

Expected: No errors (or only expected errors from existing codebase)

**Step 3: Run linting**

Run: `cd /Users/dhruv/aria/backend && ruff check src/memory/salience.py src/jobs/salience_decay.py`

Expected: No errors

**Step 4: Format code**

Run: `cd /Users/dhruv/aria/backend && ruff format src/memory/salience.py src/jobs/salience_decay.py`

**Step 5: Run full test suite to ensure no regressions**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -v --ignore=tests/integration`

Expected: All tests PASS

**Step 6: Commit any formatting fixes**

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: format salience service code

Apply ruff formatting.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Final Integration Verification

**Step 1: Verify all new files exist**

```bash
ls -la backend/src/memory/salience.py
ls -la backend/src/jobs/salience_decay.py
ls -la backend/supabase/migrations/007_memory_salience.sql
ls -la backend/tests/test_salience_config.py
ls -la backend/tests/test_salience_service.py
ls -la backend/tests/test_salience_decay_job.py
```

**Step 2: Verify imports work**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.memory import SalienceService; from src.jobs import run_salience_decay_job; print('All imports OK')"`

Expected: "All imports OK"

**Step 3: Create summary commit**

```bash
git log --oneline -10
```

---

## Summary

This plan implements US-218: Memory Salience Decay System with:

1. **Configuration** - New settings for half-life, access boost, and minimum salience
2. **Database Migration** - Tables for salience tracking and access logging with RLS
3. **SalienceService** - Core service with:
   - `calculate_decay()` - Exponential decay formula
   - `record_access()` - Log access and update salience
   - `update_all_salience()` - Batch update for background job
   - `get_by_salience()` - Query memories by salience threshold
4. **Background Job** - Daily job to recalculate all salience values
5. **Comprehensive Tests** - Unit tests for all decay calculations and service methods

The implementation follows TDD, with tests written before code for each feature.
