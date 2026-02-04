"""Tests for CRM synchronization service."""

from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import (
    CRMConnectionError,
    CRMSyncError,
    DatabaseError,
    LeadMemoryNotFoundError,
)
from src.services.crm_sync_models import (
    ConflictResolution,
    CRMProvider,
    CRMSyncState,
    SyncDirection,
    SyncStatus,
)


@pytest.fixture
def mock_sync_state_data() -> dict[str, Any]:
    """Create mock sync state data as returned from database."""
    now = datetime.now(UTC)
    return {
        "id": "sync-123",
        "lead_memory_id": "lead-456",
        "status": "synced",
        "sync_direction": None,
        "last_sync_at": now.isoformat(),
        "last_push_at": now.isoformat(),
        "last_pull_at": now.isoformat(),
        "pending_changes": [],
        "conflict_log": [],
        "error_message": None,
        "retry_count": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.fixture
def mock_lead_memory_data() -> dict[str, Any]:
    """Create mock lead memory data."""
    now = datetime.now(UTC)
    return {
        "id": "lead-456",
        "user_id": "user-123",
        "company_name": "Acme Pharma",
        "lifecycle_stage": "opportunity",
        "status": "active",
        "health_score": 75,
        "crm_id": "crm-789",
        "crm_provider": "salesforce",
        "expected_value": 100000.0,
        "expected_close_date": "2026-06-01",
        "first_touch_at": now.isoformat(),
        "last_activity_at": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "metadata": {"notes": "Existing notes"},
        "tags": ["pharma", "enterprise"],
    }


@pytest.fixture
def mock_integration_data() -> dict[str, Any]:
    """Create mock integration data for CRM connection."""
    return {
        "id": "int-123",
        "user_id": "user-123",
        "integration_type": "salesforce",
        "composio_connection_id": "conn-456",
        "status": "active",
    }


class TestCRMSyncServiceInit:
    """Tests for CRMSyncService initialization."""

    def test_service_initializes_successfully(self) -> None:
        """Test that CRMSyncService initializes without errors."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        assert service is not None

    def test_get_crm_sync_service_returns_singleton(self) -> None:
        """Test that get_crm_sync_service returns singleton instance."""
        from src.services.crm_sync import get_crm_sync_service

        # Reset singleton for clean test
        import src.services.crm_sync as module

        module._crm_sync_service = None

        service1 = get_crm_sync_service()
        service2 = get_crm_sync_service()

        assert service1 is service2

        # Clean up
        module._crm_sync_service = None


class TestCRMSyncServiceGetSyncState:
    """Tests for CRMSyncService.get_sync_state()."""

    @pytest.fixture
    def mock_supabase(self, mock_sync_state_data: dict[str, Any]) -> MagicMock:
        """Create a mocked Supabase client."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=mock_sync_state_data)
        mock_eq.single.return_value = mock_single
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        return mock_client

    @pytest.mark.asyncio
    async def test_get_sync_state_returns_state(
        self,
        mock_supabase: MagicMock,
        mock_sync_state_data: dict[str, Any],
    ) -> None:
        """Test get_sync_state returns sync state for lead."""
        from src.services.crm_sync import CRMSyncService

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_supabase,
        ):
            service = CRMSyncService()
            state = await service.get_sync_state("lead-456")

        assert state is not None
        assert state.lead_memory_id == "lead-456"
        assert state.status == SyncStatus.SYNCED
        mock_supabase.table.assert_called_with("lead_memory_crm_sync")

    @pytest.mark.asyncio
    async def test_get_sync_state_returns_none_when_not_found(self) -> None:
        """Test get_sync_state returns None when state doesn't exist."""
        from src.services.crm_sync import CRMSyncService

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=None)
        mock_eq.single.return_value = mock_single
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_client,
        ):
            service = CRMSyncService()
            state = await service.get_sync_state("nonexistent")

        assert state is None


class TestCRMSyncServiceCreateSyncState:
    """Tests for CRMSyncService.create_sync_state()."""

    @pytest.fixture
    def mock_supabase(self, mock_sync_state_data: dict[str, Any]) -> MagicMock:
        """Create a mocked Supabase client for create."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[mock_sync_state_data])
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        return mock_client

    @pytest.mark.asyncio
    async def test_create_sync_state_creates_new_state(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test create_sync_state creates a new sync state."""
        from src.services.crm_sync import CRMSyncService

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_supabase,
        ):
            service = CRMSyncService()
            state = await service.create_sync_state("lead-456")

        assert state is not None
        assert state.lead_memory_id == "lead-456"
        assert state.status == SyncStatus.SYNCED
        mock_supabase.table.assert_called_with("lead_memory_crm_sync")
        mock_supabase.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_sync_state_raises_on_db_error(self) -> None:
        """Test create_sync_state raises DatabaseError on failure."""
        from src.services.crm_sync import CRMSyncService

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[])  # Empty result
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_client,
        ):
            service = CRMSyncService()
            with pytest.raises(DatabaseError):
                await service.create_sync_state("lead-456")


class TestCRMSyncServiceUpdateSyncStatus:
    """Tests for CRMSyncService.update_sync_status()."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client for update."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table
        return mock_client

    @pytest.mark.asyncio
    async def test_update_sync_status_to_pending(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test update_sync_status updates status to pending."""
        from src.services.crm_sync import CRMSyncService

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_supabase,
        ):
            service = CRMSyncService()
            await service.update_sync_status(
                lead_memory_id="lead-456",
                status=SyncStatus.PENDING,
                pending_changes=[{"field": "notes", "value": "new note"}],
                direction=SyncDirection.PUSH,
            )

        update_call = mock_supabase.table.return_value.update
        update_data = update_call.call_args[0][0]
        assert update_data["status"] == "pending"
        assert update_data["sync_direction"] == "push"
        assert len(update_data["pending_changes"]) == 1

    @pytest.mark.asyncio
    async def test_update_sync_status_to_error(
        self,
        mock_supabase: MagicMock,
    ) -> None:
        """Test update_sync_status updates status to error with message."""
        from src.services.crm_sync import CRMSyncService

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_supabase,
        ):
            service = CRMSyncService()
            await service.update_sync_status(
                lead_memory_id="lead-456",
                status=SyncStatus.ERROR,
                error_message="Connection timeout",
            )

        update_call = mock_supabase.table.return_value.update
        update_data = update_call.call_args[0][0]
        assert update_data["status"] == "error"
        assert update_data["error_message"] == "Connection timeout"


class TestCRMSyncServicePushSummary:
    """Tests for CRMSyncService.push_summary_to_crm()."""

    @pytest.fixture
    def mock_supabase_for_push(
        self,
        mock_lead_memory_data: dict[str, Any],
        mock_integration_data: dict[str, Any],
        mock_sync_state_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mocked Supabase client for push operations."""
        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_lead_memory_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(
                    data=mock_integration_data
                )
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "lead_memory_crm_sync":
                # For get_sync_state
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_sync_state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

                # For update
                mock_update = MagicMock()
                mock_update_eq = MagicMock()
                mock_update_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
                mock_update.eq.return_value = mock_update_eq
                mock_table.update.return_value = mock_update

            elif name == "crm_audit_log":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table = table_router
        return mock_client

    @pytest.mark.asyncio
    async def test_push_summary_adds_aria_tag(
        self,
        mock_supabase_for_push: MagicMock,
    ) -> None:
        """Test push_summary_to_crm adds [ARIA] tag to notes."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(return_value={"success": True})

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_push,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.push_summary_to_crm(
                user_id="user-123",
                lead_memory_id="lead-456",
                summary="Meeting went well, next steps defined",
            )

        assert result["success"] is True

        # Verify the note content includes [ARIA] tag
        call_args = mock_oauth.execute_action.call_args
        params = call_args.kwargs["params"]
        assert "[ARIA]" in params["body"] or "[ARIA]" in params.get("content", "")

    @pytest.mark.asyncio
    async def test_push_summary_uses_correct_crm_action(
        self,
        mock_supabase_for_push: MagicMock,
    ) -> None:
        """Test push_summary_to_crm uses correct Salesforce action."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(return_value={"success": True})

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_push,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            await service.push_summary_to_crm(
                user_id="user-123",
                lead_memory_id="lead-456",
                summary="Test summary",
            )

        # Salesforce action for adding notes
        call_args = mock_oauth.execute_action.call_args
        assert call_args.kwargs["action"] in [
            "salesforce_create_note",
            "salesforce_add_note",
        ]

    @pytest.mark.asyncio
    async def test_push_summary_logs_audit(
        self,
        mock_supabase_for_push: MagicMock,
    ) -> None:
        """Test push_summary_to_crm logs to audit."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(return_value={"success": True})

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_push,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            await service.push_summary_to_crm(
                user_id="user-123",
                lead_memory_id="lead-456",
                summary="Test summary",
            )

        mock_audit.log_sync_operation.assert_called_once()
        call_kwargs = mock_audit.log_sync_operation.call_args.kwargs
        assert call_kwargs["operation"].value == "push"
        assert call_kwargs["provider"] == "salesforce"

    @pytest.mark.asyncio
    async def test_push_summary_raises_when_no_crm_connection(
        self,
        mock_lead_memory_data: dict[str, Any],
    ) -> None:
        """Test push_summary_to_crm raises when CRM not connected."""
        from src.services.crm_sync import CRMSyncService

        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()
            if name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_lead_memory_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(data=None)
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select
            return mock_table

        mock_client.table = table_router

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_client,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            with pytest.raises(CRMConnectionError):
                await service.push_summary_to_crm(
                    user_id="user-123",
                    lead_memory_id="lead-456",
                    summary="Test summary",
                )


class TestCRMSyncServicePullChanges:
    """Tests for CRMSyncService.pull_stage_changes()."""

    @pytest.fixture
    def mock_supabase_for_pull(
        self,
        mock_lead_memory_data: dict[str, Any],
        mock_integration_data: dict[str, Any],
        mock_sync_state_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mocked Supabase client for pull operations."""
        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_lead_memory_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

                # For update
                mock_update = MagicMock()
                mock_update_eq1 = MagicMock()
                mock_update_eq2 = MagicMock()
                mock_update_eq2.execute.return_value = MagicMock(
                    data=[mock_lead_memory_data]
                )
                mock_update_eq1.eq.return_value = mock_update_eq2
                mock_update.eq.return_value = mock_update_eq1
                mock_table.update.return_value = mock_update

            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(
                    data=mock_integration_data
                )
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "lead_memory_crm_sync":
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_sync_state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

                mock_update = MagicMock()
                mock_update_eq = MagicMock()
                mock_update_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
                mock_update.eq.return_value = mock_update_eq
                mock_table.update.return_value = mock_update

            elif name == "crm_audit_log":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table = table_router
        return mock_client

    @pytest.mark.asyncio
    async def test_pull_stage_changes_updates_lead(
        self,
        mock_supabase_for_pull: MagicMock,
    ) -> None:
        """Test pull_stage_changes updates lead from CRM."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        # Mock CRM returning updated data
        mock_oauth.execute_action = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "StageName": "Negotiation",
                    "Amount": 150000.0,
                    "CloseDate": "2026-07-15",
                },
            }
        )

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_pull,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit.log_conflict = AsyncMock(return_value="audit-456")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.pull_stage_changes(
                user_id="user-123",
                lead_memory_id="lead-456",
            )

        assert result["success"] is True
        assert "changes_applied" in result

    @pytest.mark.asyncio
    async def test_pull_stage_changes_crm_wins_for_structured_fields(
        self,
        mock_supabase_for_pull: MagicMock,
    ) -> None:
        """Test pull_stage_changes applies CRM wins for structured fields."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "StageName": "Negotiation",  # Different from ARIA
                    "Amount": 200000.0,  # Different from ARIA
                },
            }
        )

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_pull,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit.log_conflict = AsyncMock(return_value="audit-456")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.pull_stage_changes(
                user_id="user-123",
                lead_memory_id="lead-456",
            )

        # Verify CRM values were applied
        assert result["success"] is True


class TestCRMSyncServiceConflictResolution:
    """Tests for CRMSyncService._resolve_conflict()."""

    def test_conflict_resolution_crm_wins_for_stage(self) -> None:
        """Test that CRM wins for lifecycle_stage field."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="lifecycle_stage",
            aria_value="lead",
            crm_value="opportunity",
        )

        assert resolution == ConflictResolution.CRM_WINS

    def test_conflict_resolution_crm_wins_for_expected_value(self) -> None:
        """Test that CRM wins for expected_value field."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="expected_value",
            aria_value=100000,
            crm_value=150000,
        )

        assert resolution == ConflictResolution.CRM_WINS

    def test_conflict_resolution_crm_wins_for_close_date(self) -> None:
        """Test that CRM wins for expected_close_date field."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="expected_close_date",
            aria_value="2026-06-01",
            crm_value="2026-07-01",
        )

        assert resolution == ConflictResolution.CRM_WINS

    def test_conflict_resolution_crm_wins_for_status(self) -> None:
        """Test that CRM wins for status field."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="status",
            aria_value="active",
            crm_value="won",
        )

        assert resolution == ConflictResolution.CRM_WINS

    def test_conflict_resolution_merge_for_notes(self) -> None:
        """Test that notes are merged."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="notes",
            aria_value="ARIA note",
            crm_value="CRM note",
        )

        assert resolution == ConflictResolution.MERGE

    def test_conflict_resolution_aria_wins_for_health_score(self) -> None:
        """Test that ARIA wins for health_score field."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        resolution = service._resolve_conflict(
            field="health_score",
            aria_value=75,
            crm_value=60,
        )

        assert resolution == ConflictResolution.ARIA_WINS


class TestCRMSyncServiceManualSync:
    """Tests for CRMSyncService.trigger_manual_sync()."""

    @pytest.fixture
    def mock_supabase_for_sync(
        self,
        mock_lead_memory_data: dict[str, Any],
        mock_integration_data: dict[str, Any],
        mock_sync_state_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mocked Supabase client for sync operations."""
        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_lead_memory_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

                mock_update = MagicMock()
                mock_update_eq1 = MagicMock()
                mock_update_eq2 = MagicMock()
                mock_update_eq2.execute.return_value = MagicMock(
                    data=[mock_lead_memory_data]
                )
                mock_update_eq1.eq.return_value = mock_update_eq2
                mock_update.eq.return_value = mock_update_eq1
                mock_table.update.return_value = mock_update

            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(
                    data=mock_integration_data
                )
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "lead_memory_crm_sync":
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_sync_state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

                mock_update = MagicMock()
                mock_update_eq = MagicMock()
                mock_update_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
                mock_update.eq.return_value = mock_update_eq
                mock_table.update.return_value = mock_update

            elif name == "crm_audit_log":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table = table_router
        return mock_client

    @pytest.mark.asyncio
    async def test_manual_sync_performs_bidirectional_sync(
        self,
        mock_supabase_for_sync: MagicMock,
    ) -> None:
        """Test trigger_manual_sync performs bidirectional sync."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "StageName": "Negotiation",
                    "Amount": 150000.0,
                },
            }
        )

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_sync,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit.log_conflict = AsyncMock(return_value="audit-456")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.trigger_manual_sync(
                user_id="user-123",
                lead_memory_id="lead-456",
            )

        assert result["success"] is True
        assert result["direction"] == "bidirectional"


class TestCRMSyncServiceRetryLogic:
    """Tests for CRMSyncService retry logic."""

    @pytest.fixture
    def mock_supabase_for_retry(
        self,
        mock_sync_state_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mocked Supabase client for retry operations."""
        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "lead_memory_crm_sync":
                # For get_sync_state
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                state_data = {**mock_sync_state_data, "retry_count": 2}
                mock_single.execute.return_value = MagicMock(data=state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

                # For update
                mock_update = MagicMock()
                mock_update_eq = MagicMock()
                mock_update_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
                mock_update.eq.return_value = mock_update_eq
                mock_table.update.return_value = mock_update

            elif name == "crm_audit_log":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table = table_router
        return mock_client

    def test_should_retry_returns_true_under_max(self) -> None:
        """Test _should_retry returns True when under max retries."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        assert service._should_retry(0) is True
        assert service._should_retry(4) is True

    def test_should_retry_returns_false_at_max(self) -> None:
        """Test _should_retry returns False at max retries."""
        from src.services.crm_sync import CRMSyncService

        service = CRMSyncService()
        assert service._should_retry(5) is False
        assert service._should_retry(6) is False

    @pytest.mark.asyncio
    async def test_schedule_retry_increments_count(
        self,
        mock_supabase_for_retry: MagicMock,
    ) -> None:
        """Test schedule_retry increments retry count."""
        from src.services.crm_sync import CRMSyncService

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_retry,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.schedule_retry("lead-456")

        assert result["scheduled"] is True
        assert result["retry_count"] == 3  # Was 2, incremented to 3

    @pytest.mark.asyncio
    async def test_schedule_retry_returns_max_reached_when_at_limit(self) -> None:
        """Test schedule_retry indicates max reached when at limit."""
        from src.services.crm_sync import CRMSyncService

        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()
            if name == "lead_memory_crm_sync":
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                # At max retries
                now = datetime.now(UTC)
                state_data = {
                    "id": "sync-123",
                    "lead_memory_id": "lead-456",
                    "status": "error",
                    "sync_direction": None,
                    "last_sync_at": now.isoformat(),
                    "last_push_at": now.isoformat(),
                    "last_pull_at": now.isoformat(),
                    "pending_changes": [],
                    "conflict_log": [],
                    "error_message": "Connection failed",
                    "retry_count": 5,  # At max
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
                mock_single.execute.return_value = MagicMock(data=state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select
            return mock_table

        mock_client.table = table_router

        with patch(
            "src.services.crm_sync.SupabaseClient.get_client",
            return_value=mock_client,
        ):
            service = CRMSyncService()
            result = await service.schedule_retry("lead-456")

        assert result["scheduled"] is False
        assert result["max_retries_reached"] is True


class TestCRMSyncServicePullActivities:
    """Tests for CRMSyncService.pull_activities()."""

    @pytest.fixture
    def mock_supabase_for_activities(
        self,
        mock_lead_memory_data: dict[str, Any],
        mock_integration_data: dict[str, Any],
        mock_sync_state_data: dict[str, Any],
    ) -> MagicMock:
        """Create a mocked Supabase client for activity operations."""
        mock_client = MagicMock()

        def table_router(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_lead_memory_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(
                    data=mock_integration_data
                )
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "lead_memory_crm_sync":
                mock_select = MagicMock()
                mock_eq = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_sync_state_data)
                mock_eq.single.return_value = mock_single
                mock_select.eq.return_value = mock_eq
                mock_table.select.return_value = mock_select

                mock_update = MagicMock()
                mock_update_eq = MagicMock()
                mock_update_eq.execute.return_value = MagicMock(data=[{"id": "sync-123"}])
                mock_update.eq.return_value = mock_update_eq
                mock_table.update.return_value = mock_update

            elif name == "lead_memory_events":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "event-123"}]
                )
                mock_table.insert.return_value = mock_insert

            elif name == "crm_audit_log":
                mock_insert = MagicMock()
                mock_insert.execute.return_value = MagicMock(
                    data=[{"id": "audit-123"}]
                )
                mock_table.insert.return_value = mock_insert

            return mock_table

        mock_client.table = table_router
        return mock_client

    @pytest.mark.asyncio
    async def test_pull_activities_creates_events(
        self,
        mock_supabase_for_activities: MagicMock,
    ) -> None:
        """Test pull_activities creates lead events from CRM activities."""
        from src.services.crm_sync import CRMSyncService

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(
            return_value={
                "success": True,
                "data": [
                    {
                        "Id": "act-1",
                        "Subject": "Call with VP Sales",
                        "ActivityDate": "2026-02-01",
                        "Type": "Call",
                    },
                    {
                        "Id": "act-2",
                        "Subject": "Email follow-up",
                        "ActivityDate": "2026-02-02",
                        "Type": "Email",
                    },
                ],
            }
        )

        with (
            patch(
                "src.services.crm_sync.SupabaseClient.get_client",
                return_value=mock_supabase_for_activities,
            ),
            patch(
                "src.services.crm_sync.get_oauth_client",
                return_value=mock_oauth,
            ),
            patch(
                "src.services.crm_sync.get_crm_audit_service",
            ) as mock_audit_getter,
        ):
            mock_audit = AsyncMock()
            mock_audit.log_sync_operation = AsyncMock(return_value="audit-123")
            mock_audit_getter.return_value = mock_audit

            service = CRMSyncService()
            result = await service.pull_activities(
                user_id="user-123",
                lead_memory_id="lead-456",
            )

        assert result["success"] is True
        assert result["activities_imported"] == 2


class TestCRMStageMappings:
    """Tests for CRM stage mappings."""

    def test_salesforce_stage_map_exists(self) -> None:
        """Test Salesforce stage mapping is defined."""
        from src.services.crm_sync import SALESFORCE_STAGE_MAP

        assert "Prospecting" in SALESFORCE_STAGE_MAP
        assert "Closed Won" in SALESFORCE_STAGE_MAP
        assert SALESFORCE_STAGE_MAP["Prospecting"] == "lead"
        assert SALESFORCE_STAGE_MAP["Closed Won"] == "account"

    def test_hubspot_stage_map_exists(self) -> None:
        """Test HubSpot stage mapping is defined."""
        from src.services.crm_sync import HUBSPOT_STAGE_MAP

        assert "appointmentscheduled" in HUBSPOT_STAGE_MAP
        assert "closedwon" in HUBSPOT_STAGE_MAP
        assert HUBSPOT_STAGE_MAP["appointmentscheduled"] == "lead"
        assert HUBSPOT_STAGE_MAP["closedwon"] == "account"


class TestCRMWinsFields:
    """Tests for CRM wins field configuration."""

    def test_crm_wins_fields_contains_required(self) -> None:
        """Test CRM_WINS_FIELDS contains all required fields."""
        from src.services.crm_sync import CRM_WINS_FIELDS

        assert "lifecycle_stage" in CRM_WINS_FIELDS
        assert "expected_value" in CRM_WINS_FIELDS
        assert "expected_close_date" in CRM_WINS_FIELDS
        assert "status" in CRM_WINS_FIELDS

    def test_crm_wins_fields_excludes_aria_fields(self) -> None:
        """Test CRM_WINS_FIELDS excludes ARIA-owned fields."""
        from src.services.crm_sync import CRM_WINS_FIELDS

        assert "health_score" not in CRM_WINS_FIELDS
        assert "insights" not in CRM_WINS_FIELDS
        assert "stakeholder_map" not in CRM_WINS_FIELDS


class TestMaxRetries:
    """Tests for MAX_RETRIES constant."""

    def test_max_retries_is_five(self) -> None:
        """Test MAX_RETRIES is set to 5."""
        from src.services.crm_sync import MAX_RETRIES

        assert MAX_RETRIES == 5
