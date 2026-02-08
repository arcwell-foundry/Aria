"""Background scheduler for recurring integration sync operations.

This module implements a background scheduler that runs recurring sync operations
for integrations (CRM, Calendar) based on their next_sync_at timestamp. The scheduler
runs every minute and checks for integrations due for sync.

Key features:
- Background asyncio task for continuous scheduling
- Queries integration_sync_state table for due syncs
- Executes syncs in parallel for efficiency
- Graceful error handling - errors don't stop the scheduler
- Singleton pattern for consistent instance management
- Lifecycle management (start/stop) for FastAPI integration

Usage:
    # In FastAPI startup
    scheduler = get_sync_scheduler()
    await scheduler.start()

    # In FastAPI shutdown
    await scheduler.stop()
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.integrations.deep_sync import get_deep_sync_service
from src.integrations.domain import IntegrationType

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Background scheduler for recurring integration sync.

    Runs every minute to check for integrations due for sync based on
    their next_sync_at timestamp. Executes syncs asynchronously with
    graceful error handling.
    """

    def __init__(self, interval_seconds: int = 60) -> None:
        """Initialize the sync scheduler.

        Args:
            interval_seconds: How often to check for due syncs (default 60 seconds).
        """
        self._interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background scheduler.

        Creates an asyncio task that runs the scheduler loop.
        If already running, returns immediately.

        Logs a startup message for observability.
        """
        if self._running:
            logger.debug("Sync scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Sync scheduler started")

    async def stop(self) -> None:
        """Stop the background scheduler.

        Cancels the scheduler task and waits for cancellation to complete.
        If not running, returns immediately.

        Logs a shutdown message for observability.
        """
        if not self._running:
            logger.debug("Sync scheduler not running")
            return

        self._running = False

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        logger.info("Sync scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop.

        Runs continuously while _running is True, processing due syncs
        and sleeping for the configured interval. Errors are caught and
        logged but don't stop the loop.

        This method runs in a background asyncio task created by start().
        """
        while self._running:
            try:
                await self._process_due_syncs()
            except Exception:
                # Log but don't re-raise - scheduler should continue running
                logger.exception("Error in scheduler loop")

            await asyncio.sleep(self._interval_seconds)

    async def _process_due_syncs(self) -> None:
        """Process all integrations due for sync.

        Queries the integration_sync_state table for integrations where:
        - next_sync_at <= now
        - last_sync_status = 'success'

        For each due sync, validates the integration_type and executes
        the appropriate sync method:
        - SALESFORCE/HUBSPOT: sync_crm_to_aria()
        - GOOGLE_CALENDAR/OUTLOOK: sync_calendar()

        All syncs are executed in parallel using asyncio.gather() for
        efficiency. Exceptions are collected but don't stop other syncs.

        Logs the count of due syncs and success/failure counts.
        """
        now = datetime.now(UTC)

        try:
            # Query for due syncs
            client = SupabaseClient.get_client()
            response = (
                client.table("integration_sync_state")
                .select("*")
                .lte("next_sync_at", now.isoformat())
                .eq("last_sync_status", "success")
                .execute()
            )

            due_syncs = response.data if response.data else []

            if not due_syncs:
                return

            logger.info(
                "Processing due syncs",
                extra={"count": len(due_syncs)},
            )

            # Build sync tasks
            sync_tasks = []
            sync_service = get_deep_sync_service()

            for sync_state in due_syncs:
                # Type narrowing: treat sync_state as dict[str, Any]
                state = cast(dict[str, Any], sync_state)
                user_id = state.get("user_id")
                integration_type_str = state.get("integration_type")

                if not user_id or not integration_type_str:
                    logger.warning(
                        "Skipping sync state with missing user_id or integration_type",
                        extra={"sync_state": state},
                    )
                    continue

                # Type narrowing: user_id and integration_type_str are now str
                user_id_str = cast(str, user_id)
                integration_type_value = cast(str, integration_type_str)

                # Validate integration_type enum
                try:
                    integration_type = IntegrationType(integration_type_value)
                except ValueError:
                    logger.warning(
                        "Invalid integration_type in sync state",
                        extra={"integration_type": integration_type_value},
                    )
                    continue

                # Create sync task based on integration type
                if integration_type in (IntegrationType.SALESFORCE, IntegrationType.HUBSPOT):
                    task = sync_service.sync_crm_to_aria(user_id_str, integration_type)
                    sync_tasks.append(task)
                elif integration_type in (
                    IntegrationType.GOOGLE_CALENDAR,
                    IntegrationType.OUTLOOK,
                ):
                    task = sync_service.sync_calendar(user_id_str, integration_type)
                    sync_tasks.append(task)
                else:
                    logger.debug(
                        "Skipping unsupported integration type for scheduled sync",
                        extra={"integration_type": integration_type.value},
                    )

            # Execute all syncs in parallel
            if sync_tasks:
                results = await asyncio.gather(*sync_tasks, return_exceptions=True)

                # Count successes and failures
                success_count = sum(1 for r in results if not isinstance(r, Exception))
                failure_count = len(results) - success_count

                logger.info(
                    "Completed scheduled syncs",
                    extra={
                        "total": len(results),
                        "success": success_count,
                        "failed": failure_count,
                    },
                )

        except Exception:
            # Log but don't raise - scheduler should continue
            logger.exception("Failed to process due syncs")


# Singleton instance
_sync_scheduler: SyncScheduler | None = None


def get_sync_scheduler() -> SyncScheduler:
    """Get or create the sync scheduler singleton.

    Returns:
        The shared SyncScheduler instance.

    Example:
        scheduler = get_sync_scheduler()
        await scheduler.start()
    """
    global _sync_scheduler
    if _sync_scheduler is None:
        _sync_scheduler = SyncScheduler()
    return _sync_scheduler
