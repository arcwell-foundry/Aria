"""ARIA configuration service.

Manages ARIA role, personality, domain focus, competitor watchlist,
and communication preferences. Config stored in
user_settings.preferences.aria_config JSONB.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.aria_config import ARIAConfigUpdate, ARIARole, PersonalityTraits

logger = logging.getLogger(__name__)

_DEFAULT_PERSONALITY = PersonalityTraits().model_dump()


def _calibration_to_personality(calibration: dict[str, Any]) -> dict[str, Any]:
    """Map PersonalityCalibration values to PersonalityTraits.

    Calibration has: directness, warmth, assertiveness, detail_orientation, formality
    Config has: proactiveness, verbosity, formality, assertiveness

    Mapping:
    - assertiveness -> assertiveness (direct)
    - formality -> formality (direct)
    - detail_orientation -> verbosity (high detail = high verbosity)
    - proactiveness has no calibration source, keep default 0.7

    Args:
        calibration: Dict of PersonalityCalibration values.

    Returns:
        Dict matching PersonalityTraits fields.
    """
    result = dict(_DEFAULT_PERSONALITY)
    if "assertiveness" in calibration:
        result["assertiveness"] = calibration["assertiveness"]
    if "formality" in calibration:
        result["formality"] = calibration["formality"]
    if "detail_orientation" in calibration:
        result["verbosity"] = calibration["detail_orientation"]
    return result


class ARIAConfigService:
    """Service for managing ARIA configuration."""

    def __init__(self) -> None:
        """Initialize with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_config(self, user_id: str) -> dict[str, Any]:
        """Get ARIA config, building defaults from calibration for new users.

        Args:
            user_id: The user's ID.

        Returns:
            ARIA config dict matching ARIAConfigResponse schema.
        """
        prefs = await self._get_preferences(user_id)
        aria_config = prefs.get("aria_config")

        if aria_config:
            return cast(dict[str, Any], aria_config)

        calibration = self._extract_calibration(prefs)
        personality = _calibration_to_personality(calibration)

        default_config: dict[str, Any] = {
            "role": ARIARole.SALES_OPS.value,
            "custom_role_description": None,
            "personality": personality,
            "domain_focus": {
                "therapeutic_areas": [],
                "modalities": [],
                "geographies": [],
            },
            "competitor_watchlist": [],
            "communication": {
                "preferred_channels": ["in_app"],
                "notification_frequency": "balanced",
                "response_depth": "moderate",
                "briefing_time": "08:00",
            },
            "personality_defaults": personality,
            "updated_at": None,
        }
        return default_config

    async def update_config(self, user_id: str, data: ARIAConfigUpdate) -> dict[str, Any]:
        """Update ARIA configuration.

        Args:
            user_id: The user's ID.
            data: Config update data.

        Returns:
            Updated config dict.
        """
        prefs = await self._get_preferences(user_id)

        existing_config = prefs.get("aria_config", {})
        personality_defaults = existing_config.get("personality_defaults")
        if not personality_defaults:
            calibration = self._extract_calibration(prefs)
            personality_defaults = _calibration_to_personality(calibration)

        config_data = data.model_dump(mode="json")
        config_data["personality_defaults"] = personality_defaults
        config_data["updated_at"] = datetime.now(UTC).isoformat()

        prefs["aria_config"] = config_data
        self._db.table("user_settings").update({"preferences": prefs}).eq(
            "user_id", user_id
        ).execute()

        logger.info(
            "ARIA config updated",
            extra={"user_id": user_id, "role": data.role.value},
        )
        return config_data

    async def reset_personality(self, user_id: str) -> dict[str, Any]:
        """Reset personality sliders to calibrated defaults.

        Args:
            user_id: The user's ID.

        Returns:
            Updated config dict with reset personality.
        """
        prefs = await self._get_preferences(user_id)
        aria_config = prefs.get("aria_config", {})

        personality_defaults = aria_config.get("personality_defaults")
        if not personality_defaults:
            calibration = self._extract_calibration(prefs)
            personality_defaults = _calibration_to_personality(calibration)

        aria_config["personality"] = dict(personality_defaults)
        aria_config["personality_defaults"] = personality_defaults
        aria_config["updated_at"] = datetime.now(UTC).isoformat()
        prefs["aria_config"] = aria_config

        self._db.table("user_settings").update({"preferences": prefs}).eq(
            "user_id", user_id
        ).execute()

        logger.info("ARIA personality reset to defaults", extra={"user_id": user_id})
        return cast(dict[str, Any], aria_config)

    async def _get_preferences(self, user_id: str) -> dict[str, Any]:
        """Read user_settings.preferences for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Preferences dict (may be empty).
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                return cast(dict[str, Any], row.get("preferences", {}) or {})
        except Exception as e:
            logger.warning("Failed to read preferences: %s", e)
        return {}

    def _extract_calibration(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """Extract personality calibration from Digital Twin data.

        Args:
            prefs: Full preferences dict.

        Returns:
            Calibration dict (may be empty).
        """
        dt = prefs.get("digital_twin", {})
        calibration: dict[str, Any] = dt.get("personality_calibration", {})
        return calibration


_service: ARIAConfigService | None = None


def get_aria_config_service() -> ARIAConfigService:
    """Get or create service singleton.

    Returns:
        The ARIAConfigService singleton instance.
    """
    global _service  # noqa: PLW0603
    if _service is None:
        _service = ARIAConfigService()
    return _service
