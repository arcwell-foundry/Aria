"""CRM Connectivity Check Utility.

Provides a simple function to check if a user has an active CRM integration.
Uses the centralized validator pattern from integrations/validators.py.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# CRM integration types supported
_CRM_TYPES = ["salesforce", "hubspot", "dynamics"]


async def get_crm_status(user_id: str, db: Any) -> dict[str, Any]:
    """Check if user has CRM connected and what type.

    Uses status-aware query (not just row existence).

    Args:
        user_id: User UUID.
        db: Supabase client.

    Returns:
        Dict with connected (bool) and type (str or None).
    """
    try:
        integration = (
            db.table("user_integrations")
            .select("integration_type, status")
            .eq("user_id", user_id)
            .in_("integration_type", _CRM_TYPES)
            .eq("status", "active")
            .limit(1)
            .execute()
        )

        if integration.data:
            return {
                "connected": True,
                "type": integration.data[0]["integration_type"],
            }

        return {"connected": False, "type": None}

    except Exception as e:
        logger.warning("[CRM] Status check failed for user %s: %s", user_id, e)
        return {"connected": False, "type": None}
