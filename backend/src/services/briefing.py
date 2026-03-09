"""Daily briefing service for morning briefings.

This service generates daily briefings containing:
- Calendar overview for the day
- Lead status summary
- Market signals (enhanced with real-time news via Exa)
- Task status
- LLM-generated executive summary
"""

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from src.core.cache import cached
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.core.persona import PersonaBuilder, PersonaRequest
from src.db.supabase import SupabaseClient
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services import notification_integration
from src.core.resilience import composio_calendar_circuit_breaker
from src.services.activity_service import ActivityService
from src.core.llm_guardrails import get_email_guardrail, get_formatting_rules

try:
    from src.intelligence.causal_reasoning import SalesCausalReasoningEngine
except ImportError:
    SalesCausalReasoningEngine = None  # type: ignore[assignment,misc]


def _sanitize_text(text: str) -> str:
    """Replace em dashes and en dashes with plain dashes."""
    return text.replace("\u2014", " - ").replace("\u2013", "-")


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
    strategic_patterns: list[dict[str, Any]] = []
    connections: list[dict[str, Any]] = []


logger = logging.getLogger(__name__)

# Calendar integration types and Composio action mappings
_CALENDAR_INTEGRATION_TYPES = ("google_calendar", "outlook_calendar", "outlook")

_CALENDAR_READ_ACTIONS: dict[str, str] = {
    "google_calendar": "GOOGLECALENDAR_FIND_EVENT",
    "outlook_calendar": "OUTLOOK_GET_CALENDAR_VIEW",
    "outlook": "OUTLOOK_GET_CALENDAR_VIEW",
}


class BriefingService:
    """Service for generating and managing daily briefings."""

    # Per-user generation locks to prevent concurrent briefing generation
    # for the same user (e.g., from StrictMode double-mount or rapid retries).
    _generation_locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_user_lock(cls, user_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for the given user_id."""
        if user_id not in cls._generation_locks:
            cls._generation_locks[user_id] = asyncio.Lock()
        return cls._generation_locks[user_id]

    def __init__(self) -> None:
        """Initialize briefing service with dependencies."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._personality_calibrator = PersonalityCalibrator()
        self._activity_service = ActivityService()
        # Lazy init for Exa provider
        self._exa_provider: Any = None
        # Lazy init for OAuth client (calendar integration)
        self._oauth_client: Any = None
        # Lazy init for causal reasoning engine
        self._causal_engine: Any = None
        # Lazy init for PersonaBuilder
        self._persona_builder: PersonaBuilder | None = None

    def _get_persona_builder(self) -> PersonaBuilder:
        """Lazily initialize and return the PersonaBuilder."""
        if self._persona_builder is None:
            self._persona_builder = PersonaBuilder()
        return self._persona_builder

    def _get_oauth_client(self) -> Any:
        """Lazily initialize and return the ComposioOAuthClient."""
        if self._oauth_client is None:
            try:
                from src.integrations.oauth import get_oauth_client

                self._oauth_client = get_oauth_client()
                logger.info("BriefingService: ComposioOAuthClient initialized")
            except Exception as e:
                logger.warning("BriefingService: Failed to initialize ComposioOAuthClient: %s", e)
        return self._oauth_client

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

    def _get_causal_engine(self) -> Any:
        """Lazily initialize and return the SalesCausalReasoningEngine."""
        if self._causal_engine is None and SalesCausalReasoningEngine:
            try:
                self._causal_engine = SalesCausalReasoningEngine(
                    db_client=self._db,
                    llm_client=self._llm,
                )
                logger.info("BriefingService: SalesCausalReasoningEngine initialized")
            except Exception as e:
                logger.warning("BriefingService: Failed to initialize SalesCausalReasoningEngine: %s", e)
        return self._causal_engine

    async def _get_user_timezone(self, user_id: str) -> str:
        """Get the user's timezone from user_profiles table.

        Args:
            user_id: The user's ID.

        Returns:
            Timezone string (e.g., 'America/New_York'), defaults to 'America/New_York'.
        """
        try:
            result = (
                self._db.table("user_profiles")
                .select("timezone")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if result and result.data:
                return result.data[0].get("timezone", "America/New_York")
        except Exception as e:
            logger.warning(
                "Failed to fetch user timezone",
                extra={"user_id": user_id},
                exc_info=True,
            )
        return "America/New_York"

    async def _format_time_in_user_timezone(
        self,
        iso_time_str: str,
        user_id: str,
    ) -> str:
        """Convert an ISO time string to user's local timezone and format.

        Args:
            iso_time_str: ISO 8601 time string (e.g., '2026-03-04T16:00:00+00:00').
            user_id: The user's ID.

        Returns:
            Formatted time in user's local timezone (e.g., '11:00 AM').
        """
        try:
            # Clean the ISO string (handle Z suffix)
            cleaned = iso_time_str.replace("Z", "+00:00")
            utc_time = datetime.fromisoformat(cleaned)

            # Ensure timezone-aware
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=UTC)

            # Get user's timezone and convert
            user_tz_str = await self._get_user_timezone(user_id)
            user_tz = ZoneInfo(user_tz_str)
            local_time = utc_time.astimezone(user_tz)

            # Format as "11:00 AM" or "11:00 PM"
            return local_time.strftime("%-I:%M %p") if cleaned else ""
        except Exception as e:
            logger.warning(
                "Failed to convert time to user timezone",
                extra={"iso_time": iso_time_str, "user_id": user_id},
                exc_info=True,
            )
            # Return original string on failure
            return iso_time_str

    async def generate_briefing(
        self,
        user_id: str,
        briefing_date: date | None = None,
        queued_insights: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a new daily briefing for the user.

        Args:
            user_id: The user's ID.
            briefing_date: The date for the briefing (defaults to today).
            queued_insights: Optional list of insights consumed from the
                briefing_queue. If provided, these are woven into the
                LLM-generated summary narrative.

        Returns:
            Dict containing the briefing content.
        """
        if briefing_date is None:
            briefing_date = date.today()

        # Acquire per-user lock to prevent concurrent generation (e.g., from
        # StrictMode double-mount, rapid retries, or overlapping scheduler runs).
        # If another coroutine is already generating for this user, it waits
        # and then returns the freshly-generated briefing from the DB.
        lock = self._get_user_lock(user_id)
        was_locked = lock.locked()
        if was_locked:
            logger.info(
                "Briefing generation already in progress, waiting for lock",
                extra={"user_id": user_id},
            )

        async with lock:
            # If we waited for another coroutine, check if it already generated
            if was_locked:
                existing = await self.get_briefing(user_id, briefing_date)
                if existing and isinstance(existing.get("content"), dict):
                    logger.info(
                        "Returning briefing generated by concurrent request",
                        extra={"user_id": user_id},
                    )
                    return existing["content"]

            return await self._generate_briefing_impl(user_id, briefing_date, queued_insights)

    async def _generate_briefing_impl(
        self,
        user_id: str,
        briefing_date: date,
        queued_insights: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Internal implementation of briefing generation (called under lock)."""
        logger.info(
            "Generating daily briefing",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )

        # Gather data for briefing - each step isolated so one failure
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
        empty_tasks: dict[str, Any] = {
            "overdue": [],
            "due_today": [],
            "meetings_without_debriefs": 0,
        }
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
            "strategic_patterns": [],
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

        # Get debrief count for meetings without debriefs
        try:
            from src.services.debrief_scheduler import DebriefScheduler

            debrief_scheduler = DebriefScheduler()
            debrief_count = await debrief_scheduler.get_debrief_prompt_count(user_id)
            task_data["meetings_without_debriefs"] = debrief_count
        except Exception:
            logger.warning(
                "Failed to get debrief prompt count",
                extra={"user_id": user_id},
                exc_info=True,
            )
            task_data["meetings_without_debriefs"] = 0

        try:
            email_data = await self._get_email_data(user_id)
        except Exception:
            logger.warning("Failed to gather email data", extra={"user_id": user_id}, exc_info=True)
            email_data = empty_email

        # Gather pulse signals queued for morning briefing
        pulse_insights: list[dict[str, Any]] = []
        try:
            pulse_result = (
                self._db.table("pulse_signals")
                .select("id, title, content, source, signal_category, priority_score")
                .eq("user_id", user_id)
                .eq("delivery_channel", "morning_brief")
                .is_("delivered_at", "null")
                .order("priority_score", desc=True)
                .limit(20)
                .execute()
            )
            pulse_insights = pulse_result.data or []
        except Exception:
            logger.warning(
                "Failed to gather pulse signals for briefing",
                extra={"user_id": user_id},
                exc_info=True,
            )

        # Gather causal reasoning intelligence for market-aware briefing
        causal_actions: list[dict[str, Any]] = []
        try:
            causal_engine = self._get_causal_engine()
            if causal_engine:
                causal_result = await causal_engine.analyze_recent_signals(
                    user_id=user_id, limit=5
                )
                if causal_result and causal_result.actions:
                    causal_actions = [
                        {
                            "recommended_action": action.recommended_action,
                            "causal_narrative": action.causal_narrative,
                            "timing": action.timing,
                            "urgency": action.urgency,
                            "confidence": action.confidence,
                            "affected_lead_ids": action.affected_lead_ids,
                        }
                        for action in causal_result.actions[:5]
                    ]
        except Exception:
            logger.warning(
                "Failed to gather causal reasoning intelligence",
                extra={"user_id": user_id},
                exc_info=True,
            )

        # Get personality calibration for tone-matched briefing
        try:
            calibration = await self._personality_calibrator.get_calibration(user_id)
            tone_guidance = calibration.tone_guidance if calibration else ""
        except Exception:
            logger.warning(
                "Failed to get personality calibration", extra={"user_id": user_id}, exc_info=True
            )
            tone_guidance = ""

        # Gather Jarvis intelligence insights for the briefing
        jarvis_insights: list[dict[str, Any]] = []
        try:
            from src.intelligence.orchestrator import create_orchestrator

            # Fetch recent market signals to feed Jarvis engines
            recent_events: list[str] = []
            new_events: list[str] = []
            try:
                recent_signals_result = (
                    self._db.table("market_signals")
                    .select("headline, summary, company_name, signal_type")
                    .eq("user_id", user_id)
                    .order("detected_at", desc=True)
                    .limit(20)
                    .execute()
                )
                for s in recent_signals_result.data or []:
                    event_text = (
                        f"{s.get('company_name', 'Unknown')}: "
                        f"{s.get('headline', '')} - {s.get('summary', '')}"
                    )
                    recent_events.append(event_text)
                    if len(new_events) < 5:
                        new_events.append(s.get("headline", ""))
            except Exception:
                logger.debug("Failed to fetch market signals for Jarvis context", exc_info=True)

            orchestrator = create_orchestrator()
            insights = await orchestrator.generate_briefing(
                user_id=user_id,
                context={
                    "briefing_date": briefing_date.isoformat(),
                    "recent_events": recent_events,
                    "new_events": new_events,
                    "user_id": str(user_id),
                },
                budget_ms=3000,
            )
            jarvis_insights = [
                {
                    "content": i.content,
                    "classification": i.classification,
                    "impact_score": i.impact_score,
                    "recommended_actions": i.recommended_actions,
                    "time_horizon": i.time_horizon,
                }
                for i in insights[:5]
            ]
        except Exception:
            logger.warning(
                "Failed to gather intelligence insights",
                extra={"user_id": user_id},
                exc_info=True,
            )

        # Merge pulse signals into queued_insights for LLM synthesis
        combined_insights = list(queued_insights or [])
        for pi in pulse_insights:
            combined_insights.append({
                "type": pi.get("signal_category", "intelligence"),
                "title": pi["title"],
                "content": pi["content"],
                "source": pi.get("source", "pulse_engine"),
                "priority": pi.get("priority_score", 0),
            })

        # Generate summary using LLM with PersonaBuilder
        raw_summary = await self._generate_summary(
            user_id,
            calendar_data,
            lead_data,
            signal_data,
            task_data,
            email_data,
            tone_guidance=tone_guidance,
            queued_insights=combined_insights if combined_insights else queued_insights,
            causal_actions=causal_actions,
        )
        summary = _sanitize_text(raw_summary)

        # Gather upcoming conferences in the next 30 days
        upcoming_conferences: list[dict[str, Any]] = []
        try:
            today_iso = briefing_date.isoformat()
            thirty_days_out = (briefing_date + timedelta(days=30)).isoformat()
            conf_result = (
                self._db.table("conferences")
                .select("name, short_name, start_date, city")
                .gte("start_date", today_iso)
                .lte("start_date", thirty_days_out)
                .order("start_date")
                .limit(3)
                .execute()
            )
            upcoming_conferences = conf_result.data or []
        except Exception:
            logger.debug(
                "Failed to gather upcoming conferences for briefing",
                extra={"user_id": user_id},
                exc_info=True,
            )

        content: dict[str, Any] = {
            "summary": summary,
            "calendar": calendar_data,
            "leads": lead_data,
            "signals": signal_data,
            "tasks": task_data,
            "email_summary": email_data,
            "intelligence_insights": jarvis_insights,
            "causal_actions": causal_actions,
            "queued_insights": queued_insights or [],
            "upcoming_conferences": upcoming_conferences,
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

        # Store briefing (ws_delivered=False until WebSocket delivery occurs)
        try:
            self._db.table("daily_briefings").upsert(
                {
                    "user_id": user_id,
                    "briefing_date": briefing_date.isoformat(),
                    "content": content,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "ws_delivered": False,
                },
                on_conflict="user_id,briefing_date",
            ).execute()
        except Exception:
            logger.warning(
                "Failed to store briefing, returning content without persistence",
                extra={"user_id": user_id},
                exc_info=True,
            )

        # Mark pulse signals as delivered
        if pulse_insights:
            try:
                pulse_ids = [p["id"] for p in pulse_insights]
                self._db.table("pulse_signals").update(
                    {"delivered_at": datetime.now(UTC).isoformat()}
                ).in_("id", pulse_ids).execute()
            except Exception:
                logger.warning("Failed to mark pulse signals as delivered", exc_info=True)

        logger.info(
            "Daily briefing generated",
            extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
        )

        # Notify user that briefing is ready (with video CTA if enabled)
        await notification_integration.notify_briefing_ready_with_video(
            user_id=user_id,
            briefing_date=briefing_date.isoformat(),
        )

        # Log briefing generation to activity feed (non-blocking)
        drafts_count = email_data.get("drafts_waiting", 0)
        signals_count = (
            len(signal_data.get("company_news", []))
            + len(signal_data.get("market_trends", []))
            + len(signal_data.get("competitive_intel", []))
        )

        try:
            await self._activity_service.record(
                user_id=user_id,
                agent="strategist",
                activity_type="briefing_generated",
                title="Morning briefing ready",
                description=f"Includes {drafts_count} email drafts and {signals_count} market signals",
                confidence=0.9,
                metadata={
                    "briefing_date": briefing_date.isoformat(),
                    "meeting_count": calendar_data.get("meeting_count", 0),
                    "drafts_count": drafts_count,
                    "signals_count": signals_count,
                    "leads_needs_attention": len(lead_data.get("needs_attention", [])),
                    "tasks_overdue": len(task_data.get("overdue", [])),
                },
            )
        except Exception as e:
            logger.warning(
                "BRIEFING: Failed to log briefing activity: %s",
                e,
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
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result or not result.data:
            return None
        row = result.data[0] if isinstance(result.data, list) and result.data else result.data
        return row if isinstance(row, dict) else None

    @staticmethod
    def _briefing_cache_key(*args: Any, **kwargs: Any) -> str:
        """Generate cache key for briefing based on user_id and date.

        Note: For instance methods, args[0] is self, so we skip it.
        """
        # args[0] is self, args[1] is user_id, args[2] is briefing_date
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "")
        briefing_date = args[2] if len(args) > 2 else kwargs.get("briefing_date")
        date_str = briefing_date.isoformat() if briefing_date else date.today().isoformat()
        return f"briefing:{user_id}:{date_str}"

    @cached(ttl=3600, key_func=_briefing_cache_key)  # 1 hour TTL
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

    async def deliver_briefing(
        self,
        user_id: str,
        briefing_date: date | None = None,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deliver a briefing to the user via their preferred channel.

        This method handles delivery for all three modes:
        - chat: WebSocket message + notification (default)
        - voice: Tavus audio (TODO: Stream D)
        - avatar: Tavus video (TODO: Stream D)

        Args:
            user_id: The user's UUID.
            briefing_date: The briefing date (defaults to today).
            content: Optional pre-fetched briefing content (skips DB lookup).

        Returns:
            Dict with delivery status and method used.
        """
        if briefing_date is None:
            briefing_date = date.today()

        # Get the briefing row from DB
        briefing_result = (
            self._db.table("daily_briefings")
            .select("id, content, delivery_method, delivered_at")
            .eq("user_id", user_id)
            .eq("briefing_date", briefing_date.isoformat())
            .limit(1)
            .execute()
        )

        if not briefing_result.data:
            logger.warning(
                "No briefing found to deliver",
                extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
            )
            return {"success": False, "error": "briefing_not_found"}

        briefing_row = briefing_result.data[0]
        briefing_id = briefing_row["id"]

        # Already delivered?
        if briefing_row.get("delivered_at"):
            logger.debug(
                "Briefing already delivered",
                extra={
                    "user_id": user_id,
                    "briefing_id": briefing_id,
                    "delivery_method": briefing_row.get("delivery_method"),
                },
            )
            return {
                "success": True,
                "already_delivered": True,
                "delivery_method": briefing_row.get("delivery_method"),
            }

        # Get briefing content
        if content is None:
            raw_content = briefing_row.get("content")
            content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content

        if not content:
            return {"success": False, "error": "no_content"}

        # Get user's delivery mode preference
        delivery_mode = await self._get_delivery_mode(user_id)

        # Perform delivery based on mode
        delivery_success = False
        delivery_method = "chat"  # Default

        if delivery_mode == "chat":
            delivery_success = await self._deliver_via_websocket(
                user_id, briefing_id, content, briefing_date
            )
            delivery_method = "websocket"
        elif delivery_mode == "voice":
            # Voice mode: WebSocket + Tavus audio
            # TODO: Stream D - implement Tavus voice delivery
            delivery_success = await self._deliver_via_websocket(
                user_id, briefing_id, content, briefing_date
            )
            delivery_method = "voice"
            logger.info(
                "Voice delivery requested but not yet implemented, falling back to WebSocket",
                extra={"user_id": user_id},
            )
        elif delivery_mode == "avatar":
            # Avatar mode: WebSocket + Tavus video
            # TODO: Stream D - implement Tavus avatar delivery
            delivery_success = await self._deliver_via_websocket(
                user_id, briefing_id, content, briefing_date
            )
            delivery_method = "avatar"
            logger.info(
                "Avatar delivery requested but not yet implemented, falling back to WebSocket",
                extra={"user_id": user_id},
            )
        else:
            # Unknown mode - default to WebSocket
            delivery_success = await self._deliver_via_websocket(
                user_id, briefing_id, content, briefing_date
            )
            delivery_method = "websocket"

        # Create notification regardless of delivery method
        await self._create_briefing_notification(user_id, briefing_id, content, briefing_date)

        # Update delivery status in DB
        now = datetime.now(UTC).isoformat()
        try:
            self._db.table("daily_briefings").update(
                {
                    "delivery_method": delivery_method,
                    "delivered_at": now,
                    "ws_delivered": True,
                }
            ).eq("id", briefing_id).execute()

            logger.info(
                "Briefing delivered successfully",
                extra={
                    "user_id": user_id,
                    "briefing_id": briefing_id,
                    "delivery_method": delivery_method,
                    "briefing_date": briefing_date.isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to update delivery status",
                extra={"user_id": user_id, "briefing_id": briefing_id, "error": str(e)},
            )

        return {
            "success": delivery_success,
            "delivery_method": delivery_method,
            "briefing_id": briefing_id,
            "delivered_at": now,
        }

    async def _get_delivery_mode(self, user_id: str) -> str:
        """Get user's preferred briefing delivery mode.

        Args:
            user_id: The user's UUID.

        Returns:
            Delivery mode: 'chat', 'voice', or 'avatar'. Defaults to 'chat'.
        """
        try:
            prefs_result = (
                self._db.table("user_preferences")
                .select("briefing_delivery_mode")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if prefs_result.data:
                mode = prefs_result.data[0].get("briefing_delivery_mode", "chat")
                if mode in ("chat", "voice", "avatar"):
                    return mode
        except Exception as e:
            logger.debug(
                "Could not fetch delivery mode, using default",
                extra={"user_id": user_id, "error": str(e)},
            )
        return "chat"

    async def _deliver_via_websocket(
        self,
        user_id: str,
        briefing_id: str,
        content: dict[str, Any],
        briefing_date: date,
    ) -> bool:
        """Deliver briefing via WebSocket broadcast and chat message.

        Sends the briefing as:
        1. An ARIA message via WebSocket (if user is connected)
        2. A briefing.ready event for frontend listeners
        3. A chat message in the user's active conversation

        If the user is offline, the WebSocket send is a no-op (the user
        will receive it via _maybe_deliver_morning_briefing on reconnect).
        The chat message ensures the briefing is always persisted and
        accessible.

        Args:
            user_id: The user's UUID.
            briefing_id: The briefing's UUID.
            content: The briefing content.
            briefing_date: The briefing date.

        Returns:
            True if delivery succeeded (always True — offline is not a failure).
        """
        from src.core.ws import ws_manager

        summary = content.get("summary", "")
        rich_content = content.get("rich_content", [])
        ui_commands = content.get("ui_commands", [])
        suggestions = content.get("suggestions", ["Show me details", "Dismiss"])

        ws_sent = False

        # 1. Send ARIA message via WebSocket (no-op if user offline)
        try:
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=summary,
                rich_content=rich_content,
                ui_commands=ui_commands,
                suggestions=suggestions,
            )
            ws_sent = True
        except Exception as e:
            logger.debug(
                "WebSocket ARIA message send failed (user may be offline)",
                extra={"user_id": user_id, "error": str(e)},
            )

        # 2. Broadcast briefing.ready event for frontend listeners
        try:
            await ws_manager.send_raw_to_user(
                user_id,
                {
                    "type": "briefing.ready",
                    "payload": {
                        "briefing_id": briefing_id,
                        "briefing_date": briefing_date.isoformat(),
                        "summary": summary[:500] if summary else "",
                        "sections": list(content.keys()),
                        "generated_at": content.get("generated_at", ""),
                    },
                },
            )
        except Exception as e:
            logger.debug(
                "WebSocket briefing.ready event failed (user may be offline)",
                extra={"user_id": user_id, "error": str(e)},
            )

        # 3. Post briefing as a chat message in the user's conversation
        try:
            await self._post_briefing_as_chat_message(
                user_id, briefing_id, content, briefing_date
            )
        except Exception as e:
            logger.warning(
                "Failed to post briefing as chat message",
                extra={"user_id": user_id, "error": str(e)},
            )

        logger.info(
            "Briefing delivery completed",
            extra={
                "user_id": user_id,
                "briefing_id": briefing_id,
                "ws_sent": ws_sent,
            },
        )
        # Always return True — the briefing is generated and stored.
        # Offline users receive it on next WebSocket connect.
        return True

    async def _create_briefing_notification(
        self,
        user_id: str,
        briefing_id: str,
        content: dict[str, Any],
        briefing_date: date,
    ) -> None:
        """Create a notification for the briefing.

        Args:
            user_id: The user's UUID.
            briefing_id: The briefing's UUID.
            content: The briefing content.
            briefing_date: The briefing date.
        """
        try:
            from src.models.notification import NotificationType
            from src.services.notification_service import NotificationService

            summary = content.get("summary", "")
            # Truncate summary for notification body
            body = summary[:200] + "..." if len(summary) > 200 else summary

            await NotificationService.create_notification(
                user_id=user_id,
                type=NotificationType.BRIEFING_READY,
                title="Your morning briefing is ready",
                message=body,
                link="/briefing",
                metadata={
                    "briefing_id": briefing_id,
                    "briefing_date": briefing_date.isoformat(),
                },
            )

            logger.debug(
                "Briefing notification created",
                extra={"user_id": user_id, "briefing_id": briefing_id},
            )
        except Exception as e:
            logger.warning(
                "Failed to create briefing notification",
                extra={"user_id": user_id, "briefing_id": briefing_id, "error": str(e)},
            )

    async def _post_briefing_as_chat_message(
        self,
        user_id: str,
        briefing_id: str,
        content: dict[str, Any],
        briefing_date: date,
    ) -> None:
        """Post the briefing as an assistant message in the user's conversation.

        Finds today's most recent conversation or creates a new one, then
        inserts the briefing summary as an assistant message. This ensures
        the briefing is accessible in chat history even if the user was
        offline during WebSocket delivery.

        Args:
            user_id: The user's UUID.
            briefing_id: The briefing's UUID.
            content: The briefing content dict.
            briefing_date: The briefing date.
        """
        import uuid as _uuid

        from src.services.conversations import ConversationService

        db = self._db
        conv_svc = ConversationService(db_client=db)

        summary = content.get("summary", "")
        if not summary:
            return

        # Find today's most recent conversation for this user
        today_str = briefing_date.isoformat()
        conversation_id: str | None = None

        try:
            result = (
                db.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", f"{today_str}T00:00:00")
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                conversation_id = result.data[0]["id"]
        except Exception:
            logger.debug(
                "Could not find existing conversation for briefing",
                extra={"user_id": user_id},
            )

        # Create a new conversation if none exists today
        if not conversation_id:
            conversation_id = str(_uuid.uuid4())
            try:
                db.table("conversations").insert(
                    {
                        "id": conversation_id,
                        "user_id": user_id,
                        "title": f"Morning Briefing - {briefing_date.strftime('%b %d')}",
                        "message_count": 0,
                    }
                ).execute()
            except Exception as e:
                logger.warning(
                    "Failed to create conversation for briefing",
                    extra={"user_id": user_id, "error": str(e)},
                )
                return

        # Insert briefing as assistant message
        await conv_svc.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=summary,
            metadata={
                "type": "morning_briefing",
                "briefing_id": briefing_id,
                "briefing_date": today_str,
            },
        )

        # Update conversation metadata
        try:
            preview = summary[:100] + "..." if len(summary) > 100 else summary
            db.table("conversations").update(
                {
                    "message_count": 1,
                    "last_message_at": datetime.now(UTC).isoformat(),
                    "last_message_preview": preview,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", conversation_id).execute()
        except Exception:
            logger.debug("Could not update conversation metadata for briefing")

        logger.info(
            "Briefing posted as chat message",
            extra={
                "user_id": user_id,
                "briefing_id": briefing_id,
                "conversation_id": conversation_id,
            },
        )

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
                        "start_time": meeting.get("start_time", ""),
                        "date": meeting.get("date", ""),
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
                        "headline": f"Overdue: {_sanitize_text(task.get('task', 'Unknown task'))}",
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
        suggestions.extend(
            [
                "Focus on the critical meeting",
                "Show me the buying signals",
                "Update me on competitor activity",
            ]
        )

        return suggestions[:5]  # Limit to 5 suggestions

    async def _get_calendar_data(
        self,
        user_id: str,
        briefing_date: date,
    ) -> dict[str, Any]:
        """Get calendar events for the day from calendar_events table.

        Queries the calendar_events table (synced from Google/Outlook) with
        timezone-aware filtering. Falls back to Composio API if table is empty.

        Args:
            user_id: The user's ID.
            briefing_date: The date to get calendar for.

        Returns:
            Dict with meeting_count, key_meetings, and tomorrow_meetings info.
        """
        # Get user's timezone for proper date filtering
        user_tz_str = await self._get_user_timezone(user_id)
        user_tz = ZoneInfo(user_tz_str)

        # Calculate today's date range in user's timezone
        now_local = datetime.now(user_tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end_local = today_start_local + timedelta(days=1)
        tomorrow_end_local = today_start_local + timedelta(days=2)

        # Convert to UTC for database queries
        today_start_utc = today_start_local.astimezone(UTC)
        today_end_utc = today_end_local.astimezone(UTC)
        tomorrow_end_utc = tomorrow_end_local.astimezone(UTC)

        # First, try to get events from calendar_events table
        try:
            today_result = (
                self._db.table("calendar_events")
                .select("id, title, start_time, end_time, attendees, source")
                .eq("user_id", user_id)
                .gte("start_time", today_start_utc.isoformat())
                .lt("start_time", today_end_utc.isoformat())
                .order("start_time", desc=False)
                .limit(20)
                .execute()
            )

            # Format today's meetings from calendar_events
            key_meetings = []
            for row in today_result.data or []:
                if not isinstance(row, dict):
                    continue
                # Skip buffer events (e.g. "[15-minute buffer before ...]")
                title = row.get("title", "")
                title_lower = (title or "").lower()
                if "[buffer" in title_lower or "buffer]" in title_lower:
                    continue
                formatted_time = await self._format_time_in_user_timezone(
                    row.get("start_time", ""), user_id
                )
                attendees_raw = row.get("attendees", [])
                attendees = []
                if isinstance(attendees_raw, list):
                    for att in attendees_raw[:5]:
                        if isinstance(att, dict):
                            attendees.append({
                                "email": att.get("email", ""),
                                "name": att.get("name", ""),
                            })
                        elif isinstance(att, str):
                            attendees.append({"email": att, "name": ""})

                # Build ISO start_time and formatted date for frontend
                raw_start = row.get("start_time", "")
                formatted_date = ""
                iso_start = ""
                if raw_start:
                    try:
                        cleaned_ts = raw_start.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(cleaned_ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        user_tz_str = await self._get_user_timezone(user_id)
                        local_dt = dt.astimezone(ZoneInfo(user_tz_str))
                        formatted_date = local_dt.strftime("%B %-d, %Y")
                        iso_start = dt.isoformat()
                    except Exception:
                        iso_start = raw_start
                        formatted_date = ""

                key_meetings.append({
                    "id": row.get("id", ""),
                    "title": row.get("title", "Untitled Meeting"),
                    "time": formatted_time,
                    "start_time": iso_start,
                    "date": formatted_date,
                    "attendees": attendees,
                    "company": None,
                    "has_brief": False,
                })

            # Get tomorrow's meetings count for preview
            tomorrow_result = (
                self._db.table("calendar_events")
                .select("id, title, start_time")
                .eq("user_id", user_id)
                .gte("start_time", today_end_utc.isoformat())
                .lt("start_time", tomorrow_end_utc.isoformat())
                .order("start_time", desc=False)
                .limit(5)
                .execute()
            )
            tomorrow_meetings = [
                m for m in (tomorrow_result.data or [])
                if isinstance(m, dict)
                and not (
                    "[buffer" in (m.get("title", "") or "").lower()
                    or "buffer]" in (m.get("title", "") or "").lower()
                )
            ]
            first_tomorrow = tomorrow_meetings[0] if tomorrow_meetings else None
            tomorrow_first_time = None
            tomorrow_first_title = None
            if first_tomorrow and isinstance(first_tomorrow, dict):
                tomorrow_first_time = await self._format_time_in_user_timezone(
                    first_tomorrow.get("start_time", ""), user_id
                )
                tomorrow_first_title = first_tomorrow.get("title", "Meeting")

            logger.info(
                "Calendar events fetched from calendar_events table",
                extra={
                    "user_id": user_id,
                    "briefing_date": briefing_date.isoformat(),
                    "today_count": len(key_meetings),
                    "tomorrow_count": len(tomorrow_meetings),
                },
            )

            return {
                "meeting_count": len(key_meetings),
                "key_meetings": key_meetings,
                "tomorrow_count": len(tomorrow_meetings),
                "tomorrow_first_time": tomorrow_first_time,
                "tomorrow_first_title": tomorrow_first_title,
            }

        except Exception as e:
            logger.warning(
                "Failed to fetch from calendar_events table, falling back to Composio",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True,
            )

        # Fall back to Composio API if calendar_events table query failed
        try:
            integration_result = (
                self._db.table("user_integrations")
                .select("id, integration_type, status, composio_connection_id")
                .eq("user_id", user_id)
                .eq("status", "active")
                .in_("integration_type", list(_CALENDAR_INTEGRATION_TYPES))
                .limit(1)
                .execute()
            )

            if not integration_result or not integration_result.data:
                logger.debug(
                    "No calendar integration for user",
                    extra={"user_id": user_id},
                )
                return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

            integration = integration_result.data[0]
            provider = integration.get("integration_type")
            connection_id = integration.get("composio_connection_id")

            if not connection_id:
                return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

            action_slug = _CALENDAR_READ_ACTIONS.get(provider)
            if not action_slug:
                return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

            oauth_client = self._get_oauth_client()
            if oauth_client is None:
                return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

            # Build time range for today
            time_min = f"{briefing_date.isoformat()}T00:00:00Z"
            time_max = f"{briefing_date.isoformat()}T23:59:59Z"

            if provider == "google_calendar":
                action_params = {"timeMin": time_min, "timeMax": time_max}
            else:
                action_params = {"start_datetime": time_min, "end_datetime": time_max}

            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action=action_slug,
                params=action_params,
                user_id=user_id,
                circuit_breaker=composio_calendar_circuit_breaker,
                dangerously_skip_version_check=(provider != "google_calendar"),
            )

            if not result.get("successful"):
                return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

            data = result.get("data", {})
            events = data.get("events", data.get("items", data.get("value", [])))
            if not isinstance(events, list):
                events = [events] if events else []

            key_meetings = []
            for event in events[:10]:
                if not isinstance(event, dict):
                    continue
                # Skip buffer events in Composio results
                event_title = event.get("summary", event.get("subject", ""))
                event_title_lower = (event_title or "").lower()
                if "[buffer" in event_title_lower or "buffer]" in event_title_lower:
                    continue
                start_time = event.get("start", {})
                if isinstance(start_time, dict):
                    time_str = start_time.get("dateTime", start_time.get("date", ""))
                else:
                    time_str = str(start_time)

                formatted_time = await self._format_time_in_user_timezone(time_str, user_id)

                attendees_raw = event.get("attendees", event.get("requiredAttendees", []))
                attendees = []
                if isinstance(attendees_raw, list):
                    for att in attendees_raw[:5]:
                        if isinstance(att, dict):
                            email = att.get("emailAddress", {}).get("address", "") if isinstance(att.get("emailAddress"), dict) else att.get("email", att.get("address", ""))
                            name = att.get("emailAddress", {}).get("name", "") if isinstance(att.get("emailAddress"), dict) else att.get("name", "")
                            attendees.append({"email": email, "name": name})

                key_meetings.append({
                    "id": event.get("id", ""),
                    "title": event.get("summary", event.get("subject", "Untitled Meeting")),
                    "time": formatted_time,
                    "attendees": attendees,
                    "company": None,
                    "has_brief": False,
                })

            return {
                "meeting_count": len(key_meetings),
                "key_meetings": key_meetings,
                "tomorrow_count": 0,  # Composio fallback doesn't check tomorrow
            }

        except Exception:
            logger.warning(
                "Failed to fetch calendar events via Composio fallback",
                extra={"user_id": user_id},
                exc_info=True,
            )
            return {"meeting_count": 0, "key_meetings": [], "tomorrow_count": 0}

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
                "title": s.get("headline", ""),
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
                            if any(h.get("title") == headline for h in company_news):
                                continue

                            company_news.append(
                                {
                                    "id": f"exa-{hash(item.url) % 10000}",
                                    "company_name": company_name,
                                    "title": headline,
                                    "summary": item.text[:300] if item.text else "",
                                    "relevance_score": 0.75,
                                    "detected_at": item.published_date
                                    or datetime.now(UTC).isoformat(),
                                    "source": "exa_realtime",
                                    "url": item.url,
                                }
                            )

                        # Get similar companies for competitive intel
                        if website and len(competitive_intel) < 10:
                            similar_results = await exa.find_similar(
                                url=website,
                                num_results=3,
                                exclude_domains=[website.split("//")[1].split("/")[0]]
                                if "://" in website
                                else None,
                            )

                            for item in similar_results:
                                # Extract competitor name from URL
                                competitor_name = (
                                    item.title.split(" - ")[0]
                                    if " - " in item.title
                                    else item.title[:50]
                                )
                                competitive_intel.append(
                                    {
                                        "id": f"exa-similar-{hash(item.url) % 10000}",
                                        "company_name": competitor_name,
                                        "title": f"Similar to {company_name}: {item.title}",
                                        "summary": item.text[:200] if item.text else "",
                                        "relevance_score": 0.6,
                                        "detected_at": datetime.now(UTC).isoformat(),
                                        "source": "exa_similar",
                                        "url": item.url,
                                    }
                                )

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
        """Get task status from goals and goal_milestones tables.

        Queries goals and goal_milestones for open (non-complete) tasks.
        Also checks prospective_memories for overdue tasks (legacy support).
        Deduplicates by title, keeping the item with the earliest due_date.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with overdue, due_today, and open_tasks_count.
        """
        now = datetime.now(UTC)

        # Get open tasks from goals table (non-complete, non-cancelled, non-failed)
        open_goals_result = (
            self._db.table("goals")
            .select("id, title, status, target_date")
            .eq("user_id", user_id)
            .in_("status", ["draft", "plan_ready", "active", "paused"])
            .order("target_date", desc=False)
            .limit(20)
            .execute()
        )

        open_tasks = []
        for g in open_goals_result.data or []:
            if not isinstance(g, dict):
                continue
            open_tasks.append({
                "id": g["id"],
                "title": g.get("title", "Untitled goal"),
                "status": g.get("status"),
                "due_date": g.get("target_date"),
            })

        # Collect overdue items from multiple sources, then deduplicate
        overdue_items: dict[str, dict[str, Any]] = {}  # title -> item (keep earliest due)

        # 1. Overdue goals (due_date < now, not complete/cancelled/failed)
        overdue_goals_result = (
            self._db.table("goals")
            .select("id, title, status, target_date")
            .eq("user_id", user_id)
            .not_.in_("status", ["complete", "cancelled", "failed"])
            .lt("target_date", now.isoformat())
            .limit(20)
            .execute()
        )
        for g in overdue_goals_result.data or []:
            if not isinstance(g, dict):
                continue
            title = _sanitize_text(g.get("title", ""))
            due_date = g.get("target_date")
            if title and (
                title not in overdue_items
                or (due_date and overdue_items[title].get("due_at", "z") > due_date)
            ):
                overdue_items[title] = {
                    "id": g["id"],
                    "task": title,
                    "source": "goal",
                    "due_at": due_date,
                }

        # 2. Overdue goal_milestones (join with goals to ensure goal is active)
        # Query milestones directly, then filter by goal status in Python
        # since Supabase client doesn't support complex joins
        overdue_milestones_result = (
            self._db.table("goal_milestones")
            .select("id, goal_id, title, status, due_date")
            .not_.in_("status", ["complete", "cancelled", "done"])
            .lt("due_date", now.isoformat())
            .limit(50)
            .execute()
        )

        # Get goal statuses for filtering
        goal_ids = list({
            m.get("goal_id")
            for m in (overdue_milestones_result.data or [])
            if isinstance(m, dict) and m.get("goal_id")
        })
        goal_statuses: dict[str, str] = {}
        if goal_ids:
            goals_for_milestones = (
                self._db.table("goals")
                .select("id, status, user_id")
                .in_("id", goal_ids)
                .execute()
            )
            for goal in goals_for_milestones.data or []:
                if isinstance(goal, dict):
                    # Only include milestones for user's active goals
                    if goal.get("user_id") == user_id and goal.get("status") not in [
                        "complete",
                        "cancelled",
                        "failed",
                    ]:
                        goal_statuses[goal["id"]] = goal.get("status", "")

        for m in overdue_milestones_result.data or []:
            if not isinstance(m, dict):
                continue
            goal_id = m.get("goal_id")
            if goal_id not in goal_statuses:
                continue  # Skip milestones from inactive/other-user goals
            title = _sanitize_text(m.get("title", ""))
            due_date = m.get("due_date")
            if title and (
                title not in overdue_items
                or (due_date and overdue_items[title].get("due_at", "z") > due_date)
            ):
                overdue_items[title] = {
                    "id": m["id"],
                    "task": title,
                    "source": "milestone",
                    "due_at": due_date,
                }

        # 3. Overdue tasks from prospective_memories (legacy support)
        # Also fetch metadata to check for email thread reply evidence
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        overdue_pm_result = (
            self._db.table("prospective_memories")
            .select("id, task, priority, trigger_config, metadata")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .lt("trigger_config->>due_at", today_start.isoformat())
            .limit(20)
            .execute()
        )
        for t in overdue_pm_result.data or []:
            if not isinstance(t, dict):
                continue

            # Check if user already replied to this email thread
            metadata = t.get("metadata") or {}
            thread_id = metadata.get("thread_id")
            if thread_id and metadata.get("source") == "email_commitment":
                try:
                    reply_check = (
                        self._db.table("email_scan_log")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("thread_id", thread_id)
                        .eq("user_replied", True)
                        .limit(1)
                        .execute()
                    )
                    if reply_check.data:
                        # User already replied — auto-resolve and skip
                        try:
                            self._db.table("prospective_memories").update(
                                {"status": "completed"}
                            ).eq("id", t["id"]).execute()
                            logger.info(
                                "BRIEFING: Auto-resolved prospective_memory %s "
                                "(user replied to thread %s)",
                                t["id"],
                                thread_id,
                            )
                        except Exception as resolve_e:
                            logger.debug(
                                "BRIEFING: Failed to auto-resolve pm %s: %s",
                                t["id"],
                                resolve_e,
                            )
                        continue  # Skip this item from overdue list
                except Exception as check_e:
                    logger.debug(
                        "BRIEFING: Reply check failed for thread %s: %s",
                        thread_id,
                        check_e,
                    )

            title = _sanitize_text(t.get("task", ""))
            due_at = t.get("trigger_config", {}).get("due_at")
            if title and (
                title not in overdue_items
                or (due_at and overdue_items[title].get("due_at", "z") > due_at)
            ):
                overdue_items[title] = {
                    "id": t["id"],
                    "task": title,
                    "source": "prospective_memory",
                    "priority": t.get("priority"),
                    "due_at": due_at,
                }

        # Sort by due_at and convert to list
        overdue = sorted(
            overdue_items.values(),
            key=lambda x: x.get("due_at") or "z",
        )[:10]  # Limit to 10 overdue items

        return {
            "overdue": overdue,
            "due_today": [],  # Goals don't have due_today concept
            "open_tasks": open_tasks,
            "open_tasks_count": len(open_tasks),
        }

    async def _generate_summary(
        self,
        user_id: str,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
        tasks: dict[str, Any],
        email_data: dict[str, Any],
        tone_guidance: str = "",
        queued_insights: list[dict[str, Any]] | None = None,
        causal_actions: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate executive summary using LLM with PersonaBuilder.

        Args:
            user_id: The user's ID for persona context.
            calendar: Calendar data dict.
            leads: Lead data dict.
            signals: Signal data dict.
            tasks: Task data dict.
            email_data: Email data dict.
            tone_guidance: Personality-calibrated tone guidance.
            queued_insights: Optional queued insights from briefing_queue.
            causal_actions: Optional causal reasoning actions from market signals.

        Returns:
            Generated summary string.
        """
        meeting_count = calendar.get("meeting_count", 0)
        attention_count = len(leads.get("needs_attention", []))
        signal_count = len(signals.get("company_news", []))
        overdue_count = len(tasks.get("overdue", []))
        email_count = email_data.get("total_received", 0)
        drafts_waiting = email_data.get("drafts_waiting", 0)
        meetings_without_debriefs = tasks.get("meetings_without_debriefs", 0)
        total_activity = (
            meeting_count + attention_count + signal_count + overdue_count + email_count
        )

        # Determine time-appropriate greeting
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        # Format causal actions for the prompt
        causal_note = ""
        if causal_actions:
            causal_lines = []
            for action in causal_actions[:3]:
                causal_lines.append(
                    f"- {action.get('recommended_action', '')} "
                    f"(urgency: {action.get('urgency', 'normal')}, timing: {action.get('timing', 'flexible')})"
                )
            if causal_lines:
                causal_note = (
                    "\n\nMarket intelligence actions recommended:\n"
                    + "\n".join(causal_lines)
                    + "\nWeave the most urgent action into your summary if relevant."
                )

        if total_activity == 0:
            prompt = (
                "Generate a brief, professional briefing summary (2-3 sentences) "
                "for a user whose intelligence feeds are still initializing. They have no meetings, "
                "leads, signals, or tasks yet. Let them know ARIA is still building their "
                "intelligence profile and encourage them to add leads, connect their calendar, "
                "or set goals so ARIA can start working for them. "
                "Do not use emojis. Use clean, professional language. "
                f'Start with "{greeting}."'
            )
        else:
            debrief_note = (
                f"\nMeetings without debriefs: {meetings_without_debriefs}"
                if meetings_without_debriefs > 0
                else ""
            )
            queued_note = ""
            if queued_insights:
                items = [qi.get("title", qi.get("message", "")) for qi in queued_insights[:5]]
                queued_note = f"\nOvernight insights queued: {', '.join(items)}"

            # Format strategic email patterns for the LLM
            email_patterns = email_data.get("strategic_patterns", [])
            patterns_note = ""
            if email_patterns:
                pattern_lines = []
                for p in email_patterns[:5]:
                    pattern_lines.append(f"- [{p.get('type', 'pattern')}] {p.get('insight', '')}")
                patterns_note = (
                    "\n\nEmail patterns detected (METADATA ONLY - no email body content available):\n"
                    + "\n".join(pattern_lines)
                    + "\nYou may mention a pattern if factually supported. Never infer email content or conversation direction."
                )

            # Build rich data sections so the LLM can reference specifics
            calendar_details = ""
            if calendar.get("key_meetings"):
                meeting_lines = []
                for m in calendar["key_meetings"][:6]:
                    attendee_names = [
                        a.get("name") or a.get("email", "Unknown")
                        for a in m.get("attendees", [])
                    ]
                    attendee_str = ", ".join(attendee_names) if attendee_names else "no attendees listed"
                    meeting_lines.append(
                        f"  - {m.get('time', '?')}: \"{m.get('title', 'Untitled')}\" with {attendee_str}"
                    )
                calendar_details = "\n".join(meeting_lines)
            calendar_section = (
                f"CALENDAR ({meeting_count} meetings today):\n{calendar_details}"
                if calendar_details
                else f"CALENDAR: No meetings today - open schedule."
            )

            overdue_details = ""
            if tasks.get("overdue"):
                overdue_lines = []
                for t in tasks["overdue"][:5]:
                    days_overdue = ""
                    if t.get("due_at"):
                        try:
                            due = datetime.fromisoformat(t["due_at"].replace("Z", "+00:00"))
                            delta = (datetime.now(UTC) - due).days
                            days_overdue = f" (overdue by {delta} days)" if delta > 0 else ""
                        except (ValueError, TypeError):
                            pass
                    overdue_lines.append(f"  - \"{_sanitize_text(t.get('task', 'Untitled'))}\"{days_overdue}")
                overdue_details = "\n".join(overdue_lines)
            overdue_section = (
                f"OVERDUE TASKS ({overdue_count}):\n{overdue_details}"
                if overdue_details
                else ""
            )

            lead_details = ""
            if leads.get("needs_attention"):
                lead_lines = []
                for l in leads["needs_attention"][:3]:
                    score = l.get("health_score")
                    score_str = f" (health: {score}/100)" if score is not None else ""
                    lead_lines.append(f"  - {l.get('company_name', 'Unknown')}{score_str}")
                lead_details = "\n".join(lead_lines)
            lead_section = (
                f"LEADS NEEDING ATTENTION ({attention_count}):\n{lead_details}"
                if lead_details
                else ""
            )

            signal_details = ""
            all_signals = signals.get("company_news", []) + signals.get("market_trends", [])
            if all_signals:
                signal_lines = []
                for s in sorted(all_signals, key=lambda x: x.get("relevance_score", 0), reverse=True)[:3]:
                    signal_lines.append(
                        f"  - {s.get('company_name', 'Unknown')}: {s.get('title', '')}"
                    )
                signal_details = "\n".join(signal_lines)
            signal_section = (
                f"MARKET SIGNALS ({signal_count} new):\n{signal_details}"
                if signal_details
                else ""
            )

            email_details = ""
            if email_data.get("needs_attention"):
                email_lines = []
                for e in email_data["needs_attention"][:5]:
                    company_str = f" ({e['company']})" if e.get("company") else ""
                    email_lines.append(
                        f"  - From: {e.get('sender', 'Unknown')}{company_str} - Subject: \"{e.get('subject', 'No subject')}\""
                    )
                email_details = "\n".join(email_lines)
            email_section = (
                f"EMAILS ({email_count} received, {drafts_waiting} drafts waiting):\n{email_details}"
                if email_count > 0
                else ""
            )

            # Assemble all data sections
            data_sections = "\n\n".join(
                s for s in [
                    calendar_section,
                    overdue_section,
                    lead_section,
                    signal_section,
                    email_section,
                ]
                if s
            )

            prompt = f"""Generate a strategic morning briefing summary based on the following intelligence:

{data_sections}{debrief_note}{queued_note}{patterns_note}{causal_note}

YOUR ROLE: You are a strategic VP briefing your executive. Not a dashboard reading numbers. Not an assistant listing items.

BRIEFING RULES:
1. LEAD WITH WHAT MATTERS MOST. Not "you have X meetings." Instead: "Your priority today is [specific thing] because [specific reason]."
2. PRIORITIZE ruthlessly. The user has limited attention. What is the ONE thing they should focus on first?
3. CONNECT DOTS between data sources. If a meeting attendee also sent emails, mention that connection. If a market signal affects an upcoming meeting, connect them.
4. BE OPINIONATED. Say "I'd suggest..." or "The priority is..." - don't just list facts.
5. REFERENCE RELATIONSHIPS by name. "Rob Douglas" not "a contact." "Nira Systems" not "a company."
6. USE TIME CONTEXT. "overdue by 11 days" is more urgent than "overdue by 2 days." Say which ones are getting stale.
7. KEEP IT SHORT. 3-5 sentences for the summary. Users scan, they don't read paragraphs.
8. SUGGEST SPECIFIC ACTIONS. Not "address overdue tasks" but "Reply to Rob Douglas - he's been waiting 5 days."

WHAT NOT TO DO:
- Don't start with "Good morning" followed by counts of items. That's generic.
- Don't list every data point. Prioritize the top 2-3 things.
- Don't use corporate jargon like "leverage," "synergize," "action items."
- Don't repeat the same information in different ways.
- Don't use emojis. Use clean, professional language.

FORMAT: Return ONLY the briefing summary text. No JSON, no markdown, no bullet points. Just natural conversational prose, 3-5 sentences.

{get_email_guardrail()}
{get_formatting_rules()}
IMPORTANT: Only describe information you can directly verify from the data provided above. It is better to say less than to say something inaccurate.
"""

        # Inject tone guidance if available
        if tone_guidance:
            prompt = f"TONE: {tone_guidance}\n\n{prompt}"

        # Build system prompt using PersonaBuilder for personality consistency
        system_prompt = ""
        try:
            builder = self._get_persona_builder()
            # Format causal actions as pre-rendered text for PersonaBuilder Layer 7
            causal_actions_text = ""
            if causal_actions:
                causal_lines = []
                for action in causal_actions[:3]:
                    causal_lines.append(
                        f"- {action.get('recommended_action', '')} "
                        f"(urgency: {action.get('urgency', 'normal')})"
                    )
                if causal_lines:
                    causal_actions_text = "Market Intelligence Actions:\n" + "\n".join(causal_lines)

            request = PersonaRequest(
                user_id=user_id,
                agent_name="briefing",
                agent_role_description="Strategic VP-level morning briefing generator that prioritizes what matters most, connects dots between data sources, and suggests specific actions",
                task_description="Generate a prioritized, opinionated morning briefing that leads with the most important item and references people and companies by name",
                causal_actions=causal_actions_text if causal_actions_text else None,
            )
            ctx = await builder.build(request)
            system_prompt = ctx.to_system_prompt()
        except Exception as e:
            logger.warning(
                "Failed to build PersonaBuilder context for briefing, using fallback",
                extra={"user_id": user_id},
                exc_info=True,
            )

        # Call LLM with defensive error handling
        try:
            if system_prompt:
                return await self._llm.generate_response(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=400,
                    task=TaskType.ANALYST_SUMMARIZE,
                    agent_id="briefing",
                )
            else:
                # Fallback without PersonaBuilder
                return await self._llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                    task=TaskType.ANALYST_SUMMARIZE,
                    agent_id="briefing",
                )
        except Exception as llm_error:
            logger.error(
                "LLM call failed during briefing summary generation, using fallback",
                extra={"user_id": user_id, "error": str(llm_error)},
                exc_info=True,
            )
            # Return a minimal but valid summary so the briefing doesn't crash
            meeting_count = calendar.get("meeting_count", 0)
            if meeting_count > 0:
                return f"{greeting}. You have {meeting_count} meetings today."
            else:
                return f"{greeting}. Your daily briefing is ready."

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
            "strategic_patterns": [],
            "connections": [],
        }

        try:
            # Check if user has email integration
            integration_result = (
                self._db.table("user_integrations")
                .select("integration_type, status")
                .eq("user_id", user_id)
                .in_("integration_type", ["gmail", "outlook"])
                .eq("status", "active")
                .limit(1)
                .execute()
 )
            integration_record = integration_result.data[0] if integration_result and integration_result.data else None
            if not integration_record:
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

                needs_attention.append(
                    {
                        "sender": draft.recipient_name or draft.recipient_email,
                        "company": company,
                        "subject": draft.subject,
                        "summary": await self._summarize_draft_context(draft),
                        "urgency": "NORMAL",
                        "draft_status": "saved_to_drafts",
                        "draft_confidence": confidence_label,
                        "aria_notes": draft.aria_notes,
                        "draft_id": draft.draft_id,
                    }
                )

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

            # Cross-email pattern synthesis
            email_patterns = await self._synthesize_email_patterns(user_id, scan_result)

            # Build cross-thread connections from clustering results
            connections = [
                {
                    "topic": c.topic,
                    "emails": [
                        f"{s}: {subj}"
                        for s, subj in zip(c.senders, c.subjects)
                    ],
                    "insight": c.connection,
                }
                for c in getattr(processing_result, "cross_references", [])
            ]

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
                "strategic_patterns": email_patterns,
                "connections": connections,
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
                        json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
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

    # Personal email domains excluded from company clustering
    _PERSONAL_DOMAINS = {
        "gmail.com", "googlemail.com",
        "outlook.com", "outlook.co.uk", "hotmail.com", "hotmail.co.uk",
        "live.com", "live.co.uk", "msn.com",
        "yahoo.com", "yahoo.co.uk", "yahoo.ca",
        "icloud.com", "me.com", "mac.com",
        "aol.com", "comcast.net", "verizon.net", "att.net",
        "protonmail.com", "proton.me", "tutanota.com", "hey.com",
        "zoho.com", "mail.com", "gmx.com", "gmx.net",
        "fastmail.com",
    }

    async def _synthesize_email_patterns(
        self, user_id: str, scan_result: Any
    ) -> list[dict[str, Any]]:
        """Detect strategic patterns across multiple emails.

        Looks for company clustering (multiple emails from the same org),
        topic clustering (converging themes across senders), and volume
        anomalies compared to the user's historical average.

        Args:
            user_id: The user's ID.
            scan_result: EmailScanResult from the analyzer.

        Returns:
            List of pattern dicts, each with a ``type`` and ``insight`` key.
        """
        patterns: list[dict[str, Any]] = []
        all_emails = list(scan_result.needs_reply) + list(scan_result.fyi)

        # ------------------------------------------------------------------
        # 1. Company clustering - multiple emails from the same organisation
        # ------------------------------------------------------------------
        company_emails: dict[str, list[Any]] = {}
        for email in all_emails:
            domain = email.sender_email.split("@")[-1].lower()
            if domain not in self._PERSONAL_DOMAINS:
                company_emails.setdefault(domain, []).append(email)

        for domain, emails in company_emails.items():
            if len(emails) >= 2:
                senders = list({e.sender_name for e in emails})
                subjects = [e.subject for e in emails]
                patterns.append({
                    "type": "company_cluster",
                    "company_domain": domain,
                    "email_count": len(emails),
                    "senders": senders,
                    "subjects": subjects,
                    "insight": (
                        f"{len(emails)} emails from {domain} "
                        f"({', '.join(senders)}). "
                        f"Topics: {'; '.join(subjects)}"
                    ),
                })

        # ------------------------------------------------------------------
        # 2. Topic clustering - converging themes across different senders
        # ------------------------------------------------------------------
        if len(scan_result.needs_reply) >= 3:
            # Build email context with snippets when available (truncated to 200 chars)
            email_lines_list = []
            for e in scan_result.needs_reply:
                line = f"- From {e.sender_name}: {e.subject}"
                if e.snippet:
                    # Truncate snippet to 200 chars for LLM context efficiency
                    snippet_preview = e.snippet[:200].replace('\n', ' ').strip()
                    if snippet_preview:
                        line += f"\n  Preview: {snippet_preview}"
                email_lines_list.append(line)
            email_lines = "\n".join(email_lines_list)

            # Build constraint text based on whether we have snippets
            has_snippets = any(e.snippet for e in scan_result.needs_reply)
            if has_snippets:
                constraint_text = (
                    "CONSTRAINTS - FOLLOW EXACTLY:\n"
                    "- You have email previews (first 200 chars of body) in addition to subject lines.\n"
                    "- Base your analysis on the ACTUAL content shown in previews, not assumptions.\n"
                    "- DO identify patterns based on what the previews actually say.\n"
                    "- If a preview is missing or empty, only use the subject line for that email.\n"
                    "- DO NOT fabricate details not present in the previews or subjects.\n"
                )
            else:
                constraint_text = (
                    "CRITICAL CONSTRAINTS - FOLLOW EXACTLY:\n"
                    "- You have email METADATA only: sender names and subject lines.\n"
                    "- You do NOT have email body content. The email bodies were not provided.\n"
                    "- NEVER infer, guess, or describe what emails are about beyond what subjects state.\n"
                    "- NEVER describe the nature, intent, direction, or progress of email threads.\n"
                    "- NEVER use phrases like 'moving toward', 'discussing', 'negotiating', 'exploring', 'indicating'.\n"
                    "- NEVER fabricate relationship narratives or deal progress from subject lines.\n"
                    "- DO identify factual patterns: same sender, similar subjects, same company domain.\n"
                    "- If you cannot identify a pattern from subjects alone, return [].\n"
                )

            topics_prompt = (
                f"{constraint_text}\n"
                "Email data:\n"
                f"{email_lines}\n\n"
                "Return 0-2 factual patterns as a JSON array. Each element:\n"
                '{"pattern": "factual observation based on actual content", '
                '"emails_involved": ["sender1", "sender2"], "note": "optional context"}\n\n'
                "If no clear patterns, return []. REMEMBER: Less is more. Only state what is explicitly shown."
            )
            try:
                topic_response = await self._llm.generate_response(
                    messages=[{"role": "user", "content": topics_prompt}],
                    max_tokens=400,
                    temperature=0.0,
                    task=TaskType.ANALYST_SUMMARIZE,
                    agent_id="briefing",
                )
                parsed = json.loads(topic_response)
                if isinstance(parsed, list):
                    for p in parsed:
                        patterns.append({"type": "topic_cluster", **p})
            except (json.JSONDecodeError, Exception):
                logger.debug(
                    "Topic clustering LLM parse failed, skipping",
                    extra={"user_id": user_id},
                )

        # ------------------------------------------------------------------
        # 3. Activity anomaly - unusual volume vs historical average
        # ------------------------------------------------------------------
        total_today = len(scan_result.needs_reply) + len(scan_result.fyi)
        try:
            recent_runs = (
                self._db.table("email_processing_runs")
                .select("emails_scanned")
                .eq("user_id", user_id)
                .order("started_at", desc=True)
                .limit(10)
                .execute()
            )
            if recent_runs and recent_runs.data and len(recent_runs.data) >= 3:
                avg_volume = sum(
                    r["emails_scanned"] for r in recent_runs.data
                ) / len(recent_runs.data)
                if avg_volume > 0 and total_today > avg_volume * 1.5:
                    pct_above = int((total_today / avg_volume - 1) * 100)
                    patterns.append({
                        "type": "volume_anomaly",
                        "today_count": total_today,
                        "average_count": int(avg_volume),
                        "insight": (
                            f"Inbox volume is {total_today} emails - "
                            f"{pct_above}% above your average of "
                            f"{int(avg_volume)}"
                        ),
                    })
        except Exception:
            logger.debug(
                "Volume anomaly check failed",
                extra={"user_id": user_id},
                exc_info=True,
            )

        return patterns

    async def generate_video_briefing_context(self, user_id: str) -> str:
        """Generate a conversational script for video briefing delivery.

        Formats the daily briefing as natural speech optimized for Tavus
        avatar delivery. The output is designed to be spoken naturally,
        without markdown or formatting that would sound awkward when spoken.

        Args:
            user_id: The user's UUID.

        Returns:
            Conversational script string optimized for spoken delivery.
            Kept under 5,000 tokens for optimal Tavus LLM performance.
        """
        # Get or generate the briefing
        briefing = await self.get_or_generate_briefing(user_id)

        # Get user name for personalization from user_profiles
        user_name = "there"
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("full_name")
                .eq("id", user_id)
                .limit(1)
                .execute()
 )
            profile_record = profile_result.data[0] if profile_result and profile_result.data else None
            if profile_record:
                full_name = profile_record.get("full_name", "")
                if full_name:
                    user_name = full_name.split()[0]  # First name only
        except Exception:
            pass

        # Build conversational script
        script_parts = []

        # Opening greeting (time-appropriate)
        hour = datetime.now().hour
        if hour < 12:
            video_greeting = "Good morning"
        elif hour < 17:
            video_greeting = "Good afternoon"
        else:
            video_greeting = "Good evening"
        script_parts.append(f"{video_greeting}, {user_name}.")

        # Summary (the LLM-generated executive summary)
        summary = briefing.get("summary", "")
        if summary:
            # Remove "Good morning!" prefix if present (we add our own)
            summary = summary.replace("Good morning!", "").strip()
            if summary.startswith("Good morning"):
                summary = summary[13:].strip()  # Remove "Good morning" + space/punctuation
            script_parts.append(summary)

        # Calendar highlights
        calendar = briefing.get("calendar", {})
        meeting_count = calendar.get("meeting_count", 0)
        key_meetings = calendar.get("key_meetings", [])

        if meeting_count > 0:
            script_parts.append(
                f"You have {meeting_count} meeting{'s' if meeting_count > 1 else ''} today."
            )
            for i, meeting in enumerate(key_meetings[:3]):
                time = meeting.get("time", "")
                title = meeting.get("title", "Meeting")
                company = meeting.get("company")

                if i == 0:
                    script_parts.append("Your key meetings are:")
                if company:
                    script_parts.append(f"At {time}, {title} with {company}.")
                else:
                    script_parts.append(f"At {time}, {title}.")
        else:
            script_parts.append(
                "Your calendar is clear today, which gives you time for focused work."
            )

        # Lead updates
        leads = briefing.get("leads", {})
        hot_leads = leads.get("hot_leads", [])
        needs_attention = leads.get("needs_attention", [])

        if hot_leads:
            script_parts.append(
                f"You have {len(hot_leads)} hot lead{'s' if len(hot_leads) > 1 else ''} showing strong buying signals."
            )
            for lead in hot_leads[:3]:
                company = lead.get("company_name", "a company")
                score = lead.get("health_score", 0)
                script_parts.append(f"{company} has a health score of {score}.")

        if needs_attention:
            script_parts.append(
                f"{len(needs_attention)} lead{'s' if len(needs_attention) > 1 else ''} {'need' if len(needs_attention) == 1 else 'needs'} your attention."
            )
            for lead in needs_attention[:2]:
                company = lead.get("company_name", "a company")
                script_parts.append(f"{company} is showing declining engagement.")

        # Market signals
        signals = briefing.get("signals", {})
        company_news = signals.get("company_news", [])
        competitive_intel = signals.get("competitive_intel", [])

        if company_news or competitive_intel:
            total_signals = len(company_news) + len(competitive_intel)
            script_parts.append(
                f"I've detected {total_signals} market signal{'s' if total_signals > 1 else ''} for you."
            )

            for news in company_news[:2]:
                company = news.get("company_name", "a company")
                headline = news.get("headline", "")
                if headline:
                    script_parts.append(f"{company}: {headline}.")

            for intel in competitive_intel[:2]:
                company = intel.get("company_name", "a competitor")
                headline = intel.get("headline", "")
                if headline:
                    script_parts.append(f"Competitive intel on {company}: {headline}.")

        # Causal reasoning actions (market intelligence recommendations)
        causal_actions = briefing.get("causal_actions", [])
        if causal_actions:
            urgent_actions = [a for a in causal_actions if a.get("urgency") == "high"][:2]
            if urgent_actions:
                script_parts.append("Based on recent market signals, I recommend:")
                for action in urgent_actions:
                    rec = action.get("recommended_action", "")
                    timing = action.get("timing", "flexible")
                    if rec:
                        script_parts.append(f"{rec}. Timing: {timing}.")

        # Tasks due
        tasks = briefing.get("tasks", {})
        overdue = tasks.get("overdue", [])
        due_today = tasks.get("due_today", [])

        if overdue:
            script_parts.append(
                f"You have {len(overdue)} overdue task{'s' if len(overdue) > 1 else ''}."
            )
            for task in overdue[:2]:
                task_desc = _sanitize_text(task.get("task", "a task"))
                script_parts.append(f"{task_desc}.")

        if due_today:
            script_parts.append(
                f"{len(due_today)} task{'s' if len(due_today) > 1 else ''} {'are' if len(due_today) > 1 else 'is'} due today."
            )

        # Email summary
        email_summary = briefing.get("email_summary", {})
        drafts_waiting = email_summary.get("drafts_waiting", 0)
        drafts_high_confidence = email_summary.get("drafts_high_confidence", 0)
        needs_attention_emails = email_summary.get("needs_attention", [])

        if drafts_waiting > 0:
            conf_msg = ""
            if drafts_high_confidence > 0:
                conf_msg = f", including {drafts_high_confidence} high confidence draft{'s' if drafts_high_confidence > 1 else ''}"
            script_parts.append(
                f"I've prepared {drafts_waiting} email draft{'s' if drafts_waiting > 1 else ''} for you{conf_msg}."
            )

        if needs_attention_emails:
            script_parts.append(
                f"{len(needs_attention_emails)} email{'s' if len(needs_attention_emails) > 1 else ''} {'need' if len(needs_attention_emails) == 1 else 'needs'} your attention."
            )

        # Closing
        script_parts.append(
            "That's the picture for today. I'd prioritize the flagged items first."
        )

        # Join with natural pauses (double spaces for brief pauses)
        script = "  ".join(script_parts)

        # Ensure we stay under ~5,000 tokens (~20,000 characters as rough estimate)
        # Truncate if necessary while preserving the closing
        max_chars = 18000  # Conservative estimate for 4,500 tokens
        closing = " That's the picture for today. I'd prioritize the flagged items first."
        if len(script) > max_chars:
            script = script[: max_chars - len(closing)] + closing

        return script

    async def create_video_briefing_session(self, user_id: str) -> dict[str, Any]:
        """Create a Tavus video session for briefing delivery.

        Creates a Tavus conversation optimized for briefing delivery with:
        - session_type='briefing'
        - Conversational context as the briefing script
        - Cross-conversation memory so ARIA remembers past briefings
        - High turn_taking_patience for Sparrow-1 flow

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary with:
            - session_id: The video session UUID
            - room_url: The Tavus room URL for the video call
            - briefing_date: The date of the briefing

        Raises:
            ExternalServiceError: If Tavus API fails.
            DatabaseError: If database persistence fails.
        """
        from src.integrations.tavus import TavusAPIError, TavusConnectionError
        from src.integrations.tavus_persona import SessionType
        from src.services.video_service import VideoSessionService

        # Check if video briefing is enabled for user
        try:
            prefs_result = (
                self._db.table("user_preferences")
                .select("video_briefing_enabled")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
 )
            prefs_record = prefs_result.data[0] if prefs_result and prefs_result.data else None
            if (
                prefs_record
                and not prefs_record.get("video_briefing_enabled", False)
            ):
                logger.info(
                    "Video briefing not enabled for user",
                    extra={"user_id": user_id},
                )
                return {
                    "session_id": None,
                    "room_url": None,
                    "briefing_date": date.today().isoformat(),
                    "error": "video_briefing_not_enabled",
                }
        except Exception as e:
            logger.warning(
                "Failed to check video briefing preference",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Generate the conversational briefing script
        briefing_script = await self.generate_video_briefing_context(user_id)

        # Build custom greeting for briefing (time-appropriate)
        _hour = datetime.now().hour
        _greet = "Good morning" if _hour < 12 else ("Good afternoon" if _hour < 17 else "Good evening")
        custom_greeting = f"{_greet}. I have your daily briefing ready. Let me walk you through what's important today."

        try:
            # Create video session via VideoSessionService
            session_response = await VideoSessionService.create_session(
                user_id=user_id,
                session_type=SessionType.BRIEFING,  # type: ignore
                context=briefing_script,
                custom_greeting=custom_greeting,
            )

            logger.info(
                "Video briefing session created",
                extra={
                    "user_id": user_id,
                    "session_id": session_response.id,
                    "briefing_date": date.today().isoformat(),
                },
            )

            return {
                "session_id": session_response.id,
                "room_url": session_response.room_url,
                "briefing_date": date.today().isoformat(),
            }

        except (TavusAPIError, TavusConnectionError) as e:
            logger.error(
                "Failed to create video briefing session",
                extra={"user_id": user_id, "error": str(e)},
            )
            return {
                "session_id": None,
                "room_url": None,
                "briefing_date": date.today().isoformat(),
                "error": str(e),
            }
        except Exception as e:
            logger.exception(
                "Unexpected error creating video briefing session",
                extra={"user_id": user_id},
            )
            return {
                "session_id": None,
                "room_url": None,
                "briefing_date": date.today().isoformat(),
                "error": str(e),
            }
