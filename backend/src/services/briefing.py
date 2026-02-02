"""Daily briefing service for morning briefings.

This service generates daily briefings containing:
- Calendar overview for the day
- Lead status summary
- Market signals
- Task status
- LLM-generated executive summary
"""

import logging
from datetime import UTC, date, datetime
from typing import Any

import anthropic

from src.core.config import settings
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class BriefingService:
    """Service for generating and managing daily briefings."""

    def __init__(self) -> None:
        """Initialize briefing service with dependencies."""
        self._db = SupabaseClient.get_client()
        self._llm = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
        )

    async def generate_briefing(
        self, user_id: str, briefing_date: date | None = None
    ) -> dict[str, Any]:
        """Generate a new daily briefing for the user.

        Args:
            user_id: The user's ID.
            briefing_date: The date for the briefing (defaults to today).

        Returns:
            Dict containing the briefing content.
        """
        if briefing_date is None:
            briefing_date = date.today()

        logger.info(
            "Generating daily briefing",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )

        # Gather data for briefing
        calendar_data = await self._get_calendar_data(user_id, briefing_date)
        lead_data = await self._get_lead_data(user_id)
        signal_data = await self._get_signal_data(user_id)
        task_data = await self._get_task_data(user_id)

        # Generate summary using LLM
        summary = await self._generate_summary(
            calendar_data, lead_data, signal_data, task_data
        )

        content: dict[str, Any] = {
            "summary": summary,
            "calendar": calendar_data,
            "leads": lead_data,
            "signals": signal_data,
            "tasks": task_data,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Store briefing
        self._db.table("daily_briefings").upsert(
            {
                "user_id": user_id,
                "briefing_date": briefing_date.isoformat(),
                "content": content,
                "generated_at": datetime.now(UTC).isoformat(),
            }
        ).execute()

        logger.info(
            "Daily briefing generated",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )

        return content

    async def get_briefing(
        self, user_id: str, briefing_date: date | None = None
    ) -> dict[str, Any] | None:
        """Get existing briefing or None if not found.

        Args:
            user_id: The user's ID.
            briefing_date: The date for the briefing (defaults to today).

        Returns:
            Briefing dict if found, None otherwise.
        """
        if briefing_date is None:
            briefing_date = date.today()

        result = (
            self._db.table("daily_briefings")
            .select("*")
            .eq("user_id", user_id)
            .eq("briefing_date", briefing_date.isoformat())
            .single()
            .execute()
        )

        data = result.data
        return data if data and isinstance(data, dict) else None

    async def get_or_generate_briefing(
        self, user_id: str, briefing_date: date | None = None
    ) -> dict[str, Any]:
        """Get existing briefing or generate new one.

        Args:
            user_id: The user's ID.
            briefing_date: The date for the briefing (defaults to today).

        Returns:
            Briefing content dict.
        """
        existing = await self.get_briefing(user_id, briefing_date)
        if existing:
            content = existing.get("content")
            if isinstance(content, dict):
                return content
        return await self.generate_briefing(user_id, briefing_date)

    async def list_briefings(
        self, user_id: str, limit: int = 7
    ) -> list[dict[str, Any]]:
        """List recent briefings for user.

        Args:
            user_id: The user's ID.
            limit: Maximum number of briefings to return.

        Returns:
            List of briefing dicts.
        """
        result = (
            self._db.table("daily_briefings")
            .select("*")
            .eq("user_id", user_id)
            .order("briefing_date", desc=True)
            .limit(limit)
            .execute()
        )

        data = result.data
        return [b for b in data if isinstance(b, dict)]

    async def _get_calendar_data(
        self, user_id: str, briefing_date: date  # noqa: ARG002
    ) -> dict[str, Any]:
        """Get calendar events for the day.

        Args:
            user_id: The user's ID.
            briefing_date: The date to get calendar for.

        Returns:
            Dict with meeting_count and key_meetings.
        """
        # TODO: Integrate with calendar service
        return {"meeting_count": 0, "key_meetings": []}

    async def _get_lead_data(self, user_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Get lead status summary.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with hot_leads, needs_attention, and recently_active.
        """
        # TODO: Integrate with lead memory service
        return {"hot_leads": [], "needs_attention": [], "recently_active": []}

    async def _get_signal_data(self, user_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Get market signals.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with company_news, market_trends, and competitive_intel.
        """
        # TODO: Integrate with signal detection
        return {
            "company_news": [],
            "market_trends": [],
            "competitive_intel": [],
        }

    async def _get_task_data(self, user_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Get task status.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with overdue and due_today.
        """
        # TODO: Integrate with prospective memory
        return {"overdue": [], "due_today": []}

    async def _generate_summary(
        self, calendar: dict[str, Any], leads: dict[str, Any], signals: dict[str, Any], tasks: dict[str, Any]
    ) -> str:
        """Generate executive summary using LLM.

        Args:
            calendar: Calendar data dict.
            leads: Lead data dict.
            signals: Signal data dict.
            tasks: Task data dict.

        Returns:
            Generated summary string.
        """
        prompt = f"""Generate a brief, friendly morning briefing summary (2-3 sentences) based on:

Calendar: {calendar['meeting_count']} meetings today
Leads needing attention: {len(leads.get('needs_attention', []))}
New signals: {len(signals.get('company_news', []))}
Overdue tasks: {len(tasks.get('overdue', []))}

Be concise and actionable. Start with "Good morning!"
"""

        response = self._llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        # Get text from first content block (TextBlock has text attribute)
        content_block = response.content[0]
        if hasattr(content_block, "text"):
            return content_block.text
        # Fallback for other block types
        return str(content_block)
