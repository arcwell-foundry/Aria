"""Corporate memory module for company-level shared knowledge.

Corporate memory stores facts that are shared across all users within
a company. Key features:
- Privacy: No user-identifiable data stored
- Multi-tenant: Graphiti namespace separation by company_id
- Access control: Users can read, admins can write
- Source tracking: extracted, aggregated, or admin_stated
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from src.core.exceptions import (
    CorporateFactNotFoundError,
    CorporateMemoryError,
)
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class CorporateFactSource(Enum):
    """Source of a corporate fact."""

    EXTRACTED = "extracted"  # Extracted from user data (anonymized)
    AGGREGATED = "aggregated"  # Aggregated from cross-user patterns
    ADMIN_STATED = "admin_stated"  # Manually entered by admin


# Base confidence by source type for corporate facts
CORPORATE_SOURCE_CONFIDENCE: dict[CorporateFactSource, float] = {
    CorporateFactSource.ADMIN_STATED: 0.95,
    CorporateFactSource.AGGREGATED: 0.80,
    CorporateFactSource.EXTRACTED: 0.70,
}


@dataclass
class CorporateFact:
    """A company-level fact shared across all users.

    Uses subject-predicate-object triple structure.
    Does NOT contain any user-identifiable information.
    """

    id: str
    company_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source: CorporateFactSource
    is_active: bool
    created_at: datetime
    updated_at: datetime
    graphiti_episode_name: str | None = None
    created_by: str | None = None  # User ID of admin who created (null = system)
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize fact to dictionary for database storage.

        Returns:
            Dictionary suitable for Supabase insertion.
        """
        return {
            "id": self.id,
            "company_id": self.company_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source.value,
            "is_active": self.is_active,
            "graphiti_episode_name": self.graphiti_episode_name,
            "created_by": self.created_by,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
            "invalidation_reason": self.invalidation_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CorporateFact":
        """Create a CorporateFact from a dictionary.

        Args:
            data: Dictionary from database query.

        Returns:
            CorporateFact instance.
        """
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            confidence=data["confidence"],
            source=CorporateFactSource(data["source"]),
            is_active=data["is_active"],
            graphiti_episode_name=data.get("graphiti_episode_name"),
            created_by=data.get("created_by"),
            invalidated_at=datetime.fromisoformat(data["invalidated_at"])
            if data.get("invalidated_at")
            else None,
            invalidation_reason=data.get("invalidation_reason"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class CorporateMemory:
    """Service for managing company-level shared facts.

    Provides methods for CRUD operations on corporate facts,
    with storage in both Supabase (metadata) and Graphiti (semantic content).
    Uses company-prefixed namespace in Graphiti for multi-tenant isolation.
    """

    def _get_graphiti_episode_name(self, company_id: str, fact_id: str) -> str:
        """Generate namespaced episode name for Graphiti.

        Args:
            company_id: The company's UUID.
            fact_id: The fact's UUID.

        Returns:
            Namespaced episode name (e.g., "corp:company-123:fact-456").
        """
        return f"corp:{company_id}:{fact_id}"

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            CorporateMemoryError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise CorporateMemoryError(f"Failed to get Graphiti client: {e}") from e

    def _build_fact_body(self, fact: CorporateFact) -> str:
        """Build structured fact body for Graphiti storage.

        Args:
            fact: The CorporateFact to serialize.

        Returns:
            Structured text representation (no user-identifiable data).
        """
        parts = [
            f"Company: {fact.company_id}",
            f"Subject: {fact.subject}",
            f"Predicate: {fact.predicate}",
            f"Object: {fact.object}",
            f"Confidence: {fact.confidence}",
            f"Source: {fact.source.value}",
        ]
        return "\n".join(parts)

    async def add_fact(
        self,
        fact: CorporateFact,
        store_in_graphiti: bool = True,
    ) -> str:
        """Add a new corporate fact.

        Stores metadata in Supabase and semantic content in Graphiti.

        Args:
            fact: The corporate fact to add.
            store_in_graphiti: Whether to also store in Graphiti for search.

        Returns:
            The ID of the created fact.

        Raises:
            CorporateMemoryError: If storage fails.
        """
        try:
            fact_id = fact.id if fact.id else str(uuid.uuid4())

            # Generate Graphiti episode name
            episode_name = self._get_graphiti_episode_name(fact.company_id, fact_id)

            # Store in Graphiti first (if enabled)
            if store_in_graphiti:
                client = await self._get_graphiti_client()
                fact_body = self._build_fact_body(fact)

                from graphiti_core.nodes import EpisodeType

                await client.add_episode(
                    name=episode_name,
                    episode_body=fact_body,
                    source=EpisodeType.text,
                    source_description=f"corporate_memory:{fact.company_id}:{fact.predicate}",
                    reference_time=fact.created_at,
                )

            # Store metadata in Supabase
            supabase = SupabaseClient.get_client()
            insert_data = fact.to_dict()
            insert_data["id"] = fact_id
            insert_data["graphiti_episode_name"] = episode_name if store_in_graphiti else None

            response = supabase.table("corporate_facts").insert(insert_data).execute()

            if not response.data or len(response.data) == 0:
                raise CorporateMemoryError("No data returned from insert")

            logger.info(
                "Stored corporate fact",
                extra={
                    "fact_id": fact_id,
                    "company_id": fact.company_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                },
            )

            # Audit log (use company_id as user_id for corporate operations)
            await log_memory_operation(
                user_id=fact.created_by or fact.company_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.SEMANTIC,  # Closest existing type
                memory_id=fact_id,
                metadata={
                    "corporate": True,
                    "company_id": fact.company_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                },
                suppress_errors=True,
            )

            return fact_id

        except CorporateMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to store corporate fact")
            raise CorporateMemoryError(f"Failed to store fact: {e}") from e

    async def get_fact(self, company_id: str, fact_id: str) -> CorporateFact:
        """Retrieve a specific corporate fact by ID.

        Args:
            company_id: The company's UUID (for access control).
            fact_id: The fact's UUID.

        Returns:
            The requested CorporateFact.

        Raises:
            CorporateFactNotFoundError: If fact doesn't exist.
            CorporateMemoryError: If retrieval fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("corporate_facts")
                .select("*")
                .eq("id", fact_id)
                .eq("company_id", company_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise CorporateFactNotFoundError(fact_id)

            return CorporateFact.from_dict(cast(dict[str, Any], response.data))

        except CorporateFactNotFoundError:
            raise
        except CorporateMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get corporate fact", extra={"fact_id": fact_id})
            raise CorporateMemoryError(f"Failed to get fact: {e}") from e

    async def get_facts_for_company(
        self,
        company_id: str,
        subject: str | None = None,
        predicate: str | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[CorporateFact]:
        """Get corporate facts for a company.

        Args:
            company_id: The company's UUID.
            subject: Optional filter by subject entity.
            predicate: Optional filter by predicate type.
            active_only: Whether to exclude invalidated facts.
            limit: Maximum number of facts to return.

        Returns:
            List of matching corporate facts.

        Raises:
            CorporateMemoryError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            query = client.table("corporate_facts").select("*").eq("company_id", company_id)

            if active_only:
                query = query.eq("is_active", True)

            if subject:
                query = query.ilike("subject", f"%{subject}%")

            if predicate:
                query = query.eq("predicate", predicate)

            response = query.order("created_at", desc=True).limit(limit).execute()

            data = cast(list[dict[str, Any]], response.data or [])
            return [CorporateFact.from_dict(row) for row in data]

        except Exception as e:
            logger.exception(
                "Failed to get corporate facts",
                extra={"company_id": company_id},
            )
            raise CorporateMemoryError(f"Failed to get facts: {e}") from e

    async def search_facts(
        self,
        company_id: str,
        query: str,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[CorporateFact]:
        """Search corporate facts using Graphiti semantic search.

        Args:
            company_id: The company's UUID.
            query: Natural language search query.
            min_confidence: Minimum confidence threshold.
            limit: Maximum number of facts to return.

        Returns:
            List of relevant corporate facts.

        Raises:
            CorporateMemoryError: If search fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search with company namespace prefix
            search_query = f"company:{company_id} {query}"
            results = await client.search(search_query)

            # Get fact IDs from Graphiti results
            fact_ids: list[str] = []
            for edge in results[:limit]:
                fact = getattr(edge, "fact", "")
                # Parse company ID from fact content to verify namespace
                if f"Company: {company_id}" in fact:
                    episode_name = getattr(edge, "name", "") or ""
                    if episode_name.startswith(f"corp:{company_id}:"):
                        fact_id = episode_name.replace(f"corp:{company_id}:", "")
                        fact_ids.append(fact_id)

            if not fact_ids:
                return []

            # Fetch full facts from Supabase
            supabase = SupabaseClient.get_client()
            response = (
                supabase.table("corporate_facts")
                .select("*")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .in_("id", fact_ids)
                .gte("confidence", min_confidence)
                .limit(limit)
                .execute()
            )

            data = cast(list[dict[str, Any]], response.data or [])
            return [CorporateFact.from_dict(row) for row in data]

        except CorporateMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to search corporate facts")
            raise CorporateMemoryError(f"Failed to search facts: {e}") from e

    async def invalidate_fact(
        self,
        company_id: str,
        fact_id: str,
        reason: str,
        invalidated_by: str | None = None,
    ) -> None:
        """Invalidate a corporate fact (soft delete).

        Args:
            company_id: The company's UUID.
            fact_id: The fact's UUID.
            reason: Reason for invalidation.
            invalidated_by: User ID of admin who invalidated (optional).

        Raises:
            CorporateFactNotFoundError: If fact doesn't exist.
            CorporateMemoryError: If invalidation fails.
        """
        try:
            now = datetime.now(UTC)
            client = SupabaseClient.get_client()

            response = (
                client.table("corporate_facts")
                .update(
                    {
                        "is_active": False,
                        "invalidated_at": now.isoformat(),
                        "invalidation_reason": reason,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", fact_id)
                .eq("company_id", company_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise CorporateFactNotFoundError(fact_id)

            logger.info(
                "Invalidated corporate fact",
                extra={
                    "fact_id": fact_id,
                    "company_id": company_id,
                    "reason": reason,
                },
            )

            # Audit log
            await log_memory_operation(
                user_id=invalidated_by or company_id,
                operation=MemoryOperation.INVALIDATE,
                memory_type=MemoryType.SEMANTIC,
                memory_id=fact_id,
                metadata={
                    "corporate": True,
                    "company_id": company_id,
                    "reason": reason,
                },
                suppress_errors=True,
            )

        except CorporateFactNotFoundError:
            raise
        except CorporateMemoryError:
            raise
        except Exception as e:
            logger.exception(
                "Failed to invalidate corporate fact",
                extra={"fact_id": fact_id},
            )
            raise CorporateMemoryError(f"Failed to invalidate fact: {e}") from e

    async def delete_fact(self, company_id: str, fact_id: str) -> None:
        """Permanently delete a corporate fact.

        Removes from both Supabase and Graphiti.

        Args:
            company_id: The company's UUID.
            fact_id: The fact's UUID.

        Raises:
            CorporateFactNotFoundError: If fact doesn't exist.
            CorporateMemoryError: If deletion fails.
        """
        try:
            # Get fact to get Graphiti episode name
            fact = await self.get_fact(company_id, fact_id)

            # Delete from Graphiti if stored there
            if fact.graphiti_episode_name:
                client = await self._get_graphiti_client()
                query = """
                MATCH (e:Episode)
                WHERE e.name = $episode_name
                DETACH DELETE e
                """
                await client.driver.execute_query(
                    query,
                    episode_name=fact.graphiti_episode_name,
                )

            # Delete from Supabase
            supabase = SupabaseClient.get_client()
            response = (
                supabase.table("corporate_facts")
                .delete()
                .eq("id", fact_id)
                .eq("company_id", company_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise CorporateFactNotFoundError(fact_id)

            logger.info(
                "Deleted corporate fact",
                extra={"fact_id": fact_id, "company_id": company_id},
            )

            # Audit log
            await log_memory_operation(
                user_id=company_id,
                operation=MemoryOperation.DELETE,
                memory_type=MemoryType.SEMANTIC,
                memory_id=fact_id,
                metadata={"corporate": True, "company_id": company_id},
                suppress_errors=True,
            )

        except CorporateFactNotFoundError:
            raise
        except CorporateMemoryError:
            raise
        except Exception as e:
            logger.exception(
                "Failed to delete corporate fact",
                extra={"fact_id": fact_id},
            )
            raise CorporateMemoryError(f"Failed to delete fact: {e}") from e
