"""Tests for sync scheduler (US-942 Task 8)."""

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.domain import IntegrationType
from src.integrations.sync_scheduler import SyncScheduler, get_sync_scheduler


@pytest.fixture
def sync_scheduler() -> SyncScheduler:
    """Create a fresh sync scheduler for each test."""
    # Reset singleton for clean tests
    import src.integrations.sync_scheduler

    src.integrations.sync_scheduler._sync_scheduler = None
    return SyncScheduler(interval_seconds=1)


class TestSyncSchedulerSingleton:
    """Tests for get_sync_scheduler singleton."""

    def test_get_sync_scheduler_singleton(self) -> None:
        """Test that get_sync_scheduler returns singleton instance."""
        # Reset singleton
        import src.integrations.sync_scheduler

        src.integrations.sync_scheduler._sync_scheduler = None

        scheduler1 = get_sync_scheduler()
        scheduler2 = get_sync_scheduler()
        assert scheduler1 is scheduler2


class TestSyncSchedulerStartStop:
    """Tests for start and stop lifecycle methods."""

    @pytest.mark.asyncio
    async def test_scheduler_start_sets_running_state(self, sync_scheduler: SyncScheduler) -> None:
        """Test that start sets running state to True."""
        assert not sync_scheduler._running
        await sync_scheduler.start()
        assert sync_scheduler._running
        await sync_scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_start_when_already_running(self, sync_scheduler: SyncScheduler) -> None:
        """Test that calling start when already running is idempotent."""
        await sync_scheduler.start()
        original_task = sync_scheduler._task

        # Call start again
        await sync_scheduler.start()

        # Should still have the same task
        assert sync_scheduler._task is original_task
        await sync_scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_stop_clears_running_state(self, sync_scheduler: SyncScheduler) -> None:
        """Test that stop sets running state to False."""
        await sync_scheduler.start()
        await sync_scheduler.stop()
        assert not sync_scheduler._running

    @pytest.mark.asyncio
    async def test_scheduler_stop_when_not_running(self, sync_scheduler: SyncScheduler) -> None:
        """Test that calling stop when not running is safe."""
        # Should not raise
        await sync_scheduler.stop()
        assert not sync_scheduler._running

    @pytest.mark.asyncio
    async def test_scheduler_stop_cancels_task(self, sync_scheduler: SyncScheduler) -> None:
        """Test that stop cancels the background task."""
        await sync_scheduler.start()
        assert sync_scheduler._task is not None

        await sync_scheduler.stop()

        # Task should be cancelled
        assert sync_scheduler._task.done()


class TestProcessDueSyncs:
    """Tests for _process_due_syncs method."""

    @pytest.mark.asyncio
    async def test_process_due_syncs_empty(self, sync_scheduler: SyncScheduler) -> None:
        """Test that no errors occur when no syncs are due."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            # Should not raise
            await sync_scheduler._process_due_syncs()

    @pytest.mark.asyncio
    async def test_process_due_syncs_crm_integration(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test processing due syncs for CRM integrations."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            # Mock sync state query
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "salesforce",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                }
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            # Mock deep sync service
            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                await sync_scheduler._process_due_syncs()

                # Verify CRM sync was called
                mock_service.sync_crm_to_aria.assert_called_once_with(
                    "user-123", IntegrationType.SALESFORCE
                )

    @pytest.mark.asyncio
    async def test_process_due_syncs_calendar_integration(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test processing due syncs for calendar integrations."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-2",
                    "user_id": "user-456",
                    "integration_type": "google_calendar",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                }
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                await sync_scheduler._process_due_syncs()

                # Verify calendar sync was called
                mock_service.sync_calendar.assert_called_once_with(
                    "user-456", IntegrationType.GOOGLE_CALENDAR
                )

    @pytest.mark.asyncio
    async def test_process_due_syncs_multiple_parallel(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test that multiple syncs are executed in parallel."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "salesforce",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                },
                {
                    "id": "sync-2",
                    "user_id": "user-456",
                    "integration_type": "hubspot",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                },
                {
                    "id": "sync-3",
                    "user_id": "user-789",
                    "integration_type": "google_calendar",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                },
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                await sync_scheduler._process_due_syncs()

                # Verify all syncs were called
                assert mock_service.sync_crm_to_aria.call_count == 2
                assert mock_service.sync_calendar.call_count == 1

    @pytest.mark.asyncio
    async def test_process_due_syncs_skips_invalid_integration_type(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test that invalid integration types are skipped."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "invalid_type",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                }
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                # Should not raise
                await sync_scheduler._process_due_syncs()

                # No sync methods should be called
                mock_service.sync_crm_to_aria.assert_not_called()
                mock_service.sync_calendar.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_due_syncs_skips_unsupported_types(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test that unsupported integration types are skipped (GMAIL, SLACK)."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "gmail",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                }
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                await sync_scheduler._process_due_syncs()

                # No sync methods should be called for unsupported types
                mock_service.sync_crm_to_aria.assert_not_called()
                mock_service.sync_calendar.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_due_syncs_handles_sync_exceptions(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test that sync exceptions don't stop other syncs."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "salesforce",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                },
                {
                    "id": "sync-2",
                    "user_id": "user-456",
                    "integration_type": "hubspot",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                },
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                # First sync raises, second succeeds
                mock_sync = AsyncMock(side_effect=[
                    Exception("Sync failed"),  # First call raises
                    MagicMock(),  # Second call succeeds
                ])

                mock_service = AsyncMock()
                mock_service.sync_crm_to_aria = mock_sync
                mock_get_service.return_value = mock_service

                # Should not raise
                await sync_scheduler._process_due_syncs()

                # Both syncs should have been attempted
                assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_process_due_syncs_logs_success_count(
        self, sync_scheduler: SyncScheduler, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that sync counts are logged."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            now = datetime.now(UTC)
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                {
                    "id": "sync-1",
                    "user_id": "user-123",
                    "integration_type": "salesforce",
                    "last_sync_status": "success",
                    "next_sync_at": now.isoformat(),
                }
            ]
            mock_client.table.return_value.select.return_value.lte.return_value.eq.return_value.execute.return_value = (
                mock_response
            )
            mock_supabase.get_client.return_value = mock_client

            with patch("src.integrations.sync_scheduler.get_deep_sync_service") as mock_get_service:
                mock_service = AsyncMock()
                mock_get_service.return_value = mock_service

                with caplog.at_level(logging.INFO):
                    await sync_scheduler._process_due_syncs()

                # Check for success log
                assert any("Completed scheduled syncs" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_process_due_syncs_handles_db_query_error(
        self, sync_scheduler: SyncScheduler, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that database query errors are handled gracefully."""
        with patch("src.integrations.sync_scheduler.SupabaseClient") as mock_supabase:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Database error")
            mock_supabase.get_client.return_value = mock_client

            with caplog.at_level(logging.ERROR):
                # Should not raise
                await sync_scheduler._process_due_syncs()

                # Error should be logged
                assert any("Failed to process due syncs" in record.message for record in caplog.records)


class TestSchedulerLoopContinuesAfterError:
    """Tests for scheduler loop error handling."""

    @pytest.mark.asyncio
    async def test_scheduler_loop_continues_after_error(
        self, sync_scheduler: SyncScheduler
    ) -> None:
        """Test that errors in _process_due_syncs don't stop the scheduler loop."""
        call_count = 0

        async def mock_process_with_error():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First call fails")

        with patch.object(sync_scheduler, "_process_due_syncs", side_effect=mock_process_with_error):
            await sync_scheduler.start()

            # Wait for at least 2 iterations (interval is 1 second)
            await asyncio.sleep(2.5)

            await sync_scheduler.stop()

            # Should have been called multiple times despite error
            assert call_count >= 2
