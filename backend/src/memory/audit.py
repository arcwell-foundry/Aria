"""Memory audit logging module for tracking all memory operations.

Provides:
- AuditLogEntry: Dataclass for audit log entries
- MemoryAuditLogger: Service for logging and querying audit entries
- MemoryOperation: Enum of audit-able operations
- MemoryType: Enum of memory types
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

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
    LEAD = "lead"


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
            response = client.table("memory_audit_log").insert(entry.to_dict()).execute()

            if response.data and len(response.data) > 0:
                first_row = cast(dict[str, Any], response.data[0])
                audit_id = str(first_row.get("id", ""))
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

            response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

            return cast(list[dict[str, Any]], response.data or [])

        except Exception as e:
            logger.exception("Failed to query audit log")
            raise AuditLogError(str(e)) from e


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
