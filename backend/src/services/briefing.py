"""Daily briefing service for morning briefings.

This service generates daily briefings containing:
- Calendar overview for the day
- Lead status summary
- Market signals (enhanced with real-time news via Exa)
- Task status
- LLM-generated executive summary
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services import notification_integration


class NeedsAttentionItem(BaseModel):
    """A single email that needs attention with draft details."""

    sender: str
    company: str | None = None
    subject: str
    summary: str
    urgency: str  # URGENT, NORMAL, LOW
    draft_status: str  # saved_to_drafts, draft_failed, no_draft_needed
    draft_confidence: str | None = None  # HIGH, MEDIUM, LOW
    aria_notes: str | None = None
    draft_id: str | None = None


class EmailSummary(BaseModel):
    """Email intelligence summary for daily briefing."""

    total_received: int = 0
    needs_attention: list[NeedsAttentionItem] = []
    fyi_count: int = 0
    fyi_highlights: list[str] = []
    filtered_count: int = 0
    filtered_reason: str | None = None
    drafts_waiting: int = 0
    drafts_high_confidence: int = 0
    drafts_need_review: int = 0

logger = logging.getLogger(__name__)


class BriefingService:
    """Service for generating and managing daily briefings."""

    def __init__(self) -> None:
        """Initialize briefing service with dependencies."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._personality_calibrator = PersonalityCalibrator()
        # Lazy init for Exa provider
        self._exa_provider: Any = None

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("BriefingService: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning("BriefingService: Failed to initialize ExaEnrichmentProvider: %s", e)
        return self._exa_provider

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
        empty_leads: dict[str, Any] = {
            "hot_leads": [],
            "needs_attention": [],
            "recently_active": [],
        }
        empty_signals: dict[str, Any] = {
            "company_news": [],
            "market_trends": [],
            "competitive_intel": [],
        }
        empty_tasks: dict[str, Any] = {"overdue": [], "due_today": []}
        empty_email: dict[str, Any] = {
            "total_received": 0,
            "needs_attention": [],
            "fyi_count": 0,
            "fyi_highlights": [],
            "filtered_count": 0,
            "filtered_reason": None,
            "drafts_waiting": 0,
            "drafts_high_confidence": 0,
            "drafts_need_review": 0,
        }

        try:
            calendar_data = await self._get_calendar_data(user_id, briefing_date)
        except Exception:
            logger.warning(
                "Failed to gather calendar data", extra={"user_id": user_id}, exc_info=True
            )
            calendar_data = empty_calendar

        try:
            lead_data = await self._get_lead_data(user_id)
        except Exception:
            logger.warning("Failed to gather lead data", extra={"user_id": user_id}, exc_info=True)
            lead_data = empty_leads

        try:
            signal_data = await self._get_signal_data(user_id)
        except Exception:
            logger.warning(
                "Failed to gather signal data", extra={"user_id": user_id}, exc_info=True
            )
            signal_data = empty_signals

        try:
            task_data = await self._get_task_data(user_id)
        except Exception:
            logger.warning("Failed to gather task data", extra={"user_id": user_id}, exc_info=True)
            task_data = empty_tasks

        try:
            email_data = await self._get_email_data(user_id)
        except Exception:
            logger.warning(
                "Failed to gather email data", extra={"user_id": user_id}, exc_info=True
            )
            email_data = empty_email

        # Get personality calibration for tone-matched briefing
        try:
            calibration = await self._personality_calibrator.get_calibration(user_id)
            tone_guidance = calibration.tone_guidance if calibration else ""
        except Exception:
            logger.warning(
                "Failed to get personality calibration", extra={"user_id": user_id}, exc_info=True
            )
            tone_guidance = ""

        # Generate summary using LLM
        summary = await self._generate_summary(
            calendar_data, lead_data, signal_data, task_data, email_data,
            tone_guidance=tone_guidance,
        )

        content: dict[str, Any] = {
            "summary": summary,
            "calendar": calendar_data,
            "leads": lead_data,
            "signals": signal_data,
            "tasks": task_data,
            "email_summary": email_data,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Build rich content cards, UI commands, and suggestions
        rich_content = self._build_rich_content(
            calendar_data, lead_data, signal_data, task_data, email_data
        )
        briefing_ui_commands = self._build_briefing_ui_commands(
            calendar_data, lead_data, signal_data, email_data
        )
        briefing_suggestions = self._build_briefing_suggestions(email_data)
        content["rich_content"] = rich_content
        content["ui_commands"] = briefing_ui_commands
        content["suggestions"] = briefing_suggestions

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

    def _build_rich_content(
        self,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
        tasks: dict[str, Any],
        email_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build rich content cards from briefing data.

        Creates MeetingCard, SignalCard, and AlertCard entries for
        the frontend to render as interactive cards.

        Args:
            calendar: Calendar data with key_meetings.
            leads: Lead data with hot_leads.
            signals: Signal data with competitive_intel.
            tasks: Task data with overdue items.
            email_data: Email data with needs_attention items.
            tasks: Task data with overdue items.

        Returns:
            List of rich content card dicts with type and data keys.
        """
        rich_content: list[dict[str, Any]] = []

        # Meeting cards from calendar
        for meeting in calendar.get("key_meetings", []):
            rich_content.append(
                {
                    "type": "meeting_card",
                    "data": {
                        "id": meeting.get("id"),
                        "title": meeting.get("title"),
                        "time": meeting.get("time"),
                        "attendees": meeting.get("attendees", []),
                        "company": meeting.get("company"),
                        "has_brief": meeting.get("has_brief", False),
                    },
                }
            )

        # Signal cards from hot leads (buying signals)
        for lead in leads.get("hot_leads", [])[:3]:
            rich_content.append(
                {
                    "type": "signal_card",
                    "data": {
                        "id": lead.get("id"),
                        "company_name": lead.get("company_name"),
                        "signal_type": "buying_signal",
                        "headline": f"{lead.get('company_name', 'Unknown')} showing strong buying signals",
                        "health_score": lead.get("health_score"),
                        "lifecycle_stage": lead.get("lifecycle_stage"),
                    },
                }
            )

        # Alert cards from competitive intelligence
        for signal in signals.get("competitive_intel", [])[:3]:
            rich_content.append(
                {
                    "type": "alert_card",
                    "data": {
                        "id": signal.get("id"),
                        "company_name": signal.get("company_name"),
                        "headline": signal.get("headline", "Competitive activity detected"),
                        "summary": signal.get("summary"),
                        "severity": "medium",
                    },
                }
            )

        # Alert cards from overdue tasks
        for task in tasks.get("overdue", [])[:2]:
            rich_content.append(
                {
                    "type": "alert_card",
                    "data": {
                        "id": task.get("id"),
                        "headline": f"Overdue: {task.get('task', 'Unknown task')}",
                        "summary": f"Priority: {task.get('priority', 'normal')}. Due: {task.get('due_at', 'unknown')}",
                        "severity": "high",
                    },
                }
            )

        return rich_content

    def _build_briefing_ui_commands(
        self,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
        email_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build UI commands for sidebar badges from briefing data.

        Creates sidebar badge update commands so the frontend can
        display notification counts on relevant navigation items.

        Args:
            calendar: Calendar data with meeting_count.
            leads: Lead data with needs_attention list.
            signals: Signal data with competitive_intel, company_news, market_trends.
            email_data: Email data with drafts_waiting, needs_attention.

        Returns:
            List of UI command dicts for sidebar badge updates.
        """
        meeting_count = calendar.get("meeting_count", 0)
        needs_attention_count = len(leads.get("needs_attention", []))
        signal_count = (
            len(signals.get("competitive_intel", []))
            + len(signals.get("company_news", []))
            + len(signals.get("market_trends", []))
        )
        drafts_waiting = email_data.get("drafts_waiting", 0)

        ui_commands: list[dict[str, Any]] = []

        if meeting_count > 0:
            ui_commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "briefing",
                    "badge_count": meeting_count,
                }
            )

        if needs_attention_count > 0:
            ui_commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "pipeline",
                    "badge_count": needs_attention_count,
                }
            )

        if signal_count > 0:
            ui_commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "intelligence",
                    "badge_count": signal_count,
                }
            )

        if drafts_waiting > 0:
            ui_commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "communications",
                    "badge_count": drafts_waiting,
                }
            )

        return ui_commands

    def _build_briefing_suggestions(self, email_data: dict[str, Any]) -> list[str]:
        """Build suggestion prompts based on briefing data.

        Args:
            email_data: Email data with drafts_waiting, needs_attention.

        Returns:
            List of suggestion strings for the user.
        """
        suggestions: list[str] = []

        # Add email-related suggestions if there are drafts waiting
        drafts_waiting = email_data.get("drafts_waiting", 0)
        drafts_high_confidence = email_data.get("drafts_high_confidence", 0)

        if drafts_waiting > 0 and drafts_high_confidence > 0:
            suggestions.append(f"Review {drafts_high_confidence} high-confidence email drafts")
        elif drafts_waiting > 0:
            suggestions.append(f"Review {drafts_waiting} email drafts")

        # Add default suggestions
        suggestions.extend([
            "Focus on the critical meeting",
            "Show me the buying signals",
            "Update me on competitor activity",
        ])

        return suggestions[:5]  # Limit to 5 suggestions

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
        """Get market signals from market_signals table and real-time Exa news.

        Enhances database signals with real-time news for tracked accounts
        and competitor monitoring via Exa search_news and find_similar.

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

        # Enhance with real-time Exa news for tracked accounts
        exa = self._get_exa_provider()
        if exa:
            try:
                # Get tracked companies from lead_memories
                tracked_result = (
                    self._db.table("lead_memories")
                    .select("company_name, website")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .order("health_score", desc=True)
                    .limit(5)
                    .execute()
                )

                tracked_companies = tracked_result.data or []

                for company in tracked_companies:
                    company_name = company.get("company_name", "")
                    website = company.get("website", "")

                    if not company_name:
                        continue

                    # Get recent news for this company (last 1 day for daily briefing)
                    try:
                        news_results = await exa.search_news(
                            query=f"{company_name} news announcement",
                            num_results=3,
                            days_back=1,
                        )

                        for item in news_results:
                            # Avoid duplicates
                            headline = item.title
                            if any(h.get("headline") == headline for h in company_news):
                                continue

                            company_news.append({
                                "id": f"exa-{hash(item.url) % 10000}",
                                "company_name": company_name,
                                "headline": headline,
                                "summary": item.text[:300] if item.text else "",
                                "relevance_score": 0.75,
                                "detected_at": item.published_date or datetime.now(UTC).isoformat(),
                                "source": "exa_realtime",
                                "url": item.url,
                            })

                        # Get similar companies for competitive intel
                        if website and len(competitive_intel) < 10:
                            similar_results = await exa.find_similar(
                                url=website,
                                num_results=3,
                                exclude_domains=[website.split("//")[1].split("/")[0]] if "://" in website else None,
                            )

                            for item in similar_results:
                                # Extract competitor name from URL
                                competitor_name = item.title.split(" - ")[0] if " - " in item.title else item.title[:50]
                                competitive_intel.append({
                                    "id": f"exa-similar-{hash(item.url) % 10000}",
                                    "company_name": competitor_name,
                                    "headline": f"Similar to {company_name}: {item.title}",
                                    "summary": item.text[:200] if item.text else "",
                                    "relevance_score": 0.6,
                                    "detected_at": datetime.now(UTC).isoformat(),
                                    "source": "exa_similar",
                                    "url": item.url,
                                })

                    except Exception as e:
                        logger.warning(
                            "Failed to get Exa news for company '%s': %s",
                            company_name,
                            e,
                        )
                        continue

                logger.info(
                    "BriefingService: Enhanced signals with Exa",
                    extra={
                        "user_id": user_id,
                        "company_news_count": len(company_news),
                        "competitive_intel_count": len(competitive_intel),
                    },
                )

            except Exception as e:
                logger.warning("BriefingService: Exa enhancement failed: %s", e)

        return {
            "company_news": company_news[:8],
            "market_trends": market_trends,
            "competitive_intel": competitive_intel[:8],
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
        email_data: dict[str, Any],
        tone_guidance: str = "",
    ) -> str:
        """Generate executive summary using LLM.

        Args:
            calendar: Calendar data dict.
            leads: Lead data dict.
            signals: Signal data dict.
            tasks: Task data dict.
            email_data: Email data dict.
            tone_guidance: Personality-calibrated tone guidance.

        Returns:
            Generated summary string.
        """
        meeting_count = calendar.get("meeting_count", 0)
        attention_count = len(leads.get("needs_attention", []))
        signal_count = len(signals.get("company_news", []))
        overdue_count = len(tasks.get("overdue", []))
        email_count = email_data.get("total_received", 0)
        drafts_waiting = email_data.get("drafts_waiting", 0)
        total_activity = meeting_count + attention_count + signal_count + overdue_count + email_count

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
Emails received: {email_count}
Drafts waiting for review: {drafts_waiting}

Be concise and actionable. Start with "Good morning!"
"""

        # Inject tone guidance if available
        if tone_guidance:
            prompt = f"TONE: {tone_guidance}\n\n{prompt}"

        return await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )

    async def _get_email_data(self, user_id: str) -> dict[str, Any]:
        """Get email intelligence summary from overnight processing.

        Checks for email integration, runs AutonomousDraftEngine if available,
        and builds the email_summary structure for the briefing.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with email_summary fields.
        """
        empty_result: dict[str, Any] = {
            "total_received": 0,
            "needs_attention": [],
            "fyi_count": 0,
            "fyi_highlights": [],
            "filtered_count": 0,
            "filtered_reason": None,
            "drafts_waiting": 0,
            "drafts_high_confidence": 0,
            "drafts_need_review": 0,
        }

        try:
            # Check if user has email integration
            integration_result = (
                self._db.table("user_integrations")
                .select("integration_type, status")
                .eq("user_id", user_id)
                .in_("integration_type", ["gmail", "outlook"])
                .maybe_single()
                .execute()
            )

            if not integration_result or not integration_result.data:
                logger.debug(
                    "No email integration for user, skipping email summary",
                    extra={"user_id": user_id},
                )
                return empty_result

            # Run email processing via AutonomousDraftEngine
            from src.services.autonomous_draft_engine import AutonomousDraftEngine

            engine = AutonomousDraftEngine()
            processing_result = await engine.process_inbox(user_id, since_hours=24)

            # Also get FYI/skipped data from EmailAnalyzer
            from src.services.email_analyzer import EmailAnalyzer

            analyzer = EmailAnalyzer()
            scan_result = await analyzer.scan_inbox(user_id, since_hours=24)

            # Build needs_attention list from drafts
            needs_attention: list[dict[str, Any]] = []
            drafts_high_confidence = 0
            drafts_need_review = 0

            for draft in processing_result.drafts:
                if not draft.success:
                    continue

                # Determine confidence label
                if draft.confidence_level >= 0.75:
                    confidence_label = "HIGH"
                    drafts_high_confidence += 1
                elif draft.confidence_level >= 0.5:
                    confidence_label = "MEDIUM"
                    drafts_need_review += 1
                else:
                    confidence_label = "LOW"
                    drafts_need_review += 1

                # Look up company from relationship or sender domain
                company = await self._get_company_for_sender(user_id, draft.recipient_email)

                needs_attention.append({
                    "sender": draft.recipient_name or draft.recipient_email,
                    "company": company,
                    "subject": draft.subject,
                    "summary": await self._summarize_draft_context(draft),
                    "urgency": "NORMAL",
                    "draft_status": "saved_to_drafts",
                    "draft_confidence": confidence_label,
                    "aria_notes": draft.aria_notes,
                    "draft_id": draft.draft_id,
                })

            # Build FYI highlights from scan result
            fyi_highlights: list[str] = []
            for fyi_email in scan_result.fyi[:5]:
                if fyi_email.topic_summary:
                    fyi_highlights.append(fyi_email.topic_summary)
                elif fyi_email.subject:
                    fyi_highlights.append(fyi_email.subject)

            # Build filtered reason summary
            filtered_reasons: list[str] = []
            for skipped in scan_result.skipped[:10]:
                if skipped.reason and skipped.reason not in filtered_reasons:
                    filtered_reasons.append(skipped.reason)

            filtered_reason = ", ".join(filtered_reasons[:3]) if filtered_reasons else None

            return {
                "total_received": scan_result.total_emails,
                "needs_attention": needs_attention,
                "fyi_count": len(scan_result.fyi),
                "fyi_highlights": fyi_highlights[:5],
                "filtered_count": len(scan_result.skipped),
                "filtered_reason": filtered_reason,
                "drafts_waiting": processing_result.drafts_generated,
                "drafts_high_confidence": drafts_high_confidence,
                "drafts_need_review": drafts_need_review,
            }

        except Exception:
            logger.warning(
                "Failed to gather email data for briefing",
                extra={"user_id": user_id},
                exc_info=True,
            )
            return empty_result

    async def _get_company_for_sender(self, user_id: str, sender_email: str) -> str | None:
        """Look up company name for a sender from memory or email domain."""
        try:
            # Check semantic memory for company info
            result = (
                self._db.table("memory_semantic")
                .select("metadata")
                .eq("user_id", user_id)
                .ilike("fact", f"%{sender_email}%")
                .limit(1)
                .execute()
            )

            if result and result.data:
                import json
                metadata_raw = result.data[0].get("metadata")
                if metadata_raw:
                    metadata = (
                        json.loads(metadata_raw)
                        if isinstance(metadata_raw, str)
                        else metadata_raw
                    )
                    if metadata.get("company"):
                        return metadata["company"]

            # Fallback: extract company from email domain
            if "@" in sender_email:
                domain = sender_email.split("@")[-1]
                company_part = domain.split(".")[0]
                return company_part.title() if len(company_part) > 2 else None

        except Exception:
            pass

        return None

    async def _summarize_draft_context(self, draft: Any) -> str:
        """Generate a one-line summary of what the draft is about."""
        subject = draft.subject or ""
        if subject.lower().startswith("re:"):
            subject = subject[3:].strip()

        return subject[:100] if subject else "Email reply draft"
