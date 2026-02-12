"""Semantic memory module for storing facts and knowledge.

Semantic memory stores factual knowledge with:
- Subject-predicate-object triple structure
- Confidence scores (0.0-1.0) based on source reliability
- Temporal validity windows (valid_from, valid_to)
- Source tracking for provenance
- Soft invalidation for history preservation
- Contradiction detection

Facts are stored in Graphiti (Neo4j) for semantic search and
temporal querying capabilities, with Supabase as a durable fallback.
"""

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import FactNotFoundError, SemanticMemoryError  # noqa: F401
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
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
    """Service for storing and querying semantic facts.

    Provides async methods for CRUD operations, contradiction detection,
    and various query patterns on factual knowledge. Uses Graphiti (Neo4j)
    for semantic search with Supabase as a durable fallback.
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

    # ── Supabase fallback helpers ────────────────────────────────

    def _store_to_supabase(self, fact: SemanticFact) -> str:
        """Store a fact to the Supabase memory_semantic table.

        This is the durable write path: every fact is persisted here
        regardless of whether Graphiti succeeds.

        Args:
            fact: The SemanticFact instance to store.

        Returns:
            The fact ID.
        """
        from src.db.supabase import SupabaseClient

        row = {
            "id": fact.id,
            "user_id": fact.user_id,
            "fact": f"{fact.subject} {fact.predicate} {fact.object}",
            "confidence": fact.confidence,
            "source": fact.source.value,
            "metadata": json.dumps(fact.to_dict()),
            "created_at": fact.valid_from.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        SupabaseClient.get_client().table("memory_semantic").upsert(row).execute()
        return fact.id

    def _query_from_supabase(
        self,
        user_id: str,
        query_text: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[SemanticFact]:
        """Query facts from the Supabase memory_semantic table.

        Used as a fallback when Graphiti is unavailable.

        Args:
            user_id: The user ID to filter by.
            query_text: Optional text to search in the fact column.
            min_confidence: Minimum confidence threshold (0.0 means no filter).
            limit: Maximum rows to return.

        Returns:
            List of SemanticFact instances parsed from Supabase rows.
        """
        from src.db.supabase import SupabaseClient

        query = (
            SupabaseClient.get_client().table("memory_semantic").select("*").eq("user_id", user_id)
        )

        if query_text:
            query = query.ilike("fact", f"%{query_text}%")
        if min_confidence > 0:
            query = query.gte("confidence", min_confidence)

        query = query.order("created_at", desc=True).limit(limit)
        response = query.execute()

        facts: list[SemanticFact] = []
        for row in response.data or []:
            fact = self._parse_supabase_row(row)
            if fact:
                facts.append(fact)
        return facts

    def _parse_supabase_row(self, row: dict[str, Any]) -> SemanticFact | None:
        """Parse a Supabase row into a SemanticFact.

        Prefers the full metadata JSONB blob when available, falling
        back to top-level columns.

        Args:
            row: A dictionary representing a row from memory_semantic.

        Returns:
            SemanticFact if parsing succeeds, None otherwise.
        """
        try:
            metadata_raw = row.get("metadata")
            if metadata_raw:
                if isinstance(metadata_raw, str):
                    metadata = json.loads(metadata_raw)
                else:
                    metadata = metadata_raw
                # metadata should contain the full fact dict
                if "id" in metadata and "user_id" in metadata and "subject" in metadata:
                    return SemanticFact.from_dict(metadata)

            # Fallback: reconstruct from top-level columns
            created_at_str = row.get("created_at", "")
            created_at = (
                datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(UTC)
            )

            # The fact column stores "subject predicate object" as a single string
            fact_str = row.get("fact", "")
            parts = fact_str.split(" ", 2)
            subject = parts[0] if len(parts) > 0 else ""
            predicate = parts[1] if len(parts) > 1 else ""
            obj = parts[2] if len(parts) > 2 else ""

            source_str = row.get("source", "extracted")
            try:
                source = FactSource(source_str)
            except ValueError:
                source = FactSource.EXTRACTED

            return SemanticFact(
                id=row["id"],
                user_id=row["user_id"],
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=row.get("confidence", 0.5),
                source=source,
                valid_from=created_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Supabase row to fact: {e}")
            return None

    # ── Public API ───────────────────────────────────────────────

    async def add_fact(self, fact: SemanticFact) -> str:
        """Add a new fact to semantic memory.

        Always writes to Supabase first (durable), then attempts
        Graphiti for semantic search and contradiction detection.
        If Graphiti fails the fact is still safely persisted in Supabase.

        Args:
            fact: The fact to add.

        Returns:
            The ID of the stored fact.

        Raises:
            SemanticMemoryError: If Supabase storage fails.
        """
        try:
            # Generate ID if not provided
            fact_id = fact.id if fact.id else str(uuid.uuid4())
            fact.id = fact_id

            # ── Step 1: Always store to Supabase (durable) ──
            supabase_ok = False
            try:
                self._store_to_supabase(fact)
                supabase_ok = True
            except Exception as sb_err:
                logger.warning(
                    "Supabase store failed, will try Graphiti",
                    extra={"fact_id": fact_id, "error": str(sb_err)},
                )

            # ── Step 2: Try to also store in Graphiti ──
            graphiti_ok = False
            try:
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
                graphiti_ok = True
            except Exception as graphiti_err:
                logger.warning(
                    "Graphiti store failed for fact",
                    extra={
                        "fact_id": fact_id,
                        "user_id": fact.user_id,
                        "error": str(graphiti_err),
                    },
                )

            if not supabase_ok and not graphiti_ok:
                raise SemanticMemoryError(
                    f"Failed to store fact {fact_id}: both Supabase and Graphiti failed"
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

            # Audit log the creation
            await log_memory_operation(
                user_id=fact.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.SEMANTIC,
                memory_id=fact_id,
                metadata={"subject": fact.subject, "predicate": fact.predicate},
                suppress_errors=True,
            )

            return fact_id

        except SemanticMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to store fact", extra={"fact_id": fact.id})
            raise SemanticMemoryError(f"Failed to store fact: {e}") from e

    async def get_fact(self, user_id: str, fact_id: str) -> SemanticFact:
        """Retrieve a specific fact by ID.

        Tries Graphiti first for richer data, falls back to Supabase
        if Graphiti is unavailable.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID.

        Returns:
            The requested SemanticFact.

        Raises:
            FactNotFoundError: If fact doesn't exist in either store.
            SemanticMemoryError: If retrieval fails.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()

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

            if records:
                node = records[0]["e"]
                content = getattr(node, "content", "") or node.get("content", "")
                created_at = getattr(node, "created_at", None) or node.get("created_at")
                invalidated_at_str = getattr(node, "invalidated_at", None) or node.get(
                    "invalidated_at"
                )
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

                if fact is not None:
                    # Add invalidation info if present
                    if invalidated_at_str:
                        fact.invalidated_at = (
                            datetime.fromisoformat(invalidated_at_str)
                            if isinstance(invalidated_at_str, str)
                            else invalidated_at_str
                        )
                        fact.invalidation_reason = invalidation_reason
                    return fact

        except Exception as graphiti_err:
            logger.warning(
                "Graphiti get_fact failed, falling back to Supabase",
                extra={"fact_id": fact_id, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            from src.db.supabase import SupabaseClient

            response = (
                SupabaseClient.get_client()
                .table("memory_semantic")
                .select("*")
                .eq("id", fact_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            if response.data:
                fact = self._parse_supabase_row(response.data[0])
                if fact is not None:
                    return fact
        except Exception as sb_err:
            logger.warning(
                "Supabase get_fact also failed",
                extra={"fact_id": fact_id, "error": str(sb_err)},
            )

        raise FactNotFoundError(fact_id)

    async def get_facts_about(
        self,
        user_id: str,
        subject: str,
        as_of: datetime | None = None,
        include_invalidated: bool = False,
    ) -> list[SemanticFact]:
        """Get all facts about a specific subject.

        Tries Graphiti first for semantic search, falls back to
        Supabase text search on the fact column.

        Args:
            user_id: The user whose facts to query.
            subject: The entity to get facts about.
            as_of: Point in time to check validity. Defaults to now.
            include_invalidated: Whether to include invalidated facts.

        Returns:
            List of facts about the subject.

        Raises:
            SemanticMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()

            query = f"facts about {subject} for user {user_id}"
            results = await client.search(query)

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
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti get_facts_about failed, falling back to Supabase",
                extra={"user_id": user_id, "subject": subject, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            all_facts = self._query_from_supabase(user_id, query_text=subject)
            check_time = as_of or datetime.now(UTC)
            filtered: list[SemanticFact] = []
            for fact in all_facts:
                if subject.lower() not in fact.subject.lower():
                    continue
                if not include_invalidated and not fact.is_valid(as_of=check_time):
                    continue
                filtered.append(fact)
            return filtered
        except Exception as e:
            logger.exception("Supabase fallback also failed for get_facts_about")
            raise SemanticMemoryError(f"Failed to get facts: {e}") from e

    async def search_facts(
        self,
        user_id: str,
        query: str,
        min_confidence: float = 0.5,
        limit: int = 20,
        as_of: datetime | None = None,
    ) -> list[SemanticFact]:
        """Search facts using semantic similarity.

        Tries Graphiti first for true semantic search, falls back to
        Supabase text search with confidence filtering.

        Args:
            user_id: The user whose facts to search.
            query: Natural language search query.
            min_confidence: Minimum confidence threshold.
            limit: Maximum number of facts to return.
            as_of: Point in time to check validity. Defaults to now.

        Returns:
            List of relevant facts, ordered by relevance.

        Raises:
            SemanticMemoryError: If both stores fail.
        """
        # ── Try Graphiti first ──
        try:
            client = await self._get_graphiti_client()

            search_query = f"{query} (user: {user_id})"
            results = await client.search(search_query)

            facts = []
            for edge in results[: limit * 2]:  # Get extra to account for filtering
                fact = self._parse_edge_to_fact(edge, user_id)
                if fact is None:
                    continue

                if fact.confidence < min_confidence:
                    continue

                if not fact.is_valid(as_of=as_of):
                    continue

                facts.append(fact)

                if len(facts) >= limit:
                    break

            return facts
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti search_facts failed, falling back to Supabase",
                extra={"user_id": user_id, "query": query, "error": str(graphiti_err)},
            )

        # ── Fall back to Supabase ──
        try:
            all_facts = self._query_from_supabase(
                user_id,
                query_text=query,
                min_confidence=min_confidence,
                limit=limit * 2,
            )
            valid_facts: list[SemanticFact] = []
            for fact in all_facts:
                if not fact.is_valid(as_of=as_of):
                    continue
                valid_facts.append(fact)
                if len(valid_facts) >= limit:
                    break
            return valid_facts
        except Exception as e:
            logger.exception("Supabase fallback also failed for search_facts")
            raise SemanticMemoryError(f"Failed to search facts: {e}") from e

    async def invalidate_fact(
        self,
        user_id: str,
        fact_id: str,
        reason: str,
    ) -> None:
        """Invalidate a fact (soft delete).

        Always updates Supabase, then attempts Graphiti. Preserves
        history by marking the fact as invalidated rather than deleting it.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to invalidate.
            reason: Reason for invalidation.

        Raises:
            FactNotFoundError: If fact doesn't exist in either store.
            SemanticMemoryError: If invalidation fails.
        """
        supabase_updated = False
        graphiti_updated = False
        now = datetime.now(UTC)

        # ── Always update Supabase ──
        try:
            from src.db.supabase import SupabaseClient

            # Read existing row to get current metadata
            read_resp = (
                SupabaseClient.get_client()
                .table("memory_semantic")
                .select("metadata")
                .eq("id", fact_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )

            if read_resp.data:
                metadata_raw = read_resp.data[0].get("metadata")
                if metadata_raw:
                    metadata = (
                        json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                    )
                else:
                    metadata = {}
                metadata["invalidated_at"] = now.isoformat()
                metadata["invalidation_reason"] = reason

                SupabaseClient.get_client().table("memory_semantic").update(
                    {
                        "metadata": json.dumps(metadata),
                        "updated_at": now.isoformat(),
                    }
                ).eq("id", fact_id).eq("user_id", user_id).execute()
                supabase_updated = True
        except Exception as sb_err:
            logger.warning(
                "Supabase invalidate_fact failed",
                extra={"fact_id": fact_id, "error": str(sb_err)},
            )

        # ── Try Graphiti too ──
        try:
            client = await self._get_graphiti_client()

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
            if updated_count > 0:
                graphiti_updated = True
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti invalidate_fact failed",
                extra={"fact_id": fact_id, "error": str(graphiti_err)},
            )

        if not supabase_updated and not graphiti_updated:
            raise FactNotFoundError(fact_id)

        logger.info(
            "Invalidated fact",
            extra={"fact_id": fact_id, "user_id": user_id, "reason": reason},
        )

        # Audit log the invalidation
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.INVALIDATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=fact_id,
            metadata={"reason": reason},
            suppress_errors=True,
        )

    async def delete_fact(self, user_id: str, fact_id: str) -> None:
        """Permanently delete a fact from both stores.

        Always deletes from Supabase. Also attempts Graphiti deletion;
        a Graphiti failure is logged but does not raise.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to delete.

        Raises:
            FactNotFoundError: If fact doesn't exist in either store.
            SemanticMemoryError: If deletion fails.
        """
        supabase_deleted = False
        graphiti_deleted = False

        # ── Always delete from Supabase ──
        try:
            from src.db.supabase import SupabaseClient

            response = (
                SupabaseClient.get_client()
                .table("memory_semantic")
                .delete()
                .eq("id", fact_id)
                .eq("user_id", user_id)
                .execute()
            )
            if response.data:
                supabase_deleted = True
        except Exception as sb_err:
            logger.warning(
                "Supabase delete_fact failed",
                extra={"fact_id": fact_id, "error": str(sb_err)},
            )

        # ── Try to delete from Graphiti too ──
        try:
            client = await self._get_graphiti_client()

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
            if deleted_count > 0:
                graphiti_deleted = True
        except Exception as graphiti_err:
            logger.warning(
                "Graphiti delete_fact failed",
                extra={"fact_id": fact_id, "error": str(graphiti_err)},
            )

        if not supabase_deleted and not graphiti_deleted:
            raise FactNotFoundError(fact_id)

        logger.info(
            "Deleted fact",
            extra={"fact_id": fact_id, "user_id": user_id},
        )

        # Audit log the deletion
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.DELETE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=fact_id,
            suppress_errors=True,
        )

    async def confirm_fact(
        self,
        user_id: str,
        fact_id: str,
        confirming_source: str,
    ) -> None:
        """Confirm a fact, updating last_confirmed_at and adding corroboration.

        Always updates Supabase, then attempts Graphiti. This method is used
        when an external source corroborates an existing fact. It refreshes
        the decay clock and adds the source to corroborating_sources.

        Args:
            user_id: The user who owns the fact.
            fact_id: The fact ID to confirm.
            confirming_source: Identifier for the confirming source (e.g., "crm_import:123").

        Raises:
            FactNotFoundError: If fact doesn't exist.
            SemanticMemoryError: If confirmation fails.
        """
        try:
            # Get existing fact (uses Graphiti-first with Supabase fallback)
            fact = await self.get_fact(user_id, fact_id)

            # Update confirmation timestamp
            fact.last_confirmed_at = datetime.now(UTC)

            # Add corroborating source if not already present
            if fact.corroborating_sources is None:
                fact.corroborating_sources = []
            if confirming_source not in fact.corroborating_sources:
                fact.corroborating_sources.append(confirming_source)

            # ── Try to update Supabase ──
            try:
                self._store_to_supabase(fact)
            except Exception as sb_err:
                logger.warning(
                    "Supabase confirm_fact failed, will try Graphiti",
                    extra={"fact_id": fact_id, "error": str(sb_err)},
                )

            # ── Try to re-store in Graphiti too ──
            try:
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
            except Exception as graphiti_err:
                logger.warning(
                    "Graphiti confirm_fact failed, Supabase updated",
                    extra={"fact_id": fact_id, "error": str(graphiti_err)},
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
