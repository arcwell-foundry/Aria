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
