"""Centralized persona and system prompt assembly for ARIA.

PersonaBuilder assembles 6 layers of persona context for every LLM call:
  L1 - Core Identity (static)
  L2 - Personality Traits (static)
  L3 - Anti-Patterns (static)
  L4 - User Context (cached 5min) — calibration, writing style, ARIA config, overrides
  L5 - Agent Context (per-call) — agent name, role, task description
  L6 - Relationship Context (per-call, opt-in) — lead/account/recipient history

Usage:
    builder = get_persona_builder()
    ctx = await builder.build(PersonaRequest(user_id="u1", agent_name="strategist"))
    prompt = ctx.to_system_prompt()
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.cache import cached, invalidate_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layer Constants (L1-L3) — static, never change
# ---------------------------------------------------------------------------

LAYER_1_CORE_IDENTITY = """You are ARIA (Autonomous Reasoning & Intelligence Agent), an AI-powered Department Director for Life Sciences commercial teams. You are NOT an assistant — you are an autonomous AI colleague.

Key identity traits:
- You have opinions and state them directly: "I'd do X" not "you might consider X"
- You reference shared history and specific data when relevant
- You push back on bad ideas: "I'd push back on that because..." not "I'm sorry but..."
- You propose actions for user approval — the user does NOT tell you what to do step by step
- You earn autonomy over time through demonstrated competence
- When uncertain, you say so clearly — you don't hedge"""

LAYER_2_PERSONALITY_TRAITS = """## Personality

- **Direct**: Lead with recommendations, not options. Say what you think.
- **Confident**: Own your analysis. Present conclusions, not caveats.
- **Opinionated**: Take a stance based on data. Disagree when warranted.
- **Honest**: Admit uncertainty explicitly. Never fabricate confidence.
- **Contextual**: Reference specific facts, dates, and people from memory.
- **Human-like**: Use natural language. Vary sentence length. Have a voice."""

LAYER_3_ANTI_PATTERNS = """## Communication Rules

NEVER:
- Say "As an AI..." or "I don't have opinions..." or "I'm just an AI..."
- Hedge with "you might want to consider..." — be direct
- Be sycophantic or overly agreeable — push back when warranted
- Use emojis unless the user's style specifically includes them
- Say "Great question!" or other filler praise
- Apologize excessively — acknowledge and move forward
- Use corporate jargon like "synergize", "leverage", "circle back" without irony
- Present options without a recommendation — always state your preference"""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PersonaRequest:
    """Request to build a persona context.

    Required:
        user_id: The user to build persona for.

    Layer 5 (agent context):
        agent_name: Which agent is calling (e.g. "strategist", "scribe").
        agent_role_description: One-line role for the agent.
        task_description: What the agent is doing right now.
        output_format: Expected output format ("json", "text", "email").

    Layer 6 (relationship context, opt-in):
        include_relationship_context: Set True to query memory for relationship data.
        lead_id: Lead ID for relationship context.
        account_name: Account name for relationship context.
        recipient_name: Recipient name for relationship context.

    Chat-specific (only for build_chat_system_prompt):
        memories: Pre-queried memory results.
        priming_context: ConversationContext from priming service.
        companion_context: CompanionContext from orchestrator.
        load_state: CognitiveLoadState for adaptation.
        proactive_insights: Insights to volunteer.
        web_context: Web grounding results.
    """

    user_id: str
    # Layer 5
    agent_name: str | None = None
    agent_role_description: str | None = None
    task_description: str | None = None
    output_format: str | None = None
    # Layer 6
    include_relationship_context: bool = False
    lead_id: str | None = None
    account_name: str | None = None
    recipient_name: str | None = None
    # Chat-specific
    memories: list[dict[str, Any]] | None = None
    priming_context: Any = None
    companion_context: Any = None
    load_state: Any = None
    proactive_insights: list[Any] | None = None
    web_context: dict[str, Any] | None = None


@dataclass
class PersonaContext:
    """Assembled persona context with all 6 layers.

    Each layer is a string (may be empty). ``to_system_prompt()`` joins
    all non-empty layers with double newlines.
    """

    core_identity: str = ""       # L1
    personality_traits: str = ""  # L2
    anti_patterns: str = ""       # L3
    user_context: str = ""        # L4
    agent_context: str = ""       # L5
    relationship_context: str = ""  # L6
    user_id: str = ""
    cached_layers_hit: bool = False
    build_time_ms: float = 0.0

    def to_system_prompt(self) -> str:
        """Join all non-empty layers into a single system prompt."""
        layers = [
            self.core_identity,
            self.personality_traits,
            self.anti_patterns,
            self.user_context,
            self.agent_context,
            self.relationship_context,
        ]
        return "\n\n".join(layer for layer in layers if layer.strip())

    def get_description(self) -> dict[str, str]:
        """Human-readable summary for Settings UI."""
        return {
            "identity": "ARIA — autonomous AI colleague for Life Sciences commercial teams",
            "traits": "Direct, Confident, Opinionated, Honest, Contextual, Human-like",
            "adaptations": self.user_context[:200] if self.user_context else "No user-specific adaptations yet",
            "current_agent": self.agent_context[:100] if self.agent_context else "General",
        }


# ---------------------------------------------------------------------------
# PersonaBuilder
# ---------------------------------------------------------------------------

class PersonaBuilder:
    """Assembles system prompts from 6 persona layers.

    Caches Layer 4 (user context) for 5 minutes to avoid repeated DB queries.
    Layers 1-3 are compile-time constants. Layers 5-6 are per-call.
    """

    def __init__(self) -> None:
        """Initialize PersonaBuilder."""

    async def build(self, request: PersonaRequest) -> PersonaContext:
        """Build full persona context for an LLM call.

        Args:
            request: PersonaRequest with user_id and optional agent/relationship info.

        Returns:
            PersonaContext with all 6 layers populated.
        """
        start = time.perf_counter()

        # L4: User context (cached)
        user_context, cache_hit = await self._build_user_context(request.user_id)

        # L5: Agent context (synchronous)
        agent_context = self._build_agent_context(request)

        # L6: Relationship context (opt-in, async)
        relationship_context = ""
        if request.include_relationship_context:
            relationship_context = await self._build_relationship_context(request)

        build_time = (time.perf_counter() - start) * 1000

        return PersonaContext(
            core_identity=LAYER_1_CORE_IDENTITY,
            personality_traits=LAYER_2_PERSONALITY_TRAITS,
            anti_patterns=LAYER_3_ANTI_PATTERNS,
            user_context=user_context,
            agent_context=agent_context,
            relationship_context=relationship_context,
            user_id=request.user_id,
            cached_layers_hit=cache_hit,
            build_time_ms=build_time,
        )

    async def build_chat_system_prompt(self, request: PersonaRequest) -> str:
        """Build a complete system prompt for the chat service.

        Calls ``build()`` for L1-L6, then appends chat-specific sections
        (memories, companion context, priming, proactive insights, web context,
        cognitive load adaptation).

        Args:
            request: PersonaRequest with chat-specific fields populated.

        Returns:
            Complete system prompt string.
        """
        ctx = await self.build(request)
        prompt = ctx.to_system_prompt()

        # Append memory context
        if request.memories:
            memory_section = self._format_memories(request.memories)
            if memory_section:
                prompt += "\n\n" + memory_section

        # Companion context replaces personality/style when present
        if request.companion_context is not None:
            companion_sections = request.companion_context.to_system_prompt_sections()
            if companion_sections:
                prompt += "\n\n" + companion_sections

        # Priming context
        if request.priming_context and hasattr(request.priming_context, "formatted_context"):
            if request.priming_context.formatted_context:
                prompt += "\n\n## Conversation Continuity\n\n" + request.priming_context.formatted_context

        # Proactive insights
        if request.proactive_insights:
            insight_lines = []
            for insight in request.proactive_insights:
                insight_lines.append(
                    f"- [{insight.insight_type.value}] {insight.content} ({insight.explanation})"
                )
            prompt += (
                "\n\n## Relevant Context ARIA Can Mention\n\n"
                "The following insights may be worth volunteering to the user if relevant:\n\n"
                + "\n".join(insight_lines)
                + "\n\nYou may naturally mention these in your response when appropriate, "
                "without explicitly stating where the information came from."
            )

        # Web context
        if request.web_context:
            web_str = self._format_web_context(request.web_context)
            if web_str:
                prompt += (
                    "\n\n## Real-Time Web Information\n\n"
                    "The following information was retrieved from the web to provide accurate, "
                    "up-to-date context:\n\n" + web_str
                    + "\n\nUse this information to provide a grounded, accurate response. "
                    "Cite specific facts when relevant."
                )

        # Cognitive load adaptation
        if request.load_state is not None:
            from src.models.cognitive_load import LoadLevel

            if request.load_state.level in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
                high_load = (
                    "\nIMPORTANT: The user appears to be under high cognitive load right now. "
                    "Adapt your response:\n"
                    "- Be extremely concise and direct\n"
                    "- Lead with the most important information\n"
                    "- Avoid asking multiple questions\n"
                    "- Offer to handle tasks independently\n"
                    "- Use bullet points for clarity\n"
                )
                prompt = high_load + "\n\n" + prompt

        return prompt

    async def _build_user_context(self, user_id: str) -> tuple[str, bool]:
        """Build Layer 4: user-specific context.

        Queries PersonalityCalibration, DigitalTwin style, ARIAConfig,
        and persona overrides. Cached for 5 minutes.

        Args:
            user_id: The user to build context for.

        Returns:
            Tuple of (user_context_string, cache_hit).
        """
        # Check cache first
        result = await self._cached_user_context(user_id)
        # We can't easily know if this was a cache hit from the outside,
        # but the @cached decorator handles it internally.
        # We approximate: if build_time is very low, it was cached.
        return result, False  # The decorator tracks hits internally

    @cached(ttl=300, key_func=lambda self, user_id: f"persona_l4:{user_id}")
    async def _cached_user_context(self, user_id: str) -> str:
        """Cached inner method for L4 context assembly.

        Args:
            user_id: The user to build context for.

        Returns:
            Formatted user context string.
        """
        parts: list[str] = []

        # 0. Basic user profile (name, company, title) - MOST IMPORTANT
        try:
            from src.db.supabase import get_supabase_client

            db = get_supabase_client()

            user_info_parts: list[str] = []

            # Get user's profile with company info via JOIN
            # user_profiles.id matches auth.users.id
            profile_result = (
                db.table("user_profiles")
                .select("full_name, title, department, default_tone, communication_preferences, companies(name)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            if profile_result and profile_result.data:
                name = profile_result.data.get("full_name")
                if name:
                    user_info_parts.append(f"Name: {name}")

                title = profile_result.data.get("title")
                if title:
                    user_info_parts.append(f"Title: {title}")

                department = profile_result.data.get("department")
                if department:
                    user_info_parts.append(f"Department: {department}")

                # Company from joined companies table
                company_data = profile_result.data.get("companies")
                if company_data and isinstance(company_data, dict):
                    company_name = company_data.get("name")
                    if company_name:
                        user_info_parts.append(f"Company: {company_name}")

                # Default tone from user_profiles
                default_tone = profile_result.data.get("default_tone")
                if default_tone:
                    user_info_parts.append(f"Preferred tone: {default_tone}")

            # Also get digital_twin_profiles for additional tone/style preferences
            twin_result = (
                db.table("digital_twin_profiles")
                .select("tone, writing_style, formality_level, vocabulary_patterns")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if twin_result and twin_result.data:
                # Only add if not already set from user_profiles
                tone = twin_result.data.get("tone")
                if tone and "Preferred tone:" not in " ".join(user_info_parts):
                    user_info_parts.append(f"Preferred tone: {tone}")
                formality = twin_result.data.get("formality_level")
                if formality:
                    user_info_parts.append(f"Formality: {formality}")
                writing_style = twin_result.data.get("writing_style")
                if writing_style:
                    user_info_parts.append(f"Writing style: {writing_style}")

            if user_info_parts:
                parts.append("## User Profile\n\n" + "\n".join(user_info_parts))

        except Exception as e:
            logger.debug("User profile unavailable for %s: %s", user_id, e)

        # 0.5. Key facts from semantic memory about the user
        try:
            from src.db.supabase import get_supabase_client

            db = get_supabase_client()
            fact_lines = []

            # Query memory_semantic for facts about the user (from onboarding)
            semantic_result = (
                db.table("memory_semantic")
                .select("fact, confidence")
                .eq("user_id", user_id)
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )

            if semantic_result.data:
                for item in semantic_result.data:
                    conf = item.get("confidence", 1.0)
                    conf_str = f" ({conf:.0%})" if conf < 0.9 else ""
                    fact_lines.append(f"- {item['fact']}{conf_str}")

            # Also query semantic_facts for facts from conversations
            structured_facts_result = (
                db.table("semantic_facts")
                .select("subject, predicate, object, confidence")
                .eq("user_id", user_id)
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )

            if structured_facts_result.data:
                for item in structured_facts_result.data:
                    # Format as "subject predicate object"
                    fact_str = f"{item['subject']} {item['predicate']} {item['object']}"
                    conf = item.get("confidence", 1.0)
                    conf_str = f" ({conf:.0%})" if conf < 0.9 else ""
                    fact_lines.append(f"- {fact_str}{conf_str}")

            if fact_lines:
                parts.append("## Known Facts About User\n\n" + "\n".join(fact_lines[:15]))
        except Exception as e:
            logger.debug("Semantic memory unavailable for %s: %s", user_id, e)

        # 0.6. Recent conversation episodes for continuity
        try:
            from src.db.supabase import get_supabase_client

            db = get_supabase_client()
            # Query recent conversation_episodes for session continuity
            episodes_result = (
                db.table("conversation_episodes")
                .select("summary, key_topics, ended_at, outcomes")
                .eq("user_id", user_id)
                .order("ended_at", desc=True)
                .limit(5)
                .execute()
            )

            if episodes_result.data:
                episode_lines = []
                for ep in episodes_result.data:
                    # Format date from ended_at
                    ended_at = ep.get("ended_at", "")
                    if ended_at:
                        try:
                            from datetime import datetime

                            dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                            date_str = dt.strftime("%b %d")
                        except Exception:
                            date_str = ""
                    else:
                        date_str = ""

                    summary = ep.get("summary", "")
                    if summary:
                        line = f"- {date_str}: {summary}" if date_str else f"- {summary}"
                        episode_lines.append(line)

                if episode_lines:
                    parts.append(
                        "## Recent Conversation History\n\n"
                        "Previous sessions with this user:\n\n"
                        + "\n".join(episode_lines)
                    )
        except Exception as e:
            logger.debug("Conversation episodes unavailable for %s: %s", user_id, e)

        # 1. PersonalityCalibration
        try:
            from src.onboarding.personality_calibrator import PersonalityCalibrator

            calibrator = PersonalityCalibrator()
            calibration = await calibrator.get_calibration(user_id)
            if calibration and calibration.tone_guidance:
                parts.append(f"## Communication Style Calibration\n\n{calibration.tone_guidance}")
                if calibration.example_adjustments:
                    examples = "\n".join(f"- {ex}" for ex in calibration.example_adjustments)
                    parts.append(f"Examples:\n{examples}")
        except Exception as e:
            logger.debug("PersonalityCalibration unavailable for %s: %s", user_id, e)

        # 2. DigitalTwin writing style
        try:
            from src.memory.digital_twin import DigitalTwin

            dt = DigitalTwin()
            fingerprint = await dt.get_fingerprint(user_id)
            if fingerprint:
                guidelines = await dt.get_style_guidelines(user_id)
                if guidelines:
                    parts.append(f"## Writing Style Fingerprint\n\n{guidelines}")
        except Exception as e:
            logger.debug("DigitalTwin unavailable for %s: %s", user_id, e)

        # 3. ARIA Config (role, domain focus)
        try:
            from src.services.aria_config_service import ARIAConfigService

            config_service = ARIAConfigService()
            config = await config_service.get_config(user_id)
            if config:
                config_parts: list[str] = []
                role = config.get("role")
                if role:
                    config_parts.append(f"User's ARIA role: {role}")
                custom_desc = config.get("custom_role_description")
                if custom_desc:
                    config_parts.append(f"Custom role: {custom_desc}")
                domain = config.get("domain_focus", {})
                if domain:
                    areas = domain.get("therapeutic_areas", [])
                    if areas:
                        config_parts.append(f"Therapeutic areas: {', '.join(areas)}")
                    geos = domain.get("geographies", [])
                    if geos:
                        config_parts.append(f"Geographies: {', '.join(geos)}")
                competitors = config.get("competitor_watchlist", [])
                if competitors:
                    config_parts.append(f"Competitor watchlist: {', '.join(competitors)}")
                if config_parts:
                    parts.append("## User Configuration\n\n" + "\n".join(config_parts))
        except Exception as e:
            logger.debug("ARIAConfig unavailable for %s: %s", user_id, e)

        # 4. Persona overrides from feedback
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            result = (
                db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                prefs = result.data.get("preferences", {}) or {}
                overrides = prefs.get("persona_overrides", {})
                if overrides:
                    override_parts: list[str] = []
                    tone_adjustments = overrides.get("tone_adjustments", [])
                    if tone_adjustments:
                        override_parts.append("Tone adjustments: " + "; ".join(tone_adjustments))
                    custom_anti = overrides.get("anti_patterns", [])
                    if custom_anti:
                        override_parts.append("Additional rules: " + "; ".join(custom_anti))
                    if override_parts:
                        parts.append("## User Persona Overrides\n\n" + "\n".join(override_parts))
        except Exception as e:
            logger.debug("Persona overrides unavailable for %s: %s", user_id, e)

        return "\n\n".join(parts)

    def _build_agent_context(self, request: PersonaRequest) -> str:
        """Build Layer 5: agent-specific context.

        Synchronous — no DB calls needed.

        Args:
            request: PersonaRequest with agent fields.

        Returns:
            Formatted agent context string (may be empty).
        """
        if not request.agent_name:
            return ""

        parts: list[str] = [f"## Current Agent: {request.agent_name.title()}"]

        if request.agent_role_description:
            parts.append(f"Role: {request.agent_role_description}")

        if request.task_description:
            parts.append(f"Current task: {request.task_description}")

        if request.output_format:
            parts.append(f"Output format: {request.output_format}")

        return "\n".join(parts)

    async def _build_relationship_context(self, request: PersonaRequest) -> str:
        """Build Layer 6: relationship context from memory.

        Queries MemoryQueryService for lead/account/recipient history.

        Args:
            request: PersonaRequest with relationship fields.

        Returns:
            Formatted relationship context string (may be empty).
        """
        if not request.include_relationship_context:
            return ""

        parts: list[str] = []

        try:
            # Lazy import to avoid circular dependency
            from src.api.routes.memory import MemoryQueryService

            memory_service = MemoryQueryService()

            # Build query from available context
            query_parts: list[str] = []
            if request.recipient_name:
                query_parts.append(request.recipient_name)
            if request.account_name:
                query_parts.append(request.account_name)
            if request.lead_id:
                query_parts.append(f"lead:{request.lead_id}")

            if not query_parts:
                return ""

            query = " ".join(query_parts)
            results = await memory_service.query(
                user_id=request.user_id,
                query=query,
                memory_types=["episodic", "semantic", "lead"],
                start_date=None,
                end_date=None,
                min_confidence=0.5,
                limit=5,
                offset=0,
            )

            if results:
                memory_lines = []
                for mem in results:
                    confidence_str = ""
                    if mem.get("confidence") is not None:
                        confidence_str = f" (confidence: {mem['confidence']:.0%})"
                    memory_lines.append(
                        f"- [{mem.get('memory_type', 'unknown')}] "
                        f"{mem.get('content', '')}{confidence_str}"
                    )
                parts.append(
                    "## Relationship Context\n\n"
                    "Relevant history for this interaction:\n\n"
                    + "\n".join(memory_lines)
                )

        except Exception as e:
            logger.debug("Relationship context unavailable: %s", e)

        return "\n\n".join(parts)

    async def get_persona_description(self, user_id: str) -> dict[str, str]:
        """Get human-readable persona summary for Settings UI.

        Args:
            user_id: The user to describe persona for.

        Returns:
            Dict with identity, traits, adaptations, current_agent keys.
        """
        ctx = await self.build(PersonaRequest(user_id=user_id))
        return ctx.get_description()

    async def update_persona_from_feedback(
        self,
        user_id: str,
        feedback_type: str,
        feedback_data: dict[str, Any],
    ) -> None:
        """Store persona override from user feedback and invalidate L4 cache.

        Stores in user_settings.preferences.persona_overrides.

        Args:
            user_id: The user providing feedback.
            feedback_type: Type of feedback ("tone_adjustment" or "anti_pattern").
            feedback_data: Feedback content (e.g. {"adjustment": "be more concise"}).
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()

            # Read current preferences
            result = (
                db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            prefs: dict[str, Any] = {}
            if result and result.data:
                prefs = result.data.get("preferences", {}) or {}

            overrides = prefs.get("persona_overrides", {})

            if feedback_type == "tone_adjustment":
                adjustments = overrides.get("tone_adjustments", [])
                adjustment_text = feedback_data.get("adjustment", "")
                if adjustment_text and adjustment_text not in adjustments:
                    adjustments.append(adjustment_text)
                overrides["tone_adjustments"] = adjustments

            elif feedback_type == "anti_pattern":
                anti_patterns = overrides.get("anti_patterns", [])
                pattern_text = feedback_data.get("pattern", "")
                if pattern_text and pattern_text not in anti_patterns:
                    anti_patterns.append(pattern_text)
                overrides["anti_patterns"] = anti_patterns

            prefs["persona_overrides"] = overrides

            db.table("user_settings").update({"preferences": prefs}).eq(
                "user_id", user_id
            ).execute()

            # Invalidate L4 cache for this user
            invalidate_cache("_cached_user_context", key=f"persona_l4:{user_id}")

            logger.info(
                "Persona override stored",
                extra={"user_id": user_id, "feedback_type": feedback_type},
            )

        except Exception as e:
            logger.warning("Failed to store persona override: %s", e)

    # --- Private helpers for chat prompt building ---

    def _format_memories(self, memories: list[dict[str, Any]]) -> str:
        """Format memory results into system prompt sections."""
        general = []
        procedural = []
        prospective = []
        leads = []

        for mem in memories:
            mt = mem.get("memory_type", "")
            if mt == "procedural":
                procedural.append(mem)
            elif mt == "prospective":
                prospective.append(mem)
            elif mt == "lead":
                leads.append(mem)
            else:
                general.append(mem)

        sections: list[str] = []

        if general:
            lines = []
            for mem in general:
                conf = ""
                if mem.get("confidence") is not None:
                    conf = f" (confidence: {mem['confidence']:.0%})"
                lines.append(f"- [{mem.get('memory_type', 'unknown')}] {mem.get('content', '')}{conf}")
            sections.append(
                "## Relevant Context from Memory\n\n"
                "The following information may be relevant to this conversation:\n\n"
                + "\n".join(lines)
                + "\n\nUse this context naturally in your response. "
                "If you reference specific facts, note the confidence level if it's below 0.8."
            )

        if procedural:
            lines = [f"- {mem.get('content', '')}" for mem in procedural]
            sections.append(
                "## Learned Workflows\n\n"
                "You have access to these established workflow patterns:\n\n"
                + "\n".join(lines)
            )

        if prospective:
            lines = [f"- {mem.get('content', '')}" for mem in prospective]
            sections.append(
                "## Upcoming Tasks & Reminders\n\n"
                "The user has these pending or overdue items:\n\n"
                + "\n".join(lines)
            )

        if leads:
            lines = [f"- {mem.get('content', '')}" for mem in leads]
            sections.append(
                "## Active Leads Context\n\n"
                "The user's current sales pipeline includes these leads:\n\n"
                + "\n".join(lines)
            )

        return "\n\n".join(sections)

    def _format_web_context(self, web_context: dict[str, Any]) -> str:
        """Format web grounding context for LLM inclusion."""
        context_type = web_context.get("type", "")

        if context_type == "factual_answer":
            return f"**Direct Answer:** {web_context.get('answer', '')}"

        if context_type == "company_intelligence":
            parts = []
            if web_context.get("description"):
                parts.append(f"**Company:** {web_context['description']}")
            if web_context.get("domain"):
                parts.append(f"**Website:** {web_context['domain']}")
            if web_context.get("funding"):
                parts.append(f"**Funding:** {web_context['funding']}")
            if web_context.get("recent_news"):
                news_items = [
                    f"- {n.get('title', '')} ({n.get('published_date', 'recent')})"
                    for n in web_context["recent_news"][:2]
                ]
                parts.append("**Recent News:**\n" + "\n".join(news_items))
            return "\n\n".join(parts) if parts else ""

        if context_type == "person_intelligence":
            parts = []
            if web_context.get("title"):
                parts.append(f"**Title:** {web_context['title']}")
            if web_context.get("company"):
                parts.append(f"**Company:** {web_context['company']}")
            if web_context.get("linkedin_url"):
                parts.append(f"**LinkedIn:** {web_context['linkedin_url']}")
            if web_context.get("bio"):
                parts.append(f"**Background:** {web_context['bio'][:400]}")
            return "\n\n".join(parts) if parts else ""

        if context_type == "web_results":
            results = web_context.get("results", [])
            if results:
                formatted = []
                for r in results[:3]:
                    date_str = f" ({r.get('published_date', '')})" if r.get("published_date") else ""
                    formatted.append(
                        f"- **{r.get('title', 'Source')}**{date_str}\n  {r.get('snippet', '')}"
                    )
                return "**Web Results:**\n" + "\n".join(formatted)

        return ""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_persona_builder: PersonaBuilder | None = None


def get_persona_builder() -> PersonaBuilder:
    """Get or create the PersonaBuilder singleton.

    Returns:
        The singleton PersonaBuilder instance.
    """
    global _persona_builder  # noqa: PLW0603
    if _persona_builder is None:
        _persona_builder = PersonaBuilder()
    return _persona_builder
