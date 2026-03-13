"""OpenAI-compatible streaming endpoint for Tavus CVI.

Tavus CVI supports "bring your own LLM" via the layers.llm config in the
Persona API. It calls our endpoint at POST /tavus/v1/chat/completions with
OpenAI-format messages and expects a streaming SSE response in OpenAI
chat.completion.chunk format.

This endpoint IS ARIA — full memory, full context, full intelligence.
"""

import json
import logging
import re
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.core.config import settings
from src.core.llm import LLMClient
from src.core.task_types import TaskType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tavus", tags=["tavus-llm"])

# Pre-compile pattern for extracting user_id from system message
_USER_ID_PATTERN = re.compile(r"user_id:([0-9a-f\-]{36})")

# Spoken-mode system prompt injected alongside ARIA persona context
SPOKEN_MODE_RULES = """
CRITICAL SPEECH RULES — you are being spoken aloud by a realistic avatar:
- Maximum 2 sentences per response. Then stop completely.
- Never use bullet points, headers, asterisks, or markdown — spoken word only.
- Never say "I" to start a sentence.
- Never ask "shall I continue?" — just deliver and stop.
- Never say "great question" or any filler. Get to the answer.
- Numbers: say "eleven AM" not "11 AM". Say "seven days" not "7 days".
- If you don't know something, say "Don't have that right now" in one sentence.
- Speak like Jarvis: calm, precise, already knows everything.
"""


def _extract_user_id(messages: list[dict]) -> str | None:
    """Extract user_id from the system message content.

    Tavus passes the system prompt we configured at conversation creation.
    We inject ``user_id:<uuid>`` into that prompt so we can identify the user
    without requiring JWT auth.

    Args:
        messages: OpenAI-format message list from Tavus.

    Returns:
        User UUID string if found, None otherwise.
    """
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            match = _USER_ID_PATTERN.search(content)
            if match:
                return match.group(1)
    return None


def _validate_api_key(request: Request) -> None:
    """Validate the API key from the Authorization header.

    Args:
        request: The incoming FastAPI request.

    Raises:
        HTTPException: If the API key is missing or invalid.
    """
    secret = settings.TAVUS_LLM_SECRET
    if not secret:
        logger.error("TAVUS_LLM_SECRET not configured — rejecting request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Endpoint not configured",
        )

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )

    token = auth_header[7:]  # strip "Bearer "
    if token != secret:
        logger.warning("Tavus LLM endpoint: invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@router.post("/v1/chat/completions")
async def tavus_chat_completions(request: Request) -> StreamingResponse:
    """OpenAI-compatible streaming chat endpoint for Tavus CVI.

    Tavus sends standard OpenAI chat completion requests here.  We validate
    the shared API key, identify the user from the system message, build
    ARIA's full persona context, and stream back OpenAI-format SSE chunks
    powered by Claude Sonnet via LiteLLM.
    """
    _validate_api_key(request)

    body = await request.json()
    messages: list[dict] = body.get("messages", [])

    if not messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages array is required",
        )

    # --- Identify user ---
    user_id = _extract_user_id(messages)
    if not user_id:
        logger.warning("Tavus LLM: no user_id found in system message")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id not found in system message",
        )

    logger.info(
        "Tavus LLM request received",
        extra={"user_id": user_id, "message_count": len(messages)},
    )

    # --- Extract latest user message ---
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user message found",
        )

    # --- Build full ARIA persona context ---
    # Reuse the integration TavusClient's context pipeline which calls
    # PersonaBuilder with all 8 layers + capability context + spoken mode.
    try:
        from src.integrations.tavus import get_tavus_client

        tavus_client = get_tavus_client()
        system_prompt = await tavus_client._build_full_persona_context(user_id)
    except Exception as e:
        logger.warning(
            "Tavus LLM: persona context build failed, using fallback: %s", e
        )
        # Minimal fallback so the conversation still works
        system_prompt = (
            "You are ARIA, an autonomous AI colleague for life sciences "
            "commercial teams. You are speaking via live video avatar."
        )

    # Append the strict spoken-mode rules
    system_prompt += SPOKEN_MODE_RULES

    # --- Build conversation history for LLM ---
    # Pass prior messages (excluding the system message and latest user message)
    # as conversation context so ARIA has multi-turn awareness.
    conversation_history: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue  # We build our own system prompt
        conversation_history.append({"role": role, "content": content})

    # --- Stream response in OpenAI format ---
    llm_client = LLMClient()

    async def generate():
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        # Opening chunk with role
        opening = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aria-1",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(opening)}\n\n"

        try:
            async for token in llm_client.stream_response(
                messages=conversation_history,
                system_prompt=system_prompt,
                user_id=user_id,
                task=TaskType.TAVUS_CVI_STREAM,
                agent_id="tavus_cvi",
                temperature=0.7,
                max_tokens=300,  # Keep responses short for spoken output
            ):
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "aria-1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception:
            logger.exception(
                "Tavus LLM streaming failed",
                extra={"user_id": user_id},
            )
            # Send error as final content chunk so Tavus can read it
            error_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "aria-1",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "Apologies, having a brief technical issue."},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"

        # Done chunk
        done_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aria-1",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(done_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
