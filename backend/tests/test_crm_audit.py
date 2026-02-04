"""Tests for CRM audit service."""

from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock, patch

import pytest


class TestCRMAuditOperationEnum:
    """Tests for CRMAuditOperation enum."""

    def test_audit_operation_values(self) -> None:
        """Test CRMAuditOperation enum has correct values."""
        from src.services.crm_audit import CRMAuditOperation

        assert CRMAuditOperation.PUSH.value == "push"
        assert CRMAuditOperation.PULL.value == "pull"
        assert CRMAuditOperation.CONFLICT_DETECTED.value == "conflict_detected"
        assert CRMAuditOperation.CONFLICT_RESOLVED.value == "conflict_resolved"
        assert CRMAuditOperation.ERROR.value == "error"
        assert CRMAuditOperation.RETRY.value == "retry"


class TestCRMAuditEntryDataclass:
    """Tests for CRMAuditEntry dataclass."""

    def test_audit_entry_initialization(self) -> None:
        """Test CRMAuditEntry initializes correctly."""
        from src.services.crm_audit import CRMAuditEntry, CRMAuditOperation

        now = datetime.now(UTC)
        entry = CRMAuditEntry(
            user_id="user-123",
            lead_memory_id="lead-456",
            operation=CRMAuditOperation.PUSH,
            provider="salesforce",
            success=True,
            details={"fields_synced": ["stage", "notes"]},
            created_at=now,
        )

        assert entry.user_id == "user-123"
        assert entry.operation == CRMAuditOperation.PUSH
        assert entry.success is True

    def test_audit_entry_to_dict(self) -> None:
        """Test CRMAuditEntry.to_dict serializes correctly."""
        from src.services.crm_audit import CRMAuditEntry, CRMAuditOperation

        now = datetime.now(UTC)
        entry = CRMAuditEntry(
            user_id="user-123",
            lead_memory_id="lead-456",
            operation=CRMAuditOperation.CONFLICT_DETECTED,
            provider="hubspot",
            success=False,
            details={"conflicting_field": "stage"},
            created_at=now,
        )

        data = entry.to_dict()

        assert data["operation"] == "conflict_detected"
        assert data["provider"] == "hubspot"
        assert data["success"] is False


class TestCRMAuditServiceLogOperation:
    """Tests for CRMAuditService.log_sync_operation()."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "audit-123"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_log_sync_operation_push(self, mock_supabase: MagicMock) -> None:
        """Test logging a push operation."""
        from src.services.crm_audit import CRMAuditService, CRMAuditOperation

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase):
            service = CRMAuditService()
            audit_id = await service.log_sync_operation(
                user_id="user-123",
                lead_memory_id="lead-456",
                operation=CRMAuditOperation.PUSH,
                provider="salesforce",
                success=True,
                details={"notes_pushed": 3},
            )

        assert audit_id == "audit-123"
        mock_supabase.table.assert_called_with("crm_audit_log")

    @pytest.mark.asyncio
    async def test_log_sync_operation_stores_all_fields(self, mock_supabase: MagicMock) -> None:
        """Test that log_sync_operation stores all required fields."""
        from src.services.crm_audit import CRMAuditService, CRMAuditOperation

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase):
            service = CRMAuditService()
            await service.log_sync_operation(
                user_id="user-123",
                lead_memory_id="lead-456",
                operation=CRMAuditOperation.PULL,
                provider="hubspot",
                success=True,
                details={"stages_synced": 1},
            )

        insert_call = mock_supabase.table.return_value.insert
        insert_data = insert_call.call_args[0][0]
        assert insert_data["user_id"] == "user-123"
        assert insert_data["lead_memory_id"] == "lead-456"
        assert insert_data["operation"] == "pull"
        assert insert_data["provider"] == "hubspot"


class TestCRMAuditServiceLogConflict:
    """Tests for CRMAuditService.log_conflict()."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "audit-789"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        return mock_client

    @pytest.mark.asyncio
    async def test_log_conflict_with_resolution(self, mock_supabase: MagicMock) -> None:
        """Test logging a conflict with resolution details."""
        from src.services.crm_audit import CRMAuditService

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase):
            service = CRMAuditService()
            audit_id = await service.log_conflict(
                user_id="user-123",
                lead_memory_id="lead-456",
                provider="salesforce",
                field="lifecycle_stage",
                aria_value="opportunity",
                crm_value="prospect",
                resolution="crm_wins",
                resolved_value="prospect",
            )

        assert audit_id == "audit-789"
        insert_data = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_data["operation"] == "conflict_resolved"
        assert insert_data["details"]["field"] == "lifecycle_stage"
        assert insert_data["details"]["resolution"] == "crm_wins"


class TestCRMAuditServiceQuery:
    """Tests for CRMAuditService.query_audit_log()."""

    @pytest.fixture
    def mock_supabase_with_logs(self) -> MagicMock:
        """Create a mocked Supabase client with audit logs."""
        mock_client = MagicMock()
        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "audit-1",
                "user_id": "user-123",
                "lead_memory_id": "lead-456",
                "operation": "push",
                "provider": "salesforce",
                "success": True,
                "details": {},
                "created_at": now.isoformat(),
            },
            {
                "id": "audit-2",
                "user_id": "user-123",
                "lead_memory_id": "lead-456",
                "operation": "pull",
                "provider": "salesforce",
                "success": True,
                "details": {},
                "created_at": (now - timedelta(hours=1)).isoformat(),
            },
        ]

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.gte.return_value = mock_select
        mock_select.lte.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.limit.return_value = mock_select
        mock_select.offset.return_value = mock_select
        mock_select.execute.return_value = mock_response

        return mock_client

    @pytest.mark.asyncio
    async def test_query_by_lead(self, mock_supabase_with_logs: MagicMock) -> None:
        """Test querying audit log by lead ID."""
        from src.services.crm_audit import CRMAuditService

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase_with_logs):
            service = CRMAuditService()
            logs = await service.query_audit_log(lead_memory_id="lead-456")

        assert len(logs) == 2
        assert logs[0]["id"] == "audit-1"

    @pytest.mark.asyncio
    async def test_query_by_date_range(self, mock_supabase_with_logs: MagicMock) -> None:
        """Test querying audit log by date range."""
        from src.services.crm_audit import CRMAuditService

        now = datetime.now(UTC)
        start = now - timedelta(days=7)
        end = now

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase_with_logs):
            service = CRMAuditService()
            logs = await service.query_audit_log(
                date_start=start,
                date_end=end,
            )

        mock_select = mock_supabase_with_logs.table.return_value.select.return_value
        mock_select.gte.assert_called()
        mock_select.lte.assert_called()


class TestCRMAuditServiceExport:
    """Tests for CRMAuditService.export_audit_log()."""

    @pytest.fixture
    def mock_supabase_with_logs(self) -> MagicMock:
        """Create a mocked Supabase client with audit logs."""
        mock_client = MagicMock()
        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "audit-1",
                "user_id": "user-123",
                "lead_memory_id": "lead-456",
                "operation": "push",
                "provider": "salesforce",
                "success": True,
                "details": {"notes": 2},
                "created_at": now.isoformat(),
            },
        ]

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.gte.return_value = mock_select
        mock_select.lte.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.execute.return_value = mock_response

        return mock_client

    @pytest.mark.asyncio
    async def test_export_to_csv_format(self, mock_supabase_with_logs: MagicMock) -> None:
        """Test exporting audit log in CSV format."""
        from src.services.crm_audit import CRMAuditService

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase_with_logs):
            service = CRMAuditService()
            csv_data = await service.export_audit_log(
                user_id="user-123",
                format="csv",
            )

        assert "id,user_id,lead_memory_id" in csv_data
        assert "audit-1" in csv_data
        assert "salesforce" in csv_data

    @pytest.mark.asyncio
    async def test_export_to_json_format(self, mock_supabase_with_logs: MagicMock) -> None:
        """Test exporting audit log in JSON format."""
        import json
        from src.services.crm_audit import CRMAuditService

        with patch("src.services.crm_audit.SupabaseClient.get_client", return_value=mock_supabase_with_logs):
            service = CRMAuditService()
            json_data = await service.export_audit_log(
                user_id="user-123",
                format="json",
            )

        parsed = json.loads(json_data)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "audit-1"
