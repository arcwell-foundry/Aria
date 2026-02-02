"""Post-meeting debrief service for extracting structured insights.

This module provides functionality for processing user's post-meeting debrief notes
and extracting structured data including action items, commitments, and insights.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

import anthropic

from src.core.config import settings
from src.db.supabase import SupabaseClient

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
    """Service for creating and managing meeting debriefs."""

    def __init__(self) -> None:
        """Initialize the debrief service."""
        self.db = SupabaseClient.get_client()
        self.llm = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    async def create_debrief(
        self,
        user_id: str,
        meeting_id: str,
        user_notes: str,
        meeting_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process user's debrief notes and extract structured data.

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
        # Get meeting context if not provided
        if not meeting_context:
            meeting_context = await self._get_meeting_context(meeting_id)

        # Extract structured data using LLM
        extracted = await self._extract_debrief_data(user_notes, meeting_context)

        # Store debrief
        debrief_data = {
            "user_id": user_id,
            "meeting_id": meeting_id,
            "meeting_title": meeting_context.get("title", "Unknown Meeting"),
            "meeting_time": meeting_context.get("start_time"),
            "raw_notes": user_notes,
            "summary": extracted["summary"],
            "outcome": extracted["outcome"],
            "action_items": extracted["action_items"],
            "commitments_ours": extracted["commitments_ours"],
            "commitments_theirs": extracted["commitments_theirs"],
            "insights": extracted["insights"],
            "follow_up_needed": extracted["follow_up_needed"],
            "created_at": datetime.now(UTC).isoformat(),
        }

        result = self.db.table("meeting_debriefs").insert(debrief_data).execute()
        debrief = cast(dict[str, Any], result.data[0])

        # If follow-up needed, generate draft
        if extracted["follow_up_needed"]:
            draft = await self._generate_follow_up_draft(meeting_context, extracted, user_id)
            debrief["follow_up_draft"] = draft

        # Link to Lead Memory if applicable
        await self._link_to_lead_memory(user_id, meeting_context, extracted)

        logger.info(
            "Debrief created",
            extra={
                "user_id": user_id,
                "meeting_id": meeting_id,
                "debrief_id": debrief.get("id"),
                "outcome": extracted["outcome"],
            },
        )

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

    async def _get_meeting_context(self, meeting_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Get meeting context from calendar.

        Args:
            meeting_id: The meeting's unique identifier.

        Returns:
            Meeting context dict with title, start_time, and attendees.
        """
        # TODO: Integrate with calendar service
        return {
            "title": "Meeting",
            "start_time": datetime.now(UTC).isoformat(),
            "attendees": [],
        }

    async def _extract_debrief_data(self, notes: str, context: dict[str, Any]) -> dict[str, Any]:
        """Use LLM to extract structured data from notes.

        Args:
            notes: User's debrief notes.
            context: Meeting context.

        Returns:
            Extracted structured data.
        """
        prompt = f"""Analyze these meeting debrief notes and extract structured information.

Meeting: {context.get('title', 'Unknown')}
Attendees: {', '.join(context.get('attendees', []))}

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
        # The Anthropic SDK returns content blocks; we need the text from the first TextBlock
        for block in response.content:
            if hasattr(block, "text"):
                response_text = block.text
                break
        else:
            # Fallback if no text block found
            response_text = str(response.content[0])

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        return cast(dict[str, Any], json.loads(response_text.strip()))

    async def _generate_follow_up_draft(
        self, meeting_context: dict[str, Any], extracted: dict[str, Any], user_id: str  # noqa: ARG002
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

Meeting: {meeting_context.get('title')}
Outcome: {extracted['outcome']}
Summary: {extracted['summary']}
Our commitments: {', '.join(extracted['commitments_ours'])}
Their commitments: {', '.join(extracted['commitments_theirs'])}
Action items: {extracted['action_items']}

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

        # Get text from content block
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content[0])

    async def _link_to_lead_memory(
        self, user_id: str, meeting_context: dict[str, Any], extracted: dict[str, Any]
    ) -> None:
        """Link debrief insights to Lead Memory if applicable.

        Args:
            user_id: The user's UUID.
            meeting_context: Meeting context with attendees.
            extracted: Extracted debrief data with insights.
        """
        # Find matching lead by attendee emails
        attendees = meeting_context.get("attendees", [])
        if not attendees:
            return

        # Look for leads with matching stakeholders
        for attendee in attendees:
            result = (
                self.db.table("lead_memory_stakeholders")
                .select("lead_memory_id")
                .eq("contact_email", attendee)
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

                break  # Only link to first matching lead
