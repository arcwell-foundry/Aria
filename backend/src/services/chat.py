"""Chat service with memory integration.

This service handles chat interactions by:
1. Querying relevant memories before generating a response
2. Including memory context in the LLM prompt
3. Updating working memory with the conversation flow
4. Extracting and storing new information from the chat
5. Web grounding for real-time information via Exa
"""

import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from src.api.routes.memory import MemoryQueryService
from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.intelligence.proactive_memory import ProactiveMemoryService
from src.memory.conversation import ConversationService
from src.memory.digital_twin import DigitalTwin
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.priming import ConversationContext, ConversationPrimingService
from src.memory.salience import SalienceService
from src.memory.working import WorkingMemoryManager
from src.models.cognitive_load import CognitiveLoadState, LoadLevel
from src.models.proactive_insight import ProactiveInsight
from src.onboarding.personality_calibrator import PersonalityCalibration, PersonalityCalibrator
from src.services.email_tools import (
    EMAIL_TOOL_DEFINITIONS,
    execute_email_tool,
    get_email_integration,
)
from src.services.extraction import ExtractionService

from src.core.cognitive_friction import (
    FRICTION_CHALLENGE,
    FRICTION_FLAG,
    FRICTION_REFUSE,
    FrictionDecision,
    get_cognitive_friction_engine,
)

logger = logging.getLogger(__name__)

# Agent-to-trust-category mapping for autonomy upgrade checks
_AGENT_TO_CATEGORY: dict[str, str] = {
    "hunter": "lead_discovery",
    "analyst": "research",
    "strategist": "strategy",
    "scribe": "email_draft",
    "operator": "crm_action",
    "scout": "market_monitoring",
    "verifier": "verification",
    "executor": "browser_automation",
}


# ---------------------------------------------------------------------------
# Web Grounding Service
# ---------------------------------------------------------------------------


class WebGroundingService:
    """Detects when chat needs web data and fetches it via Exa.

    Uses regex-based pattern matching (<50ms) for query type detection,
    routing to appropriate Exa endpoints for real-time information.

    Design decisions:
    - Regex over LLM for speed (<50ms vs >500ms)
    - Graceful fallback to LLM on errors
    - LRU caching with 1hr TTL for entities
    """

    # Pattern for detecting company-related queries
    COMPANY_PATTERNS = [
        r"(?i)(?:about|tell me about|what is|who is)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*(?:company|inc|corp|llc|ltd)?",
        r"(?i)(?:revenue|funding|employees|valuation)\s+(?:of\s+)?([A-Z][a-zA-Z]+)",
        r"(?i)(?:news|latest|recent)\s+(?:about\s+)?([A-Z][a-zA-Z]+)",
        r"(?i)(?:what does|what's)\s+([A-Z][a-zA-Z]+)\s+(?:do|make|sell)",
    ]

    # Pattern for detecting person-related queries
    PERSON_PATTERNS = [
        r"(?i)(?:who is|find|contact)\s+(?:the\s+)?(?:VP|CEO|CTO|CFO|Director|Head|Chief|President)?\s*(?:of\s+)?(?:Sales|Marketing|Engineering|Finance|Operations)?\s*(?:at\s+)?([A-Z][a-zA-Z]+)",
        r"(?i)(?:ceo|cto|cfo|vp|director)\s+(?:of\s+)?([A-Z][a-zA-Z]+)",
        r"(?i)(?:linkedin|profile)\s+(?:for\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
    ]

    # Pattern for factual questions (answer endpoint)
    FACTUAL_PATTERNS = [
        r"(?i)^(?:what|when|where|who|how many|how much)\s+",
        r"(?i)^(?:is|are|was|were|did|does|do|has|have)\s+",
    ]

    # Entity cache (1 hour TTL)
    _entity_cache: dict[str, tuple[Any, float]] = {}
    _CACHE_TTL_SECONDS = 3600  # 1 hour

    def __init__(self) -> None:
        """Initialize the web grounding service with lazy Exa provider."""
        self._exa_provider: Any = None

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("WebGroundingService: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning(
                    "WebGroundingService: Failed to initialize ExaEnrichmentProvider: %s", e
                )
        return self._exa_provider

    def _get_cached(self, key: str) -> Any | None:
        """Get a cached value if not expired."""
        if key in self._entity_cache:
            value, timestamp = self._entity_cache[key]
            if time.time() - timestamp < self._CACHE_TTL_SECONDS:
                return value
            del self._entity_cache[key]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Cache a value with current timestamp."""
        self._entity_cache[key] = (value, time.time())

    async def detect_and_ground(self, message: str) -> dict[str, Any] | None:
        """Detect query type and fetch web-grounded context.

        Args:
            message: The user's message to analyze.

        Returns:
            Dict with grounding results, or None if no grounding needed/failed.
        """
        exa = self._get_exa_provider()
        if not exa:
            return None

        grounding_start = time.perf_counter()

        try:
            # Check for factual question first (highest priority for answer endpoint)
            for pattern in self.FACTUAL_PATTERNS:
                if re.search(pattern, message):
                    logger.info(
                        "WebGroundingService: Detected factual question",
                        extra={"message_preview": message[:100]},
                    )
                    return await self._ground_factual(message)

            # Check for company query
            for pattern in self.COMPANY_PATTERNS:
                match = re.search(pattern, message)
                if match:
                    company_name = match.group(1)
                    logger.info(
                        "WebGroundingService: Detected company query",
                        extra={"company": company_name, "message_preview": message[:100]},
                    )
                    return await self._ground_company(company_name)

            # Check for person query
            for pattern in self.PERSON_PATTERNS:
                match = re.search(pattern, message)
                if match:
                    entity = match.group(1)
                    logger.info(
                        "WebGroundingService: Detected person query",
                        extra={"entity": entity, "message_preview": message[:100]},
                    )
                    return await self._ground_person(entity, message)

            # General web grounding for queries with question words
            question_words = ["what", "who", "when", "where", "how", "which", "latest", "recent"]
            if any(word in message.lower() for word in question_words):
                logger.info(
                    "WebGroundingService: Detected general question",
                    extra={"message_preview": message[:100]},
                )
                return await self._ground_general(message)

        except Exception as e:
            logger.warning(
                "WebGroundingService: Grounding failed",
                extra={"error": str(e), "message_preview": message[:100]},
            )
            return None

        grounding_ms = (time.perf_counter() - grounding_start) * 1000
        logger.debug(
            "WebGroundingService: No grounding needed",
            extra={"message_preview": message[:100], "detection_ms": round(grounding_ms, 2)},
        )
        return None

    async def _ground_factual(self, question: str) -> dict[str, Any] | None:
        """Get a direct factual answer using Exa answer endpoint."""
        exa = self._get_exa_provider()
        if not exa:
            return None

        # Check cache
        cache_key = f"answer:{question}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            answer = await exa.answer(question=question)
            if answer:
                result = {
                    "type": "factual_answer",
                    "question": question,
                    "answer": answer,
                    "source": "exa_answer",
                }
                self._set_cached(cache_key, result)
                logger.info(
                    "WebGroundingService: Got factual answer",
                    extra={"answer_length": len(answer)},
                )
                return result
        except Exception as e:
            logger.warning("WebGroundingService: Factual answer failed: %s", e)

        return None

    async def _ground_company(self, company_name: str) -> dict[str, Any] | None:
        """Get company intelligence using Exa search_company endpoint."""
        exa = self._get_exa_provider()
        if not exa:
            return None

        # Check cache
        cache_key = f"company:{company_name.lower()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            enrichment = await exa.search_company(company_name)

            result = {
                "type": "company_intelligence",
                "company_name": company_name,
                "description": enrichment.description[:500] if enrichment.description else None,
                "domain": enrichment.domain,
                "recent_news": enrichment.recent_news[:3] if enrichment.recent_news else [],
                "funding": enrichment.latest_funding_round,
                "confidence": enrichment.confidence,
                "source": "exa_company",
            }

            self._set_cached(cache_key, result)
            logger.info(
                "WebGroundingService: Got company intelligence",
                extra={
                    "company": company_name,
                    "has_description": bool(enrichment.description),
                    "news_count": len(enrichment.recent_news or []),
                },
            )
            return result

        except Exception as e:
            logger.warning(
                "WebGroundingService: Company search failed: %s",
                e,
                extra={"company": company_name},
            )

        return None

    async def _ground_person(self, name: str, context: str) -> dict[str, Any] | None:
        """Get person intelligence using Exa search_person endpoint."""
        exa = self._get_exa_provider()
        if not exa:
            return None

        # Check cache
        cache_key = f"person:{name.lower()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Extract company from context if present
            company = ""
            at_match = re.search(r"(?:at|@)\s+([A-Z][a-zA-Z]+)", context)
            if at_match:
                company = at_match.group(1)

            enrichment = await exa.search_person(name=name, company=company)

            result = {
                "type": "person_intelligence",
                "name": name,
                "title": enrichment.title,
                "company": enrichment.company,
                "linkedin_url": enrichment.linkedin_url,
                "bio": enrichment.bio[:500] if enrichment.bio else None,
                "web_mentions": enrichment.web_mentions[:3] if enrichment.web_mentions else [],
                "confidence": enrichment.confidence,
                "source": "exa_person",
            }

            self._set_cached(cache_key, result)
            logger.info(
                "WebGroundingService: Got person intelligence",
                extra={
                    "name": name,
                    "has_linkedin": bool(enrichment.linkedin_url),
                    "has_bio": bool(enrichment.bio),
                },
            )
            return result

        except Exception as e:
            logger.warning(
                "WebGroundingService: Person search failed: %s",
                e,
                extra={"name": name},
            )

        return None

    async def _ground_general(self, query: str) -> dict[str, Any] | None:
        """Get general web results using Exa search_instant endpoint."""
        exa = self._get_exa_provider()
        if not exa:
            return None

        try:
            results = await exa.search_instant(query=query, num_results=3)

            if results:
                formatted_results = [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.text[:300] if r.text else "",
                        "published_date": r.published_date,
                    }
                    for r in results
                ]

                result = {
                    "type": "web_results",
                    "query": query,
                    "results": formatted_results,
                    "source": "exa_instant",
                }

                logger.info(
                    "WebGroundingService: Got instant results",
                    extra={"query": query[:50], "result_count": len(results)},
                )
                return result

        except Exception as e:
            logger.warning(
                "WebGroundingService: Instant search failed: %s",
                e,
                extra={"query": query[:50]},
            )

        return None


# ---------------------------------------------------------------------------
# Email Check Service
# ---------------------------------------------------------------------------


class EmailCheckService:
    """Detects email check requests and triggers inbox scanning.

    Uses regex-based pattern matching (<50ms) for request detection,
    routing to EmailAnalyzer for real-time inbox scanning.

    Design decisions:
    - Regex over LLM for speed (<50ms vs >500ms)
    - Direct scan trigger with natural language response
    - Integrates with RealtimeEmailNotifier for urgent emails
    """

    # Patterns for detecting email check requests
    EMAIL_CHECK_PATTERNS = [
        r"(?i)check my email",
        r"(?i)check my emails",
        r"(?i)scan my inbox",
        r"(?i)scan my email",
        r"(?i)any new emails?",
        r"(?i)any new email",
        r"(?i)what'?s in my inbox",
        r"(?i)what is in my inbox",
        r"(?i)do i have (?:any )?emails",
        r"(?i)do i have (?:any )?urgent emails",
        r"(?i)show me my emails",
        r"(?i)read my email",
        r"(?i)check for new mail",
        r"(?i)inbox check",
    ]

    # Pattern for urgent-specific requests
    URGENT_CHECK_PATTERNS = [
        r"(?i)any urgent",
        r"(?i)urgent emails?",
        r"(?i)anything urgent",
        r"(?i)urgent mail",
    ]

    def __init__(self) -> None:
        """Initialize the email check service with lazy dependencies."""
        self._email_analyzer: Any = None
        self._realtime_notifier: Any = None

    def _get_email_analyzer(self) -> Any:
        """Lazily initialize and return the EmailAnalyzer."""
        if self._email_analyzer is None:
            try:
                from src.services.email_analyzer import EmailAnalyzer

                self._email_analyzer = EmailAnalyzer()
                logger.info("EmailCheckService: EmailAnalyzer initialized")
            except Exception as e:
                logger.warning(
                    "EmailCheckService: Failed to initialize EmailAnalyzer: %s", e
                )
        return self._email_analyzer

    def _get_realtime_notifier(self) -> Any:
        """Lazily initialize and return the RealtimeEmailNotifier."""
        if self._realtime_notifier is None:
            try:
                from src.services.realtime_email_notifier import get_realtime_email_notifier

                self._realtime_notifier = get_realtime_email_notifier()
                logger.info("EmailCheckService: RealtimeEmailNotifier initialized")
            except Exception as e:
                logger.warning(
                    "EmailCheckService: Failed to initialize RealtimeEmailNotifier: %s", e
                )
        return self._realtime_notifier

    def detect_email_check_request(self, message: str) -> bool:
        """Detect if the message is an email check request.

        Args:
            message: The user's message to analyze.

        Returns:
            True if this is an email check request.
        """
        for pattern in self.EMAIL_CHECK_PATTERNS:
            if re.search(pattern, message):
                return True
        return False

    def is_urgent_specific(self, message: str) -> bool:
        """Check if the request is specifically about urgent emails.

        Args:
            message: The user's message to analyze.

        Returns:
            True if this is an urgent-specific request.
        """
        for pattern in self.URGENT_CHECK_PATTERNS:
            if re.search(pattern, message):
                return True
        return False

    async def check_email(
        self,
        user_id: str,
        message: str,
    ) -> dict[str, Any] | None:
        """Handle an email check request and return natural language summary.

        Args:
            user_id: The user's ID.
            message: The user's original message.

        Returns:
            Dict with email check results and response text, or None if failed.
        """
        analyzer = self._get_email_analyzer()
        if not analyzer:
            return None

        check_start = time.perf_counter()

        try:
            logger.info(
                "EmailCheckService: Processing email check for user %s",
                user_id,
            )

            # Scan inbox (last 24 hours)
            scan_result = await analyzer.scan_inbox(user_id, since_hours=24)

            scan_ms = (time.perf_counter() - check_start) * 1000

            # Build response based on results
            response_text = self._build_response_text(
                scan_result.total_emails,
                len(scan_result.needs_reply),
                scan_result.urgent,
                self.is_urgent_specific(message),
            )

            # Process urgent emails with notifications
            urgent_details: list[dict[str, Any]] = []
            if scan_result.urgent:
                notifier = self._get_realtime_notifier()
                if notifier:
                    notifications = await notifier.process_and_notify(
                        user_id=user_id,
                        urgent_emails=scan_result.urgent,
                        generate_drafts=True,
                    )
                    urgent_details = [
                        {
                            "email_id": n.email_id,
                            "sender": n.sender_name,
                            "subject": n.subject,
                            "draft_saved": n.draft_saved,
                        }
                        for n in notifications
                    ]

            logger.info(
                "EmailCheckService: Scan complete for user %s - %d total, %d urgent, %.0fms",
                user_id,
                scan_result.total_emails,
                len(scan_result.urgent),
                scan_ms,
            )

            return {
                "type": "email_check_result",
                "total_emails": scan_result.total_emails,
                "needs_reply": len(scan_result.needs_reply),
                "urgent_count": len(scan_result.urgent),
                "urgent_details": urgent_details,
                "response_text": response_text,
                "scan_ms": scan_ms,
            }

        except Exception as e:
            logger.warning(
                "EmailCheckService: Email check failed for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            return {
                "type": "email_check_result",
                "error": str(e),
                "response_text": "I encountered an error checking your email. Please try again.",
            }

    def _build_response_text(
        self,
        total: int,
        needs_reply: int,
        urgent: list[Any],
        urgent_specific: bool,
    ) -> str:
        """Build natural language response for email check.

        Args:
            total: Total emails scanned.
            needs_reply: Count of emails needing reply.
            urgent: List of urgent emails.
            urgent_specific: Whether user specifically asked about urgent.

        Returns:
            Natural language response string.
        """
        if total == 0:
            return "Your inbox is clear - no new emails to process."

        if urgent_specific:
            if not urgent:
                return f"Good news - no urgent emails found. I scanned {total} emails and none require immediate attention."
            else:
                urgent_senders = [e.sender_name or e.sender_email for e in urgent[:3]]
                senders_str = ", ".join(urgent_senders)
                if len(urgent) == 1:
                    return f"You have 1 urgent email from {senders_str}. I've drafted a reply and it's ready for review."
                else:
                    return f"You have {len(urgent)} urgent emails from {senders_str}{' and others' if len(urgent) > 3 else ''}. I've drafted replies and they're ready for review."

        if urgent:
            urgent_senders = [e.sender_name or e.sender_email for e in urgent[:3]]
            senders_str = ", ".join(urgent_senders)
            if len(urgent) == 1:
                return (
                    f"I scanned {total} emails. You have 1 urgent email from {senders_str}. "
                    f"I've drafted a reply and it's ready for review. "
                    f"{needs_reply - 1} other emails need replies but aren't time-sensitive."
                )
            else:
                return (
                    f"I scanned {total} emails. You have {len(urgent)} urgent emails from "
                    f"{senders_str}{' and others' if len(urgent) > 3 else ''}. "
                    f"I've drafted replies and they're ready for review. "
                    f"{needs_reply - len(urgent)} other emails need replies but aren't time-sensitive."
                )

        if needs_reply > 0:
            return (
                f"I scanned {total} emails. {needs_reply} {'need' if needs_reply > 1 else 'needs'} "
                f"a reply, but nothing is urgent. Would you like me to draft responses?"
            )

        return f"I scanned {total} emails. Nothing needs a reply right now - you're all caught up!"


# Web grounding context template for LLM
WEB_GROUNDING_TEMPLATE = """## Real-Time Web Information

The following information was retrieved from the web to provide accurate, up-to-date context:

{web_context}

Use this information to provide a grounded, accurate response. Cite specific facts when relevant."""

# System prompt template for ARIA
ARIA_SYSTEM_PROMPT = """You are ARIA (Autonomous Reasoning & Intelligence Agent), an AI-powered Department Director for Life Sciences commercial teams. You are helpful, professional, and focused on helping sales representatives be more effective.

When responding:
- Be concise and actionable
- Reference specific information you know about the user when relevant
- Cite your sources when using information from memory
- Ask clarifying questions when the user's intent is unclear

{memory_context}"""

MEMORY_CONTEXT_TEMPLATE = """## Relevant Context from Memory

The following information may be relevant to this conversation:

{memories}

Use this context naturally in your response. If you reference specific facts, note the confidence level if it's below 0.8."""

PROCEDURAL_CONTEXT_TEMPLATE = """## Learned Workflows

You have access to these established workflow patterns. Reference them when the user asks about processes, past approaches, or how things were done:

{workflows}"""

PROSPECTIVE_CONTEXT_TEMPLATE = """## Upcoming Tasks & Reminders

The user has these pending or overdue items. Proactively mention overdue items and upcoming deadlines when relevant:

{tasks}"""

LEAD_CONTEXT_TEMPLATE = """## Active Leads Context

The user's current sales pipeline includes these leads. Reference specific leads, health scores, and stages when discussing pipeline, accounts, or sales activity:

{leads}"""

PROACTIVE_INSIGHTS_TEMPLATE = """## Relevant Context ARIA Can Mention

The following insights may be worth volunteering to the user if relevant:

{insights}

You may naturally mention these in your response when appropriate, without explicitly stating where the information came from."""

PERSONALITY_CONTEXT_TEMPLATE = """## Communication Style Calibration

Adapt your tone and style to match this user's preferences:

{tone_guidance}

{examples}"""

WRITING_STYLE_TEMPLATE = """## Writing Style Fingerprint

Match this communication style when composing content for or as this user:

{style_guidelines}"""

PRIMING_CONTEXT_TEMPLATE = """## Conversation Continuity

{priming_context}"""

HIGH_LOAD_INSTRUCTION = """
IMPORTANT: The user appears to be under high cognitive load right now. Adapt your response:
- Be extremely concise and direct
- Lead with the most important information
- Avoid asking multiple questions
- Offer to handle tasks independently
- Use bullet points for clarity
"""

# Default memory types queried for every chat interaction.
# All three chat paths (REST, SSE, WebSocket) must use this constant
# so that responses are equally informed regardless of transport.
DEFAULT_MEMORY_TYPES: list[str] = ["episodic", "semantic", "procedural", "prospective", "lead"]

# Skill detection confidence threshold
_SKILL_CONFIDENCE_THRESHOLD = 0.7


class ChatService:
    """Service for memory-integrated chat interactions."""

    # Feature flag: set True to use PersonaBuilder for system prompt assembly.
    # When False, uses the existing _build_system_prompt method.
    _use_persona_builder: bool = True

    def __init__(self) -> None:
        """Initialize chat service with dependencies."""
        self._memory_service = MemoryQueryService()
        self._llm_client = LLMClient()
        self._working_memory_manager = WorkingMemoryManager()
        self._extraction_service = ExtractionService()
        self._personality_calibrator = PersonalityCalibrator()
        self._digital_twin = DigitalTwin()
        db = get_supabase_client()
        self._cognitive_monitor = CognitiveLoadMonitor(db_client=db)
        self._proactive_service = ProactiveMemoryService(db_client=db)
        self._priming_service = ConversationPrimingService(
            conversation_service=ConversationService(db_client=db, llm_client=self._llm_client),
            salience_service=SalienceService(db_client=db),
            db_client=db,
        )
        self._episodic_memory = EpisodicMemory()

        # PersonaBuilder — lazily initialized on first use
        self._persona_builder: Any = None

        # Skill detection — lazily initialized on first use
        self._skill_registry: Any = None
        self._skill_orchestrator: Any = None
        self._skill_registry_initialized = False

        # Web grounding — lazily initialized on first use
        self._web_grounding: WebGroundingService | None = None

        # Companion orchestrator — lazily initialized on first use
        self._companion_orchestrator: Any = None

        # Cognitive Friction Engine — lazily initialized
        self._friction_engine: Any = None

        # Trust Calibration Service — lazily initialized
        self._trust_service: Any = None

    def _get_friction_engine(self) -> Any:
        """Lazily initialize CognitiveFrictionEngine."""
        if self._friction_engine is None:
            try:
                self._friction_engine = get_cognitive_friction_engine()
            except Exception as e:
                logger.warning("Failed to initialize CognitiveFrictionEngine: %s", e)
        return self._friction_engine

    def _get_trust_service(self) -> Any:
        """Lazily initialize TrustCalibrationService."""
        if self._trust_service is None:
            try:
                from src.core.trust import get_trust_calibration_service

                self._trust_service = get_trust_calibration_service()
            except Exception as e:
                logger.warning("Failed to initialize TrustCalibrationService: %s", e)
        return self._trust_service

    async def _get_skill_registry(self) -> Any:
        """Lazily initialize and return the SkillRegistry.

        Returns:
            Initialized SkillRegistry, or None if initialization fails.
        """
        if self._skill_registry_initialized:
            return self._skill_registry

        self._skill_registry_initialized = True
        try:
            from src.skills.registry import SkillRegistry

            registry = SkillRegistry()
            await registry.initialize()
            self._skill_registry = registry
        except Exception as e:
            logger.warning("Failed to initialize SkillRegistry for chat: %s", e)
            self._skill_registry = None

        return self._skill_registry

    async def _get_skill_orchestrator(self) -> Any:
        """Lazily initialize and return the SkillOrchestrator.

        Returns:
            SkillOrchestrator instance, or None if initialization fails.
        """
        if self._skill_orchestrator is not None:
            return self._skill_orchestrator

        try:
            from src.security.skill_audit import SkillAuditService
            from src.skills.autonomy import SkillAutonomyService
            from src.skills.executor import SkillExecutor
            from src.skills.index import SkillIndex
            from src.skills.orchestrator import SkillOrchestrator

            index = SkillIndex()
            executor = SkillExecutor(index=index, llm_client=self._llm_client)
            autonomy = SkillAutonomyService()
            audit = SkillAuditService()
            self._skill_orchestrator = SkillOrchestrator(
                executor=executor,
                index=index,
                autonomy=autonomy,
                audit=audit,
            )
        except Exception as e:
            logger.warning("Failed to initialize SkillOrchestrator for chat: %s", e)
            self._skill_orchestrator = None

        return self._skill_orchestrator

    async def _detect_skill_match(
        self,
        message: str,
    ) -> tuple[bool, list[Any], float]:
        """Check if a message matches any skill capability.

        Uses SkillRegistry.get_for_task() to find matching skills.
        Returns True if the best match confidence exceeds the threshold.

        Args:
            message: The user's message to analyze.

        Returns:
            Tuple of (should_route, ranked_skills, best_confidence).
        """
        registry = await self._get_skill_registry()
        if registry is None:
            return False, [], 0.0

        try:
            task = {"description": message, "type": "chat_request"}
            ranked_skills = await registry.get_for_task(task)

            if not ranked_skills:
                return False, [], 0.0

            best_confidence = ranked_skills[0].relevance if ranked_skills else 0.0

            if best_confidence >= _SKILL_CONFIDENCE_THRESHOLD:
                logger.info(
                    "Skill match detected in chat",
                    extra={
                        "best_skill": ranked_skills[0].entry.name,
                        "confidence": best_confidence,
                        "message_preview": message[:100],
                    },
                )
                return True, ranked_skills, best_confidence

            return False, ranked_skills, best_confidence

        except Exception as e:
            logger.warning("Skill detection failed: %s", e)
            return False, [], 0.0

    async def _detect_plan_extension(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
    ) -> str | None:
        """Detect if the user is requesting a follow-on action to a prior skill result.

        Checks if the previous ARIA response included skill results AND the
        new message references those results. Uses LLM to determine intent.

        Args:
            user_id: The user's ID.
            conversation_id: Current conversation identifier.
            message: The user's new message.

        Returns:
            The plan_id to extend, or None if not a follow-on.
        """
        # Get working memory to check last response
        working_memory = await self._working_memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=user_id,
        )
        context = working_memory.get_context_for_llm()

        if len(context) < 2:
            return None

        # Check if the last assistant message included skill execution results
        last_assistant = None
        last_plan_id = None
        for msg in reversed(context):
            if msg.get("role") == "assistant":
                last_assistant = msg.get("content", "")
                # Look for plan_id markers in metadata
                metadata = msg.get("metadata", {})
                if isinstance(metadata, dict):
                    last_plan_id = metadata.get("skill_plan_id")
                break

        if not last_assistant or not last_plan_id:
            # Also check DB for recent plans in this conversation
            try:
                db = get_supabase_client()
                recent_plans = (
                    db.table("skill_execution_plans")
                    .select("id, status, task_description")
                    .eq("user_id", user_id)
                    .in_("status", ["completed", "failed"])
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if recent_plans.data:
                    last_plan_id = recent_plans.data[0]["id"]
                    last_assistant = recent_plans.data[0].get("task_description", "")
                else:
                    return None
            except Exception:
                return None

        if not last_plan_id:
            return None

        # Use LLM to check if the new message is a follow-on
        try:
            check_prompt = (
                "Determine if the user's new message is requesting a follow-on action "
                "based on the previous skill execution results.\n\n"
                f"Previous ARIA response (skill result summary):\n{last_assistant[:500]}\n\n"
                f"User's new message:\n{message}\n\n"
                'Respond with ONLY valid JSON: {"is_followon": true|false, "reasoning": "..."}'
            )

            response = await self._llm_client.generate_response(
                messages=[{"role": "user", "content": check_prompt}],
                system_prompt=(
                    "You determine if a user message is a follow-on request "
                    "to previous results. Output ONLY valid JSON."
                ),
                temperature=0.0,
                max_tokens=100,
            )

            parsed = json.loads(response)
            if parsed.get("is_followon"):
                logger.info(
                    "Plan extension detected",
                    extra={
                        "plan_id": last_plan_id,
                        "reasoning": parsed.get("reasoning", ""),
                    },
                )
                return last_plan_id

        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Follow-on detection failed: %s", e)

        return None

    async def _route_through_skill(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        extend_plan_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Route a message through the skill orchestrator.

        Either creates a new plan from the message or extends an existing plan.

        Args:
            user_id: The user's ID.
            conversation_id: Current conversation identifier.
            message: The user's message.
            extend_plan_id: If set, extend this plan instead of creating new.

        Returns:
            Dict with skill execution results, or None if routing failed.
        """
        _ = conversation_id  # Reserved for per-conversation plan scoping
        orchestrator = await self._get_skill_orchestrator()
        if orchestrator is None:
            return None

        try:
            if extend_plan_id:
                plan = await orchestrator.extend_plan(
                    completed_plan_id=extend_plan_id,
                    new_request=message,
                    user_id=user_id,
                )
            else:
                task = {"description": message}
                plan = await orchestrator.analyze_task(task, user_id)

            if not plan.steps:
                return None

            # Auto-approve if low risk
            if not plan.approval_required:
                result = await orchestrator.execute_plan(
                    user_id=user_id,
                    plan=plan,
                )

                # Build a summary of skill results for the LLM to incorporate
                step_summaries = []
                for entry in result.working_memory:
                    step_summaries.append(f"- {entry.skill_id} [{entry.status}]: {entry.summary}")

                return {
                    "plan_id": result.plan_id,
                    "status": result.status,
                    "steps_completed": result.steps_completed,
                    "steps_failed": result.steps_failed,
                    "skill_summaries": "\n".join(step_summaries),
                    "working_memory": [
                        {
                            "skill_id": e.skill_id,
                            "status": e.status,
                            "summary": e.summary,
                            "artifacts": e.artifacts,
                            "extracted_facts": e.extracted_facts,
                        }
                        for e in result.working_memory
                    ],
                }
            else:
                # Plan requires approval — return plan details for user review
                return {
                    "plan_id": plan.plan_id,
                    "status": "pending_approval",
                    "risk_level": plan.risk_level,
                    "reasoning": plan.reasoning,
                    "steps": [
                        {
                            "step_number": s.step_number,
                            "skill_path": s.skill_path,
                            "depends_on": s.depends_on,
                        }
                        for s in plan.steps
                    ],
                    "skill_summaries": (
                        f"I've prepared a {plan.risk_level}-risk plan with "
                        f"{len(plan.steps)} steps that needs your approval."
                    ),
                }

        except Exception as e:
            logger.warning("Skill routing failed: %s", e)
            return None

    async def _ensure_conversation_record(
        self,
        user_id: str,
        conversation_id: str,
    ) -> None:
        """Ensure a conversation record exists for this conversation_id.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        from src.db.supabase import get_supabase_client

        try:
            db = get_supabase_client()

            # Check if conversation exists
            result = (
                db.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .execute()
            )

            if result.data:
                # Conversation exists, update it
                (
                    db.table("conversations")
                    .update(
                        {
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    .eq("user_id", user_id)
                    .eq("id", conversation_id)
                    .execute()
                )
            else:
                # Create new conversation record
                db.table("conversations").insert(
                    {
                        "id": conversation_id,
                        "user_id": user_id,
                        "message_count": 0,
                    }
                ).execute()

        except Exception as e:
            logger.warning(
                "Failed to ensure conversation record",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )

    async def _update_conversation_metadata(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
    ) -> None:
        """Update conversation metadata after message exchange.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.
            user_message: The user's message content (used for preview).

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        from src.db.supabase import get_supabase_client

        try:
            db = get_supabase_client()

            # Generate preview from user message (first 100 chars)
            preview = user_message[:100]
            if len(user_message) > 100:
                preview += "..."

            # Get current message count
            current = (
                db.table("conversations")
                .select("message_count")
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .single()
                .execute()
            )

            message_count = 0
            if current.data:
                message_count = current.data.get("message_count", 0)

            # Update metadata
            (
                db.table("conversations")
                .update(
                    {
                        "message_count": message_count + 2,  # user + assistant
                        "last_message_at": datetime.now(UTC).isoformat(),
                        "last_message_preview": preview,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .execute()
            )

        except Exception as e:
            logger.warning(
                "Failed to update conversation metadata",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )

    async def persist_turn(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        assistant_metadata: dict[str, Any] | None = None,
        conversation_context: list[dict[str, str]] | None = None,
    ) -> None:
        """Single source of truth for persisting a conversation turn.

        Saves both messages, updates conversation metadata, and runs
        information extraction. All errors are logged but not raised.
        """
        # 1. Save both messages
        try:
            from src.services.conversations import ConversationService as _ConvService

            conv_svc = _ConvService(db_client=get_supabase_client())
            await conv_svc.save_message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
            )
            await conv_svc.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                metadata=assistant_metadata,
            )
        except Exception as e:
            logger.warning(
                "Message persistence failed",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

        # 2. Update conversation metadata (message_count, timestamps, preview)
        await self._update_conversation_metadata(user_id, conversation_id, user_message)

        # 3. Extract and store information (fire-and-forget)
        try:
            await self._extraction_service.extract_and_store(
                conversation=conversation_context
                or [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_message},
                ],
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(
                "Information extraction failed",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def process_message(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        memory_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Process a user message and generate a response.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.
            message: The user's message.
            memory_types: Memory types to query (default: episodic, semantic).

        Returns:
            Dict containing response message, citations, and timing.
        """
        total_start = time.perf_counter()

        if memory_types is None:
            memory_types = DEFAULT_MEMORY_TYPES

        # Get or create working memory for this conversation
        working_memory = await self._working_memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Ensure conversation record exists for sidebar
        await self._ensure_conversation_record(user_id, conversation_id)

        # Add user message to working memory
        working_memory.add_message("user", message)

        # Get conversation history for cognitive load estimation
        conversation_messages = working_memory.get_context_for_llm()

        # Estimate cognitive load from recent messages
        recent_messages = conversation_messages[-5:]  # Last 5 messages
        load_state = await self._cognitive_monitor.estimate_load(
            user_id=user_id,
            recent_messages=recent_messages,
            session_id=conversation_id,
        )

        # Query relevant memories with timing
        memory_start = time.perf_counter()
        memories = await self._query_relevant_memories(
            user_id=user_id,
            query=message,
            memory_types=memory_types,
        )
        memory_ms = (time.perf_counter() - memory_start) * 1000

        # Web grounding: Detect and fetch real-time web data
        web_grounding_start = time.perf_counter()
        web_context: dict[str, Any] | None = None
        try:
            if self._web_grounding is None:
                self._web_grounding = WebGroundingService()
            web_context = await self._web_grounding.detect_and_ground(message)
        except Exception as e:
            logger.warning("Web grounding failed: %s", e)
        web_grounding_ms = (time.perf_counter() - web_grounding_start) * 1000

        # Check if user has email integration (for tool-based email access)
        email_check_start = time.perf_counter()
        email_integration: dict[str, Any] | None = None
        try:
            email_integration = await get_email_integration(user_id)
        except Exception as e:
            logger.warning("Email integration check failed: %s", e)
        email_check_ms = (time.perf_counter() - email_check_start) * 1000

        # Get proactive insights to volunteer
        proactive_start = time.perf_counter()
        proactive_insights = await self._get_proactive_insights(
            user_id=user_id,
            current_message=message,
            conversation_messages=conversation_messages,
        )
        proactive_ms = (time.perf_counter() - proactive_start) * 1000

        # --- Cognitive Friction: evaluate before any action routing ---
        friction_ms = 0.0
        friction_decision: FrictionDecision | None = None
        try:
            friction_start = time.perf_counter()
            friction_engine = self._get_friction_engine()
            if friction_engine:
                friction_decision = await friction_engine.evaluate(
                    user_id=user_id,
                    user_request=message,
                    task_characteristics=None,
                    user_context=None,
                )
            friction_ms = (time.perf_counter() - friction_start) * 1000
        except Exception as e:
            logger.warning("Cognitive friction evaluation failed (fail-open): %s", e)

        # Early return on challenge or refuse
        if friction_decision and friction_decision.level in (
            FRICTION_CHALLENGE,
            FRICTION_REFUSE,
        ):
            pushback_msg = (
                friction_decision.user_message
                or "I need to pause on that request."
            )
            working_memory.add_message("assistant", pushback_msg)
            await self.persist_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=message,
                assistant_message=pushback_msg,
                assistant_metadata={"friction_level": friction_decision.level},
                conversation_context=conversation_messages[-2:],
            )
            return {
                "message": pushback_msg,
                "citations": [],
                "conversation_id": conversation_id,
                "rich_content": [
                    {
                        "type": "friction_decision",
                        "data": {
                            "level": friction_decision.level,
                            "proceed_if_confirmed": friction_decision.proceed_if_confirmed,
                        },
                    }
                ],
                "ui_commands": [],
                "suggestions": (
                    ["Confirm and proceed", "Let me rethink"]
                    if friction_decision.proceed_if_confirmed
                    else ["Understood", "Tell me more"]
                ),
                "timing": {
                    "memory_query_ms": round(memory_ms, 2),
                    "proactive_query_ms": round(proactive_ms, 2),
                    "web_grounding_ms": round(web_grounding_ms, 2),
                    "email_check_ms": round(email_check_ms, 2),
                    "friction_ms": round(friction_ms, 2),
                    "skill_detection_ms": 0,
                    "llm_response_ms": 0,
                    "total_ms": round(
                        (time.perf_counter() - total_start) * 1000, 2
                    ),
                },
                "cognitive_load": {
                    "level": load_state.level.value,
                    "score": round(load_state.score, 3),
                    "recommendation": load_state.recommendation,
                },
                "proactive_insights": [],
            }

        # Build companion context (replaces personality calibration + style guidelines)
        companion_ctx = None
        try:
            if self._companion_orchestrator is None:
                from src.companion.factory import create_companion_orchestrator

                self._companion_orchestrator = create_companion_orchestrator()
            companion_ctx = await self._companion_orchestrator.build_full_context(
                user_id=user_id,
                message=message,
                conversation_history=conversation_messages,
                session_id=conversation_id,
            )
        except Exception as e:
            logger.warning("Companion orchestrator failed, falling back: %s", e)

        # Fall back to individual calls if orchestrator failed
        if companion_ctx is not None:
            personality = None
            style_guidelines = None
        else:
            personality = await self._get_personality_calibration(user_id)
            style_guidelines = await self._get_style_guidelines(user_id)

        # Prime conversation with recent episodes, open threads, and salient facts
        priming_context = await self._get_priming_context(user_id, message)

        # Build system prompt with all context layers
        if self._use_persona_builder:
            system_prompt = await self._build_system_prompt_v2(
                user_id,
                memories,
                load_state,
                proactive_insights,
                priming_context,
                web_context,
                companion_context=companion_ctx,
            )
        else:
            system_prompt = self._build_system_prompt(
                memories,
                load_state,
                proactive_insights,
                personality,
                style_guidelines,
                priming_context,
                web_context,
                companion_context=companion_ctx,
            )

        # Inject friction flag note into system prompt if flagged
        if (
            friction_decision
            and friction_decision.level == FRICTION_FLAG
            and friction_decision.user_message
        ):
            system_prompt += (
                f"\n\n## Cognitive Friction Note\n"
                f"Surface this concern naturally alongside your response: "
                f"{friction_decision.user_message}"
            )

        logger.info(
            "Processing chat message",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "memory_count": len(memories),
                "proactive_insight_count": len(proactive_insights),
                "message_count": len(conversation_messages),
                "memory_query_ms": memory_ms,
                "proactive_query_ms": proactive_ms,
                "web_grounding_ms": web_grounding_ms,
                "has_web_context": web_context is not None,
                "web_context_type": web_context.get("type") if web_context else None,
                "cognitive_load_level": load_state.level.value,
                "has_style_guidelines": style_guidelines is not None,
                "has_companion_context": companion_ctx is not None,
                "companion_failed_subsystems": companion_ctx.failed_subsystems if companion_ctx else [],
                "has_priming_context": priming_context is not None,
            },
        )

        # Skill-aware routing: check if message matches a skill capability
        skill_result: dict[str, Any] | None = None
        skill_ms = 0.0

        skill_start = time.perf_counter()
        try:
            # First check for plan extension (follow-on to prior skill results)
            extend_plan_id = await self._detect_plan_extension(user_id, conversation_id, message)

            if extend_plan_id:
                skill_result = await self._route_through_skill(
                    user_id,
                    conversation_id,
                    message,
                    extend_plan_id=extend_plan_id,
                )
            else:
                # Check for new skill match
                should_route, ranked_skills, best_confidence = await self._detect_skill_match(
                    message
                )
                if should_route:
                    skill_result = await self._route_through_skill(
                        user_id,
                        conversation_id,
                        message,
                    )
        except Exception as e:
            logger.warning("Skill detection/routing error: %s", e)
        skill_ms = (time.perf_counter() - skill_start) * 1000

        # What-if simulation: Detect "what if" questions and run simulation
        whatif_result: dict[str, Any] | None = None
        whatif_ms = 0.0
        whatif_indicators = [
            "what if",
            "what would happen",
            "what happens if",
            "imagine if",
            "hypothetically",
            "suppose",
            "scenario where",
            "let's say",
        ]
        if any(indicator in message.lower() for indicator in whatif_indicators):
            whatif_start = time.perf_counter()
            try:
                from src.intelligence.simulation import MentalSimulationEngine

                sim_engine = MentalSimulationEngine()
                quick_result = await sim_engine.quick_simulate(
                    user_id=user_id, question=message
                )
                whatif_result = {
                    "answer": quick_result.answer,
                    "key_points": quick_result.key_points,
                    "confidence": quick_result.confidence,
                }
            except Exception as e:
                logger.warning("What-if simulation failed: %s", e)
            whatif_ms = (time.perf_counter() - whatif_start) * 1000

        # Temporal analysis: Detect if user is making a decision and run cross-scale analysis
        temporal_result: dict[str, Any] | None = None
        temporal_ms = 0.0
        decision_indicators = [
            "should i",
            "thinking about",
            "considering",
            "deciding between",
            "weighing",
            "need to decide",
            "my options are",
            "trying to choose",
            "which option",
            "better to",
            "go with",
        ]

        if any(indicator in message.lower() for indicator in decision_indicators):
            temporal_start = time.perf_counter()
            try:
                from src.intelligence.temporal import (
                    MultiScaleTemporalReasoner,
                    TemporalAnalysisRequest,
                )

                reasoner = MultiScaleTemporalReasoner(
                    llm_client=self._llm_client,
                    db_client=get_supabase_client(),
                )

                temporal_analysis = await reasoner.analyze_decision(
                    user_id=user_id,
                    decision=message,
                )

                temporal_result = {
                    "primary_scale": temporal_analysis.primary_scale.value,
                    "conflicts": [
                        {
                            "type": c.conflict_type,
                            "description": c.description,
                            "severity": c.severity,
                        }
                        for c in temporal_analysis.conflicts
                    ],
                    "recommendations": {
                        scale: rec.recommendation
                        for scale, rec in temporal_analysis.recommendations.items()
                    },
                    "overall_alignment": temporal_analysis.overall_alignment,
                }

                logger.info(
                    "Temporal analysis completed for decision",
                    extra={
                        "user_id": user_id,
                        "primary_scale": temporal_analysis.primary_scale.value,
                        "conflicts": len(temporal_analysis.conflicts),
                        "alignment": temporal_analysis.overall_alignment,
                    },
                )

            except Exception as e:
                logger.warning("Temporal analysis failed: %s", e)
            temporal_ms = (time.perf_counter() - temporal_start) * 1000

        # If skill execution produced results, inject them into the LLM context
        if skill_result and skill_result.get("skill_summaries"):
            skill_context = (
                "\n\n## Skill Execution Results\n"
                "ARIA executed the following skills to gather real-time data "
                "for this request. Incorporate these results into your response:\n\n"
                f"{skill_result['skill_summaries']}"
            )
            system_prompt = system_prompt + skill_context

        # If temporal analysis was performed, inject insights into LLM context
        if temporal_result and temporal_result.get("conflicts"):
            temporal_context = (
                "\n\n## Multi-Scale Temporal Analysis\n"
                f"The user appears to be making a decision. Analysis across time scales shows:\n"
                f"- Primary time scale: {temporal_result['primary_scale']}\n"
                f"- Overall alignment: {temporal_result['overall_alignment']}\n"
                f"- Conflicts detected: {len(temporal_result['conflicts'])}\n\n"
                "Detected conflicts:\n"
                + "\n".join(
                    f"- {c['description']} (severity: {c['severity']:.0%})"
                    for c in temporal_result["conflicts"]
                )
                + "\n\nConsider these cross-scale implications in your response. "
                "If there are conflicts, suggest ways to balance short-term and long-term considerations."
            )
            system_prompt = system_prompt + temporal_context

        # If what-if simulation produced results, inject them into LLM context
        if whatif_result:
            whatif_context = (
                "\n\n## What-If Simulation Results\n"
                f"ARIA ran a scenario simulation:\n"
                f"Answer: {whatif_result['answer']}\n"
                f"Key points: {', '.join(whatif_result['key_points'])}\n"
                f"Confidence: {whatif_result['confidence']:.0%}\n"
                "Incorporate these simulation results into your response."
            )
            system_prompt = system_prompt + whatif_context

        # Generate response from LLM with timing (with optional email tools)
        llm_start = time.perf_counter()

        if email_integration:
            # Add email capability context to system prompt
            provider_name = email_integration.get("integration_type", "email").title()
            system_prompt += (
                f"\n\n## Email Access\n"
                f"You have access to the user's {provider_name} email via tools. "
                f"When they ask about emails, inbox, messages, or anything email-related, "
                f"use the email tools to fetch real data. Do NOT say you can't access emails.\n"
                f"You can also DRAFT replies to emails. When the user asks to draft, write, "
                f"or reply to an email, use the draft_email_reply tool. It will find the "
                f"email, gather full context, generate a style-matched draft, and save it "
                f"to their {provider_name} drafts folder. Include any special instructions "
                f"the user mentions (e.g. 'keep it brief', 'mention the Q3 timeline')."
            )

            response_text = await self._run_tool_loop(
                messages=conversation_messages,
                system_prompt=system_prompt,
                tools=EMAIL_TOOL_DEFINITIONS,
                user_id=user_id,
                email_integration=email_integration,
            )
        else:
            response_text = await self._llm_client.generate_response(
                messages=conversation_messages,
                system_prompt=system_prompt,
            )

        llm_ms = (time.perf_counter() - llm_start) * 1000

        # Add assistant response to working memory with skill metadata
        assistant_metadata: dict[str, Any] = {}
        if skill_result:
            assistant_metadata["skill_plan_id"] = skill_result.get("plan_id")
            assistant_metadata["skill_status"] = skill_result.get("status")
        working_memory.add_message("assistant", response_text, metadata=assistant_metadata)

        # Build citations from used memories
        citations = self._build_citations(memories)

        # Persist messages, update metadata, extract information
        await self.persist_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=response_text,
            assistant_metadata=assistant_metadata if assistant_metadata else None,
            conversation_context=conversation_messages[-2:],
        )

        # Companion post-response hooks (narrative increment + theory of mind store)
        if companion_ctx is not None and self._companion_orchestrator is not None:
            try:
                await self._companion_orchestrator.post_response_hooks(
                    user_id=user_id,
                    mental_state_dict=companion_ctx.mental_state,
                    session_id=conversation_id,
                )
            except Exception as e:
                logger.warning("Companion post-response hooks failed: %s", e)

        # Store conversation turn as episodic memory (unique to non-streaming path)
        try:
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="conversation",
                content=f"User asked: {message}\nARIA responded: {response_text[:500]}",
                participants=[user_id, "aria"],
                occurred_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                context={
                    "conversation_id": conversation_id,
                    "memory_count": len(memories),
                    "had_skill_execution": skill_result is not None,
                },
            )
            await self._episodic_memory.store_episode(episode)
        except Exception as e:
            logger.warning("Failed to store episodic memory: %s", e)

        total_ms = (time.perf_counter() - total_start) * 1000

        # Build rich_content from skill execution results
        rich_content: list[dict[str, Any]] = []
        ui_commands: list[dict[str, Any]] = []
        suggestions: list[str] = []

        if skill_result:
            if skill_result.get("status") == "pending_approval":
                rich_content.append(
                    {
                        "type": "execution_plan",
                        "data": {
                            "plan_id": skill_result.get("plan_id"),
                            "risk_level": skill_result.get("risk_level"),
                            "reasoning": skill_result.get("reasoning"),
                            "steps": skill_result.get("steps", []),
                        },
                    }
                )
            elif skill_result.get("working_memory"):
                # Completed skill execution — surface artifacts as rich content
                for entry in skill_result["working_memory"]:
                    artifacts = entry.get("artifacts") or {}
                    if artifacts.get("rich_content_type"):
                        rich_content.append(
                            {
                                "type": artifacts["rich_content_type"],
                                "data": artifacts,
                            }
                        )

        # Add temporal analysis to rich_content if conflicts were found
        if temporal_result and temporal_result.get("conflicts"):
            rich_content.append(
                {
                    "type": "temporal_analysis",
                    "data": {
                        "primary_scale": temporal_result["primary_scale"],
                        "conflicts": temporal_result["conflicts"],
                        "recommendations": temporal_result["recommendations"],
                        "overall_alignment": temporal_result["overall_alignment"],
                    },
                }
            )

        # Generate companion-driven ui_commands from response + context
        if companion_ctx is not None and self._companion_orchestrator is not None:
            try:
                companion_commands = self._companion_orchestrator.generate_ui_commands(
                    response_text, companion_ctx
                )
                ui_commands.extend(companion_commands)
            except Exception as e:
                logger.warning("Companion ui_commands generation failed: %s", e)

        result: dict[str, Any] = {
            "message": response_text,
            "citations": citations,
            "conversation_id": conversation_id,
            "rich_content": rich_content,
            "ui_commands": ui_commands,
            "suggestions": suggestions,
            "timing": {
                "memory_query_ms": round(memory_ms, 2),
                "proactive_query_ms": round(proactive_ms, 2),
                "web_grounding_ms": round(web_grounding_ms, 2),
                "email_check_ms": round(email_check_ms, 2),
                "friction_ms": round(friction_ms, 2),
                "skill_detection_ms": round(skill_ms, 2),
                "whatif_simulation_ms": round(whatif_ms, 2),
                "temporal_analysis_ms": round(temporal_ms, 2),
                "companion_context_ms": round(companion_ctx.build_time_ms, 2) if companion_ctx else 0.0,
                "llm_response_ms": round(llm_ms, 2),
                "total_ms": round(total_ms, 2),
            },
            "cognitive_load": {
                "level": load_state.level.value,
                "score": round(load_state.score, 3),
                "recommendation": load_state.recommendation,
            },
            "proactive_insights": [insight.to_dict() for insight in proactive_insights],
        }

        # Include skill execution data in response if present
        if skill_result:
            result["skill_execution"] = {
                "plan_id": skill_result.get("plan_id"),
                "status": skill_result.get("status"),
                "steps_completed": skill_result.get("steps_completed", 0),
                "steps_failed": skill_result.get("steps_failed", 0),
            }

        # Check if ARIA can request autonomy upgrade after successful skill execution
        if skill_result and skill_result.get("status") == "completed":
            try:
                trust_svc = self._get_trust_service()
                if trust_svc:
                    skill_agent = skill_result.get("agent_type", "general")
                    category = _AGENT_TO_CATEGORY.get(skill_agent, "general")
                    can_upgrade = await trust_svc.can_request_autonomy_upgrade(
                        user_id, category
                    )
                    if can_upgrade:
                        autonomy_request = await trust_svc.format_autonomy_request(
                            user_id, category
                        )
                        result["autonomy_request"] = autonomy_request
            except Exception as e:
                logger.warning("Autonomy upgrade check failed: %s", e)

        return result

    async def _run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        user_id: str,
        email_integration: dict[str, Any],
        max_rounds: int = 3,
    ) -> str:
        """Run the LLM with tools, executing tool calls in a loop.

        If the LLM requests a tool call, execute it, feed the result back,
        and let the LLM generate a final text response. Limits to max_rounds
        to prevent runaway loops.

        Args:
            messages: Conversation messages for the LLM.
            system_prompt: The system prompt.
            tools: Tool definitions (Anthropic format).
            user_id: The user's ID.
            email_integration: The user's email integration record.
            max_rounds: Max tool-call round-trips.

        Returns:
            Final text response from the LLM.
        """
        current_messages = list(messages)

        for _round in range(max_rounds):
            response = await self._llm_client.generate_response_with_tools(
                messages=current_messages,
                tools=tools,
                system_prompt=system_prompt,
                user_id=user_id,
            )

            # If no tool calls, return the text response
            if not response.tool_calls:
                return response.text or "I wasn't able to process that request."

            # Build the assistant message with all content blocks
            assistant_content: list[dict[str, Any]] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })

            current_messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call and build tool_result messages
            tool_results: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                logger.info(
                    "Executing email tool %s for user %s",
                    tc.name,
                    user_id,
                )
                result = await execute_email_tool(
                    tool_name=tc.name,
                    params=tc.input,
                    user_id=user_id,
                    integration=email_integration,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

            current_messages.append({"role": "user", "content": tool_results})

        # If we exhausted rounds, do one final call without tools
        final_response = await self._llm_client.generate_response(
            messages=current_messages,
            system_prompt=system_prompt,
        )
        return final_response

    async def _query_relevant_memories(
        self,
        user_id: str,
        query: str,
        memory_types: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Query memories relevant to the current message."""
        return await self._memory_service.query(
            user_id=user_id,
            query=query,
            memory_types=memory_types,
            start_date=None,
            end_date=None,
            min_confidence=0.5,
            limit=limit,
            offset=0,
        )

    async def _get_proactive_insights(
        self,
        user_id: str,
        current_message: str,
        conversation_messages: list[dict[str, Any]] | None = None,
    ) -> list[ProactiveInsight]:
        """Get proactive insights for current context.

        Args:
            user_id: User identifier
            current_message: Current message content
            conversation_messages: Optional conversation history

        Returns:
            List of relevant proactive insights
        """
        try:
            return await self._proactive_service.find_volunteerable_context(
                user_id=user_id,
                current_message=current_message,
                conversation_messages=conversation_messages or [],
            )
        except Exception as e:
            logger.warning("Failed to get proactive insights: %s", e)
            return []

    async def _get_personality_calibration(
        self,
        user_id: str,
    ) -> PersonalityCalibration | None:
        """Load Digital Twin personality calibration for tone matching.

        Args:
            user_id: User identifier.

        Returns:
            PersonalityCalibration if available, None otherwise.
        """
        try:
            return await self._personality_calibrator.get_calibration(user_id)
        except Exception as e:
            logger.warning("Failed to load personality calibration: %s", e)
            return None

    async def _get_style_guidelines(
        self,
        user_id: str,
    ) -> str | None:
        """Fetch Digital Twin writing style fingerprint for content generation.

        Only returns guidelines when a real fingerprint exists (not the
        generic fallback from get_style_guidelines).

        Args:
            user_id: User identifier.

        Returns:
            Style guidelines string if a fingerprint exists, None otherwise.
        """
        try:
            fingerprint = await self._digital_twin.get_fingerprint(user_id)
            if not fingerprint:
                return None
            return await self._digital_twin.get_style_guidelines(user_id)
        except Exception as e:
            logger.warning("Failed to load Digital Twin style guidelines: %s", e)
            return None

    async def _get_priming_context(
        self,
        user_id: str,
        initial_message: str,
    ) -> ConversationContext | None:
        """Prime conversation with recent episodes, open threads, and salient facts.

        Args:
            user_id: User identifier.
            initial_message: The user's current message for entity relevance.

        Returns:
            ConversationContext if available, None otherwise.
        """
        try:
            return await self._priming_service.prime_conversation(
                user_id=user_id,
                initial_message=initial_message,
            )
        except Exception as e:
            logger.warning("Failed to prime conversation: %s", e)
            return None

    def _build_system_prompt(
        self,
        memories: list[dict[str, Any]],
        load_state: CognitiveLoadState | None = None,
        proactive_insights: list[ProactiveInsight] | None = None,
        personality: PersonalityCalibration | None = None,
        style_guidelines: str | None = None,
        priming_context: ConversationContext | None = None,
        web_context: dict[str, Any] | None = None,
        companion_context: Any = None,
    ) -> str:
        """Build system prompt with all context layers.

        Args:
            memories: List of memory dicts to include as context.
            load_state: Optional cognitive load state for response adaptation.
            proactive_insights: Optional list of insights to volunteer.
            personality: Optional personality calibration from Digital Twin.
            style_guidelines: Optional writing style fingerprint from Digital Twin.
            priming_context: Optional conversation priming context.
            web_context: Optional web-grounded context from Exa.
            companion_context: Optional CompanionContext from orchestrator
                (replaces personality + style_guidelines when present).

        Returns:
            Formatted system prompt string.
        """
        # Separate memories by type for dedicated prompt sections
        general_memories = []
        procedural_memories = []
        prospective_memories = []
        lead_memories = []

        for mem in memories:
            mt = mem.get("memory_type", "")
            if mt == "procedural":
                procedural_memories.append(mem)
            elif mt == "prospective":
                prospective_memories.append(mem)
            elif mt == "lead":
                lead_memories.append(mem)
            else:
                general_memories.append(mem)

        # Build general memory context (episodic + semantic)
        if not general_memories:
            memory_context = ""
        else:
            memory_lines = []
            for mem in general_memories:
                confidence_str = ""
                if mem.get("confidence") is not None:
                    confidence_str = f" (confidence: {mem['confidence']:.0%})"
                memory_lines.append(f"- [{mem['memory_type']}] {mem['content']}{confidence_str}")

            memory_context = MEMORY_CONTEXT_TEMPLATE.format(memories="\n".join(memory_lines))

        base_prompt = ARIA_SYSTEM_PROMPT.format(memory_context=memory_context)

        # Add dedicated procedural memory section
        if procedural_memories:
            workflow_lines = [f"- {mem['content']}" for mem in procedural_memories]
            base_prompt += "\n\n" + PROCEDURAL_CONTEXT_TEMPLATE.format(
                workflows="\n".join(workflow_lines)
            )

        # Add dedicated prospective memory section
        if prospective_memories:
            task_lines = [f"- {mem['content']}" for mem in prospective_memories]
            base_prompt += "\n\n" + PROSPECTIVE_CONTEXT_TEMPLATE.format(tasks="\n".join(task_lines))

        # Add dedicated lead memory section
        if lead_memories:
            lead_lines = [f"- {mem['content']}" for mem in lead_memories]
            base_prompt += "\n\n" + LEAD_CONTEXT_TEMPLATE.format(leads="\n".join(lead_lines))

        # Add companion context OR fall back to individual personality/style sections
        if companion_context is not None:
            companion_sections = companion_context.to_system_prompt_sections()
            if companion_sections:
                base_prompt = base_prompt + "\n\n" + companion_sections
        else:
            # Fallback: Add personality calibration from Digital Twin
            if personality and personality.tone_guidance:
                examples_text = ""
                if personality.example_adjustments:
                    examples_text = "Examples:\n" + "\n".join(
                        f"- {ex}" for ex in personality.example_adjustments
                    )
                personality_context = PERSONALITY_CONTEXT_TEMPLATE.format(
                    tone_guidance=personality.tone_guidance,
                    examples=examples_text,
                )
                base_prompt = base_prompt + "\n\n" + personality_context

            # Fallback: Add Digital Twin writing style fingerprint
            if style_guidelines:
                style_context = WRITING_STYLE_TEMPLATE.format(
                    style_guidelines=style_guidelines,
                )
                base_prompt = base_prompt + "\n\n" + style_context

        # Add conversation priming context (recent episodes, open threads, salient facts)
        if priming_context and priming_context.formatted_context:
            priming_section = PRIMING_CONTEXT_TEMPLATE.format(
                priming_context=priming_context.formatted_context,
            )
            base_prompt = base_prompt + "\n\n" + priming_section

        # Add proactive insights if available
        if proactive_insights:
            insight_lines = []
            for insight in proactive_insights:
                insight_lines.append(
                    f"- [{insight.insight_type.value}] {insight.content} ({insight.explanation})"
                )
            proactive_context = PROACTIVE_INSIGHTS_TEMPLATE.format(
                insights="\n".join(insight_lines)
            )
            base_prompt = base_prompt + "\n\n" + proactive_context

        # Add web-grounded context if available
        if web_context:
            web_context_str = self._format_web_context(web_context)
            if web_context_str:
                web_section = WEB_GROUNDING_TEMPLATE.format(web_context=web_context_str)
                base_prompt = base_prompt + "\n\n" + web_section

        # Add high load instruction if needed
        if load_state and load_state.level in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
            base_prompt = HIGH_LOAD_INSTRUCTION + "\n\n" + base_prompt

        return base_prompt

    async def _build_system_prompt_v2(
        self,
        user_id: str,
        memories: list[dict[str, Any]],
        load_state: CognitiveLoadState | None = None,
        proactive_insights: list[ProactiveInsight] | None = None,
        priming_context: ConversationContext | None = None,
        web_context: dict[str, Any] | None = None,
        companion_context: Any = None,
    ) -> str:
        """Build system prompt using PersonaBuilder (v2).

        Delegates all prompt assembly to PersonaBuilder.build_chat_system_prompt().
        Falls back to _build_system_prompt if PersonaBuilder fails.

        Args:
            user_id: The user's ID.
            memories: List of memory dicts.
            load_state: Optional cognitive load state.
            proactive_insights: Optional proactive insights.
            priming_context: Optional conversation priming context.
            web_context: Optional web-grounded context.
            companion_context: Optional CompanionContext.

        Returns:
            Formatted system prompt string.
        """
        try:
            if self._persona_builder is None:
                from src.core.persona import get_persona_builder

                self._persona_builder = get_persona_builder()

            from src.core.persona import PersonaRequest

            request = PersonaRequest(
                user_id=user_id,
                memories=memories,
                priming_context=priming_context,
                companion_context=companion_context,
                load_state=load_state,
                proactive_insights=proactive_insights,
                web_context=web_context,
            )
            return await self._persona_builder.build_chat_system_prompt(request)

        except Exception as e:
            logger.warning("PersonaBuilder v2 prompt failed, falling back: %s", e)
            # Fallback to existing method
            personality = await self._get_personality_calibration(user_id)
            style_guidelines = await self._get_style_guidelines(user_id)
            return self._build_system_prompt(
                memories, load_state, proactive_insights,
                personality, style_guidelines, priming_context,
                web_context, companion_context=companion_context,
            )

    def _build_citations(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build citations list from memories."""
        return [
            {
                "id": mem["id"],
                "type": mem["memory_type"],
                "content": (
                    mem["content"][:100] + "..." if len(mem["content"]) > 100 else mem["content"]
                ),
                "confidence": mem.get("confidence"),
            }
            for mem in memories
        ]

    def _format_web_context(self, web_context: dict[str, Any]) -> str:
        """Format web grounding context for LLM inclusion.

        Args:
            web_context: Dict from WebGroundingService.detect_and_ground().

        Returns:
            Formatted string for LLM context, or empty string if no content.
        """
        context_type = web_context.get("type", "")

        if context_type == "factual_answer":
            return f"**Direct Answer:** {web_context.get('answer', '')}"

        elif context_type == "company_intelligence":
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
                parts.append(f"**Recent News:**\n" + "\n".join(news_items))
            return "\n\n".join(parts) if parts else ""

        elif context_type == "person_intelligence":
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

        elif context_type == "web_results":
            results = web_context.get("results", [])
            if results:
                formatted = []
                for r in results[:3]:
                    date_str = f" ({r.get('published_date', '')})" if r.get("published_date") else ""
                    formatted.append(f"- **{r.get('title', 'Source')}**{date_str}\n  {r.get('snippet', '')}")
                return "**Web Results:**\n" + "\n".join(formatted)
            return ""

        return ""
