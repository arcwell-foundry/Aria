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
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.core.exceptions import EpisodicMemoryError

if TYPE_CHECKING:
    from graphiti_core import Graphiti

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

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            EpisodicMemoryError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise EpisodicMemoryError(f"Failed to get Graphiti client: {e}") from e

    def _build_episode_body(self, episode: Episode) -> str:
        """Build a structured episode body string for storage.

        Args:
            episode: The Episode instance to serialize.

        Returns:
            Structured text representation of the episode.
        """
        parts = [
            f"Event Type: {episode.event_type}",
            f"Content: {episode.content}",
            f"Occurred At: {episode.occurred_at.isoformat()}",
            f"Recorded At: {episode.recorded_at.isoformat()}",
        ]

        if episode.participants:
            parts.append(f"Participants: {', '.join(episode.participants)}")

        if episode.context:
            context_items = [f"{k}={v}" for k, v in episode.context.items()]
            parts.append(f"Context: {'; '.join(context_items)}")

        return "\n".join(parts)

    async def store_episode(self, episode: Episode) -> str:
        """Store an episode in memory.

        Args:
            episode: The Episode instance to store.

        Returns:
            The ID of the stored episode.

        Raises:
            EpisodicMemoryError: If storage fails.
        """
        try:
            # Generate ID if not provided
            episode_id = episode.id if episode.id else str(uuid.uuid4())

            # Get Graphiti client
            client = await self._get_graphiti_client()

            # Build episode body
            episode_body = self._build_episode_body(episode)

            # Store in Graphiti
            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=episode_id,
                episode_body=episode_body,
                source=EpisodeType.text,
                source_description=f"episodic_memory:{episode.user_id}",
                reference_time=episode.occurred_at,
            )

            logger.info(f"Stored episode {episode_id} for user {episode.user_id}")
            return episode_id

        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception(f"Failed to store episode: {e}")
            raise EpisodicMemoryError(f"Failed to store episode: {e}") from e

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
