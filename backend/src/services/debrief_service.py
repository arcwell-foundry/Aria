"""Post-meeting debrief service for extracting structured insights.

This module provides functionality for processing user's post-meeting debrief notes
and extracting structured data including action items, commitments, and insights.

Workflow:
1. initiate_debrief: Creates a pending debrief linked to a calendar event
2. process_debrief: AI-powered extraction from user's free-form notes
3. post_process_debrief: Downstream integration (lead memory, email draft, etc.)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

import anthropic

from src.core.config import settings
from src.db.supabase import SupabaseClient
from src.models.notification import NotificationType
from src.services.activity_service import ActivityService
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class DebriefContent:
    """Structured debrief content extracted from user notes.

    Attributes:
        summary: 2-3 sentence summary of meeting outcome
        outcome: Meeting outcome (positive, neutral, negative)
        action_items: List of action items with task, owner, and due_date
        commitments_ours: Things we committed to do
        commitments_theirs: Things they committed to do
        insights: List of insights by type and content
        follow_up_needed: Whether a follow-up is needed
        follow_up_draft: Optional drafted follow-up message
    """

    summary: str
    outcome: str  # positive, neutral, negative
    action_items: list[dict[str, Any]]  # {task, owner, due_date}
    commitments_ours: list[str]
    commitments_theirs: list[str]
    insights: list[dict[str, Any]]  # {type, content}
    follow_up_needed: bool
    follow_up_draft: str | None


class DebriefService:
    """Service for creating and managing meeting debriefs.

    Supports a three-phase workflow:
    1. initiate_debrief: Create pending debrief, link to meeting and leads
    2. process_debrief: AI extraction of structured data from notes
    3. post_process_debrief: Downstream integration (lead events, email drafts, etc.)
    """

    def __init__(self) -> None:
        """Initialize the debrief service."""
        self.db = SupabaseClient.get_client()
        self.llm = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    # =========================================================================
    # Phase 1: Initiate Debrief
    # =========================================================================

    async def initiate_debrief(
        self,
        user_id: str,
        meeting_id: str,
    ) -> dict[str, Any]:
        """Create a pending debrief linked to a calendar event.

        Fetches meeting from calendar_events, auto-links to lead_memories
        if any attendee email matches a lead stakeholder, pre-fills meeting
        title and time, and creates a notification for the user.

        Args:
            user_id: The user's UUID.
            meeting_id: The meeting's unique identifier (calendar_event.id).

        Returns:
            Created debrief data with status 'pending'.

        Raises:
            Exception: If database operation fails.
        """
        # Fetch meeting from calendar_events
        meeting_context = await self._get_meeting_context_from_db(user_id, meeting_id)

        # Auto-link to lead if attendee matches a stakeholder
        linked_lead_id = await self._find_linked_lead(user_id, meeting_context.get("attendees", []))

        # Create pending debrief
        debrief_data: dict[str, Any] = {
            "user_id": user_id,
            "meeting_id": meeting_id,
            "meeting_title": meeting_context.get("title", "Unknown Meeting"),
            "meeting_time": meeting_context.get("start_time"),
            "status": "pending",
            "linked_lead_id": linked_lead_id,
            "action_items": [],
            "commitments_ours": [],
            "commitments_theirs": [],
            "insights": [],
            "follow_up_needed": False,
            "created_at": datetime.now(UTC).isoformat(),
        }

        result = self.db.table("meeting_debriefs").insert(debrief_data).execute()
        debrief = cast(dict[str, Any], result.data[0])

        # Create notification for user
        company_name = meeting_context.get("external_company", "your meeting")
        await NotificationService.create_notification(
            user_id=user_id,
            type=NotificationType.TASK_DUE,
            title="Meeting Debrief",
            message=f"How did your meeting with {company_name} go?",
            link=f"/communications/debriefs/{debrief['id']}",
            metadata={"debrief_id": debrief["id"], "meeting_id": meeting_id},
        )

        logger.info(
            "Debrief initiated",
            extra={
                "user_id": user_id,
                "meeting_id": meeting_id,
                "debrief_id": debrief.get("id"),
                "linked_lead_id": linked_lead_id,
            },
        )

        return debrief

    # =========================================================================
    # Phase 2: Process Debrief (AI Extraction)
    # =========================================================================

    async def process_debrief(
        self,
        debrief_id: str,
        user_input: str,
    ) -> dict[str, Any]:
        """Process user's free-form notes and extract structured data using AI.

        Updates the debrief with extracted data including summary, outcome,
        action items, commitments, and insights.

        Args:
            debrief_id: The debrief's UUID.
            user_input: User's free-form debrief notes.

        Returns:
            Updated debrief data with status 'processing'.

        Raises:
            Exception: If debrief not found or extraction fails.
        """
        # Get existing debrief
        result = (
            self.db.table("meeting_debriefs").select("*").eq("id", debrief_id).single().execute()
        )
        if not result.data:
            raise ValueError(f"Debrief not found: {debrief_id}")

        debrief = cast(dict[str, Any], result.data)
        user_id = debrief["user_id"]

        # Update status to processing
        self.db.table("meeting_debriefs").update({"status": "processing"}).eq(
            "id", debrief_id
        ).execute()

        # Build meeting context for extraction
        meeting_context = {
            "title": debrief.get("meeting_title", "Meeting"),
            "start_time": debrief.get("meeting_time"),
            "attendees": [],  # Would need to fetch from calendar_events if needed
        }

        # Extract structured data using LLM
        extracted = await self._extract_debrief_data(user_input, meeting_context)

        # Update debrief with extracted data
        update_data: dict[str, Any] = {
            "raw_notes": user_input,
            "summary": extracted["summary"],
            "outcome": extracted["outcome"],
            "action_items": extracted["action_items"],
            "commitments_ours": extracted["commitments_ours"],
            "commitments_theirs": extracted["commitments_theirs"],
            "insights": extracted["insights"],
            "follow_up_needed": extracted["follow_up_needed"],
        }

        result = (
            self.db.table("meeting_debriefs").update(update_data).eq("id", debrief_id).execute()
        )
        updated_debrief = cast(dict[str, Any], result.data[0])

        logger.info(
            "Debrief processed",
            extra={
                "user_id": user_id,
                "debrief_id": debrief_id,
                "outcome": extracted["outcome"],
                "action_items_count": len(extracted["action_items"]),
            },
        )

        return updated_debrief

    # =========================================================================
    # Phase 3: Post-Process Debrief (Downstream Integration)
    # =========================================================================

    async def post_process_debrief(self, debrief_id: str) -> dict[str, Any]:
        """Execute downstream integration after debrief processing.

        Performs the following integrations:
        - Creates lead_memory_events entry if linked to a lead
        - Updates stakeholder sentiment based on outcome
        - Recalculates lead health score
        - Stores in episodic memory
        - Generates email draft if follow_up_needed
        - Creates prospective_memories for action items
        - Logs to aria_activity

        Args:
            debrief_id: The debrief's UUID.

        Returns:
            Updated debrief data with status 'completed'.

        Raises:
            Exception: If debrief not found.
        """
        # Get debrief
        result = (
            self.db.table("meeting_debriefs").select("*").eq("id", debrief_id).single().execute()
        )
        if not result.data:
            raise ValueError(f"Debrief not found: {debrief_id}")

        debrief = cast(dict[str, Any], result.data)
        user_id = debrief["user_id"]
        linked_lead_id = debrief.get("linked_lead_id")

        # 1. If linked to lead: create lead_memory_events entry
        if linked_lead_id:
            await self._create_lead_event(user_id, linked_lead_id, debrief)

            # 2. Update stakeholder sentiment based on outcome
            await self._update_stakeholder_sentiment(linked_lead_id, debrief["outcome"])

            # 3. Recalculate health score
            await self._recalculate_health_score(linked_lead_id, debrief["outcome"])

        # 4. Store in episodic memory
        await self._store_episodic_memory(user_id, debrief)

        # 5. If follow_up_needed: generate email draft
        email_draft = None
        if debrief.get("follow_up_needed") and linked_lead_id:
            email_draft = await self._generate_email_draft(user_id, linked_lead_id, debrief)

        # 6. Create prospective_memories for action items
        await self._create_prospective_memories(user_id, debrief)

        # 7. Log to aria_activity
        activity_service = ActivityService()
        await activity_service.record(
            user_id=user_id,
            agent="scribe",
            activity_type="debrief_completed",
            title=f"Meeting debrief: {debrief.get('meeting_title', 'Unknown')}",
            description=debrief.get("summary", ""),
            confidence=0.9,
            related_entity_type="lead" if linked_lead_id else None,
            related_entity_id=linked_lead_id,
            metadata={
                "debrief_id": debrief_id,
                "outcome": debrief.get("outcome"),
                "action_items_count": len(debrief.get("action_items", [])),
            },
        )

        # Update status to completed
        final_update: dict[str, Any] = {"status": "completed"}
        if email_draft:
            final_update["follow_up_draft"] = email_draft

        result = (
            self.db.table("meeting_debriefs").update(final_update).eq("id", debrief_id).execute()
        )

        logger.info(
            "Debrief post-processed",
            extra={
                "user_id": user_id,
                "debrief_id": debrief_id,
                "linked_lead_id": linked_lead_id,
                "email_draft_created": email_draft is not None,
            },
        )

        return cast(dict[str, Any], result.data[0])

    # =========================================================================
    # Check for Pending Debriefs
    # =========================================================================

    async def check_pending_debriefs(self, user_id: str) -> list[dict[str, Any]]:
        """Check for meetings that ended but have no debrief.

        Queries calendar_events where end_time < now() and no matching
        meeting_debrief exists.

        Args:
            user_id: The user's UUID.

        Returns:
            List of meetings needing debrief.
        """
        now = datetime.now(UTC).isoformat()

        # Find calendar events that have ended
        result = (
            self.db.table("calendar_events")
            .select("id, title, start_time, end_time, external_company, attendees")
            .eq("user_id", user_id)
            .lt("end_time", now)
            .order("end_time", desc=True)
            .limit(50)
            .execute()
        )

        events = cast(list[dict[str, Any]], result.data or [])
        meetings_needing_debrief = []

        # Check which events don't have debriefs
        for event in events:
            debrief_result = (
                self.db.table("meeting_debriefs")
                .select("id")
                .eq("user_id", user_id)
                .eq("meeting_id", event["id"])
                .maybe_single()
                .execute()
            )

            if not debrief_result.data:
                meetings_needing_debrief.append(event)

        logger.info(
            "Checked for pending debriefs",
            extra={
                "user_id": user_id,
                "past_meetings": len(events),
                "needing_debrief": len(meetings_needing_debrief),
            },
        )

        return meetings_needing_debrief

    # =========================================================================
    # Legacy/Convenience Methods
    # =========================================================================

    async def create_debrief(
        self,
        user_id: str,
        meeting_id: str,
        user_notes: str,
        meeting_context: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Process user's debrief notes and extract structured data.

        This is a convenience method that combines initiate, process, and
        post_process into a single call for backward compatibility.

        Args:
            user_id: The user's UUID.
            meeting_id: The meeting's unique identifier.
            user_notes: The user's debrief notes.
            meeting_context: Optional meeting context (title, attendees, etc).

        Returns:
            Created debrief data.

        Raises:
            Exception: If database operation fails.
        """
        # Initiate
        debrief = await self.initiate_debrief(user_id, meeting_id)

        # Process
        debrief = await self.process_debrief(debrief["id"], user_notes)

        # Post-process
        debrief = await self.post_process_debrief(debrief["id"])

        return debrief

    async def get_debrief(self, user_id: str, debrief_id: str) -> dict[str, Any] | None:
        """Get a specific debrief.

        Args:
            user_id: The user's UUID.
            debrief_id: The debrief's UUID.

        Returns:
            Debrief data if found, None otherwise.
        """
        result = (
            self.db.table("meeting_debriefs")
            .select("*")
            .eq("id", debrief_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return cast(dict[str, Any] | None, result.data)

    async def get_debriefs_for_meeting(self, user_id: str, meeting_id: str) -> list[dict[str, Any]]:
        """Get all debriefs for a meeting.

        Args:
            user_id: The user's UUID.
            meeting_id: The meeting's unique identifier.

        Returns:
            List of debrief data, newest first.
        """
        result = (
            self.db.table("meeting_debriefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("meeting_id", meeting_id)
            .order("created_at", desc=True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data)

    async def list_recent_debriefs(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """List recent debriefs.

        Args:
            user_id: The user's UUID.
            limit: Maximum number of debriefs to return.

        Returns:
            List of recent debrief data.
        """
        result = (
            self.db.table("meeting_debriefs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data)

    async def list_debriefs_filtered(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        start_date: str | None = None,
        end_date: str | None = None,
        linked_lead_id: str | None = None,
    ) -> dict[str, Any]:
        """List debriefs with pagination and filtering.

        Args:
            user_id: The user's UUID.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            start_date: Optional ISO date string to filter from.
            end_date: Optional ISO date string to filter to.
            linked_lead_id: Optional lead ID to filter by.

        Returns:
            Dict with items, total, and has_more.
        """
        offset = (page - 1) * page_size

        # Build query
        query = (
            self.db.table("meeting_debriefs")
            .select("*", count="exact")
            .eq("user_id", user_id)
        )

        # Apply filters
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)
        if linked_lead_id:
            query = query.eq("linked_lead_id", linked_lead_id)

        # Apply pagination
        query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)

        result = query.execute()

        items = cast(list[dict[str, Any]], result.data or [])
        total = result.count if result.count is not None else len(items)
        has_more = (offset + page_size) < total

        return {
            "items": items,
            "total": total,
            "has_more": has_more,
        }

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _get_meeting_context_from_db(self, user_id: str, meeting_id: str) -> dict[str, Any]:
        """Get meeting context from calendar_events table.

        Args:
            user_id: The user's UUID.
            meeting_id: The calendar event's ID.

        Returns:
            Meeting context dict with title, start_time, attendees, and external_company.
        """
        result = (
            self.db.table("calendar_events")
            .select("*")
            .eq("id", meeting_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result.data:
            event = cast(dict[str, Any], result.data)
            return {
                "title": event.get("title", "Meeting"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
                "attendees": event.get("attendees", []),
                "external_company": event.get("external_company"),
                "metadata": event.get("metadata", {}),
            }

        # Fallback to default context
        return {
            "title": "Meeting",
            "start_time": datetime.now(UTC).isoformat(),
            "attendees": [],
        }

    async def _get_meeting_context(self, meeting_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Get meeting context from calendar.

        Legacy method maintained for backward compatibility.

        Args:
            meeting_id: The meeting's unique identifier.

        Returns:
            Meeting context dict with title, start_time, and attendees.
        """
        return {
            "title": "Meeting",
            "start_time": datetime.now(UTC).isoformat(),
            "attendees": [],
        }

    async def _find_linked_lead(
        self,
        user_id: str,  # noqa: ARG002
        attendees: list[Any],  # noqa: ARG002
    ) -> str | None:
        """Find lead memory linked to meeting attendees.

        Checks if any attendee email matches a lead_memory_stakeholders entry.

        Args:
            user_id: The user's UUID.
            attendees: List of attendee emails or dicts with email field.

        Returns:
            Lead memory ID if found, None otherwise.
        """
        if not attendees:
            return None

        for attendee in attendees:
            # Handle both string emails and dict with email field
            email = attendee if isinstance(attendee, str) else attendee.get("email")
            if not email:
                continue

            result = (
                self.db.table("lead_memory_stakeholders")
                .select("lead_memory_id")
                .eq("contact_email", email)
                .maybe_single()
                .execute()
            )

            if result.data:
                return cast(dict[str, Any], result.data)["lead_memory_id"]

        return None

    async def _extract_debrief_data(self, notes: str, context: dict[str, Any]) -> dict[str, Any]:
        """Use LLM to extract structured data from notes.

        Args:
            notes: User's debrief notes.
            context: Meeting context.

        Returns:
            Extracted structured data.
        """
        prompt = f"""Analyze these meeting debrief notes and extract structured information.

Meeting: {context.get("title", "Unknown")}
Attendees: {", ".join(context.get("attendees", []))}

User's Notes:
{notes}

Extract and return as JSON:
{{
    "summary": "2-3 sentence summary of meeting outcome",
    "outcome": "positive|neutral|negative",
    "action_items": [
        {{"task": "description", "owner": "us|them|both", "due_date": "if mentioned or null"}}
    ],
    "commitments_ours": ["things we committed to do"],
    "commitments_theirs": ["things they committed to do"],
    "insights": [
        {{"type": "objection|buying_signal|concern|opportunity", "content": "description"}}
    ],
    "follow_up_needed": true/false
}}

Be concise. Only include items explicitly mentioned or clearly implied."""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse JSON from response
        for block in response.content:
            if hasattr(block, "text"):
                response_text = block.text
                break
        else:
            response_text = str(response.content[0])

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        return cast(dict[str, Any], json.loads(response_text.strip()))

    async def _create_lead_event(
        self, user_id: str, linked_lead_id: str, debrief: dict[str, Any]
    ) -> None:
        """Create a lead_memory_events entry for the debrief.

        Args:
            user_id: The user's UUID.
            linked_lead_id: The lead memory UUID.
            debrief: The debrief data.
        """
        event_data = {
            "lead_memory_id": linked_lead_id,
            "event_type": "meeting_debrief",
            "direction": "internal",
            "subject": debrief.get("meeting_title", "Meeting Debrief"),
            "content": debrief.get("summary", ""),
            "occurred_at": debrief.get("meeting_time", datetime.now(UTC).isoformat()),
            "source": "aria_debrief",
            "source_id": debrief.get("id"),
            "metadata": {
                "outcome": debrief.get("outcome"),
                "action_items": debrief.get("action_items", []),
                "insights": debrief.get("insights", []),
            },
        }

        self.db.table("lead_memory_events").insert(event_data).execute()

        logger.info(
            "Lead event created from debrief",
            extra={
                "user_id": user_id,
                "lead_id": linked_lead_id,
                "debrief_id": debrief.get("id"),
            },
        )

    async def _update_stakeholder_sentiment(self, linked_lead_id: str, outcome: str) -> None:
        """Update stakeholder sentiment based on meeting outcome.

        Args:
            linked_lead_id: The lead memory UUID.
            outcome: The meeting outcome (positive, neutral, negative).
        """
        # Map outcome to sentiment
        sentiment_map = {
            "positive": "positive",
            "neutral": "neutral",
            "negative": "negative",
        }
        new_sentiment = sentiment_map.get(outcome, "neutral")

        # Update all stakeholders for this lead
        self.db.table("lead_memory_stakeholders").update(
            {"sentiment": new_sentiment, "updated_at": datetime.now(UTC).isoformat()}
        ).eq("lead_memory_id", linked_lead_id).execute()

        logger.info(
            "Stakeholder sentiment updated",
            extra={
                "lead_id": linked_lead_id,
                "sentiment": new_sentiment,
            },
        )

    async def _recalculate_health_score(self, linked_lead_id: str, outcome: str) -> None:
        """Recalculate lead health score based on meeting outcome.

        Args:
            linked_lead_id: The lead memory UUID.
            outcome: The meeting outcome.
        """
        # Get current health score
        result = (
            self.db.table("lead_memories")
            .select("health_score")
            .eq("id", linked_lead_id)
            .single()
            .execute()
        )

        if not result.data:
            return

        current_score = cast(dict[str, Any], result.data).get("health_score", 50)

        # Adjust score based on outcome
        score_adjustments = {
            "positive": 5,
            "neutral": 0,
            "negative": -10,
        }
        adjustment = score_adjustments.get(outcome, 0)
        new_score = max(0, min(100, current_score + adjustment))

        # Update lead
        self.db.table("lead_memories").update(
            {
                "health_score": new_score,
                "last_activity_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", linked_lead_id).execute()

        logger.info(
            "Health score recalculated",
            extra={
                "lead_id": linked_lead_id,
                "old_score": current_score,
                "new_score": new_score,
                "adjustment": adjustment,
            },
        )

    async def _store_episodic_memory(self, user_id: str, debrief: dict[str, Any]) -> None:
        """Store debrief in episodic memory.

        Args:
            user_id: The user's UUID.
            debrief: The debrief data.
        """
        memory_data = {
            "user_id": user_id,
            "event_type": "meeting_debrief",
            "content": json.dumps(
                {
                    "meeting_title": debrief.get("meeting_title"),
                    "summary": debrief.get("summary"),
                    "outcome": debrief.get("outcome"),
                    "action_items": debrief.get("action_items", []),
                }
            ),
            "metadata": {
                "debrief_id": debrief.get("id"),
                "meeting_id": debrief.get("meeting_id"),
            },
        }

        self.db.table("episodic_memories").insert(memory_data).execute()

        logger.info(
            "Episodic memory stored",
            extra={
                "user_id": user_id,
                "debrief_id": debrief.get("id"),
            },
        )

    async def _generate_email_draft(
        self, user_id: str, linked_lead_id: str, debrief: dict[str, Any]
    ) -> str | None:
        """Generate email draft for follow-up.

        Args:
            user_id: The user's UUID.
            linked_lead_id: The lead memory UUID.
            debrief: The debrief data.

        Returns:
            Generated email draft text, or None if generation fails.
        """
        # Get lead context for company name
        result = (
            self.db.table("lead_memories")
            .select("company_name")
            .eq("id", linked_lead_id)
            .single()
            .execute()
        )

        company_name = "your company"
        if result.data:
            company_name = cast(dict[str, Any], result.data).get("company_name", company_name)

        meeting_context = {
            "title": debrief.get("meeting_title", "Meeting"),
        }
        extracted = {
            "outcome": debrief.get("outcome", "neutral"),
            "summary": debrief.get("summary", ""),
            "commitments_ours": debrief.get("commitments_ours", []),
            "commitments_theirs": debrief.get("commitments_theirs", []),
            "action_items": debrief.get("action_items", []),
        }

        return await self._generate_follow_up_draft(meeting_context, extracted, user_id)

    async def _generate_follow_up_draft(
        self,
        meeting_context: dict[str, Any],
        extracted: dict[str, Any],
        user_id: str,  # noqa: ARG002
    ) -> str:
        """Generate a follow-up email draft.

        Args:
            meeting_context: Meeting context dict.
            extracted: Extracted debrief data.
            user_id: The user's UUID.

        Returns:
            Generated follow-up email text.
        """
        prompt = f"""Write a brief follow-up email after this meeting.

Meeting: {meeting_context.get("title")}
Outcome: {extracted["outcome"]}
Summary: {extracted["summary"]}
Our commitments: {", ".join(extracted["commitments_ours"])}
Their commitments: {", ".join(extracted["commitments_theirs"])}
Action items: {extracted["action_items"]}

Write a professional, concise follow-up email that:
1. Thanks them for their time
2. Summarizes key points discussed
3. Lists action items with owners
4. Proposes next steps if appropriate

Keep it under 200 words."""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content[0])

    async def _create_prospective_memories(self, user_id: str, debrief: dict[str, Any]) -> None:
        """Create prospective memories for action items.

        Args:
            user_id: The user's UUID.
            debrief: The debrief data.
        """
        action_items = debrief.get("action_items", [])
        linked_lead_id = debrief.get("linked_lead_id")

        for item in action_items:
            if not isinstance(item, dict):
                continue

            task = item.get("task", "")
            owner = item.get("owner", "us")
            due_date = item.get("due_date")

            # Only create prospective memory for items we own
            if owner not in ("us", "both"):
                continue

            trigger_config: dict[str, Any] = {}
            if due_date:
                trigger_config["due_at"] = due_date

            memory_data = {
                "user_id": user_id,
                "task": task,
                "description": f"Action item from meeting: {debrief.get('meeting_title', 'Unknown')}",
                "trigger_type": "time" if due_date else "event",
                "trigger_config": trigger_config,
                "status": "pending",
                "priority": "medium",
                "related_lead_id": linked_lead_id,
            }

            self.db.table("prospective_memories").insert(memory_data).execute()

        logger.info(
            "Prospective memories created",
            extra={
                "user_id": user_id,
                "debrief_id": debrief.get("id"),
                "action_items_count": len(action_items),
            },
        )

    async def _link_to_lead_memory(
        self, user_id: str, meeting_context: dict[str, Any], extracted: dict[str, Any]
    ) -> None:
        """Link debrief insights to Lead Memory if applicable.

        Args:
            user_id: The user's UUID.
            meeting_context: Meeting context with attendees.
            extracted: Extracted debrief data with insights.
        """
        attendees = meeting_context.get("attendees", [])
        if not attendees:
            return

        for attendee in attendees:
            email = attendee if isinstance(attendee, str) else attendee.get("email")
            if not email:
                continue

            result = (
                self.db.table("lead_memory_stakeholders")
                .select("lead_memory_id")
                .eq("contact_email", email)
                .execute()
            )

            if result.data:
                lead_id = cast(dict[str, Any], result.data[0])["lead_memory_id"]

                # Add insights to lead
                for insight in extracted.get("insights", []):
                    self.db.table("lead_memory_insights").insert(
                        {
                            "lead_memory_id": lead_id,
                            "insight_type": insight["type"],
                            "content": insight["content"],
                            "confidence": 0.8,
                            "detected_at": datetime.now(UTC).isoformat(),
                        }
                    ).execute()

                # Update lead's last_activity_at
                self.db.table("lead_memories").update(
                    {"last_activity_at": datetime.now(UTC).isoformat()}
                ).eq("id", lead_id).execute()

                logger.info(
                    "Debrief linked to lead",
                    extra={
                        "user_id": user_id,
                        "lead_id": lead_id,
                        "insights_count": len(extracted.get("insights", [])),
                    },
                )

                break
