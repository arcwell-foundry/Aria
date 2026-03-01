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
