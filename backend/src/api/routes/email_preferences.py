"""Email preferences API routes for ARIA.

Users can manage their email preferences including:
- Weekly summary emails
- Feature announcements
- Security alerts (cannot be disabled)
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.core.exceptions import sanitize_error
from src.db.supabase import SupabaseClient
from src.models.preferences import EmailPreferencesResponse, EmailPreferencesUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/email-preferences", tags=["settings"])


class EmailPreferencesService:
    """Service for managing user email preferences.

    Email preferences are stored in user_settings.preferences.email_preferences.
    Security alerts cannot be disabled and will always return True.
    """

    def __init__(self) -> None:
        """Initialize email preferences service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_email_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user email preferences, creating defaults if not found.

        Args:
            user_id: The user's ID.

        Returns:
            Email preferences dict with user_id, weekly_summary,
            feature_announcements, and security_alerts (always True).
        """
        logger.info("Fetching email preferences", extra={"user_id": user_id})

        try:
            # Get user_settings record
            result = (
                self._db.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if result.data is None:
                logger.info(
                    "No user settings found, creating defaults",
                    extra={"user_id": user_id},
                )
                return await self._create_default_email_preferences(user_id)

            settings = cast(dict[str, Any], result.data)
            preferences = settings.get("preferences", {})
            email_prefs = preferences.get("email_preferences", {})

            # Return email preferences or defaults
            return {
                "user_id": user_id,
                "weekly_summary": email_prefs.get("weekly_summary", True),
                "feature_announcements": email_prefs.get("feature_announcements", True),
                "security_alerts": True,  # Always True, cannot be disabled
            }

        except Exception as e:
            # Check if it's a "no rows" error (PGRST116)
            if "PGRST116" in str(e):
                logger.info(
                    "No user settings found, creating defaults",
                    extra={"user_id": user_id},
                )
                return await self._create_default_email_preferences(user_id)
            logger.exception(
                "Error fetching email preferences",
                extra={"user_id": user_id},
            )
            raise

    async def update_email_preferences(
        self, user_id: str, data: EmailPreferencesUpdate
    ) -> dict[str, Any]:
        """Update user email preferences.

        Args:
            user_id: The user's ID.
            data: Email preference update data.

        Returns:
            Updated email preferences dict.

        Raises:
            ValueError: If attempting to disable security_alerts.
        """
        # Security alerts cannot be disabled
        if data.security_alerts is False:
            raise ValueError("Security alerts cannot be disabled")

        # Get current settings
        current_settings = await self.get_email_preferences(user_id)

        # Build update dict, excluding None values
        update_data: dict[str, Any] = {}
        if data.weekly_summary is not None:
            update_data["weekly_summary"] = data.weekly_summary
        if data.feature_announcements is not None:
            update_data["feature_announcements"] = data.feature_announcements

        # If no fields to update, return current prefs
        if not update_data:
            logger.info(
                "No email preference changes to apply",
                extra={"user_id": user_id},
            )
            return current_settings

        # Get current user_settings to merge preferences
        try:
            settings_result = (
                self._db.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if settings_result.data is None:
                # Create new settings
                return await self._create_default_email_preferences(user_id)

            settings = cast(dict[str, Any], settings_result.data)
            preferences = settings.get("preferences", {})

            # Merge email preferences
            email_prefs = preferences.get("email_preferences", {})
            email_prefs.update(update_data)

            # Update in database
            (
                self._db.table("user_settings")
                .update({"preferences": {**preferences, "email_preferences": email_prefs}})
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(
                "Email preferences updated",
                extra={
                    "user_id": user_id,
                    "updated_fields": list(update_data.keys()),
                },
            )

            # Return updated preferences
            return {
                "user_id": user_id,
                "weekly_summary": email_prefs.get("weekly_summary", True),
                "feature_announcements": email_prefs.get("feature_announcements", True),
                "security_alerts": True,  # Always True
            }

        except Exception:
            logger.exception(
                "Error updating email preferences",
                extra={"user_id": user_id},
            )
            raise

    async def _create_default_email_preferences(self, user_id: str) -> dict[str, Any]:
        """Create default email preferences for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Created email preferences dict with defaults (all True).
        """
        default_prefs = {
            "user_id": user_id,
            "weekly_summary": True,
            "feature_announcements": True,
            "security_alerts": True,  # Always True, cannot be disabled
        }

        try:
            # First check if user_settings exists
            existing = self._db.table("user_settings").select("*").eq("user_id", user_id).execute()

            if existing.data:
                # Update existing settings
                settings = cast(dict[str, Any], existing.data[0])
                preferences = settings.get("preferences", {})
                preferences["email_preferences"] = {
                    "weekly_summary": True,
                    "feature_announcements": True,
                }

                (
                    self._db.table("user_settings")
                    .update({"preferences": preferences})
                    .eq("user_id", user_id)
                    .execute()
                )
            else:
                # Create new settings with email preferences
                (
                    self._db.table("user_settings")
                    .insert(
                        {
                            "user_id": user_id,
                            "preferences": {
                                "email_preferences": {
                                    "weekly_summary": True,
                                    "feature_announcements": True,
                                }
                            },
                            "integrations": {},
                        }
                    )
                    .execute()
                )

            logger.info(
                "Created default email preferences",
                extra={"user_id": user_id},
            )

            return default_prefs

        except Exception:
            logger.exception(
                "Error creating default email preferences",
                extra={"user_id": user_id},
            )
            raise


def _get_service() -> EmailPreferencesService:
    """Get email preferences service instance."""
    return EmailPreferencesService()


@router.get("", response_model=EmailPreferencesResponse)
async def get_email_preferences(current_user: CurrentUser) -> dict[str, Any]:
    """Get current user's email preferences.

    Returns defaults if none exist. Security alerts cannot be disabled
    and will always return True.

    Args:
        current_user: The authenticated user.

    Returns:
        Email preferences dict with user_id, weekly_summary,
        feature_announcements, and security_alerts (always True).
    """
    service = _get_service()
    try:
        preferences = await service.get_email_preferences(current_user.id)
        logger.info(
            "Email preferences retrieved via API",
            extra={"user_id": current_user.id},
        )
        return preferences
    except Exception as e:
        logger.exception("Error fetching email preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch email preferences",
        ) from e


@router.patch("", response_model=EmailPreferencesResponse)
async def update_email_preferences(
    data: EmailPreferencesUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's email preferences.

    Accepts partial updates. Security alerts cannot be disabled
    and attempting to set them to False will return a 400 error.

    Args:
        data: Email preference update data.
        current_user: The authenticated user.

    Returns:
        Updated email preferences dict.
    """
    service = _get_service()
    try:
        preferences = await service.update_email_preferences(current_user.id, data)
        logger.info(
            "Email preferences updated via API",
            extra={"user_id": current_user.id},
        )
        return preferences
    except ValueError as e:
        logger.warning(
            "Email preferences update failed",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=sanitize_error(e)
        ) from e
    except Exception as e:
        logger.exception("Error updating email preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update email preferences",
        ) from e
