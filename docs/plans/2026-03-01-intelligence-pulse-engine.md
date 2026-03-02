# Intelligence Pulse Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the routing layer between ARIA's signal producers and delivery channels so ARIA decides *how* and *when* to tell the user about detected events.

**Architecture:** A centralized `IntelligencePulseEngine` service receives raw signals from existing producers (scout, email, goals, OODA, calendar), scores salience using deterministic rules + lightweight LLM (Haiku), computes priority, routes to delivery channel (immediate/check-in/morning-brief/weekly-digest/silent), persists to `pulse_signals` table, and triggers delivery. Check-in signals are injected into the chat system prompt; morning brief signals are consumed by the existing briefing service.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase (PostgreSQL) / Claude Haiku for scoring / APScheduler for sweep job / WebSocket for immediate delivery

---

## Task 1: Database Migration — Create pulse_signals and user_pulse_config Tables

**Files:**
- Create: `backend/supabase/migrations/20260301000000_pulse_system_tables.sql`

**Step 1: Write the migration SQL**

```sql
-- Intelligence Pulse Engine tables
-- pulse_signals: stores every detected signal with salience scores and delivery routing
-- user_pulse_config: per-user thresholds and delivery preferences

CREATE TABLE IF NOT EXISTS pulse_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    -- Signal classification
    pulse_type TEXT NOT NULL CHECK (pulse_type IN ('scheduled', 'event', 'intelligent')),
    source TEXT NOT NULL,
    signal_category TEXT,

    -- Content
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    entities TEXT[],
    related_goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    related_lead_id UUID,
    raw_data JSONB,

    -- Salience scores (0.0 to 1.0)
    goal_relevance FLOAT DEFAULT 0 CHECK (goal_relevance >= 0 AND goal_relevance <= 1),
    time_sensitivity FLOAT DEFAULT 0 CHECK (time_sensitivity >= 0 AND time_sensitivity <= 1),
    value_impact FLOAT DEFAULT 0 CHECK (value_impact >= 0 AND value_impact <= 1),
    user_preference FLOAT DEFAULT 0.5 CHECK (user_preference >= 0 AND user_preference <= 1),
    surprise_factor FLOAT DEFAULT 0 CHECK (surprise_factor >= 0 AND surprise_factor <= 1),

    -- Computed priority (0-100)
    priority_score FLOAT DEFAULT 0,

    -- Delivery routing
    delivery_channel TEXT CHECK (delivery_channel IN ('immediate', 'check_in', 'morning_brief', 'weekly_digest', 'silent')),
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,

    -- Timestamps
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pulse_signals_user_undelivered
    ON pulse_signals(user_id, delivery_channel) WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pulse_signals_user_priority
    ON pulse_signals(user_id, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_signals_source
    ON pulse_signals(source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_signals_category
    ON pulse_signals(user_id, signal_category);

ALTER TABLE pulse_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own pulse signals" ON pulse_signals
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on pulse_signals" ON pulse_signals
    FOR ALL TO service_role USING (true);

CREATE TABLE IF NOT EXISTS user_pulse_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    morning_brief_enabled BOOLEAN DEFAULT TRUE,
    morning_brief_time TIME DEFAULT '07:00',
    immediate_threshold INT DEFAULT 90,
    check_in_threshold INT DEFAULT 70,
    morning_brief_threshold INT DEFAULT 50,
    push_notifications_enabled BOOLEAN DEFAULT TRUE,
    email_digest_enabled BOOLEAN DEFAULT FALSE,
    weekend_briefings TEXT DEFAULT 'abbreviated' CHECK (weekend_briefings IN ('full', 'abbreviated', 'none')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_pulse_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own pulse config" ON user_pulse_config
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on user_pulse_config" ON user_pulse_config
    FOR ALL TO service_role USING (true);
```

**Step 2: Apply migration via Supabase**

Run: `cd /Users/dhruv/aria && python3 -c "from backend.src.db.supabase import SupabaseClient; db = SupabaseClient.get_client(); print('connected')"` to verify DB connectivity, then apply via Supabase dashboard or `supabase db push`.

Alternatively, run the SQL directly against the database using the Supabase MCP query tool.

**Step 3: Verify tables exist**

Run SQL: `SELECT table_name FROM information_schema.tables WHERE table_name IN ('pulse_signals', 'user_pulse_config');`

Expected: both tables returned.

**Step 4: Commit**

```bash
git add backend/supabase/migrations/20260301000000_pulse_system_tables.sql
git commit -m "feat: add pulse_signals and user_pulse_config tables for Intelligence Pulse Engine"
```

---

## Task 2: Core Service — IntelligencePulseEngine

**Files:**
- Create: `backend/src/services/intelligence_pulse.py`
- Test: `backend/tests/test_intelligence_pulse.py`

**Step 1: Write failing tests**

```python
"""Tests for IntelligencePulseEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    db = MagicMock()
    # pulse_signals insert chain
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "test-signal-id", "priority_score": 75, "delivery_channel": "check_in"}]
    )
    # active_goals select chain
    db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"id": "goal-1", "title": "Close Acme deal", "description": "Enterprise sale"}]
    )
    # user_pulse_config select chain
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    return db


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = AsyncMock()
    llm.generate_response.return_value = '{"goal_relevance": 0.7, "surprise_factor": 0.4}'
    return llm


@pytest.fixture
def mock_notification_service():
    """Mock NotificationService."""
    ns = MagicMock()
    ns.create_notification = AsyncMock()
    return ns


@pytest.fixture
def engine(mock_db, mock_llm, mock_notification_service):
    """Create IntelligencePulseEngine with mocks."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    return IntelligencePulseEngine(
        supabase_client=mock_db,
        llm_client=mock_llm,
        notification_service=mock_notification_service,
    )


@pytest.mark.asyncio
async def test_process_signal_returns_record(engine, mock_db):
    """process_signal should return the persisted record."""
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "scout_agent",
            "title": "Acme raised Series C",
            "content": "Acme Corp announced $50M Series C funding",
            "signal_category": "competitive",
            "pulse_type": "event",
        },
    )
    assert result["id"] == "test-signal-id"
    assert mock_db.table.called


@pytest.mark.asyncio
async def test_process_signal_computes_priority(engine):
    """process_signal should compute a numeric priority_score."""
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "goal_monitor",
            "title": "Goal completed",
            "content": "Q1 pipeline goal is done",
            "signal_category": "goal",
            "pulse_type": "event",
            "related_goal_id": "goal-1",
        },
    )
    # We can't assert exact value due to mocking, but result should exist
    assert result is not None


@pytest.mark.asyncio
async def test_determine_channel_immediate():
    """Score >= 90 routes to immediate channel."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=95,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "immediate"


@pytest.mark.asyncio
async def test_determine_channel_check_in():
    """Score 70-89 routes to check_in channel."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=75,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "check_in"


@pytest.mark.asyncio
async def test_determine_channel_morning_brief():
    """Score 50-69 routes to morning_brief."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=55,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "morning_brief"


@pytest.mark.asyncio
async def test_determine_channel_weekly_digest():
    """Score 30-49 routes to weekly_digest."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=35,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "weekly_digest"


@pytest.mark.asyncio
async def test_determine_channel_silent():
    """Score < 30 routes to silent."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=15,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "silent"


@pytest.mark.asyncio
async def test_process_signal_graceful_on_llm_failure(engine, mock_llm):
    """If LLM scoring fails, engine should still persist with fallback scores."""
    mock_llm.generate_response.side_effect = Exception("LLM down")
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "test",
            "title": "Test signal",
            "content": "Testing fallback behavior",
            "signal_category": "deal_health",
            "pulse_type": "intelligent",
        },
    )
    # Should still return a result (graceful degradation)
    assert result is not None


@pytest.mark.asyncio
async def test_process_signal_graceful_on_db_failure(mock_llm, mock_notification_service):
    """If DB insert fails, engine should not raise."""
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.side_effect = Exception("DB down")
    mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    from src.services.intelligence_pulse import IntelligencePulseEngine

    engine = IntelligencePulseEngine(
        supabase_client=mock_db,
        llm_client=mock_llm,
        notification_service=mock_notification_service,
    )
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "test",
            "title": "Test",
            "content": "DB failure test",
            "signal_category": "deal_health",
            "pulse_type": "event",
        },
    )
    assert result is None  # Failed gracefully, returned None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_intelligence_pulse.py -v`
Expected: FAIL — module `src.services.intelligence_pulse` does not exist.

**Step 3: Implement IntelligencePulseEngine**

Create `backend/src/services/intelligence_pulse.py`:

```python
"""Intelligence Pulse Engine — signal routing layer.

Receives raw signals from producers (scout, email, goals, OODA, calendar),
scores salience, computes priority, routes to delivery channel, persists,
and triggers delivery.

Callers:
    - scout_signal_scan_job.py (market signals)
    - autonomous_draft_engine.py (urgent emails)
    - goal_execution.py (goal completion/blocked)
    - scheduler.py OODA checks (goal state changes)
    - scheduler.py pulse_sweep (overdue prospective memories)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Salience weights (must sum to 1.0)
_W_GOAL = 0.30
_W_TIME = 0.25
_W_VALUE = 0.20
_W_PREF = 0.15
_W_SURPRISE = 0.10

# Default thresholds (used when user has no pulse_config row)
_DEFAULT_IMMEDIATE = 90
_DEFAULT_CHECK_IN = 70
_DEFAULT_MORNING = 50
_DEFAULT_SILENT_BELOW = 30


class IntelligencePulseEngine:
    """Routes signals from producers to delivery channels.

    Args:
        supabase_client: Supabase DB client (from SupabaseClient.get_client()).
        llm_client: LLMClient instance for salience scoring (should be Haiku).
        notification_service: NotificationService class for immediate delivery.
    """

    def __init__(
        self,
        supabase_client: Any,
        llm_client: Any,
        notification_service: Any,
    ) -> None:
        self._db = supabase_client
        self._llm = llm_client
        self._notifications = notification_service

    async def process_signal(
        self,
        user_id: str,
        signal: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Main entry point. Score, route, persist, and deliver a signal.

        Args:
            user_id: The user's UUID.
            signal: Dict with keys:
                - source: str (e.g. 'scout_agent', 'email_scanner', 'calendar')
                - title: str
                - content: str
                - signal_category: str (e.g. 'competitive', 'deal_health', 'calendar', 'email', 'goal')
                - pulse_type: str ('scheduled', 'event', 'intelligent')
                - entities: list[str] (optional)
                - related_goal_id: str (optional)
                - related_lead_id: str (optional)
                - raw_data: dict (optional)

        Returns:
            The persisted pulse_signals record dict, or None on failure.
        """
        try:
            # 1. Fetch context
            active_goals = await self._fetch_active_goals(user_id)
            user_config = await self._fetch_user_config(user_id)

            # 2. Score salience
            scores = await self._score_salience(user_id, signal, active_goals)

            # 3. Compute priority
            priority_score = (
                scores["goal_relevance"] * _W_GOAL
                + scores["time_sensitivity"] * _W_TIME
                + scores["value_impact"] * _W_VALUE
                + scores["user_preference"] * _W_PREF
                + scores["surprise_factor"] * _W_SURPRISE
            ) * 100

            # 4. Determine channel
            immediate_t = user_config.get("immediate_threshold", _DEFAULT_IMMEDIATE)
            check_in_t = user_config.get("check_in_threshold", _DEFAULT_CHECK_IN)
            morning_t = user_config.get("morning_brief_threshold", _DEFAULT_MORNING)
            channel = self._determine_channel_static(
                priority_score, immediate_t, check_in_t, morning_t,
            )

            # 5. Persist
            record = await self._persist_signal(user_id, signal, scores, priority_score, channel)
            if record is None:
                return None

            # 6. Deliver
            await self._deliver(record, channel, user_id)

            return record

        except Exception:
            logger.exception(
                "IntelligencePulseEngine: failed to process signal",
                extra={"user_id": user_id, "source": signal.get("source")},
            )
            return None

    async def _fetch_active_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch user's active goals for relevance scoring."""
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "pending"])
                .execute()
            )
            return result.data or []
        except Exception:
            logger.warning("Pulse: failed to fetch active goals", extra={"user_id": user_id})
            return []

    async def _fetch_user_config(self, user_id: str) -> dict[str, Any]:
        """Fetch user pulse config, returning defaults if none exists."""
        try:
            result = (
                self._db.table("user_pulse_config")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception:
            logger.debug("Pulse: no user config found, using defaults", extra={"user_id": user_id})
        return {
            "immediate_threshold": _DEFAULT_IMMEDIATE,
            "check_in_threshold": _DEFAULT_CHECK_IN,
            "morning_brief_threshold": _DEFAULT_MORNING,
        }

    async def _score_salience(
        self,
        user_id: str,
        signal: dict[str, Any],
        active_goals: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate 5 salience dimensions.

        Uses deterministic rules for time_sensitivity, value_impact, user_preference.
        Uses LLM (Haiku) for goal_relevance and surprise_factor when no direct match.
        """
        goal_relevance = 0.1
        time_sensitivity = 0.3
        value_impact = 0.3
        user_preference = 0.5
        surprise_factor = 0.3

        source = signal.get("source", "")
        category = signal.get("signal_category", "")
        related_goal_id = signal.get("related_goal_id")

        # --- goal_relevance ---
        if related_goal_id:
            # Direct goal reference
            if any(g["id"] == related_goal_id for g in active_goals):
                goal_relevance = 0.9
            else:
                goal_relevance = 0.5
        elif active_goals:
            # Try LLM scoring for entity overlap
            try:
                goal_titles = ", ".join(g["title"] for g in active_goals[:5])
                prompt = (
                    f"Rate 0.0-1.0 how relevant this signal is to the user's active goals.\n"
                    f"Goals: {goal_titles}\n"
                    f"Signal: {signal.get('title', '')} — {signal.get('content', '')[:200]}\n"
                    f"Return JSON: {{\"goal_relevance\": 0.X, \"surprise_factor\": 0.X}}"
                )
                resp = await self._llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt="You are a sales intelligence scoring engine. Return only valid JSON.",
                    max_tokens=100,
                    temperature=0.0,
                )
                parsed = json.loads(resp)
                goal_relevance = max(0.0, min(1.0, float(parsed.get("goal_relevance", 0.3))))
                surprise_factor = max(0.0, min(1.0, float(parsed.get("surprise_factor", 0.3))))
            except Exception:
                logger.debug("Pulse: LLM scoring failed, using defaults")
                goal_relevance = 0.3

        # --- time_sensitivity ---
        if category == "calendar":
            # Calendar events are time-sensitive by nature
            raw = signal.get("raw_data", {})
            hours_until = raw.get("hours_until")
            if hours_until is not None:
                if hours_until <= 2:
                    time_sensitivity = 1.0
                elif hours_until <= 24:
                    time_sensitivity = 0.7
                else:
                    time_sensitivity = 0.4
            else:
                time_sensitivity = 0.7
        elif category == "email":
            time_sensitivity = 0.8
        elif source == "scout_agent":
            time_sensitivity = 0.6
        elif category == "goal":
            time_sensitivity = 0.5

        # --- value_impact ---
        if category == "deal_health":
            value_impact = 0.8
        elif category in ("competitive", "regulatory"):
            value_impact = 0.7
        elif category == "goal":
            value_impact = 0.6
        elif category == "email":
            value_impact = 0.5
        elif category == "calendar":
            value_impact = 0.4

        return {
            "goal_relevance": goal_relevance,
            "time_sensitivity": time_sensitivity,
            "value_impact": value_impact,
            "user_preference": user_preference,
            "surprise_factor": surprise_factor,
        }

    @staticmethod
    def _determine_channel_static(
        priority_score: float,
        immediate_threshold: int = _DEFAULT_IMMEDIATE,
        check_in_threshold: int = _DEFAULT_CHECK_IN,
        morning_brief_threshold: int = _DEFAULT_MORNING,
    ) -> str:
        """Route signal to delivery channel based on priority and thresholds."""
        if priority_score >= immediate_threshold:
            return "immediate"
        elif priority_score >= check_in_threshold:
            return "check_in"
        elif priority_score >= morning_brief_threshold:
            return "morning_brief"
        elif priority_score >= _DEFAULT_SILENT_BELOW:
            return "weekly_digest"
        else:
            return "silent"

    async def _persist_signal(
        self,
        user_id: str,
        signal: dict[str, Any],
        scores: dict[str, float],
        priority_score: float,
        channel: str,
    ) -> dict[str, Any] | None:
        """Insert signal record into pulse_signals table."""
        try:
            now = datetime.now(UTC).isoformat()
            row = {
                "user_id": user_id,
                "pulse_type": signal.get("pulse_type", "event"),
                "source": signal.get("source", "unknown"),
                "signal_category": signal.get("signal_category"),
                "title": signal["title"],
                "content": signal["content"],
                "entities": signal.get("entities", []),
                "related_goal_id": signal.get("related_goal_id"),
                "related_lead_id": signal.get("related_lead_id"),
                "raw_data": signal.get("raw_data"),
                "goal_relevance": scores["goal_relevance"],
                "time_sensitivity": scores["time_sensitivity"],
                "value_impact": scores["value_impact"],
                "user_preference": scores["user_preference"],
                "surprise_factor": scores["surprise_factor"],
                "priority_score": round(priority_score, 2),
                "delivery_channel": channel,
                "detected_at": now,
                "created_at": now,
            }
            # Mark silent signals as immediately delivered
            if channel == "silent":
                row["delivered_at"] = now

            result = self._db.table("pulse_signals").insert(row).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception:
            logger.exception(
                "Pulse: failed to persist signal",
                extra={"user_id": user_id, "title": signal.get("title")},
            )
            return None

    async def _deliver(
        self,
        record: dict[str, Any],
        channel: str,
        user_id: str,
    ) -> None:
        """Execute delivery based on channel.

        - immediate: notification + WebSocket push
        - check_in: no action (consumed by chat priming at next conversation)
        - morning_brief: no action (consumed by briefing generator)
        - weekly_digest: no action (consumed by weekly digest job)
        - silent: already marked delivered
        """
        if channel != "immediate":
            return

        try:
            from src.models.notification import NotificationType

            await self._notifications.create_notification(
                user_id=user_id,
                type=NotificationType.SYSTEM,
                title=record["title"],
                message=record["content"][:500],
                metadata={
                    "pulse_signal_id": record["id"],
                    "source": record["source"],
                    "priority_score": record["priority_score"],
                },
            )
        except Exception:
            logger.warning(
                "Pulse: notification delivery failed",
                extra={"user_id": user_id, "signal_id": record.get("id")},
            )

        # WebSocket push for real-time
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_signal(
                user_id=user_id,
                signal_type=record.get("signal_category", "system"),
                title=record["title"],
                severity="high" if record.get("priority_score", 0) >= 90 else "medium",
                data={
                    "pulse_signal_id": record["id"],
                    "content": record["content"][:300],
                    "source": record["source"],
                },
            )
        except Exception:
            logger.debug("Pulse: WebSocket push failed (user may not be connected)")

        # Mark as delivered
        try:
            self._db.table("pulse_signals").update(
                {"delivered_at": datetime.now(UTC).isoformat()}
            ).eq("id", record["id"]).execute()
        except Exception:
            logger.debug("Pulse: failed to mark signal as delivered")


# ---------------------------------------------------------------------------
# Module-level convenience: lazy singleton
# ---------------------------------------------------------------------------

_engine_instance: IntelligencePulseEngine | None = None


def get_pulse_engine() -> IntelligencePulseEngine:
    """Get or create the global IntelligencePulseEngine singleton.

    Uses Haiku model for cost-effective salience scoring.
    """
    global _engine_instance
    if _engine_instance is None:
        from src.core.llm import LLMClient
        from src.db.supabase import SupabaseClient
        from src.services.notification_service import NotificationService

        _engine_instance = IntelligencePulseEngine(
            supabase_client=SupabaseClient.get_client(),
            llm_client=LLMClient(model="claude-haiku-4-5-20251001"),
            notification_service=NotificationService,
        )
    return _engine_instance
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_intelligence_pulse.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add backend/src/services/intelligence_pulse.py backend/tests/test_intelligence_pulse.py
git commit -m "feat: add IntelligencePulseEngine core service with salience scoring and channel routing"
```

---

## Task 3: Wire Scout Signal Scan Job

**Files:**
- Modify: `backend/src/jobs/scout_signal_scan_job.py` (after line 125, the `stats["signals_detected"] += 1` line)

**Step 1: Write the failing test**

Add to `backend/tests/test_intelligence_pulse.py`:

```python
@pytest.mark.asyncio
async def test_scout_signal_scan_calls_pulse_engine():
    """Verify scout job integration point exists and is callable."""
    # This is a structural test — verify the import works
    from src.services.intelligence_pulse import get_pulse_engine
    engine = get_pulse_engine()
    assert engine is not None
```

**Step 2: Run test to verify it passes** (this is a structural validation)

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_intelligence_pulse.py::test_scout_signal_scan_calls_pulse_engine -v`

**Step 3: Add pulse signal call to scout_signal_scan_job.py**

At `backend/src/jobs/scout_signal_scan_job.py`, after line 125 (`stats["signals_detected"] += 1`), add:

```python
                # Route through Intelligence Pulse Engine
                try:
                    from src.services.intelligence_pulse import get_pulse_engine

                    pulse_engine = get_pulse_engine()
                    await pulse_engine.process_signal(
                        user_id=user_id,
                        signal={
                            "source": "scout_agent",
                            "title": headline,
                            "content": signal.get("summary", ""),
                            "signal_category": signal.get("signal_type", "news"),
                            "pulse_type": "event",
                            "entities": [signal.get("company_name", "Unknown")],
                            "raw_data": signal,
                        },
                    )
                except Exception:
                    logger.debug("Pulse engine routing failed for signal: %s", headline[:60])
```

**Step 4: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/jobs/scout_signal_scan_job.py').read()); print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/src/jobs/scout_signal_scan_job.py
git commit -m "feat: wire scout signal scan to Intelligence Pulse Engine"
```

---

## Task 4: Wire Autonomous Draft Engine (Urgent Emails)

**Files:**
- Modify: `backend/src/services/autonomous_draft_engine.py` (in `process_inbox`, after the activity logging block ~line 267)

**Step 1: Add pulse signal call for urgent emails**

After the activity logging `try/except` block (around line 267), before the `# Get user info for signature` line, add:

```python
            # Route urgent email signals through Intelligence Pulse Engine
            if scan_result.needs_reply:
                try:
                    from src.services.intelligence_pulse import get_pulse_engine

                    pulse_engine = get_pulse_engine()
                    await pulse_engine.process_signal(
                        user_id=user_id,
                        signal={
                            "source": "email_scanner",
                            "title": f"{len(scan_result.needs_reply)} emails need attention",
                            "content": f"Inbox scan found {result.emails_scanned} emails: "
                                       f"{result.emails_needs_reply} need reply, "
                                       f"{len(scan_result.fyi)} FYI",
                            "signal_category": "email",
                            "pulse_type": "event",
                            "entities": [],
                            "raw_data": {
                                "run_id": run_id,
                                "emails_scanned": result.emails_scanned,
                                "needs_reply": result.emails_needs_reply,
                            },
                        },
                    )
                except Exception:
                    logger.debug("DRAFT_ENGINE: Pulse engine routing failed")
```

**Step 2: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/autonomous_draft_engine.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/services/autonomous_draft_engine.py
git commit -m "feat: wire autonomous draft engine to Intelligence Pulse Engine for urgent emails"
```

---

## Task 5: Wire Goal Execution Service

**Files:**
- Modify: `backend/src/services/goal_execution.py` (after goal completion at ~line 651, before the WebSocket notification)

**Step 1: Add pulse signal call after goal completion**

In `execute_goal_sync`, after the `_record_goal_update` call on line 646 and before the try block that sends the completion message (line 653), add:

```python
        # Route goal completion through Intelligence Pulse Engine
        try:
            from src.services.intelligence_pulse import get_pulse_engine

            pulse_engine = get_pulse_engine()
            await pulse_engine.process_signal(
                user_id=user_id,
                signal={
                    "source": "goal_monitor",
                    "title": f"Goal completed: {goal.get('title', '')}",
                    "content": f"Goal completed: {success_count}/{len(results)} agents succeeded",
                    "signal_category": "goal",
                    "pulse_type": "event",
                    "related_goal_id": goal_id,
                    "raw_data": {"goal_id": goal_id, "status": "complete"},
                },
            )
        except Exception:
            logger.debug("Pulse engine routing failed for goal completion", exc_info=True)
```

**Step 2: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/goal_execution.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/services/goal_execution.py
git commit -m "feat: wire goal execution completions to Intelligence Pulse Engine"
```

---

## Task 6: Wire OODA Goal Checks in Scheduler

**Files:**
- Modify: `backend/src/services/scheduler.py` (in `_run_ooda_goal_checks`, after goal completion detection ~line 339 and after blocked detection ~line 360)

**Step 1: Add pulse signal calls for OODA decisions**

In `_run_ooda_goal_checks`, after the goal completion block (line 339-344) and inside the `if state.is_complete` branch, add after the WebSocket completion event try/except:

```python
                    # Route OODA completion signal through Pulse Engine
                    try:
                        from src.services.intelligence_pulse import get_pulse_engine

                        pulse_engine = get_pulse_engine()
                        await pulse_engine.process_signal(
                            user_id=user_id,
                            signal={
                                "source": "ooda",
                                "title": f"Goal completed: {goal.get('title', '')}",
                                "content": f"OODA loop determined goal '{goal.get('title', '')}' is complete",
                                "signal_category": "goal",
                                "pulse_type": "intelligent",
                                "related_goal_id": goal_id,
                                "raw_data": {"goal_id": goal_id, "action": "complete"},
                            },
                        )
                    except Exception:
                        logger.debug("Pulse engine failed for OODA completion signal")
```

Similarly, after the blocked detection block (line 360-376), after the WebSocket blocked event try/except:

```python
                    # Route OODA blocked signal through Pulse Engine
                    try:
                        from src.services.intelligence_pulse import get_pulse_engine

                        pulse_engine = get_pulse_engine()
                        await pulse_engine.process_signal(
                            user_id=user_id,
                            signal={
                                "source": "ooda",
                                "title": f"Goal blocked: {goal.get('title', '')}",
                                "content": f"Blocked reason: {state.blocked_reason or 'Unknown'}",
                                "signal_category": "goal",
                                "pulse_type": "intelligent",
                                "related_goal_id": goal_id,
                                "raw_data": {"goal_id": goal_id, "action": "blocked", "reason": state.blocked_reason},
                            },
                        )
                    except Exception:
                        logger.debug("Pulse engine failed for OODA blocked signal")
```

**Step 2: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/scheduler.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "feat: wire OODA goal checks to Intelligence Pulse Engine for completion/blocked signals"
```

---

## Task 7: Add Pulse Sweep Scheduler Job

**Files:**
- Modify: `backend/src/services/scheduler.py` (add new job function and register it)

**Step 1: Add pulse sweep job function**

Before the `_scheduler: Any = None` line (~line 1054 in scheduler.py), add:

```python
async def _run_pulse_sweep() -> None:
    """Sweep for signals that don't have explicit producer hooks.

    Catches:
    1. Goals that changed status meaningfully since last check
    2. Overdue prospective memories
    """
    try:
        from datetime import timedelta

        from src.db.supabase import SupabaseClient
        from src.services.intelligence_pulse import get_pulse_engine

        db = SupabaseClient.get_client()
        pulse_engine = get_pulse_engine()

        # Time window: signals from the last 15 minutes
        cutoff = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()

        # 1. Goals that recently changed to blocked or complete
        try:
            goals_result = (
                db.table("goals")
                .select("id, user_id, title, status, updated_at")
                .gt("updated_at", cutoff)
                .in_("status", ["blocked", "complete"])
                .execute()
            )
            for goal in (goals_result.data or []):
                # Deduplicate: check if pulse_signals already has this goal+status
                existing = (
                    db.table("pulse_signals")
                    .select("id")
                    .eq("related_goal_id", goal["id"])
                    .eq("source", "pulse_sweep")
                    .gt("created_at", cutoff)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                await pulse_engine.process_signal(
                    user_id=goal["user_id"],
                    signal={
                        "source": "pulse_sweep",
                        "title": f"Goal {goal['status']}: {goal.get('title', '')}",
                        "content": f"Goal '{goal.get('title', '')}' changed to {goal['status']}",
                        "signal_category": "goal",
                        "pulse_type": "scheduled",
                        "related_goal_id": goal["id"],
                        "raw_data": {"goal_id": goal["id"], "status": goal["status"]},
                    },
                )
        except Exception:
            logger.warning("Pulse sweep: goal status check failed", exc_info=True)

        # 2. Overdue prospective memories
        try:
            now = datetime.now(UTC).isoformat()
            overdue_result = (
                db.table("prospective_memories")
                .select("id, user_id, task, description, priority")
                .eq("status", "active")
                .is_("completed_at", "null")
                .lte("trigger_at", now)
                .limit(20)
                .execute()
            )
            for task in (overdue_result.data or []):
                # Deduplicate
                existing = (
                    db.table("pulse_signals")
                    .select("id")
                    .eq("source", "pulse_sweep")
                    .eq("title", f"Overdue: {task.get('task', '')[:80]}")
                    .eq("user_id", task["user_id"])
                    .gt("created_at", cutoff)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                await pulse_engine.process_signal(
                    user_id=task["user_id"],
                    signal={
                        "source": "pulse_sweep",
                        "title": f"Overdue: {task.get('task', '')[:80]}",
                        "content": task.get("description", "Overdue prospective memory task"),
                        "signal_category": "goal",
                        "pulse_type": "scheduled",
                        "raw_data": {"prospective_memory_id": task["id"]},
                    },
                )
        except Exception:
            logger.warning("Pulse sweep: overdue memory check failed", exc_info=True)

    except Exception:
        logger.exception("Pulse sweep scheduler run failed")
```

**Step 2: Register the job in `start_scheduler`**

In the `start_scheduler()` function, before `_scheduler.start()` (~line 1271), add:

```python
        _scheduler.add_job(
            _run_pulse_sweep,
            trigger=CronTrigger(minute="*/15"),
            id="pulse_sweep",
            name="Intelligence Pulse Engine sweep for missed signals",
            replace_existing=True,
        )
```

**Step 3: Add the missing import at the top of the sweep function**

The function uses `datetime` from the standard library. Add `from datetime import UTC, datetime` at the top of the function (lazy import pattern matches the codebase).

**Step 4: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/scheduler.py').read()); print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "feat: add pulse sweep scheduler job for missed signal detection"
```

---

## Task 8: Wire Morning Brief Generator

**Files:**
- Modify: `backend/src/services/briefing.py` (in `generate_briefing`, add pulse_signals query alongside existing data sources)

**Step 1: Add pulse_signals data source to briefing generator**

In `generate_briefing()`, after the `email_data` try/except block (~line 242) and before the causal reasoning block (~line 244), add a new data-gathering block:

```python
        # Gather pulse signals queued for morning briefing
        pulse_insights: list[dict[str, Any]] = []
        try:
            pulse_result = (
                self._db.table("pulse_signals")
                .select("id, title, content, source, signal_category, priority_score")
                .eq("user_id", user_id)
                .eq("delivery_channel", "morning_brief")
                .is_("delivered_at", "null")
                .order("priority_score", desc=True)
                .limit(20)
                .execute()
            )
            pulse_insights = pulse_result.data or []
        except Exception:
            logger.warning(
                "Failed to gather pulse signals for briefing",
                extra={"user_id": user_id},
                exc_info=True,
            )
```

Then, pass `pulse_insights` to the `_generate_summary` call. Modify the call (~line 310) to include it:

In the `_generate_summary` method, add `pulse_insights` as an optional parameter and include them in the LLM prompt if non-empty. The simplest integration: add pulse insights to `queued_insights`.

Actually, the cleanest approach is to prepend pulse insights to the existing `queued_insights` list before passing to `_generate_summary`:

```python
        # Merge pulse signals into queued_insights for LLM synthesis
        combined_insights = list(queued_insights or [])
        for pi in pulse_insights:
            combined_insights.append({
                "type": pi.get("signal_category", "intelligence"),
                "title": pi["title"],
                "content": pi["content"],
                "source": pi.get("source", "pulse_engine"),
                "priority": pi.get("priority_score", 0),
            })
```

Then after the briefing is stored, mark the pulse signals as delivered:

```python
        # Mark pulse signals as delivered
        if pulse_insights:
            try:
                pulse_ids = [p["id"] for p in pulse_insights]
                self._db.table("pulse_signals").update(
                    {"delivered_at": datetime.now(UTC).isoformat()}
                ).in_("id", pulse_ids).execute()
            except Exception:
                logger.warning("Failed to mark pulse signals as delivered", exc_info=True)
```

**Step 2: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/briefing.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/services/briefing.py
git commit -m "feat: wire morning briefing to consume pulse_signals for richer briefings"
```

---

## Task 9: Wire Check-In Delivery to Chat Service

**Files:**
- Modify: `backend/src/services/chat.py` (in `_get_priming_context`, add pulse check-in query)

**Step 1: Add pulse check-in signals to priming context**

In the `_get_priming_context` method (~line 3213), after the existing `prime_conversation` call, add a pulse check-in query:

```python
    async def _get_priming_context(
        self,
        user_id: str,
        initial_message: str,
    ) -> ConversationContext | None:
        """Prime conversation with recent episodes, open threads, and salient facts."""
        try:
            context = await self._priming_service.prime_conversation(
                user_id=user_id,
                initial_message=initial_message,
            )

            # Inject pending pulse check-in signals into formatted context
            try:
                db = get_supabase_client()
                check_ins = (
                    db.table("pulse_signals")
                    .select("id, title, content, source, priority_score")
                    .eq("user_id", user_id)
                    .eq("delivery_channel", "check_in")
                    .is_("delivered_at", "null")
                    .order("priority_score", desc=True)
                    .limit(5)
                    .execute()
                )
                if check_ins.data:
                    pulse_section = "\n\n## Pending Updates (mention naturally in conversation)\n"
                    for signal in check_ins.data:
                        pulse_section += f"- {signal['title']}: {signal['content'][:200]}\n"

                    if context and context.formatted_context:
                        context.formatted_context += pulse_section
                    elif context:
                        context.formatted_context = pulse_section

                    # Mark as delivered
                    ids = [s["id"] for s in check_ins.data]
                    db.table("pulse_signals").update(
                        {"delivered_at": datetime.now(UTC).isoformat()}
                    ).in_("id", ids).execute()
            except Exception:
                logger.debug("Pulse check-in injection failed (non-fatal)")

            return context
        except Exception as e:
            logger.warning("Failed to prime conversation: %s", e)
            return None
```

Note: The `datetime` import already exists at line 16 of chat.py (`from datetime import UTC, datetime`).

**Step 2: Verify file parses**

Run: `cd /Users/dhruv/aria && python -c "import ast; ast.parse(open('backend/src/services/chat.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/services/chat.py
git commit -m "feat: wire check-in pulse signals into chat conversation priming"
```

---

## Task 10: Run Full Test Suite and Final Verification

**Step 1: Run pulse engine tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_intelligence_pulse.py -v`
Expected: All tests pass.

**Step 2: Run full unit test suite** (exclude smoke and integration tests)

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/ -v --ignore=backend/tests/test_llm_gateway_smoke.py -k "not integration" --timeout=60 -x -q`
Expected: No regressions from the pulse engine changes.

**Step 3: Verify all modified files parse**

Run:
```bash
cd /Users/dhruv/aria && python -c "
import ast
files = [
    'backend/src/services/intelligence_pulse.py',
    'backend/src/jobs/scout_signal_scan_job.py',
    'backend/src/services/autonomous_draft_engine.py',
    'backend/src/services/goal_execution.py',
    'backend/src/services/scheduler.py',
    'backend/src/services/briefing.py',
    'backend/src/services/chat.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'OK: {f}')
print('All files parse successfully')
"
```

**Step 4: Verify pulse_signals table exists**

Use Supabase MCP query tool: `SELECT table_name FROM information_schema.tables WHERE table_name = 'pulse_signals';`

**Step 5: Final commit (if any outstanding changes)**

```bash
git add -A
git status
# If clean, skip. If changes, commit with descriptive message.
```

---

## Summary of Files

### Files Created
1. `backend/supabase/migrations/20260301000000_pulse_system_tables.sql` — DB migration
2. `backend/src/services/intelligence_pulse.py` — Core engine service
3. `backend/tests/test_intelligence_pulse.py` — Unit tests

### Files Modified (single pulse call added)
4. `backend/src/jobs/scout_signal_scan_job.py` — after line 125
5. `backend/src/services/autonomous_draft_engine.py` — after line 267
6. `backend/src/services/goal_execution.py` — after line 651
7. `backend/src/services/scheduler.py` — OODA completion/blocked + pulse_sweep job + registration
8. `backend/src/services/briefing.py` — pulse_signals query + merge into insights
9. `backend/src/services/chat.py` — check-in signals in `_get_priming_context`
