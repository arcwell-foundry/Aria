"""Episodic memory module for storing past events and interactions.

Episodic memory stores events that happened in the past, with:
- Bi-temporal tracking (when it occurred vs when it was recorded)
- Participant tracking for multi-party events
- Event type classification
- Rich context metadata

Episodes are stored in Graphiti (Neo4j) for temporal querying and
semantic search capabilities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Episode:
    """An episodic memory record representing a past event.

    Captures events like meetings, calls, emails, decisions, etc.
    with temporal awareness and participant tracking.
    """

    id: str
    user_id: str
    event_type: str  # meeting, email, call, decision, note, etc.
    content: str
    participants: list[str]
    occurred_at: datetime  # When the event actually happened
    recorded_at: datetime  # When we recorded it (bi-temporal)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize episode to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "content": self.content,
            "participants": self.participants,
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        """Create an Episode instance from a dictionary.

        Args:
            data: Dictionary containing episode data.

        Returns:
            Episode instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            event_type=data["event_type"],
            content=data["content"],
            participants=data["participants"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            recorded_at=datetime.fromisoformat(data["recorded_at"]),
            context=data.get("context", {}),
        )
