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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.exceptions import EpisodeNotFoundError, EpisodicMemoryError
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

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

    def _parse_edge_to_episode(self, edge: Any, user_id: str) -> Episode | None:
        """Parse a Graphiti edge into an Episode.

        Args:
            edge: The Graphiti edge object.
            user_id: The expected user ID.

        Returns:
            Episode if parsing succeeds and matches user, None otherwise.
        """
        try:
            fact = getattr(edge, "fact", "")
            created_at = getattr(edge, "created_at", datetime.now(UTC))
            # Try to get edge uuid, fall back to generating new one
            edge_uuid = getattr(edge, "uuid", None) or str(uuid.uuid4())

            # Parse structured content from fact
            lines = fact.split("\n")
            event_type = "unknown"
            content = ""
            participants: list[str] = []

            for line in lines:
                if line.startswith("Event Type:"):
                    event_type = line.replace("Event Type:", "").strip()
                elif line.startswith("Content:"):
                    content = line.replace("Content:", "").strip()
                elif line.startswith("Participants:"):
                    participants_str = line.replace("Participants:", "").strip()
                    participants = [p.strip() for p in participants_str.split(",") if p.strip()]

            return Episode(
                id=edge_uuid,
                user_id=user_id,
                event_type=event_type,
                content=content.strip(),
                participants=participants,
                occurred_at=created_at if isinstance(created_at, datetime) else datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                context={},
            )
        except Exception as e:
            logger.warning(f"Failed to parse edge to episode: {e}")
            return None

    def _parse_content_to_episode(
        self,
        episode_id: str,
        content: str,
        user_id: str,
        created_at: datetime,
    ) -> Episode | None:
        """Parse episode content string into Episode object.

        Args:
            episode_id: The episode ID.
            content: The raw content string.
            user_id: The user ID.
            created_at: When the episode was created.

        Returns:
            Episode if parsing succeeds, None otherwise.
        """
        try:
            lines = content.split("\n")
            event_type = "unknown"
            episode_content = ""
            participants: list[str] = []

            for line in lines:
                if line.startswith("Event Type:"):
                    event_type = line.replace("Event Type:", "").strip()
                elif line.startswith("Participants:"):
                    participants_str = line.replace("Participants:", "").strip()
                    participants = [p.strip() for p in participants_str.split(",") if p.strip()]
                elif line.startswith("Content:"):
                    episode_content = line.replace("Content:", "").strip()
                elif (
                    not any(
                        line.startswith(p) for p in ["Occurred At:", "Recorded At:", "Context:"]
                    )
                    and episode_content
                ):
                    episode_content += "\n" + line

            return Episode(
                id=episode_id,
                user_id=user_id,
                event_type=event_type,
                content=episode_content.strip(),
                participants=participants,
                occurred_at=created_at,
                recorded_at=datetime.now(UTC),
                context={},
            )
        except Exception as e:
            logger.warning(f"Failed to parse episode content: {e}")
            return None

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

            # Audit log the creation
            await log_memory_operation(
                user_id=episode.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.EPISODIC,
                memory_id=episode.id,
                metadata={"event_type": episode.event_type},
                suppress_errors=True,
            )

            return episode_id

        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception(f"Failed to store episode: {e}")
            raise EpisodicMemoryError(f"Failed to store episode: {e}") from e

    async def get_episode(self, user_id: str, episode_id: str) -> Episode:
        """Retrieve a specific episode by ID.

        Args:
            user_id: The user who owns the episode.
            episode_id: The episode ID.

        Returns:
            The requested Episode.

        Raises:
            EpisodeNotFoundError: If episode doesn't exist.
            EpisodicMemoryError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Query for specific episode by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $episode_name
            RETURN e
            """

            episode_name = episode_id

            result = await client.driver.execute_query(
                query,
                episode_name=episode_name,
            )

            records = result[0] if result else []

            if not records:
                raise EpisodeNotFoundError(episode_id)

            # Parse the node into an Episode
            node = records[0]["e"]
            content = getattr(node, "content", "") or node.get("content", "")
            created_at = getattr(node, "created_at", None) or node.get("created_at")

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            elif created_at is None:
                created_at = datetime.now(UTC)

            episode = self._parse_content_to_episode(
                episode_id=episode_id,
                content=content,
                user_id=user_id,
                created_at=created_at,
            )

            if episode is None:
                raise EpisodeNotFoundError(episode_id)

            return episode

        except EpisodeNotFoundError:
            raise
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get episode", extra={"episode_id": episode_id})
            raise EpisodicMemoryError(f"Failed to get episode: {e}") from e

    def _extract_recorded_at_from_fact(self, fact: str) -> datetime | None:
        """Extract recorded_at timestamp from a fact string.

        Args:
            fact: The fact string containing episode metadata.

        Returns:
            The recorded_at datetime if found, None otherwise.
        """
        for line in fact.split("\n"):
            if line.startswith("Recorded At:"):
                recorded_at_str = line.replace("Recorded At:", "").strip()
                try:
                    return datetime.fromisoformat(recorded_at_str)
                except ValueError:
                    return None
        return None

    async def query_by_time_range(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Query episodes within a time range.

        Args:
            user_id: The user ID to query episodes for.
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances within the time range.

        Raises:
            EpisodicMemoryError: If the query fails.
        """
        try:
            client = await self._get_graphiti_client()
            query = f"episodes for user {user_id} between {start.isoformat()} and {end.isoformat()}"
            results = await client.search(query)

            episodes = []
            for edge in results[:limit]:
                # Apply as_of filter if provided
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        # Skip episodes recorded after the as_of date
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode:
                    episodes.append(episode)
            return episodes
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to query episodes by time range")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def query_by_event_type(
        self,
        user_id: str,
        event_type: str,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Query episodes by event type.

        Args:
            user_id: The user ID to query episodes for.
            event_type: The type of event (e.g., 'meeting', 'call', 'email').
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances matching the event type.

        Raises:
            EpisodicMemoryError: If the query fails.
        """
        try:
            client = await self._get_graphiti_client()
            query = f"{event_type} events for user {user_id}"
            results = await client.search(query)

            episodes = []
            for edge in results[:limit]:
                # Apply as_of filter if provided
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        # Skip episodes recorded after the as_of date
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode and episode.event_type == event_type:
                    episodes.append(episode)
            return episodes
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to query episodes by event type")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def query_by_participant(
        self,
        user_id: str,
        participant: str,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Query episodes by participant.

        Args:
            user_id: The user ID to query episodes for.
            participant: The participant name to search for.
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances involving the participant.

        Raises:
            EpisodicMemoryError: If the query fails.
        """
        try:
            client = await self._get_graphiti_client()
            query = f"interactions with {participant} for user {user_id}"
            results = await client.search(query)

            episodes = []
            participant_lower = participant.lower()
            for edge in results[:limit]:
                # Apply as_of filter if provided
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        # Skip episodes recorded after the as_of date
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode and (
                    any(participant_lower in p.lower() for p in episode.participants)
                    or participant_lower in episode.content.lower()
                ):
                    episodes.append(episode)
            return episodes
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to query episodes by participant")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def semantic_search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Search episodes using semantic similarity.

        Args:
            user_id: The user ID to search episodes for.
            query: The natural language query string.
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances semantically similar to the query.

        Raises:
            EpisodicMemoryError: If the search fails.
        """
        try:
            client = await self._get_graphiti_client()
            search_query = f"{query} (user: {user_id})"
            results = await client.search(search_query)

            episodes = []
            for edge in results[:limit]:
                # Apply as_of filter if provided
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        # Skip episodes recorded after the as_of date
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode:
                    episodes.append(episode)
            return episodes
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to perform semantic search")
            raise EpisodicMemoryError(f"Failed to search episodes: {e}") from e

    async def delete_episode(self, user_id: str, episode_id: str) -> None:
        """Delete an episode.

        Args:
            user_id: The user who owns the episode.
            episode_id: The episode ID to delete.

        Raises:
            EpisodeNotFoundError: If episode doesn't exist.
            EpisodicMemoryError: If deletion fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Delete episode node by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $episode_name
            DETACH DELETE e
            RETURN count(e) as deleted
            """

            episode_name = episode_id  # Use episode_id directly as name

            result = await client.driver.execute_query(
                query,
                episode_name=episode_name,
            )

            # Check if episode was found and deleted
            records = result[0] if result else []
            deleted_count = records[0]["deleted"] if records else 0

            if deleted_count == 0:
                raise EpisodeNotFoundError(episode_id)

            logger.info("Deleted episode", extra={"episode_id": episode_id, "user_id": user_id})

        except EpisodeNotFoundError:
            raise
        except EpisodicMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete episode", extra={"episode_id": episode_id})
            raise EpisodicMemoryError(f"Failed to delete episode: {e}") from e
