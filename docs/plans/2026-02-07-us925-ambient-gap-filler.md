# US-925: Continuous Onboarding Loop (Ambient Gap Filling) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a background service that proactively fills knowledge gaps after formal onboarding ends, through natural conversation prompts — NOT pop-ups.

**Architecture:** The `AmbientGapFiller` service runs daily per user. It checks readiness sub-scores against a configurable threshold (default 60%), applies anti-nagging spacing logic (min 3 days between prompts, max 2/week), picks the highest-impact gap, generates a natural prompt, and stores it for pickup by the chat service. Two API endpoints let the chat service retrieve pending prompts and record user engagement outcomes. Outcomes feed into procedural memory for future prompt strategy optimization.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (`onboarding_state`, `prospective_memories`, `ambient_prompts`), Pydantic models, existing `OnboardingReadinessService` (US-913), existing `KnowledgeGapDetector` (US-912), existing `OnboardingOutcomeTracker` (US-924)

---

## File Structure

```
backend/src/onboarding/
├── ambient_gap_filler.py          # NEW: AmbientGapFiller service class

backend/src/api/routes/
├── ambient_onboarding.py          # NEW: API routes for ambient prompts

backend/tests/
├── test_ambient_gap_filler.py     # NEW: Comprehensive unit tests

backend/supabase/migrations/
├── 20260207160000_ambient_prompts.sql  # NEW: Database table for prompt tracking
```

---

## Task 1: Create Database Migration for Ambient Prompts

**Files:**
- Create: `backend/supabase/migrations/20260207160000_ambient_prompts.sql`

**Step 1: Create the migration file**

```sql
-- US-925: Ambient Gap Filling prompt tracking
-- Stores pending and historical ambient prompts for continuous onboarding

CREATE TABLE IF NOT EXISTS ambient_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    domain TEXT NOT NULL,         -- readiness domain: corporate_memory, digital_twin, etc.
    prompt TEXT NOT NULL,         -- natural language prompt text
    score FLOAT NOT NULL,        -- readiness score at time of generation
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, delivered, engaged, dismissed, deferred
    metadata JSONB DEFAULT '{}', -- additional context (gap details, generation params)
    created_at TIMESTAMPTZ DEFAULT now(),
    delivered_at TIMESTAMPTZ,    -- when shown to user in conversation
    resolved_at TIMESTAMPTZ      -- when user engaged/dismissed/deferred
);

-- Index for fast lookup of pending prompts per user
CREATE INDEX idx_ambient_prompts_user_pending
    ON ambient_prompts(user_id, status) WHERE status = 'pending';

-- Index for weekly count queries
CREATE INDEX idx_ambient_prompts_user_created
    ON ambient_prompts(user_id, created_at DESC);

-- RLS
ALTER TABLE ambient_prompts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_ambient_prompts" ON ambient_prompts
    FOR ALL TO authenticated USING (user_id = auth.uid());
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260207160000_ambient_prompts.sql
git commit -m "feat(US-925): add ambient_prompts migration for continuous onboarding"
```

---

## Task 2: Write Failing Tests for AmbientGapFiller

**Files:**
- Create: `backend/tests/test_ambient_gap_filler.py`

**Step 1: Write the complete test suite**

```python
"""Tests for US-925: Continuous Onboarding Loop (Ambient Gap Filling).

Tests cover:
- Readiness threshold detection: domains below 60% trigger prompts
- Anti-nagging spacing: minimum 3 days between prompts
- Weekly limit enforcement: max 2 prompts per week
- Priority domain selection: lowest score domain chosen first
- Prompt generation per domain: natural, non-intrusive text
- Prompt storage and retrieval for chat service pickup
- Outcome tracking: engaged, dismissed, deferred
- Procedural memory integration: outcomes feed learning
- All-above-threshold: no prompt generated
- Edge cases: no onboarding state, empty readiness
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.ambient_gap_filler import AmbientGapFiller


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Create a mock Supabase client."""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_response
    )
    mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
        mock_response
    )
    mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = (
        mock_response
    )
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = (
        mock_response
    )
    mock.table.return_value.insert.return_value.execute.return_value = mock_response
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        mock_response
    )
    return mock


@pytest.fixture
def filler(mock_supabase: MagicMock) -> AmbientGapFiller:
    """Create an AmbientGapFiller with mocked DB."""
    with patch("src.onboarding.ambient_gap_filler.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_supabase
        svc = AmbientGapFiller()
    return svc


# ---------------------------------------------------------------------------
# Threshold detection
# ---------------------------------------------------------------------------


class TestThresholdDetection:
    """Test readiness sub-score threshold detection."""

    @pytest.mark.asyncio
    async def test_all_scores_above_threshold_returns_none(
        self, filler: AmbientGapFiller
    ) -> None:
        """When all readiness scores >= 60, no prompt generated."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 76.0,
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_one_score_below_threshold_generates_prompt(
        self, filler: AmbientGapFiller
    ) -> None:
        """When one domain is below 60, a prompt is generated for that domain."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 40.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 70.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=None):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=0):
                    with patch.object(
                        filler, "_store_pending_prompt", new_callable=AsyncMock
                    ):
                        with patch.object(
                            filler,
                            "_record_prompt_generated",
                            new_callable=AsyncMock,
                        ):
                            result = await filler.check_and_generate("user-123")

                            assert result is not None
                            assert result["domain"] == "digital_twin"
                            assert result["type"] == "ambient_gap_fill"
                            assert result["score"] == 40.0

    @pytest.mark.asyncio
    async def test_picks_lowest_score_domain(
        self, filler: AmbientGapFiller
    ) -> None:
        """When multiple domains are below threshold, picks the lowest."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 30.0,
                "digital_twin": 45.0,
                "relationship_graph": 55.0,
                "integrations": 10.0,
                "goal_clarity": 75.0,
                "overall": 43.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=None):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=0):
                    with patch.object(
                        filler, "_store_pending_prompt", new_callable=AsyncMock
                    ):
                        with patch.object(
                            filler,
                            "_record_prompt_generated",
                            new_callable=AsyncMock,
                        ):
                            result = await filler.check_and_generate("user-123")

                            assert result is not None
                            assert result["domain"] == "integrations"
                            assert result["score"] == 10.0


# ---------------------------------------------------------------------------
# Anti-nagging spacing
# ---------------------------------------------------------------------------


class TestSpacingEnforcement:
    """Test minimum spacing between prompts."""

    @pytest.mark.asyncio
    async def test_too_soon_since_last_prompt_returns_none(
        self, filler: AmbientGapFiller
    ) -> None:
        """If last prompt was < 3 days ago, returns None."""
        recent_time = datetime.now(UTC) - timedelta(days=1)
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 20.0,
                "digital_twin": 40.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 58.0,
            },
        ):
            with patch.object(
                filler, "_get_last_prompt_time", return_value=recent_time
            ):
                result = await filler.check_and_generate("user-123")
                assert result is None

    @pytest.mark.asyncio
    async def test_enough_time_since_last_prompt_generates(
        self, filler: AmbientGapFiller
    ) -> None:
        """If last prompt was >= 3 days ago, generates a prompt."""
        old_time = datetime.now(UTC) - timedelta(days=4)
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 20.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 64.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=old_time):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=0):
                    with patch.object(
                        filler, "_store_pending_prompt", new_callable=AsyncMock
                    ):
                        with patch.object(
                            filler,
                            "_record_prompt_generated",
                            new_callable=AsyncMock,
                        ):
                            result = await filler.check_and_generate("user-123")
                            assert result is not None
                            assert result["domain"] == "corporate_memory"

    @pytest.mark.asyncio
    async def test_no_previous_prompt_generates(
        self, filler: AmbientGapFiller
    ) -> None:
        """If no previous prompt exists, generates one."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 50.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 70.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=None):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=0):
                    with patch.object(
                        filler, "_store_pending_prompt", new_callable=AsyncMock
                    ):
                        with patch.object(
                            filler,
                            "_record_prompt_generated",
                            new_callable=AsyncMock,
                        ):
                            result = await filler.check_and_generate("user-123")
                            assert result is not None


# ---------------------------------------------------------------------------
# Weekly limit
# ---------------------------------------------------------------------------


class TestWeeklyLimit:
    """Test max 2 prompts per week enforcement."""

    @pytest.mark.asyncio
    async def test_weekly_limit_reached_returns_none(
        self, filler: AmbientGapFiller
    ) -> None:
        """If 2+ prompts sent this week, returns None."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 20.0,
                "digital_twin": 40.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 58.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=None):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=2):
                    result = await filler.check_and_generate("user-123")
                    assert result is None

    @pytest.mark.asyncio
    async def test_below_weekly_limit_generates(
        self, filler: AmbientGapFiller
    ) -> None:
        """If < 2 prompts this week, generates a prompt."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 20.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 64.0,
            },
        ):
            with patch.object(filler, "_get_last_prompt_time", return_value=None):
                with patch.object(filler, "_get_weekly_prompt_count", return_value=1):
                    with patch.object(
                        filler, "_store_pending_prompt", new_callable=AsyncMock
                    ):
                        with patch.object(
                            filler,
                            "_record_prompt_generated",
                            new_callable=AsyncMock,
                        ):
                            result = await filler.check_and_generate("user-123")
                            assert result is not None


# ---------------------------------------------------------------------------
# Prompt generation per domain
# ---------------------------------------------------------------------------


class TestPromptGeneration:
    """Test natural prompt generation per readiness domain."""

    @pytest.mark.asyncio
    async def test_digital_twin_prompt(self, filler: AmbientGapFiller) -> None:
        """Digital twin domain generates writing-style prompt."""
        result = await filler._generate_prompt("user-1", "digital_twin", 40.0)
        assert result["domain"] == "digital_twin"
        assert "writing style" in result["prompt"].lower() or "email" in result["prompt"].lower()
        assert result["type"] == "ambient_gap_fill"

    @pytest.mark.asyncio
    async def test_corporate_memory_prompt(self, filler: AmbientGapFiller) -> None:
        """Corporate memory domain generates product-related prompt."""
        result = await filler._generate_prompt("user-1", "corporate_memory", 30.0)
        assert result["domain"] == "corporate_memory"
        assert "company" in result["prompt"].lower() or "product" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_relationship_graph_prompt(self, filler: AmbientGapFiller) -> None:
        """Relationship graph domain generates contacts prompt."""
        result = await filler._generate_prompt("user-1", "relationship_graph", 25.0)
        assert result["domain"] == "relationship_graph"
        assert "contact" in result["prompt"].lower() or "people" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_integrations_prompt(self, filler: AmbientGapFiller) -> None:
        """Integrations domain generates connection prompt."""
        result = await filler._generate_prompt("user-1", "integrations", 15.0)
        assert result["domain"] == "integrations"
        assert "connect" in result["prompt"].lower() or "calendar" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_goal_clarity_prompt(self, filler: AmbientGapFiller) -> None:
        """Goal clarity domain generates goal-related prompt."""
        result = await filler._generate_prompt("user-1", "goal_clarity", 20.0)
        assert result["domain"] == "goal_clarity"
        assert "goal" in result["prompt"].lower() or "working on" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_unknown_domain_generates_fallback(
        self, filler: AmbientGapFiller
    ) -> None:
        """Unknown domain generates a generic fallback prompt."""
        result = await filler._generate_prompt("user-1", "unknown_domain", 30.0)
        assert result["domain"] == "unknown_domain"
        assert len(result["prompt"]) > 0


# ---------------------------------------------------------------------------
# Pending prompt retrieval
# ---------------------------------------------------------------------------


class TestPendingPromptRetrieval:
    """Test retrieving pending prompts for chat service."""

    @pytest.mark.asyncio
    async def test_get_pending_returns_prompt(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Returns the oldest pending prompt."""
        prompt_data = {
            "id": "prompt-123",
            "domain": "digital_twin",
            "prompt": "Forward me some emails",
            "score": 40.0,
            "status": "pending",
        }
        mock_response = MagicMock()
        mock_response.data = prompt_data
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = (
            mock_response
        )

        result = await filler.get_pending_prompt("user-123")
        assert result is not None
        assert result["id"] == "prompt-123"

    @pytest.mark.asyncio
    async def test_get_pending_returns_none_when_empty(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Returns None when no pending prompts exist."""
        mock_response = MagicMock()
        mock_response.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = (
            mock_response
        )

        result = await filler.get_pending_prompt("user-123")
        assert result is None


# ---------------------------------------------------------------------------
# Outcome tracking
# ---------------------------------------------------------------------------


class TestOutcomeTracking:
    """Test recording prompt engagement outcomes."""

    @pytest.mark.asyncio
    async def test_record_engaged_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'engaged' outcome and updates prompt status."""
        await filler.record_outcome("user-123", "prompt-123", "engaged")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_record_dismissed_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'dismissed' outcome."""
        await filler.record_outcome("user-123", "prompt-123", "dismissed")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_record_deferred_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'deferred' outcome."""
        await filler.record_outcome("user-123", "prompt-123", "deferred")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_outcome_stores_to_procedural_memory(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Engaged outcomes create procedural memory entries."""
        # Get the prompt data so we can verify procedural insert
        mock_prompt_response = MagicMock()
        mock_prompt_response.data = {
            "id": "prompt-123",
            "domain": "digital_twin",
            "prompt": "Forward me some emails",
            "score": 40.0,
            "status": "delivered",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            mock_prompt_response
        )

        await filler.record_outcome("user-123", "prompt-123", "engaged")

        # Verify insert was called (for procedural memory)
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_no_readiness_data_returns_none(
        self, filler: AmbientGapFiller
    ) -> None:
        """If readiness service returns empty, no prompt generated."""
        with patch.object(filler, "_get_readiness", return_value={}):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_readiness_error_returns_none(
        self, filler: AmbientGapFiller
    ) -> None:
        """If readiness fetch fails, returns None gracefully."""
        with patch.object(
            filler, "_get_readiness", side_effect=Exception("DB error")
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_overall_key_excluded_from_domain_check(
        self, filler: AmbientGapFiller
    ) -> None:
        """The 'overall' key should not be treated as a domain."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 30.0,  # Below threshold but should be excluded
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_confidence_modifier_excluded_from_domain_check(
        self, filler: AmbientGapFiller
    ) -> None:
        """The 'confidence_modifier' string key should not be treated as a domain."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 76.0,
                "confidence_modifier": "high",
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None
```

**Step 2: Run tests to verify they fail (RED phase)**

Run: `cd backend && python -m pytest tests/test_ambient_gap_filler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.onboarding.ambient_gap_filler'`

**Step 3: Commit test file**

```bash
git add backend/tests/test_ambient_gap_filler.py
git commit -m "test(US-925): add comprehensive tests for AmbientGapFiller service"
```

---

## Task 3: Implement AmbientGapFiller Service

**Files:**
- Create: `backend/src/onboarding/ambient_gap_filler.py`

**Step 1: Implement the service**

```python
"""US-925: Continuous Onboarding Loop (Ambient Gap Filling).

Background service that proactively fills knowledge gaps after formal
onboarding ends. Generates natural conversation prompts — NOT pop-ups —
woven into ARIA's natural interaction.

Builds on:
- US-912: KnowledgeGapDetector (identifies what ARIA doesn't know)
- US-913: OnboardingReadinessService (readiness sub-scores)
- US-924: OnboardingOutcomeTracker (procedural memory)

Theory of Mind: Don't nag busy users. Space prompts. Detect receptivity.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.onboarding.readiness import OnboardingReadinessService

logger = logging.getLogger(__name__)

# Domains that are NOT readiness sub-scores
_EXCLUDED_KEYS = {"overall", "confidence_modifier"}


class AmbientGapFiller:
    """Proactively fills knowledge gaps through natural interaction.

    Runs daily. If any readiness sub-score < threshold (default 60%),
    generates a natural prompt to surface in the next ARIA conversation.

    Theory of Mind aware: Don't nag busy users. Space prompts.
    """

    THRESHOLD = 60.0
    MIN_DAYS_BETWEEN_PROMPTS = 3
    MAX_PROMPTS_PER_WEEK = 2

    def __init__(self) -> None:
        """Initialize with database client and readiness service."""
        self._db = SupabaseClient.get_client()
        self._readiness_service = OnboardingReadinessService()

    async def check_and_generate(self, user_id: str) -> dict[str, Any] | None:
        """Check gaps and generate ambient prompt if appropriate.

        Steps:
        1. Get readiness scores
        2. Find domains below threshold
        3. Check spacing (don't nag)
        4. Check weekly limit
        5. Pick highest-impact gap (lowest score)
        6. Generate natural prompt
        7. Store for next conversation pickup
        8. Track generation event

        Args:
            user_id: The user to check and generate prompts for.

        Returns:
            Prompt dict if generated, None if no prompt needed or suppressed.
        """
        try:
            # 1. Check readiness scores
            readiness = await self._get_readiness(user_id)

            if not readiness:
                return None

            # 2. Find domains below threshold
            low_domains: dict[str, float] = {}
            for key, value in readiness.items():
                if key in _EXCLUDED_KEYS:
                    continue
                if not isinstance(value, (int, float)):
                    continue
                if value < self.THRESHOLD:
                    low_domains[key] = float(value)

            if not low_domains:
                return None

            # 3. Check spacing — don't nag
            last_prompt = await self._get_last_prompt_time(user_id)
            if last_prompt and self._too_soon(last_prompt):
                return None

            # 4. Check weekly limit
            weekly_count = await self._get_weekly_prompt_count(user_id)
            if weekly_count >= self.MAX_PROMPTS_PER_WEEK:
                return None

            # 5. Pick highest-impact gap (lowest score)
            priority_domain = min(low_domains, key=low_domains.get)  # type: ignore[arg-type]

            # 6. Generate natural prompt
            prompt = await self._generate_prompt(
                user_id, priority_domain, low_domains[priority_domain]
            )

            # 7. Store for next conversation pickup
            await self._store_pending_prompt(user_id, prompt)

            # 8. Track
            await self._record_prompt_generated(user_id, prompt)

            return prompt

        except Exception:
            logger.exception(
                "Error in ambient gap check",
                extra={"user_id": user_id},
            )
            return None

    def _too_soon(self, last_prompt_time: datetime) -> bool:
        """Check if last prompt was too recent.

        Args:
            last_prompt_time: Timestamp of last generated prompt.

        Returns:
            True if we should wait before sending another prompt.
        """
        min_gap = timedelta(days=self.MIN_DAYS_BETWEEN_PROMPTS)
        return datetime.now(UTC) - last_prompt_time < min_gap

    async def _get_readiness(self, user_id: str) -> dict[str, Any]:
        """Get readiness scores as a dict.

        Args:
            user_id: The user to get scores for.

        Returns:
            Dict of domain → score mappings.
        """
        breakdown = await self._readiness_service.get_readiness(user_id)
        return breakdown.model_dump()

    async def _get_last_prompt_time(self, user_id: str) -> datetime | None:
        """Get timestamp of most recent ambient prompt for user.

        Args:
            user_id: The user to check.

        Returns:
            Datetime of last prompt, or None if no prompts exist.
        """
        try:
            response = (
                self._db.table("ambient_prompts")
                .select("created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                row = response.data[0]
                if isinstance(row, dict) and row.get("created_at"):
                    ts = row["created_at"]
                    if isinstance(ts, str):
                        return datetime.fromisoformat(
                            ts.replace("Z", "+00:00")
                        )
            return None
        except Exception:
            logger.warning(
                "Failed to get last prompt time",
                extra={"user_id": user_id},
            )
            return None

    async def _get_weekly_prompt_count(self, user_id: str) -> int:
        """Count prompts generated for user in the last 7 days.

        Args:
            user_id: The user to count for.

        Returns:
            Number of prompts generated in the past week.
        """
        try:
            week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            response = (
                self._db.table("ambient_prompts")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", week_ago)
                .execute()
            )
            return len(response.data or [])
        except Exception:
            logger.warning(
                "Failed to get weekly prompt count",
                extra={"user_id": user_id},
            )
            return 0

    async def _generate_prompt(
        self, user_id: str, domain: str, score: float
    ) -> dict[str, Any]:
        """Generate a natural, non-intrusive prompt for a gap domain.

        Each domain has a carefully crafted prompt that feels like
        natural conversation, not a system notification.

        Args:
            user_id: The user who will receive the prompt.
            domain: The readiness domain to fill.
            score: Current readiness score for the domain.

        Returns:
            Prompt dict with domain, prompt text, score, and type.
        """
        prompts: dict[str, str] = {
            "digital_twin": (
                "I'd love to match your writing style more closely. "
                "Could you forward me a few recent emails? Even 3-4 "
                "would make a big difference in how I draft for you."
            ),
            "corporate_memory": (
                "I have some gaps in my understanding of your company's "
                "product lineup. When you have a moment, could you share "
                "a capabilities deck or product sheet?"
            ),
            "relationship_graph": (
                "I'd be much more effective if I knew more about your "
                "key contacts. Who are the 3-5 people you interact with most?"
            ),
            "integrations": (
                "Connecting your calendar would let me prepare meeting "
                "briefs automatically. Want to set that up?"
            ),
            "goal_clarity": (
                "What's the most important thing you're working on this "
                "week? Setting a specific goal helps me prioritize what "
                "I work on."
            ),
        }

        return {
            "domain": domain,
            "prompt": prompts.get(
                domain,
                f"I'd like to learn more about your {domain.replace('_', ' ')}.",
            ),
            "score": score,
            "type": "ambient_gap_fill",
        }

    async def _store_pending_prompt(
        self, user_id: str, prompt: dict[str, Any]
    ) -> None:
        """Store prompt in ambient_prompts table for chat service pickup.

        Args:
            user_id: The user to store the prompt for.
            prompt: The generated prompt data.
        """
        try:
            self._db.table("ambient_prompts").insert(
                {
                    "user_id": user_id,
                    "domain": prompt["domain"],
                    "prompt": prompt["prompt"],
                    "score": prompt["score"],
                    "status": "pending",
                    "metadata": {
                        "type": prompt["type"],
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                }
            ).execute()
        except Exception:
            logger.exception(
                "Failed to store pending prompt",
                extra={"user_id": user_id},
            )

    async def _record_prompt_generated(
        self, user_id: str, prompt: dict[str, Any]
    ) -> None:
        """Record prompt generation event for tracking.

        Args:
            user_id: The user who received the prompt.
            prompt: The generated prompt data.
        """
        logger.info(
            "Ambient gap prompt generated",
            extra={
                "user_id": user_id,
                "domain": prompt["domain"],
                "score": prompt["score"],
            },
        )

    async def get_pending_prompt(
        self, user_id: str
    ) -> dict[str, Any] | None:
        """Get pending ambient prompt for next conversation.

        Called by chat service before generating ARIA response to
        weave gap-filling into natural interaction.

        Args:
            user_id: The user to get a pending prompt for.

        Returns:
            Prompt dict or None if no pending prompts.
        """
        try:
            response = (
                self._db.table("ambient_prompts")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .order("created_at", desc=False)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if response.data and isinstance(response.data, dict):
                # Mark as delivered
                prompt_id = response.data.get("id")
                if prompt_id:
                    (
                        self._db.table("ambient_prompts")
                        .update(
                            {
                                "status": "delivered",
                                "delivered_at": datetime.now(UTC).isoformat(),
                            }
                        )
                        .eq("id", prompt_id)
                        .execute()
                    )
                return dict(response.data)
            return None
        except Exception:
            logger.exception(
                "Failed to get pending prompt",
                extra={"user_id": user_id},
            )
            return None

    async def record_outcome(
        self, user_id: str, prompt_id: str, outcome: str
    ) -> None:
        """Track prompt engagement outcome.

        Records whether user engaged, dismissed, or deferred the prompt.
        Engaged outcomes feed into procedural memory for better future
        prompt strategies.

        Args:
            user_id: The user who responded.
            prompt_id: The ambient_prompts row ID.
            outcome: One of "engaged", "dismissed", "deferred".
        """
        try:
            # Update prompt status
            self._db.table("ambient_prompts").update(
                {
                    "status": outcome,
                    "resolved_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", prompt_id).execute()

            # For engaged outcomes, record to procedural memory
            if outcome == "engaged":
                # Fetch prompt details for context
                prompt_response = (
                    self._db.table("ambient_prompts")
                    .select("*")
                    .eq("id", prompt_id)
                    .maybe_single()
                    .execute()
                )
                if prompt_response.data and isinstance(
                    prompt_response.data, dict
                ):
                    domain = prompt_response.data.get("domain", "unknown")
                    self._db.table("procedural_insights").insert(
                        {
                            "insight": (
                                f"Ambient gap-fill prompt for {domain} "
                                f"was effective — user engaged"
                            ),
                            "insight_type": "ambient_gap_fill",
                            "evidence_count": 1,
                            "confidence": 0.6,
                        }
                    ).execute()

            logger.info(
                "Ambient prompt outcome recorded",
                extra={
                    "user_id": user_id,
                    "prompt_id": prompt_id,
                    "outcome": outcome,
                },
            )
        except Exception:
            logger.exception(
                "Failed to record prompt outcome",
                extra={
                    "user_id": user_id,
                    "prompt_id": prompt_id,
                },
            )
```

**Step 2: Run tests to verify they pass (GREEN phase)**

Run: `cd backend && python -m pytest tests/test_ambient_gap_filler.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add backend/src/onboarding/ambient_gap_filler.py
git commit -m "feat(US-925): implement AmbientGapFiller service for continuous onboarding"
```

---

## Task 4: Create API Routes for Ambient Prompts

**Files:**
- Create: `backend/src/api/routes/ambient_onboarding.py`
- Modify: `backend/src/api/routes/__init__.py`
- Modify: `backend/src/main.py`

**Step 1: Create the route module**

```python
"""Ambient Onboarding API routes (US-925).

Endpoints for the chat service to retrieve pending ambient gap-fill
prompts and record user engagement outcomes.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.onboarding.ambient_gap_filler import AmbientGapFiller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ambient-onboarding", tags=["ambient-onboarding"])


class AmbientPromptResponse(BaseModel):
    """Response model for an ambient prompt."""

    id: str = Field(..., description="Prompt UUID")
    domain: str = Field(..., description="Readiness domain")
    prompt: str = Field(..., description="Natural language prompt text")
    score: float = Field(..., description="Readiness score when generated")
    status: str = Field(..., description="Prompt status")


class OutcomeRequest(BaseModel):
    """Request model for recording prompt outcome."""

    outcome: str = Field(
        ...,
        pattern="^(engaged|dismissed|deferred)$",
        description="User engagement outcome",
    )


@router.get(
    "/ambient-prompt",
    response_model=AmbientPromptResponse | None,
    status_code=status.HTTP_200_OK,
)
async def get_ambient_prompt(
    current_user: CurrentUser,
) -> AmbientPromptResponse | None:
    """Get pending ambient prompt for the current conversation.

    Called by the chat service before generating ARIA's response.
    Returns the oldest pending prompt, marking it as delivered.

    Args:
        current_user: The authenticated user (auto-injected).

    Returns:
        AmbientPromptResponse if a prompt exists, None (204) otherwise.
    """
    try:
        filler = AmbientGapFiller()
        prompt = await filler.get_pending_prompt(current_user.id)

        if prompt is None:
            return None

        return AmbientPromptResponse(
            id=prompt.get("id", ""),
            domain=prompt.get("domain", ""),
            prompt=prompt.get("prompt", ""),
            score=float(prompt.get("score", 0.0)),
            status=prompt.get("status", "delivered"),
        )
    except Exception as e:
        logger.exception("Error fetching ambient prompt")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ambient prompt",
        ) from e


@router.post(
    "/ambient-prompt/{prompt_id}/outcome",
    status_code=status.HTTP_200_OK,
)
async def record_prompt_outcome(
    prompt_id: str,
    request: OutcomeRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Record user engagement outcome for an ambient prompt.

    Tracks whether user engaged (provided data), dismissed (ignored),
    or deferred (acknowledged but not now). Engaged outcomes feed
    procedural memory for future prompt optimization.

    Args:
        prompt_id: The ambient prompt UUID.
        request: The outcome to record.
        current_user: The authenticated user (auto-injected).

    Returns:
        Confirmation message.
    """
    try:
        filler = AmbientGapFiller()
        await filler.record_outcome(
            current_user.id, prompt_id, request.outcome
        )
        return {"status": "recorded", "outcome": request.outcome}
    except Exception as e:
        logger.exception("Error recording prompt outcome")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record outcome",
        ) from e
```

**Step 2: Register the route in `__init__.py`**

Add to `backend/src/api/routes/__init__.py`:

```python
from src.api.routes import ambient_onboarding as ambient_onboarding
```

**Step 3: Register the router in `main.py`**

Add to imports in `backend/src/main.py`:

```python
    ambient_onboarding,
```

Add router registration (near the other `include_router` calls):

```python
app.include_router(ambient_onboarding.router, prefix="/api/v1")
```

**Step 4: Run quality gate on new route**

Run: `cd backend && python -m pytest tests/test_ambient_gap_filler.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/ambient_onboarding.py backend/src/api/routes/__init__.py backend/src/main.py
git commit -m "feat(US-925): add API routes for ambient prompt retrieval and outcome tracking"
```

---

## Task 5: Run Quality Gates

**Files:**
- All US-925 files

**Step 1: Run all tests**

Run: `cd backend && python -m pytest tests/test_ambient_gap_filler.py -v`
Expected: ALL PASS

**Step 2: Run ruff format**

Run: `cd backend && ruff format src/onboarding/ambient_gap_filler.py src/api/routes/ambient_onboarding.py tests/test_ambient_gap_filler.py`
Expected: No changes or minor formatting fixes

**Step 3: Run ruff check**

Run: `cd backend && ruff check src/onboarding/ambient_gap_filler.py src/api/routes/ambient_onboarding.py tests/test_ambient_gap_filler.py`
Expected: PASS (no lint errors)

**Step 4: Run mypy**

Run: `cd backend && mypy src/onboarding/ambient_gap_filler.py src/api/routes/ambient_onboarding.py --strict`
Expected: PASS (no type errors)

**Step 5: Verify imports work end-to-end**

Run: `cd backend && python -c "from src.onboarding.ambient_gap_filler import AmbientGapFiller; print('Import OK')"`
Expected: Prints "Import OK"

**Step 6: Commit any formatting fixes**

```bash
git add -A
git commit -m "style(US-925): apply formatting fixes from quality gates"
```

(Skip this commit if no changes were made.)

---

## Summary of Changes

### New Files
1. `backend/supabase/migrations/20260207160000_ambient_prompts.sql` — Database table for prompt tracking
2. `backend/src/onboarding/ambient_gap_filler.py` — AmbientGapFiller service
3. `backend/src/api/routes/ambient_onboarding.py` — API routes
4. `backend/tests/test_ambient_gap_filler.py` — Comprehensive tests

### Modified Files
1. `backend/src/api/routes/__init__.py` — Register ambient_onboarding route
2. `backend/src/main.py` — Include ambient_onboarding router

### Key Features
- **Threshold detection**: Domains below 60% readiness trigger prompts
- **Anti-nagging**: Minimum 3 days between prompts, max 2 per week
- **Priority selection**: Lowest score domain is addressed first
- **Natural prompts**: Per-domain carefully crafted conversation starters
- **Chat integration**: `get_pending_prompt()` for chat service to weave into conversation
- **Outcome tracking**: engaged/dismissed/deferred feeds procedural memory
- **Procedural learning**: Successful prompts create insights for future optimization

### Integration Checklist
- [x] Data stored in correct memory type (ambient_prompts table + procedural_insights)
- [x] Knowledge gaps identified → prompts generated from readiness service
- [x] Readiness sub-score read to determine gaps
- [x] Downstream features notified (chat service via get_pending_prompt)
- [x] Audit log entry created (logging on all operations)
- [x] Procedural memory updated on engaged outcomes

### API Endpoints
- `GET /api/v1/ambient-onboarding/ambient-prompt` — Get pending prompt for current session
- `POST /api/v1/ambient-onboarding/ambient-prompt/{prompt_id}/outcome` — Record engagement
