"""Monitored entity service for auto-populating Scout signal scan targets.

Provides an upsert-based `ensure_entity()` method that hooks into lead
creation, onboarding enrichment, and ICP profile saves to automatically
populate the `monitored_entities` table used by Scout's signal scan job.
"""

import logging
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class MonitoredEntityService:
    """Manages the monitored_entities table for proactive signal scanning."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def ensure_entity(
        self,
        user_id: str,
        entity_type: str,
        entity_name: str,
        monitoring_config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Upsert a monitored entity for a user.

        Uses the UNIQUE(user_id, entity_type, entity_name) constraint to
        avoid duplicates. If the entity already exists, it is activated
        (is_active=True) if previously deactivated.

        Args:
            user_id: The user's UUID.
            entity_type: Entity type (e.g. "company", "competitor", "contact").
            entity_name: Human-readable entity name.
            monitoring_config: Optional JSON config for monitoring preferences.

        Returns:
            The upserted entity dict, or None on failure.
        """
        if not entity_name or not entity_name.strip():
            return None

        entity_name = entity_name.strip()

        try:
            row = {
                "user_id": user_id,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "monitoring_config": monitoring_config or {},
                "is_active": True,
            }

            result = (
                self._db.table("monitored_entities")
                .upsert(row, on_conflict="user_id,entity_type,entity_name")
                .execute()
            )

            if result.data:
                logger.info(
                    "Ensured monitored entity",
                    extra={
                        "user_id": user_id,
                        "entity_type": entity_type,
                        "entity_name": entity_name,
                    },
                )
                return result.data[0]

            return None

        except Exception:
            logger.warning(
                "Failed to ensure monitored entity: %s/%s for user %s",
                entity_type,
                entity_name,
                user_id,
                exc_info=True,
            )
            return None

    async def ensure_entities_batch(
        self,
        user_id: str,
        entity_type: str,
        entity_names: list[str],
    ) -> int:
        """Ensure multiple entities exist for a user.

        Args:
            user_id: The user's UUID.
            entity_type: Entity type for all entities.
            entity_names: List of entity names to ensure.

        Returns:
            Count of successfully upserted entities.
        """
        count = 0
        for name in entity_names:
            result = await self.ensure_entity(user_id, entity_type, name)
            if result:
                count += 1
        return count
