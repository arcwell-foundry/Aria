"""Admin memory backfill API route.

POST /admin/backfill-memory — Run retroactive memory backfill for all users.
"""

import logging

from fastapi import APIRouter

from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-backfill"])


@router.post("/backfill-memory")
async def backfill_memory() -> dict:
    """Run retroactive memory backfill for ALL users with data in ARIA.

    Iterates over all users found in email_scan_log, calendar_events,
    and meeting_debriefs. Routes their historical data through the
    universal memory_writer.

    Returns:
        Aggregate counts of items processed.
    """
    # TODO: restrict to admin role — add AdminUser dependency
    from src.services.memory_backfill import run_backfill

    db = get_supabase_client()
    totals = await run_backfill(db)
    return totals
