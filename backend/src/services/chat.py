"""Chat service with memory integration.

This service handles chat interactions by:
1. Querying relevant memories before generating a response
2. Including memory context in the LLM prompt
3. Updating working memory with the conversation flow
4. Extracting and storing new information from the chat
"""

import logging
from typing import Any

from src.api.routes.memory import MemoryQueryService
from src.core.llm import LLMClient
from src.memory.working import WorkingMemoryManager
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


class ChatService:
    """Service for memory-integrated chat interactions."""

    def __init__(self) -> None:
        """Initialize chat service with dependencies."""
        self._memory_service = MemoryQueryService()
        self._llm_client = LLMClient()
        self._working_memory_manager = WorkingMemoryManager()
        self._extraction_service = ExtractionService()

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
            Dict containing response message and citations.
        """
        if memory_types is None:
            memory_types = ["episodic", "semantic"]

        # Get or create working memory for this conversation
        working_memory = self._working_memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Add user message to working memory
        working_memory.add_message("user", message)

        # Query relevant memories
        memories = await self._query_relevant_memories(
            user_id=user_id,
            query=message,
            memory_types=memory_types,
        )

        # Build system prompt with memory context
        system_prompt = self._build_system_prompt(memories)

        # Get conversation history
        conversation_messages = working_memory.get_context_for_llm()

        logger.info(
            "Processing chat message",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "memory_count": len(memories),
                "message_count": len(conversation_messages),
            },
        )

        # Generate response from LLM
        response_text = await self._llm_client.generate_response(
            messages=conversation_messages,
            system_prompt=system_prompt,
        )

        # Add assistant response to working memory
        working_memory.add_message("assistant", response_text)

        # Build citations from used memories
        citations = self._build_citations(memories)

        # Extract and store new information (fire and forget)
        # This runs after response is generated to not block the user
        try:
            await self._extraction_service.extract_and_store(
                conversation=conversation_messages[-2:],  # Just the latest exchange
                user_id=user_id,
            )
        except Exception as e:
            # Log but don't fail the response
            logger.warning(
                "Information extraction failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        return {
            "message": response_text,
            "citations": citations,
            "conversation_id": conversation_id,
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

    def _build_system_prompt(self, memories: list[dict[str, Any]]) -> str:
        """Build system prompt with memory context."""
        if not memories:
            return ARIA_SYSTEM_PROMPT.format(memory_context="")

        memory_lines = []
        for mem in memories:
            confidence_str = ""
            if mem.get("confidence") is not None:
                confidence_str = f" (confidence: {mem['confidence']:.0%})"
            memory_lines.append(f"- [{mem['memory_type']}] {mem['content']}{confidence_str}")

        memory_context = MEMORY_CONTEXT_TEMPLATE.format(memories="\n".join(memory_lines))

        return ARIA_SYSTEM_PROMPT.format(memory_context=memory_context)

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
