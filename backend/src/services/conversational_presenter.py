"""Conversational Presenter — transforms agent outputs into ARIA chat messages.

Converts raw agent execution results into (message, rich_content, suggestions)
tuples for delivery via ws_manager.send_aria_message(). Template-based for
per-agent results (zero LLM cost), small LLM call for goal completion summaries.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Agent type → conversational template config
_AGENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "hunter": {
        "rich_type": "lead_card",
        "extract": lambda r: {
            "count": len(r.get("leads", r.get("companies", []))),
            "top_name": _first_name(r.get("leads", r.get("companies", []))),
            "reason": _first_field(r.get("leads", r.get("companies", [])), "reason", "match_reason", "description"),
            "items": r.get("leads", r.get("companies", [])),
        },
        "template": "I found {count} companies matching your ICP. {top_detail}",
        "suggestions": ["Tell me more about the top lead", "Refine my ICP criteria", "Start outreach"],
    },
    "analyst": {
        "rich_type": "research_results",
        "extract": lambda r: {
            "target": r.get("target", r.get("company", r.get("topic", ""))),
            "headline": r.get("headline", r.get("summary", r.get("key_finding", ""))),
        },
        "template": "The research on {target} is ready. Key finding: {headline}",
        "suggestions": ["Dig deeper on this", "Show all findings", "Draft a summary email"],
    },
    "scribe": {
        "rich_type": "email_draft",
        "extract": lambda r: {
            "doc_type": r.get("doc_type", r.get("type", "email")),
            "recipient": r.get("recipient", r.get("to", "")),
        },
        "template": "I've drafted {doc_type_article} {doc_type} for {recipient}. Want to review?",
        "suggestions": ["Show me the draft", "Send it", "Revise the tone"],
    },
    "scout": {
        "rich_type": "signal_card",
        "extract": lambda r: {
            "count": len(r.get("signals", r.get("items", []))),
            "top_signal": _first_field(r.get("signals", r.get("items", [])), "title", "headline", "summary"),
            "items": r.get("signals", r.get("items", [])),
        },
        "template": "Picked up {count} market signals. Most notable: {top_signal}",
        "suggestions": ["Show all signals", "Set up alerts for this", "What does this mean for us?"],
    },
    "strategist": {
        "rich_type": "battle_card",
        "extract": lambda r: {
            "target": r.get("target", r.get("competitor", r.get("company", ""))),
            "key_insight": r.get("key_insight", r.get("summary", r.get("recommendation", ""))),
        },
        "template": "Here's the competitive picture for {target}. {key_insight}",
        "suggestions": ["Compare positioning", "Draft talking points", "What are their weaknesses?"],
    },
    "operator": {
        "rich_type": None,
        "extract": lambda r: {
            "action_summary": r.get("summary", r.get("action", r.get("message", "Task completed"))),
        },
        "template": "Done — {action_summary}.",
        "suggestions": ["What else needs doing?", "Show activity log"],
    },
}


def _first_name(items: list[dict[str, Any]] | Any) -> str:
    """Extract name from first item in a list."""
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if isinstance(first, dict):
        return first.get("name", first.get("company_name", first.get("title", "")))
    return str(first)


def _first_field(items: list[dict[str, Any]] | Any, *fields: str) -> str:
    """Extract first matching field from first item in a list."""
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if isinstance(first, dict):
        for field in fields:
            val = first.get(field)
            if val:
                return str(val)[:200]
    return ""


def _article(word: str) -> str:
    """Return 'an' for vowel-starting words, 'a' otherwise."""
    return "an" if word and word[0].lower() in "aeiou" else "a"


class ConversationalPresenter:
    """Transforms agent outputs into conversational ARIA messages with rich content."""

    def present_agent_result(
        self,
        user_id: str,
        agent_type: str,
        result: dict[str, Any],
        goal_title: str = "",
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Convert an agent result into (message, rich_content, suggestions).

        Zero LLM cost — uses templates only.

        Args:
            user_id: The user who will receive the message.
            agent_type: The agent type (hunter, analyst, etc.).
            result: The raw agent result dict.
            goal_title: Title of the parent goal.

        Returns:
            Tuple of (message_text, rich_content_list, suggestions_list).
        """
        if not result or not result.get("success", True):
            return "", [], []

        content = result.get("content", result)
        if isinstance(content, str):
            # Some agents return string content — wrap as generic
            return (
                f"{agent_type.title()} analysis complete: {content[:200]}",
                [],
                ["Tell me more", "What's next?"],
            )

        template_config = _AGENT_TEMPLATES.get(agent_type)
        if not template_config:
            return (
                f"{agent_type.title()} analysis complete.",
                [],
                ["Show me the results", "What's next?"],
            )

        try:
            extracted = template_config["extract"](content)
        except Exception:
            logger.debug("Failed to extract fields for %s", agent_type, exc_info=True)
            return (
                f"{agent_type.title()} analysis complete.",
                [],
                ["Show me the results", "What's next?"],
            )

        # Build message from template
        message = self._build_message(template_config["template"], extracted, agent_type)
        if not message:
            message = f"{agent_type.title()} analysis complete."

        # Build rich_content
        rich_content: list[dict[str, Any]] = []
        rich_type = template_config.get("rich_type")
        if rich_type:
            rich_content.append({
                "type": rich_type,
                "data": content,
            })

        suggestions = template_config.get("suggestions", ["Show me the results", "What's next?"])

        return message, rich_content, suggestions

    async def present_goal_completion(
        self,
        user_id: str,
        goal_id: str,
        goal_title: str,
        results: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Generate a conversational goal completion message.

        Uses a small LLM call (~150 tokens) for personality. Falls back to
        template if LLM call fails or budget is exceeded.

        Args:
            user_id: The user who will receive the message.
            goal_id: The completed goal's ID.
            goal_title: The goal title.
            results: List of agent result dicts.

        Returns:
            Tuple of (message_text, rich_content_list, suggestions_list).
        """
        success_count = sum(1 for r in results if r.get("success"))
        total = len(results)
        agent_summaries = self._extract_agent_summaries(results)

        # Try LLM for personality-infused summary
        message = await self._generate_completion_llm(
            user_id, goal_title, success_count, total, agent_summaries
        )

        # Build rich_content with per-agent summaries
        rich_content: list[dict[str, Any]] = []
        if agent_summaries:
            rich_content.append({
                "type": "goal_completion",
                "data": {
                    "goal_id": goal_id,
                    "goal_title": goal_title,
                    "success_count": success_count,
                    "total_agents": total,
                    "agent_results": agent_summaries,
                },
            })

        suggestions = [
            "Show me the full report",
            "What should I focus on next?",
            "Start a follow-up goal",
        ]

        return message, rich_content, suggestions

    def present_action_pending(
        self,
        action_data: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Convert a pending action into a conversational message.

        Args:
            action_data: Action details (action_id, title, agent, risk_level, etc.).

        Returns:
            Tuple of (message_text, rich_content_list, suggestions_list).
        """
        agent = action_data.get("agent", "").title()
        title = action_data.get("title", "an action")
        reasoning = action_data.get("reasoning", "")

        message = f"I'd like to {title.lower()}."
        if reasoning:
            message += f" {reasoning}"

        rich_content: list[dict[str, Any]] = [{
            "type": "action_approval",
            "data": {
                "action_id": action_data.get("action_id", ""),
                "title": title,
                "description": action_data.get("description", ""),
                "agent": agent,
                "risk_level": action_data.get("risk_level", "medium"),
                "reasoning": reasoning,
            },
        }]

        suggestions = ["Approve", "Tell me more", "Reject"]
        return message, rich_content, suggestions

    def present_integration_needed(
        self,
        integration_category: str,
        display_name: str,
        providers: list[str],
        benefit: str,
        route: str,
        agent_name: str,
        task_description: str = "",
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        """Convert an integration request into a conversational message with card.

        Args:
            integration_category: The integration key (calendar, crm, gmail, etc.).
            display_name: Human-readable name.
            providers: List of provider names.
            benefit: What connecting enables.
            route: Settings route to navigate to.
            agent_name: The agent requesting the integration.
            task_description: What the agent was trying to do.

        Returns:
            Tuple of (message_text, rich_content_list, suggestions_list).
        """
        rich_content: list[dict[str, Any]] = [{
            "type": "integration_request",
            "data": {
                "integration": integration_category,
                "display_name": display_name,
                "providers": providers,
                "benefit": benefit,
                "route": route,
                "agent": agent_name,
            },
        }]

        suggestions = [
            f"Connect {providers[0]}" if providers else "Connect now",
            "Skip this step",
            "Tell me more",
        ]

        # Message is already generated by IntegrationRequestService — return empty
        # to let the caller decide
        return "", rich_content, suggestions

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _build_message(
        self,
        template: str,
        extracted: dict[str, Any],
        agent_type: str,
    ) -> str:
        """Build message from template with extracted fields.

        Falls back gracefully when fields are missing.
        """
        try:
            # Handle special cases
            if agent_type == "hunter":
                count = extracted.get("count", 0)
                top_name = extracted.get("top_name", "")
                reason = extracted.get("reason", "")
                if count == 0:
                    return "I ran a lead search but didn't find strong matches. Want to adjust the criteria?"
                top_detail = ""
                if top_name and reason:
                    top_detail = f"{top_name} looks strong — {reason}."
                elif top_name:
                    top_detail = f"{top_name} looks like a strong match."
                return template.format(count=count, top_detail=top_detail).strip()

            if agent_type == "scribe":
                doc_type = extracted.get("doc_type", "email")
                recipient = extracted.get("recipient", "")
                if not recipient:
                    return f"I've drafted {_article(doc_type)} {doc_type}. Want to review?"
                return template.format(
                    doc_type_article=_article(doc_type),
                    doc_type=doc_type,
                    recipient=recipient,
                ).strip()

            if agent_type == "scout":
                count = extracted.get("count", 0)
                top_signal = extracted.get("top_signal", "")
                if count == 0:
                    return "No new market signals detected. I'll keep monitoring."
                if not top_signal:
                    return f"Picked up {count} market signals. Take a look."
                return template.format(count=count, top_signal=top_signal).strip()

            # Generic template formatting for analyst, strategist, operator
            return template.format(**extracted).strip()
        except (KeyError, IndexError):
            logger.debug("Template formatting failed for %s", agent_type, exc_info=True)
            return ""

    def _extract_agent_summaries(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract per-agent summaries from execution results."""
        summaries: list[dict[str, Any]] = []
        for r in results:
            agent_type = r.get("agent_type", r.get("agent", "unknown"))
            success = r.get("success", False)
            content = r.get("content", {})
            summary_text = ""

            if isinstance(content, str):
                summary_text = content[:200]
            elif isinstance(content, dict):
                summary_text = content.get("summary", content.get("headline", ""))
                if not summary_text:
                    # Try to build a short summary from known fields
                    if agent_type == "hunter":
                        count = len(content.get("leads", content.get("companies", [])))
                        summary_text = f"{count} leads found" if count else "No leads found"
                    elif agent_type == "scout":
                        count = len(content.get("signals", content.get("items", [])))
                        summary_text = f"{count} signals detected" if count else "No signals"
                    elif agent_type == "scribe":
                        summary_text = f"Draft for {content.get('recipient', 'review')}"

            summaries.append({
                "agent_type": agent_type,
                "success": success,
                "summary": summary_text or ("Completed" if success else "Failed"),
            })
        return summaries

    async def _generate_completion_llm(
        self,
        user_id: str,
        goal_title: str,
        success_count: int,
        total: int,
        agent_summaries: list[dict[str, Any]],
    ) -> str:
        """Generate personality-infused goal completion message via LLM.

        Budget-checked via CostGovernor. Falls back to template on failure.
        """
        # Build summary lines for the prompt
        summary_lines = []
        for s in agent_summaries:
            status = "completed" if s["success"] else "failed"
            summary_lines.append(f"- {s['agent_type'].title()}: {status} — {s['summary']}")
        summary_text = "\n".join(summary_lines) if summary_lines else "No details available."

        fallback = self._fallback_completion_message(goal_title, success_count, total, agent_summaries)

        try:
            from src.core.cost_governor import CostGovernor
            from src.core.llm import LLMClient
            from src.db.supabase import SupabaseClient

            governor = CostGovernor(SupabaseClient.get_client())
            budget = await governor.check_budget(user_id)
            if not budget.can_proceed:
                return fallback

            llm = LLMClient()
            prompt = (
                "You are ARIA, an AI Department Director. Write a 1-2 sentence "
                "conversational summary of a completed goal. Be direct and specific.\n\n"
                f"Goal: {goal_title}\n"
                f"Results: {success_count}/{total} agents succeeded\n"
                f"Agent results:\n{summary_text}\n\n"
                "Rules:\n"
                "- Reference specific results (numbers, names, findings)\n"
                "- Sound like a confident colleague reporting back\n"
                "- Do NOT use emojis or 'As an AI'\n"
                "- End with what they should look at first"
            )

            response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.7,
                user_id=None,
            )

            await governor.record_usage(user_id, getattr(response, "usage", None))
            result = response.strip() if isinstance(response, str) else str(response).strip()
            return result if result else fallback
        except Exception:
            logger.debug("LLM goal completion generation failed", exc_info=True)
            return fallback

    def _fallback_completion_message(
        self,
        goal_title: str,
        success_count: int,
        total: int,
        agent_summaries: list[dict[str, Any]],
    ) -> str:
        """Template-based fallback for goal completion message."""
        title = goal_title or "your goal"
        parts = [f'"{title}" is complete — {success_count} of {total} agents delivered.']

        # Add the most interesting result
        for s in agent_summaries:
            if s["success"] and s["summary"] and s["summary"] not in ("Completed", ""):
                parts.append(s["summary"] + ".")
                break

        return " ".join(parts)
