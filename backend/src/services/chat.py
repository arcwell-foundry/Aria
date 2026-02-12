"""Chat service with memory integration.

This service handles chat interactions by:
1. Querying relevant memories before generating a response
2. Including memory context in the LLM prompt
3. Updating working memory with the conversation flow
4. Extracting and storing new information from the chat
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
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
from src.services.extraction import ExtractionService

logger = logging.getLogger(__name__)

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

# Skill detection confidence threshold
_SKILL_CONFIDENCE_THRESHOLD = 0.7


class ChatService:
    """Service for memory-integrated chat interactions."""

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

        # Skill detection — lazily initialized on first use
        self._skill_registry: Any = None
        self._skill_orchestrator: Any = None
        self._skill_registry_initialized = False

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
            memory_types = ["episodic", "semantic", "procedural", "prospective"]

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

        # Get proactive insights to volunteer
        proactive_start = time.perf_counter()
        proactive_insights = await self._get_proactive_insights(
            user_id=user_id,
            current_message=message,
            conversation_messages=conversation_messages,
        )
        proactive_ms = (time.perf_counter() - proactive_start) * 1000

        # Load Digital Twin personality calibration for style matching
        personality = await self._get_personality_calibration(user_id)

        # Fetch Digital Twin writing style fingerprint for content generation
        style_guidelines = await self._get_style_guidelines(user_id)

        # Prime conversation with recent episodes, open threads, and salient facts
        priming_context = await self._get_priming_context(user_id, message)

        # Build system prompt with all context layers
        system_prompt = self._build_system_prompt(
            memories,
            load_state,
            proactive_insights,
            personality,
            style_guidelines,
            priming_context,
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
                "cognitive_load_level": load_state.level.value,
                "has_style_guidelines": style_guidelines is not None,
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

        # If skill execution produced results, inject them into the LLM context
        if skill_result and skill_result.get("skill_summaries"):
            skill_context = (
                "\n\n## Skill Execution Results\n"
                "ARIA executed the following skills to gather real-time data "
                "for this request. Incorporate these results into your response:\n\n"
                f"{skill_result['skill_summaries']}"
            )
            system_prompt = system_prompt + skill_context

        # Generate response from LLM with timing
        llm_start = time.perf_counter()
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

        # Persist both messages to the messages table
        try:
            from src.services.conversations import ConversationService as _ConvService

            conv_svc = _ConvService(db_client=get_supabase_client())
            await conv_svc.save_message(
                conversation_id=conversation_id,
                role="user",
                content=message,
            )
            await conv_svc.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                metadata=assistant_metadata if assistant_metadata else None,
            )
        except Exception as e:
            logger.warning(
                "Message persistence failed",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )

        # Build citations from used memories
        citations = self._build_citations(memories)

        # Extract and store new information (fire and forget)
        try:
            await self._extraction_service.extract_and_store(
                conversation=conversation_messages[-2:],
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(
                "Information extraction failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Store conversation turn as episodic memory
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

        # Update conversation metadata for sidebar
        await self._update_conversation_metadata(user_id, conversation_id, message)

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
                "skill_detection_ms": round(skill_ms, 2),
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

        return result

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
    ) -> str:
        """Build system prompt with all context layers.

        Args:
            memories: List of memory dicts to include as context.
            load_state: Optional cognitive load state for response adaptation.
            proactive_insights: Optional list of insights to volunteer.
            personality: Optional personality calibration from Digital Twin.
            style_guidelines: Optional writing style fingerprint from Digital Twin.
            priming_context: Optional conversation priming context.

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

        # Add personality calibration from Digital Twin
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

        # Add Digital Twin writing style fingerprint
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

        # Add high load instruction if needed
        if load_state and load_state.level in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
            base_prompt = HIGH_LOAD_INSTRUCTION + "\n\n" + base_prompt

        return base_prompt

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
