"""Chat API routes for memory-integrated conversations."""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.services.chat import ChatService

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


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: str
    citations: list[Citation]
    conversation_id: str


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
    )
