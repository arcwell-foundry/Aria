"""Learning Mode Service for email drafting.

Manages the first-week learning mode that restricts draft generation
to top contacts and tracks user interactions for the learning loop.

Learning Mode Thresholds:
- Duration: 7 days from first email connection
- OR: 20 draft interactions (whichever comes first)
- Contact limit: Top 10 contacts by email frequency from bootstrap
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Learning mode configuration
LEARNING_MODE_DURATION_DAYS = 7
LEARNING_MODE_INTERACTION_THRESHOLD = 20
TOP_CONTACTS_LIMIT = 10


class LearningModeConfig(BaseModel):
    """Configuration for learning mode stored in user_settings."""

    learning_mode: bool = True
    learning_mode_start_date: str | None = None
    draft_interaction_count: int = 0
    top_contacts: list[str] = []
    full_mode_transition_date: str | None = None


# Import Pydantic after the docstring
from pydantic import BaseModel


class LearningModeService:
    """Manages learning mode state and transitions for email drafting.

    Learning mode provides a graduated onboarding experience:
    - First 7 days (or 20 draft interactions): Only draft for top 10 contacts
    - After threshold reached: Full inbox drafting enabled

    This allows ARIA to learn from user feedback before handling
    all incoming emails.
    """

    def __init__(self) -> None:
        """Initialize with database client."""
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def activate_learning_mode(self, user_id: str) -> dict[str, Any]:
        """Activate learning mode after email bootstrap completes.

        Called at the end of email_bootstrap.run_bootstrap().

        Args:
            user_id: The user whose learning mode to activate.

        Returns:
            Dict with activation status and config.
        """
        try:
            # Get top contacts from email bootstrap
            top_contacts = await self._get_top_contacts_from_bootstrap(user_id)

            # Build learning mode config
            now = datetime.now(UTC).isoformat()
            config = {
                "learning_mode": True,
                "learning_mode_start_date": now,
                "draft_interaction_count": 0,
                "top_contacts": top_contacts[:TOP_CONTACTS_LIMIT],
                "full_mode_transition_date": None,
            }

            # Update user_settings.integrations.email
            await self._update_learning_mode_config(user_id, config)

            logger.info(
                "LEARNING_MODE: Activated for user %s with %d top contacts",
                user_id,
                len(config["top_contacts"]),
            )

            return {
                "success": True,
                "learning_mode": True,
                "top_contacts_count": len(config["top_contacts"]),
                "start_date": now,
            }

        except Exception as e:
            logger.error(
                "LEARNING_MODE: Failed to activate for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            return {"success": False, "error": str(e)}

    async def is_learning_mode_active(self, user_id: str) -> bool:
        """Check if learning mode is still active for a user.

        Learning mode ends when EITHER:
        - 7 days have passed since activation
        - 20 draft interactions have occurred

        Args:
            user_id: The user to check.

        Returns:
            True if learning mode is active, False if in full mode.
        """
        try:
            config = await self._get_learning_mode_config(user_id)

            if not config or not config.get("learning_mode"):
                # No learning mode config = full mode
                return False

            # Check if already transitioned
            if config.get("full_mode_transition_date"):
                return False

            # Check time threshold (7 days)
            start_date_str = config.get("learning_mode_start_date")
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                days_elapsed = (datetime.now(UTC) - start_date).days
                if days_elapsed >= LEARNING_MODE_DURATION_DAYS:
                    await self._transition_to_full_mode(user_id, "time_threshold")
                    return False

            # Check interaction threshold (20 drafts)
            interaction_count = config.get("draft_interaction_count", 0)
            if interaction_count >= LEARNING_MODE_INTERACTION_THRESHOLD:
                await self._transition_to_full_mode(user_id, "interaction_threshold")
                return False

            return True

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error checking status for user %s: %s",
                user_id,
                e,
            )
            # Default to learning mode on error (safer)
            return True

    async def get_top_contacts(self, user_id: str) -> list[str]:
        """Get the top contacts for learning mode.

        Args:
            user_id: The user whose top contacts to retrieve.

        Returns:
            List of top contact email addresses (up to 10).
        """
        try:
            config = await self._get_learning_mode_config(user_id)
            if config and config.get("top_contacts"):
                return config.get("top_contacts", [])[:TOP_CONTACTS_LIMIT]

            # Fallback: derive from bootstrap if config missing
            return await self._get_top_contacts_from_bootstrap(user_id)

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error getting top contacts for user %s: %s",
                user_id,
                e,
            )
            return []

    async def increment_draft_interaction(self, user_id: str) -> int:
        """Increment the draft interaction counter.

        Called when a draft is generated during learning mode.

        Args:
            user_id: The user whose counter to increment.

        Returns:
            New interaction count.
        """
        try:
            config = await self._get_learning_mode_config(user_id)
            if not config:
                return 0

            new_count = config.get("draft_interaction_count", 0) + 1
            config["draft_interaction_count"] = new_count

            await self._update_learning_mode_config(user_id, config)

            logger.debug(
                "LEARNING_MODE: Incremented interaction count for user %s to %d",
                user_id,
                new_count,
            )

            return new_count

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error incrementing counter for user %s: %s",
                user_id,
                e,
            )
            return 0

    def get_learning_mode_note(self) -> str:
        """Get the note to append to drafts during learning mode.

        Returns:
            Note string explaining learning mode status.
        """
        return "LEARNING_MODE: ARIA is learning your style. Please review carefully."

    async def is_contact_in_top_list(
        self,
        user_id: str,
        contact_email: str,
    ) -> bool:
        """Check if a contact is in the user's top contacts list.

        Args:
            user_id: The user to check.
            contact_email: The contact email to look for.

        Returns:
            True if contact is in top list, False otherwise.
        """
        top_contacts = await self.get_top_contacts(user_id)
        contact_lower = contact_email.lower().strip()

        for contact in top_contacts:
            if contact.lower().strip() == contact_lower:
                return True

        return False

    async def get_learning_mode_status(self, user_id: str) -> dict[str, Any]:
        """Get comprehensive learning mode status for a user.

        Args:
            user_id: The user to check.

        Returns:
            Dict with learning mode status details.
        """
        try:
            config = await self._get_learning_mode_config(user_id)
            is_active = await self.is_learning_mode_active(user_id)

            if not config:
                return {
                    "active": False,
                    "reason": "not_configured",
                    "top_contacts": [],
                    "interaction_count": 0,
                    "days_remaining": 0,
                    "interactions_remaining": 0,
                }

            start_date_str = config.get("learning_mode_start_date")
            days_remaining = 0
            interactions_remaining = 0

            if is_active and start_date_str:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                days_elapsed = (datetime.now(UTC) - start_date).days
                days_remaining = max(0, LEARNING_MODE_DURATION_DAYS - days_elapsed)

                interaction_count = config.get("draft_interaction_count", 0)
                interactions_remaining = max(
                    0, LEARNING_MODE_INTERACTION_THRESHOLD - interaction_count
                )

            return {
                "active": is_active,
                "start_date": config.get("learning_mode_start_date"),
                "days_remaining": days_remaining,
                "interaction_count": config.get("draft_interaction_count", 0),
                "interactions_remaining": interactions_remaining,
                "top_contacts": config.get("top_contacts", []),
                "transition_date": config.get("full_mode_transition_date"),
            }

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error getting status for user %s: %s",
                user_id,
                e,
            )
            return {
                "active": True,
                "reason": "error",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    async def _get_learning_mode_config(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve learning mode config from user_settings.

        Args:
            user_id: The user whose config to retrieve.

        Returns:
            Learning mode config dict or None if not found.
        """
        try:
            result = (
                self._db.table("user_settings")
                .select("integrations")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                integrations = result.data.get("integrations", {})
                return integrations.get("email", {}).get("learning_mode_config")

            return None

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error getting config for user %s: %s",
                user_id,
                e,
            )
            return None

    async def _update_learning_mode_config(
        self,
        user_id: str,
        config: dict[str, Any],
    ) -> None:
        """Update learning mode config in user_settings.

        Args:
            user_id: The user whose config to update.
            config: The new learning mode config.
        """
        try:
            # Get current integrations
            result = (
                self._db.table("user_settings")
                .select("integrations")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            current_integrations: dict[str, Any] = {}
            if result and result.data:
                current_integrations = result.data.get("integrations", {}) or {}

            # Update email.learning_mode_config
            email_config = current_integrations.get("email", {})
            email_config["learning_mode_config"] = config
            current_integrations["email"] = email_config

            # Save back
            (
                self._db.table("user_settings")
                .update({"integrations": current_integrations})
                .eq("user_id", user_id)
                .execute()
            )

        except Exception as e:
            logger.error(
                "LEARNING_MODE: Error updating config for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            raise

    async def _get_top_contacts_from_bootstrap(self, user_id: str) -> list[str]:
        """Derive top contacts from email bootstrap data.

        Queries memory_semantic for contacts discovered during bootstrap,
        sorted by interaction count.

        Args:
            user_id: The user whose top contacts to find.

        Returns:
            List of top contact email addresses.
        """
        try:
            # Query contacts from memory_semantic (stored by email_bootstrap)
            result = (
                self._db.table("memory_semantic")
                .select("metadata")
                .eq("user_id", user_id)
                .eq("source", "email_bootstrap")
                .like("fact", "Contact:%")
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )

            if not result or not result.data:
                return []

            # Extract and sort by interaction count
            contacts: list[tuple[str, int]] = []
            for row in result.data:
                metadata = row.get("metadata", {})
                email = metadata.get("email", "")
                interaction_count = metadata.get("interaction_count", 0)
                if email:
                    contacts.append((email.lower(), interaction_count))

            # Sort by interaction count descending
            contacts.sort(key=lambda x: x[1], reverse=True)

            return [email for email, _ in contacts[:TOP_CONTACTS_LIMIT]]

        except Exception as e:
            logger.warning(
                "LEARNING_MODE: Error getting top contacts from bootstrap for user %s: %s",
                user_id,
                e,
            )
            return []

    async def _transition_to_full_mode(
        self,
        user_id: str,
        reason: str,
    ) -> None:
        """Transition user from learning mode to full mode.

        Args:
            user_id: The user to transition.
            reason: Why the transition occurred (time_threshold/interaction_threshold).
        """
        try:
            config = await self._get_learning_mode_config(user_id)
            if not config:
                return

            config["learning_mode"] = False
            config["full_mode_transition_date"] = datetime.now(UTC).isoformat()

            await self._update_learning_mode_config(user_id, config)

            logger.info(
                "LEARNING_MODE: Transitioned user %s to full mode (reason: %s)",
                user_id,
                reason,
            )

            # Record episodic memory for the transition
            try:
                from src.memory.episodic import Episode, EpisodicMemory
                import uuid

                now = datetime.now(UTC)
                episode = Episode(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    event_type="learning_mode_transition",
                    content=(
                        f"ARIA completed learning mode and is now drafting for all contacts. "
                        f"Transition reason: {reason}. "
                        f"Total draft interactions during learning: {config.get('draft_interaction_count', 0)}"
                    ),
                    participants=[],
                    occurred_at=now,
                    recorded_at=now,
                    context={
                        "transition_reason": reason,
                        "draft_interaction_count": config.get("draft_interaction_count", 0),
                        "top_contacts_count": len(config.get("top_contacts", [])),
                    },
                )
                await EpisodicMemory().store_episode(episode)
            except Exception as e:
                logger.warning(
                    "LEARNING_MODE: Failed to record episodic for transition: %s",
                    e,
                )

        except Exception as e:
            logger.error(
                "LEARNING_MODE: Error transitioning user %s to full mode: %s",
                user_id,
                e,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_service: LearningModeService | None = None


def get_learning_mode_service() -> LearningModeService:
    """Get the singleton LearningModeService instance."""
    global _service
    if _service is None:
        _service = LearningModeService()
    return _service
