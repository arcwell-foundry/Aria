"""Return Greeting Service — generates personalized greetings when users return.

When a user opens ARIA after being away for more than 1 hour, this service
gathers what happened while they were away and generates a personalized
greeting via Claude API. The greeting is sent as the first WebSocket message.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Minimum absence to trigger a return greeting (seconds)
MIN_ABSENCE_SECONDS = 3600  # 1 hour


class ReturnGreetingService:
    """Generates personalized return greetings based on background activity."""

    def __init__(self) -> None:
        self._db: Any = None
        self._llm: Any = None

    def _get_db(self) -> Any:
        if self._db is None:
            from src.db.supabase import SupabaseClient

            self._db = SupabaseClient.get_client()
        return self._db

    def _get_llm(self) -> Any:
        if self._llm is None:
            from src.core.llm import LLMClient

            self._llm = LLMClient()
        return self._llm

    async def generate_return_greeting(
        self,
        user_id: str,
        absence_seconds: float,
    ) -> str | None:
        """Generate a personalized greeting for a returning user.

        Queries what happened while the user was away and generates a
        conversational greeting via Claude API.

        Args:
            user_id: The returning user's ID.
            absence_seconds: How long the user was disconnected.

        Returns:
            Greeting message string, or None if nothing notable happened.
        """
        if absence_seconds < MIN_ABSENCE_SECONDS:
            return None

        db = self._get_db()
        since = datetime.now(UTC) - timedelta(seconds=absence_seconds)
        since_iso = since.isoformat()

        # Gather what happened while away — all queries are per-user
        context = await self._gather_away_context(db, user_id, since_iso)

        if not context["has_activity"]:
            return None

        # Get user name for greeting
        user_name = await self._get_user_name(db, user_id)

        # Generate greeting via Claude API
        greeting = await self._generate_greeting_llm(user_name, absence_seconds, context)
        return greeting

    async def _gather_away_context(
        self,
        db: Any,
        user_id: str,
        since_iso: str,
    ) -> dict[str, Any]:
        """Gather all background activity that happened while user was away.

        Args:
            db: Supabase client.
            user_id: The user's ID.
            since_iso: ISO timestamp of when the user went offline.

        Returns:
            Dict with activity summaries and has_activity flag.
        """
        context: dict[str, Any] = {
            "has_activity": False,
            "completed_executions": [],
            "goal_progress": [],
            "pending_drafts": 0,
            "pending_actions": 0,
            "new_signals": 0,
            "briefing_ready": False,
        }

        # 1. Agent executions completed since absence
        try:
            exec_result = (
                db.table("agent_executions")
                .select("id, goal_agent_id, status, result_summary, completed_at")
                .eq("user_id", user_id)
                .eq("status", "completed")
                .gte("completed_at", since_iso)
                .order("completed_at", desc=True)
                .limit(10)
                .execute()
            )
            execs = exec_result.data or []
            if execs:
                context["completed_executions"] = execs
                context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query agent_executions for return greeting", exc_info=True)

        # 2. Goal progress changes
        try:
            goal_result = (
                db.table("goal_updates")
                .select("goal_id, update_type, content, progress_delta, created_at")
                .eq("created_by", "aria")
                .gte("created_at", since_iso)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            # Filter to this user's goals
            updates = goal_result.data or []
            if updates:
                # Get this user's goal IDs to filter
                user_goals_result = (
                    db.table("goals")
                    .select("id")
                    .eq("user_id", user_id)
                    .execute()
                )
                user_goal_ids = {g["id"] for g in (user_goals_result.data or [])}
                user_updates = [u for u in updates if u.get("goal_id") in user_goal_ids]
                if user_updates:
                    context["goal_progress"] = user_updates
                    context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query goal_updates for return greeting", exc_info=True)

        # 3. Pending email drafts ready for review
        try:
            draft_result = (
                db.table("email_drafts")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("status", "ready")
                .gte("created_at", since_iso)
                .execute()
            )
            draft_count = draft_result.count or 0
            if draft_count > 0:
                context["pending_drafts"] = draft_count
                context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query email_drafts for return greeting", exc_info=True)

        # 4. Pending approval actions
        try:
            action_result = (
                db.table("aria_action_queue")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )
            action_count = action_result.count or 0
            if action_count > 0:
                context["pending_actions"] = action_count
                context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query action_queue for return greeting", exc_info=True)

        # 5. New market signals
        try:
            signal_result = (
                db.table("market_signals")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .gte("created_at", since_iso)
                .execute()
            )
            signal_count = signal_result.count or 0
            if signal_count > 0:
                context["new_signals"] = signal_count
                context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query market_signals for return greeting", exc_info=True)

        # 6. Daily briefing generated
        try:
            briefing_result = (
                db.table("daily_briefings")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", since_iso)
                .limit(1)
                .execute()
            )
            if briefing_result.data:
                context["briefing_ready"] = True
                context["has_activity"] = True
        except Exception:
            logger.debug("Failed to query daily_briefings for return greeting", exc_info=True)

        return context

    async def _get_user_name(self, db: Any, user_id: str) -> str:
        """Get user's first name for greeting.

        Args:
            db: Supabase client.
            user_id: The user's ID.

        Returns:
            User's first name or empty string.
        """
        try:
            result = (
                db.table("user_profiles")
                .select("full_name")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                full_name = result.data.get("full_name", "")
                return full_name.split()[0] if full_name else ""
        except Exception:
            logger.debug("Failed to get user name for greeting", exc_info=True)
        return ""

    async def _generate_greeting_llm(
        self,
        user_name: str,
        absence_seconds: float,
        context: dict[str, Any],
    ) -> str:
        """Generate personalized greeting via Claude API.

        Args:
            user_name: User's first name.
            absence_seconds: Duration of absence.
            context: Activity context from _gather_away_context.

        Returns:
            Generated greeting string.
        """
        hours_away = absence_seconds / 3600
        time_description = (
            f"{int(hours_away)} hours"
            if hours_away < 24
            else f"{int(hours_away / 24)} days"
        )

        # Build activity summary for prompt
        activity_lines: list[str] = []
        exec_count = len(context.get("completed_executions", []))
        if exec_count > 0:
            activity_lines.append(f"- {exec_count} agent executions completed")

        progress_count = len(context.get("goal_progress", []))
        if progress_count > 0:
            activity_lines.append(f"- {progress_count} goal progress updates")

        drafts = context.get("pending_drafts", 0)
        if drafts > 0:
            activity_lines.append(f"- {drafts} email draft(s) ready for review")

        actions = context.get("pending_actions", 0)
        if actions > 0:
            activity_lines.append(f"- {actions} action(s) pending your approval")

        signals = context.get("new_signals", 0)
        if signals > 0:
            activity_lines.append(f"- {signals} new market signal(s) detected")

        if context.get("briefing_ready"):
            activity_lines.append("- Your daily briefing is ready")

        activity_summary = "\n".join(activity_lines) if activity_lines else "Nothing notable."

        prompt = (
            "You are ARIA, an AI Department Director. Generate a brief, warm return "
            "greeting for your user who just came back online. Be direct and "
            "conversational — like a colleague updating them.\n\n"
            f"User name: {user_name or 'there'}\n"
            f"Time away: {time_description}\n"
            f"Current hour: {datetime.now(UTC).hour} UTC\n\n"
            f"What happened while they were away:\n{activity_summary}\n\n"
            "Rules:\n"
            "- 2-4 sentences max\n"
            "- Reference specific numbers from the activity\n"
            "- Use appropriate time-of-day greeting (morning/afternoon/evening)\n"
            "- If there are pending actions or drafts, mention them\n"
            "- Do NOT use emojis\n"
            "- Do NOT say 'As an AI' or 'While you were away:'\n"
            "- Sound like a confident colleague, not a notification system\n"
            "- End with what you'd suggest they look at first"
        )

        try:
            llm = self._get_llm()
            greeting = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.7,
                user_id=None,  # Don't track this small call against user budget
            )
            return greeting.strip()
        except Exception as e:
            logger.warning("Failed to generate return greeting via LLM: %s", e)
            # Fallback to a simple templated greeting
            return self._fallback_greeting(user_name, context)

    def _fallback_greeting(self, user_name: str, context: dict[str, Any]) -> str:
        """Generate a simple fallback greeting without LLM.

        Args:
            user_name: User's first name.
            context: Activity context.

        Returns:
            Templated greeting string.
        """
        name = user_name or "there"
        parts = [f"Welcome back, {name}."]

        exec_count = len(context.get("completed_executions", []))
        if exec_count > 0:
            parts.append(f"{exec_count} agent tasks completed while you were away.")

        drafts = context.get("pending_drafts", 0)
        if drafts > 0:
            parts.append(f"{drafts} email draft{'s' if drafts != 1 else ''} ready for your review.")

        actions = context.get("pending_actions", 0)
        if actions > 0:
            parts.append(f"{actions} action{'s' if actions != 1 else ''} pending your approval.")

        return " ".join(parts)
