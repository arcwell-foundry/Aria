"""Video tool executor for Tavus CVI tool calls.

Routes tool calls from Tavus video conversations to the appropriate ARIA
agent or service, executes them, and returns results formatted for spoken
delivery (natural language, not raw JSON).

Flow:
1. Frontend receives ``conversation.tool_call`` event from Daily
2. Frontend calls ``POST /video/tools/execute`` with tool name + args
3. This executor routes to the right agent/service
4. Result is formatted as natural spoken text
5. Frontend echoes result back via ``conversation.echo``
"""

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.task_types import TaskType
from src.integrations.tavus_tools import TOOL_AGENT_MAP, VALID_TOOL_NAMES

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a video tool execution."""

    spoken_text: str
    rich_content: dict[str, Any] | None = None


class VideoToolExecutor:
    """Executes ARIA tool calls triggered during Tavus video conversations.

    Each public method corresponds to one of the 12 video tools and routes
    to the appropriate agent or service.  Results are always returned as
    a human-readable string suitable for the avatar to speak aloud.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._llm: Any = None
        self._db: Any = None

    # ------------------------------------------------------------------
    # Lazy initialisers
    # ------------------------------------------------------------------

    @property
    def llm(self) -> Any:
        if self._llm is None:
            from src.core.llm import LLMClient

            self._llm = LLMClient()
        return self._llm

    @property
    def db(self) -> Any:
        if self._db is None:
            from src.db.supabase import SupabaseClient

            self._db = SupabaseClient.get_client()
        return self._db

    # ------------------------------------------------------------------
    # Persona preamble helper
    # ------------------------------------------------------------------

    async def _get_persona_preamble(self) -> str:
        """Get a lightweight persona preamble for LLM-generated spoken responses.

        Uses only LAYER 1 + LAYER 2 (core identity + personality traits)
        to ensure ARIA sounds like herself when generating spoken text.

        Returns:
            Persona preamble string, or empty string on failure.
        """
        try:
            from src.core.persona import (
                LAYER_1_CORE_IDENTITY,
                LAYER_2_PERSONALITY_TRAITS,
            )

            return f"{LAYER_1_CORE_IDENTITY}\n\n{LAYER_2_PERSONALITY_TRAITS}"
        except Exception as e:
            logger.debug(
                "Failed to get persona preamble for video tool: %s", e
            )
            return ""

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a video tool call and return a spoken-ready result.

        Args:
            tool_name: One of the 12 registered tool names.
            arguments: Parameters parsed from the tool call.

        Returns:
            ToolResult with spoken text and optional rich content for overlays.
        """
        if tool_name not in VALID_TOOL_NAMES:
            return ToolResult(
                spoken_text=f"I don't have a tool called {tool_name}. Let me help you another way."
            )

        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            return ToolResult(
                spoken_text="That capability isn't available right now."
            )

        try:
            result = await handler(arguments)
            await self._log_activity(tool_name, arguments, success=True)
            await self._store_episodic(tool_name, arguments, result)
            return result
        except Exception:
            logger.exception(
                "Video tool execution failed",
                extra={
                    "tool_name": tool_name,
                    "user_id": self._user_id,
                },
            )
            await self._log_activity(tool_name, arguments, success=False)
            return ToolResult(
                spoken_text=(
                    f"I ran into an issue executing {tool_name.replace('_', ' ')}. "
                    "Let me try a different approach."
                )
            )

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _handle_search_companies(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import HunterAgent

        agent = HunterAgent(llm_client=self.llm, user_id=self._user_id)
        results = await agent._call_tool(
            "search_companies",
            query=args["query"],
            limit=5,
        )

        if not results:
            return ToolResult(
                spoken_text=f"I searched for companies matching '{args['query']}' but didn't find any results. Want me to broaden the search?"
            )

        companies = results if isinstance(results, list) else results.get("companies", [])
        if not companies:
            return ToolResult(
                spoken_text=f"No companies found matching '{args['query']}'. Would you like me to try different criteria?"
            )

        lines = [f"I found {len(companies)} companies matching your search."]
        for i, company in enumerate(companies[:5], 1):
            name = company.get("name") or company.get("company_name", "Unknown")
            description = company.get("description", "")
            snippet = description[:80] + "..." if len(description) > 80 else description
            lines.append(f"{i}. {name}" + (f" — {snippet}" if snippet else ""))

        lines.append("Would you like me to dig deeper into any of these, or add them to your pipeline?")
        spoken_text = " ".join(lines)

        # Build rich_content from the first result
        first = companies[0]
        rich_content: dict[str, Any] = {
            "type": "lead_card",
            "data": {
                "company_name": first.get("name") or first.get("company_name", "Unknown"),
                "contacts": first.get("contacts", []),
                "fit_score": first.get("fit_score"),
                "signals": first.get("signals", []),
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_search_leads(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import HunterAgent

        agent = HunterAgent(llm_client=self.llm, user_id=self._user_id)
        results = await agent._call_tool(
            "search_companies",
            query=args["icp_criteria"],
            limit=5,
        )

        if not results:
            return ToolResult(
                spoken_text="I couldn't find leads matching that profile right now. Can you refine the criteria?"
            )

        leads = results if isinstance(results, list) else results.get("companies", [])
        if not leads:
            return ToolResult(
                spoken_text="No leads matched your ICP criteria. Would you like to adjust the search?"
            )

        lines = [f"I found {len(leads)} potential leads matching your ideal customer profile."]
        for i, lead in enumerate(leads[:5], 1):
            name = lead.get("name") or lead.get("company_name", "Unknown")
            fit = lead.get("fit_score")
            fit_str = f" with a {fit}% fit score" if fit else ""
            lines.append(f"{i}. {name}{fit_str}")

        lines.append("Want me to add any of these to your pipeline?")
        spoken_text = " ".join(lines)

        # Build rich_content from the first result
        first = leads[0]
        rich_content: dict[str, Any] = {
            "type": "lead_card",
            "data": {
                "company_name": first.get("name") or first.get("company_name", "Unknown"),
                "contacts": first.get("contacts", []),
                "fit_score": first.get("fit_score"),
                "signals": first.get("signals", []),
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_get_lead_details(self, args: dict[str, Any]) -> ToolResult:
        company_name = args["company_name"]

        result = (
            self.db.table("lead_memories")
            .select("company_name, health_score, lifecycle_stage, last_activity_at, status, website, metadata")
            .eq("user_id", self._user_id)
            .ilike("company_name", f"%{company_name}%")
            .limit(1)
            .execute()
        )

        if not result.data:
            return ToolResult(
                spoken_text=f"I don't have {company_name} in your pipeline. Would you like me to research them and add them?"
            )

        lead = result.data[0]
        name = lead.get("company_name", company_name)
        score = lead.get("health_score", 0)
        stage = lead.get("lifecycle_stage", "unknown")
        status = lead.get("status", "unknown")
        last_activity = lead.get("last_activity_at", "")

        parts = [f"Here's what I have on {name}."]
        parts.append(f"They're currently in the {stage} stage with a health score of {score} out of 100.")
        parts.append(f"Status is {status}.")
        if last_activity:
            parts.append(f"Last activity was on {last_activity[:10]}.")

        spoken_text = " ".join(parts)

        rich_content: dict[str, Any] = {
            "type": "lead_card",
            "data": {
                "company_name": name,
                "fit_score": score,
                "signals": [stage, status],
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_get_battle_card(self, args: dict[str, Any]) -> ToolResult:
        competitor_name = args["competitor_name"]

        result = (
            self.db.table("battle_cards")
            .select("*")
            .eq("user_id", self._user_id)
            .ilike("competitor_name", f"%{competitor_name}%")
            .limit(1)
            .execute()
        )

        if result.data:
            card = result.data[0]
            return self._format_battle_card(card, competitor_name)

        # No card in DB — generate one via Strategist
        try:
            from src.agents import StrategistAgent

            agent = StrategistAgent(llm_client=self.llm, user_id=self._user_id)
            analysis = await agent._call_tool(
                "analyze_account",
                goal={"title": f"Competitive analysis of {competitor_name}", "type": "research"},
                context={"target_company": competitor_name},
            )

            if not analysis:
                return ToolResult(
                    spoken_text=(
                        f"I don't have a battle card for {competitor_name} yet "
                        "and couldn't generate one right now. Would you like me to try again?"
                    )
                )

            # Extract competitive data
            comp_analysis = analysis.get("competitive_analysis", {})
            competitors = comp_analysis.get("competitors", [])
            target: dict[str, Any] = next(
                (c for c in competitors if competitor_name.lower() in c.get("name", "").lower()),
                {},
            )

            strengths = target.get("strengths", analysis.get("challenges", []))
            weaknesses = target.get("weaknesses", analysis.get("opportunities", []))
            recommendation = analysis.get("recommendation", "")

            # Cache the generated card in DB (best-effort)
            try:
                self.db.table("battle_cards").insert({
                    "user_id": self._user_id,
                    "competitor_name": competitor_name,
                    "strengths": json.dumps(strengths),
                    "weaknesses": json.dumps(weaknesses),
                    "overview": recommendation,
                    "update_source": "strategist_agent",
                }).execute()
            except Exception:
                logger.debug("Failed to cache generated battle card", exc_info=True)

            # Build response
            card = {
                "competitor_name": competitor_name,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "win_strategy": recommendation,
                "our_differentiators": analysis.get("opportunities", []),
            }
            return self._format_battle_card(card, competitor_name)

        except Exception:
            logger.debug("Strategist battle card generation failed", exc_info=True)
            return ToolResult(
                spoken_text=(
                    f"I don't have a battle card for {competitor_name} yet. "
                    "Would you like me to create one?"
                )
            )

    def _format_battle_card(self, card: dict[str, Any], competitor_name: str) -> ToolResult:
        """Format a battle card dict into a ToolResult with spoken text and rich content."""
        name = card.get("competitor_name", competitor_name)
        parts = [f"Here's the battle card for {name}."]

        strengths = card.get("strengths")
        if strengths:
            if isinstance(strengths, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    strengths = json.loads(strengths)
            s = strengths if isinstance(strengths, str) else ", ".join(str(x) for x in strengths[:3])
            parts.append(f"Their key strengths are: {s}.")

        weaknesses = card.get("weaknesses")
        if weaknesses:
            if isinstance(weaknesses, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    weaknesses = json.loads(weaknesses)
            w = weaknesses if isinstance(weaknesses, str) else ", ".join(str(x) for x in weaknesses[:3])
            parts.append(f"Their weaknesses include: {w}.")

        differentiators = card.get("our_differentiators") or card.get("differentiators")
        if differentiators:
            d = differentiators if isinstance(differentiators, str) else ", ".join(str(x) for x in differentiators[:3])
            parts.append(f"Our key differentiators: {d}.")

        win_strategy = card.get("win_strategy") or card.get("overview")
        if win_strategy:
            parts.append(f"Recommended win strategy: {str(win_strategy)[:150]}.")

        spoken_text = " ".join(parts)

        rows: list[dict[str, str]] = []
        if strengths and not isinstance(strengths, str):
            for s_item in strengths[:3]:
                rows.append({"dimension": "Strength", "competitor": str(s_item), "us": ""})
        if weaknesses and not isinstance(weaknesses, str):
            for w_item in weaknesses[:3]:
                rows.append({"dimension": "Weakness", "competitor": str(w_item), "us": ""})
        if differentiators and not isinstance(differentiators, str):
            for d_item in differentiators[:3]:
                rows.append({"dimension": "Differentiator", "competitor": "", "us": str(d_item)})
        if win_strategy:
            rows.append({"dimension": "Win Strategy", "competitor": "", "us": str(win_strategy)[:150]})

        rich_content: dict[str, Any] = {
            "type": "battle_card",
            "data": {
                "competitor_name": name,
                "our_company": "Your Team",
                "rows": rows,
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_search_pubmed(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import AnalystAgent

        agent = AnalystAgent(llm_client=self.llm, user_id=self._user_id)
        max_results = min(args.get("max_results", 5), 10)

        results = await agent._call_tool(
            "pubmed_search",
            query=args["query"],
            max_results=max_results,
        )

        count = results.get("count", 0) if isinstance(results, dict) else 0
        pmids = results.get("pmids", []) if isinstance(results, dict) else []

        if count == 0:
            return ToolResult(
                spoken_text=f"I didn't find any PubMed articles for '{args['query']}'. Try broadening your search terms."
            )

        # Fetch article details for the PMIDs
        try:
            details = await agent._call_tool(
                "pubmed_fetch_details",
                pmids=pmids[:5],
            )
            articles = details.get("articles", []) if isinstance(details, dict) else []
        except Exception:
            articles = []

        parts = [f"I found {count} articles on PubMed for '{args['query']}'."]

        if articles:
            parts.append("Here are the top results:")
            for i, article in enumerate(articles[:3], 1):
                title = article.get("title", "Untitled")
                year = article.get("year", "")
                journal = article.get("journal", "")
                parts.append(f"{i}. {title[:100]}" + (f", published in {journal} {year}" if journal else ""))
        else:
            parts.append(f"I found {len(pmids)} article IDs but couldn't fetch the details right now.")

        spoken_text = " ".join(parts)

        # Build rich_content only if we fetched article details
        rich_content: dict[str, Any] | None = None
        if articles:
            rich_results: list[dict[str, Any]] = []
            for article in articles[:5]:
                pmid = article.get("pmid", "")
                rich_results.append({
                    "title": article.get("title", "Untitled"),
                    "authors": article.get("authors", ""),
                    "date": article.get("year", ""),
                    "excerpt": article.get("abstract", "")[:200] if article.get("abstract") else "",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                    "source": "PubMed",
                })
            rich_content = {
                "type": "research_results",
                "data": {
                    "query": args["query"],
                    "total_count": count,
                    "results": rich_results,
                },
            }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_search_clinical_trials(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import AnalystAgent

        agent = AnalystAgent(llm_client=self.llm, user_id=self._user_id)

        # Build query from structured fields
        query_parts = []
        if args.get("condition"):
            query_parts.append(args["condition"])
        if args.get("intervention"):
            query_parts.append(args["intervention"])
        if args.get("sponsor"):
            query_parts.append(args["sponsor"])
        query = " ".join(query_parts) if query_parts else "clinical trial"

        results = await agent._call_tool(
            "clinical_trials_search",
            query=query,
            max_results=5,
        )

        total = results.get("total_count", 0) if isinstance(results, dict) else 0
        studies = results.get("studies", []) if isinstance(results, dict) else []

        if total == 0:
            return ToolResult(
                spoken_text=f"No clinical trials found for {query}. Want me to try different search terms?"
            )

        parts = [f"I found {total} clinical trials related to {query}."]
        for i, study in enumerate(studies[:3], 1):
            title = study.get("title", study.get("brief_title", "Untitled"))
            phase = study.get("phase", "")
            status = study.get("status", study.get("overall_status", ""))
            sponsor = study.get("sponsor", study.get("lead_sponsor", ""))
            desc = title[:80]
            if phase:
                desc += f", Phase {phase}"
            if status:
                desc += f", {status}"
            if sponsor:
                desc += f", sponsored by {sponsor}"
            parts.append(f"{i}. {desc}")

        spoken_text = " ".join(parts)

        # Build rich_content only if studies were found
        rich_results: list[dict[str, Any]] = []
        for study in studies[:5]:
            nct_id = study.get("nct_id", "")
            phase = study.get("phase", "")
            status = study.get("status", study.get("overall_status", ""))
            excerpt_parts = []
            if phase:
                excerpt_parts.append(f"Phase {phase}")
            if status:
                excerpt_parts.append(status)

            rich_results.append({
                "title": study.get("title", study.get("brief_title", "Untitled")),
                "authors": study.get("sponsor", study.get("lead_sponsor", "")),
                "date": study.get("start_date", ""),
                "excerpt": " - ".join(excerpt_parts),
                "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
                "source": "ClinicalTrials.gov",
            })

        rich_content: dict[str, Any] = {
            "type": "research_results",
            "data": {
                "query": query,
                "total_count": total,
                "results": rich_results,
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_get_pipeline_summary(self, _args: dict[str, Any]) -> ToolResult:
        result = (
            self.db.table("lead_memories")
            .select("lifecycle_stage, health_score, status")
            .eq("user_id", self._user_id)
            .eq("status", "active")
            .execute()
        )

        if not result.data:
            return ToolResult(
                spoken_text="Your pipeline is empty right now. Would you like me to find some leads to get started?"
            )

        leads = result.data
        total = len(leads)

        # Count by stage
        stages: dict[str, int] = {}
        health_sum = 0
        for lead in leads:
            stage = lead.get("lifecycle_stage", "unknown")
            stages[stage] = stages.get(stage, 0) + 1
            health_sum += lead.get("health_score", 0)

        avg_health = round(health_sum / total) if total > 0 else 0

        parts = [f"Here's your pipeline summary. You have {total} active leads."]

        stage_order = ["prospect", "qualified", "proposal", "negotiation", "won"]
        for stage in stage_order:
            count = stages.get(stage, 0)
            if count > 0:
                parts.append(f"{count} in {stage}.")

        # Report any stages not in the standard order
        for stage, count in stages.items():
            if stage not in stage_order and count > 0:
                parts.append(f"{count} in {stage}.")

        parts.append(f"Average health score is {avg_health} out of 100.")

        hot = sum(1 for lead in leads if lead.get("health_score", 0) >= 70)
        if hot > 0:
            parts.append(f"{hot} leads are hot with a health score above 70.")

        spoken_text = " ".join(parts)

        # Build stages array for the chart (include all stages with counts)
        stages_list: list[dict[str, Any]] = []
        for stage in stage_order:
            count = stages.get(stage, 0)
            if count > 0:
                stages_list.append({"stage": stage, "count": count})
        for stage, count in stages.items():
            if stage not in stage_order and count > 0:
                stages_list.append({"stage": stage, "count": count})

        rich_content: dict[str, Any] = {
            "type": "pipeline_chart",
            "data": {
                "stages": stages_list,
                "total": total,
                "avg_health": avg_health,
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_get_meeting_brief(self, args: dict[str, Any]) -> ToolResult:
        meeting_id = args.get("meeting_id")

        if meeting_id:
            result = (
                self.db.table("meeting_briefs")
                .select("*")
                .eq("user_id", self._user_id)
                .eq("calendar_event_id", meeting_id)
                .limit(1)
                .execute()
            )
        else:
            # Get the next upcoming meeting brief
            now = datetime.now(UTC).isoformat()
            result = (
                self.db.table("meeting_briefs")
                .select("*")
                .eq("user_id", self._user_id)
                .gte("meeting_time", now)
                .order("meeting_time")
                .limit(1)
                .execute()
            )

        if not result.data:
            return ToolResult(
                spoken_text="I don't have a meeting brief ready. Would you like me to generate one for your next meeting?"
            )

        brief = result.data[0]
        title = brief.get("meeting_title", "your meeting")
        meeting_time = brief.get("meeting_time", "")
        attendees = brief.get("attendees", [])
        content = brief.get("brief_content", {})

        parts = [f"Here's the brief for {title}."]

        if meeting_time:
            parts.append(f"It's scheduled for {meeting_time[:16].replace('T', ' at ')}.")

        if attendees:
            names = attendees if isinstance(attendees, list) else [attendees]
            parts.append(f"Attendees: {', '.join(names[:4])}.")

        if isinstance(content, dict):
            summary = content.get("summary") or content.get("key_points")
            if summary:
                text = summary if isinstance(summary, str) else ". ".join(summary[:3])
                parts.append(text[:200])

            talking_points = content.get("talking_points", [])
            if talking_points:
                points = talking_points if isinstance(talking_points, list) else [talking_points]
                parts.append(f"Key talking points: {', '.join(str(p) for p in points[:3])}.")

        return ToolResult(spoken_text=" ".join(parts))

    async def _handle_draft_email(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import ScribeAgent
        from src.memory.digital_twin import DigitalTwin

        # Inject PersonaBuilder for Digital Twin style matching
        persona_builder = None
        try:
            from src.core.persona import get_persona_builder

            persona_builder = get_persona_builder()
        except Exception:
            pass

        agent = ScribeAgent(
            llm_client=self.llm,
            user_id=self._user_id,
            persona_builder=persona_builder,
        )

        recipient = {"name": args["to"]}
        if "@" in args["to"]:
            recipient = {"email": args["to"]}

        tone = args.get("tone", "formal")

        # Load Digital Twin writing style
        style: dict[str, Any] = {}
        try:
            dt = DigitalTwin()
            fingerprint = await dt.get_fingerprint(self._user_id)
            if fingerprint:
                style = {
                    "preferred_greeting": fingerprint.greeting_style,
                    "signature": fingerprint.sign_off_style,
                    "formality": "formal" if fingerprint.formality_score > 0.6 else "casual",
                }
            # Check recipient-specific profile
            if "@" in args["to"]:
                rp = (
                    self.db.table("recipient_writing_profiles")
                    .select("greeting_style, signoff_style, formality_level, tone")
                    .eq("user_id", self._user_id)
                    .eq("recipient_email", args["to"])
                    .limit(1)
                    .execute()
                )
                if rp.data:
                    profile = rp.data[0]
                    if profile.get("greeting_style"):
                        style["preferred_greeting"] = profile["greeting_style"]
                    if profile.get("signoff_style"):
                        style["signature"] = profile["signoff_style"]
                    if profile.get("formality_level") is not None:
                        style["formality"] = (
                            "formal" if profile["formality_level"] > 0.6 else "casual"
                        )
                    if profile.get("tone"):
                        tone = profile["tone"]
        except Exception:
            logger.debug("Failed to load digital twin style", exc_info=True)

        result = await agent._call_tool(
            "draft_email",
            recipient=recipient,
            context=args["subject_context"],
            goal=args["subject_context"],
            tone=tone,
            style=style,
        )

        if not result:
            return ToolResult(
                spoken_text="I wasn't able to draft that email. Can you give me more context?"
            )

        subject = result.get("subject", "")
        body = result.get("body", "")
        draft_id = result.get("draft_id", "")
        word_count = result.get("word_count", 0)

        parts = [f"I've drafted an email to {args['to']}."]
        if subject:
            parts.append(f"Subject line: {subject}.")
        if word_count:
            parts.append(f"It's {word_count} words.")
        parts.append(
            "The draft is saved and ready for your review. "
            "Would you like me to read it, adjust the tone, or send it?"
        )

        spoken_text = " ".join(parts)

        rich_content: dict[str, Any] = {
            "type": "email_draft",
            "data": {
                "to": args["to"],
                "subject": subject,
                "body": body,
                "draft_id": draft_id,
                "tone": tone,
            },
        }

        return ToolResult(spoken_text=spoken_text, rich_content=rich_content)

    async def _handle_schedule_meeting(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import OperatorAgent

        agent = OperatorAgent(llm_client=self.llm, user_id=self._user_id)

        attendees_raw = args["attendees"]
        attendees = [a.strip() for a in attendees_raw.split(",")]

        event = {
            "summary": args["purpose"],
            "attendees": [{"email": a} if "@" in a else {"displayName": a} for a in attendees],
            "description": args["purpose"],
            "start_time": args["time_range"],
        }

        result = await agent._call_tool(
            "calendar_write",
            action="create",
            event=event,
        )

        if isinstance(result, dict) and not result.get("connected", True):
            return ToolResult(
                spoken_text=(
                    "Your calendar isn't connected yet. "
                    "You can connect Google Calendar or Outlook in Settings under Integrations. "
                    "Once connected, I'll be able to schedule meetings directly."
                )
            )

        parts = [f"I'm setting up a meeting for {args['purpose']} with {', '.join(attendees)}."]
        parts.append(f"Targeting {args['time_range']}.")

        if isinstance(result, dict) and result.get("event_id"):
            parts.append("The meeting has been created and invitations sent.")
        else:
            parts.append("I've submitted the request. Check your calendar for confirmation.")

        return ToolResult(spoken_text=" ".join(parts))

    async def _handle_get_market_signals(self, args: dict[str, Any]) -> ToolResult:
        from src.agents import ScoutAgent

        agent = ScoutAgent(llm_client=self.llm, user_id=self._user_id)
        topic = args["topic"]

        results = await agent._call_tool(
            "news_search",
            query=topic,
            limit=5,
            days_back=14,
        )

        if not results:
            return ToolResult(
                spoken_text=f"I didn't find any recent market signals for {topic}. Want me to expand the time window?"
            )

        articles = results if isinstance(results, list) else []
        if not articles:
            return ToolResult(
                spoken_text=f"No recent signals found for {topic}."
            )

        parts = [f"Here are the latest market signals for {topic}."]
        for i, article in enumerate(articles[:4], 1):
            title = article.get("title", "")
            source = article.get("source", "")
            if title:
                entry = f"{i}. {title[:100]}"
                if source:
                    entry += f" from {source}"
                parts.append(entry)

        parts.append("Would you like me to analyse any of these signals in more detail?")

        # Build rich content for signal overlay
        signal_items: list[dict[str, str]] = []
        for article in articles[:5]:
            signal_items.append({
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "url": article.get("url", ""),
                "date": article.get("published_at", article.get("date", "")),
            })

        rich_content: dict[str, Any] = {
            "type": "signal_list",
            "data": {
                "topic": topic,
                "signals": signal_items,
            },
        }

        return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)

    async def _handle_add_lead_to_pipeline(self, args: dict[str, Any]) -> ToolResult:
        company_name = args["company_name"]
        contact_name = args.get("contact_name")
        notes = args.get("notes", "Added during video conversation")

        # Check if already exists
        existing = (
            self.db.table("lead_memories")
            .select("id, company_name, lifecycle_stage")
            .eq("user_id", self._user_id)
            .ilike("company_name", f"%{company_name}%")
            .limit(1)
            .execute()
        )

        if existing.data:
            lead = existing.data[0]
            return ToolResult(
                spoken_text=(
                    f"{lead['company_name']} is already in your pipeline "
                    f"at the {lead.get('lifecycle_stage', 'prospect')} stage. "
                    "Would you like me to update their information?"
                )
            )

        # Insert new lead
        lead_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        row: dict[str, Any] = {
            "id": lead_id,
            "user_id": self._user_id,
            "company_name": company_name,
            "lifecycle_stage": "prospect",
            "health_score": 50,
            "status": "active",
            "last_activity_at": now,
            "created_at": now,
            "metadata": json.dumps({
                "source": "video_conversation",
                "notes": notes,
                "contact_name": contact_name,
                "added_at": now,
            }),
        }

        self.db.table("lead_memories").insert(row).execute()

        parts = [f"Done. I've added {company_name} to your pipeline as a prospect."]
        if contact_name:
            parts.append(f"Primary contact: {contact_name}.")
        parts.append("I'll start monitoring them for signals and enriching the profile.")

        return ToolResult(spoken_text=" ".join(parts))

    async def _handle_trigger_goal_action(self, args: dict[str, Any]) -> ToolResult:
        goal_description = args["goal_description"]

        # Find matching active goal
        goals_result = (
            self.db.table("goals")
            .select("id, title, description, goal_type, config, progress, status")
            .eq("user_id", self._user_id)
            .eq("status", "active")
            .execute()
        )

        if not goals_result.data:
            return ToolResult(
                spoken_text=(
                    "You don't have any active goals right now. "
                    "Would you like me to create one?"
                )
            )

        # Find best match by keyword overlap
        query_words = set(goal_description.lower().split())
        best_match = None
        best_score = 0
        for goal in goals_result.data:
            title_words = set(goal.get("title", "").lower().split())
            desc_words = set(goal.get("description", "").lower().split())
            all_words = title_words | desc_words
            overlap = len(query_words & all_words)
            if overlap > best_score:
                best_score = overlap
                best_match = goal

        if not best_match or best_score == 0:
            # No keyword match — use first active goal
            best_match = goals_result.data[0]

        goal_title = best_match.get("title", "your goal")

        # Run one OODA iteration
        try:
            from src.core.ooda import OODAConfig, OODALoop, OODAState
            from src.memory.episodic import EpisodicMemory
            from src.memory.semantic import SemanticMemory
            from src.memory.working import WorkingMemory

            episodic = EpisodicMemory()
            semantic = SemanticMemory()
            working = WorkingMemory(
                conversation_id=f"video-ooda-{best_match['id']}",
                user_id=self._user_id,
            )

            ooda = OODALoop(
                llm_client=self.llm,
                episodic_memory=episodic,
                semantic_memory=semantic,
                working_memory=working,
                config=OODAConfig(max_iterations=1),
            )

            state = OODAState(goal_id=best_match["id"])
            state = await ooda.run_single_iteration(state, best_match)

            decision = state.decision or {}
            action = decision.get("action", "observe")
            agent = decision.get("agent", "")
            reasoning = decision.get("reasoning", "")

            parts = [f"Working on '{goal_title}'."]

            if action == "complete":
                parts.append("This goal appears to be complete based on current data.")
            elif state.is_blocked:
                parts.append(
                    f"I'm blocked on this goal. {state.blocked_reason or 'I need more information.'}"
                )
            else:
                if reasoning:
                    parts.append(reasoning[:150])
                if agent:
                    parts.append(f"I've dispatched the {agent} agent to take action.")
                if state.action_result:
                    summary = (
                        state.action_result.get("summary", "")
                        if isinstance(state.action_result, dict)
                        else str(state.action_result)[:150]
                    )
                    if summary:
                        parts.append(summary[:150])

            parts.append("Want me to continue working on this?")
            return ToolResult(spoken_text=" ".join(parts))

        except Exception:
            logger.exception("OODA trigger failed", extra={"goal_id": best_match.get("id")})
            return ToolResult(
                spoken_text=(
                    f"I found your goal '{goal_title}' but ran into an issue "
                    "processing it right now. I'll keep monitoring it in the background."
                )
            )

    async def _handle_create_goal_from_video(self, args: dict[str, Any]) -> ToolResult:
        """Create a goal from video conversation and generate a plan."""
        from src.core.ws import ws_manager
        from src.models.goal import GoalCreate, GoalType
        from src.services.goal_execution import GoalExecutionService

        goal_title = args.get("goal_title", "")
        goal_description = args.get("goal_description", goal_title)
        goal_type_str = args.get("goal_type", "task")

        # Map goal_type string to enum
        type_mapping = {
            "research": GoalType.RESEARCH,
            "outreach": GoalType.OUTREACH,
            "analysis": GoalType.ANALYSIS,
            "meeting_prep": GoalType.MEETING_PREP,
            "content_creation": GoalType.CONTENT_CREATION,
            "task": GoalType.TASK,
        }
        goal_type = type_mapping.get(goal_type_str.lower(), GoalType.TASK)

        try:
            # Create the goal
            from src.services.goal_service import GoalService

            goal_service = GoalService()
            goal = await goal_service.create_goal(
                user_id=self._user_id,
                data=GoalCreate(
                    title=goal_title,
                    description=goal_description,
                    goal_type=goal_type,
                    config={"source": "video_conversation"},
                ),
            )
            goal_id = goal["id"]

            # Generate plan using GoalExecutionService
            execution_service = GoalExecutionService()
            plan_result = await execution_service.plan_goal(
                user_id=self._user_id,
                goal_id=goal_id,
            )

            # Extract plan details for spoken text
            plan = plan_result.get("plan", {})
            phases = plan.get("phases", [])
            agents = plan.get("agents", [])
            timeline = plan.get("timeline", "a few days")

            parts = [f"I've put together a plan for '{goal_title}'."]
            if phases:
                parts.append(f"The plan has {len(phases)} phases.")
            if agents:
                agent_names = [a.replace("_", " ").title() for a in agents[:3]]
                parts.append(f"I'll use the {', '.join(agent_names)} agent{'s' if len(agents) > 1 else ''}.")
            parts.append(f"Estimated timeline: {timeline}.")
            parts.append("Check the chat panel for details. Would you like me to start executing this plan?")

            # Send WebSocket event to show GoalPlanCard in chat panel
            rich_content = {
                "type": "goal_plan",
                "data": {
                    "id": goal_id,
                    "title": goal_title,
                    "rationale": goal_description,
                    "approach": plan.get("approach", ""),
                    "phases": phases,
                    "agents": agents,
                    "timeline": timeline,
                    "goal_type": goal_type_str,
                    "status": "proposed",
                },
            }

            # Emit to frontend via WebSocket
            await ws_manager.send_aria_message(
                user_id=self._user_id,
                message="",
                rich_content=[rich_content],
                suggestions=["Approve plan", "Modify plan", "Discuss approach"],
            )

            return ToolResult(
                spoken_text=" ".join(parts),
                rich_content=rich_content,
            )

        except Exception:
            logger.exception("Failed to create goal from video")
            return ToolResult(
                spoken_text=(
                    f"I'd like to help with '{goal_title}', but I ran into an issue "
                    "creating the plan. Let me try a different approach."
                )
            )

    async def _handle_get_capabilities(self, args: dict[str, Any]) -> ToolResult:
        """Get ARIA's capabilities and integration status."""
        detail_level = args.get("detail_level", "brief")

        # Get integration status
        integrations_result = (
            self.db.table("user_integrations")
            .select("integration_type, status")
            .eq("user_id", self._user_id)
            .execute()
        )
        connected = [i["integration_type"] for i in (integrations_result.data or []) if i.get("status") == "active"]

        # Build capability summary
        if detail_level == "full":
            capabilities = [
                "I can search for companies and discover new leads using the Hunter agent.",
                "I can research scientific publications and clinical trials through the Analyst agent.",
                "I can draft emails and documents with the Scribe agent.",
                "I can schedule meetings and manage your calendar via the Operator agent.",
                "I can monitor market signals and news through the Scout agent.",
                "I can create goals and plans, and work on them autonomously.",
                "I can prepare meeting briefs with attendee profiles and talking points.",
                "I can manage your pipeline and track lead health scores.",
            ]
            parts = ["Here's what I can do for you:"] + capabilities

            if connected:
                parts.append(f"\nYour connected integrations: {', '.join(connected)}.")
            else:
                parts.append("\nNo integrations are currently connected. You can connect Google Calendar, Gmail, or Outlook in Settings.")
        else:
            # Brief summary
            parts = [
                "I can help you find leads, research companies and science, draft emails, "
                "schedule meetings, monitor market signals, and work on goals autonomously."
            ]
            if connected:
                integration_names = {
                    "gmail": "email", "google_calendar": "calendar", "outlook": "Outlook"
                }
                connected_friendly = [integration_names.get(i, i) for i in connected[:3]]
                parts.append(f"I have access to your {', '.join(connected_friendly)}.")
            else:
                parts.append("Connect your calendar or email in Settings to unlock more capabilities.")

        return ToolResult(spoken_text=" ".join(parts))

    async def _handle_get_meeting_prep(self, args: dict[str, Any]) -> ToolResult:
        """Get comprehensive meeting preparation."""
        from src.services.briefing import BriefingService

        meeting_id = args.get("meeting_id")

        if meeting_id:
            result = (
                self.db.table("meeting_briefs")
                .select("*")
                .eq("user_id", self._user_id)
                .eq("calendar_event_id", meeting_id)
                .limit(1)
                .execute()
            )
        else:
            # Get next upcoming meeting brief
            now = datetime.now(UTC).isoformat()
            result = (
                self.db.table("meeting_briefs")
                .select("*")
                .eq("user_id", self._user_id)
                .gte("meeting_time", now)
                .order("meeting_time")
                .limit(1)
                .execute()
            )

        if not result.data:
            # No meeting brief - check if there's a calendar event
            calendar_result = (
                self.db.table("calendar_events")
                .select("id, title, start_time, attendees")
                .eq("user_id", self._user_id)
                .gte("start_time", datetime.now(UTC).isoformat())
                .order("start_time")
                .limit(1)
                .execute()
            )

            if not calendar_result.data:
                return ToolResult(
                    spoken_text="You don't have any upcoming meetings on your calendar. Would you like me to help you schedule one?"
                )

            # Generate prep from calendar event
            event = calendar_result.data[0]
            title = event.get("title", "your meeting")
            attendees = event.get("attendees", [])
            start_time = event.get("start_time", "")

            parts = [f"Here's prep for {title}."]
            if start_time:
                parts.append(f"Starting at {start_time[:16].replace('T', ' at ')}.")
            if attendees:
                names = [a.get("displayName", a.get("email", "Unknown")) for a in attendees[:4]]
                parts.append(f"Attendees: {', '.join(names)}.")

            # Try to get company signals for attendees
            try:
                briefing_service = BriefingService()
                signals = await briefing_service._get_signal_data(self._user_id)
                company_news = signals.get("company_news", [])[:2]
                if company_news:
                    parts.append("Recent signals:")
                    for news in company_news:
                        parts.append(f"{news.get('company_name')}: {news.get('headline', '')[:60]}.")
            except Exception:
                pass

            parts.append("Would you like me to generate a full briefing for this meeting?")

            return ToolResult(spoken_text=" ".join(parts))

        # Use existing meeting brief
        brief = result.data[0]
        title = brief.get("meeting_title", "your meeting")
        meeting_time = brief.get("meeting_time", "")
        attendees = brief.get("attendees", [])
        content = brief.get("brief_content", {})

        parts = [f"Here's your prep for {title}."]

        if meeting_time:
            parts.append(f"Starting at {meeting_time[:16].replace('T', ' at ')}.")

        if attendees:
            names = attendees if isinstance(attendees, list) else [attendees]
            parts.append(f"Attendees: {', '.join(str(a) for a in names[:4])}.")

        if isinstance(content, dict):
            summary = content.get("summary") or content.get("key_points")
            if summary:
                text = summary if isinstance(summary, str) else ". ".join(str(s) for s in summary[:3])
                parts.append(text[:200])

            talking_points = content.get("talking_points", [])
            if talking_points:
                points = talking_points if isinstance(talking_points, list) else [talking_points]
                parts.append(f"Suggested talking points: {', '.join(str(p) for p in points[:3])}.")

            objections = content.get("potential_objections", [])
            if objections:
                parts.append("Watch for potential objections around their budget and timeline.")

        parts.append("Would you like me to go deeper on any of these points?")

        # Build rich content for side panel
        rich_content = {
            "type": "meeting_prep",
            "data": {
                "meeting_id": brief.get("calendar_event_id"),
                "title": title,
                "meeting_time": meeting_time,
                "attendees": attendees,
                "brief_content": content,
            },
        }

        return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)

    async def _handle_debrief_meeting(self, args: dict[str, Any]) -> ToolResult:
        """Record a post-meeting debrief and extract action items."""
        meeting_id = args.get("meeting_id")
        summary = args.get("summary", "")
        action_items_text = args.get("action_items", "")
        next_steps_text = args.get("next_steps", "")

        # Find the meeting
        if meeting_id:
            result = (
                self.db.table("meeting_briefs")
                .select("id, calendar_event_id, meeting_title, attendees")
                .eq("user_id", self._user_id)
                .eq("calendar_event_id", meeting_id)
                .limit(1)
                .execute()
            )
        else:
            # Get most recent past meeting
            now = datetime.now(UTC).isoformat()
            result = (
                self.db.table("meeting_briefs")
                .select("id, calendar_event_id, meeting_title, attendees")
                .eq("user_id", self._user_id)
                .lt("meeting_time", now)
                .order("meeting_time", desc=True)
                .limit(1)
                .execute()
            )

        if not result.data:
            return ToolResult(
                spoken_text="I don't see a recent meeting to debrief. Which meeting would you like to discuss?"
            )

        meeting = result.data[0]
        meeting_title = meeting.get("meeting_title", "the meeting")

        # Extract action items via LLM if not explicitly provided
        action_items = []
        if not action_items_text and summary:
            try:
                # Get persona preamble so ARIA sounds like herself
                persona_preamble = await self._get_persona_preamble()
                extraction_prompt = (
                    f"Extract action items from this meeting debrief. Return as JSON array:\n\n"
                    f"Debrief: {summary}\n\n"
                    f'Return format: {{"action_items": [{{"task": "...", "priority": "high|medium|low"}}]}}'
                )
                messages = [{"role": "user", "content": extraction_prompt}]
                if persona_preamble:
                    messages.insert(0, {"role": "system", "content": persona_preamble})
                raw = await self.llm.generate_response(
                    messages=messages,
                    max_tokens=512,
                    temperature=0.2,
                    task=TaskType.GENERAL,
                    agent_id="tavus",
                )

                extracted = json.loads(raw)
                action_items = extracted.get("action_items", [])
            except Exception:
                # Fallback: treat summary as a single action item
                action_items = [{"task": summary[:100], "priority": "medium"}]
        elif action_items_text:
            action_items = [{"task": action_items_text, "priority": "medium"}]

        # Create prospective memory tasks for action items
        tasks_created = 0
        try:
            from src.memory.prospective import ProspectiveMemory, ProspectiveTask, TaskPriority, TaskStatus, TriggerType

            prospective = ProspectiveMemory()
            for item in action_items[:5]:
                priority_str = item.get("priority", "medium")
                try:
                    priority = TaskPriority(priority_str)
                except ValueError:
                    priority = TaskPriority.MEDIUM

                task = ProspectiveTask(
                    id=str(uuid.uuid4()),
                    user_id=self._user_id,
                    task=item.get("task", "Follow up from meeting"),
                    description=f"From meeting: {meeting_title}",
                    trigger_type=TriggerType.TIME,
                    trigger_config={},
                    status=TaskStatus.PENDING,
                    priority=priority,
                    created_at=datetime.now(UTC),
                )
                await prospective.create_task(task)
                tasks_created += 1
        except Exception:
            logger.debug("Failed to create prospective tasks from debrief", exc_info=True)

        # Update meeting brief with debrief notes
        try:
            self.db.table("meeting_briefs").update({
                "debrief_notes": {
                    "summary": summary,
                    "action_items": action_items,
                    "next_steps": next_steps_text,
                    "debriefed_at": datetime.now(UTC).isoformat(),
                }
            }).eq("id", meeting["id"]).execute()
        except Exception:
            logger.debug("Failed to update meeting brief with debrief", exc_info=True)

        # Build response
        parts = [f"Got it. I've captured your debrief for {meeting_title}."]

        if tasks_created > 0:
            parts.append(f"I created {tasks_created} follow-up task{'s' if tasks_created > 1 else ''} for you.")
            for item in action_items[:3]:
                parts.append(f"- {item.get('task', 'Action item')[:80]}")

        if next_steps_text:
            parts.append(f"Next steps: {next_steps_text[:100]}.")

        parts.append("Anything else you'd like to add or adjust?")

        # Build rich content
        rich_content = {
            "type": "meeting_debrief",
            "data": {
                "meeting_id": meeting.get("calendar_event_id"),
                "meeting_title": meeting_title,
                "action_items": action_items,
                "next_steps": next_steps_text,
                "tasks_created": tasks_created,
            },
        }

        return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)

    async def _handle_get_recent_work(self, args: dict[str, Any]) -> ToolResult:
        """Get a summary of recent ARIA activity."""
        from datetime import timedelta

        timeframe = args.get("timeframe", "recent")

        # Determine time window
        if timeframe == "today":
            since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "this_week":
            since = datetime.now(UTC) - timedelta(days=7)
        else:
            since = datetime.now(UTC) - timedelta(days=3)

        since_iso = since.isoformat()

        # Get recent activity
        activity_result = (
            self.db.table("aria_activity")
            .select("agent, activity_type, title, created_at, confidence")
            .eq("user_id", self._user_id)
            .gte("created_at", since_iso)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        # Get goal progress
        goals_result = (
            self.db.table("goals")
            .select("id, title, status, progress, updated_at")
            .eq("user_id", self._user_id)
            .in_("status", ["active", "plan_ready"])
            .order("updated_at", desc=True)
            .limit(5)
            .execute()
        )

        activities = activity_result.data or []
        goals = goals_result.data or []

        if not activities and not goals:
            return ToolResult(
                spoken_text="I haven't been working on anything specific recently. "
                "Would you like me to start on a goal or research something for you?"
            )

        parts = ["Here's what I've been working on."]

        # Summarize recent activity by type
        if activities:
            agent_counts: dict[str, int] = {}
            recent_titles: list[str] = []
            for activity in activities[:8]:
                agent = activity.get("agent", "aria")
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
                if activity.get("title"):
                    recent_titles.append(activity["title"])

            # Agent activity summary
            agent_names = {
                "hunter": "lead discovery",
                "analyst": "research",
                "strategist": "strategy",
                "scribe": "drafting",
                "operator": "operations",
                "scout": "monitoring",
                "aria": "general tasks",
            }
            for agent, count in list(agent_counts.items())[:3]:
                friendly_name = agent_names.get(agent, agent)
                parts.append(f"{count} {friendly_name} task{'s' if count > 1 else ''}.")

            # Recent highlights
            if recent_titles:
                parts.append(f"Most recently: {recent_titles[0][:80]}.")

        # Goal progress
        if goals:
            parts.append(f"\nYou have {len(goals)} active goal{'s' if len(goals) > 1 else ''}.")
            for goal in goals[:2]:
                title = goal.get("title", "a goal")
                progress = goal.get("progress", 0)
                parts.append(f"{title} is at {progress}% progress.")

        parts.append("Want me to continue on any of these, or start something new?")

        # Build rich content
        rich_content = {
            "type": "recent_activity",
            "data": {
                "activities": activities[:8],
                "goals": goals[:5],
                "timeframe": timeframe,
            },
        }

        return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)

    # ------------------------------------------------------------------
    # Activity logging
    # ------------------------------------------------------------------

    async def _log_activity(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
    ) -> None:
        """Log tool execution to aria_activity."""
        try:
            from src.services.activity_service import ActivityService

            activity = ActivityService()
            agent_name = TOOL_AGENT_MAP.get(tool_name, "service")

            await activity.record(
                user_id=self._user_id,
                agent=agent_name if agent_name != "service" else "aria",
                activity_type="video_tool_executed",
                title=f"Video tool: {tool_name.replace('_', ' ')}",
                description=f"Executed {tool_name} during video conversation",
                confidence=1.0 if success else 0.0,
                metadata={
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "success": success,
                    "source": "tavus_video",
                },
            )
        except Exception:
            logger.debug("Failed to log video tool activity", exc_info=True)

    # ------------------------------------------------------------------
    # Episodic memory
    # ------------------------------------------------------------------

    async def _store_episodic(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        """Store video tool execution as an episodic memory."""
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            em = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=self._user_id,
                event_type=f"video_tool_{tool_name}",
                content=result.spoken_text,
                participants=[self._user_id],
                occurred_at=now,
                recorded_at=now,
                context={
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "source": "tavus_video",
                    "has_rich_content": result.rich_content is not None,
                },
            )
            await em.store_episode(episode)
        except Exception:
            logger.debug("Failed to store episodic memory for video tool", exc_info=True)
