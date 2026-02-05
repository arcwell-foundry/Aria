# [Skill Audit Trail] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an immutable blockchain-style audit trail for all skill executions with cryptographic hash chain integrity verification.

**Architecture:** Hash-chained audit log where each entry contains the hash of the previous entry, creating an immutable chain. Any tampering breaks the chain. Uses SHA256 for hashing and stores entries in Supabase with RLS for user isolation.

**Tech Stack:** Python 3.11+, Supabase (PostgreSQL), hashlib (SHA256), pytest

---

## Task 1: Create Database Migration

**Files:**
- Create: `supabase/migrations/20260205000000_create_skill_audit_log.sql`

**Step 1: Write the migration file**

```sql
-- Migration: Create skill_audit_log table
-- US-527: Skill Audit Trail

-- Create skill_audit_log table with hash chain for tamper evidence
CREATE TABLE skill_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    tenant_id UUID,  -- Future: for multi-tenant support
    skill_id TEXT NOT NULL,
    skill_path TEXT NOT NULL,
    skill_trust_level TEXT NOT NULL,
    task_id UUID,  -- Nullable: not all executions have task IDs
    agent_id TEXT,  -- Nullable: which agent triggered the skill
    trigger_reason TEXT NOT NULL,  -- Why this skill was invoked
    data_classes_requested TEXT[] NOT NULL,  -- Data classes skill wanted
    data_classes_granted TEXT[] NOT NULL,  -- Data classes actually allowed
    data_redacted BOOLEAN DEFAULT FALSE NOT NULL,  -- Was sensitive data redacted?
    tokens_used TEXT[] DEFAULT '{}',  -- Token counts per model used
    input_hash TEXT NOT NULL,  -- Hash of input data for integrity
    output_hash TEXT,  -- Hash of output data (null if failed)
    execution_time_ms INT,  -- Execution duration in milliseconds
    success BOOLEAN NOT NULL,  -- Did execution succeed?
    error TEXT,  -- Error message if failed
    sandbox_config JSONB,  -- Sandbox settings used
    security_flags TEXT[] DEFAULT '{}',  -- Any security concerns flagged
    previous_hash TEXT NOT NULL,  -- Hash of previous entry for chain
    entry_hash TEXT NOT NULL  -- Hash of this entry (includes previous_hash)
);

-- Index for user-based queries (most common access pattern)
CREATE INDEX idx_skill_audit_user_time ON skill_audit_log(user_id, timestamp DESC);

-- Index for skill_id filtering
CREATE INDEX idx_skill_audit_skill_id ON skill_audit_log(skill_id);

-- Index for hash chain verification
CREATE INDEX idx_skill_audit_entry_hash ON skill_audit_log(entry_hash);

-- Enable RLS
ALTER TABLE skill_audit_log ENABLE ROW LEVEL SECURITY;

-- Users can only read their own audit logs
CREATE POLICY "Users can read own skill audit logs"
    ON skill_audit_log
    FOR SELECT
    USING (user_id = auth.uid());

-- Service role can insert audit logs
CREATE POLICY "Service can insert skill audit logs"
    ON skill_audit_log
    FOR INSERT
    WITH CHECK (true);

-- Service role can read audit logs (for backend admin queries)
CREATE POLICY "Service can read skill audit logs"
    ON skill_audit_log
    FOR SELECT
    USING (auth.role() = 'service_role');

-- Add comment for documentation
COMMENT ON TABLE skill_audit_log IS 'Immutable audit trail for skill executions with hash chain integrity. Tampering breaks the cryptographic chain.';
```

**Step 2: Run the migration**

Run: `supabase db push`
Expected: Migration applied successfully, table created

**Step 3: Verify table exists**

Run: `supabase db inspect`
Expected: Table `skill_audit_log` appears in schema

**Step 4: Commit**

```bash
git add supabase/migrations/20260205000000_create_skill_audit_log.sql
git commit -m "feat(skill-audit): create skill_audit_log table with hash chain"
```

---

## Task 2: Create SkillAuditEntry Dataclass

**Files:**
- Create: `backend/src/security/skill_audit.py`

**Step 1: Write the failing test**

```python
"""Tests for skill_audit module."""

import pytest
from dataclasses import dataclass


def test_skill_audit_entry_dataclass_exists() -> None:
    """Test SkillAuditEntry dataclass can be imported."""
    from src.security.skill_audit import SkillAuditEntry

    assert SkillAuditEntry is not None


def test_skill_audit_entry_has_required_fields() -> None:
    """Test SkillAuditEntry has all required fields."""
    from src.security.skill_audit import SkillAuditEntry

    entry = SkillAuditEntry(
        user_id="user-123",
        skill_id="skill-456",
        skill_path="/skills/pdf",
        skill_trust_level="core",
        trigger_reason="user_request",
        data_classes_requested=["public", "internal"],
        data_classes_granted=["public", "internal"],
        input_hash="abc123",
        previous_hash="def456",
        entry_hash="computed_hash",
        success=True,
    )

    assert entry.user_id == "user-123"
    assert entry.skill_id == "skill-456"
    assert entry.skill_path == "/skills/pdf"
    assert entry.skill_trust_level == "core"
    assert entry.trigger_reason == "user_request"
    assert entry.data_classes_requested == ["public", "internal"]
    assert entry.data_classes_granted == ["public", "internal"]
    assert entry.input_hash == "abc123"
    assert entry.previous_hash == "def456"
    assert entry.entry_hash == "computed_hash"
    assert entry.success is True


def test_skill_audit_entry_optional_fields_default() -> None:
    """Test SkillAuditEntry optional fields have sensible defaults."""
    from src.security.skill_audit import SkillAuditEntry

    entry = SkillAuditEntry(
        user_id="user-123",
        skill_id="skill-456",
        skill_path="/skills/pdf",
        skill_trust_level="core",
        trigger_reason="user_request",
        data_classes_requested=["public"],
        data_classes_granted=["public"],
        input_hash="abc123",
        previous_hash="def456",
        entry_hash="computed_hash",
        success=True,
    )

    assert entry.tenant_id is None
    assert entry.task_id is None
    assert entry.agent_id is None
    assert entry.data_redacted is False
    assert entry.tokens_used == []
    assert entry.output_hash is None
    assert entry.execution_time_ms is None
    assert entry.error is None
    assert entry.sandbox_config is None
    assert entry.security_flags == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.security.skill_audit'"

**Step 3: Write minimal implementation**

Create `backend/src/security/skill_audit.py`:

```python
"""Skill audit trail system for ARIA.

Provides immutable, hash-chained audit logging for all skill executions.
Any tampering with audit records breaks the cryptographic chain.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.core.exceptions import DatabaseError
from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class SkillAuditEntry:
    """Single audit entry for a skill execution.

    Each entry contains a hash of the previous entry, creating an immutable
    chain. Any modification to historical records breaks the chain.

    Attributes:
        user_id: User who triggered the skill execution.
        tenant_id: Optional tenant ID for multi-tenant scenarios.
        skill_id: Unique identifier for the skill.
        skill_path: File path or identifier for the skill.
        skill_trust_level: Trust level of the skill (core, verified, community, user).
        task_id: Optional task UUID this execution is part of.
        agent_id: Optional agent ID that triggered the skill.
        trigger_reason: Why this skill was invoked.
        data_classes_requested: Data classes the skill requested access to.
        data_classes_granted: Data classes actually granted to the skill.
        data_redacted: Whether sensitive data was redacted before passing to skill.
        tokens_used: List of token counts per model used.
        input_hash: SHA256 hash of input data for integrity verification.
        output_hash: SHA256 hash of output data (null if execution failed).
        execution_time_ms: Execution duration in milliseconds.
        success: Whether the skill execution succeeded.
        error: Error message if execution failed.
        sandbox_config: Sandbox settings applied during execution.
        security_flags: Any security concerns flagged during execution.
        previous_hash: Hash of the previous entry in the chain.
        entry_hash: SHA256 hash of this entry (includes previous_hash).
    """

    user_id: str
    skill_id: str
    skill_path: str
    skill_trust_level: str
    trigger_reason: str
    data_classes_requested: list[str]
    data_classes_granted: list[str]
    input_hash: str
    previous_hash: str
    entry_hash: str
    success: bool
    tenant_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    data_redacted: bool = False
    tokens_used: list[str] = field(default_factory=list)
    output_hash: str | None = None
    execution_time_ms: int | None = None
    error: str | None = None
    sandbox_config: dict[str, Any] | None = None
    security_flags: list[str] = field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add SkillAuditEntry dataclass"
```

---

## Task 3: Implement Hash Computation

**Files:**
- Modify: `backend/src/security/skill_audit.py` (add _compute_hash method to SkillAuditService)
- Test: `backend/tests/test_skill_audit.py` (add tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestHashComputation:
    """Tests for hash computation logic."""

    def test_compute_hash_creates_sha256(self) -> None:
        """Test _compute_hash creates a valid SHA256 hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {
            "skill_id": "test-skill",
            "user_id": "user-123",
            "success": True,
        }
        previous_hash = "prev-hash"

        result = service._compute_hash(entry_dict, previous_hash)

        # SHA256 hashes are 64 hex characters
        assert len(result) == 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_hash_is_deterministic(self) -> None:
        """Test same input produces same hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {
            "skill_id": "test-skill",
            "user_id": "user-123",
            "success": True,
        }
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(entry_dict, previous_hash)
        hash2 = service._compute_hash(entry_dict, previous_hash)

        assert hash1 == hash2

    def test_compute_hash_different_input_different_hash(self) -> None:
        """Test different input produces different hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict1 = {"skill_id": "skill-a", "user_id": "user-123", "success": True}
        entry_dict2 = {"skill_id": "skill-b", "user_id": "user-123", "success": True}
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(entry_dict1, previous_hash)
        hash2 = service._compute_hash(entry_dict2, previous_hash)

        assert hash1 != hash2

    def test_compute_hash_includes_previous_hash(self) -> None:
        """Test hash changes when previous_hash changes."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {"skill_id": "test-skill", "user_id": "user-123", "success": True}

        hash1 = service._compute_hash(entry_dict, "prev-hash-1")
        hash2 = service._compute_hash(entry_dict, "prev-hash-2")

        assert hash1 != hash2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestHashComputation -v`
Expected: FAIL with "AttributeError: 'SkillAuditService' object has no attribute '_compute_hash'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/skill_audit.py` (after the dataclass):

```python
class SkillAuditService:
    """Service for managing skill audit trail with hash chain integrity."""

    def __init__(self, supabase_client: Client | None = None) -> None:
        """Initialize the audit service.

        Args:
            supabase_client: Optional Supabase client. If None, uses default.
        """
        from src.db.supabase import SupabaseClient

        self._client = supabase_client or SupabaseClient.get_client()

    def _compute_hash(self, entry_data: dict[str, Any], previous_hash: str) -> str:
        """Compute SHA256 hash of entry data including previous hash.

        This creates the cryptographic link between entries in the chain.

        Args:
            entry_data: Dictionary of entry data to hash.
            previous_hash: Hash of the previous entry in the chain.

        Returns:
            64-character hex SHA256 hash.
        """
        # Create deterministic string representation
        # Sort keys for consistent ordering
        canonical = json.dumps(entry_data, sort_keys=True, default=str)
        # Include previous hash to chain entries together
        combined = f"{canonical}:{previous_hash}"
        # Return SHA256 as hex string
        return hashlib.sha256(combined.encode()).hexdigest()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestHashComputation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add hash computation method"
```

---

## Task 4: Implement get_latest_hash

**Files:**
- Modify: `backend/src/security/skill_audit.py` (add get_latest_hash method)
- Test: `backend/tests/test_skill_audit.py` (add tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestGetLatestHash:
    """Tests for get_latest_hash method."""

    @pytest.mark.asyncio
    async def test_returns_zero_hash_for_new_user(self) -> None:
        """Test returns zero hash when user has no audit entries."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []  # No entries
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.single.return_value.execute = (
            AsyncMock(return_value=mock_response)
        )

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_latest_hash("new-user-123")

        # Zero hash for genesis entry
        assert result == "0" * 64

    @pytest.mark.asyncio
    async def test_returns_last_entry_hash(self) -> None:
        """Test returns entry_hash of most recent entry."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        expected_hash = "a" * 64

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"entry_hash": expected_hash}]
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.single.return_value.execute = (
            AsyncMock(return_value=mock_response)
        )

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_latest_hash("user-123")

        assert result == expected_hash

    @pytest.mark.asyncio
    async def test_queries_correct_table_and_order(self) -> None:
        """Test queries skill_audit_log ordered by timestamp DESC."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_execute = AsyncMock(return_value=mock_response)
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.single.return_value.execute = (
            mock_execute
        )

        service = SkillAuditService(supabase_client=mock_client)
        await service.get_latest_hash("user-456")

        # Verify table name
        mock_client.table.assert_called_once_with("skill_audit_log")
        # Verify ordering
        mock_client.table.return_value.select.return_value.order.assert_called_once_with(
            "timestamp", desc=True
        )
        # Verify limit
        mock_client.table.return_value.select.return_value.order.return_value.limit.assert_called_once_with(
            1
        )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestGetLatestHash -v`
Expected: FAIL with "AttributeError: 'SkillAuditService' object has no attribute 'get_latest_hash'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/skill_audit.py` in SkillAuditService class:

```python
    async def get_latest_hash(self, user_id: str) -> str:
        """Get the entry_hash of the most recent audit entry for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            The entry_hash of the most recent entry, or zero hash if none exist.
        """
        try:
            response = (
                self._client.table("skill_audit_log")
                .select("entry_hash")
                .eq("user_id", user_id)
                .order("timestamp", desc=True)
                .limit(1)
                .single()
                .execute()
            )

            if response.data and response.data.get("entry_hash"):
                return str(response.data["entry_hash"])

            # No entries: return zero hash for genesis block
            return "0" * 64

        except Exception as e:
            logger.warning(
                "Failed to fetch latest hash, using zero hash",
                extra={"user_id": user_id, "error": str(e)},
            )
            return "0" * 64
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestGetLatestHash -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add get_latest_hash method"
```

---

## Task 5: Implement log_execution

**Files:**
- Modify: `backend/src/security/skill_audit.py` (add log_execution method)
- Test: `backend/tests/test_skill_audit.py` (add tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestLogExecution:
    """Tests for log_execution method."""

    @pytest.mark.asyncio
    async def test_logs_entry_to_database(self) -> None:
        """Test entry is saved to database."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditEntry, SkillAuditService

        entry = SkillAuditEntry(
            user_id="user-123",
            skill_id="skill-456",
            skill_path="/skills/test",
            skill_trust_level="core",
            trigger_reason="user_request",
            data_classes_requested=["public"],
            data_classes_granted=["public"],
            input_hash="input123",
            previous_hash="0" * 64,
            entry_hash="entry456",
            success=True,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "audit-id-123"}]
        mock_client.table.return_value.insert.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        service = SkillAuditService(supabase_client=mock_client)
        await service.log_execution(entry)

        # Verify table name
        mock_client.table.assert_called_once_with("skill_audit_log")
        # Verify insert was called
        mock_client.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_entry_hash_matches_computation(self) -> None:
        """Test logged entry has correct entry_hash computed by service."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditEntry, SkillAuditService

        # Create entry with a known hash
        service = SkillAuditService()
        entry_data = {
            "user_id": "user-123",
            "skill_id": "skill-456",
            "skill_path": "/skills/test",
            "skill_trust_level": "core",
            "trigger_reason": "user_request",
            "data_classes_requested": ["public"],
            "data_classes_granted": ["public"],
            "input_hash": "input123",
            "success": True,
        }
        previous_hash = "0" * 64
        expected_hash = service._compute_hash(entry_data, previous_hash)

        entry = SkillAuditEntry(
            **entry_data,
            previous_hash=previous_hash,
            entry_hash=expected_hash,
        )

        insert_args = None

        def capture_insert(data):
            nonlocal insert_args
            insert_args = data
            mock_response = MagicMock()
            mock_response.data = [{"id": "audit-id"}]
            return MagicMock(execute=AsyncMock(return_value=mock_response))

        mock_client = MagicMock()
        mock_client.table.return_value.insert = capture_insert

        service2 = SkillAuditService(supabase_client=mock_client)
        await service2.log_execution(entry)

        assert insert_args is not None
        assert insert_args["entry_hash"] == expected_hash
        assert insert_args["previous_hash"] == previous_hash

    @pytest.mark.asyncio
    async def test_includes_all_entry_fields(self) -> None:
        """Test all entry fields are included in database record."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditEntry, SkillAuditService

        entry = SkillAuditEntry(
            user_id="user-123",
            tenant_id="tenant-456",
            skill_id="skill-789",
            skill_path="/skills/test",
            skill_trust_level="verified",
            task_id="task-123",
            agent_id="agent-456",
            trigger_reason="automation",
            data_classes_requested=["public", "internal"],
            data_classes_granted=["public"],
            data_redacted=True,
            tokens_used=["1000", "500"],
            input_hash="input123",
            output_hash="output456",
            execution_time_ms=1500,
            success=True,
            error=None,
            sandbox_config={"timeout": 30},
            security_flags=["large_output"],
            previous_hash="0" * 64,
            entry_hash="hash123",
        )

        insert_args = None

        def capture_insert(data):
            nonlocal insert_args
            insert_args = data
            mock_response = MagicMock()
            mock_response.data = [{"id": "audit-id"}]
            return MagicMock(execute=AsyncMock(return_value=mock_response))

        mock_client = MagicMock()
        mock_client.table.return_value.insert = capture_insert

        service = SkillAuditService(supabase_client=mock_client)
        await service.log_execution(entry)

        assert insert_args is not None
        assert insert_args["user_id"] == "user-123"
        assert insert_args["tenant_id"] == "tenant-456"
        assert insert_args["skill_id"] == "skill-789"
        assert insert_args["skill_path"] == "/skills/test"
        assert insert_args["skill_trust_level"] == "verified"
        assert insert_args["task_id"] == "task-123"
        assert insert_args["agent_id"] == "agent-456"
        assert insert_args["trigger_reason"] == "automation"
        assert insert_args["data_classes_requested"] == ["public", "internal"]
        assert insert_args["data_classes_granted"] == ["public"]
        assert insert_args["data_redacted"] is True
        assert insert_args["tokens_used"] == ["1000", "500"]
        assert insert_args["input_hash"] == "input123"
        assert insert_args["output_hash"] == "output456"
        assert insert_args["execution_time_ms"] == 1500
        assert insert_args["success"] is True
        assert insert_args["error"] is None
        assert insert_args["sandbox_config"] == {"timeout": 30}
        assert insert_args["security_flags"] == ["large_output"]
        assert insert_args["previous_hash"] == "0" * 64
        assert insert_args["entry_hash"] == "hash123"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestLogExecution -v`
Expected: FAIL with "AttributeError: 'SkillAuditService' object has no attribute 'log_execution'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/skill_audit.py` in SkillAuditService class:

```python
    async def log_execution(self, entry: SkillAuditEntry) -> None:
        """Log a skill execution to the audit trail.

        Args:
            entry: The audit entry to log.

        Raises:
            DatabaseError: If logging fails.
        """
        try:
            # Convert dataclass to dict for database insertion
            data = {
                "user_id": entry.user_id,
                "tenant_id": entry.tenant_id,
                "skill_id": entry.skill_id,
                "skill_path": entry.skill_path,
                "skill_trust_level": entry.skill_trust_level,
                "task_id": entry.task_id,
                "agent_id": entry.agent_id,
                "trigger_reason": entry.trigger_reason,
                "data_classes_requested": entry.data_classes_requested,
                "data_classes_granted": entry.data_classes_granted,
                "data_redacted": entry.data_redacted,
                "tokens_used": entry.tokens_used,
                "input_hash": entry.input_hash,
                "output_hash": entry.output_hash,
                "execution_time_ms": entry.execution_time_ms,
                "success": entry.success,
                "error": entry.error,
                "sandbox_config": entry.sandbox_config,
                "security_flags": entry.security_flags,
                "previous_hash": entry.previous_hash,
                "entry_hash": entry.entry_hash,
            }

            self._client.table("skill_audit_log").insert(data).execute()

            logger.info(
                "Skill execution logged",
                extra={
                    "user_id": entry.user_id,
                    "skill_id": entry.skill_id,
                    "success": entry.success,
                },
            )

        except Exception as e:
            logger.exception(
                "Failed to log skill execution",
                extra={"user_id": entry.user_id, "skill_id": entry.skill_id},
            )
            raise DatabaseError(f"Failed to log skill execution: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestLogExecution -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add log_execution method"
```

---

## Task 6: Implement verify_chain

**Files:**
- Modify: `backend/src/security/skill_audit.py` (add verify_chain method)
- Test: `backend/tests/test_skill_audit.py` (add tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestVerifyChain:
    """Tests for hash chain verification."""

    @pytest.mark.asyncio
    async def test_verify_chain_passes_with_valid_chain(self) -> None:
        """Test verification passes when chain is intact."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        # Build a valid chain: entry1 -> entry2 -> entry3
        # Each entry's entry_hash is computed from its data + previous entry's entry_hash
        service = SkillAuditService()
        zero_hash = "0" * 64

        # Entry 1 (genesis)
        entry1_data = {"id": "1", "skill_id": "skill1", "user_id": "user123"}
        entry1_hash = service._compute_hash(entry1_data, zero_hash)

        # Entry 2
        entry2_data = {"id": "2", "skill_id": "skill2", "user_id": "user123"}
        entry2_hash = service._compute_hash(entry2_data, entry1_hash)

        # Entry 3
        entry3_data = {"id": "3", "skill_id": "skill3", "user_id": "user123"}
        entry3_hash = service._compute_hash(entry3_data, entry2_hash)

        mock_entries = [
            {
                "id": "1",
                "skill_id": "skill1",
                "user_id": "user123",
                "previous_hash": zero_hash,
                "entry_hash": entry1_hash,
            },
            {
                "id": "2",
                "skill_id": "skill2",
                "user_id": "user123",
                "previous_hash": entry1_hash,
                "entry_hash": entry2_hash,
            },
            {
                "id": "3",
                "skill_id": "skill3",
                "user_id": "user123",
                "previous_hash": entry2_hash,
                "entry_hash": entry3_hash,
            },
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = mock_entries
        mock_client.table.return_value.select.return_value.order.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        service2 = SkillAuditService(supabase_client=mock_client)
        result = await service2.verify_chain("user123")

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_chain_fails_with_tampered_entry(self) -> None:
        """Test verification fails when an entry is tampered."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        zero_hash = "0" * 64

        # Valid chain
        entry1_hash = service._compute_hash({"id": "1"}, zero_hash)
        entry2_hash = service._compute_hash({"id": "2"}, entry1_hash)

        # Tampered entry: previous_hash doesn't match actual previous entry_hash
        mock_entries = [
            {
                "id": "1",
                "previous_hash": zero_hash,
                "entry_hash": entry1_hash,
            },
            {
                "id": "2",
                "previous_hash": "tampered" * 8,  # Wrong!
                "entry_hash": entry2_hash,
            },
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = mock_entries
        mock_client.table.return_value.select.return_value.order.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        service2 = SkillAuditService(supabase_client=mock_client)
        result = await service2.verify_chain("user123")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_chain_fails_with_broken_hash(self) -> None:
        """Test verification fails when entry_hash doesn't match computed."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        zero_hash = "0" * 64

        mock_entries = [
            {
                "id": "1",
                "previous_hash": zero_hash,
                "entry_hash": "wrong" * 16,  # Doesn't match computed hash!
            },
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = mock_entries
        mock_client.table.return_value.select.return_value.order.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.verify_chain("user123")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_chain_returns_true_for_empty_chain(self) -> None:
        """Test verification passes when user has no entries."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.order.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.verify_chain("user123")

        assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestVerifyChain -v`
Expected: FAIL with "AttributeError: 'SkillAuditService' object has no attribute 'verify_chain'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/skill_audit.py` in SkillAuditService class:

```python
    async def verify_chain(self, user_id: str) -> bool:
        """Verify the integrity of a user's audit log hash chain.

        Checks that each entry's previous_hash matches the entry_hash of the
        immediately preceding entry. Any mismatch indicates tampering.

        Args:
            user_id: The user's UUID.

        Returns:
            True if chain is valid, False if tampering detected.
        """
        try:
            response = (
                self._client.table("skill_audit_log")
                .select("*")
                .eq("user_id", user_id)
                .order("timestamp", desc=False)  # Oldest first
                .execute()
            )

            entries = response.data

            # Empty chain is valid
            if not entries:
                return True

            # Verify each link in the chain
            previous_hash = "0" * 64  # Genesis block has zero previous hash

            for entry in entries:
                # Check previous_hash matches
                if entry.get("previous_hash") != previous_hash:
                    logger.warning(
                        "Hash chain broken: previous_hash mismatch",
                        extra={
                            "user_id": user_id,
                            "entry_id": entry.get("id"),
                            "expected": previous_hash,
                            "actual": entry.get("previous_hash"),
                        },
                    )
                    return False

                # Recompute hash to verify entry wasn't modified
                entry_data = {
                    k: v
                    for k, v in entry.items()
                    if k not in ["id", "timestamp", "entry_hash", "previous_hash"]
                }
                computed_hash = self._compute_hash(entry_data, previous_hash)

                if entry.get("entry_hash") != computed_hash:
                    logger.warning(
                        "Hash chain broken: entry_hash mismatch",
                        extra={
                            "user_id": user_id,
                            "entry_id": entry.get("id"),
                            "expected": computed_hash,
                            "actual": entry.get("entry_hash"),
                        },
                    )
                    return False

                # Chain continues
                previous_hash = entry.get("entry_hash", "")

            return True

        except Exception as e:
            logger.exception("Failed to verify hash chain", extra={"user_id": user_id})
            return False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestVerifyChain -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add verify_chain method for tamper detection"
```

---

## Task 7: Implement get_audit_log and get_audit_for_skill

**Files:**
- Modify: `backend/src/security/skill_audit.py` (add query methods)
- Test: `backend/tests/test_skill_audit.py` (add tests)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestQueryMethods:
    """Tests for audit log query methods."""

    @pytest.mark.asyncio
    async def test_get_audit_log_returns_entries(self) -> None:
        """Test get_audit_log returns user's audit entries."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_entries = [
            {
                "id": "1",
                "user_id": "user-123",
                "skill_id": "skill-a",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "id": "2",
                "user_id": "user-123",
                "skill_id": "skill-b",
                "timestamp": "2024-01-02T00:00:00Z",
            },
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = mock_entries
        mock_client.table.return_value.select.return_value.order.return_value.range.return_value.execute = (
            AsyncMock(return_value=mock_response)
        )

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_audit_log("user-123", limit=10, offset=0)

        assert len(result) == 2
        assert result[0]["skill_id"] == "skill-a"
        assert result[1]["skill_id"] == "skill-b"

    @pytest.mark.asyncio
    async def test_get_audit_log_applies_limit_and_offset(self) -> None:
        """Test get_audit_log applies pagination."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_range = AsyncMock(return_value=mock_response)
        mock_client.table.return_value.select.return_value.order.return_value.range = mock_range

        service = SkillAuditService(supabase_client=mock_client)
        await service.get_audit_log("user-123", limit=20, offset=40)

        # Verify range was called with correct offset/limit
        mock_range.assert_called_once_with(40, 59)  # offset to offset + limit - 1

    @pytest.mark.asyncio
    async def test_get_audit_for_skill_filters_by_skill_id(self) -> None:
        """Test get_audit_for_skill filters by skill_id."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_entries = [
            {
                "id": "1",
                "user_id": "user-123",
                "skill_id": "pdf",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = mock_entries

        # Track call chain
        mock_eq = AsyncMock(return_value=mock_response)
        mock_order = AsyncMock(return_value=mock_response)
        mock_range = AsyncMock(return_value=mock_response)

        mock_client.table.return_value.select.return_value.eq = mock_eq
        mock_eq.return_value.order = mock_order
        mock_order.return_value.range = mock_range

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_audit_for_skill("user-123", "pdf", limit=10, offset=0)

        # Verify eq was called with skill_id
        mock_eq.assert_called_once_with("skill_id", "pdf")
        assert len(result) == 1
        assert result[0]["skill_id"] == "pdf"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestQueryMethods -v`
Expected: FAIL with "AttributeError: 'SkillAuditService' object has no attribute 'get_audit_log'"

**Step 3: Write minimal implementation**

Add to `backend/src/security/skill_audit.py` in SkillAuditService class:

```python
    async def get_audit_log(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get audit log entries for a user.

        Args:
            user_id: The user's UUID.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of audit entry dictionaries.
        """
        try:
            response = (
                self._client.table("skill_audit_log")
                .select("*")
                .eq("user_id", user_id)
                .order("timestamp", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.exception("Failed to fetch audit log", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch audit log: {e}") from e

    async def get_audit_for_skill(
        self,
        user_id: str,
        skill_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get audit log entries for a specific skill.

        Args:
            user_id: The user's UUID.
            skill_id: The skill identifier to filter by.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of audit entry dictionaries for the specified skill.
        """
        try:
            response = (
                self._client.table("skill_audit_log")
                .select("*")
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .order("timestamp", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.exception(
                "Failed to fetch audit log for skill",
                extra={"user_id": user_id, "skill_id": skill_id},
            )
            raise DatabaseError(f"Failed to fetch audit log for skill: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestQueryMethods -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): add query methods get_audit_log and get_audit_for_skill"
```

---

## Task 8: Update Security Module Exports

**Files:**
- Modify: `backend/src/security/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestModuleExports:
    """Tests for skill_audit module exports."""

    def test_skill_audit_entry_exported(self) -> None:
        """Test SkillAuditEntry is exported from security module."""
        from src.security import SkillAuditEntry

        assert SkillAuditEntry is not None

    def test_skill_audit_service_exported(self) -> None:
        """Test SkillAuditService is exported from security module."""
        from src.security import SkillAuditService

        assert SkillAuditService is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestModuleExports -v`
Expected: FAIL with "ImportError: cannot import name 'SkillAuditEntry' from 'src.security'"

**Step 3: Write minimal implementation**

Edit `backend/src/security/__init__.py`:

```python
"""Security module for ARIA.

Provides data classification, trust levels, sanitization, sandboxing, audit
capabilities, and skill audit trail for the skills integration system.
"""

from src.security.data_classification import (
    ClassifiedData,
    DataClass,
    DataClassifier,
)
from src.security.sandbox import (
    SANDBOX_BY_TRUST,
    SandboxConfig,
    SandboxResult,
    SandboxViolation,
    SkillSandbox,
)
from src.security.sanitization import (
    DataSanitizer,
    LeakageReport,
    TokenMap,
)
from src.security.skill_audit import (
    SkillAuditEntry,
    SkillAuditService,
)
from src.security.trust_levels import (
    TRUST_DATA_ACCESS,
    TRUSTED_SKILL_SOURCES,
    SkillTrustLevel,
    can_access_data,
    determine_trust_level,
)

__all__ = [
    # Data classification
    "ClassifiedData",
    "DataClass",
    "DataClassifier",
    # Trust levels
    "SkillTrustLevel",
    "TRUST_DATA_ACCESS",
    "TRUSTED_SKILL_SOURCES",
    "determine_trust_level",
    "can_access_data",
    # Sanitization
    "TokenMap",
    "LeakageReport",
    "DataSanitizer",
    # Sandbox
    "SandboxConfig",
    "SandboxViolation",
    "SandboxResult",
    "SkillSandbox",
    "SANDBOX_BY_TRUST",
    # Skill audit
    "SkillAuditEntry",
    "SkillAuditService",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestModuleExports -v`
Expected: PASS

**Step 5: Run all skill_audit tests**

Run: `cd backend && pytest tests/test_skill_audit.py -v`
Expected: All 20+ tests PASS

**Step 6: Commit**

```bash
git add backend/src/security/__init__.py backend/tests/test_skill_audit.py
git commit -m "feat(skill-audit): export SkillAuditEntry and SkillAuditService from security module"
```

---

## Task 9: Integration Test for Full Workflow

**Files:**
- Test: `backend/tests/test_skill_audit.py` (add integration test class)

**Step 1: Write the failing test**

Add to `backend/tests/test_skill_audit.py`:

```python
class TestSkillAuditIntegration:
    """Integration tests for full audit workflow."""

    @pytest.mark.asyncio
    async def test_full_audit_workflow_with_chain_verification(self) -> None:
        """Test complete workflow: log entries, verify chain, query logs."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditEntry, SkillAuditService

        service = SkillAuditService()
        zero_hash = "0" * 64

        # Mock database responses
        logged_entries = []

        def mock_insert(data):
            logged_entries.append(data)
            mock_response = MagicMock()
            mock_response.data = [{"id": f"audit-{len(logged_entries)}"}]
            return MagicMock(execute=AsyncMock(return_value=mock_response))

        mock_client = MagicMock()
        mock_client.table.return_value.insert = mock_insert

        # Mock get_latest_hash to return our tracked chain
        async def mock_get_latest_hash(user_id: str) -> str:
            if not logged_entries:
                return zero_hash
            return logged_entries[-1]["entry_hash"]

        # Mock get_audit_log to return logged entries
        async def mock_get_audit_log(user_id: str, limit: int, offset: int) -> list[dict]:
            return list(reversed(logged_entries))  # Return newest first

        service_with_mock = SkillAuditService(supabase_client=mock_client)
        service_with_mock.get_latest_hash = mock_get_latest_hash
        service_with_mock.get_audit_log = mock_get_audit_log

        # Log first entry
        entry1_data = {
            "user_id": "user-123",
            "skill_id": "skill-a",
            "skill_path": "/skills/a",
            "skill_trust_level": "core",
            "trigger_reason": "test",
            "data_classes_requested": ["public"],
            "data_classes_granted": ["public"],
            "input_hash": "input1",
        }
        entry1_hash = service._compute_hash(entry1_data, zero_hash)

        entry1 = SkillAuditEntry(
            **entry1_data,
            previous_hash=zero_hash,
            entry_hash=entry1_hash,
            success=True,
        )
        await service_with_mock.log_execution(entry1)

        # Log second entry
        entry2_data = {
            "user_id": "user-123",
            "skill_id": "skill-b",
            "skill_path": "/skills/b",
            "skill_trust_level": "verified",
            "trigger_reason": "test",
            "data_classes_requested": ["internal"],
            "data_classes_granted": ["internal"],
            "input_hash": "input2",
        }
        entry2_hash = service._compute_hash(entry2_data, entry1_hash)

        entry2 = SkillAuditEntry(
            **entry2_data,
            previous_hash=entry1_hash,
            entry_hash=entry2_hash,
            success=True,
        )
        await service_with_mock.log_execution(entry2)

        # Query logs
        logs = await service_with_mock.get_audit_log("user-123")
        assert len(logs) == 2

        # Verify chain
        # Mock verify_chain's database query
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "1",
                "user_id": "user-123",
                "skill_id": "skill-a",
                "skill_path": "/skills/a",
                "skill_trust_level": "core",
                "trigger_reason": "test",
                "data_classes_requested": ["public"],
                "data_classes_granted": ["public"],
                "input_hash": "input1",
                "previous_hash": zero_hash,
                "entry_hash": entry1_hash,
            },
            {
                "id": "2",
                "user_id": "user-123",
                "skill_id": "skill-b",
                "skill_path": "/skills/b",
                "skill_trust_level": "verified",
                "trigger_reason": "test",
                "data_classes_requested": ["internal"],
                "data_classes_granted": ["internal"],
                "input_hash": "input2",
                "previous_hash": entry1_hash,
                "entry_hash": entry2_hash,
            },
        ]
        mock_client.table.return_value.select.return_value.order.return_value.execute = AsyncMock(
            return_value=mock_response
        )

        is_valid = await service_with_mock.verify_chain("user-123")
        assert is_valid is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_audit.py::TestSkillAuditIntegration -v`
Expected: FAIL (if any part of workflow is broken)

**Step 3: Implement (no changes needed if previous steps complete)**

The implementation should already be complete from previous tasks. Just verify.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_audit.py::TestSkillAuditIntegration -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd backend && pytest tests/test_skill_audit.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/tests/test_skill_audit.py
git commit -m "test(skill-audit): add integration test for full workflow"
```

---

## Final Verification

**Step 1: Run all skill_audit tests**

Run: `cd backend && pytest tests/test_skill_audit.py -v --tb=short`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd backend && mypy src/security/skill_audit.py --strict`
Expected: No errors (may need to add type stubs for some imports)

**Step 3: Run linting**

Run: `cd backend && ruff check src/security/skill_audit.py`
Expected: No errors

Run: `cd backend && ruff format src/security/skill_audit.py`
Expected: File is already formatted

**Step 4: Run full security tests**

Run: `cd backend && pytest tests/test_skill_audit.py tests/test_data_classification.py tests/test_trust_levels.py tests/test_sanitization.py tests/test_sandbox.py -v`
Expected: All security module tests PASS

**Step 5: Final commit if needed**

```bash
git add backend/src/security/skill_audit.py backend/tests/test_skill_audit.py backend/src/security/__init__.py
git commit -m "feat(skill-audit): complete skill audit trail implementation"
```

---

## Summary

This plan creates a complete skill audit trail system with:

1. **Database schema** with hash chain fields (`previous_hash`, `entry_hash`)
2. **SkillAuditEntry dataclass** for structured audit records
3. **SkillAuditService class** with methods for:
   - `log_execution()` - Save audit entries
   - `get_latest_hash()` - Get last entry hash for chaining
   - `_compute_hash()` - SHA256 hash computation
   - `verify_chain()` - Detect tampering by validating hash chain
   - `get_audit_log()` - Query user's audit history
   - `get_audit_for_skill()` - Filter by specific skill
4. **Module exports** updated in `__init__.py`
5. **Comprehensive tests** covering single entry, chain integrity, verification, and queries

The hash chain ensures any tampering with historical records is detectable, providing an immutable audit trail for compliance and security monitoring.
