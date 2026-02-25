"""ARIA Persona Manager for Tavus Conversational Video.

This module manages the ARIA persona configuration for Tavus, including:
- Phoenix-4 replica with lifelike video generation
- Raven-1 perception for user emotion/engagement detection
- Sparrow-1 turn detection for natural conversation flow
- Custom Claude LLM integration
- Cartesia TTS for expressive speech
- Life sciences domain guardrails

IMPORTANT: The core ARIA identity is defined in src/core/persona.py (LAYER_1, LAYER_2, LAYER_3).
This file only defines Tavus-specific configuration (tools, guardrails, perception layers).
The persona context is built dynamically via TavusClient._build_full_persona_context().
"""

import logging
from datetime import date
from enum import Enum
from typing import Any

from src.core.config import settings
from src.core.persona import (
    LAYER_1_CORE_IDENTITY,
    LAYER_2_PERSONALITY_TRAITS,
    LAYER_3_ANTI_PATTERNS,
)
from src.db.supabase import SupabaseClient
from src.integrations.tavus import TavusClient
from src.integrations.tavus_tools import ARIA_VIDEO_TOOLS

logger = logging.getLogger(__name__)

ARIA_PERSONA_NAME = "ARIA - Life Sciences AI Director"


class SessionType(str, Enum):
    """Types of ARIA conversation sessions."""

    CHAT = "chat"
    BRIEFING = "briefing"
    DEBRIEF = "debrief"
    CONSULTATION = "consultation"


# ARIA System Prompt for Tavus - references canonical identity
# This combines the canonical L1-L3 layers with Tavus-specific tool definitions
# The actual persona context is built dynamically in TavusClient._build_full_persona_context()
ARIA_SYSTEM_PROMPT = f"""{LAYER_1_CORE_IDENTITY}

{LAYER_2_PERSONALITY_TRAITS}

{LAYER_3_ANTI_PATTERNS}

## Your Capabilities
- Research companies, contacts, and market signals
- Generate battle cards and competitive intelligence
- Draft emails with per-recipient writing profiles
- Track goals with milestones and agent orchestration
- Provide daily briefings with calendar, leads, signals, and email drafts
- Debrief after meetings to extract insights and action items

## Communication Style
- Speak conversationally, as a colleague would
- Use natural speech patterns with brief pauses for emphasis
- Avoid markdown, bullet points, or numbered lists in spoken responses
- Reference specific data: "Lonza's stock is up 12% this quarter" not "a competitor is performing well"
- Acknowledge uncertainty: "Based on what I've seen..." or "The latest data suggests..."
- Keep responses concise but complete

## Behavioral Rules
- NEVER provide medical, clinical, or drug dosing advice
- NEVER share competitor pricing or proprietary customer data
- Redirect clinical questions to medical affairs teams
- Stay in the commercial/sales lane
- When uncertain about sensitive topics, explain your limitations
- Always propose, never assume user agreement

## Your Tools
You have live tools you can call during this conversation. When the user asks you to do something, USE the appropriate tool — don't just describe what you could do.

Available tools:
- search_companies: Find companies by industry, funding, location
- search_leads: Discover leads matching ICP criteria
- get_lead_details: Look up a specific lead in the pipeline
- get_battle_card: Get competitive intelligence on a competitor
- search_pubmed: Search scientific publications
- search_clinical_trials: Search ClinicalTrials.gov
- get_pipeline_summary: Get pipeline stats and health metrics
- get_meeting_brief: Get prep material for upcoming meetings
- draft_email: Draft a personalised email
- schedule_meeting: Book a meeting on the calendar
- get_market_signals: Get recent market intelligence and news
- add_lead_to_pipeline: Add a company to the pipeline

When you call a tool, briefly tell the user what you're doing: "Let me search for that..." Then share the results conversationally. Don't read raw data — summarise and highlight what matters.

## What You Never Do
- Never open with "Absolutely!", "Sure!", "Of course!", "Great question!", "I'd be happy to help!"
- Never end responses with "Would you like me to...?" or "What would you like to...?" — state what you think should happen next
- Never say "As an AI..." or "I don't have opinions..."
- Never use emojis
- Never present options without stating which one you'd pick"""

# Life sciences domain hotwords for STT accuracy
ARIA_STT_HOTWORDS = " ".join(
    [
        # Company names
        "ARIA",
        "LuminOne",
        "Cytiva",
        "Repligen",
        "Danaher",
        "Thermo Fisher",
        "Merck",
        "Pfizer",
        "Moderna",
        "Lonza",
        "Catalent",
        "Samsung Biologics",
        "WuXi AppTec",
        "AGC Biologics",
        "FUJIFILM Diosynth",
        "AbbVie",
        "Amgen",
        "Bristol-Myers",
        "Eli Lilly",
        # Domain terms
        "biotech",
        "pharma",
        "CDMO",
        "bioreactor",
        "chromatography",
        "cell culture",
        "upstream",
        "downstream",
        "fill-finish",
        "lyophilization",
        "single-use",
        "biosimilar",
        "monoclonal",
        "antibody",
        "vaccine",
        "gene therapy",
        "cell therapy",
        "mRNA",
        "plasmid",
        "viral vector",
        "expi293",
        "expiCHO",
        "PER.C6",
        # Regulatory
        "FDA",
        "EMA",
        "BLA",
        "NDA",
        "IND",
        "GMP",
        "GLP",
        "GCP",
        "cGMP",
        "validation",
        "qualification",
        "regulatory",
        # Commercial
        "pipeline",
        "forecast",
        "quota",
        "SOW",
        "MSA",
        "RFP",
        "RFI",
        "stakeholder",
        "champion",
        "decision-maker",
        "influencer",
    ]
)

# ARIA persona layers configuration with exact model versions
ARIA_PERSONA_LAYERS: dict[str, Any] = {
    "perception": {
        "perception_model": "raven-1",
        "visual_awareness_queries": [
            "Is the user looking at the screen or away?",
            "Is the user taking notes or typing?",
            "Does the user appear engaged or distracted?",
            "Is the user smiling, frowning, or neutral?",
        ],
        "perception_analysis_queries": [
            "Summarize the user's emotional state throughout the conversation",
            "Identify moments of confusion or hesitation",
            "Note any moments of strong positive engagement",
            "Detect signs of agreement or disagreement",
        ],
        "perception_tool_prompt": (
            "You have two perception tools available. "
            "When you detect that the user appears confused, hesitant, or is struggling "
            "to understand, call adapt_to_confusion with the observed indicator and the "
            "current topic as a snake_case label (e.g. 'pipeline_review', 'battle_card'). "
            "When you detect that the user is disengaged, distracted, or losing interest, "
            "call note_engagement_drop with the type of disengagement and the current "
            "topic as a snake_case label. Always classify the current topic before calling "
            "either tool."
        ),
        "perception_tools": [
            {
                "type": "function",
                "function": {
                    "name": "adapt_to_confusion",
                    "description": (
                        "Called when the user shows signs of confusion or hesitation. "
                        "ARIA will adapt its explanation style, simplify language, or "
                        "offer to re-explain the current topic."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "confusion_indicator": {
                                "type": "string",
                                "description": (
                                    "What indicates the user is confused, e.g. "
                                    "'furrowed brow', 'repeated question', 'long pause'"
                                ),
                            },
                            "topic": {
                                "type": "string",
                                "description": (
                                    "The current topic as a snake_case label, e.g. "
                                    "'pipeline_review', 'battle_card', 'goal_planning'"
                                ),
                            },
                        },
                        "required": ["confusion_indicator", "topic"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "note_engagement_drop",
                    "description": (
                        "Called when the user shows signs of disengagement or distraction. "
                        "ARIA will adjust pacing, switch topics, or re-engage the user."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "disengagement_type": {
                                "type": "string",
                                "description": (
                                    "The type of disengagement observed, e.g. "
                                    "'looking_away', 'fidgeting', 'monotone_responses'"
                                ),
                            },
                            "topic": {
                                "type": "string",
                                "description": (
                                    "The current topic as a snake_case label, e.g. "
                                    "'pipeline_review', 'battle_card', 'goal_planning'"
                                ),
                            },
                        },
                        "required": ["disengagement_type", "topic"],
                    },
                },
            },
        ],
    },
    "conversational_flow": {
        "turn_detection_model": "sparrow-1",
        "turn_taking_patience": "medium",
        "replica_interruptibility": "low",
    },
    "stt": {
        "hotwords": ARIA_STT_HOTWORDS,
    },
    "llm": {
        "model": "claude-sonnet-4-5-20250929",
        "base_url": "https://api.anthropic.com/v1",
        "api_key": "<ANTHROPIC_API_KEY>",
        "speculative_inference": True,
        "extra_body": {"temperature": 0.7, "top_p": 0.9},
        "tools": ARIA_VIDEO_TOOLS,
    },
    "tts": {
        "tts_engine": "cartesia",
        "tts_emotion_control": True,
        "voice_settings": {"speed": 0.5, "emotion": ["positivity:high", "curiosity"]},
    },
}

# Life sciences guardrails configuration
ARIA_GUARDRAILS = [
    {
        "type": "topic",
        "action": "block",
        "topics": [
            "medical advice",
            "drug dosing",
            "clinical recommendations",
            "prescribing medication",
            "treatment protocols",
        ],
        "response": "That's outside my lane — medical and clinical advice needs to go through your medical affairs team. My focus is the commercial side.",
    },
    {
        "type": "topic",
        "action": "block",
        "topics": [
            "competitor pricing",
            "proprietary customer data",
            "confidential contracts",
            "insider information",
        ],
        "response": "I don't have access to competitor pricing or proprietary customer data. For competitive intelligence, I work from publicly available information and market positioning analysis.",
    },
    {
        "type": "topic",
        "action": "block",
        "topics": [
            "legal advice",
            "contract interpretation",
            "regulatory compliance advice",
        ],
        "response": "I'm not able to provide legal or regulatory compliance advice. Please consult with your legal or regulatory affairs team for guidance on these matters.",
    },
    {
        "type": "redirect",
        "action": "redirect",
        "triggers": [
            "clinical trial results",
            "patient outcomes",
            "adverse events",
            "efficacy data",
        ],
        "response": "Clinical data and patient outcomes sit with your medical affairs team. On my end, I can work with the commercial implications of public trial results.",
    },
]


class ARIAPersonaManager:
    """Manager for ARIA persona in Tavus.

    Handles persona creation, guardrails configuration, and dynamic
    context building for different session types.
    """

    def __init__(self) -> None:
        """Initialize the ARIA persona manager."""
        self._tavus_client: TavusClient | None = None
        self._profile_service: Any = None
        self._briefing_service: Any = None
        self._goal_service: Any = None
        self._db: Any = None

    @property
    def tavus_client(self) -> TavusClient:
        """Get Tavus client lazily.

        Returns:
            TavusClient instance.
        """
        if self._tavus_client is None:
            self._tavus_client = TavusClient()
        return self._tavus_client

    @property
    def profile_service(self) -> Any:
        """Get ProfileService lazily.

        Returns:
            ProfileService instance.
        """
        if self._profile_service is None:
            from src.services.profile_service import ProfileService

            self._profile_service = ProfileService()
        return self._profile_service

    @property
    def briefing_service(self) -> Any:
        """Get BriefingService lazily.

        Returns:
            BriefingService instance.
        """
        if self._briefing_service is None:
            from src.services.briefing import BriefingService

            self._briefing_service = BriefingService()
        return self._briefing_service

    @property
    def goal_service(self) -> Any:
        """Get GoalService lazily.

        Returns:
            GoalService instance.
        """
        if self._goal_service is None:
            from src.services.goal_service import GoalService

            self._goal_service = GoalService()
        return self._goal_service

    @property
    def db(self) -> Any:
        """Get Supabase client lazily.

        Returns:
            Supabase client instance.
        """
        if self._db is None:
            self._db = SupabaseClient.get_client()
        return self._db

    async def create_aria_guardrails(self) -> dict[str, Any]:
        """Create ARIA guardrails in Tavus.

        Returns:
            Dict with guardrails_id and other details.

        Raises:
            TavusAPIError: If API returns an error.
            TavusConnectionError: If unable to connect.
        """
        logger.info("Creating ARIA guardrails in Tavus")
        result = await self.tavus_client.create_guardrails(ARIA_GUARDRAILS)
        guardrails_id = result.get("guardrails_id")
        logger.info("ARIA guardrails created", extra={"guardrails_id": guardrails_id})
        return result

    async def create_aria_persona(
        self,
        guardrails_id: str,
        replica_id: str,
    ) -> dict[str, Any]:
        """Create ARIA persona with layers configuration.

        Args:
            guardrails_id: ID of the guardrails to attach.
            replica_id: ID of the Phoenix-4 replica to use.

        Returns:
            Dict with persona_id and other details.

        Raises:
            TavusAPIError: If API returns an error.
            TavusConnectionError: If unable to connect.
        """
        logger.info("Creating ARIA persona in Tavus")

        # Build layers with actual API key
        layers = dict(ARIA_PERSONA_LAYERS)
        api_key = settings.ANTHROPIC_API_KEY
        if api_key:
            layers["llm"]["api_key"] = api_key.get_secret_value()

        result = await self.tavus_client.create_persona(
            persona_name=ARIA_PERSONA_NAME,
            system_prompt=ARIA_SYSTEM_PROMPT,
            context="You are ARIA, having a conversation with a life sciences commercial professional.",
            layers=layers,
            default_replica_id=replica_id,
            guardrails_id=guardrails_id,
        )

        persona_id = result.get("persona_id")
        logger.info(
            "ARIA persona created",
            extra={"persona_id": persona_id, "guardrails_id": guardrails_id},
        )
        return result

    async def get_or_create_persona(
        self,
        replica_id: str | None = None,
        force_recreate: bool = False,
    ) -> dict[str, Any]:
        """Get existing ARIA persona or create new one.

        Idempotent - checks for existing persona by name before creating.

        Args:
            replica_id: ID of the replica to use (defaults to configured).
            force_recreate: If True, delete existing and recreate.

        Returns:
            Dict with persona_id, guardrails_id, and created flag.

        Raises:
            ValueError: If replica_id is not provided or configured.
            TavusAPIError: If API returns an error.
            TavusConnectionError: If unable to connect.
        """
        replica = replica_id or settings.TAVUS_REPLICA_ID
        if not replica:
            raise ValueError(
                "Replica ID is required. Set TAVUS_REPLICA_ID in environment or pass replica_id."
            )

        # Check for existing persona
        existing_personas = await self.tavus_client.list_personas()
        for persona in existing_personas:
            if persona.get("persona_name") == ARIA_PERSONA_NAME:
                if force_recreate:
                    logger.info(
                        "Deleting existing ARIA persona for recreation",
                        extra={"persona_id": persona.get("persona_id")},
                    )
                    await self.tavus_client.delete_persona(persona["persona_id"])
                    break
                else:
                    logger.info(
                        "Found existing ARIA persona",
                        extra={"persona_id": persona.get("persona_id")},
                    )
                    return {
                        "persona_id": persona["persona_id"],
                        "guardrails_id": persona.get("guardrails_id"),
                        "created": False,
                    }

        # Create new guardrails
        guardrails_result = await self.create_aria_guardrails()
        guardrails_id = guardrails_result["guardrails_id"]

        # Create new persona
        persona_result = await self.create_aria_persona(guardrails_id, replica)
        persona_id = persona_result["persona_id"]

        return {
            "persona_id": persona_id,
            "guardrails_id": guardrails_id,
            "created": True,
        }

    async def build_context(
        self,
        user_id: str,
        session_type: SessionType,
        additional_context: dict[str, Any] | None = None,
    ) -> str:
        """Build dynamic context for a conversation session.

        Args:
            user_id: The user's UUID.
            session_type: Type of session (chat, briefing, debrief, consultation).
            additional_context: Optional additional context to include.

        Returns:
            Formatted context string for the Tavus conversation.
        """
        context_parts: list[str] = []

        # Always include user context
        user_context = await self._get_user_context(user_id)
        if user_context:
            context_parts.append(f"## User Profile\n{user_context}")

        # Add session-type-specific context
        if session_type == SessionType.BRIEFING:
            briefing_context = await self._get_briefing_context(user_id)
            if briefing_context:
                context_parts.append(f"## Today's Briefing\n{briefing_context}")

        elif session_type == SessionType.DEBRIEF:
            debrief_context = await self._get_debrief_context(user_id, additional_context or {})
            if debrief_context:
                context_parts.append(f"## Meeting Debrief\n{debrief_context}")

        elif session_type == SessionType.CONSULTATION:
            consultation_context = await self._get_consultation_context(
                user_id, additional_context or {}
            )
            if consultation_context:
                context_parts.append(f"## Goal Consultation\n{consultation_context}")

        else:  # CHAT
            chat_context = await self._get_chat_context(user_id)
            if chat_context:
                context_parts.append(f"## Current Context\n{chat_context}")

        # Add recent conversation context
        recent_context = await self._get_recent_conversation_context(user_id)
        if recent_context:
            context_parts.append(f"## Recent Conversations\n{recent_context}")

        # Add any additional context
        if additional_context:
            extra = additional_context.get("extra_context")
            if extra:
                context_parts.append(f"## Additional Context\n{extra}")

        return "\n\n".join(context_parts) if context_parts else ""

    async def _get_user_context(self, user_id: str) -> str | None:
        """Get user profile context.

        Args:
            user_id: The user's UUID.

        Returns:
            Formatted user context or None on error.
        """
        try:
            profile = await self.profile_service.get_full_profile(user_id)
            user = profile.get("user", {})
            company = profile.get("company", {})

            parts = []
            if user.get("full_name"):
                parts.append(f"Name: {user['full_name']}")
            if user.get("title"):
                parts.append(f"Title: {user['title']}")
            if company.get("name"):
                parts.append(f"Company: {company['name']}")
            if company.get("industry"):
                parts.append(f"Industry: {company['industry']}")

            return "\n".join(parts) if parts else None

        except Exception as e:
            logger.warning(
                "Failed to get user context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_briefing_context(self, user_id: str) -> str | None:
        """Get daily briefing context.

        Args:
            user_id: The user's UUID.

        Returns:
            Formatted briefing context or None on error.
        """
        try:
            briefing = await self.briefing_service.get_or_generate_briefing(user_id, date.today())

            parts = []

            # Summary
            summary = briefing.get("summary")
            if summary:
                parts.append(f"Summary: {summary}")

            # Calendar
            calendar = briefing.get("calendar", {})
            meeting_count = calendar.get("meeting_count", 0)
            if meeting_count > 0:
                parts.append(f"Meetings today: {meeting_count}")
                for meeting in calendar.get("key_meetings", [])[:3]:
                    time = meeting.get("time", "")
                    title = meeting.get("title", "Meeting")
                    parts.append(f"  - {time}: {title}")

            # Hot leads
            leads = briefing.get("leads", {})
            hot_leads = leads.get("hot_leads", [])
            if hot_leads:
                parts.append(f"Hot leads: {len(hot_leads)}")
                for lead in hot_leads[:3]:
                    name = lead.get("company_name", "Unknown")
                    score = lead.get("health_score", 0)
                    parts.append(f"  - {name} (health: {score})")

            # Email drafts
            email = briefing.get("email_summary", {})
            drafts = email.get("drafts_waiting", 0)
            if drafts > 0:
                high_conf = email.get("drafts_high_confidence", 0)
                parts.append(f"Email drafts ready: {drafts} ({high_conf} high confidence)")

            # Signals
            signals = briefing.get("signals", {})
            news = len(signals.get("company_news", []))
            intel = len(signals.get("competitive_intel", []))
            if news + intel > 0:
                parts.append(f"Market signals: {news} news, {intel} competitive intel")

            return "\n".join(parts) if parts else None

        except Exception as e:
            logger.warning(
                "Failed to get briefing context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_debrief_context(
        self,
        user_id: str,
        additional_context: dict[str, Any],
    ) -> str | None:
        """Get meeting debrief context.

        Args:
            user_id: The user's UUID.
            additional_context: Dict with meeting_id, attendees, etc.

        Returns:
            Formatted debrief context or None on error.
        """
        try:
            parts = []

            # Meeting details from additional context
            meeting_title = additional_context.get("meeting_title", "Meeting")
            parts.append(f"Meeting: {meeting_title}")

            attendees = additional_context.get("attendees", [])
            if attendees:
                parts.append(f"Attendees: {', '.join(attendees[:5])}")

            # Look up related lead memories
            if attendees:
                for attendee in attendees[:3]:
                    result = (
                        self.db.table("lead_memory_stakeholders")
                        .select("lead_memory_id, lead_memories(company_name)")
                        .eq("contact_email", attendee)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        lead = result.data[0]
                        lead_info = lead.get("lead_memories", {})
                        company = lead_info.get("company_name") if lead_info else None
                        if company:
                            parts.append(f"Related account: {company}")
                            break

            return "\n".join(parts) if len(parts) > 1 else None

        except Exception as e:
            logger.warning(
                "Failed to get debrief context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_consultation_context(
        self,
        user_id: str,
        additional_context: dict[str, Any],
    ) -> str | None:
        """Get goal consultation context.

        Args:
            user_id: The user's UUID.
            additional_context: Dict with goal_id.

        Returns:
            Formatted consultation context or None on error.
        """
        try:
            goal_id = additional_context.get("goal_id")
            if not goal_id:
                return None

            goal = await self.goal_service.get_goal_detail(user_id, goal_id)
            if not goal:
                return None

            parts = []

            title = goal.get("title", "Goal")
            goal_type = goal.get("goal_type", "general")
            status = goal.get("status", "unknown")
            progress = goal.get("progress", 0)

            parts.append(f"Goal: {title}")
            parts.append(f"Type: {goal_type}")
            parts.append(f"Status: {status}")
            parts.append(f"Progress: {progress}%")

            description = goal.get("description")
            if description:
                parts.append(f"Description: {description[:200]}")

            # Milestones
            milestones = goal.get("milestones", [])
            if milestones:
                complete = sum(1 for m in milestones if m.get("status") == "complete")
                parts.append(f"Milestones: {complete}/{len(milestones)} complete")

            return "\n".join(parts)

        except Exception as e:
            logger.warning(
                "Failed to get consultation context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_chat_context(self, user_id: str) -> str | None:
        """Get general chat context with active goals and hot leads.

        Args:
            user_id: The user's UUID.

        Returns:
            Formatted chat context or None on error.
        """
        try:
            parts = []

            # Active goals
            goals = await self.goal_service.list_goals(user_id)
            active_goals = [g for g in goals if g.get("status") == "active"]
            if active_goals:
                parts.append(f"Active goals: {len(active_goals)}")
                for goal in active_goals[:3]:
                    title = goal.get("title", "Goal")
                    progress = goal.get("progress", 0)
                    parts.append(f"  - {title} ({progress}%)")

            # Hot leads
            result = (
                self.db.table("lead_memories")
                .select("company_name, health_score")
                .eq("user_id", user_id)
                .eq("status", "active")
                .gte("health_score", 70)
                .order("health_score", desc=True)
                .limit(3)
                .execute()
            )

            if result.data:
                parts.append(f"Hot leads: {len(result.data)}")
                for lead in result.data:
                    name = lead.get("company_name", "Unknown")
                    score = lead.get("health_score", 0)
                    parts.append(f"  - {name} (health: {score})")

            return "\n".join(parts) if parts else None

        except Exception as e:
            logger.warning(
                "Failed to get chat context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_recent_conversation_context(self, user_id: str) -> str | None:
        """Get recent conversation summaries for context.

        Args:
            user_id: The user's UUID.

        Returns:
            Formatted recent context or None on error.
        """
        try:
            result = (
                self.db.table("conversations")
                .select("summary, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(3)
                .execute()
            )

            if not result.data:
                return None

            parts = []
            for conv in result.data:
                summary = conv.get("summary")
                if summary:
                    # Truncate to first sentence
                    first_sentence = summary.split(".")[0] + "."
                    parts.append(f"- {first_sentence[:100]}")

            return "\n".join(parts) if parts else None

        except Exception as e:
            logger.warning(
                "Failed to get recent conversation context",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None


# Singleton instance
_aria_persona_manager: ARIAPersonaManager | None = None


def get_aria_persona_manager() -> ARIAPersonaManager:
    """Get or create ARIA persona manager singleton.

    Returns:
        The shared ARIAPersonaManager instance.
    """
    global _aria_persona_manager
    if _aria_persona_manager is None:
        _aria_persona_manager = ARIAPersonaManager()
    return _aria_persona_manager
