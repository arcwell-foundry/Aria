"""Semantic memory module for storing facts and knowledge.

Semantic memory stores factual knowledge with:
- Subject-predicate-object triple structure
- Confidence scores (0.0-1.0) based on source reliability
- Temporal validity windows (valid_from, valid_to)
- Source tracking for provenance
- Soft invalidation for history preservation
- Contradiction detection

Facts are stored in Graphiti (Neo4j) for semantic search and
temporal querying capabilities.
"""

import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import FactNotFoundError, SemanticMemoryError  # noqa: F401
from src.memory.confidence import ConfidenceScorer

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class FactSource(Enum):
    """Source of a semantic fact, used for confidence scoring."""

    USER_STATED = "user_stated"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    CRM_IMPORT = "crm_import"
    WEB_RESEARCH = "web_research"


# Base confidence by source type
SOURCE_CONFIDENCE: dict[FactSource, float] = {
    FactSource.USER_STATED: 0.95,
    FactSource.CRM_IMPORT: 0.90,
    FactSource.EXTRACTED: 0.75,
    FactSource.WEB_RESEARCH: 0.70,
    FactSource.INFERRED: 0.60,
}


@dataclass
class SemanticFact:
    """A semantic fact representing knowledge about an entity.

    Uses subject-predicate-object triple structure (e.g., "John works_at Acme").
    Tracks confidence, source, and temporal validity.
    """

    id: str
    user_id: str
    subject: str  # Entity the fact is about
    predicate: str  # Relationship type
    object: str  # Value or related entity
    confidence: float  # 0.0 to 1.0
    source: FactSource
    valid_from: datetime
    valid_to: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    last_confirmed_at: datetime | None = None  # When fact was last confirmed
    corroborating_sources: list[str] | None = None  # List of source IDs that corroborate

    def __post_init__(self) -> None:
        """Initialize mutable defaults."""
        if self.corroborating_sources is None:
            self.corroborating_sources = []

    def to_dict(self) -> dict[str, Any]:
        """Serialize fact to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
            "invalidation_reason": self.invalidation_reason,
            "last_confirmed_at": self.last_confirmed_at.isoformat()
            if self.last_confirmed_at
            else None,
            "corroborating_sources": self.corroborating_sources or [],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticFact":
        """Create a SemanticFact instance from a dictionary.

        Args:
            data: Dictionary containing fact data.

        Returns:
            SemanticFact instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            confidence=data["confidence"],
            source=FactSource(data["source"]),
            valid_from=datetime.fromisoformat(data["valid_from"]),
            valid_to=datetime.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
            invalidated_at=datetime.fromisoformat(data["invalidated_at"])
            if data.get("invalidated_at")
            else None,
            invalidation_reason=data.get("invalidation_reason"),
            last_confirmed_at=datetime.fromisoformat(data["last_confirmed_at"])
            if data.get("last_confirmed_at")
            else None,
            corroborating_sources=data.get("corroborating_sources") or [],
        )

    def is_valid(self, as_of: datetime | None = None) -> bool:
        """Check if this fact is valid at a given point in time.

        Args:
            as_of: The point in time to check validity. Defaults to now.

        Returns:
            True if the fact is valid at the specified time.
        """
        check_time = as_of or datetime.now(UTC)

        # Invalidated facts are never valid
        if self.invalidated_at is not None:
            return False

        # Check if we're within the validity window
        if check_time < self.valid_from:
            return False

        return not (self.valid_to is not None and check_time > self.valid_to)

    def contradicts(self, other: "SemanticFact") -> bool:
        """Check if this fact contradicts another fact.

        Two facts contradict if they have the same subject and predicate
        but different objects. This is used for contradiction detection
        when adding new facts.

        Args:
            other: Another fact to compare against.

        Returns:
            True if the facts contradict each other.
        """
        return (
            self.subject.lower() == other.subject.lower()
            and self.predicate.lower() == other.predicate.lower()
            and self.object.lower() != other.object.lower()
        )


class SemanticMemory:
    """Service for storing and querying semantic facts in Graphiti.

    Provides async methods for CRUD operations, contradiction detection,
    and various query patterns on factual knowledge stored in the
    temporal knowledge graph.
    """

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            SemanticMemoryError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise SemanticMemoryError(f"Failed to get Graphiti client: {e}") from e

    def _build_fact_body(self, fact: SemanticFact) -> str:
        """Build a structured fact body string for storage.

        Args:
            fact: The SemanticFact instance to serialize.

        Returns:
            Structured text representation of the fact.
        """
        parts = [
            f"Subject: {fact.subject}",
            f"Predicate: {fact.predicate}",
            f"Object: {fact.object}",
            f"Confidence: {fact.confidence}",
            f"Source: {fact.source.value}",
            f"Valid From: {fact.valid_from.isoformat()}",
        ]

        if fact.valid_to:
            parts.append(f"Valid To: {fact.valid_to.isoformat()}")

        if fact.last_confirmed_at:
            parts.append(f"Last Confirmed At: {fact.last_confirmed_at.isoformat()}")

        if fact.corroborating_sources:
            parts.append(f"Corroborating Sources: {','.join(fact.corroborating_sources)}")

        return "\n".join(parts)

    def _parse_edge_to_fact(self, edge: Any, user_id: str) -> SemanticFact | None:
        """Parse a Graphiti edge into a SemanticFact.

        Args:
            edge: The Graphiti edge object.
            user_id: The expected user ID.

        Returns:
            SemanticFact if parsing succeeds, None otherwise.
        """
        try:
            fact = getattr(edge, "fact", "")
            created_at = getattr(edge, "created_at", datetime.now(UTC))
            edge_uuid = getattr(edge, "uuid", None) or str(uuid.uuid4())

            return self._parse_content_to_fact(
                fact_id=edge_uuid,
                content=fact,
                user_id=user_id,
                created_at=created_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse edge to fact: {e}")
            return None

    def _parse_content_to_fact(
        self,
        fact_id: str,
        content: str,
        user_id: str,
        created_at: datetime,
    ) -> SemanticFact | None:
        """Parse fact content string into SemanticFact object.

        Args:
            fact_id: The fact ID.
            content: The raw content string.
            user_id: The user ID.
            created_at: When the fact was created.

        Returns:
            SemanticFact if parsing succeeds, None otherwise.
        """
        try:
            lines = content.split("\n")
            subject = ""
            predicate = ""
            obj = ""
            confidence = 0.5
            source = FactSource.EXTRACTED
            valid_from = created_at
            valid_to = None
            invalidated_at = None
            invalidation_reason = None
            last_confirmed_at = None
            corroborating_sources: list[str] = []

            for line in lines:
                if line.startswith("Subject:"):
                    subject = line.replace("Subject:", "").strip()
                elif line.startswith("Predicate:"):
                    predicate = line.replace("Predicate:", "").strip()
                elif line.startswith("Object:"):
                    obj = line.replace("Object:", "").strip()
                elif line.startswith("Confidence:"):
                    with contextlib.suppress(ValueError):
                        confidence = float(line.replace("Confidence:", "").strip())
                elif line.startswith("Source:"):
                    source_str = line.replace("Source:", "").strip()
                    with contextlib.suppress(ValueError):
                        source = FactSource(source_str)
                elif line.startswith("Valid From:"):
                    with contextlib.suppress(ValueError):
                        valid_from = datetime.fromisoformat(line.replace("Valid From:", "").strip())
                elif line.startswith("Valid To:"):
                    with contextlib.suppress(ValueError):
                        valid_to = datetime.fromisoformat(line.replace("Valid To:", "").strip())
                elif line.startswith("Last Confirmed At:"):
                    with contextlib.suppress(ValueError):
                        last_confirmed_at = datetime.fromisoformat(
                            line.replace("Last Confirmed At:", "").strip()
                        )
                elif line.startswith("Corroborating Sources:"):
                    sources_str = line.replace("Corroborating Sources:", "").strip()
                    if sources_str:
                        corroborating_sources = [
                            s.strip() for s in sources_str.split(",") if s.strip()
                        ]

            if not subject or not predicate or not obj:
                return None

            return SemanticFact(
                id=fact_id,
                user_id=user_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=confidence,
                source=source,
                valid_from=valid_from,
                valid_to=valid_to,
                invalidated_at=invalidated_at,
                invalidation_reason=invalidation_reason,
                last_confirmed_at=last_confirmed_at,
                corroborating_sources=corroborating_sources,
            )
        except Exception as e:
            logger.warning(f"Failed to parse fact content: {e}")
            return None

    async def _check_and_invalidate_contradictions(
        self,
        client: "Graphiti",
        new_fact: SemanticFact,
    ) -> None:
        """Check for and invalidate contradicting facts.

        Args:
            client: The Graphiti client.
            new_fact: The new fact being added.
        """
        try:
            # Search for existing facts about the same subject-predicate
            query = f"facts about {new_fact.subject} {new_fact.predicate}"
            results = await client.search(query)

            for edge in results:
                existing_fact = self._parse_edge_to_fact(edge, new_fact.user_id)
                if (
                    existing_fact
                    and existing_fact.is_valid()
                    and new_fact.contradicts(existing_fact)
                ):
                    logger.info(
                        "Invalidating contradicting fact",
                        extra={
                            "old_fact_id": existing_fact.id,
                            "new_fact_id": new_fact.id,
                        },
                    )
                    # Invalidate by updating in Neo4j
                    await self._invalidate_in_neo4j(
                        client,
                        existing_fact.id,
                        f"superseded by fact:{new_fact.id}",
                    )

        except Exception as e:
            logger.warning(f"Failed to check contradictions: {e}")
            # Continue with adding the fact even if contradiction check fails

    async def _invalidate_in_neo4j(
        self,
        client: "Graphiti",
        fact_id: str,
        reason: str,
    ) -> None:
        """Mark a fact as invalidated in Neo4j.

        Args:
            client: The Graphiti client.
            fact_id: The fact ID to invalidate.
            reason: Reason for invalidation.
        """
        now = datetime.now(UTC)
        query = """
        MATCH (e:Episode)
        WHERE e.name = $fact_name
        SET e.invalidated_at = $invalidated_at,
            e.invalidation_reason = $reason
        RETURN e
        """

        await client.driver.execute_query(
            query,
            fact_name=f"fact:{fact_id}",
            invalidated_at=now.isoformat(),
            reason=reason,
        )

    async def add_fact(self, fact: SemanticFact) -> str:
        """Add a new fact to semantic memory.

        Checks for contradicting facts and invalidates them before
        storing the new fact.

        Args:
            fact: The fact to add.

        Returns:
            The ID of the stored fact.

        Raises:
            SemanticMemoryError: If storage fails.
        """
        try:
            # Generate ID if not provided
            fact_id = fact.id if fact.id else str(uuid.uuid4())

            # Get Graphiti client
            client = await self._get_graphiti_client()

            # Check for contradicting facts and invalidate them
            await self._check_and_invalidate_contradictions(client, fact)

            # Build fact body
            fact_body = self._build_fact_body(fact)

            # Store in Graphiti
            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=f"fact:{fact_id}",
                episode_body=fact_body,
                source=EpisodeType.text,
                source_description=f"semantic_memory:{fact.user_id}:{fact.predicate}",
                reference_time=fact.valid_from,
            )

            logger.info(
                "Stored fact",
                extra={
                    "fact_id": fact_id,
                    "user_id": fact.user_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                },
            )

            return fact_id

        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to store fact", extra={"fact_id": fact.id})
            raise SemanticMemoryError(f"Failed to store fact: {e}") from e

    async def get_fact(self, user_id: str, fact_id: str) -> SemanticFact:
        """Retrieve a specific fact by ID.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID.

        Returns:
            The requested SemanticFact.

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Query for specific fact by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $fact_name
            RETURN e
            """

            fact_name = f"fact:{fact_id}"

            result = await client.driver.execute_query(
                query,
                fact_name=fact_name,
            )

            records = result[0] if result else []

            if not records:
                raise FactNotFoundError(fact_id)

            # Parse the node into a SemanticFact
            node = records[0]["e"]
            content = getattr(node, "content", "") or node.get("content", "")
            created_at = getattr(node, "created_at", None) or node.get("created_at")
            invalidated_at_str = getattr(node, "invalidated_at", None) or node.get("invalidated_at")
            invalidation_reason = getattr(node, "invalidation_reason", None) or node.get(
                "invalidation_reason"
            )

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            elif created_at is None:
                created_at = datetime.now(UTC)

            fact = self._parse_content_to_fact(
                fact_id=fact_id,
                content=content,
                user_id=user_id,
                created_at=created_at,
            )

            if fact is None:
                raise FactNotFoundError(fact_id)

            # Add invalidation info if present
            if invalidated_at_str:
                fact.invalidated_at = (
                    datetime.fromisoformat(invalidated_at_str)
                    if isinstance(invalidated_at_str, str)
                    else invalidated_at_str
                )
                fact.invalidation_reason = invalidation_reason

            return fact

        except FactNotFoundError:
            raise
        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get fact", extra={"fact_id": fact_id})
            raise SemanticMemoryError(f"Failed to get fact: {e}") from e

    async def get_facts_about(
        self,
        user_id: str,
        subject: str,
        as_of: datetime | None = None,
        include_invalidated: bool = False,
    ) -> list[SemanticFact]:
        """Get all facts about a specific subject.

        Args:
            user_id: The user whose facts to query.
            subject: The entity to get facts about.
            as_of: Point in time to check validity. Defaults to now.
            include_invalidated: Whether to include invalidated facts.

        Returns:
            List of facts about the subject.

        Raises:
            SemanticMemoryError: If query fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Build query for facts about the subject
            query = f"facts about {subject} for user {user_id}"

            results = await client.search(query)

            # Parse results and filter
            check_time = as_of or datetime.now(UTC)
            facts = []

            for edge in results:
                fact = self._parse_edge_to_fact(edge, user_id)
                if fact is None:
                    continue

                # Check subject matches (case-insensitive)
                if subject.lower() not in fact.subject.lower():
                    continue

                # Filter by validity unless including invalidated
                if not include_invalidated and not fact.is_valid(as_of=check_time):
                    continue

                facts.append(fact)

            return facts

        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get facts about subject", extra={"subject": subject})
            raise SemanticMemoryError(f"Failed to get facts: {e}") from e

    async def search_facts(
        self,
        user_id: str,
        query: str,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[SemanticFact]:
        """Search facts using semantic similarity.

        Args:
            user_id: The user whose facts to search.
            query: Natural language search query.
            min_confidence: Minimum confidence threshold.
            limit: Maximum number of facts to return.

        Returns:
            List of relevant facts, ordered by relevance.

        Raises:
            SemanticMemoryError: If search fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Build semantic query with user context
            search_query = f"{query} (user: {user_id})"

            results = await client.search(search_query)

            # Parse results and filter by confidence
            facts = []
            for edge in results[: limit * 2]:  # Get extra to account for filtering
                fact = self._parse_edge_to_fact(edge, user_id)
                if fact is None:
                    continue

                # Filter by minimum confidence
                if fact.confidence < min_confidence:
                    continue

                # Only include valid facts
                if not fact.is_valid():
                    continue

                facts.append(fact)

                if len(facts) >= limit:
                    break

            return facts

        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to search facts", extra={"query": query})
            raise SemanticMemoryError(f"Failed to search facts: {e}") from e

    async def invalidate_fact(
        self,
        user_id: str,
        fact_id: str,
        reason: str,
    ) -> None:
        """Invalidate a fact (soft delete).

        Preserves history by marking the fact as invalidated rather
        than deleting it.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to invalidate.
            reason: Reason for invalidation.

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If invalidation fails.
        """
        try:
            client = await self._get_graphiti_client()

            now = datetime.now(UTC)
            query = """
            MATCH (e:Episode)
            WHERE e.name = $fact_name
            SET e.invalidated_at = $invalidated_at,
                e.invalidation_reason = $reason
            RETURN count(e) as updated
            """

            fact_name = f"fact:{fact_id}"

            result = await client.driver.execute_query(
                query,
                fact_name=fact_name,
                invalidated_at=now.isoformat(),
                reason=reason,
            )

            records = result[0] if result else []
            updated_count = records[0]["updated"] if records else 0

            if updated_count == 0:
                raise FactNotFoundError(fact_id)

            logger.info(
                "Invalidated fact",
                extra={"fact_id": fact_id, "user_id": user_id, "reason": reason},
            )

        except FactNotFoundError:
            raise
        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to invalidate fact", extra={"fact_id": fact_id})
            raise SemanticMemoryError(f"Failed to invalidate fact: {e}") from e

    async def delete_fact(self, user_id: str, fact_id: str) -> None:
        """Permanently delete a fact.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to delete.

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If deletion fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Delete fact node by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $fact_name
            DETACH DELETE e
            RETURN count(e) as deleted
            """

            fact_name = f"fact:{fact_id}"

            result = await client.driver.execute_query(
                query,
                fact_name=fact_name,
            )

            records = result[0] if result else []
            deleted_count = records[0]["deleted"] if records else 0

            if deleted_count == 0:
                raise FactNotFoundError(fact_id)

            logger.info(
                "Deleted fact",
                extra={"fact_id": fact_id, "user_id": user_id},
            )

        except FactNotFoundError:
            raise
        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to delete fact", extra={"fact_id": fact_id})
            raise SemanticMemoryError(f"Failed to delete fact: {e}") from e

    async def confirm_fact(
        self,
        user_id: str,
        fact_id: str,
        confirming_source: str,
    ) -> None:
        """Confirm a fact, updating last_confirmed_at and adding corroboration.

        This method is used when an external source corroborates an existing fact.
        It refreshes the decay clock and adds the source to corroborating_sources.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to confirm.
            confirming_source: Identifier for the confirming source (e.g., "crm_import:123").

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If confirmation fails.
        """
        try:
            # Get existing fact
            fact = await self.get_fact(user_id, fact_id)

            # Update confirmation timestamp
            fact.last_confirmed_at = datetime.now(UTC)

            # Add corroborating source if not already present
            if fact.corroborating_sources is None:
                fact.corroborating_sources = []
            if confirming_source not in fact.corroborating_sources:
                fact.corroborating_sources.append(confirming_source)

            # Re-store the updated fact
            client = await self._get_graphiti_client()

            # Delete old version
            await self._delete_episode(client, fact_id)

            # Store updated version
            fact_body = self._build_fact_body(fact)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=f"fact:{fact_id}",
                episode_body=fact_body,
                source=EpisodeType.text,
                source_description=f"semantic_memory:{user_id}:{fact.predicate}:confirmed",
                reference_time=fact.valid_from,
            )

            logger.info(
                "Confirmed fact",
                extra={
                    "fact_id": fact_id,
                    "user_id": user_id,
                    "confirming_source": confirming_source,
                },
            )

        except FactNotFoundError:
            raise
        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to confirm fact", extra={"fact_id": fact_id})
            raise SemanticMemoryError(f"Failed to confirm fact: {e}") from e

    async def _delete_episode(self, client: "Graphiti", fact_id: str) -> None:
        """Delete an episode by fact ID (helper for updates).

        Args:
            client: The Graphiti client.
            fact_id: The fact ID to delete.
        """
        query = """
        MATCH (e:Episode)
        WHERE e.name = $fact_name
        DETACH DELETE e
        """
        await client.driver.execute_query(
            query,
            fact_name=f"fact:{fact_id}",
        )

    def get_effective_confidence(
        self,
        fact: SemanticFact,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate the effective confidence for a fact.

        Applies time-based decay and corroboration boosts to get the
        current confidence value for the fact.

        Args:
            fact: The SemanticFact to calculate confidence for.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Effective confidence score between 0.3 and 0.99.
        """
        scorer = ConfidenceScorer()
        return scorer.get_effective_confidence(
            original_confidence=fact.confidence,
            created_at=fact.valid_from,
            last_confirmed_at=fact.last_confirmed_at,
            corroborating_source_count=len(fact.corroborating_sources or []),
            as_of=as_of,
        )
