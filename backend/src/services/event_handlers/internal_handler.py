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
        event_type = getattr(envelope.event_type, "value", str(envelope.event_type))

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
