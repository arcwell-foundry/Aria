# US-211: Memory Audit Log Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a comprehensive memory audit logging system that tracks all memory operations for enterprise compliance and debugging.

**Architecture:**
- Create a `MemoryAuditLogger` class in `src/memory/audit.py` that logs operations to a Supabase `memory_audit_log` table
- Integrate audit logging into all existing memory classes (episodic, semantic, procedural, prospective) via a simple decorator pattern
- Expose an admin-only query endpoint at `GET /api/v1/memory/audit`

**Tech Stack:** Python/FastAPI, Supabase (PostgreSQL), Pydantic models

---

## Task 1: Create SQL Migration for memory_audit_log Table

**Files:**
- Create: `supabase/migrations/20260202000000_create_memory_audit_log.sql`

**Step 1: Write the SQL migration file**

```sql
-- Create memory_audit_log table for tracking all memory operations
CREATE TABLE memory_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    operation TEXT NOT NULL,  -- create, update, delete, query, invalidate
    memory_type TEXT NOT NULL,  -- episodic, semantic, procedural, prospective
    memory_id UUID,  -- ID of the affected memory record (null for queries)
    metadata JSONB,  -- Additional operation context (query params, counts, etc.)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for user-based queries (most common access pattern)
CREATE INDEX idx_audit_user_time ON memory_audit_log(user_id, created_at DESC);

-- Index for operation type filtering
CREATE INDEX idx_audit_operation ON memory_audit_log(operation);

-- Index for memory type filtering
CREATE INDEX idx_audit_memory_type ON memory_audit_log(memory_type);

-- Enable RLS
ALTER TABLE memory_audit_log ENABLE ROW LEVEL SECURITY;

-- Admin can read all audit logs
CREATE POLICY "Admins can read all audit logs"
    ON memory_audit_log
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Users can only read their own audit logs
CREATE POLICY "Users can read own audit logs"
    ON memory_audit_log
    FOR SELECT
    USING (user_id = auth.uid());

-- Service role can insert audit logs
CREATE POLICY "Service can insert audit logs"
    ON memory_audit_log
    FOR INSERT
    WITH CHECK (true);

-- Add comment for documentation
COMMENT ON TABLE memory_audit_log IS 'Audit log for all memory operations. Retention: 90 days (managed by cleanup job)';
```

**Step 2: Verify migration syntax is valid**

Run: `cd backend && cat ../supabase/migrations/20260202000000_create_memory_audit_log.sql | head -50`
Expected: The SQL file contents display without errors

**Step 3: Commit migration**

```bash
git add supabase/migrations/20260202000000_create_memory_audit_log.sql
git commit -m "feat(db): add memory_audit_log table for US-211"
```

---

## Task 2: Create MemoryAuditLog Exception

**Files:**
- Modify: `backend/src/core/exceptions.py`
- Test: `backend/tests/test_exceptions.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_exceptions.py`:

```python
def test_audit_log_error_initialization() -> None:
    """Test AuditLogError initializes correctly."""
    from src.core.exceptions import AuditLogError

    error = AuditLogError("Failed to write audit log")

    assert error.message == "Audit log operation failed: Failed to write audit log"
    assert error.code == "AUDIT_LOG_ERROR"
    assert error.status_code == 500
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_exceptions.py::test_audit_log_error_initialization -v`
Expected: FAIL with "cannot import name 'AuditLogError'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` after `FingerprintNotFoundError`:

```python
class AuditLogError(ARIAException):
    """Audit log operation error (500).

    Used for failures when writing or querying audit logs.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize audit log error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Audit log operation failed: {message}",
            code="AUDIT_LOG_ERROR",
            status_code=500,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_exceptions.py::test_audit_log_error_initialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_exceptions.py
git commit -m "feat(exceptions): add AuditLogError for memory audit logging"
```

---

## Task 3: Create MemoryAuditLogger Core Class

**Files:**
- Create: `backend/src/memory/audit.py`
- Test: `backend/tests/test_memory_audit.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_memory_audit.py`:

```python
"""Tests for memory audit logging module."""

from datetime import UTC, datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_memory_operation_enum_values() -> None:
    """Test MemoryOperation enum has expected values."""
    from src.memory.audit import MemoryOperation

    assert MemoryOperation.CREATE.value == "create"
    assert MemoryOperation.UPDATE.value == "update"
    assert MemoryOperation.DELETE.value == "delete"
    assert MemoryOperation.QUERY.value == "query"
    assert MemoryOperation.INVALIDATE.value == "invalidate"


def test_memory_type_enum_values() -> None:
    """Test MemoryType enum has expected values."""
    from src.memory.audit import MemoryType

    assert MemoryType.EPISODIC.value == "episodic"
    assert MemoryType.SEMANTIC.value == "semantic"
    assert MemoryType.PROCEDURAL.value == "procedural"
    assert MemoryType.PROSPECTIVE.value == "prospective"


def test_audit_log_entry_dataclass() -> None:
    """Test AuditLogEntry dataclass initialization."""
    from src.memory.audit import AuditLogEntry, MemoryOperation, MemoryType

    entry = AuditLogEntry(
        user_id="user-123",
        operation=MemoryOperation.CREATE,
        memory_type=MemoryType.SEMANTIC,
        memory_id="mem-456",
        metadata={"subject": "John"},
    )

    assert entry.user_id == "user-123"
    assert entry.operation == MemoryOperation.CREATE
    assert entry.memory_type == MemoryType.SEMANTIC
    assert entry.memory_id == "mem-456"
    assert entry.metadata == {"subject": "John"}


def test_audit_log_entry_to_dict() -> None:
    """Test AuditLogEntry.to_dict serializes correctly."""
    from src.memory.audit import AuditLogEntry, MemoryOperation, MemoryType

    entry = AuditLogEntry(
        user_id="user-123",
        operation=MemoryOperation.QUERY,
        memory_type=MemoryType.EPISODIC,
        memory_id=None,
        metadata={"query": "test search"},
    )

    data = entry.to_dict()

    assert data["user_id"] == "user-123"
    assert data["operation"] == "query"
    assert data["memory_type"] == "episodic"
    assert data["memory_id"] is None
    assert data["metadata"] == {"query": "test search"}


def test_memory_audit_logger_has_log_method() -> None:
    """Test MemoryAuditLogger class has log method."""
    from src.memory.audit import MemoryAuditLogger

    logger = MemoryAuditLogger()
    assert hasattr(logger, "log")
    assert callable(logger.log)


def test_memory_audit_logger_has_query_method() -> None:
    """Test MemoryAuditLogger class has query method."""
    from src.memory.audit import MemoryAuditLogger

    logger = MemoryAuditLogger()
    assert hasattr(logger, "query")
    assert callable(logger.query)


@pytest.mark.asyncio
async def test_log_inserts_to_supabase() -> None:
    """Test log method inserts audit entry to Supabase."""
    from src.memory.audit import AuditLogEntry, MemoryAuditLogger, MemoryOperation, MemoryType

    entry = AuditLogEntry(
        user_id="user-123",
        operation=MemoryOperation.CREATE,
        memory_type=MemoryType.SEMANTIC,
        memory_id="fact-456",
        metadata={"subject": "John"},
    )

    logger = MemoryAuditLogger()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "audit-789"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        result = await logger.log(entry)

    assert result == "audit-789"
    mock_client.table.assert_called_once_with("memory_audit_log")


@pytest.mark.asyncio
async def test_log_handles_database_error() -> None:
    """Test log method raises AuditLogError on database failure."""
    from src.core.exceptions import AuditLogError
    from src.memory.audit import AuditLogEntry, MemoryAuditLogger, MemoryOperation, MemoryType

    entry = AuditLogEntry(
        user_id="user-123",
        operation=MemoryOperation.CREATE,
        memory_type=MemoryType.SEMANTIC,
        memory_id="fact-456",
    )

    logger = MemoryAuditLogger()

    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("DB Error")

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        with pytest.raises(AuditLogError):
            await logger.log(entry)


@pytest.mark.asyncio
async def test_query_returns_audit_entries() -> None:
    """Test query method returns audit entries from Supabase."""
    from src.memory.audit import MemoryAuditLogger

    logger = MemoryAuditLogger()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        {
            "id": "audit-1",
            "user_id": "user-123",
            "operation": "create",
            "memory_type": "semantic",
            "memory_id": "fact-456",
            "metadata": {},
            "created_at": "2026-02-02T00:00:00+00:00",
        }
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.offset.return_value.execute.return_value = mock_response

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        results = await logger.query(user_id="user-123", limit=50, offset=0)

    assert len(results) == 1
    assert results[0]["id"] == "audit-1"


@pytest.mark.asyncio
async def test_query_with_filters() -> None:
    """Test query method applies operation and memory_type filters."""
    from src.memory.audit import MemoryAuditLogger, MemoryOperation, MemoryType

    logger = MemoryAuditLogger()

    mock_client = MagicMock()
    mock_chain = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []

    # Build mock chain
    mock_client.table.return_value.select.return_value = mock_chain
    mock_chain.eq.return_value = mock_chain
    mock_chain.order.return_value = mock_chain
    mock_chain.limit.return_value = mock_chain
    mock_chain.offset.return_value = mock_chain
    mock_chain.execute.return_value = mock_response

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        await logger.query(
            user_id="user-123",
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            limit=20,
            offset=0,
        )

    # Verify eq was called for each filter
    calls = [str(call) for call in mock_chain.eq.call_args_list]
    assert any("user_id" in str(c) for c in calls)
    assert any("operation" in str(c) or "create" in str(c) for c in calls)
    assert any("memory_type" in str(c) or "semantic" in str(c) for c in calls)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_memory_audit.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.audit'"

**Step 3: Write minimal implementation**

Create `backend/src/memory/audit.py`:

```python
"""Memory audit logging module for tracking all memory operations.

Provides:
- AuditLogEntry: Dataclass for audit log entries
- MemoryAuditLogger: Service for logging and querying audit entries
- MemoryOperation: Enum of audit-able operations
- MemoryType: Enum of memory types
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.core.exceptions import AuditLogError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class MemoryOperation(Enum):
    """Types of memory operations that are audited."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    INVALIDATE = "invalidate"


class MemoryType(Enum):
    """Types of memory that can be audited."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PROSPECTIVE = "prospective"


@dataclass
class AuditLogEntry:
    """A single audit log entry for a memory operation.

    Captures the who, what, and when of memory operations
    without storing sensitive content (only IDs).
    """

    user_id: str
    operation: MemoryOperation
    memory_type: MemoryType
    memory_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for database storage.

        Returns:
            Dictionary suitable for Supabase insertion.
        """
        return {
            "user_id": self.user_id,
            "operation": self.operation.value,
            "memory_type": self.memory_type.value,
            "memory_id": self.memory_id,
            "metadata": self.metadata,
        }


class MemoryAuditLogger:
    """Service for logging and querying memory audit entries.

    Provides async methods to log memory operations to Supabase
    and query the audit log for admin users.
    """

    async def log(self, entry: AuditLogEntry) -> str:
        """Log a memory operation to the audit table.

        Args:
            entry: The audit log entry to store.

        Returns:
            The ID of the created audit log entry.

        Raises:
            AuditLogError: If logging fails.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("memory_audit_log")
                .insert(entry.to_dict())
                .execute()
            )

            if response.data and len(response.data) > 0:
                audit_id = response.data[0].get("id", "")
                logger.debug(
                    "Audit log entry created",
                    extra={
                        "audit_id": audit_id,
                        "operation": entry.operation.value,
                        "memory_type": entry.memory_type.value,
                    },
                )
                return audit_id

            raise AuditLogError("No data returned from insert")

        except AuditLogError:
            raise
        except Exception as e:
            logger.exception("Failed to write audit log")
            raise AuditLogError(str(e)) from e

    async def query(
        self,
        user_id: str | None = None,
        operation: MemoryOperation | None = None,
        memory_type: MemoryType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query audit log entries with optional filters.

        Args:
            user_id: Filter by user ID (required for non-admin).
            operation: Filter by operation type.
            memory_type: Filter by memory type.
            limit: Maximum entries to return.
            offset: Number of entries to skip.

        Returns:
            List of audit log entries.

        Raises:
            AuditLogError: If query fails.
        """
        try:
            client = SupabaseClient.get_client()
            query = client.table("memory_audit_log").select("*")

            if user_id is not None:
                query = query.eq("user_id", user_id)

            if operation is not None:
                query = query.eq("operation", operation.value)

            if memory_type is not None:
                query = query.eq("memory_type", memory_type.value)

            response = (
                query.order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.exception("Failed to query audit log")
            raise AuditLogError(str(e)) from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_memory_audit.py -v`
Expected: All tests PASS

**Step 5: Run mypy to check types**

Run: `cd backend && mypy src/memory/audit.py --strict`
Expected: Success: no issues found

**Step 6: Commit**

```bash
git add backend/src/memory/audit.py backend/tests/test_memory_audit.py
git commit -m "feat(memory): add MemoryAuditLogger for audit logging"
```

---

## Task 4: Add Audit Logger Helper Function for Convenience

**Files:**
- Modify: `backend/src/memory/audit.py`
- Modify: `backend/tests/test_memory_audit.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_memory_audit.py`:

```python
@pytest.mark.asyncio
async def test_log_memory_operation_convenience_function() -> None:
    """Test log_memory_operation convenience function."""
    from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "audit-convenience"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        result = await log_memory_operation(
            user_id="user-123",
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id="fact-789",
            metadata={"test": True},
        )

    assert result == "audit-convenience"


@pytest.mark.asyncio
async def test_log_memory_operation_suppresses_errors() -> None:
    """Test log_memory_operation does not raise on failure when suppress=True."""
    from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("DB down")

    with patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client):
        # Should not raise, returns None
        result = await log_memory_operation(
            user_id="user-123",
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            suppress_errors=True,
        )

    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_memory_audit.py::test_log_memory_operation_convenience_function -v`
Expected: FAIL with "cannot import name 'log_memory_operation'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/audit.py` at the end:

```python
async def log_memory_operation(
    user_id: str,
    operation: MemoryOperation,
    memory_type: MemoryType,
    memory_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    suppress_errors: bool = False,
) -> str | None:
    """Convenience function to log a memory operation.

    Provides a simpler interface than using MemoryAuditLogger directly.
    Can optionally suppress errors to prevent audit failures from
    breaking the main operation.

    Args:
        user_id: The user performing the operation.
        operation: The type of operation.
        memory_type: The type of memory being accessed.
        memory_id: Optional ID of the affected memory.
        metadata: Optional additional context.
        suppress_errors: If True, log errors but don't raise.

    Returns:
        Audit log entry ID, or None if suppressed error occurred.
    """
    entry = AuditLogEntry(
        user_id=user_id,
        operation=operation,
        memory_type=memory_type,
        memory_id=memory_id,
        metadata=metadata or {},
    )

    audit_logger = MemoryAuditLogger()

    try:
        return await audit_logger.log(entry)
    except AuditLogError:
        if suppress_errors:
            logger.warning(
                "Audit log failed (suppressed)",
                extra={
                    "user_id": user_id,
                    "operation": operation.value,
                    "memory_type": memory_type.value,
                },
            )
            return None
        raise
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_memory_audit.py::test_log_memory_operation_convenience_function tests/test_memory_audit.py::test_log_memory_operation_suppresses_errors -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/audit.py backend/tests/test_memory_audit.py
git commit -m "feat(memory): add log_memory_operation convenience function"
```

---

## Task 5: Add Audit Logging to SemanticMemory

**Files:**
- Modify: `backend/src/memory/semantic.py`
- Modify: `backend/tests/test_semantic_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_semantic_memory.py`:

```python
@pytest.mark.asyncio
async def test_add_fact_logs_audit_entry() -> None:
    """Test that add_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-audit-test",
        user_id="user-456",
        subject="Jane",
        predicate="title",
        object="CEO",
        confidence=0.90,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
    )

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="new-uuid"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_client

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-123"

            await memory.add_fact(fact)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == "user-456"
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.SEMANTIC
            assert call_kwargs["memory_id"] == "fact-audit-test"
            assert call_kwargs["suppress_errors"] is True


@pytest.mark.asyncio
async def test_invalidate_fact_logs_audit_entry() -> None:
    """Test that invalidate_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"updated": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-456"

            await memory.invalidate_fact(
                user_id="user-456",
                fact_id="fact-123",
                reason="outdated",
            )

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.INVALIDATE
            assert call_kwargs["memory_type"] == MemoryType.SEMANTIC


@pytest.mark.asyncio
async def test_delete_fact_logs_audit_entry() -> None:
    """Test that delete_fact logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType

    memory = SemanticMemory()
    mock_client = MagicMock()
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.semantic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-789"

            await memory.delete_fact(user_id="user-456", fact_id="fact-123")

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.DELETE
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_add_fact_logs_audit_entry -v`
Expected: FAIL (log_memory_operation not called or not imported)

**Step 3: Write minimal implementation**

Modify `backend/src/memory/semantic.py`:

1. Add import at top after other imports:
```python
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
```

2. Add audit logging to `add_fact` method, after the successful storage (before the final return):
```python
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
```

3. Add audit logging to `invalidate_fact` method, after successful invalidation:
```python
            # Audit log the invalidation
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.INVALIDATE,
                memory_type=MemoryType.SEMANTIC,
                memory_id=fact_id,
                metadata={"reason": reason},
                suppress_errors=True,
            )
```

4. Add audit logging to `delete_fact` method, after successful deletion:
```python
            # Audit log the deletion
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.DELETE,
                memory_type=MemoryType.SEMANTIC,
                memory_id=fact_id,
                suppress_errors=True,
            )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_semantic_memory.py::test_add_fact_logs_audit_entry tests/test_semantic_memory.py::test_invalidate_fact_logs_audit_entry tests/test_semantic_memory.py::test_delete_fact_logs_audit_entry -v`
Expected: All PASS

**Step 5: Run mypy**

Run: `cd backend && mypy src/memory/semantic.py --strict`
Expected: Success

**Step 6: Commit**

```bash
git add backend/src/memory/semantic.py backend/tests/test_semantic_memory.py
git commit -m "feat(semantic): add audit logging to SemanticMemory operations"
```

---

## Task 6: Add Audit Logging to EpisodicMemory

**Files:**
- Modify: `backend/src/memory/episodic.py`
- Modify: `backend/tests/test_episodic_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_episodic_memory.py`:

```python
@pytest.mark.asyncio
async def test_store_episode_logs_audit_entry() -> None:
    """Test that store_episode logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType
    from src.memory.episodic import Episode, EpisodicMemory

    now = datetime.now(UTC)
    episode = Episode(
        id="ep-audit-test",
        user_id="user-456",
        event_type="meeting",
        content="Met with client",
        participants=["John"],
        occurred_at=now,
        recorded_at=now,
        context={},
    )

    memory = EpisodicMemory()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-uuid"))

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        with patch("src.memory.episodic.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-ep-123"

            await memory.store_episode(episode)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["user_id"] == "user-456"
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.EPISODIC
            assert call_kwargs["suppress_errors"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_episodic_memory.py::test_store_episode_logs_audit_entry -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `backend/src/memory/episodic.py`:

1. Add import:
```python
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
```

2. Add audit logging to `store_episode` after successful storage:
```python
            # Audit log the creation
            await log_memory_operation(
                user_id=episode.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.EPISODIC,
                memory_id=episode.id,
                metadata={"event_type": episode.event_type},
                suppress_errors=True,
            )

            return episode.id
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_episodic_memory.py::test_store_episode_logs_audit_entry -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/episodic.py backend/tests/test_episodic_memory.py
git commit -m "feat(episodic): add audit logging to EpisodicMemory operations"
```

---

## Task 7: Add Audit Logging to ProceduralMemory

**Files:**
- Modify: `backend/src/memory/procedural.py`
- Modify: `backend/tests/test_procedural_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_procedural_memory.py`:

```python
@pytest.mark.asyncio
async def test_create_workflow_logs_audit_entry() -> None:
    """Test that create_workflow logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType
    from src.memory.procedural import ProceduralMemory, Workflow

    now = datetime.now(UTC)
    workflow = Workflow(
        id="wf-audit-test",
        user_id="user-456",
        workflow_name="test_workflow",
        description="Test",
        trigger_conditions={},
        steps=[{"action": "test"}],
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=now,
        updated_at=now,
    )

    memory = ProceduralMemory()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "wf-audit-test"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

    with patch("src.memory.procedural.SupabaseClient.get_client", return_value=mock_client):
        with patch("src.memory.procedural.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-wf-123"

            await memory.create_workflow(workflow)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.PROCEDURAL
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_create_workflow_logs_audit_entry -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `backend/src/memory/procedural.py`:

1. Add import:
```python
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
```

2. Add audit logging to `create_workflow` after successful storage:
```python
            # Audit log the creation
            await log_memory_operation(
                user_id=workflow.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROCEDURAL,
                memory_id=workflow.id,
                metadata={"workflow_name": workflow.workflow_name},
                suppress_errors=True,
            )

            return workflow.id
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_procedural_memory.py::test_create_workflow_logs_audit_entry -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/procedural.py backend/tests/test_procedural_memory.py
git commit -m "feat(procedural): add audit logging to ProceduralMemory operations"
```

---

## Task 8: Add Audit Logging to ProspectiveMemory

**Files:**
- Modify: `backend/src/memory/prospective.py`
- Modify: `backend/tests/test_prospective_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_prospective_memory.py`:

```python
@pytest.mark.asyncio
async def test_create_task_logs_audit_entry() -> None:
    """Test that create_task logs an audit entry."""
    from src.memory.audit import MemoryOperation, MemoryType
    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    now = datetime.now(UTC)
    task = ProspectiveTask(
        id="task-audit-test",
        user_id="user-456",
        task="Follow up",
        description="Follow up with client",
        trigger_type=TriggerType.TIME,
        trigger_config={"due_at": now.isoformat()},
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        related_goal_id=None,
        related_lead_id=None,
        completed_at=None,
        created_at=now,
    )

    memory = ProspectiveMemory()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": "task-audit-test"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

    with patch("src.memory.prospective.SupabaseClient.get_client", return_value=mock_client):
        with patch("src.memory.prospective.log_memory_operation", new_callable=AsyncMock) as mock_log:
            mock_log.return_value = "audit-task-123"

            await memory.create_task(task)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["operation"] == MemoryOperation.CREATE
            assert call_kwargs["memory_type"] == MemoryType.PROSPECTIVE
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_create_task_logs_audit_entry -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `backend/src/memory/prospective.py`:

1. Add import:
```python
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
```

2. Add audit logging to `create_task` after successful storage:
```python
            # Audit log the creation
            await log_memory_operation(
                user_id=task.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROSPECTIVE,
                memory_id=task.id,
                metadata={"task": task.task, "trigger_type": task.trigger_type.value},
                suppress_errors=True,
            )

            return task.id
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prospective_memory.py::test_create_task_logs_audit_entry -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/prospective.py backend/tests/test_prospective_memory.py
git commit -m "feat(prospective): add audit logging to ProspectiveMemory operations"
```

---

## Task 9: Create Audit Log API Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/test_api_memory.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_api_memory.py`:

```python
def test_audit_log_endpoint_returns_entries(
    test_client: TestClient,
) -> None:
    """Test that audit log endpoint returns entries for current user."""
    from src.memory.audit import MemoryAuditLogger

    with patch.object(MemoryAuditLogger, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = [
            {
                "id": "audit-1",
                "user_id": "test-user-123",
                "operation": "create",
                "memory_type": "semantic",
                "memory_id": "fact-123",
                "metadata": {},
                "created_at": "2026-02-02T00:00:00+00:00",
            }
        ]

        response = test_client.get("/api/v1/memory/audit")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "audit-1"


def test_audit_log_endpoint_filters_by_operation(
    test_client: TestClient,
) -> None:
    """Test that audit log endpoint accepts operation filter."""
    from src.memory.audit import MemoryAuditLogger, MemoryOperation

    with patch.object(MemoryAuditLogger, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = []

        response = test_client.get("/api/v1/memory/audit?operation=create")

    assert response.status_code == 200
    # Verify the filter was passed to query
    mock_query.assert_called_once()
    call_kwargs = mock_query.call_args.kwargs
    assert call_kwargs["operation"] == MemoryOperation.CREATE


def test_audit_log_endpoint_filters_by_memory_type(
    test_client: TestClient,
) -> None:
    """Test that audit log endpoint accepts memory_type filter."""
    from src.memory.audit import MemoryAuditLogger, MemoryType

    with patch.object(MemoryAuditLogger, "query", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = []

        response = test_client.get("/api/v1/memory/audit?memory_type=semantic")

    assert response.status_code == 200
    call_kwargs = mock_query.call_args.kwargs
    assert call_kwargs["memory_type"] == MemoryType.SEMANTIC
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api_memory.py::test_audit_log_endpoint_returns_entries -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/memory.py`:

1. Add imports at top:
```python
from src.memory.audit import MemoryAuditLogger, MemoryOperation, MemoryType
```

2. Add response model after existing models:
```python
class AuditLogEntry(BaseModel):
    """A single audit log entry."""

    id: str
    user_id: str
    operation: str
    memory_type: str
    memory_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Paginated response for audit log queries."""

    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_more: bool
```

3. Add endpoint at end of file:
```python
@router.get("/audit", response_model=AuditLogResponse)
async def query_audit_log(
    current_user: CurrentUser,
    operation: Literal["create", "update", "delete", "query", "invalidate"] | None = Query(
        None, description="Filter by operation type"
    ),
    memory_type: Literal["episodic", "semantic", "procedural", "prospective"] | None = Query(
        None, description="Filter by memory type"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Results per page"),
) -> AuditLogResponse:
    """Query the memory audit log.

    Returns audit log entries for the current user. Admins can see
    all entries via the admin audit endpoint.

    Args:
        current_user: Authenticated user.
        operation: Optional filter by operation type.
        memory_type: Optional filter by memory type.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated audit log entries.
    """
    offset = (page - 1) * page_size

    audit_logger = MemoryAuditLogger()

    # Convert string filters to enums
    op_filter = MemoryOperation(operation) if operation else None
    mt_filter = MemoryType(memory_type) if memory_type else None

    # Query with one extra to determine has_more
    results = await audit_logger.query(
        user_id=current_user.id,
        operation=op_filter,
        memory_type=mt_filter,
        limit=page_size + 1,
        offset=offset,
    )

    has_more = len(results) > page_size
    results = results[:page_size]

    items = [
        AuditLogEntry(
            id=r["id"],
            user_id=r["user_id"],
            operation=r["operation"],
            memory_type=r["memory_type"],
            memory_id=r.get("memory_id"),
            metadata=r.get("metadata") or {},
            created_at=datetime.fromisoformat(r["created_at"]),
        )
        for r in results
    ]

    logger.info(
        "Audit log queried",
        extra={
            "user_id": current_user.id,
            "operation_filter": operation,
            "memory_type_filter": memory_type,
            "results_count": len(items),
        },
    )

    return AuditLogResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=has_more,
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_memory.py::test_audit_log_endpoint_returns_entries tests/test_api_memory.py::test_audit_log_endpoint_filters_by_operation tests/test_api_memory.py::test_audit_log_endpoint_filters_by_memory_type -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/test_api_memory.py
git commit -m "feat(api): add /memory/audit endpoint for querying audit logs"
```

---

## Task 10: Export Audit Module from Memory Package

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Verify current exports don't include audit module**

Run: `cd backend && python -c "from src.memory import MemoryAuditLogger" 2>&1 | head -1`
Expected: ImportError

**Step 2: Add exports to __init__.py**

Add to `backend/src/memory/__init__.py`:

1. Add import after existing imports:
```python
from src.memory.audit import (
    AuditLogEntry,
    MemoryAuditLogger,
    MemoryOperation,
    MemoryType,
    log_memory_operation,
)
```

2. Add to `__all__`:
```python
    # Memory Audit
    "AuditLogEntry",
    "MemoryAuditLogger",
    "MemoryOperation",
    "MemoryType",
    "log_memory_operation",
```

**Step 3: Verify exports work**

Run: `cd backend && python -c "from src.memory import MemoryAuditLogger, log_memory_operation; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add backend/src/memory/__init__.py
git commit -m "feat(memory): export audit module from memory package"
```

---

## Task 11: Run Full Quality Gates

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run mypy**

Run: `cd backend && mypy src/ --strict`
Expected: Success: no issues found

**Step 3: Run ruff check**

Run: `cd backend && ruff check src/`
Expected: No warnings

**Step 4: Run ruff format check**

Run: `cd backend && ruff format src/ --check`
Expected: All files formatted correctly

**Step 5: Commit any fixes if needed, then create final commit**

```bash
git add -A
git commit -m "chore: final quality gate verification for US-211"
```

---

## Summary

This plan implements US-211: Memory Audit Log with the following deliverables:

1. **SQL Migration** - `memory_audit_log` table with indexes and RLS policies
2. **AuditLogError** - Custom exception for audit failures
3. **MemoryAuditLogger** - Core class for logging and querying audit entries
4. **log_memory_operation()** - Convenience function with error suppression
5. **Audit integration** - Added to SemanticMemory, EpisodicMemory, ProceduralMemory, ProspectiveMemory
6. **API Endpoint** - `GET /api/v1/memory/audit` with filtering and pagination
7. **Package exports** - All audit types exported from memory module

Key design decisions:
- **Error suppression**: Audit failures don't break main operations (suppress_errors=True)
- **No sensitive content**: Only IDs and operation metadata are logged
- **User isolation**: RLS policies ensure users only see their own logs
- **Admin access**: Admins can query all logs via RLS policy
