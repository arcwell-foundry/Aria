"""Episodic memory module for storing past events and interactions.

Episodic memory stores events that happened in the past, with:
- Bi-temporal tracking (when it occurred vs when it was recorded)
- Participant tracking for multi-party events
- Event type classification
- Rich context metadata

Episodes are stored in Graphiti (Neo4j) for temporal querying and
semantic search capabilities.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


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


class EpisodicMemory:
    """Service class for episodic memory operations.

    Provides async interface for storing, retrieving, and querying
    episodic memories. Uses Graphiti (Neo4j) as the underlying storage
    for temporal querying and semantic search capabilities.
    """

    async def store_episode(self, episode: Episode) -> str:
        """Store an episode in memory.

        Args:
            episode: The Episode instance to store.

        Returns:
            The ID of the stored episode.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("store_episode not yet implemented")

    async def get_episode(self, user_id: str, episode_id: str) -> Episode:
        """Retrieve a specific episode by ID.

        Args:
            user_id: The user ID who owns the episode.
            episode_id: The unique episode identifier.

        Returns:
            The Episode instance if found.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("get_episode not yet implemented")

    async def query_by_time_range(
        self, user_id: str, start: datetime, end: datetime, limit: int = 50
    ) -> list[Episode]:
        """Query episodes within a time range.

        Args:
            user_id: The user ID to query episodes for.
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).
            limit: Maximum number of episodes to return.

        Returns:
            List of Episode instances within the time range.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("query_by_time_range not yet implemented")

    async def query_by_event_type(
        self, user_id: str, event_type: str, limit: int = 50
    ) -> list[Episode]:
        """Query episodes by event type.

        Args:
            user_id: The user ID to query episodes for.
            event_type: The type of event (e.g., 'meeting', 'call', 'email').
            limit: Maximum number of episodes to return.

        Returns:
            List of Episode instances matching the event type.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("query_by_event_type not yet implemented")

    async def query_by_participant(
        self, user_id: str, participant: str, limit: int = 50
    ) -> list[Episode]:
        """Query episodes by participant.

        Args:
            user_id: The user ID to query episodes for.
            participant: The participant name to search for.
            limit: Maximum number of episodes to return.

        Returns:
            List of Episode instances involving the participant.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("query_by_participant not yet implemented")

    async def semantic_search(self, user_id: str, query: str, limit: int = 10) -> list[Episode]:
        """Search episodes using semantic similarity.

        Args:
            user_id: The user ID to search episodes for.
            query: The natural language query string.
            limit: Maximum number of episodes to return.

        Returns:
            List of Episode instances semantically similar to the query.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("semantic_search not yet implemented")

    async def delete_episode(self, user_id: str, episode_id: str) -> None:
        """Delete an episode from memory.

        Args:
            user_id: The user ID who owns the episode.
            episode_id: The unique episode identifier to delete.

        Raises:
            NotImplementedError: Method not yet implemented.
        """
        raise NotImplementedError("delete_episode not yet implemented")
