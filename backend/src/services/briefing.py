"""Daily briefing service for morning briefings.

This service generates daily briefings containing:
- Calendar overview for the day
- Lead status summary
- Market signals
- Task status
- LLM-generated executive summary
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import anthropic

from src.core.config import settings
from src.db.supabase import SupabaseClient
from src.services import notification_integration

logger = logging.getLogger(__name__)


class BriefingService:
    """Service for generating and managing daily briefings."""

    def __init__(self) -> None:
        """Initialize briefing service with dependencies."""
        self._db = SupabaseClient.get_client()
        self._llm = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

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

        # Gather data for briefing — each step isolated so one failure
        # doesn't prevent the entire briefing from generating
        empty_calendar: dict[str, Any] = {"meeting_count": 0, "key_meetings": []}
        empty_leads: dict[str, Any] = {"hot_leads": [], "needs_attention": [], "recently_active": []}
        empty_signals: dict[str, Any] = {
            "company_news": [],
            "market_trends": [],
            "competitive_intel": [],
        }
        empty_tasks: dict[str, Any] = {"overdue": [], "due_today": []}

        try:
            calendar_data = await self._get_calendar_data(user_id, briefing_date)
        except Exception:
            logger.warning("Failed to gather calendar data", extra={"user_id": user_id}, exc_info=True)
            calendar_data = empty_calendar

        try:
            lead_data = await self._get_lead_data(user_id)
        except Exception:
            logger.warning("Failed to gather lead data", extra={"user_id": user_id}, exc_info=True)
            lead_data = empty_leads

        try:
            signal_data = await self._get_signal_data(user_id)
        except Exception:
            logger.warning("Failed to gather signal data", extra={"user_id": user_id}, exc_info=True)
            signal_data = empty_signals

        try:
            task_data = await self._get_task_data(user_id)
        except Exception:
            logger.warning("Failed to gather task data", extra={"user_id": user_id}, exc_info=True)
            task_data = empty_tasks

        # Generate summary using LLM
        summary = await self._generate_summary(calendar_data, lead_data, signal_data, task_data)

        content: dict[str, Any] = {
            "summary": summary,
            "calendar": calendar_data,
            "leads": lead_data,
            "signals": signal_data,
            "tasks": task_data,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Store briefing
        try:
            self._db.table("daily_briefings").upsert(
                {
                    "user_id": user_id,
                    "briefing_date": briefing_date.isoformat(),
                    "content": content,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception:
            logger.warning(
                "Failed to store briefing, returning content without persistence",
                extra={"user_id": user_id},
                exc_info=True,
            )

        logger.info(
            "Daily briefing generated",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )

        # Notify user that briefing is ready
        await notification_integration.notify_briefing_ready(
            user_id=user_id,
            briefing_date=briefing_date.isoformat(),
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
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            return None
        return result.data if isinstance(result.data, dict) else None

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

    async def list_briefings(self, user_id: str, limit: int = 7) -> list[dict[str, Any]]:
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
        self,
        user_id: str,
        briefing_date: date,
    ) -> dict[str, Any]:
        """Get calendar events for the day.

        Args:
            user_id: The user's ID.
            briefing_date: The date to get calendar for.

        Returns:
            Dict with meeting_count and key_meetings.
        """
        # Check if user has calendar integration
        integration_result = (
            self._db.table("user_integrations")
            .select("id, provider, status")
            .eq("user_id", user_id)
            .eq("provider", "google_calendar")
            .eq("status", "active")
            .maybe_single()
            .execute()
        )

        if not integration_result or not integration_result.data:
            logger.debug(
                "No calendar integration for user",
                extra={"user_id": user_id},
            )
            return {"meeting_count": 0, "key_meetings": []}

        # TODO: Implement Composio calendar fetch when available
        # For now, return empty structure as calendar integration
        # requires external OAuth flow completion
        logger.info(
            "Calendar integration found but fetch not yet implemented",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )
        return {"meeting_count": 0, "key_meetings": []}

    async def _get_lead_data(self, user_id: str) -> dict[str, Any]:
        """Get lead status summary from lead_memories.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with hot_leads, needs_attention, and recently_active.
        """
        week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

        # Hot leads: health_score >= 70 AND status = active
        hot_result = (
            self._db.table("lead_memories")
            .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
            .eq("user_id", user_id)
            .eq("status", "active")
            .gte("health_score", 70)
            .order("health_score", desc=True)
            .limit(5)
            .execute()
        )

        # Needs attention: health_score <= 40 AND status = active
        attention_result = (
            self._db.table("lead_memories")
            .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
            .eq("user_id", user_id)
            .eq("status", "active")
            .lte("health_score", 40)
            .order("health_score", desc=False)
            .limit(5)
            .execute()
        )

        # Recently active: last_activity_at within 7 days
        active_result = (
            self._db.table("lead_memories")
            .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
            .eq("user_id", user_id)
            .eq("status", "active")
            .gte("last_activity_at", week_ago)
            .order("last_activity_at", desc=True)
            .limit(5)
            .execute()
        )

        def format_lead(lead: dict[str, Any]) -> dict[str, Any]:
            return {
                "id": lead["id"],
                "company_name": lead["company_name"],
                "health_score": lead.get("health_score"),
                "lifecycle_stage": lead.get("lifecycle_stage"),
                "last_activity_at": lead.get("last_activity_at"),
            }

        return {
            "hot_leads": [
                format_lead(lead) for lead in (hot_result.data or []) if isinstance(lead, dict)
            ],
            "needs_attention": [
                format_lead(lead)
                for lead in (attention_result.data or [])
                if isinstance(lead, dict)
            ],
            "recently_active": [
                format_lead(lead) for lead in (active_result.data or []) if isinstance(lead, dict)
            ],
        }

    async def _get_signal_data(self, user_id: str) -> dict[str, Any]:
        """Get market signals from market_signals table.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with company_news, market_trends, and competitive_intel.
        """
        week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

        # Get unread signals from the past week
        result = (
            self._db.table("market_signals")
            .select(
                "id, company_name, signal_type, headline, summary, relevance_score, detected_at"
            )
            .eq("user_id", user_id)
            .is_("dismissed_at", "null")
            .gte("detected_at", week_ago)
            .order("relevance_score", desc=True)
            .limit(20)
            .execute()
        )

        signals = result.data or []

        # Categorize by signal type
        company_news_types = {"funding", "leadership", "earnings", "partnership"}
        market_trend_types = {"regulatory", "clinical_trial", "fda_approval", "patent"}
        competitive_types = {"product", "hiring"}

        def format_signal(s: dict[str, Any]) -> dict[str, Any]:
            return {
                "id": s["id"],
                "company_name": s["company_name"],
                "headline": s["headline"],
                "summary": s.get("summary"),
                "relevance_score": s.get("relevance_score"),
                "detected_at": s.get("detected_at"),
            }

        company_news = [
            format_signal(s)
            for s in signals
            if isinstance(s, dict) and s.get("signal_type") in company_news_types
        ][:5]

        market_trends = [
            format_signal(s)
            for s in signals
            if isinstance(s, dict) and s.get("signal_type") in market_trend_types
        ][:5]

        competitive_intel = [
            format_signal(s)
            for s in signals
            if isinstance(s, dict) and s.get("signal_type") in competitive_types
        ][:5]

        return {
            "company_news": company_news,
            "market_trends": market_trends,
            "competitive_intel": competitive_intel,
        }

    async def _get_task_data(self, user_id: str) -> dict[str, Any]:
        """Get task status from prospective memories.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with overdue and due_today tasks.
        """
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Get overdue tasks (due_at < today AND status = pending)
        overdue_result = (
            self._db.table("prospective_memories")
            .select("id, task, priority, trigger_config")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .lt("trigger_config->>due_at", today_start.isoformat())
            .order("trigger_config->>due_at", desc=False)
            .limit(10)
            .execute()
        )

        # Get tasks due today (today_start <= due_at < today_end AND status = pending)
        today_result = (
            self._db.table("prospective_memories")
            .select("id, task, priority, trigger_config")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .gte("trigger_config->>due_at", today_start.isoformat())
            .lt("trigger_config->>due_at", today_end.isoformat())
            .order("trigger_config->>due_at", desc=False)
            .limit(10)
            .execute()
        )

        overdue = [
            {
                "id": t["id"],
                "task": t["task"],
                "priority": t["priority"],
                "due_at": t.get("trigger_config", {}).get("due_at"),
            }
            for t in (overdue_result.data or [])
            if isinstance(t, dict)
        ]

        due_today = [
            {
                "id": t["id"],
                "task": t["task"],
                "priority": t["priority"],
                "due_at": t.get("trigger_config", {}).get("due_at"),
            }
            for t in (today_result.data or [])
            if isinstance(t, dict)
        ]

        return {"overdue": overdue, "due_today": due_today}

    async def _generate_summary(
        self,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
        tasks: dict[str, Any],
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
        meeting_count = calendar.get("meeting_count", 0)
        attention_count = len(leads.get("needs_attention", []))
        signal_count = len(signals.get("company_news", []))
        overdue_count = len(tasks.get("overdue", []))
        total_activity = meeting_count + attention_count + signal_count + overdue_count

        if total_activity == 0:
            prompt = (
                "Generate a brief, friendly morning briefing summary (2-3 sentences) "
                "for a new user who just started using the platform. They have no meetings, "
                "leads, signals, or tasks yet. Welcome them warmly and encourage them to "
                "explore the platform — add leads, connect their calendar, set goals. "
                'Start with "Good morning!"'
            )
        else:
            prompt = f"""Generate a brief, friendly morning briefing summary (2-3 sentences) based on:

Calendar: {meeting_count} meetings today
Leads needing attention: {attention_count}
New signals: {signal_count}
Overdue tasks: {overdue_count}

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
