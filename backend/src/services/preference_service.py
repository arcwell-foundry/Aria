"""Preference service for user preferences management.

Handles CRUD operations for user preferences including:
- Briefing time and notification settings
- Meeting brief lead hours
- Communication tone preferences
- Tracked competitors
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.preferences import PreferenceUpdate

logger = logging.getLogger(__name__)


class PreferenceService:
    """Service for managing user preferences."""

    def __init__(self) -> None:
        """Initialize preference service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user preferences, creating defaults if not found.

        Args:
            user_id: The user's ID.

        Returns:
            Preference dict.
        """
        result = (
            self._db.table("user_preferences")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if result.data is None:
            logger.info(
                "No preferences found, creating defaults",
                extra={"user_id": user_id},
            )
            return await self._create_default_preferences(user_id)

        logger.info("Preferences retrieved", extra={"user_id": user_id})
        return cast(dict[str, Any], result.data)

    async def update_preferences(
        self, user_id: str, data: PreferenceUpdate
    ) -> dict[str, Any]:
        """Update user preferences.

        Args:
            user_id: The user's ID.
            data: Preference update data.

        Returns:
            Updated preference dict.
        """
        # First ensure preferences exist
        current_prefs = await self.get_preferences(user_id)

        # Build update dict, excluding None values
        update_data: dict[str, Any] = {}
        for field, value in data.model_dump().items():
            if value is not None:
                # Handle enum values by extracting .value
                if hasattr(value, "value"):
                    update_data[field] = value.value
                else:
                    update_data[field] = value

        # If no fields to update, return current prefs
        if not update_data:
            logger.info(
                "No preference changes to apply",
                extra={"user_id": user_id},
            )
            return current_prefs

        # Set updated_at timestamp
        update_data["updated_at"] = datetime.now(UTC).isoformat()

        result = (
            self._db.table("user_preferences")
            .update(update_data)
            .eq("user_id", user_id)
            .execute()
        )

        logger.info(
            "Preferences updated",
            extra={
                "user_id": user_id,
                "updated_fields": list(update_data.keys()),
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def _create_default_preferences(self, user_id: str) -> dict[str, Any]:
        """Create default preferences for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Created preference dict with defaults.
        """
        result = (
            self._db.table("user_preferences")
            .insert({"user_id": user_id})
            .execute()
        )

        logger.info(
            "Created default preferences",
            extra={"user_id": user_id},
        )

        return cast(dict[str, Any], result.data[0])


# Singleton instance
_preference_service: PreferenceService | None = None


def get_preference_service() -> PreferenceService:
    """Get or create preference service singleton.

    Returns:
        The PreferenceService singleton instance.
    """
    global _preference_service
    if _preference_service is None:
        _preference_service = PreferenceService()
    return _preference_service
