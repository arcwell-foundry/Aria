"""Chat service with memory integration.

This service handles chat interactions by:
1. Querying relevant memories before generating a response
2. Including memory context in the LLM prompt
3. Updating working memory with the conversation flow
4. Extracting and storing new information from the chat
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from src.api.routes.memory import MemoryQueryService
from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.cognitive_load import CognitiveLoadMonitor
from src.intelligence.proactive_memory import ProactiveMemoryService
from src.memory.working import WorkingMemoryManager
from src.models.cognitive_load import CognitiveLoadState, LoadLevel
from src.models.proactive_insight import ProactiveInsight
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

PROACTIVE_INSIGHTS_TEMPLATE = """## Relevant Context ARIA Can Mention

The following insights may be worth volunteering to the user if relevant:

{insights}

You may naturally mention these in your response when appropriate, without explicitly stating where the information came from."""

HIGH_LOAD_INSTRUCTION = """
IMPORTANT: The user appears to be under high cognitive load right now. Adapt your response:
- Be extremely concise and direct
- Lead with the most important information
- Avoid asking multiple questions
- Offer to handle tasks independently
- Use bullet points for clarity
"""


class ChatService:
    """Service for memory-integrated chat interactions."""

    def __init__(self) -> None:
        """Initialize chat service with dependencies."""
        self._memory_service = MemoryQueryService()
        self._llm_client = LLMClient()
        self._working_memory_manager = WorkingMemoryManager()
        self._extraction_service = ExtractionService()
        db = get_supabase_client()
        self._cognitive_monitor = CognitiveLoadMonitor(db_client=db)
        self._proactive_service = ProactiveMemoryService(db_client=db)

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
        assistant_message: str,
    ) -> None:
        """Update conversation metadata after message exchange.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.
            user_message: The user's message content.
            assistant_message: The assistant's response content.

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
            memory_types = ["episodic", "semantic"]

        # Get or create working memory for this conversation
        working_memory = self._working_memory_manager.get_or_create(
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

        # Build system prompt with memory context, load adaptation, and proactive insights
        system_prompt = self._build_system_prompt(memories, load_state, proactive_insights)

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
            },
        )

        # Generate response from LLM with timing
        llm_start = time.perf_counter()
        response_text = await self._llm_client.generate_response(
            messages=conversation_messages,
            system_prompt=system_prompt,
        )
        llm_ms = (time.perf_counter() - llm_start) * 1000

        # Add assistant response to working memory
        working_memory.add_message("assistant", response_text)

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

        # Update conversation metadata for sidebar
        await self._update_conversation_metadata(user_id, conversation_id, message, response_text)

        total_ms = (time.perf_counter() - total_start) * 1000

        return {
            "message": response_text,
            "citations": citations,
            "conversation_id": conversation_id,
            "timing": {
                "memory_query_ms": round(memory_ms, 2),
                "proactive_query_ms": round(proactive_ms, 2),
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

    def _build_system_prompt(
        self,
        memories: list[dict[str, Any]],
        load_state: CognitiveLoadState | None = None,
        proactive_insights: list[ProactiveInsight] | None = None,
    ) -> str:
        """Build system prompt with memory context, load adaptation, and proactive insights.

        Args:
            memories: List of memory dicts to include as context.
            load_state: Optional cognitive load state for response adaptation.
            proactive_insights: Optional list of insights to volunteer.

        Returns:
            Formatted system prompt string.
        """
        if not memories:
            memory_context = ""
        else:
            memory_lines = []
            for mem in memories:
                confidence_str = ""
                if mem.get("confidence") is not None:
                    confidence_str = f" (confidence: {mem['confidence']:.0%})"
                memory_lines.append(f"- [{mem['memory_type']}] {mem['content']}{confidence_str}")

            memory_context = MEMORY_CONTEXT_TEMPLATE.format(memories="\n".join(memory_lines))

        base_prompt = ARIA_SYSTEM_PROMPT.format(memory_context=memory_context)

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
