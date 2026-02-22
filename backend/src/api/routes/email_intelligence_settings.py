"""Email intelligence settings API routes for ARIA.

Users can manage their email intelligence settings including:
- VIP contacts (always get immediate drafts + alerts)
- Excluded senders (never get drafts)
- Auto-draft behavior (on/off)
- Draft timing (overnight vs real-time)
- Learning mode status (read-only)
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/email-intelligence", tags=["settings"])


class EmailIntelligenceSettings(BaseModel):
    """Response model for email intelligence settings."""

    auto_draft_enabled: bool = True
    draft_timing: str = "overnight"  # "overnight" | "realtime"
    vip_contacts: list[str] = []
    excluded_senders: list[str] = []


class EmailIntelligenceSettingsUpdate(BaseModel):
    """Request model for updating email intelligence settings."""

    auto_draft_enabled: bool | None = None
    draft_timing: str | None = None
    vip_contacts: list[str] | None = None
    excluded_senders: list[str] | None = None


class EmailIntelligenceSettingsResponse(BaseModel):
    """Full response including learning mode status."""

    auto_draft_enabled: bool
    draft_timing: str
    vip_contacts: list[str]
    excluded_senders: list[str]
    learning_mode_active: bool
    learning_mode_day: int | None = None
    email_provider: str | None = None
    email_connected: bool = False


class EmailIntelligenceSettingsService:
    """Service for managing email intelligence settings.

    Settings are stored in user_settings.preferences JSONB field,
    using keys that the email_analyzer already reads (vip_contacts, etc).
    """

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def get_settings(self, user_id: str) -> dict[str, Any]:
        """Get email intelligence settings for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with all email intelligence settings.
        """
        logger.info("Fetching email intelligence settings", extra={"user_id": user_id})

        try:
            result = (
                self._db.table("user_settings")
                .select("preferences, integrations")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            prefs: dict[str, Any] = {}
            integrations: dict[str, Any] = {}

            if result and result.data:
                settings = cast(dict[str, Any], result.data)
                prefs = settings.get("preferences", {}) or {}
                integrations = settings.get("integrations", {}) or {}

            # Extract email intelligence settings
            auto_draft_enabled = prefs.get("auto_draft_enabled", True)
            draft_timing = prefs.get("draft_timing", "overnight")
            vip_contacts = prefs.get("vip_contacts", [])
            excluded_senders = prefs.get("excluded_senders", [])

            # Learning mode from integrations.email
            email_config = integrations.get("email", {}) or {}
            learning_mode = email_config.get("learning_mode", False)
            learning_start = email_config.get("learning_mode_start_date")
            transition_date = email_config.get("full_mode_transition_date")

            learning_mode_active = bool(learning_mode and not transition_date)
            learning_mode_day: int | None = None

            if learning_mode_active and learning_start:
                from datetime import UTC, datetime

                try:
                    start = datetime.fromisoformat(
                        learning_start.replace("Z", "+00:00")
                    )
                    learning_mode_day = (datetime.now(UTC) - start).days + 1
                except (ValueError, AttributeError):
                    learning_mode_day = None

            # Email connection status
            email_provider: str | None = None
            email_connected = False

            # Check user_integrations for email connection
            try:
                int_result = (
                    self._db.table("user_integrations")
                    .select("integration_type, status")
                    .eq("user_id", user_id)
                    .in_("integration_type", ["gmail", "outlook"])
                    .execute()
                )
                if int_result and int_result.data:
                    for row in int_result.data:
                        if row.get("status") == "active":
                            email_provider = row["integration_type"]
                            email_connected = True
                            break
            except Exception as e:
                logger.warning(
                    "Failed to check email connection: %s", e
                )

            return {
                "auto_draft_enabled": auto_draft_enabled,
                "draft_timing": draft_timing,
                "vip_contacts": vip_contacts if isinstance(vip_contacts, list) else [],
                "excluded_senders": excluded_senders if isinstance(excluded_senders, list) else [],
                "learning_mode_active": learning_mode_active,
                "learning_mode_day": learning_mode_day,
                "email_provider": email_provider,
                "email_connected": email_connected,
            }

        except Exception:
            logger.exception(
                "Error fetching email intelligence settings",
                extra={"user_id": user_id},
            )
            raise

    async def update_settings(
        self, user_id: str, data: EmailIntelligenceSettingsUpdate
    ) -> dict[str, Any]:
        """Update email intelligence settings.

        Args:
            user_id: The user's ID.
            data: Settings to update.

        Returns:
            Updated settings dict.
        """
        # Validate draft_timing
        if data.draft_timing is not None and data.draft_timing not in (
            "overnight",
            "realtime",
        ):
            raise ValueError("draft_timing must be 'overnight' or 'realtime'")

        # Build update dict from non-None fields
        update_data: dict[str, Any] = {}
        if data.auto_draft_enabled is not None:
            update_data["auto_draft_enabled"] = data.auto_draft_enabled
        if data.draft_timing is not None:
            update_data["draft_timing"] = data.draft_timing
        if data.vip_contacts is not None:
            update_data["vip_contacts"] = data.vip_contacts
        if data.excluded_senders is not None:
            update_data["excluded_senders"] = data.excluded_senders

        if not update_data:
            return await self.get_settings(user_id)

        try:
            # Get current user_settings
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                settings = cast(dict[str, Any], result.data)
                prefs = settings.get("preferences", {}) or {}
                prefs.update(update_data)

                self._db.table("user_settings").update(
                    {"preferences": prefs}
                ).eq("user_id", user_id).execute()
            else:
                # Create new user_settings record
                self._db.table("user_settings").insert(
                    {
                        "user_id": user_id,
                        "preferences": update_data,
                        "integrations": {},
                    }
                ).execute()

            logger.info(
                "Email intelligence settings updated",
                extra={
                    "user_id": user_id,
                    "updated_fields": list(update_data.keys()),
                },
            )

            return await self.get_settings(user_id)

        except Exception:
            logger.exception(
                "Error updating email intelligence settings",
                extra={"user_id": user_id},
            )
            raise


def _get_service() -> EmailIntelligenceSettingsService:
    return EmailIntelligenceSettingsService()


@router.get("", response_model=EmailIntelligenceSettingsResponse)
async def get_email_intelligence_settings(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current user's email intelligence settings.

    Returns auto-draft behavior, draft timing, VIP contacts,
    excluded senders, learning mode status, and email connection info.
    """
    service = _get_service()
    try:
        return await service.get_settings(current_user.id)
    except Exception as e:
        logger.exception("Error fetching email intelligence settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch email intelligence settings",
        ) from e


@router.patch("", response_model=EmailIntelligenceSettingsResponse)
async def update_email_intelligence_settings(
    data: EmailIntelligenceSettingsUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update email intelligence settings.

    Accepts partial updates for auto_draft_enabled, draft_timing,
    vip_contacts, and excluded_senders.
    """
    service = _get_service()
    try:
        return await service.update_settings(current_user.id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating email intelligence settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update email intelligence settings",
        ) from e
