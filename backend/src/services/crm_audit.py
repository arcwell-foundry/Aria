"""CRM audit service for tracking sync operations.

Provides immutable logging of all CRM synchronization operations
for compliance and debugging purposes.
"""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from src.core.exceptions import DatabaseError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class CRMAuditOperation(str, Enum):
    """Types of CRM audit operations."""

    PUSH = "push"
    PULL = "pull"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    ERROR = "error"
    RETRY = "retry"


@dataclass
class CRMAuditEntry:
    """A single CRM audit log entry."""

    user_id: str
    lead_memory_id: str
    operation: CRMAuditOperation
    provider: str
    success: bool
    details: dict[str, Any]
    created_at: datetime
    id: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for database storage."""
        return {
            "user_id": self.user_id,
            "lead_memory_id": self.lead_memory_id,
            "operation": self.operation.value,
            "provider": self.provider,
            "success": self.success,
            "details": self.details,
            "error_message": self.error_message,
        }


class CRMAuditService:
    """Service for CRM audit logging and querying.

    Provides methods to log sync operations, conflicts,
    and query/export audit logs for compliance.
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance."""
        return SupabaseClient.get_client()

    async def log_sync_operation(
        self,
        user_id: str,
        lead_memory_id: str,
        operation: CRMAuditOperation,
        provider: str,
        success: bool,
        details: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> str:
        """Log a CRM sync operation.

        Args:
            user_id: The user performing the sync.
            lead_memory_id: The lead memory being synced.
            operation: Type of sync operation.
            provider: CRM provider (salesforce, hubspot).
            success: Whether the operation succeeded.
            details: Additional operation details.
            error_message: Error message if failed.

        Returns:
            The ID of the created audit log entry.
        """
        try:
            client = self._get_supabase_client()

            entry = CRMAuditEntry(
                user_id=user_id,
                lead_memory_id=lead_memory_id,
                operation=operation,
                provider=provider,
                success=success,
                details=details or {},
                error_message=error_message,
                created_at=datetime.now(UTC),
            )

            data = entry.to_dict()
            response = client.table("crm_audit_log").insert(data).execute()

            if response.data and len(response.data) > 0:
                audit_id = str(response.data[0].get("id", ""))
                logger.info(
                    "CRM audit log entry created",
                    extra={
                        "audit_id": audit_id,
                        "operation": operation.value,
                        "provider": provider,
                        "lead_memory_id": lead_memory_id,
                    },
                )
                return audit_id

            raise DatabaseError("Failed to create audit log: no data returned from insert")

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to write CRM audit log")
            raise DatabaseError(f"Failed to write CRM audit log: {e}") from e

    async def log_conflict(
        self,
        user_id: str,
        lead_memory_id: str,
        provider: str,
        field: str,
        aria_value: Any,
        crm_value: Any,
        resolution: str,
        resolved_value: Any,
    ) -> str:
        """Log a sync conflict and its resolution.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory with conflict.
            provider: CRM provider.
            field: The conflicting field name.
            aria_value: ARIA's value for the field.
            crm_value: CRM's value for the field.
            resolution: How the conflict was resolved.
            resolved_value: The final resolved value.

        Returns:
            The ID of the created audit log entry.
        """
        details = {
            "field": field,
            "aria_value": aria_value,
            "crm_value": crm_value,
            "resolution": resolution,
            "resolved_value": resolved_value,
        }

        return await self.log_sync_operation(
            user_id=user_id,
            lead_memory_id=lead_memory_id,
            operation=CRMAuditOperation.CONFLICT_RESOLVED,
            provider=provider,
            success=True,
            details=details,
        )

    async def query_audit_log(
        self,
        user_id: str | None = None,
        lead_memory_id: str | None = None,
        operation: CRMAuditOperation | None = None,
        provider: str | None = None,
        success: bool | None = None,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query audit log entries with filters.

        Args:
            user_id: Filter by user ID.
            lead_memory_id: Filter by lead memory ID.
            operation: Filter by operation type.
            provider: Filter by CRM provider.
            success: Filter by success status.
            date_start: Filter by start date.
            date_end: Filter by end date.
            limit: Maximum entries to return.
            offset: Number of entries to skip.

        Returns:
            List of audit log entries.
        """
        try:
            client = self._get_supabase_client()
            query = client.table("crm_audit_log").select("*")

            if user_id is not None:
                query = query.eq("user_id", user_id)

            if lead_memory_id is not None:
                query = query.eq("lead_memory_id", lead_memory_id)

            if operation is not None:
                query = query.eq("operation", operation.value)

            if provider is not None:
                query = query.eq("provider", provider)

            if success is not None:
                query = query.eq("success", success)

            if date_start is not None:
                query = query.gte("created_at", date_start.isoformat())

            if date_end is not None:
                query = query.lte("created_at", date_end.isoformat())

            response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

            return cast(list[dict[str, Any]], response.data or [])

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to query CRM audit log")
            raise DatabaseError(f"Failed to query CRM audit log: {e}") from e

    async def export_audit_log(
        self,
        user_id: str,
        format: str = "csv",
        lead_memory_id: str | None = None,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> str:
        """Export audit log for compliance.

        Args:
            user_id: The user to export logs for.
            format: Export format ("csv" or "json").
            lead_memory_id: Optional filter by lead.
            date_start: Optional start date filter.
            date_end: Optional end date filter.

        Returns:
            Exported data as string (CSV or JSON).
        """
        try:
            client = self._get_supabase_client()
            query = client.table("crm_audit_log").select("*").eq("user_id", user_id)

            if lead_memory_id is not None:
                query = query.eq("lead_memory_id", lead_memory_id)

            if date_start is not None:
                query = query.gte("created_at", date_start.isoformat())

            if date_end is not None:
                query = query.lte("created_at", date_end.isoformat())

            response = query.order("created_at", desc=True).execute()
            logs = response.data or []

            if format == "json":
                return json.dumps(logs, indent=2, default=str)

            # Default to CSV
            if not logs:
                return ""

            output = io.StringIO()
            fieldnames = [
                "id",
                "user_id",
                "lead_memory_id",
                "operation",
                "provider",
                "success",
                "details",
                "error_message",
                "created_at",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            for log in logs:
                log_copy = log.copy()
                if isinstance(log_copy.get("details"), dict):
                    log_copy["details"] = json.dumps(log_copy["details"])
                writer.writerow(log_copy)

            return output.getvalue()

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to export CRM audit log")
            raise DatabaseError(f"Failed to export CRM audit log: {e}") from e


# Singleton instance
_crm_audit_service: CRMAuditService | None = None


def get_crm_audit_service() -> CRMAuditService:
    """Get or create CRM audit service singleton.

    Returns:
        The shared CRMAuditService instance.
    """
    global _crm_audit_service
    if _crm_audit_service is None:
        _crm_audit_service = CRMAuditService()
    return _crm_audit_service
