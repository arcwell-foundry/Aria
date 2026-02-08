"""Chat API routes for memory-integrated conversations."""

import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import NotFoundError, sanitize_error
from src.db.supabase import get_supabase_client
from src.services.chat import ChatService
from src.services.conversations import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str = Field(..., min_length=1, description="User's message")
    conversation_id: str | None = Field(
        None, description="Conversation ID (generated if not provided)"
    )
    memory_types: list[str] | None = Field(
        None, description="Memory types to query (default: episodic, semantic)"
    )


class Citation(BaseModel):
    """A memory citation in the response."""

    id: str
    type: str
    content: str
    confidence: float | None = None


class Timing(BaseModel):
    """Performance timing information."""

    memory_query_ms: float
    llm_response_ms: float
    total_ms: float


class CognitiveLoadInfo(BaseModel):
    """Cognitive load information in chat response."""

    level: str
    score: float
    recommendation: str


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: str
    citations: list[Citation]
    conversation_id: str
    timing: Timing | None = None
    cognitive_load: CognitiveLoadInfo | None = None


class ConversationListResponse(BaseModel):
    """Response for listing conversations."""

    conversations: list[dict]
    total: int


class ConversationTitleRequest(BaseModel):
    """Request to update conversation title."""

    title: str = Field(..., min_length=1, max_length=200)


class ConversationTitleResponse(BaseModel):
    """Response for updating conversation title."""

    id: str
    title: str | None
    message_count: int
    last_message_at: str | None
    last_message_preview: str | None
    updated_at: str


class ConversationMessageResponse(BaseModel):
    """A single message in a conversation."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


@router.post("", response_model=ChatResponse)
async def chat(
    current_user: CurrentUser,
    request: ChatRequest,
) -> ChatResponse:
    """Send a message and receive a memory-aware response."""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    service = ChatService()

    try:
        result = await service.process_message(
            user_id=current_user.id,
            conversation_id=conversation_id,
            message=request.message,
            memory_types=request.memory_types,
        )
    except Exception:
        logger.exception(
            "Chat processing failed",
            extra={
                "user_id": current_user.id,
                "conversation_id": conversation_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Chat service temporarily unavailable",
        ) from None

    logger.info(
        "Chat message processed",
        extra={
            "user_id": current_user.id,
            "conversation_id": conversation_id,
            "citation_count": len(result.get("citations", [])),
        },
    )

    return ChatResponse(
        message=result["message"],
        citations=[Citation(**c) for c in result.get("citations", [])],
        conversation_id=result["conversation_id"],
        timing=Timing(**result["timing"]) if result.get("timing") else None,
        cognitive_load=CognitiveLoadInfo(**result["cognitive_load"])
        if result.get("cognitive_load")
        else None,
    )


@router.post("/stream")
async def chat_stream(
    current_user: CurrentUser,
    request: ChatRequest,
) -> StreamingResponse:
    """Stream a chat response as Server-Sent Events.

    Emits SSE events:
    - {"type": "metadata", "message_id": "...", "conversation_id": "..."}
    - {"type": "token", "content": "..."}
    - [DONE]
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    service = ChatService()

    async def event_stream():  # noqa: C901
        total_start = time.perf_counter()

        memory_types = request.memory_types or ["episodic", "semantic"]

        # Get or create working memory
        working_memory = service._working_memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=current_user.id,
        )

        # Ensure conversation record exists
        await service._ensure_conversation_record(current_user.id, conversation_id)

        # Add user message to working memory
        working_memory.add_message("user", request.message)

        # Query relevant memories
        memories = await service._query_relevant_memories(
            user_id=current_user.id,
            query=request.message,
            memory_types=memory_types,
        )

        # Get conversation context
        conversation_messages = working_memory.get_context_for_llm()

        # Estimate cognitive load
        recent_messages = conversation_messages[-5:]
        load_state = await service._cognitive_monitor.estimate_load(
            user_id=current_user.id,
            recent_messages=recent_messages,
            session_id=conversation_id,
        )

        # Get proactive insights
        proactive_insights = await service._get_proactive_insights(
            user_id=current_user.id,
            current_message=request.message,
            conversation_messages=conversation_messages,
        )

        # Build system prompt
        system_prompt = service._build_system_prompt(
            memories, load_state, proactive_insights
        )

        # Send metadata event
        metadata = {
            "type": "metadata",
            "message_id": message_id,
            "conversation_id": conversation_id,
        }
        yield f"data: {json.dumps(metadata)}\n\n"

        # Stream LLM response
        full_content = ""
        try:
            async for token in service._llm_client.stream_response(
                messages=conversation_messages,
                system_prompt=system_prompt,
            ):
                full_content += token
                event = {"type": "token", "content": token}
                yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception(
                "Streaming chat failed",
                extra={
                    "user_id": current_user.id,
                    "conversation_id": conversation_id,
                },
            )
            error_event = {"type": "error", "content": "Chat service temporarily unavailable"}
            yield f"data: {json.dumps(error_event)}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Add assistant response to working memory
        working_memory.add_message("assistant", full_content)

        # Update conversation metadata
        await service._update_conversation_metadata(
            current_user.id, conversation_id, request.message
        )

        # Extract and store new information (fire and forget)
        try:
            await service._extraction_service.extract_and_store(
                conversation=conversation_messages[-2:],
                user_id=current_user.id,
            )
        except Exception as e:
            logger.warning(
                "Information extraction failed during stream",
                extra={"user_id": current_user.id, "error": str(e)},
            )

        total_ms = (time.perf_counter() - total_start) * 1000
        logger.info(
            "Streaming chat completed",
            extra={
                "user_id": current_user.id,
                "conversation_id": conversation_id,
                "total_ms": round(total_ms, 2),
            },
        )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: CurrentUser,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List all conversations for the current user.

    Args:
        current_user: The authenticated user.
        search: Optional search query to filter by title.
        limit: Maximum number of conversations to return.
        offset: Number of conversations to skip.

    Returns:
        List of conversations ordered by most recently updated.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    conversations = await service.list_conversations(
        user_id=current_user.id,
        search_query=search,
        limit=limit,
        offset=offset,
    )

    # Get total count
    count_result = (
        db.table("conversations")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .execute()
    )
    total = (
        count_result.count
        if hasattr(count_result, "count") and count_result.count is not None
        else len(conversations)
    )

    return ConversationListResponse(
        conversations=[c.to_dict() for c in conversations],
        total=total,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageResponse],
)
async def get_conversation_messages(
    current_user: CurrentUser,
    conversation_id: str,
) -> list[ConversationMessageResponse]:
    """Get messages for a specific conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.

    Returns:
        List of messages in the conversation.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        messages = await service.get_conversation_messages(
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    except NotFoundError as e:
        logger.exception("Conversation not found for messages")
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e

    return [
        ConversationMessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.put("/conversations/{conversation_id}/title", response_model=ConversationTitleResponse)
async def update_conversation_title(
    current_user: CurrentUser,
    conversation_id: str,
    request: ConversationTitleRequest,
) -> ConversationTitleResponse:
    """Update the title of a conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.
        request: Request containing new title.

    Returns:
        Updated conversation metadata.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        conversation = await service.update_conversation_title(
            user_id=current_user.id,
            conversation_id=conversation_id,
            title=request.title,
        )
    except NotFoundError as e:
        logger.exception("Conversation not found for title update")
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e

    return ConversationTitleResponse(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at.isoformat()
        if conversation.last_message_at
        else None,
        last_message_preview=conversation.last_message_preview,
        updated_at=conversation.updated_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    current_user: CurrentUser,
    conversation_id: str,
) -> dict[str, str]:
    """Delete a conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.

    Returns:
        Success message.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        await service.delete_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    except NotFoundError as e:
        logger.exception("Conversation not found for deletion")
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e

    logger.info(
        "Conversation deleted via API",
        extra={
            "user_id": current_user.id,
            "conversation_id": conversation_id,
        },
    )

    return {"status": "deleted", "id": conversation_id}
