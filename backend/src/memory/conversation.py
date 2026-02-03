"""Conversation episode service for extracting durable memories.

Extracts structured information from conversations:
- Summary of key points
- Topics discussed
- Entities mentioned
- User emotional/cognitive state
- Outcomes and decisions
- Open threads requiring follow-up
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ConversationEpisode:
    """A durable memory extracted from a conversation.

    Represents the essential content of a conversation that should
    persist beyond the session for future context priming.
    """

    id: str
    user_id: str
    conversation_id: str
    summary: str
    key_topics: list[str]
    entities_discussed: list[str]
    user_state: dict[str, Any]
    outcomes: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    message_count: int
    duration_minutes: int
    started_at: datetime
    ended_at: datetime
    current_salience: float = 1.0
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "summary": self.summary,
            "key_topics": self.key_topics,
            "entities_discussed": self.entities_discussed,
            "user_state": self.user_state,
            "outcomes": self.outcomes,
            "open_threads": self.open_threads,
            "message_count": self.message_count,
            "duration_minutes": self.duration_minutes,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "current_salience": self.current_salience,
            "last_accessed_at": self.last_accessed_at.isoformat(),
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationEpisode:
        """Create a ConversationEpisode from a dictionary."""
        started_at = data["started_at"]
        ended_at = data["ended_at"]
        last_accessed = data.get("last_accessed_at")

        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        if isinstance(ended_at, str):
            ended_at = datetime.fromisoformat(ended_at)
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            conversation_id=data["conversation_id"],
            summary=data["summary"],
            key_topics=data.get("key_topics", []),
            entities_discussed=data.get("entities_discussed", []),
            user_state=data.get("user_state", {}),
            outcomes=data.get("outcomes", []),
            open_threads=data.get("open_threads", []),
            message_count=data.get("message_count", 0),
            duration_minutes=data.get("duration_minutes", 0),
            started_at=started_at,
            ended_at=ended_at,
            current_salience=data.get("current_salience", 1.0),
            last_accessed_at=last_accessed or datetime.now(UTC),
            access_count=data.get("access_count", 0),
        )
