"""Return Greeting Service — generates personalized greetings when users return.

When a user opens ARIA after being away for more than 2 hours, this service
gathers what happened while they were away and generates a personalized
greeting via Claude API with rich content cards. The greeting is sent as
the first WebSocket message.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.persona import PersonaBuilder, PersonaRequest
from src.core.task_types import TaskType

logger = logging.getLogger(__name__)

# Minimum absence to trigger a return greeting (seconds)
MIN_ABSENCE_SECONDS = 7200  # 2 hours


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
    ) -> dict[str, Any] | None:
        """Generate a personalized greeting for a returning user.

        Queries what happened while the user was away and generates a
        conversational greeting via Claude API with rich content cards.

        Args:
            user_id: The returning user's ID.
            absence_seconds: How long the user was disconnected.

        Returns:
            Dict with message, rich_content, and suggestions, or None.
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

        # Build rich_content cards from gathered context
        rich_content = self._build_rich_content(context)

        # Build contextual suggestions based on what happened
        suggestions = self._build_suggestions(context)

        # Generate greeting via Claude API with full persona context
        greeting_text = await self._generate_greeting_llm(user_name, absence_seconds, context, user_id)

        return {
            "message": greeting_text,
            "rich_content": rich_content,
            "suggestions": suggestions,
        }

    async def _gather_away_context(
        self,
        db: Any,
        user_id: str,
        since_iso: str,
    ) -> dict[str, Any]:
        """Gather all background activity that happened while user was away.

        Fetches both counts and top items for rich content cards.

        Args:
            db: Supabase client.
            user_id: The user's ID.
            since_iso: ISO timestamp of when the user went offline.

        Returns:
            Dict with activity summaries, top items, and has_activity flag.
        """
        context: dict[str, Any] = {
            "has_activity": False,
            "completed_executions": [],
            "goal_progress": [],
            "pending_drafts": 0,
            "pending_actions": 0,
            "new_signals": 0,
            "briefing_ready": False,
            # Top items for rich content cards
            "top_execution": None,
            "top_draft": None,
            "top_signal": None,
        }

        # 1. Agent executions completed since absence (with full details for top result)
        try:
            exec_result = (
                db.table("agent_executions")
                .select("id, goal_agent_id, status, result_summary, result_data, completed_at")
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
                # Top execution for rich content card
                context["top_execution"] = execs[0]
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

        # 3. Pending email drafts ready for review (with top draft details)
        try:
            draft_result = (
                db.table("email_drafts")
                .select("id, subject, recipient_email, recipient_name, created_at")
                .eq("user_id", user_id)
                .eq("status", "ready")
                .gte("created_at", since_iso)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            drafts = draft_result.data or []
            if drafts:
                context["pending_drafts"] = len(drafts)
                context["has_activity"] = True
                context["top_draft"] = drafts[0]
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

        # 5. New market signals (with top signal details)
        try:
            signal_result = (
                db.table("market_signals")
                .select("id, title, signal_type, severity, source, created_at")
                .eq("user_id", user_id)
                .gte("created_at", since_iso)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            signals = signal_result.data or []
            if signals:
                context["new_signals"] = len(signals)
                context["has_activity"] = True
                context["top_signal"] = signals[0]
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

    def _build_rich_content(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Build rich_content cards from gathered context.

        Args:
            context: Activity context from _gather_away_context.

        Returns:
            List of rich_content card dicts.
        """
        cards: list[dict[str, Any]] = []

        # Top agent execution result card
        top_exec = context.get("top_execution")
        if top_exec:
            result_data = top_exec.get("result_data")
            if isinstance(result_data, dict):
                # Determine card type from agent type
                agent_id = top_exec.get("goal_agent_id", "")
                card_type = self._agent_to_card_type(agent_id)
                if card_type:
                    cards.append({
                        "type": card_type,
                        "data": result_data,
                    })

        # Top email draft card
        top_draft = context.get("top_draft")
        if top_draft:
            cards.append({
                "type": "email_draft",
                "data": {
                    "draft_id": top_draft.get("id", ""),
                    "subject": top_draft.get("subject", ""),
                    "recipient": top_draft.get("recipient_name", top_draft.get("recipient_email", "")),
                },
            })

        # Top signal card
        top_signal = context.get("top_signal")
        if top_signal:
            cards.append({
                "type": "signal_card",
                "data": {
                    "id": top_signal.get("id", ""),
                    "title": top_signal.get("title", ""),
                    "signal_type": top_signal.get("signal_type", ""),
                    "severity": top_signal.get("severity", ""),
                    "source": top_signal.get("source", ""),
                },
            })

        return cards

    def _build_suggestions(self, context: dict[str, Any]) -> list[str]:
        """Build contextual suggestion chips based on what happened.

        Args:
            context: Activity context from _gather_away_context.

        Returns:
            List of suggestion strings.
        """
        suggestions: list[str] = []

        if context.get("pending_drafts", 0) > 0:
            suggestions.append("Review my drafts")
        if context.get("pending_actions", 0) > 0:
            suggestions.append("Show pending actions")
        if context.get("new_signals", 0) > 0:
            suggestions.append("Show market signals")
        if context.get("briefing_ready"):
            suggestions.append("Play my briefing")
        if len(context.get("completed_executions", [])) > 0:
            suggestions.append("Show what you did")

        # Always include a fallback
        if not suggestions:
            suggestions = ["Show me updates", "What needs my attention?"]
        elif len(suggestions) < 3:
            suggestions.append("What should I focus on?")

        return suggestions[:4]  # Max 4 suggestions

    def _agent_to_card_type(self, agent_id: str) -> str | None:
        """Map agent type identifier to rich content card type.

        Args:
            agent_id: The agent identifier (may be a UUID or agent type name).

        Returns:
            Card type string or None.
        """
        # agent_id might be the agent type directly or a goal_agent row ID
        agent_lower = agent_id.lower() if agent_id else ""
        mapping = {
            "hunter": "lead_card",
            "analyst": "research_results",
            "scribe": "email_draft",
            "scout": "signal_card",
            "strategist": "battle_card",
        }
        for key, card_type in mapping.items():
            if key in agent_lower:
                return card_type
        return None

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
        user_id: str | None = None,
    ) -> str:
        """Generate personalized greeting via Claude API.

        Args:
            user_name: User's first name.
            absence_seconds: Duration of absence.
            context: Activity context from _gather_away_context.
            user_id: The user's ID for PersonaBuilder personalization.

        Returns:
            Generated greeting string.
        """
        hours_away = absence_seconds / 3600
        time_description = (
            f"{int(hours_away)} hours"
            if hours_away < 24
            else f"{int(hours_away / 24)} days"
        )

        # Build detailed activity summary for prompt
        activity_lines: list[str] = []
        exec_count = len(context.get("completed_executions", []))
        if exec_count > 0:
            # Include top execution detail
            top_exec = context.get("top_execution")
            summary = ""
            if top_exec:
                summary = top_exec.get("result_summary", "")
            if summary:
                activity_lines.append(f"- {exec_count} agent executions completed (latest: {summary})")
            else:
                activity_lines.append(f"- {exec_count} agent executions completed")

        progress_count = len(context.get("goal_progress", []))
        if progress_count > 0:
            activity_lines.append(f"- {progress_count} goal progress updates")

        drafts = context.get("pending_drafts", 0)
        if drafts > 0:
            top_draft = context.get("top_draft")
            if top_draft and top_draft.get("recipient_name"):
                activity_lines.append(
                    f"- {drafts} email draft(s) ready for review "
                    f"(first: to {top_draft['recipient_name']})"
                )
            else:
                activity_lines.append(f"- {drafts} email draft(s) ready for review")

        actions = context.get("pending_actions", 0)
        if actions > 0:
            activity_lines.append(f"- {actions} action(s) pending your approval")

        signals = context.get("new_signals", 0)
        if signals > 0:
            top_signal = context.get("top_signal")
            if top_signal and top_signal.get("title"):
                activity_lines.append(
                    f"- {signals} new market signal(s) (top: {top_signal['title']})"
                )
            else:
                activity_lines.append(f"- {signals} new market signal(s) detected")

        if context.get("briefing_ready"):
            activity_lines.append("- Your daily briefing is ready")

        activity_summary = "\n".join(activity_lines) if activity_lines else "Nothing notable."

        task_prompt = (
            f"User name: {user_name or 'there'}\n"
            f"Time away: {time_description}\n"
            f"Current hour: {datetime.now(UTC).hour} UTC\n\n"
            f"What happened while they were away:\n{activity_summary}\n\n"
            "Rules:\n"
            "- 2-4 sentences max\n"
            "- Reference specific numbers and details from the activity\n"
            "- Use appropriate time-of-day greeting (morning/afternoon/evening)\n"
            "- If there are pending actions or drafts, mention them\n"
            "- Do NOT use emojis\n"
            "- Do NOT say 'As an AI' or 'While you were away:'\n"
            "- Sound like a confident colleague, not a notification system\n"
            "- End with what you'd suggest they look at first"
        )

        try:
            llm = self._get_llm()

            # Build full persona context for user-facing greeting
            system_prompt = None
            try:
                if user_id:
                    builder = PersonaBuilder()
                    persona_ctx = await builder.build(
                        PersonaRequest(
                            user_id=user_id,
                            agent_name="return_greeting",
                            agent_role_description="Generates personalized return greetings",
                            task_description="Greeting a returning user with a summary of what happened while away",
                        )
                    )
                    system_prompt = persona_ctx.to_system_prompt()
            except Exception as e:
                logger.warning("PersonaBuilder failed for return greeting, using fallback: %s", e)

            # Fallback to minimal persona if PersonaBuilder fails
            if not system_prompt:
                from src.core.persona import (
                    LAYER_1_CORE_IDENTITY,
                    LAYER_2_PERSONALITY_TRAITS,
                    LAYER_3_ANTI_PATTERNS,
                )
                system_prompt = "\n\n".join([
                    LAYER_1_CORE_IDENTITY,
                    LAYER_2_PERSONALITY_TRAITS,
                    LAYER_3_ANTI_PATTERNS,
                ])

            greeting = await llm.generate_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                max_tokens=256,
                temperature=0.7,
                user_id=None,  # Don't track this small call against user budget
                task=TaskType.CHAT_RESPONSE,
                agent_id="return_greeting",
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
