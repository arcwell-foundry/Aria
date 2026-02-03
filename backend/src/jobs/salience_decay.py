"""Background job for daily salience decay updates.

This job should be scheduled to run once per day (e.g., via cron or
a task scheduler). It recalculates salience for all user memories
based on time elapsed since last access.
"""

import logging
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.memory.salience import SalienceService

logger = logging.getLogger(__name__)


async def run_salience_decay_job() -> dict[str, Any]:
    """Run the daily salience decay update for all users.

    Fetches all users and updates their memory salience values.
    Continues processing even if individual users fail.

    Returns:
        Summary dict with users_processed, records_updated, and errors.
    """
    db = SupabaseClient.get_client()
    salience_service = SalienceService(db_client=db)

    # Get all user IDs
    users_result = db.table("user_profiles").select("id").execute()
    users = cast(list[dict[str, Any]], users_result.data or [])

    total_updated = 0
    errors = 0

    for user in users:
        user_id = cast(str, user["id"])
        try:
            updated = await salience_service.update_all_salience(user_id)
            total_updated += updated
            logger.info(
                f"Updated salience for user {user_id}",
                extra={"user_id": user_id, "records_updated": updated},
            )
        except Exception as e:
            errors += 1
            logger.error(
                f"Failed to update salience for user {user_id}",
                extra={"user_id": user_id, "error": str(e)},
            )

    result = {
        "users_processed": len(users),
        "records_updated": total_updated,
        "errors": errors,
    }

    logger.info("Salience decay job completed", extra=result)
    return result
