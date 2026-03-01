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
