# ARIA Event Trigger System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real-time event processing so ARIA reacts to external events (email, calendar, CRM) and internal events (goal completed, agent finished) within ~60 seconds instead of the current 30-minute polling cycles.

**Architecture:** Central EventTriggerService receives all events (Composio webhooks + internal signals), classifies them with pure regex/rules (<10ms, no LLM), routes to domain handlers, emits signals to the Pulse Engine for salience scoring, and delivers via WebSocket. Existing polling jobs remain unchanged as reconciliation safety nets.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase (sync client) / Composio webhooks / APScheduler / WebSocket (ConnectionManager)

---

## Critical Context for the Implementing Engineer

### Supabase Client is SYNCHRONOUS
The Supabase client (`SupabaseClient.get_client()`) returns a **synchronous** `Client`. Do NOT `await` database calls:
```python
# RIGHT — sync call
from src.db.supabase import get_supabase_client
db = get_supabase_client()
result = db.table("event_log").select("*").eq("user_id", uid).execute()

# WRONG — will fail
result = await db.table("event_log").select("*").execute()
```
File: `backend/src/db/supabase.py:22-53` (singleton), `backend/src/db/supabase.py:344` (`get_supabase_client` convenience).

### WebSocket Manager Signature
`ws_manager.send_signal()` takes **positional keyword args**, NOT a dict:
```python
from src.core.ws import ws_manager
await ws_manager.send_signal(
    user_id=user_id,
    signal_type="email.received",    # str
    title="New email from Sarah",     # str
    severity="medium",                # "low"|"medium"|"high"
    data={"sender": "...", ...},      # dict
)
```
File: `backend/src/core/ws.py:259-274`.

### Pulse Engine Signal Format
`IntelligencePulseEngine.process_signal(user_id, signal)` expects a dict with specific keys:
```python
signal = {
    "source": "email",                    # str — producer name
    "title": "New email from Sarah",      # str
    "content": "Email snippet...",         # str
    "signal_category": "email",           # str — 'competitive'|'deal_health'|'calendar'|'email'|'goal'
    "pulse_type": "event",               # str — 'scheduled'|'event'|'intelligent'
    "entities": [],                       # list[str] — optional
    "related_goal_id": None,              # str — optional
    "related_lead_id": None,              # str — optional
    "raw_data": {},                       # dict — optional
}
```
File: `backend/src/services/intelligence_pulse.py:55-77`, singleton: `get_pulse_engine()` at line 384.

### Existing Webhooks Router
`backend/src/api/routes/webhooks.py` is the **Tavus webhook handler** with `prefix="/webhooks"` and route `POST /tavus`. It's already registered in `main.py:355` as `webhooks.router`. Our Composio webhook route must use a **different file name** (e.g., `composio_webhooks.py`) to avoid import conflicts.

### Authentication
- `CurrentUser = Annotated[Any, Depends(get_current_user)]` — file: `backend/src/api/deps.py:149`
- The Composio webhook endpoint must NOT use auth (Composio can't send JWTs). Use HMAC signature verification instead.
- The test endpoint should use `CurrentUser` for auth.

### User Integration Schema
Table `user_integrations` has `composio_connection_id` (TEXT NOT NULL) and `composio_account_id` (TEXT), NOT `external_account_id`. File: `backend/supabase/migrations/20260202000007_create_user_integrations.sql:8-9`.

### Lead Contacts Are in Stakeholders Table
`lead_memories` does NOT have `contact_email`. Contacts are in `lead_memory_stakeholders` with `contact_email` and `lead_memory_id` FK. File: `backend/supabase/migrations/005_lead_memory_schema.sql:39-53`.

### No `email_contacts` Table
There is no `email_contacts` table in the database. VIP detection needs to query `lead_memory_stakeholders` or rely on lead matching only.

### Router Registration Pattern
Routers are imported in a multi-line import block at `main.py:14-73` and registered with `app.include_router(name.router, prefix="/api/v1")` at lines 295-363.

---

## Task 1: Database Migration — `event_log` Table

**Files:**
- Create: `backend/supabase/migrations/20260301300000_event_trigger_system.sql`

**Step 1: Write the migration SQL**

```sql
-- Event Trigger System: Central event log for real-time event processing
-- Tracks all events (Composio webhooks, internal signals, reconciliation catches)
-- through their full lifecycle: received → classified → processing → handled → delivered

CREATE TABLE IF NOT EXISTS event_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    event_type TEXT NOT NULL,
    event_source TEXT NOT NULL,
    source_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}',
    classification JSONB,
    handler_result JSONB,
    pulse_signal_id UUID,
    status TEXT NOT NULL DEFAULT 'received',
    error_message TEXT,
    latency_ms INTEGER,
    is_reconciliation BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);

CREATE INDEX idx_event_log_user_status ON event_log(user_id, status);
CREATE INDEX idx_event_log_type ON event_log(event_type);
CREATE INDEX idx_event_log_source_id ON event_log(source_id);
CREATE INDEX idx_event_log_created ON event_log(created_at DESC);

ALTER TABLE event_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own events"
    ON event_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service can insert events"
    ON event_log FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service can update events"
    ON event_log FOR UPDATE
    USING (true);
```

**Step 2: Apply the migration**

Run: `cd /Users/dhruv/aria && npx supabase migration up --linked` (or the project's migration approach)

If using Supabase CLI linked to project `asqcmailhanhmyoaujje`, the migration runs remotely. If running locally, the file just needs to exist — the deployment pipeline handles it.

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260301300000_event_trigger_system.sql
git commit -m "feat: add event_log table for real-time event trigger system"
```

---

## Task 2: Core EventTriggerService

**Files:**
- Create: `backend/src/services/event_trigger.py`
- Test: `backend/tests/test_event_trigger.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_event_trigger.py`:

```python
"""Tests for EventTriggerService — central event router."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import asdict

from src.services.event_trigger import (
    EventTriggerService,
    EventEnvelope,
    EventSource,
    EventType,
    EventClassification,
    HandlerOutput,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock Supabase client (synchronous calls)."""
    db = MagicMock()
    # Default: no duplicate found
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    # Default: insert returns id
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "evt-log-001"}]
    )
    # Default: update succeeds
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    return db


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket ConnectionManager."""
    ws = MagicMock()
    ws.send_signal = AsyncMock()
    return ws


@pytest.fixture
def mock_pulse_engine():
    """Mock IntelligencePulseEngine."""
    pulse = MagicMock()
    pulse.process_signal = AsyncMock(return_value={"signal_id": "pulse-001"})
    return pulse


@pytest.fixture
def service(mock_db, mock_ws_manager, mock_pulse_engine):
    return EventTriggerService(mock_db, mock_ws_manager, mock_pulse_engine)


@pytest.fixture
def email_envelope():
    return EventEnvelope(
        event_type=EventType.EMAIL_RECEIVED,
        source=EventSource.COMPOSIO,
        user_id="user-001",
        source_id="msg-abc-123",
        payload={
            "sender": "sarah@lonza.com",
            "subject": "Re: PFA Vessel Pricing",
            "snippet": "Thanks for the follow-up...",
            "messageId": "msg-abc-123",
            "threadId": "thread-001",
        },
    )


@pytest.fixture
def calendar_envelope():
    return EventEnvelope(
        event_type=EventType.CALENDAR_EVENT_CREATED,
        source=EventSource.COMPOSIO,
        user_id="user-001",
        source_id="cal-evt-456",
        payload={
            "summary": "Q1 Pipeline Review",
            "start": {"dateTime": "2026-03-02T10:00:00Z"},
            "attendees": [{"email": "bob@example.com"}],
            "id": "cal-evt-456",
            "status": "confirmed",
        },
    )


@pytest.fixture
def internal_envelope():
    return EventEnvelope(
        event_type=EventType.GOAL_COMPLETED,
        source=EventSource.INTERNAL,
        user_id="user-001",
        payload={"title": "Close Lonza Q1 deal", "id": "goal-789"},
    )


# ── Classification Tests ──────────────────────────────────────────────────

class TestClassification:
    """Test fast classification (no LLM, <10ms)."""

    @pytest.mark.asyncio
    async def test_email_classified_to_email_handler(self, service, email_envelope):
        classification = await service._classify(email_envelope)
        assert classification.handler_key == "email"
        assert classification.event_type == "email.received"

    @pytest.mark.asyncio
    async def test_calendar_classified_to_calendar_handler(self, service, calendar_envelope):
        classification = await service._classify(calendar_envelope)
        assert classification.handler_key == "calendar"

    @pytest.mark.asyncio
    async def test_internal_classified_to_internal_handler(self, service, internal_envelope):
        classification = await service._classify(internal_envelope)
        assert classification.handler_key == "internal"

    @pytest.mark.asyncio
    async def test_urgent_subject_gets_urgent_priority(self, service):
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"sender": "boss@co.com", "subject": "URGENT: Need response ASAP"},
        )
        classification = await service._classify(envelope)
        assert classification.priority_hint == "urgent"

    @pytest.mark.asyncio
    async def test_cancelled_calendar_gets_high_priority(self, service):
        envelope = EventEnvelope(
            event_type=EventType.CALENDAR_EVENT_DELETED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"status": "cancelled", "summary": "Meeting"},
        )
        classification = await service._classify(envelope)
        assert classification.priority_hint == "high"

    @pytest.mark.asyncio
    async def test_deal_stage_change_gets_high_priority(self, service):
        envelope = EventEnvelope(
            event_type=EventType.CRM_DEAL_STAGE_CHANGED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"deal_id": "deal-1"},
        )
        classification = await service._classify(envelope)
        assert classification.priority_hint == "high"

    @pytest.mark.asyncio
    async def test_noise_email_gets_low_priority(self, service):
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={
                "sender": "noreply@newsletter.com",
                "subject": "Weekly digest",
                "snippet": "Unsubscribe from this list",
            },
        )
        classification = await service._classify(envelope)
        assert classification.priority_hint == "low"

    @pytest.mark.asyncio
    async def test_unknown_event_type_gets_default_handler(self, service):
        envelope = EventEnvelope(
            event_type="unknown.event",
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={},
        )
        classification = await service._classify(envelope)
        assert classification.handler_key == "default"


# ── Ingestion Pipeline Tests ──────────────────────────────────────────────

class TestIngestion:
    """Test full ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_ingest_with_handler_returns_processed(self, service, email_envelope):
        mock_handler = MagicMock()
        mock_handler.process = AsyncMock(return_value=HandlerOutput(
            signals=[{"title": "New email", "summary": "test"}],
            summary="Email from sarah@lonza.com",
        ))
        service.register_handler("email", mock_handler)

        result = await service.ingest(email_envelope)

        assert result["status"] == "processed"
        assert "latency_ms" in result
        assert result["handler"] == "email"
        mock_handler.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_no_handler_returns_no_handler(self, service, email_envelope):
        # No handlers registered
        result = await service.ingest(email_envelope)
        assert result["status"] == "no_handler"

    @pytest.mark.asyncio
    async def test_duplicate_detection_skips_event(self, service, email_envelope, mock_db):
        # Simulate existing event_log entry for this source_id
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "existing-evt-id"}]
        )

        result = await service.ingest(email_envelope)
        assert result["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_emit_internal_creates_envelope_and_ingests(self, service):
        mock_handler = MagicMock()
        mock_handler.process = AsyncMock(return_value=HandlerOutput(
            signals=[{"title": "Goal done"}],
            summary="Goal completed",
        ))
        service.register_handler("internal", mock_handler)

        result = await service.emit_internal(
            EventType.GOAL_COMPLETED, "user-001", {"title": "Close deal"}
        )

        assert result["status"] == "processed"
        mock_handler.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failed(self, service, email_envelope):
        mock_handler = MagicMock()
        mock_handler.process = AsyncMock(side_effect=RuntimeError("boom"))
        service.register_handler("email", mock_handler)

        result = await service.ingest(email_envelope)
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_pulse_engine_receives_signals(self, service, email_envelope, mock_pulse_engine):
        mock_handler = MagicMock()
        mock_handler.process = AsyncMock(return_value=HandlerOutput(
            signals=[{"title": "New email", "summary": "test", "source": "email",
                       "signal_category": "email", "pulse_type": "event",
                       "content": "snippet"}],
            summary="Email from sarah",
        ))
        service.register_handler("email", mock_handler)

        await service.ingest(email_envelope)
        mock_pulse_engine.process_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_urgent_event_delivers_direct_websocket(self, service, mock_ws_manager):
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"sender": "ceo@co.com", "subject": "URGENT: Board meeting"},
        )
        mock_handler = MagicMock()
        mock_handler.process = AsyncMock(return_value=HandlerOutput(
            signals=[], summary="Urgent email from CEO",
        ))
        service.register_handler("email", mock_handler)

        await service.ingest(envelope)
        mock_ws_manager.send_signal.assert_called()


# ── Cache Tests ───────────────────────────────────────────────────────────

class TestCaches:
    def test_clear_caches_for_user(self, service):
        service._vip_cache["user-001"] = {"a@b.com"}
        service._active_goals_cache["user-001"] = [{"id": "g1"}]
        service._lead_contacts_cache["user-001"] = {"a@b.com": "lead-1"}

        service.clear_caches("user-001")

        assert "user-001" not in service._vip_cache
        assert "user-001" not in service._active_goals_cache
        assert "user-001" not in service._lead_contacts_cache

    def test_clear_all_caches(self, service):
        service._vip_cache["user-001"] = {"a@b.com"}
        service._vip_cache["user-002"] = {"c@d.com"}

        service.clear_caches()

        assert len(service._vip_cache) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_trigger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.event_trigger'`

**Step 3: Write the EventTriggerService implementation**

Create `backend/src/services/event_trigger.py`:

```python
"""EventTriggerService — Central event router for ARIA.

All events (external webhooks + internal signals) flow through this service.
It classifies, routes to handlers, emits to Pulse Engine, and delivers via WebSocket.

Flow: Event arrives → ingest() → classify() → route to handler → emit to Pulse → deliver
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
import time
import re
import logging

logger = logging.getLogger(__name__)


class EventSource(str, Enum):
    COMPOSIO = "composio"
    INTERNAL = "internal"
    RECONCILIATION = "reconciliation"


class EventType(str, Enum):
    # External — email
    EMAIL_RECEIVED = "email.received"
    EMAIL_SENT = "email.sent"
    EMAIL_THREAD_REPLY = "email.thread_reply"
    # External — calendar
    CALENDAR_EVENT_CREATED = "calendar.event_created"
    CALENDAR_EVENT_UPDATED = "calendar.event_updated"
    CALENDAR_EVENT_DELETED = "calendar.event_deleted"
    CALENDAR_EVENT_REMINDER = "calendar.event_reminder"
    # External — CRM
    CRM_LEAD_CREATED = "crm.lead_created"
    CRM_LEAD_UPDATED = "crm.lead_updated"
    CRM_DEAL_STAGE_CHANGED = "crm.deal_stage_changed"
    CRM_CONTACT_UPDATED = "crm.contact_updated"
    # External — Slack
    SLACK_MESSAGE_RECEIVED = "slack.message_received"
    SLACK_MENTION = "slack.mention"
    # Internal
    GOAL_COMPLETED = "goal.completed"
    GOAL_BLOCKED = "goal.blocked"
    AGENT_TASK_FINISHED = "agent.task_finished"
    DRAFT_APPROVED = "draft.approved"
    DRAFT_REJECTED = "draft.rejected"
    ACTION_APPROVED = "action.approved"
    ACTION_REJECTED = "action.rejected"
    # System
    RECONCILIATION_FOUND = "reconciliation.found"


@dataclass
class EventEnvelope:
    """Typed container for all events flowing through the system."""
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: EventType | str = ""
    source: EventSource = EventSource.COMPOSIO
    user_id: str = ""
    source_id: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


@dataclass
class EventClassification:
    """Result of fast, no-LLM classification."""
    event_type: str
    priority_hint: str = "normal"
    matched_leads: list[str] = field(default_factory=list)
    matched_goals: list[str] = field(default_factory=list)
    matched_contacts: list[str] = field(default_factory=list)
    is_vip_sender: bool = False
    handler_key: str = ""
    skip_processing: bool = False
    skip_reason: str = ""


@dataclass
class HandlerOutput:
    """Result from a domain-specific handler."""
    artifacts: list[dict] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    summary: str = ""
    error: str = ""


class EventTriggerService:
    """Central event router. All events flow through here.

    Usage:
        service = EventTriggerService(db, ws_manager, pulse_engine)
        service.register_handler("email", EmailEventHandler())

        # From webhook:
        await service.ingest(envelope)

        # From internal code:
        await service.emit_internal(EventType.GOAL_COMPLETED, user_id, payload)
    """

    def __init__(self, db: Any, ws_manager: Any, pulse_engine: Any = None) -> None:
        self.db = db
        self.ws_manager = ws_manager
        self.pulse_engine = pulse_engine
        self._handlers: dict[str, Any] = {}
        self._vip_cache: dict[str, set] = {}
        self._active_goals_cache: dict[str, list] = {}
        self._lead_contacts_cache: dict[str, dict] = {}

    def register_handler(self, key: str, handler: Any) -> None:
        self._handlers[key] = handler
        logger.info("Registered event handler: %s", key)

    async def ingest(self, envelope: EventEnvelope) -> dict:
        """Main entry point. Process an event through the full pipeline."""
        start_time = time.time()
        event_log_id = None

        try:
            # 0. Deduplicate
            if envelope.source_id:
                existing = self._check_duplicate(envelope)
                if existing:
                    logger.info("Duplicate event skipped: %s", envelope.source_id)
                    return {"status": "duplicate", "existing_id": existing}

            # 1. Log receipt
            event_log_id = self._log_event(envelope, "received")

            # 2. Fast classify (no LLM, <10ms)
            classification = await self._classify(envelope)
            self._update_event_log(event_log_id, "classified", classification=classification)

            if classification.skip_processing:
                self._update_event_log(
                    event_log_id, "skipped",
                    handler_result={"skip_reason": classification.skip_reason},
                )
                return {"status": "skipped", "reason": classification.skip_reason}

            # 3. Route to handler
            handler = self._handlers.get(classification.handler_key)
            if not handler:
                logger.warning("No handler for key: %s", classification.handler_key)
                self._update_event_log(event_log_id, "no_handler")
                return {"status": "no_handler", "handler_key": classification.handler_key}

            self._update_event_log(event_log_id, "processing")
            handler_output = await handler.process(envelope, classification)
            self._update_event_log(event_log_id, "handled", handler_result=handler_output.__dict__)

            # 4. Emit to Pulse Engine
            if self.pulse_engine and handler_output.signals:
                for signal_data in handler_output.signals:
                    try:
                        pulse_signal_id = await self._emit_to_pulse(
                            envelope.user_id, signal_data, classification,
                        )
                        if pulse_signal_id:
                            self._update_event_log(
                                event_log_id, "delivered",
                                pulse_signal_id=pulse_signal_id,
                            )
                    except Exception as e:
                        logger.error("Pulse emission failed: %s", e)

            # 5. Direct WebSocket delivery (urgent items or no Pulse Engine)
            if classification.priority_hint == "urgent" or not self.pulse_engine:
                await self._deliver_direct(envelope.user_id, handler_output, classification)
                self._update_event_log(event_log_id, "delivered")

            latency_ms = int((time.time() - start_time) * 1000)
            self._update_event_log(event_log_id, latency_ms=latency_ms)

            logger.info(
                "Event processed: %s for user %s in %dms (handler=%s, priority=%s)",
                envelope.event_type, envelope.user_id[:8], latency_ms,
                classification.handler_key, classification.priority_hint,
            )

            return {
                "status": "processed",
                "event_log_id": event_log_id,
                "latency_ms": latency_ms,
                "handler": classification.handler_key,
                "priority": classification.priority_hint,
                "artifacts_count": len(handler_output.artifacts),
                "signals_count": len(handler_output.signals),
            }

        except Exception as e:
            logger.error("Event processing failed: %s", e, exc_info=True)
            if event_log_id:
                self._update_event_log(event_log_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}

    async def emit_internal(self, event_type: EventType, user_id: str, payload: dict) -> dict:
        """Convenience method for internal events."""
        envelope = EventEnvelope(
            event_type=event_type,
            source=EventSource.INTERNAL,
            user_id=user_id,
            payload=payload,
        )
        return await self.ingest(envelope)

    # ── Fast classify (rules + regex, no LLM) ─────────────────────────

    async def _classify(self, envelope: EventEnvelope) -> EventClassification:
        """Classify event using rules + regex. NO LLM. Target: <10ms."""
        event_type = str(envelope.event_type)
        payload = envelope.payload
        classification = EventClassification(event_type=event_type)

        # Handler routing from event type prefix
        if event_type.startswith("email."):
            classification.handler_key = "email"
        elif event_type.startswith("calendar."):
            classification.handler_key = "calendar"
        elif event_type.startswith("crm."):
            classification.handler_key = "crm"
        elif event_type.startswith("slack."):
            classification.handler_key = "slack"
        elif event_type.startswith("goal.") or event_type.startswith("agent."):
            classification.handler_key = "internal"
        elif event_type.startswith("draft.") or event_type.startswith("action."):
            classification.handler_key = "action"
        else:
            classification.handler_key = "default"

        # Email-specific
        if classification.handler_key == "email":
            sender = payload.get("sender", payload.get("from", "")).lower()
            subject = payload.get("subject", "")

            # Check against active leads (stakeholder emails)
            lead_contacts = self._get_lead_contacts(envelope.user_id)
            if sender in lead_contacts:
                classification.matched_leads.append(lead_contacts[sender])
                classification.priority_hint = "high"

            # Check against active goals
            active_goals = self._get_active_goals(envelope.user_id)
            for goal in active_goals:
                goal_keywords = goal.get("keywords", [])
                if any(kw.lower() in subject.lower() for kw in goal_keywords if kw):
                    classification.matched_goals.append(goal["id"])

            # Urgency keywords
            urgency_patterns = r"\b(urgent|asap|eod|deadline|immediately|critical|time.?sensitive)\b"
            if re.search(urgency_patterns, subject, re.IGNORECASE):
                classification.priority_hint = "urgent"

            # Noise detection
            noise_patterns = [
                r"unsubscribe", r"noreply@", r"no-reply@",
                r"newsletter", r"automated.?message", r"do.?not.?reply",
            ]
            sender_plus_body = sender + " " + payload.get("snippet", "")
            if any(re.search(p, sender_plus_body, re.IGNORECASE) for p in noise_patterns):
                classification.priority_hint = "low"

        # Calendar-specific
        elif classification.handler_key == "calendar":
            if payload.get("status") == "cancelled":
                classification.priority_hint = "high"

        # CRM-specific
        elif classification.handler_key == "crm":
            if event_type == EventType.CRM_DEAL_STAGE_CHANGED:
                classification.priority_hint = "high"

        return classification

    # ── Cached lookups ─────────────────────────────────────────────────

    def _get_lead_contacts(self, user_id: str) -> dict:
        """Get lead stakeholder email → lead_id mapping. Cached."""
        if user_id in self._lead_contacts_cache:
            return self._lead_contacts_cache[user_id]

        try:
            # Join stakeholders with active leads
            result = self.db.table("lead_memory_stakeholders") \
                .select("contact_email, lead_memory_id, lead_memories!inner(user_id, status)") \
                .eq("lead_memories.user_id", user_id) \
                .eq("lead_memories.status", "active") \
                .execute()

            contacts = {}
            for r in (result.data or []):
                email = r.get("contact_email", "")
                if email:
                    contacts[email.lower()] = r["lead_memory_id"]
            self._lead_contacts_cache[user_id] = contacts
            return contacts
        except Exception:
            return {}

    def _get_active_goals(self, user_id: str) -> list:
        """Get active goals with keywords for matching. Cached."""
        if user_id in self._active_goals_cache:
            return self._active_goals_cache[user_id]

        try:
            result = self.db.table("goals") \
                .select("id, title, config") \
                .eq("user_id", user_id) \
                .eq("status", "active") \
                .execute()

            goals = []
            for r in (result.data or []):
                keywords = []
                if r.get("config") and isinstance(r["config"], dict):
                    keywords = r["config"].get("keywords", [])
                title_words = [w for w in r.get("title", "").split() if len(w) > 3]
                keywords.extend(title_words)
                goals.append({"id": r["id"], "keywords": keywords})

            self._active_goals_cache[user_id] = goals
            return goals
        except Exception:
            return []

    def clear_caches(self, user_id: str | None = None) -> None:
        """Clear lookup caches. Call when leads/goals change."""
        if user_id:
            self._vip_cache.pop(user_id, None)
            self._active_goals_cache.pop(user_id, None)
            self._lead_contacts_cache.pop(user_id, None)
        else:
            self._vip_cache.clear()
            self._active_goals_cache.clear()
            self._lead_contacts_cache.clear()

    # ── Pulse emission ─────────────────────────────────────────────────

    async def _emit_to_pulse(
        self, user_id: str, signal_data: dict, classification: EventClassification,
    ) -> Optional[str]:
        """Send signal to Pulse Engine for salience scoring."""
        signal_data["matched_leads"] = classification.matched_leads
        signal_data["matched_goals"] = classification.matched_goals
        signal_data["is_vip"] = classification.is_vip_sender
        signal_data["priority_hint"] = classification.priority_hint

        # Map to Pulse Engine expected format
        pulse_signal = {
            "source": signal_data.get("source", "event_trigger"),
            "title": signal_data.get("title", ""),
            "content": signal_data.get("content", signal_data.get("summary", "")),
            "signal_category": signal_data.get("signal_category", signal_data.get("source", "email")),
            "pulse_type": signal_data.get("pulse_type", "event"),
            "entities": signal_data.get("entities", []),
            "related_goal_id": classification.matched_goals[0] if classification.matched_goals else None,
            "related_lead_id": classification.matched_leads[0] if classification.matched_leads else None,
            "raw_data": signal_data,
        }

        if hasattr(self.pulse_engine, "process_signal"):
            result = await self.pulse_engine.process_signal(user_id, pulse_signal)
            return result.get("id") if isinstance(result, dict) else None

        # Fallback: direct WebSocket
        await self._deliver_direct(
            user_id, HandlerOutput(summary=signal_data.get("summary", "")), classification,
        )
        return None

    # ── Direct WebSocket delivery ──────────────────────────────────────

    async def _deliver_direct(
        self, user_id: str, output: HandlerOutput, classification: EventClassification,
    ) -> None:
        """Push via WebSocket (bypasses Pulse for urgent items)."""
        if not output.summary and not output.artifacts:
            return

        title = self._generate_notification_title(classification)
        try:
            await self.ws_manager.send_signal(
                user_id=user_id,
                signal_type=classification.event_type,
                title=title,
                severity="high" if classification.priority_hint in ("high", "urgent") else "medium",
                data={
                    "message": output.summary or "New event processed",
                    "priority": classification.priority_hint,
                    "event_type": classification.event_type,
                    "artifacts": output.artifacts[:3],
                    "matched_leads": classification.matched_leads,
                    "matched_goals": classification.matched_goals,
                },
            )
        except Exception as e:
            logger.error("WebSocket delivery failed for user %s: %s", user_id, e)

    def _generate_notification_title(self, classification: EventClassification) -> str:
        type_titles = {
            "email.received": "New email",
            "email.thread_reply": "Email reply",
            "calendar.event_created": "New meeting",
            "calendar.event_updated": "Meeting changed",
            "calendar.event_deleted": "Meeting cancelled",
            "crm.deal_stage_changed": "Deal stage changed",
            "crm.lead_created": "New lead",
            "goal.completed": "Goal completed",
            "agent.task_finished": "Task finished",
        }
        title = type_titles.get(classification.event_type, "Event")
        if classification.is_vip_sender:
            title += " (VIP)"
        return title

    # ── Database ops (SYNC — no await) ─────────────────────────────────

    def _check_duplicate(self, envelope: EventEnvelope) -> Optional[str]:
        """Check if source_id was already processed."""
        try:
            result = self.db.table("event_log") \
                .select("id") \
                .eq("user_id", envelope.user_id) \
                .eq("source_id", envelope.source_id) \
                .neq("status", "failed") \
                .limit(1) \
                .execute()

            if result.data:
                return result.data[0]["id"]
        except Exception:
            pass
        return None

    def _log_event(self, envelope: EventEnvelope, status: str) -> str:
        """Create event_log entry. Returns event_log id."""
        try:
            result = self.db.table("event_log").insert({
                "user_id": envelope.user_id,
                "event_type": str(envelope.event_type),
                "event_source": envelope.source.value,
                "source_id": envelope.source_id or None,
                "payload": envelope.payload,
                "status": status,
                "is_reconciliation": envelope.source == EventSource.RECONCILIATION,
            }).execute()

            return result.data[0]["id"] if result.data else envelope.id
        except Exception as e:
            logger.error("Failed to log event: %s", e)
            return envelope.id

    def _update_event_log(self, event_log_id: str, status: str | None = None, **kwargs: Any) -> None:
        """Update event_log entry."""
        try:
            update: dict[str, Any] = {}
            if status:
                update["status"] = status
            if "classification" in kwargs:
                cls = kwargs["classification"]
                update["classification"] = cls.__dict__ if hasattr(cls, "__dict__") else cls
            if "handler_result" in kwargs:
                update["handler_result"] = kwargs["handler_result"]
            if "pulse_signal_id" in kwargs:
                update["pulse_signal_id"] = kwargs["pulse_signal_id"]
            if "error" in kwargs:
                update["error_message"] = kwargs["error"]
            if "latency_ms" in kwargs:
                update["latency_ms"] = kwargs["latency_ms"]
            if status == "handled":
                update["processed_at"] = datetime.now(timezone.utc).isoformat()
            if status == "delivered":
                update["delivered_at"] = datetime.now(timezone.utc).isoformat()

            if update:
                self.db.table("event_log") \
                    .update(update) \
                    .eq("id", event_log_id) \
                    .execute()
        except Exception as e:
            logger.error("Failed to update event log %s: %s", event_log_id, e)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_trigger.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/event_trigger.py backend/tests/test_event_trigger.py
git commit -m "feat: add EventTriggerService with classification, routing, and Pulse integration"
```

---

## Task 3: Domain Event Handlers

**Files:**
- Create: `backend/src/services/event_handlers/__init__.py`
- Create: `backend/src/services/event_handlers/email_handler.py`
- Create: `backend/src/services/event_handlers/calendar_handler.py`
- Create: `backend/src/services/event_handlers/internal_handler.py`
- Test: `backend/tests/test_event_handlers.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_event_handlers.py`:

```python
"""Tests for domain event handlers."""

import pytest
from unittest.mock import MagicMock

from src.services.event_trigger import EventEnvelope, EventSource, EventType, EventClassification
from src.services.event_handlers.email_handler import EmailEventHandler
from src.services.event_handlers.calendar_handler import CalendarEventHandler
from src.services.event_handlers.internal_handler import InternalEventHandler


@pytest.fixture
def mock_db():
    return MagicMock()


class TestEmailEventHandler:
    @pytest.mark.asyncio
    async def test_basic_email_produces_signal(self, mock_db):
        handler = EmailEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={
                "sender": "sarah@lonza.com",
                "subject": "PFA Vessel Pricing",
                "snippet": "Thanks for the follow-up...",
                "messageId": "msg-001",
                "threadId": "thread-001",
            },
        )
        classification = EventClassification(event_type="email.received", handler_key="email")

        output = await handler.process(envelope, classification)

        assert len(output.signals) == 1
        assert output.signals[0]["source"] == "email"
        assert "sarah@lonza.com" in output.summary
        assert len(output.artifacts) == 1
        assert output.artifacts[0]["type"] == "email_notification"

    @pytest.mark.asyncio
    async def test_vip_email_noted_in_summary(self, mock_db):
        handler = EmailEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"sender": "ceo@co.com", "subject": "Hi"},
        )
        classification = EventClassification(
            event_type="email.received", handler_key="email", is_vip_sender=True,
        )

        output = await handler.process(envelope, classification)
        assert "VIP" in output.summary

    @pytest.mark.asyncio
    async def test_lead_match_noted_in_summary(self, mock_db):
        handler = EmailEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.EMAIL_RECEIVED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"sender": "lead@co.com", "subject": "Deal update"},
        )
        classification = EventClassification(
            event_type="email.received", handler_key="email",
            matched_leads=["lead-001"],
        )

        output = await handler.process(envelope, classification)
        assert "matched lead" in output.summary


class TestCalendarEventHandler:
    @pytest.mark.asyncio
    async def test_new_meeting_produces_signal(self, mock_db):
        handler = CalendarEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.CALENDAR_EVENT_CREATED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={
                "summary": "Q1 Review",
                "start": {"dateTime": "2026-03-02T10:00:00Z"},
                "attendees": [{"email": "bob@co.com"}],
                "id": "cal-001",
            },
        )
        classification = EventClassification(event_type="calendar.event_created", handler_key="calendar")

        output = await handler.process(envelope, classification)
        assert len(output.signals) == 1
        assert "New meeting" in output.summary
        assert output.artifacts[0]["action"] == "event_created"

    @pytest.mark.asyncio
    async def test_cancelled_meeting_flagged(self, mock_db):
        handler = CalendarEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.CALENDAR_EVENT_DELETED,
            source=EventSource.COMPOSIO,
            user_id="user-001",
            payload={"summary": "Cancelled Meeting", "id": "cal-002", "status": "cancelled"},
        )
        classification = EventClassification(event_type="calendar.event_deleted", handler_key="calendar")

        output = await handler.process(envelope, classification)
        assert "cancelled" in output.summary.lower()


class TestInternalEventHandler:
    @pytest.mark.asyncio
    async def test_goal_completed_produces_signal(self, mock_db):
        handler = InternalEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.GOAL_COMPLETED,
            source=EventSource.INTERNAL,
            user_id="user-001",
            payload={"title": "Close Lonza deal", "id": "goal-001"},
        )
        classification = EventClassification(event_type="goal.completed", handler_key="internal")

        output = await handler.process(envelope, classification)
        assert "Goal completed" in output.summary
        assert "Lonza" in output.summary

    @pytest.mark.asyncio
    async def test_agent_finished_produces_signal(self, mock_db):
        handler = InternalEventHandler(mock_db)
        envelope = EventEnvelope(
            event_type=EventType.AGENT_TASK_FINISHED,
            source=EventSource.INTERNAL,
            user_id="user-001",
            payload={"agent_type": "Hunter", "task_summary": "Found 3 leads"},
        )
        classification = EventClassification(event_type="agent.task_finished", handler_key="internal")

        output = await handler.process(envelope, classification)
        assert "Hunter" in output.summary
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the handler implementations**

Create `backend/src/services/event_handlers/__init__.py`:

```python
from .email_handler import EmailEventHandler
from .calendar_handler import CalendarEventHandler
from .internal_handler import InternalEventHandler

__all__ = ["EmailEventHandler", "CalendarEventHandler", "InternalEventHandler"]
```

Create `backend/src/services/event_handlers/email_handler.py`:

```python
"""Email event handler. Bridges EventTriggerService to existing email pipeline."""

import logging
from typing import Any

from ..event_trigger import EventEnvelope, EventClassification, HandlerOutput

logger = logging.getLogger(__name__)


class EmailEventHandler:
    """Process email events and create Pulse signals."""

    def __init__(self, db: Any, email_service: Any = None) -> None:
        self.db = db
        self.email_service = email_service

    async def process(
        self, envelope: EventEnvelope, classification: EventClassification,
    ) -> HandlerOutput:
        payload = envelope.payload
        sender = payload.get("sender", payload.get("from", "Unknown"))
        subject = payload.get("subject", "No subject")
        snippet = payload.get("snippet", payload.get("messageText", ""))[:200]
        message_id = payload.get("id", payload.get("messageId", ""))
        thread_id = payload.get("threadId", "")

        summary = f"Email from {sender}: {subject}"
        if classification.is_vip_sender:
            summary = f"VIP — {summary}"
        if classification.matched_leads:
            summary += " (matched lead)"

        signal = {
            "title": f"New email from {sender}",
            "summary": summary,
            "content": snippet,
            "source": "email",
            "signal_category": "email",
            "pulse_type": "event",
            "source_id": message_id,
            "metadata": {
                "sender": sender,
                "subject": subject,
                "thread_id": thread_id,
                "message_id": message_id,
            },
        }

        return HandlerOutput(
            signals=[signal],
            summary=summary,
            artifacts=[{
                "type": "email_notification",
                "sender": sender,
                "subject": subject,
                "message_id": message_id,
            }],
        )
```

Create `backend/src/services/event_handlers/calendar_handler.py`:

```python
"""Calendar event handler. Processes calendar events from Composio triggers."""

import logging
from typing import Any

from ..event_trigger import EventEnvelope, EventClassification, HandlerOutput

logger = logging.getLogger(__name__)


class CalendarEventHandler:
    """Process calendar events and trigger meeting brief generation."""

    def __init__(self, db: Any, meeting_brief_service: Any = None) -> None:
        self.db = db
        self.meeting_brief_service = meeting_brief_service

    async def process(
        self, envelope: EventEnvelope, classification: EventClassification,
    ) -> HandlerOutput:
        payload = envelope.payload
        summary_text = payload.get("summary", payload.get("subject", "Meeting"))
        start = payload.get("start", {}).get("dateTime", "")
        attendees = payload.get("attendees", [])
        event_id = payload.get("id", "")
        status = payload.get("status", "confirmed")

        event_action = str(envelope.event_type).split(".")[-1]

        if event_action == "event_deleted" or status == "cancelled":
            summary = f"Meeting cancelled: {summary_text}"
            signal_title = f"Meeting cancelled: {summary_text}"
        elif event_action == "event_updated":
            summary = f"Meeting updated: {summary_text}"
            signal_title = f"Meeting changed: {summary_text}"
        else:
            summary = f"New meeting: {summary_text}"
            signal_title = f"New meeting: {summary_text}"

        signal = {
            "title": signal_title,
            "summary": summary,
            "content": f"{summary_text} — {start}" if start else summary_text,
            "source": "calendar",
            "signal_category": "calendar",
            "pulse_type": "event",
            "source_id": event_id,
            "metadata": {
                "event_id": event_id,
                "start": start,
                "attendee_count": len(attendees),
                "status": status,
            },
        }

        return HandlerOutput(
            signals=[signal],
            summary=summary,
            artifacts=[{
                "type": "calendar_notification",
                "event_id": event_id,
                "summary": summary_text,
                "action": event_action,
            }],
        )
```

Create `backend/src/services/event_handlers/internal_handler.py`:

```python
"""Internal event handler for ARIA-to-ARIA events."""

import logging
from typing import Any

from ..event_trigger import EventEnvelope, EventClassification, HandlerOutput

logger = logging.getLogger(__name__)


class InternalEventHandler:
    """Process internal state change events."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def process(
        self, envelope: EventEnvelope, classification: EventClassification,
    ) -> HandlerOutput:
        payload = envelope.payload
        event_type = str(envelope.event_type)

        if event_type == "goal.completed":
            goal_title = payload.get("title", "Goal")
            summary = f"Goal completed: {goal_title}"
        elif event_type == "goal.blocked":
            summary = f"Goal blocked: {payload.get('title', 'Goal')} — {payload.get('reason', '')}"
        elif event_type == "agent.task_finished":
            summary = f"{payload.get('agent_type', 'Agent')} finished: {payload.get('task_summary', '')}"
        else:
            summary = f"Event: {event_type}"

        signal = {
            "title": summary[:80],
            "summary": summary,
            "source": "internal",
            "signal_category": "goal" if "goal" in event_type else "email",
            "pulse_type": "event",
            "source_id": payload.get("id", ""),
        }

        return HandlerOutput(signals=[signal], summary=summary)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_handlers.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/event_handlers/ backend/tests/test_event_handlers.py
git commit -m "feat: add email, calendar, and internal event handlers"
```

---

## Task 4: Composio Webhook Endpoint

**Files:**
- Create: `backend/src/api/routes/composio_webhooks.py`
- Test: `backend/tests/test_composio_webhooks.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_composio_webhooks.py`:

```python
"""Tests for Composio webhook ingestion endpoint."""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.composio_webhooks import router, COMPOSIO_TRIGGER_MAP
from src.services.event_trigger import EventTriggerService, EventType


@pytest.fixture
def mock_event_service():
    service = MagicMock(spec=EventTriggerService)
    service.ingest = AsyncMock(return_value={
        "status": "processed", "event_log_id": "evt-001", "latency_ms": 15,
    })
    return service


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Default: resolve user from composio_connection_id
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "user-001"}]
    )
    return db


@pytest.fixture
def app(mock_event_service, mock_db):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    test_app.state.event_trigger_service = mock_event_service
    test_app.state.db = mock_db
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestComposioWebhook:
    def test_gmail_webhook_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "GMAIL_NEW_GMAIL_MESSAGE",
            "trigger_id": "trig-001",
            "connected_account_id": "conn-abc",
            "payload": {
                "id": "msg-gmail-001",
                "sender": "sarah@lonza.com",
                "subject": "PFA Pricing",
                "snippet": "Thanks for following up...",
            },
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        mock_event_service.ingest.assert_called_once()

    def test_calendar_webhook_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "GOOGLECALENDAR_EVENT_CREATED",
            "trigger_id": "trig-002",
            "connected_account_id": "conn-abc",
            "payload": {
                "id": "cal-001",
                "summary": "Q1 Review",
                "start": {"dateTime": "2026-03-02T10:00:00Z"},
            },
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200

    def test_unknown_trigger_still_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "UNKNOWN_TRIGGER_TYPE",
            "trigger_id": "trig-003",
            "connected_account_id": "conn-abc",
            "payload": {"data": "some data"},
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200

    def test_unresolvable_user_returns_200(self, client, mock_db):
        # No user found for this connected_account_id
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        payload = {
            "trigger_name": "GMAIL_NEW_GMAIL_MESSAGE",
            "trigger_id": "trig-004",
            "connected_account_id": "conn-unknown",
            "payload": {"id": "msg-002"},
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "user_not_found"

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/api/v1/webhooks/composio",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_trigger_map_covers_main_integrations(self):
        assert "GMAIL_NEW_GMAIL_MESSAGE" in COMPOSIO_TRIGGER_MAP
        assert "OUTLOOK_NEW_EMAIL" in COMPOSIO_TRIGGER_MAP
        assert "GOOGLECALENDAR_EVENT_CREATED" in COMPOSIO_TRIGGER_MAP
        assert "SALESFORCE_NEW_LEAD" in COMPOSIO_TRIGGER_MAP
        assert "HUBSPOT_DEAL_STAGE_CHANGED" in COMPOSIO_TRIGGER_MAP
        assert "SLACK_RECEIVE_MESSAGE" in COMPOSIO_TRIGGER_MAP
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_composio_webhooks.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the Composio webhook route**

Create `backend/src/api/routes/composio_webhooks.py`:

```python
"""Composio webhook ingestion endpoint for event triggers.

Receives POST requests from Composio when triggers fire
(new email, calendar change, CRM update, etc.).

Security: Verify HMAC signature using COMPOSIO_WEBHOOK_SECRET env var.
No JWT auth — Composio can't send JWTs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from src.services.event_trigger import (
    EventEnvelope,
    EventSource,
    EventTriggerService,
    EventType,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["composio-webhooks"])

COMPOSIO_TRIGGER_MAP: dict[str, EventType] = {
    "GMAIL_NEW_GMAIL_MESSAGE": EventType.EMAIL_RECEIVED,
    "GMAIL_NEW_GMAIL_THREAD": EventType.EMAIL_THREAD_REPLY,
    "OUTLOOK_NEW_EMAIL": EventType.EMAIL_RECEIVED,
    "OUTLOOK_NEW_CALENDAR_EVENT": EventType.CALENDAR_EVENT_CREATED,
    "OUTLOOK_CALENDAR_EVENT_UPDATED": EventType.CALENDAR_EVENT_UPDATED,
    "GOOGLECALENDAR_EVENT_CREATED": EventType.CALENDAR_EVENT_CREATED,
    "GOOGLECALENDAR_EVENT_UPDATED": EventType.CALENDAR_EVENT_UPDATED,
    "GOOGLECALENDAR_EVENT_DELETED": EventType.CALENDAR_EVENT_DELETED,
    "SALESFORCE_NEW_LEAD": EventType.CRM_LEAD_CREATED,
    "SALESFORCE_LEAD_UPDATED": EventType.CRM_LEAD_UPDATED,
    "SALESFORCE_OPPORTUNITY_STAGE_CHANGED": EventType.CRM_DEAL_STAGE_CHANGED,
    "HUBSPOT_NEW_CONTACT": EventType.CRM_CONTACT_UPDATED,
    "HUBSPOT_DEAL_STAGE_CHANGED": EventType.CRM_DEAL_STAGE_CHANGED,
    "SLACK_RECEIVE_MESSAGE": EventType.SLACK_MESSAGE_RECEIVED,
    "SLACK_RECEIVE_MENTION": EventType.SLACK_MENTION,
}


def _verify_composio_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify Composio webhook HMAC-SHA256 signature."""
    if not signature:
        return False
    computed = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/composio")
async def handle_composio_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(None, alias="x-webhook-signature"),
) -> dict[str, Any]:
    """Receive webhook from Composio when a trigger fires.

    Always returns 200 to prevent Composio from retrying.
    Errors are logged internally in event_log.
    """
    body = await request.body()

    # Verify signature if secret is configured
    webhook_secret = os.getenv("COMPOSIO_WEBHOOK_SECRET")
    if webhook_secret and x_webhook_signature:
        if not _verify_composio_signature(body, x_webhook_signature, webhook_secret):
            logger.warning("Invalid Composio webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    trigger_name = data.get("trigger_name", "")
    trigger_id = data.get("trigger_id", "")
    connected_account_id = data.get("connected_account_id", "")
    payload = data.get("payload", {})

    logger.info("Composio webhook received: %s (trigger_id=%s)", trigger_name, trigger_id)

    # Map trigger to ARIA event type
    event_type: EventType | str = COMPOSIO_TRIGGER_MAP.get(trigger_name, f"composio.{trigger_name.lower()}")

    # Resolve user_id from connected_account_id
    db = request.app.state.db
    user_id = _resolve_user_id(db, connected_account_id)
    if not user_id:
        logger.error("Cannot resolve user for connected_account_id: %s", connected_account_id)
        return {"status": "user_not_found", "connected_account_id": connected_account_id}

    source_id = _extract_source_id(trigger_name, payload)

    envelope = EventEnvelope(
        event_type=event_type,
        source=EventSource.COMPOSIO,
        user_id=user_id,
        source_id=source_id,
        payload=payload,
        metadata={
            "trigger_name": trigger_name,
            "trigger_id": trigger_id,
            "connected_account_id": connected_account_id,
        },
    )

    event_service: EventTriggerService = request.app.state.event_trigger_service
    result = await event_service.ingest(envelope)

    return {"status": "accepted", "result": result}


def _resolve_user_id(db: Any, connected_account_id: str) -> str | None:
    """Look up ARIA user_id from Composio connected_account_id."""
    try:
        # Check composio_connection_id in user_integrations
        result = db.table("user_integrations") \
            .select("user_id") \
            .eq("composio_connection_id", connected_account_id) \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]["user_id"]

        # Fallback: check composio_account_id
        result = db.table("user_integrations") \
            .select("user_id") \
            .eq("composio_account_id", connected_account_id) \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]["user_id"]
    except Exception as e:
        logger.error("User resolution failed: %s", e)

    return None


def _extract_source_id(trigger_name: str, payload: dict) -> str:
    """Extract a stable unique ID from the event payload for deduplication."""
    if "GMAIL" in trigger_name:
        return payload.get("id", payload.get("messageId", ""))
    elif "OUTLOOK" in trigger_name:
        return payload.get("id", payload.get("internetMessageId", ""))
    elif "CALENDAR" in trigger_name or "GOOGLECALENDAR" in trigger_name:
        return payload.get("id", payload.get("eventId", ""))
    elif "SALESFORCE" in trigger_name:
        return payload.get("Id", payload.get("id", ""))
    elif "HUBSPOT" in trigger_name:
        return payload.get("objectId", payload.get("id", ""))
    elif "SLACK" in trigger_name:
        return payload.get("ts", payload.get("event_ts", ""))
    return ""
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_composio_webhooks.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/composio_webhooks.py backend/tests/test_composio_webhooks.py
git commit -m "feat: add Composio webhook ingestion endpoint with trigger mapping"
```

---

## Task 5: Wire Into FastAPI App + Test Endpoint

**Files:**
- Modify: `backend/src/main.py` (add import + router registration + lifespan init)
- Modify: `backend/src/api/routes/health.py` (add test-event endpoint)

**Step 1: Add import and router registration to main.py**

In `backend/src/main.py`, add to the import block (after line 70, the existing `webhooks` import):

```python
# After line 70: webhooks,  # Tavus webhook handler
# Add:
    composio_webhooks,  # Composio event trigger webhooks
```

Then add router registration (after line 355, the existing `webhooks.router` line):

```python
app.include_router(composio_webhooks.router, prefix="/api/v1")
```

**Step 2: Add EventTriggerService initialization to the lifespan function**

In the lifespan function (around line 244, before the `yield`), add:

```python
    # Event Trigger System: real-time event processing
    try:
        from src.db.supabase import get_supabase_client
        from src.core.ws import ws_manager
        from src.services.event_trigger import EventTriggerService
        from src.services.event_handlers import (
            EmailEventHandler,
            CalendarEventHandler,
            InternalEventHandler,
        )

        db = get_supabase_client()
        pulse_engine = None
        try:
            from src.services.intelligence_pulse import get_pulse_engine
            pulse_engine = get_pulse_engine()
        except Exception:
            logger.warning("Pulse Engine not available — events will deliver via WebSocket only")

        event_service = EventTriggerService(db, ws_manager, pulse_engine)
        event_service.register_handler("email", EmailEventHandler(db))
        event_service.register_handler("calendar", CalendarEventHandler(db))
        event_service.register_handler("internal", InternalEventHandler(db))
        _app.state.event_trigger_service = event_service
        _app.state.db = db  # Expose for webhook user resolution
        logger.info("EventTriggerService initialized with handlers: email, calendar, internal")
    except Exception:
        logger.exception("Failed to initialize EventTriggerService")
```

**Step 3: Add test-event endpoint to health routes**

In `backend/src/api/routes/health.py`, add after the `test-push` endpoint (after line ~195):

```python
@router.post("/test-event")
async def test_event_trigger(
    request: Request,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Test the full event trigger pipeline with a synthetic email event."""
    from uuid import uuid4
    from src.services.event_trigger import (
        EventTriggerService,
        EventEnvelope,
        EventType,
        EventSource,
    )

    event_service: EventTriggerService = request.app.state.event_trigger_service
    user_id = str(current_user.id)

    envelope = EventEnvelope(
        event_type=EventType.EMAIL_RECEIVED,
        source=EventSource.INTERNAL,
        user_id=user_id,
        source_id=f"test-{uuid4()}",
        payload={
            "sender": "sarah@lonza.com",
            "subject": "Re: PFA Vessel Pricing Discussion",
            "snippet": "Hi, thanks for the follow-up. I've reviewed the pricing and have a few questions about volume discounts...",
            "messageId": f"test-msg-{uuid4()}",
            "threadId": "test-thread-001",
        },
    )

    result = await event_service.ingest(envelope)
    return {"test": "event_trigger_pipeline", "result": result}
```

Add necessary imports at the top of health.py:
- `from fastapi import Request` (if not already imported)
- `from typing import Any` (if not already imported)
- `from src.api.deps import CurrentUser` (if not already imported — check existing imports)

**Step 4: Run existing tests to ensure nothing broke**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_trigger.py backend/tests/test_event_handlers.py backend/tests/test_composio_webhooks.py -v`
Expected: All tests PASS

**Step 5: Verify the app starts**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.main import app; print('App loads OK')"`
Expected: prints "App loads OK" (may show warnings about missing env vars, that's fine)

**Step 6: Commit**

```bash
git add backend/src/main.py backend/src/api/routes/health.py
git commit -m "feat: wire EventTriggerService into FastAPI app with test endpoint"
```

---

## Task 6: Reconciliation Sweep Stub

**Files:**
- Modify: `backend/src/services/scheduler.py` (add stub job)

**Step 1: Add reconciliation sweep stub function**

Add to `backend/src/services/scheduler.py` (before the `start_scheduler` function):

```python
async def _run_reconciliation_sweep() -> None:
    """Safety net: Check for events that webhooks might have missed.

    Runs every 30 min. Catches stragglers that Composio triggers didn't deliver.
    Checks: "Are there emails in inbox that DON'T have a matching event_log entry?"

    Currently a stub — will be wired to existing email scan logic later.
    """
    logger.info("Reconciliation sweep: stub (not yet implemented)")
```

**Step 2: Register the job in start_scheduler**

In the `start_scheduler()` function, add after the last `scheduler.add_job(...)` call:

```python
    scheduler.add_job(
        _run_reconciliation_sweep,
        "interval",
        minutes=30,
        id="reconciliation_sweep",
        name="Event reconciliation sweep",
    )
```

**Step 3: Run a quick sanity check**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.services.scheduler import _run_reconciliation_sweep; print('Import OK')"`
Expected: prints "Import OK"

**Step 4: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "feat: add reconciliation sweep stub to scheduler"
```

---

## Task 7: Verify Everything Works End-to-End

**Files:** None (verification only)

**Step 1: Run all new tests together**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_event_trigger.py backend/tests/test_event_handlers.py backend/tests/test_composio_webhooks.py -v --tb=short`
Expected: All tests PASS

**Step 2: Run a broader test sweep to confirm no regressions**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/ -v --tb=short -x --ignore=backend/tests/test_llm_gateway_smoke.py -k "not integration" 2>&1 | tail -30`
Expected: Existing tests still pass (some pre-existing failures are acceptable — compare with baseline of 5,320 pass / 92 fail from Session 7)

**Step 3: Verify imports work end-to-end**

Run:
```bash
cd /Users/dhruv/aria/backend && python -c "
from src.services.event_trigger import EventTriggerService, EventEnvelope, EventType, EventSource
from src.services.event_handlers import EmailEventHandler, CalendarEventHandler, InternalEventHandler
from src.api.routes.composio_webhooks import router as composio_router
print('All imports successful')
print(f'Event types: {len(EventType)}')
print(f'Composio webhook route: {composio_router.prefix}')
"
```
Expected: All imports succeed, prints counts

**Step 4: Final commit (if any test fixes were needed)**

```bash
git add -A
git commit -m "fix: address any test regressions from event trigger system"
```

---

## Acceptance Criteria Checklist

| # | Criterion | Verified By |
|---|-----------|-------------|
| 1 | `event_log` table created with indexes and RLS | Task 1 migration file |
| 2 | `POST /api/v1/webhooks/composio` accepts payloads and returns 200 | Task 4 tests |
| 3 | Classification is pure rules/regex, no LLM, <10ms | Task 2 tests + code review |
| 4 | Email events produce Pulse signal or WebSocket notification | Task 2 + Task 3 tests |
| 5 | Calendar events produce notification | Task 3 tests |
| 6 | Duplicate events detected and skipped (same source_id) | Task 2 test: `test_duplicate_detection_skips_event` |
| 7 | `POST /api/v1/health/test-event` sends synthetic event through pipeline | Task 5 endpoint |
| 8 | Event processing logged in `event_log` with status/timing | Task 2 implementation |
| 9 | Existing polling jobs/WebSocket/Pulse unchanged | Task 5 Step 2 regression test |
| 10 | No LLM calls in classification or routing | Code review — `_classify()` is pure regex |

## What Was NOT Built (intentionally deferred)

- Composio trigger setup/enablement (separate task)
- Email draft generation from events (existing pipeline handles this)
- Reconciliation sweep logic (stub only — wire when existing email scan is stable)
- CRM and Slack handlers (implement when those integrations are active)
- LiteLLM model routing rules (separate task)
