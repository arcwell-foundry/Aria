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

    def test_compute_hash_handles_key_ordering(self) -> None:
        """Test semantically equivalent dicts with different key ordering produce same hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        # Same data, different key ordering
        dict1 = {"skill_id": "test", "user_id": "123", "success": True}
        dict2 = {"user_id": "123", "skill_id": "test", "success": True}
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(dict1, previous_hash)
        hash2 = service._compute_hash(dict2, previous_hash)

        assert hash1 == hash2

    def test_compute_hash_handles_boolean_and_none(self) -> None:
        """Test hash handles boolean and None values correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        data = {"active": True, "deleted": False, "metadata": None}
        result = service._compute_hash(data, "prev")

        # Should produce valid 64-char hash without error
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_hash_handles_numeric_values(self) -> None:
        """Test hash handles integer and float values correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        data = {"count": 42, "ratio": 3.14, "tokens_used": 1000}
        result = service._compute_hash(data, "prev")

        assert len(result) == 64

    def test_compute_hash_handles_empty_dict(self) -> None:
        """Test hash handles empty dictionary correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        result = service._compute_hash({}, "prev-hash")

        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestGetLatestHash:
    """Tests for get_latest_hash method."""

    @pytest.mark.asyncio
    async def test_returns_zero_hash_for_new_user(self) -> None:
        """Test returns zero hash when user has no audit entries."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.limit.return_value = mock_query_builder
        mock_query_builder.single.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.table.return_value.select.return_value = mock_query_builder

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
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.limit.return_value = mock_query_builder
        mock_query_builder.single.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(
            return_value=MagicMock(data={"entry_hash": expected_hash})
        )
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_latest_hash("user-123")

        assert result == expected_hash

    @pytest.mark.asyncio
    async def test_queries_correct_table_and_order(self) -> None:
        """Test queries skill_audit_log ordered by timestamp DESC."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.limit.return_value = mock_query_builder
        mock_query_builder.single.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        await service.get_latest_hash("user-456")

        # Verify table name
        mock_client.table.assert_called_once_with("skill_audit_log")
        # Verify select column
        mock_client.table.return_value.select.assert_called_once_with("entry_hash")
        # Verify ordering
        mock_query_builder.order.assert_called_once_with("timestamp", desc=True)
        # Verify limit
        mock_query_builder.limit.assert_called_once_with(1)


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


class TestVerifyChain:
    """Tests for hash chain verification."""

    @pytest.mark.asyncio
    async def test_verify_chain_passes_with_valid_chain(self) -> None:
        """Test verification passes when chain is intact."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        # Build a valid chain: entry1 -> entry2 -> entry3
        service = SkillAuditService()
        zero_hash = "0" * 64

        # Entry 1 (genesis) - compute hash WITHOUT filtered fields (id, timestamp, entry_hash, previous_hash)
        entry1_data = {"skill_id": "skill1", "user_id": "user123"}
        entry1_hash = service._compute_hash(entry1_data, zero_hash)

        # Entry 2
        entry2_data = {"skill_id": "skill2", "user_id": "user123"}
        entry2_hash = service._compute_hash(entry2_data, entry1_hash)

        # Entry 3
        entry3_data = {"skill_id": "skill3", "user_id": "user123"}
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
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=mock_entries))
        mock_client.table.return_value.select.return_value = mock_query_builder

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

        # Valid chain - compute hashes WITHOUT filtered fields
        entry1_data = {"skill_id": "skill1", "user_id": "user123"}
        entry1_hash = service._compute_hash(entry1_data, zero_hash)
        entry2_data = {"skill_id": "skill2", "user_id": "user123"}
        entry2_hash = service._compute_hash(entry2_data, entry1_hash)

        # Tampered entry: previous_hash doesn't match actual previous entry_hash
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
                "previous_hash": "tampered" * 8,  # Wrong!
                "entry_hash": entry2_hash,
            },
        ]

        mock_client = MagicMock()
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=mock_entries))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service2 = SkillAuditService(supabase_client=mock_client)
        result = await service2.verify_chain("user123")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_chain_fails_with_broken_hash(self) -> None:
        """Test verification fails when entry_hash doesn't match computed."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        zero_hash = "0" * 64

        # Create an entry with a wrong entry_hash (doesn't match computed)
        entry1_data = {"skill_id": "skill1", "user_id": "user123"}
        correct_hash = service._compute_hash(entry1_data, zero_hash)

        mock_entries = [
            {
                "id": "1",
                "skill_id": "skill1",
                "user_id": "user123",
                "previous_hash": zero_hash,
                "entry_hash": "wrong" * 16,  # Doesn't match computed hash!
            },
        ]

        mock_client = MagicMock()
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=mock_entries))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.verify_chain("user123")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_chain_returns_true_for_empty_chain(self) -> None:
        """Test verification passes when user has no entries."""
        from unittest.mock import AsyncMock, MagicMock

        from src.security.skill_audit import SkillAuditService

        mock_client = MagicMock()
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.verify_chain("user123")

        assert result is True


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
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.range.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=mock_entries))
        mock_client.table.return_value.select.return_value = mock_query_builder

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
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.range.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        await service.get_audit_log("user-123", limit=20, offset=40)

        # Verify range was called with correct offset/limit
        mock_query_builder.range.assert_called_once_with(40, 59)  # offset to offset + limit - 1

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
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.order.return_value = mock_query_builder
        mock_query_builder.range.return_value = mock_query_builder
        mock_query_builder.execute = AsyncMock(return_value=MagicMock(data=mock_entries))
        mock_client.table.return_value.select.return_value = mock_query_builder

        service = SkillAuditService(supabase_client=mock_client)
        result = await service.get_audit_for_skill("user-123", "pdf", limit=10, offset=0)

        # Verify eq was called twice: once for user_id, once for skill_id
        assert mock_query_builder.eq.call_count == 2
        # Second call should be with skill_id
        mock_query_builder.eq.assert_any_call("user_id", "user-123")
        mock_query_builder.eq.assert_any_call("skill_id", "pdf")
        assert len(result) == 1
        assert result[0]["skill_id"] == "pdf"


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
