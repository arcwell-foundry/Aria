"""Tests for memory audit logging module."""

from unittest.mock import MagicMock, patch

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

    with (
        patch("src.memory.audit.SupabaseClient.get_client", return_value=mock_client),
        pytest.raises(AuditLogError),
    ):
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
