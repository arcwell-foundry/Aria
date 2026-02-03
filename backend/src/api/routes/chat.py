"""Chat API routes for memory-integrated conversations."""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import NotFoundError
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


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: str
    citations: list[Citation]
    conversation_id: str
    timing: Timing | None = None


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


@router.get("/conversations/{conversation_id}", response_model=ConversationListResponse)
async def get_conversation(
    current_user: CurrentUser,
    conversation_id: str,
) -> ConversationListResponse:
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
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ConversationListResponse(
        conversations=[m.to_dict() for m in messages],
        total=len(messages),
    )


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
        raise HTTPException(status_code=404, detail=str(e)) from e

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
        raise HTTPException(status_code=404, detail=str(e)) from e

    logger.info(
        "Conversation deleted via API",
        extra={
            "user_id": current_user.id,
            "conversation_id": conversation_id,
        },
    )

    return {"status": "deleted", "id": conversation_id}
