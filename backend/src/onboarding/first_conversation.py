"""US-914: First Conversation Generator (Intelligence Demonstration).

Generates ARIA's intelligence-demonstrating first message after memory
construction (US-911) completes. This is the single most important moment
in ARIA's product experience — the first message must prove she's worth
$200K/year from the first interaction.

The message:
1. Shows what ARIA already knows (Corporate Memory)
2. Demonstrates competitive awareness
3. Honestly flags knowledge gaps
4. Orients toward the user's goal
5. Matches the user's communication style
6. Includes a Memory Delta for correction
7. Suggests a concrete next step
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

logger = logging.getLogger(__name__)


class FirstConversationMessage(BaseModel):
    """The structured output of ARIA's first message to a user."""

    content: str
    memory_delta: dict[str, Any]
    suggested_next_action: str
    facts_referenced: int
    confidence_level: str  # "high", "moderate", "limited"
    rich_content: list[dict[str, Any]] = Field(default_factory=list)
    ui_commands: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class FirstConversationGenerator:
    """Generates ARIA's intelligence-demonstrating first message.

    Assembles highest-confidence facts from all memory systems,
    identifies the most interesting finding, and crafts a personalized
    opening that proves ARIA has done her homework.
    """

    def __init__(self) -> None:
        """Initialize with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()

    async def generate(self, user_id: str) -> FirstConversationMessage:
        """Generate the first conversation message for a user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            FirstConversationMessage with content, memory delta, and metadata.
        """
        logger.info("Generating first conversation", extra={"user_id": user_id})

        # 1. Gather intelligence from all memory systems
        facts = await self._get_top_facts(user_id, limit=30)
        classification = await self._get_classification(user_id)
        gaps = await self._get_critical_gaps(user_id)
        goal = await self._get_first_goal(user_id)
        style = await self._get_writing_style(user_id)
        personality = await self._get_personality_calibration(user_id)
        user_profile = await self._get_user_profile(user_id)

        # 2. Find the most interesting/surprising finding
        interesting_fact = await self._identify_surprising_fact(facts, classification)

        # 3. Build the message via LLM
        message = await self._compose_message(
            user_profile=user_profile,
            classification=classification,
            facts=facts,
            interesting_fact=interesting_fact,
            gaps=gaps,
            goal=goal,
            style=style,
            personality=personality,
        )

        # Generate goal proposals as rich content
        goal_proposals = await self._generate_goal_proposals(
            user_profile=user_profile,
            classification=classification,
            facts=facts,
            gaps=gaps,
        )

        # Build UI commands (sidebar badges)
        ui_commands = self._build_ui_commands(facts, classification)

        # Build suggestions
        suggestion_list = [
            "Tell me more about the first goal",
            "What competitors did you find?",
            "Start with the pipeline goal",
        ]

        # Attach to message
        message.rich_content = goal_proposals
        message.ui_commands = ui_commands
        message.suggestions = suggestion_list

        # 4. Store as first message in conversation thread
        await self._store_first_message(user_id, message)

        # 5. Record episodic memory event
        await self._record_episodic_event(user_id, message)

        # Audit log entry
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.EPISODIC,
            metadata={
                "action": "first_conversation_delivered",
                "facts_referenced": message.facts_referenced,
                "confidence_level": message.confidence_level,
            },
            suppress_errors=True,
        )

        logger.info(
            "First conversation generated",
            extra={
                "user_id": user_id,
                "facts_referenced": message.facts_referenced,
                "confidence_level": message.confidence_level,
            },
        )

        return message

    async def _identify_surprising_fact(
        self,
        facts: list[dict[str, Any]],
        classification: dict[str, Any] | None,
    ) -> str | None:
        """Find the most interesting/non-obvious fact to lead with.

        Args:
            facts: Top semantic facts sorted by confidence.
            classification: Company classification data.

        Returns:
            The most interesting fact text, or None if no facts available.
        """
        if not facts:
            return None

        fact_text = "\n".join(f"- {f.get('fact', '')}" for f in facts[:20])

        company_context = ""
        if classification:
            company_context = f"\nCompany type: {classification.get('company_type', 'unknown')}"

        prompt = (
            "From these facts about a life sciences company, identify the "
            "single most interesting or surprising finding that would impress "
            "a sales professional.\n\n"
            f"Facts:\n{fact_text}{company_context}\n\n"
            "The fact should be:\n"
            "- Non-obvious (not something they'd already know about their own company)\n"
            "- Business-relevant (useful for sales strategy)\n"
            "- Specific (includes numbers, names, or dates if possible)\n\n"
            "Return just the fact text, nothing else."
        )

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            return response.strip() if response else None
        except Exception as e:
            logger.warning(f"Surprising fact identification failed: {e}")
            # Fall back to the highest-confidence fact
            return facts[0].get("fact") if facts else None

    async def _compose_message(
        self,
        user_profile: dict[str, Any] | None,
        classification: dict[str, Any] | None,
        facts: list[dict[str, Any]],
        interesting_fact: str | None,
        gaps: list[dict[str, Any]],
        goal: dict[str, Any] | None,
        style: dict[str, Any] | None,
        personality: dict[str, Any] | None = None,
    ) -> FirstConversationMessage:
        """Compose the full first message using LLM.

        Args:
            user_profile: User profile data.
            classification: Company classification data.
            facts: Top semantic facts.
            interesting_fact: The most surprising finding.
            gaps: Critical knowledge gaps.
            goal: User's first goal.
            style: Writing style preferences from Digital Twin.

        Returns:
            FirstConversationMessage with full content and metadata.
        """
        # Extract user name
        user_name = ""
        if user_profile and user_profile.get("full_name"):
            user_name = user_profile["full_name"].split()[0]

        # Build facts summary
        facts_summary = "\n".join(
            f"- {f.get('fact', '')} (confidence: {f.get('confidence', 0):.0%})" for f in facts[:15]
        )

        # Build gap list
        gap_list = "\n".join(f"- {g.get('task', '')}" for g in gaps[:3])

        # Extract goal text
        goal_text = goal.get("title", "") if goal else ""

        # Build style guidance
        style_guidance = self._build_style_guidance(style)

        system_prompt = (
            "You are ARIA, an AI Department Director for a life sciences "
            "commercial team. You are writing your FIRST message to a new "
            "user. This message must demonstrate real intelligence — proving "
            "you've done your homework and are worth the investment. Sound "
            "like an impressive, knowledgeable colleague — not a chatbot."
        )

        # Inject personality calibration tone guidance if available
        tone_guidance = (personality or {}).get("tone_guidance")
        if tone_guidance:
            system_prompt += f"\n\nAdapt your communication style: {tone_guidance}"

        user_prompt = (
            f"Write your FIRST message to {user_name or 'the user'}.\n\n"
            f"CONTEXT:\n"
            f"- Company classification: {classification or 'Unknown'}\n"
            f"- User's role: {(user_profile or {}).get('role', 'Unknown')}\n"
            f"- User's title: {(user_profile or {}).get('title', 'Unknown')}\n"
            f"- Key facts I've learned:\n{facts_summary or 'None yet'}\n\n"
            f"- Most interesting finding: {interesting_fact or 'None yet'}\n"
            f"- Knowledge gaps: {gap_list or 'None critical'}\n"
            f"- User's first goal: {goal_text or 'Not set yet'}\n\n"
            f"STYLE: {style_guidance}\n\n"
            "REQUIREMENTS:\n"
            "1. Open with a warm, confident greeting using their first name if available\n"
            "2. Lead with the most interesting/surprising finding to demonstrate intelligence\n"
            "3. Briefly summarize 3-4 key things you've learned (Corporate Memory demonstration)\n"
            "4. If competitive info was found, mention it naturally (don't force it)\n"
            "5. Honestly flag 1-2 things you don't know yet and would like to learn\n"
            '6. If a goal was set, orient toward it ("I\'ve already started on...")\n'
            "7. End with a concrete suggested next action\n"
            "8. Keep it CONCISE — max 200 words. This is a colleague, not a report.\n"
            "9. Do NOT use bullet points or headers. Write as natural conversation.\n"
            '10. Include a closing like: "Here\'s what I know so far — anything I got wrong or missing?"\n\n'
            "IMPORTANT: Sound like an impressive, knowledgeable colleague — not a chatbot. "
            'No "I\'m excited to help you!" nonsense.'
        )

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.7,
            )
        except Exception as e:
            logger.error(f"LLM generation failed for first conversation: {e}")
            # Fallback message when LLM fails
            response = self._build_fallback_message(user_name, facts, gaps, goal_text)

        # Build Memory Delta (structured facts for correction UI)
        memory_delta = self._build_memory_delta(facts, classification, gaps)

        # Determine confidence level
        fact_count = len(facts)
        if fact_count > 15:
            confidence_level = "high"
        elif fact_count > 5:
            confidence_level = "moderate"
        else:
            confidence_level = "limited"

        return FirstConversationMessage(
            content=response.strip(),
            memory_delta=memory_delta,
            suggested_next_action=(goal_text or "Let's review what I've found about your company"),
            facts_referenced=min(fact_count, 15),
            confidence_level=confidence_level,
        )

    async def _generate_goal_proposals(
        self,
        user_profile: dict[str, Any] | None,
        classification: dict[str, Any] | None,
        facts: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate 3 strategic goal proposals as rich_content GoalPlanCards.

        Uses the LLM to propose goals specific to the user's company, role,
        and the intelligence gathered during onboarding.

        Args:
            user_profile: User profile data (name, role, title).
            classification: Company classification data.
            facts: Top semantic facts from memory.
            gaps: Critical knowledge gaps.

        Returns:
            List of rich_content dicts with type="goal_plan".
        """
        company_name = ""
        role = ""
        if user_profile:
            company_name = user_profile.get("company_name", "")
            role = user_profile.get("role", "")

        company_type = ""
        if classification:
            company_type = classification.get("company_type", "")

        facts_summary = "\n".join(f"- {f.get('fact', '')}" for f in facts[:10])
        gaps_summary = "\n".join(f"- {g.get('task', '')}" for g in gaps[:3])

        prompt = (
            "You are ARIA, an AI Department Director for life sciences commercial teams.\n\n"
            f"Company: {company_name}\n"
            f"Company type: {company_type}\n"
            f"User role: {role}\n\n"
            f"Key facts gathered:\n{facts_summary or 'Limited data so far'}\n\n"
            f"Knowledge gaps:\n{gaps_summary or 'None critical'}\n\n"
            "Propose exactly 3 strategic goals that would deliver the most value "
            "for this user in their first 30 days. Each goal should be specific "
            "to their company and role, not generic.\n\n"
            "Return a JSON array with exactly 3 objects, each having:\n"
            '- "title": concise goal title (max 60 chars)\n'
            '- "rationale": why this goal matters for them specifically (1 sentence)\n'
            '- "approach": high-level approach ARIA will take (1-2 sentences)\n'
            '- "agents": array of agent names that will work on this '
            "(from: Hunter, Analyst, Strategist, Scribe, Operator, Scout)\n"
            '- "timeline": estimated timeline (e.g. "1-2 weeks")\n'
            '- "goal_type": one of "pipeline", "competitive_intel", '
            '"account_strategy", "communication", "market_research"\n\n'
            "Return ONLY the JSON array, no other text."
        )

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.7,
            )

            # Parse JSON from response (handle markdown code blocks)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Remove markdown code fences
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[: -len("```")]
                cleaned = cleaned.strip()

            goals = json.loads(cleaned)

            # Convert to rich_content format
            rich_content: list[dict[str, Any]] = []
            for i, goal in enumerate(goals[:3]):
                rich_content.append(
                    {
                        "type": "goal_plan",
                        "data": {
                            "id": f"proposed-goal-{i + 1}",
                            "title": goal.get("title", f"Goal {i + 1}"),
                            "rationale": goal.get("rationale", ""),
                            "approach": goal.get("approach", ""),
                            "agents": goal.get("agents", []),
                            "timeline": goal.get("timeline", "2 weeks"),
                            "goal_type": goal.get("goal_type", "custom"),
                            "status": "proposed",
                        },
                    }
                )

            return rich_content
        except Exception as e:
            logger.warning(f"Goal proposal generation failed: {e}")
            return []

    def _build_ui_commands(
        self,
        facts: list[dict[str, Any]],
        classification: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Build UI commands for sidebar badges based on gathered intelligence.

        Adds badge counts to sidebar items so the user sees ARIA has
        already populated their workspace with intelligence.

        Args:
            facts: Top semantic facts from memory.
            classification: Company classification data.

        Returns:
            List of ui_command dicts for sidebar badge updates.
        """
        commands: list[dict[str, Any]] = []

        # Count competitor mentions in facts
        competitor_count = 0
        competitor_keywords = {"competitor", "competing", "rival", "versus", "vs"}
        for fact in facts:
            fact_text = fact.get("fact", "").lower()
            if any(kw in fact_text for kw in competitor_keywords):
                competitor_count += 1

        # Also check classification for competitor data
        if classification and classification.get("competitors"):
            competitor_count = max(competitor_count, len(classification["competitors"]))

        if competitor_count > 0:
            commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "intelligence",
                    "badge_count": competitor_count,
                }
            )

        # Add pipeline badge with facts count
        if facts:
            commands.append(
                {
                    "action": "update_sidebar_badge",
                    "sidebar_item": "pipeline",
                    "badge_count": len(facts),
                }
            )

        return commands

    def _build_style_guidance(self, style: dict[str, Any] | None) -> str:
        """Build style guidance from Digital Twin writing style.

        Args:
            style: Writing style dict with directness, formality_index, etc.

        Returns:
            Style guidance string for the LLM prompt.
        """
        if not style:
            return "Balanced — professional but approachable"

        parts: list[str] = []
        directness = style.get("directness", 0.5)
        formality = style.get("formality_index", 0.5)

        if directness > 0.7:
            parts.append("Be direct and concise. No fluff.")
        elif directness < 0.3:
            parts.append("Be warm and diplomatic. Build rapport.")

        if formality > 0.7:
            parts.append("Use formal tone.")
        elif formality < 0.3:
            parts.append("Keep it casual and conversational.")

        return " ".join(parts) if parts else "Balanced — professional but approachable"

    def _build_memory_delta(
        self,
        facts: list[dict[str, Any]],
        classification: dict[str, Any] | None,
        gaps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build Memory Delta structure for correction UI.

        Args:
            facts: Top semantic facts.
            classification: Company classification data.
            gaps: Knowledge gaps.

        Returns:
            Structured dict for the MemoryDelta component.
        """
        # Group facts by confidence tier using CLAUDE.md confidence mapping
        high_confidence: list[str] = []
        moderate_confidence: list[str] = []
        low_confidence: list[str] = []

        for f in facts[:8]:
            fact_text = f.get("fact", "")
            confidence = f.get("confidence", 0)
            if confidence >= 0.95:
                high_confidence.append(fact_text)
            elif confidence >= 0.80:
                moderate_confidence.append(fact_text)
            else:
                low_confidence.append(fact_text)

        return {
            "facts_stated": high_confidence,
            "facts_inferred": moderate_confidence,
            "facts_uncertain": low_confidence,
            "classification": classification or {},
            "gaps": [g.get("task", "") for g in gaps[:3]],
        }

    def _build_fallback_message(
        self,
        user_name: str,
        facts: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        goal_text: str,
    ) -> str:
        """Build a fallback message when LLM generation fails.

        Args:
            user_name: User's first name.
            facts: Available facts.
            gaps: Knowledge gaps.
            goal_text: First goal text.

        Returns:
            A simple but functional first message.
        """
        greeting = f"Hi {user_name}," if user_name else "Hi,"
        fact_count = len(facts)

        if fact_count > 0:
            body = (
                f" I've been reviewing your company and gathered {fact_count} key findings so far."
            )
        else:
            body = " I'm getting set up and ready to learn about your business."

        if gaps:
            body += " There are a few areas I'd love to learn more about."

        if goal_text:
            body += f' I see you want to focus on "{goal_text}" — let\'s start there.'

        body += " Here's what I know so far — anything I got wrong or missing?"

        return greeting + body

    async def _store_first_message(
        self,
        user_id: str,
        message: FirstConversationMessage,
    ) -> None:
        """Store as the first message in a new conversation thread.

        Args:
            user_id: The user's ID.
            message: The generated first conversation message.
        """
        try:
            conv = (
                self._db.table("conversations")
                .insert(
                    {
                        "user_id": user_id,
                        "metadata": {"type": "first_conversation"},
                    }
                )
                .execute()
            )

            if conv.data:
                self._db.table("messages").insert(
                    {
                        "conversation_id": conv.data[0]["id"],
                        "role": "assistant",
                        "content": message.content,
                        "metadata": {
                            "type": "first_conversation",
                            "memory_delta": message.memory_delta,
                            "facts_referenced": message.facts_referenced,
                            "confidence_level": message.confidence_level,
                        },
                    }
                ).execute()

                logger.info(
                    "First conversation stored",
                    extra={
                        "user_id": user_id,
                        "conversation_id": conv.data[0]["id"],
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to store first message: {e}")

    async def _record_episodic_event(
        self,
        user_id: str,
        message: FirstConversationMessage,
    ) -> None:
        """Record first conversation delivery to episodic memory.

        Args:
            user_id: The user's ID.
            message: The generated message with metadata.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="first_conversation_delivered",
                content=(
                    f"Delivered first conversation — highlighted "
                    f"{message.facts_referenced} insights "
                    f"(confidence: {message.confidence_level})"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "facts_referenced": message.facts_referenced,
                    "confidence_level": message.confidence_level,
                    "suggested_next_action": message.suggested_next_action,
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(f"Episodic record failed: {e}")

    # --- Data fetchers ---

    async def _get_top_facts(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """Get highest-confidence semantic facts for a user.

        Args:
            user_id: The user's ID.
            limit: Maximum number of facts to retrieve.

        Returns:
            List of fact dicts ordered by confidence descending.
        """
        result = (
            self._db.table("memory_semantic")
            .select("*")
            .eq("user_id", user_id)
            .order("confidence", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    async def _get_classification(self, user_id: str) -> dict[str, Any] | None:
        """Get company classification for the user's company.

        Args:
            user_id: The user's ID.

        Returns:
            Classification dict or None.
        """
        profile = (
            self._db.table("user_profiles")
            .select("company_id")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if not profile.data or not profile.data.get("company_id"):
            return None

        company = (
            self._db.table("companies")
            .select("settings")
            .eq("id", profile.data["company_id"])
            .maybe_single()
            .execute()
        )
        if not company.data:
            return None

        return company.data.get("settings", {}).get("classification")

    async def _get_critical_gaps(self, user_id: str) -> list[dict[str, Any]]:
        """Get critical and high-priority knowledge gaps.

        Args:
            user_id: The user's ID.

        Returns:
            List of gap dicts with task and metadata.
        """
        result = (
            self._db.table("prospective_memories")
            .select("task, metadata")
            .eq("user_id", user_id)
            .execute()
        )
        gaps = [
            r
            for r in (result.data or [])
            if r.get("metadata", {}).get("type") == "knowledge_gap"
            and r.get("metadata", {}).get("priority") in ("critical", "high")
        ]
        return gaps[:5]

    async def _get_first_goal(self, user_id: str) -> dict[str, Any] | None:
        """Get the user's first goal from onboarding.

        Args:
            user_id: The user's ID.

        Returns:
            Goal dict with title and description, or None.
        """
        result = (
            self._db.table("goals")
            .select("title, description")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data

    async def _get_writing_style(self, user_id: str) -> dict[str, Any] | None:
        """Get Digital Twin writing style for tone calibration.

        Args:
            user_id: The user's ID.

        Returns:
            Writing style dict or None.
        """
        result = (
            self._db.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data.get("preferences", {}).get("digital_twin", {}).get("writing_style")
        return None

    async def _get_personality_calibration(self, user_id: str) -> dict[str, Any] | None:
        """Get personality calibration from Digital Twin for tone matching.

        Args:
            user_id: The user's ID.

        Returns:
            Personality calibration dict with tone_guidance, or None.
        """
        result = (
            self._db.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            return (
                result.data.get("preferences", {})
                .get("digital_twin", {})
                .get("personality_calibration")
            )
        return None

    async def _get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get the user's profile for personalization.

        Args:
            user_id: The user's ID.

        Returns:
            Profile dict or None.
        """
        result = (
            self._db.table("user_profiles").select("*").eq("id", user_id).maybe_single().execute()
        )
        return result.data
