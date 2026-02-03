"""Attendee profile service for caching researched profiles.

Manages the shared cache of attendee research data.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class AttendeeProfileService:
    """Service for managing cached attendee profiles."""

    def __init__(self) -> None:
        """Initialize attendee profile service."""
        self._db = SupabaseClient.get_client()

    async def get_profile(self, email: str) -> dict[str, Any] | None:
        """Get a profile by email.

        Args:
            email: Attendee email address.

        Returns:
            Profile dict if found, None otherwise.
        """
        result = (
            self._db.table("attendee_profiles")
            .select("*")
            .eq("email", email.lower())
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def get_profiles_batch(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        """Get multiple profiles by email.

        Args:
            emails: List of email addresses.

        Returns:
            Dict mapping email to profile data.
        """
        if not emails:
            return {}

        normalized_emails = [e.lower() for e in emails]

        result = (
            self._db.table("attendee_profiles")
            .select("*")
            .in_("email", normalized_emails)
            .execute()
        )

        profiles: list[dict[str, Any]] = cast(list[dict[str, Any]], result.data or [])
        return {p["email"]: p for p in profiles}

    async def upsert_profile(
        self,
        email: str,
        name: str | None = None,
        title: str | None = None,
        company: str | None = None,
        linkedin_url: str | None = None,
        profile_data: dict[str, Any] | None = None,
        research_status: str = "completed",
    ) -> dict[str, Any]:
        """Create or update an attendee profile.

        Args:
            email: Attendee email address.
            name: Full name.
            title: Job title.
            company: Company name.
            linkedin_url: LinkedIn profile URL.
            profile_data: Additional profile data.
            research_status: Research status.

        Returns:
            Upserted profile dict.
        """
        data: dict[str, Any] = {
            "email": email.lower(),
            "research_status": research_status,
            "last_researched_at": datetime.now(UTC).isoformat(),
        }

        if name is not None:
            data["name"] = name
        if title is not None:
            data["title"] = title
        if company is not None:
            data["company"] = company
        if linkedin_url is not None:
            data["linkedin_url"] = linkedin_url
        if profile_data is not None:
            data["profile_data"] = profile_data

        result = self._db.table("attendee_profiles").upsert(data, on_conflict="email").execute()

        logger.info(
            "Upserted attendee profile",
            extra={"email": email.lower(), "research_status": research_status},
        )

        return cast(dict[str, Any], result.data[0])

    async def is_stale(self, email: str, max_age_days: int = 7) -> bool:
        """Check if a profile needs refresh.

        Args:
            email: Attendee email address.
            max_age_days: Maximum age in days before considered stale.

        Returns:
            True if profile is stale or doesn't exist.
        """
        profile = await self.get_profile(email)

        if not profile:
            return True

        last_researched = profile.get("last_researched_at")
        if not last_researched:
            return True

        # Parse ISO format timestamp
        if isinstance(last_researched, str):
            last_researched_dt = datetime.fromisoformat(last_researched.replace("Z", "+00:00"))
        else:
            last_researched_dt = last_researched

        age = datetime.now(UTC) - last_researched_dt
        return age > timedelta(days=max_age_days)

    async def mark_not_found(self, email: str) -> dict[str, Any]:
        """Mark a profile as not found (couldn't research).

        Args:
            email: Attendee email address.

        Returns:
            Updated profile dict.
        """
        return await self.upsert_profile(
            email=email,
            research_status="not_found",
        )


# Singleton instance
_attendee_profile_service: AttendeeProfileService | None = None


def get_attendee_profile_service() -> AttendeeProfileService:
    """Get or create attendee profile service singleton.

    Returns:
        The AttendeeProfileService singleton instance.
    """
    global _attendee_profile_service
    if _attendee_profile_service is None:
        _attendee_profile_service = AttendeeProfileService()
    return _attendee_profile_service
