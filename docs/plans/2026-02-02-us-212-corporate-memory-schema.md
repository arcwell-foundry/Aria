# US-212: Corporate Memory Schema Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement company-level memory storage that enables organizational knowledge sharing across users while maintaining privacy.

**Architecture:** Corporate memory extends the existing SemanticMemory pattern with a new `corporate.py` module. Company-level facts use a separate `company_id` scope instead of `user_id`. Privacy is ensured by stripping user-identifiable information before storing corporate facts. Supabase stores corporate facts metadata with company-based RLS, while Graphiti stores the semantic content with company namespace prefixes.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (PostgreSQL), Graphiti (Neo4j), Pydantic

---

## Acceptance Criteria Reference (from PHASE_2_MEMORY.md)

- [ ] Company-level facts stored separately from user facts
- [ ] Community patterns extracted from cross-user data
- [ ] Privacy: no user-identifiable data in corporate memory
- [ ] Access control: users can read company facts
- [ ] Admin can manage corporate facts
- [ ] Graphiti namespace separation for multi-tenant
- [ ] Unit tests for isolation

---

## Task 1: Create CorporateMemoryError Exception

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/core/exceptions.py`
- Test: `/Users/dhruv/aria/backend/tests/test_exceptions.py`

**Step 1.1: Write the failing test**

Add to `backend/tests/test_exceptions.py`:

```python
def test_corporate_memory_error() -> None:
    """Test CorporateMemoryError exception."""
    from src.core.exceptions import CorporateMemoryError

    error = CorporateMemoryError("Test error")
    assert str(error) == "Corporate memory operation failed: Test error"
    assert error.code == "CORPORATE_MEMORY_ERROR"
    assert error.status_code == 500


def test_corporate_fact_not_found_error() -> None:
    """Test CorporateFactNotFoundError exception."""
    from src.core.exceptions import CorporateFactNotFoundError

    error = CorporateFactNotFoundError("abc123")
    assert "Corporate fact" in str(error)
    assert error.status_code == 404
```

**Step 1.2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_exceptions.py::test_corporate_memory_error tests/test_exceptions.py::test_corporate_fact_not_found_error -v`
Expected: FAIL with "cannot import name 'CorporateMemoryError'"

**Step 1.3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` after `AuditLogError`:

```python
class CorporateMemoryError(ARIAException):
    """Corporate memory operation error (500).

    Used for failures when storing or retrieving company-level facts.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize corporate memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Corporate memory operation failed: {message}",
            code="CORPORATE_MEMORY_ERROR",
            status_code=500,
        )


class CorporateFactNotFoundError(NotFoundError):
    """Corporate fact not found error (404)."""

    def __init__(self, fact_id: str) -> None:
        """Initialize corporate fact not found error.

        Args:
            fact_id: The ID of the corporate fact that was not found.
        """
        super().__init__(resource="Corporate fact", resource_id=fact_id)
```

**Step 1.4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_exceptions.py::test_corporate_memory_error tests/test_exceptions.py::test_corporate_fact_not_found_error -v`
Expected: PASS

**Step 1.5: Run quality gates**

Run: `cd backend && mypy src/core/exceptions.py --strict && ruff check src/core/exceptions.py`
Expected: No errors

**Step 1.6: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_exceptions.py
git commit -m "$(cat <<'EOF'
feat(memory): add CorporateMemoryError and CorporateFactNotFoundError exceptions

Part of US-212: Corporate Memory Schema

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create Supabase Migration for corporate_facts Table

**Files:**
- Create: `/Users/dhruv/aria/supabase/migrations/20260202000001_create_corporate_facts.sql`

**Step 2.1: Write the migration**

Create `supabase/migrations/20260202000001_create_corporate_facts.sql`:

```sql
-- Create corporate_facts table for company-level shared knowledge
-- Part of US-212: Corporate Memory Schema

CREATE TABLE corporate_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0.75,
    source TEXT NOT NULL DEFAULT 'extracted',  -- extracted, aggregated, admin_stated
    graphiti_episode_name TEXT,  -- Reference to Graphiti episode for this fact
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES auth.users(id),  -- NULL = system-generated
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for company-based queries (primary access pattern)
CREATE INDEX idx_corporate_facts_company ON corporate_facts(company_id, is_active);

-- Index for subject-based lookups
CREATE INDEX idx_corporate_facts_subject ON corporate_facts(company_id, subject);

-- Index for predicate-based lookups
CREATE INDEX idx_corporate_facts_predicate ON corporate_facts(company_id, predicate);

-- Enable RLS
ALTER TABLE corporate_facts ENABLE ROW LEVEL SECURITY;

-- Users can read facts for their company
CREATE POLICY "Users can read company facts"
    ON corporate_facts
    FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
        )
    );

-- Admins can insert facts for their company
CREATE POLICY "Admins can insert company facts"
    ON corporate_facts
    FOR INSERT
    WITH CHECK (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    );

-- Admins can update facts for their company
CREATE POLICY "Admins can update company facts"
    ON corporate_facts
    FOR UPDATE
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    );

-- Service role has full access (for backend aggregation)
CREATE POLICY "Service can manage corporate facts"
    ON corporate_facts
    FOR ALL
    USING (auth.role() = 'service_role');

-- Add comments for documentation
COMMENT ON TABLE corporate_facts IS 'Company-level shared facts extracted from cross-user patterns. Privacy: no user-identifiable data.';
COMMENT ON COLUMN corporate_facts.source IS 'Fact source: extracted (from user data), aggregated (from patterns), admin_stated (manual entry)';
COMMENT ON COLUMN corporate_facts.graphiti_episode_name IS 'Reference to Graphiti episode containing semantic content';
```

**Step 2.2: Verify migration syntax**

Run: `cd backend && python -c "open('../supabase/migrations/20260202000001_create_corporate_facts.sql').read()"`
Expected: No errors (file is readable)

**Step 2.3: Commit**

```bash
git add supabase/migrations/20260202000001_create_corporate_facts.sql
git commit -m "$(cat <<'EOF'
feat(db): add corporate_facts table for company-level knowledge

Part of US-212: Corporate Memory Schema

- Company-scoped facts with RLS policies
- Users can read, admins can manage
- Service role for backend aggregation
- Graphiti episode reference for semantic content

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create CorporateMemory Data Models

**Files:**
- Create: `/Users/dhruv/aria/backend/src/memory/corporate.py`
- Test: `/Users/dhruv/aria/backend/tests/test_corporate_memory.py`

**Step 3.1: Write the failing test for data models**

Create `backend/tests/test_corporate_memory.py`:

```python
"""Tests for corporate memory module."""

from datetime import UTC, datetime

import pytest


def test_corporate_fact_source_enum() -> None:
    """Test CorporateFactSource enum values."""
    from src.memory.corporate import CorporateFactSource

    assert CorporateFactSource.EXTRACTED.value == "extracted"
    assert CorporateFactSource.AGGREGATED.value == "aggregated"
    assert CorporateFactSource.ADMIN_STATED.value == "admin_stated"


def test_corporate_fact_dataclass() -> None:
    """Test CorporateFact dataclass initialization."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Acme Corp",
        predicate="has_headquarters",
        object="San Francisco",
        confidence=0.85,
        source=CorporateFactSource.ADMIN_STATED,
        is_active=True,
        created_by="user-456",
        created_at=now,
        updated_at=now,
    )

    assert fact.id == "test-id"
    assert fact.company_id == "company-123"
    assert fact.subject == "Acme Corp"
    assert fact.predicate == "has_headquarters"
    assert fact.object == "San Francisco"
    assert fact.confidence == 0.85
    assert fact.source == CorporateFactSource.ADMIN_STATED
    assert fact.is_active is True
    assert fact.created_by == "user-456"


def test_corporate_fact_to_dict() -> None:
    """Test CorporateFact serialization to dictionary."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Test Subject",
        predicate="test_predicate",
        object="Test Object",
        confidence=0.75,
        source=CorporateFactSource.EXTRACTED,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    data = fact.to_dict()
    assert data["id"] == "test-id"
    assert data["company_id"] == "company-123"
    assert data["source"] == "extracted"
    assert data["created_at"] == now.isoformat()


def test_corporate_fact_from_dict() -> None:
    """Test CorporateFact deserialization from dictionary."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    data = {
        "id": "test-id",
        "company_id": "company-123",
        "subject": "Test Subject",
        "predicate": "test_predicate",
        "object": "Test Object",
        "confidence": 0.8,
        "source": "aggregated",
        "is_active": True,
        "graphiti_episode_name": "corp:company-123:test-id",
        "created_by": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    fact = CorporateFact.from_dict(data)
    assert fact.id == "test-id"
    assert fact.company_id == "company-123"
    assert fact.source == CorporateFactSource.AGGREGATED
    assert fact.graphiti_episode_name == "corp:company-123:test-id"


def test_corporate_memory_class_exists() -> None:
    """Test CorporateMemory class can be instantiated."""
    from src.memory.corporate import CorporateMemory

    memory = CorporateMemory()
    assert memory is not None
```

**Step 3.2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_corporate_memory.py -v`
Expected: FAIL with "No module named 'src.memory.corporate'"

**Step 3.3: Write minimal implementation**

Create `backend/src/memory/corporate.py`:

```python
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
from typing import TYPE_CHECKING, Any

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
            "invalidated_at": self.invalidated_at.isoformat()
            if self.invalidated_at
            else None,
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

            return CorporateFact.from_dict(response.data)

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

            return [CorporateFact.from_dict(row) for row in (response.data or [])]

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

            return [CorporateFact.from_dict(row) for row in (response.data or [])]

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
```

**Step 3.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_corporate_memory.py -v`
Expected: All 6 tests PASS

**Step 3.5: Run quality gates**

Run: `cd backend && mypy src/memory/corporate.py --strict && ruff check src/memory/corporate.py && ruff format src/memory/corporate.py --check`
Expected: No errors

**Step 3.6: Commit**

```bash
git add backend/src/memory/corporate.py backend/tests/test_corporate_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): add CorporateMemory module for company-level facts

Part of US-212: Corporate Memory Schema

- CorporateFact dataclass with privacy-safe storage
- CorporateFactSource enum (extracted, aggregated, admin_stated)
- CorporateMemory service with CRUD operations
- Graphiti namespace separation for multi-tenant isolation
- Supabase + Graphiti dual storage pattern

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update Memory Package Exports

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/memory/__init__.py`

**Step 4.1: Add corporate memory exports**

Update `backend/src/memory/__init__.py`:

```python
"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
- Digital Twin: User writing style fingerprinting (Graphiti)
- Corporate: Company-level shared knowledge (Graphiti + Supabase)
"""

from src.memory.audit import (
    AuditLogEntry,
    MemoryAuditLogger,
    MemoryOperation,
    MemoryType,
    log_memory_operation,
)
from src.memory.confidence import ConfidenceScorer
from src.memory.corporate import (
    CorporateFact,
    CorporateFactSource,
    CorporateMemory,
    CORPORATE_SOURCE_CONFIDENCE,
)
from src.memory.digital_twin import (
    DigitalTwin,
    TextStyleAnalyzer,
    WritingStyleFingerprint,
)
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory
from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)

__all__ = [
    # Memory Audit
    "AuditLogEntry",
    "MemoryAuditLogger",
    "MemoryOperation",
    "MemoryType",
    "log_memory_operation",
    # Confidence Scoring
    "ConfidenceScorer",
    # Working Memory
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    # Semantic Memory
    "FactSource",
    "SemanticFact",
    "SemanticMemory",
    # Procedural Memory
    "ProceduralMemory",
    "Workflow",
    # Prospective Memory
    "ProspectiveMemory",
    "ProspectiveTask",
    "TriggerType",
    "TaskStatus",
    "TaskPriority",
    # Digital Twin
    "DigitalTwin",
    "TextStyleAnalyzer",
    "WritingStyleFingerprint",
    # Corporate Memory
    "CorporateFact",
    "CorporateFactSource",
    "CorporateMemory",
    "CORPORATE_SOURCE_CONFIDENCE",
]
```

**Step 4.2: Run import test**

Run: `cd backend && python -c "from src.memory import CorporateMemory, CorporateFact, CorporateFactSource; print('OK')"`
Expected: "OK"

**Step 4.3: Commit**

```bash
git add backend/src/memory/__init__.py
git commit -m "$(cat <<'EOF'
feat(memory): export corporate memory from package

Part of US-212: Corporate Memory Schema

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Corporate Memory API Endpoints

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/api/routes/memory.py`
- Test: `/Users/dhruv/aria/backend/tests/test_api_corporate_memory.py`

**Step 5.1: Write the failing test**

Create `backend/tests/test_api_corporate_memory.py`:

```python
"""Tests for corporate memory API endpoints."""

import pytest


def test_create_corporate_fact_request_model() -> None:
    """Test CreateCorporateFactRequest model validation."""
    from src.api.routes.memory import CreateCorporateFactRequest

    request = CreateCorporateFactRequest(
        subject="Acme Corp",
        predicate="has_industry",
        object="Technology",
        source="admin_stated",
        confidence=0.9,
    )
    assert request.subject == "Acme Corp"
    assert request.predicate == "has_industry"
    assert request.confidence == 0.9


def test_corporate_fact_response_model() -> None:
    """Test CorporateFactResponse model structure."""
    from datetime import UTC, datetime

    from src.api.routes.memory import CorporateFactResponse

    response = CorporateFactResponse(
        id="test-id",
        company_id="company-123",
        subject="Test",
        predicate="test_pred",
        object="Value",
        confidence=0.8,
        source="extracted",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert response.id == "test-id"


def test_create_corporate_fact_response_model() -> None:
    """Test CreateCorporateFactResponse model."""
    from src.api.routes.memory import CreateCorporateFactResponse

    response = CreateCorporateFactResponse(id="fact-123")
    assert response.id == "fact-123"
    assert response.message == "Corporate fact created successfully"
```

**Step 5.2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_corporate_memory.py -v`
Expected: FAIL with "cannot import name 'CreateCorporateFactRequest'"

**Step 5.3: Add API models and endpoints**

Add to `backend/src/api/routes/memory.py` (after existing models, before routes):

```python
# Add these imports at the top (add to existing imports section):
from src.memory.corporate import (
    CorporateFact,
    CorporateFactSource,
    CorporateMemory,
    CORPORATE_SOURCE_CONFIDENCE,
)

# Add these models after existing models:

# Corporate Memory Models
class CreateCorporateFactRequest(BaseModel):
    """Request body for creating a new corporate fact."""

    subject: str = Field(..., min_length=1, description="Entity the fact is about")
    predicate: str = Field(..., min_length=1, description="Relationship type")
    object: str = Field(..., min_length=1, description="Value or related entity")
    source: Literal["extracted", "aggregated", "admin_stated"] | None = Field(
        None, description="Source of the fact"
    )
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score"
    )


class CreateCorporateFactResponse(BaseModel):
    """Response body for corporate fact creation."""

    id: str
    message: str = "Corporate fact created successfully"


class CorporateFactResponse(BaseModel):
    """Response body for a single corporate fact."""

    id: str
    company_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    is_active: bool
    created_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CorporateFactsResponse(BaseModel):
    """Response body for listing corporate facts."""

    items: list[CorporateFactResponse]
    total: int
    has_more: bool


class InvalidateCorporateFactRequest(BaseModel):
    """Request body for invalidating a corporate fact."""

    reason: str = Field(..., min_length=1, description="Reason for invalidation")
```

Add these endpoints after existing endpoints:

```python
# Corporate Memory Endpoints


@router.post("/corporate/fact", response_model=CreateCorporateFactResponse, status_code=201)
async def store_corporate_fact(
    current_user: CurrentUser,
    request: CreateCorporateFactRequest,
) -> CreateCorporateFactResponse:
    """Store a new corporate fact (admin only).

    Creates a fact at the company level that is shared across all users.
    Only admins can create corporate facts. Facts do not contain any
    user-identifiable information.

    Args:
        current_user: Authenticated admin user.
        request: Corporate fact creation request body.

    Returns:
        Created corporate fact with ID.

    Raises:
        HTTPException: 403 if user is not an admin.
    """
    # Get user profile to verify admin role and get company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user role") from None

    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create corporate facts")

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Determine source and confidence
    source = CorporateFactSource(request.source) if request.source else CorporateFactSource.ADMIN_STATED
    confidence = (
        request.confidence
        if request.confidence is not None
        else CORPORATE_SOURCE_CONFIDENCE[source]
    )

    # Build fact
    now = datetime.now(UTC)
    fact = CorporateFact(
        id=str(uuid.uuid4()),
        company_id=company_id,
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        confidence=confidence,
        source=source,
        is_active=True,
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )

    # Store fact
    memory = CorporateMemory()
    try:
        fact_id = await memory.add_fact(fact)
    except CorporateMemoryError as e:
        logger.error(
            "Failed to store corporate fact",
            extra={"error": str(e), "company_id": company_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    logger.info(
        "Stored corporate fact via API",
        extra={
            "fact_id": fact_id,
            "company_id": company_id,
            "subject": request.subject,
            "predicate": request.predicate,
            "admin_id": current_user.id,
        },
    )

    return CreateCorporateFactResponse(id=fact_id)


@router.get("/corporate/facts", response_model=CorporateFactsResponse)
async def list_corporate_facts(
    current_user: CurrentUser,
    subject: str | None = Query(None, description="Filter by subject"),
    predicate: str | None = Query(None, description="Filter by predicate"),
    active_only: bool = Query(True, description="Only return active facts"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
) -> CorporateFactsResponse:
    """List corporate facts for the user's company.

    Returns facts that are shared across all users in the company.

    Args:
        current_user: Authenticated user.
        subject: Optional filter by subject entity.
        predicate: Optional filter by predicate type.
        active_only: Whether to exclude invalidated facts.
        limit: Maximum number of facts to return.

    Returns:
        List of corporate facts.
    """
    # Get user's company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user") from None

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Query facts
    memory = CorporateMemory()
    try:
        facts = await memory.get_facts_for_company(
            company_id=company_id,
            subject=subject,
            predicate=predicate,
            active_only=active_only,
            limit=limit + 1,  # Get extra to check has_more
        )
    except CorporateMemoryError as e:
        logger.error(
            "Failed to list corporate facts",
            extra={"error": str(e), "company_id": company_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    has_more = len(facts) > limit
    facts = facts[:limit]

    items = [
        CorporateFactResponse(
            id=f.id,
            company_id=f.company_id,
            subject=f.subject,
            predicate=f.predicate,
            object=f.object,
            confidence=f.confidence,
            source=f.source.value,
            is_active=f.is_active,
            created_by=f.created_by,
            invalidated_at=f.invalidated_at,
            invalidation_reason=f.invalidation_reason,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in facts
    ]

    return CorporateFactsResponse(
        items=items,
        total=len(items),
        has_more=has_more,
    )


@router.get("/corporate/facts/{fact_id}", response_model=CorporateFactResponse)
async def get_corporate_fact(
    current_user: CurrentUser,
    fact_id: str,
) -> CorporateFactResponse:
    """Get a specific corporate fact by ID.

    Args:
        current_user: Authenticated user.
        fact_id: The fact's UUID.

    Returns:
        The corporate fact.

    Raises:
        HTTPException: 404 if fact not found.
    """
    # Get user's company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user") from None

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Get fact
    memory = CorporateMemory()
    try:
        fact = await memory.get_fact(company_id, fact_id)
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail="Corporate fact not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to get corporate fact",
            extra={"error": str(e), "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    return CorporateFactResponse(
        id=fact.id,
        company_id=fact.company_id,
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        confidence=fact.confidence,
        source=fact.source.value,
        is_active=fact.is_active,
        created_by=fact.created_by,
        invalidated_at=fact.invalidated_at,
        invalidation_reason=fact.invalidation_reason,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


@router.post("/corporate/facts/{fact_id}/invalidate", status_code=204)
async def invalidate_corporate_fact(
    current_user: CurrentUser,
    fact_id: str,
    request: InvalidateCorporateFactRequest,
) -> None:
    """Invalidate a corporate fact (admin only, soft delete).

    Args:
        current_user: Authenticated admin user.
        fact_id: The fact's UUID.
        request: Invalidation request with reason.

    Raises:
        HTTPException: 403 if user is not admin, 404 if fact not found.
    """
    # Verify admin role and get company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user role") from None

    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can invalidate corporate facts")

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Invalidate fact
    memory = CorporateMemory()
    try:
        await memory.invalidate_fact(
            company_id=company_id,
            fact_id=fact_id,
            reason=request.reason,
            invalidated_by=current_user.id,
        )
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail="Corporate fact not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to invalidate corporate fact",
            extra={"error": str(e), "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    logger.info(
        "Invalidated corporate fact via API",
        extra={
            "fact_id": fact_id,
            "company_id": company_id,
            "admin_id": current_user.id,
            "reason": request.reason,
        },
    )


@router.delete("/corporate/facts/{fact_id}", status_code=204)
async def delete_corporate_fact(
    current_user: CurrentUser,
    fact_id: str,
) -> None:
    """Permanently delete a corporate fact (admin only).

    Args:
        current_user: Authenticated admin user.
        fact_id: The fact's UUID.

    Raises:
        HTTPException: 403 if user is not admin, 404 if fact not found.
    """
    # Verify admin role and get company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user role") from None

    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete corporate facts")

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Delete fact
    memory = CorporateMemory()
    try:
        await memory.delete_fact(company_id, fact_id)
    except CorporateFactNotFoundError:
        raise HTTPException(status_code=404, detail="Corporate fact not found") from None
    except CorporateMemoryError as e:
        logger.error(
            "Failed to delete corporate fact",
            extra={"error": str(e), "fact_id": fact_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    logger.info(
        "Deleted corporate fact via API",
        extra={
            "fact_id": fact_id,
            "company_id": company_id,
            "admin_id": current_user.id,
        },
    )


@router.get("/corporate/search", response_model=CorporateFactsResponse)
async def search_corporate_facts(
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search query"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="Minimum confidence"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> CorporateFactsResponse:
    """Search corporate facts using semantic similarity.

    Args:
        current_user: Authenticated user.
        q: Natural language search query.
        min_confidence: Minimum confidence threshold.
        limit: Maximum number of facts to return.

    Returns:
        List of matching corporate facts.
    """
    # Get user's company_id
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify user") from None

    company_id = profile.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with a company")

    # Search facts
    memory = CorporateMemory()
    try:
        facts = await memory.search_facts(
            company_id=company_id,
            query=q,
            min_confidence=min_confidence,
            limit=limit,
        )
    except CorporateMemoryError as e:
        logger.error(
            "Failed to search corporate facts",
            extra={"error": str(e), "company_id": company_id},
        )
        raise HTTPException(status_code=503, detail="Corporate memory unavailable") from None

    items = [
        CorporateFactResponse(
            id=f.id,
            company_id=f.company_id,
            subject=f.subject,
            predicate=f.predicate,
            object=f.object,
            confidence=f.confidence,
            source=f.source.value,
            is_active=f.is_active,
            created_by=f.created_by,
            invalidated_at=f.invalidated_at,
            invalidation_reason=f.invalidation_reason,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in facts
    ]

    return CorporateFactsResponse(
        items=items,
        total=len(items),
        has_more=False,  # Search doesn't paginate
    )
```

Also add the import for CorporateFactNotFoundError at the top:

```python
from src.core.exceptions import (
    CorporateFactNotFoundError,
    CorporateMemoryError,
    DigitalTwinError,
    EpisodicMemoryError,
    ProceduralMemoryError,
    ProspectiveMemoryError,
    SemanticMemoryError,
)
```

**Step 5.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_corporate_memory.py -v`
Expected: All 3 tests PASS

**Step 5.5: Run quality gates**

Run: `cd backend && mypy src/api/routes/memory.py --strict && ruff check src/api/routes/memory.py && ruff format src/api/routes/memory.py --check`
Expected: No errors

**Step 5.6: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/test_api_corporate_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add corporate memory endpoints

Part of US-212: Corporate Memory Schema

Endpoints:
- POST /memory/corporate/fact - Create fact (admin only)
- GET /memory/corporate/facts - List company facts
- GET /memory/corporate/facts/{id} - Get specific fact
- POST /memory/corporate/facts/{id}/invalidate - Soft delete (admin)
- DELETE /memory/corporate/facts/{id} - Hard delete (admin)
- GET /memory/corporate/search - Semantic search

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Unit Tests for Isolation

**Files:**
- Modify: `/Users/dhruv/aria/backend/tests/test_corporate_memory.py`

**Step 6.1: Add isolation tests**

Append to `backend/tests/test_corporate_memory.py`:

```python
def test_graphiti_episode_name_includes_company_namespace() -> None:
    """Test that Graphiti episode names use company namespace for isolation."""
    from src.memory.corporate import CorporateMemory

    memory = CorporateMemory()
    episode_name = memory._get_graphiti_episode_name("company-abc", "fact-123")

    # Should use corp: prefix with company_id for namespace isolation
    assert episode_name == "corp:company-abc:fact-123"
    assert "company-abc" in episode_name


def test_corporate_fact_excludes_user_identifiable_data() -> None:
    """Test that CorporateFact can be created without user-identifiable info."""
    from datetime import UTC, datetime

    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)

    # Create fact without any user ID
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Market Trend",
        predicate="shows_growth",
        object="15% YoY",
        confidence=0.8,
        source=CorporateFactSource.AGGREGATED,
        is_active=True,
        created_by=None,  # System-generated, no user
        created_at=now,
        updated_at=now,
    )

    # Fact should not require user_id
    assert fact.created_by is None

    # to_dict should not include any user_id field
    data = fact.to_dict()
    assert "user_id" not in data


def test_fact_body_does_not_contain_user_info() -> None:
    """Test that Graphiti fact body excludes user-identifiable data."""
    from datetime import UTC, datetime

    from src.memory.corporate import CorporateFact, CorporateFactSource, CorporateMemory

    memory = CorporateMemory()
    now = datetime.now(UTC)

    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Industry Trend",
        predicate="affects",
        object="Market Size",
        confidence=0.75,
        source=CorporateFactSource.EXTRACTED,
        is_active=True,
        created_by="user-456",  # Even if created_by is set
        created_at=now,
        updated_at=now,
    )

    body = memory._build_fact_body(fact)

    # Body should contain company_id (needed for namespace)
    assert "company-123" in body

    # Body should NOT contain user_id or created_by
    assert "user-456" not in body
    assert "created_by" not in body.lower()
    assert "user_id" not in body.lower()


def test_corporate_source_confidence_defaults() -> None:
    """Test that corporate fact sources have appropriate default confidence."""
    from src.memory.corporate import CORPORATE_SOURCE_CONFIDENCE, CorporateFactSource

    # Admin-stated should have highest confidence
    assert CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.ADMIN_STATED] >= 0.9

    # Aggregated should be higher than extracted (more data points)
    assert (
        CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.AGGREGATED]
        > CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.EXTRACTED]
    )

    # All confidence values should be in valid range
    for source, confidence in CORPORATE_SOURCE_CONFIDENCE.items():
        assert 0.0 <= confidence <= 1.0, f"Invalid confidence for {source}"
```

**Step 6.2: Run tests**

Run: `cd backend && pytest tests/test_corporate_memory.py -v`
Expected: All 10 tests PASS

**Step 6.3: Commit**

```bash
git add backend/tests/test_corporate_memory.py
git commit -m "$(cat <<'EOF'
test(memory): add isolation and privacy tests for corporate memory

Part of US-212: Corporate Memory Schema

- Verify namespace isolation in Graphiti
- Verify no user-identifiable data in fact body
- Verify confidence defaults by source type

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Run Full Quality Gates and Final Verification

**Step 7.1: Run backend quality gates**

```bash
cd backend
pytest tests/ -v
mypy src/ --strict
ruff check src/
ruff format src/ --check
```

Expected: All tests pass, no type errors, no lint errors

**Step 7.2: Verify migration file is valid**

```bash
ls -la supabase/migrations/20260202000001_create_corporate_facts.sql
```

Expected: File exists

**Step 7.3: Final commit (if any formatting changes needed)**

```bash
git status
# If any files need formatting:
cd backend && ruff format src/
git add -A
git commit -m "$(cat <<'EOF'
chore: format code

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Acceptance Criteria Checklist

After completing all tasks, verify:

- [x] **Company-level facts stored separately from user facts**
  - `corporate_facts` table with `company_id` scope
  - Separate from `semantic_facts` (user-level)

- [x] **Community patterns extracted from cross-user data**
  - `CorporateFactSource.AGGREGATED` source type
  - Service role policies for backend aggregation

- [x] **Privacy: no user-identifiable data in corporate memory**
  - `CorporateFact` has no `user_id` field
  - `_build_fact_body()` excludes user info
  - Unit tests verify privacy

- [x] **Access control: users can read company facts**
  - RLS policy: "Users can read company facts"
  - `/memory/corporate/facts` endpoint for users

- [x] **Admin can manage corporate facts**
  - RLS policies for admin insert/update
  - Endpoints verify admin role before mutations

- [x] **Graphiti namespace separation for multi-tenant**
  - Episode names: `corp:{company_id}:{fact_id}`
  - Search queries include company namespace

- [x] **Unit tests for isolation**
  - `test_graphiti_episode_name_includes_company_namespace`
  - `test_corporate_fact_excludes_user_identifiable_data`
  - `test_fact_body_does_not_contain_user_info`

---

## Files Modified Summary

| File | Action |
|------|--------|
| `backend/src/core/exceptions.py` | Add CorporateMemoryError, CorporateFactNotFoundError |
| `supabase/migrations/20260202000001_create_corporate_facts.sql` | Create corporate_facts table |
| `backend/src/memory/corporate.py` | Create CorporateMemory module |
| `backend/src/memory/__init__.py` | Export corporate memory classes |
| `backend/src/api/routes/memory.py` | Add corporate memory endpoints |
| `backend/tests/test_exceptions.py` | Add exception tests |
| `backend/tests/test_corporate_memory.py` | Add module and isolation tests |
| `backend/tests/test_api_corporate_memory.py` | Add API endpoint tests |
