"""Episodic memory module for storing past events and interactions.

Episodic memory stores events that happened in the past, with:
- Bi-temporal tracking (when it occurred vs when it was recorded)
- Participant tracking for multi-party events
- Event type classification
- Rich context metadata

Episodes are stored in Graphiti (Neo4j) for temporal querying and
semantic search capabilities, with Supabase as a durable fallback.
"""

import contextlib
import json
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
    for temporal querying and semantic search capabilities, with
    Supabase as a durable fallback for writes and reads.
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
            occurred_at: datetime | None = None
            recorded_at: datetime | None = None

            for line in lines:
                if line.startswith("Event Type:"):
                    event_type = line.replace("Event Type:", "").strip()
                elif line.startswith("Content:"):
                    content = line.replace("Content:", "").strip()
                elif line.startswith("Participants:"):
                    participants_str = line.replace("Participants:", "").strip()
                    participants = [p.strip() for p in participants_str.split(",") if p.strip()]
                elif line.startswith("Occurred At:"):
                    occurred_at_str = line.replace("Occurred At:", "").strip()
                    with contextlib.suppress(ValueError):
                        occurred_at = datetime.fromisoformat(occurred_at_str)
                elif line.startswith("Recorded At:"):
                    recorded_at_str = line.replace("Recorded At:", "").strip()
                    with contextlib.suppress(ValueError):
                        recorded_at = datetime.fromisoformat(recorded_at_str)

            # Fall back to edge created_at for occurred_at if not parsed
            if occurred_at is None:
                occurred_at = created_at if isinstance(created_at, datetime) else datetime.now(UTC)

            # Fall back to now for recorded_at if not parsed
            if recorded_at is None:
                recorded_at = datetime.now(UTC)

            return Episode(
                id=edge_uuid,
                user_id=user_id,
                event_type=event_type,
                content=content.strip(),
                participants=participants,
                occurred_at=occurred_at,
                recorded_at=recorded_at,
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

    # ── Supabase fallback helpers ────────────────────────────────

    def _store_to_supabase(self, episode: Episode) -> str:
        """Store an episode to the Supabase episodic_memories table.

        This is the durable write path: every episode is persisted here
        regardless of whether Graphiti succeeds.

        Args:
            episode: The Episode instance to store.

        Returns:
            The episode ID.
        """
        from src.db.supabase import SupabaseClient

        row = {
            "id": episode.id,
            "user_id": episode.user_id,
            "event_type": episode.event_type,
            "content": episode.content,
            "metadata": json.dumps(episode.to_dict()),
            "created_at": episode.occurred_at.isoformat(),
        }
        SupabaseClient.get_client().table("episodic_memories").upsert(row).execute()
        return episode.id

    def _query_from_supabase(
        self,
        user_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[Episode]:
        """Query episodes from the Supabase episodic_memories table.

        Used as a fallback when Graphiti is unavailable.

        Args:
            user_id: The user ID to filter by.
            filters: Optional filters. Supported keys:
                - event_type: exact match on event_type column
                - content_search: text search on content column
                - start: ISO datetime string for created_at >= filter
                - end: ISO datetime string for created_at <= filter
            limit: Maximum rows to return.

        Returns:
            List of Episode instances parsed from Supabase rows.
        """
        from src.db.supabase import SupabaseClient

        query = (
            SupabaseClient.get_client()
            .table("episodic_memories")
            .select("*")
            .eq("user_id", user_id)
        )

        if filters:
            if "event_type" in filters:
                query = query.eq("event_type", filters["event_type"])
            if "content_search" in filters:
                query = query.ilike("content", f"%{filters['content_search']}%")
            if "start" in filters:
                query = query.gte("created_at", filters["start"])
            if "end" in filters:
                query = query.lte("created_at", filters["end"])

        query = query.order("created_at", desc=True).limit(limit)
        response = query.execute()

        episodes: list[Episode] = []
        for row in response.data or []:
            episode = self._parse_supabase_row(row)
            if episode:
                episodes.append(episode)
        return episodes

    def _parse_supabase_row(self, row: dict[str, Any]) -> Episode | None:
        """Parse a Supabase row into an Episode.

        Prefers the full metadata JSONB blob when available, falling
        back to top-level columns.

        Args:
            row: A dictionary representing a row from episodic_memories.

        Returns:
            Episode if parsing succeeds, None otherwise.
        """
        try:
            metadata_raw = row.get("metadata")
            if metadata_raw:
                if isinstance(metadata_raw, str):
                    metadata = json.loads(metadata_raw)
                else:
                    metadata = metadata_raw
                # metadata should contain the full episode dict
                if "id" in metadata and "user_id" in metadata:
                    return Episode.from_dict(metadata)

            # Fallback: reconstruct from top-level columns
            created_at_str = row.get("created_at", "")
            created_at = (
                datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(UTC)
            )
            return Episode(
                id=row["id"],
                user_id=row["user_id"],
                event_type=row.get("event_type", "unknown"),
                content=row.get("content", ""),
                participants=[],
                occurred_at=created_at,
                recorded_at=datetime.now(UTC),
                context={},
            )
        except Exception as e:
            logger.warning(f"Failed to parse Supabase row to episode: {e}")
            return None

    # ── Public API ───────────────────────────────────────────────

    async def store_episode(self, episode: Episode) -> str:
        """Store an episode in memory.

        Always writes to Supabase first (durable), then attempts
        Graphiti for semantic search capabilities. If Graphiti fails
        the episode is still safely persisted in Supabase.

        Args:
            episode: The Episode instance to store.

        Returns:
            The ID of the stored episode.

        Raises:
            EpisodicMemoryError: If Supabase storage fails.
        """
        try:
            # Generate ID if not provided
            episode_id = episode.id if episode.id else str(uuid.uuid4())
            episode.id = episode_id

            # ── Step 1: Always store to Supabase (durable) ──
            supabase_ok = False
            try:
                self._store_to_supabase(episode)
                supabase_ok = True
            except Exception as sb_err:
                logger.warning(
                    "Supabase store failed, will try Graphiti",
                    extra={"episode_id": episode_id, "error": str(sb_err)},
                )

            # ── Step 2: Try to also store in Graphiti ──
            graphiti_ok = False
            try:
                client = await self._get_graphiti_client()
                episode_body = self._build_episode_body(episode)

                from graphiti_core.nodes import EpisodeType

                await client.add_episode(
                    name=episode_id,
                    episode_body=episode_body,
                    source=EpisodeType.text,
                    source_description=f"episodic_memory:{episode.user_id}",
                    reference_time=episode.occurred_at,
                )
                graphiti_ok = True
            except Exception as graphiti_err:
                logger.warning(
                    "Graphiti store failed for episode",
                    extra={
                        "episode_id": episode_id,
                        "user_id": episode.user_id,
                        "error": str(graphiti_err),
                    },
                )

            if not supabase_ok and not graphiti_ok:
                raise EpisodicMemoryError(
                    f"Failed to store episode {episode_id}: both Supabase and Graphiti failed"
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

        Tries Graphiti first for richer data, falls back to Supabase
        if Graphiti is unavailable.

        Args:
            user_id: The user who owns the episode.
            episode_id: The episode ID.

        Returns:
            The requested Episode.

        Raises:
            EpisodeNotFoundError: If episode doesn't exist in either store.
            EpisodicMemoryError: If retrieval fails.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()

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

            if records:
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

                if episode is not None:
                    return episode

        except Exception as graphiti_err:
            logger.warning(
                "Graphiti get_episode failed, falling back to Supabase",
                extra={"episode_id": episode_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            from src.db.supabase import SupabaseClient

            response = (
                SupabaseClient.get_client()
                .table("episodic_memories")
                .select("*")
                .eq("id", episode_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            if response.data:
                episode = self._parse_supabase_row(response.data[0])
                if episode is not None:
                    return episode
        except Exception as sb_err:
            logger.warning(
                "Supabase get_episode also failed",
                extra={"episode_id": episode_id, "error": str(sb_err)},
            )

        raise EpisodeNotFoundError(episode_id)

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

        Tries Graphiti first for semantic-aware results, falls back
        to Supabase SQL filtering on created_at.

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
            EpisodicMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()
            query = f"episodes for user {user_id} between {start.isoformat()} and {end.isoformat()}"
            results = await client.search(query)

            episodes = []
            for edge in results[:limit]:
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode:
                    episodes.append(episode)
            return episodes
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti query_by_time_range failed, falling back to Supabase",
                extra={"user_id": user_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            filters: dict[str, Any] = {
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
            return self._query_from_supabase(user_id, filters=filters, limit=limit)
        except Exception as e:
            logger.exception("Supabase fallback also failed for query_by_time_range")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def query_by_event_type(
        self,
        user_id: str,
        event_type: str,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Query episodes by event type.

        Tries Graphiti first, falls back to Supabase with event_type
        SQL filter.

        Args:
            user_id: The user ID to query episodes for.
            event_type: The type of event (e.g., 'meeting', 'call', 'email').
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances matching the event type.

        Raises:
            EpisodicMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()
            query = f"{event_type} events for user {user_id}"
            results = await client.search(query)

            episodes = []
            for edge in results[:limit]:
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode and episode.event_type == event_type:
                    episodes.append(episode)
            return episodes
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti query_by_event_type failed, falling back to Supabase",
                extra={"user_id": user_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            filters: dict[str, Any] = {"event_type": event_type}
            return self._query_from_supabase(user_id, filters=filters, limit=limit)
        except Exception as e:
            logger.exception("Supabase fallback also failed for query_by_event_type")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def query_by_participant(
        self,
        user_id: str,
        participant: str,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Query episodes by participant.

        Tries Graphiti first, falls back to Supabase with text search
        on content.

        Args:
            user_id: The user ID to query episodes for.
            participant: The participant name to search for.
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances involving the participant.

        Raises:
            EpisodicMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()
            query = f"interactions with {participant} for user {user_id}"
            results = await client.search(query)

            episodes = []
            participant_lower = participant.lower()
            for edge in results[:limit]:
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode and (
                    any(participant_lower in p.lower() for p in episode.participants)
                    or participant_lower in episode.content.lower()
                ):
                    episodes.append(episode)
            return episodes
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti query_by_participant failed, falling back to Supabase",
                extra={"user_id": user_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            filters: dict[str, Any] = {"content_search": participant}
            return self._query_from_supabase(user_id, filters=filters, limit=limit)
        except Exception as e:
            logger.exception("Supabase fallback also failed for query_by_participant")
            raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e

    async def semantic_search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        as_of: datetime | None = None,
    ) -> list[Episode]:
        """Search episodes using semantic similarity.

        Tries Graphiti first (best semantic search), falls back to
        Supabase text search on content.

        Args:
            user_id: The user ID to search episodes for.
            query: The natural language query string.
            limit: Maximum number of episodes to return.
            as_of: Optional point-in-time filter. If provided, only episodes
                   recorded on or before this datetime are included.

        Returns:
            List of Episode instances semantically similar to the query.

        Raises:
            EpisodicMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()
            search_query = f"{query} (user: {user_id})"
            results = await client.search(search_query)

            episodes = []
            for edge in results[:limit]:
                if as_of is not None:
                    fact = getattr(edge, "fact", "")
                    recorded_at = self._extract_recorded_at_from_fact(fact)
                    if recorded_at is not None and recorded_at > as_of:
                        continue

                episode = self._parse_edge_to_episode(edge, user_id)
                if episode:
                    episodes.append(episode)
            return episodes
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti semantic_search failed, falling back to Supabase",
                extra={"user_id": user_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            filters: dict[str, Any] = {"content_search": query}
            return self._query_from_supabase(user_id, filters=filters, limit=limit)
        except Exception as e:
            logger.exception("Supabase fallback also failed for semantic_search")
            raise EpisodicMemoryError(f"Failed to search episodes: {e}") from e

    async def delete_episode(self, user_id: str, episode_id: str) -> None:
        """Delete an episode from both stores.

        Always deletes from Supabase. Also attempts Graphiti deletion;
        a Graphiti failure is logged but does not raise.

        Args:
            user_id: The user who owns the episode.
            episode_id: The episode ID to delete.

        Raises:
            EpisodeNotFoundError: If episode doesn't exist in either store.
            EpisodicMemoryError: If deletion fails in Supabase.
        """
        supabase_deleted = False
        graphiti_deleted = False

        # ── Always delete from Supabase ──
        try:
            from src.db.supabase import SupabaseClient

            response = (
                SupabaseClient.get_client()
                .table("episodic_memories")
                .delete()
                .eq("id", episode_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data:
                supabase_deleted = True
        except Exception as sb_err:
            logger.warning(
                "Supabase delete_episode failed",
                extra={"episode_id": episode_id, "error": str(sb_err)},
            )

        # ── Try to delete from Graphiti too ──
        try:
            client = await self._get_graphiti_client()

            query = """
            MATCH (e:Episode)
            WHERE e.name = $episode_name
            DETACH DELETE e
            RETURN count(e) as deleted
            """

            episode_name = episode_id

            result = await client.driver.execute_query(
                query,
                episode_name=episode_name,
            )

            records = result[0] if result else []
            deleted_count = records[0]["deleted"] if records else 0
            if deleted_count > 0:
                graphiti_deleted = True
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti delete_episode failed",
                extra={"episode_id": episode_id, "error": str(graphiti_err)},
            )

        if not supabase_deleted and not graphiti_deleted:
            raise EpisodeNotFoundError(episode_id)

        logger.info("Deleted episode", extra={"episode_id": episode_id, "user_id": user_id})
