"""Meeting brief service for pre-meeting research.

Manages meeting brief CRUD operations and coordinates research generation.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

import anthropic

from src.agents.scout import ScoutAgent
from src.core.config import settings
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.services import notification_integration
from src.services.attendee_profile import AttendeeProfileService

logger = logging.getLogger(__name__)


class MeetingBriefService:
    """Service for managing pre-meeting research briefs."""

    def __init__(self) -> None:
        """Initialize meeting brief service."""
        self._db = SupabaseClient.get_client()

    async def get_brief(self, user_id: str, calendar_event_id: str) -> dict[str, Any] | None:
        """Get a meeting brief by calendar event ID.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("calendar_event_id", calendar_event_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def get_brief_by_id(self, user_id: str, brief_id: str) -> dict[str, Any] | None:
        """Get a meeting brief by its ID.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.

        Returns:
            Brief dict if found, None otherwise.
        """
        result = (
            self._db.table("meeting_briefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", brief_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return cast(dict[str, Any], result.data)

    async def create_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a pending meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Created brief dict.
        """
        brief_data: dict[str, Any] = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = self._db.table("meeting_briefs").insert(brief_data).execute()

        logger.info(
            "Created pending meeting brief",
            extra={
                "user_id": user_id,
                "calendar_event_id": calendar_event_id,
                "meeting_title": meeting_title,
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def update_brief_status(
        self,
        user_id: str,
        brief_id: str,
        status: str,
        brief_content: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Update brief status and optionally content.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.
            status: New status (pending/generating/completed/failed).
            brief_content: Optional brief content to set.
            error_message: Optional error message if failed.

        Returns:
            Updated brief dict, or None if not found.
        """
        update_data: dict[str, Any] = {"status": status}

        if brief_content is not None:
            update_data["brief_content"] = brief_content
            update_data["generated_at"] = datetime.now(UTC).isoformat()

        if error_message is not None:
            update_data["error_message"] = error_message

        result = (
            self._db.table("meeting_briefs")
            .update(update_data)
            .eq("id", brief_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            logger.warning(
                "Brief not found for update",
                extra={"brief_id": brief_id, "user_id": user_id},
            )
            return None

        logger.info(
            "Updated meeting brief status",
            extra={"brief_id": brief_id, "status": status, "user_id": user_id},
        )

        return cast(dict[str, Any], result.data[0])

    async def get_upcoming_meetings(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get upcoming meetings with brief status.

        Args:
            user_id: The user's ID.
            limit: Maximum number of meetings to return.

        Returns:
            List of meeting briefs ordered by meeting time.
        """
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("meeting_briefs")
            .select("id, calendar_event_id, meeting_title, meeting_time, status, attendees")
            .eq("user_id", user_id)
            .gte("meeting_time", now)
            .order("meeting_time", desc=False)
            .limit(limit)
            .execute()
        )

        return cast(list[dict[str, Any]], result.data or [])

    async def upsert_brief(
        self,
        user_id: str,
        calendar_event_id: str,
        meeting_title: str | None,
        meeting_time: datetime,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create or update a meeting brief.

        Args:
            user_id: The user's ID.
            calendar_event_id: Calendar event identifier.
            meeting_title: Meeting title.
            meeting_time: Meeting start time.
            attendees: List of attendee email addresses.

        Returns:
            Upserted brief dict.
        """
        brief_data: dict[str, Any] = {
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": meeting_title,
            "meeting_time": meeting_time.isoformat(),
            "attendees": attendees or [],
            "status": "pending",
            "brief_content": {},
        }

        result = (
            self._db.table("meeting_briefs")
            .upsert(brief_data, on_conflict="user_id,calendar_event_id")
            .execute()
        )

        return cast(dict[str, Any], result.data[0])

    async def generate_brief_content(
        self,
        user_id: str,
        brief_id: str,
    ) -> dict[str, Any] | None:
        """Generate brief content using Scout agent and Claude.

        Args:
            user_id: The user's ID.
            brief_id: The brief's ID.

        Returns:
            Brief content dict with summary, agenda, and risks, or None if failed.
        """
        # Step 1: Get the brief
        brief = await self.get_brief_by_id(user_id, brief_id)
        if not brief:
            logger.warning(
                "Brief not found for generation",
                extra={"brief_id": brief_id, "user_id": user_id},
            )
            return None

        # Store meeting details for notification
        meeting_title = brief.get("meeting_title")
        calendar_event_id = brief.get("calendar_event_id")

        # Step 2: Update status to generating
        await self.update_brief_status(user_id=user_id, brief_id=brief_id, status="generating")

        try:
            # Step 3: Get attendee profiles from cache
            attendees = brief.get("attendees", [])
            profile_service = AttendeeProfileService()
            attendee_profiles = await profile_service.get_profiles_batch(attendees)

            # Step 4: Research companies via Scout agent
            companies = list(
                {
                    profile.get("company")
                    for profile in attendee_profiles.values()
                    if profile.get("company")
                }
            )

            company_signals: list[dict[str, Any]] = []
            if companies:
                llm_client = LLMClient()
                scout = ScoutAgent(llm_client=llm_client, user_id=user_id)
                if scout.validate_input({"entities": companies}):
                    scout_result = await scout.execute({"entities": companies})
                    if scout_result.success:
                        company_signals = scout_result.data

            # Step 5: Build context and call Claude
            context = self._build_brief_context(brief, attendee_profiles, company_signals)

            # Call Claude to synthesize the brief
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": context,
                    }
                ],
            )

            # Parse Claude's response
            first_block = response.content[0]
            response_text = first_block.text if hasattr(first_block, "text") else ""
            try:
                llm_output = json.loads(response_text)
            except json.JSONDecodeError:
                llm_output = {
                    "summary": response_text,
                    "suggested_agenda": [],
                    "risks_opportunities": [],
                }

            # Step 6: Build complete brief content
            brief_content: dict[str, Any] = {
                "summary": llm_output.get("summary", ""),
                "suggested_agenda": llm_output.get("suggested_agenda", []),
                "risks_opportunities": llm_output.get("risks_opportunities", []),
                "attendee_profiles": attendee_profiles,
                "company_signals": company_signals,
            }

            # Step 7: Update brief status to completed
            await self.update_brief_status(
                user_id=user_id,
                brief_id=brief_id,
                status="completed",
                brief_content=brief_content,
            )

            # Notify user that meeting brief is ready
            if meeting_title and calendar_event_id:
                await notification_integration.notify_meeting_brief_ready(
                    user_id=user_id,
                    meeting_title=meeting_title,
                    calendar_event_id=calendar_event_id,
                )

            logger.info(
                "Generated meeting brief content",
                extra={
                    "brief_id": brief_id,
                    "user_id": user_id,
                    "attendee_count": len(attendee_profiles),
                    "signal_count": len(company_signals),
                },
            )

            return brief_content

        except Exception as e:
            logger.exception(
                "Failed to generate brief content",
                extra={"brief_id": brief_id, "user_id": user_id, "error": str(e)},
            )
            await self.update_brief_status(
                user_id=user_id,
                brief_id=brief_id,
                status="failed",
                error_message=str(e),
            )
            return None

    def _build_brief_context(
        self,
        brief: dict[str, Any],
        attendee_profiles: dict[str, dict[str, Any]],
        company_signals: list[dict[str, Any]],
    ) -> str:
        """Build context string for Claude to generate the brief.

        Args:
            brief: The meeting brief data.
            attendee_profiles: Dict of attendee email to profile data.
            company_signals: List of company signals from Scout.

        Returns:
            Formatted context string for the LLM.
        """
        context_parts = [
            "Generate a pre-meeting brief for the following meeting.",
            "Return a JSON object with 'summary', 'suggested_agenda', and 'risks_opportunities'.",
            "",
            f"Meeting Title: {brief.get('meeting_title', 'Unknown')}",
            f"Meeting Time: {brief.get('meeting_time', 'Unknown')}",
            "",
            "Attendees:",
        ]

        for email, profile in attendee_profiles.items():
            name = profile.get("name", email)
            title = profile.get("title", "Unknown")
            company = profile.get("company", "Unknown")
            context_parts.append(f"- {name} ({title} at {company})")

        if not attendee_profiles:
            for email in brief.get("attendees", []):
                context_parts.append(f"- {email}")

        if company_signals:
            context_parts.append("")
            context_parts.append("Recent Company News/Signals:")
            for signal in company_signals[:5]:  # Limit to top 5 signals
                headline = signal.get("headline", "")
                company_name = signal.get("company_name", "")
                context_parts.append(f"- {company_name}: {headline}")

        return "\n".join(context_parts)
