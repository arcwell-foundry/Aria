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

        event_type_val = getattr(envelope.event_type, "value", str(envelope.event_type))
        event_action = event_type_val.split(".")[-1]

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
