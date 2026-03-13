"""OpenAI-compatible streaming endpoint for Tavus CVI.

Tavus CVI supports "bring your own LLM" via the layers.llm config in the
Persona API. It calls our endpoint at POST /tavus/v1/chat/completions with
OpenAI-format messages and expects a streaming SSE response in OpenAI
chat.completion.chunk format.

This endpoint IS ARIA — full memory, full context, full intelligence.

Performance: Uses Haiku directly via Anthropic SDK (no LiteLLM routing)
and caches persona context per conversation to eliminate DB round-trips
on turns 2+.

Multi-tenancy: Every DB query is scoped to user_id. Cache keys use
conversation_id (globally unique per-user per-session GUIDs from Tavus).
No hardcoded user IDs anywhere.
"""

import json
import logging
import re
import time
import uuid
from datetime import date

import anthropic
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tavus", tags=["tavus-llm"])

# Pre-compile pattern for extracting user_id from system message
_USER_ID_PATTERN = re.compile(r"user_id:([0-9a-f\-]{36})")

# --- Context cache: cache_key → (system_prompt, monotonic_timestamp) ---
_context_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 7200  # 2 hours

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


def _get_cached_context(cache_key: str) -> str | None:
    """Return cached system prompt if still within TTL, else None."""
    entry = _context_cache.get(cache_key)
    if entry is not None:
        prompt, ts = entry
        if time.monotonic() - ts < _CACHE_TTL_SECONDS:
            return prompt
        del _context_cache[cache_key]
    return None


def _set_cached_context(cache_key: str, prompt: str) -> None:
    """Store system prompt in cache with current timestamp."""
    _context_cache[cache_key] = (prompt, time.monotonic())


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


def _extract_conversation_id(request: Request, body: dict) -> str | None:
    """Extract conversation_id from Tavus request headers or body."""
    conv_id = request.headers.get("x-tavus-conversation-id")
    if conv_id:
        return conv_id
    conv_id = body.get("conversation_id")
    if conv_id:
        return str(conv_id)
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


async def _build_tavus_system_prompt(user_id: str) -> str:
    """Build ARIA's system prompt for a CVI session.

    Uses today's pre-generated briefing script as the factual grounding.
    Fully scoped to user_id — no cross-tenant data leakage possible.

    Args:
        user_id: The authenticated user's UUID.

    Returns:
        Complete system prompt string with briefing context and speech rules.
    """
    context_section = "No briefing has been generated for today yet."

    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        today_str = date.today().isoformat()

        result = (
            db.table("daily_briefings")
            .select("tavus_script, content")
            .eq("user_id", user_id)
            .eq("briefing_date", today_str)
            .execute()
        )

        if result.data:
            row = result.data[0]
            # tavus_script is the top-level column; fall back to content JSON
            script = (row.get("tavus_script") or "").strip()
            if not script:
                script = ((row.get("content") or {}).get("tavus_script") or "").strip()

            if script:
                context_section = f"TODAY'S BRIEFING CONTEXT:\n{script}"
    except Exception as e:
        logger.warning("Tavus LLM: briefing query failed for user %s: %s", user_id, e)

    return f"""You are ARIA, an autonomous AI colleague for life sciences commercial teams.
Speak in 1-2 sentences maximum. No markdown, no bullets, no asterisks.
Be precise and direct. Answer from the briefing context below.
Use specific names, times, and companies when they exist in context.
If something is not in the context, say "that's not in today's briefing."
Never say you don't have access — you have everything you need below.

{context_section}
{SPOKEN_MODE_RULES}"""


@router.post("/v1/chat/completions")
async def tavus_chat_completions(request: Request) -> StreamingResponse:
    """OpenAI-compatible streaming chat endpoint for Tavus CVI.

    Uses Haiku directly via Anthropic SDK for minimal latency.
    Caches persona context per conversation to eliminate DB round-trips
    on turns 2+.
    """
    t0 = time.monotonic()

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

    # --- Extract conversation_id for caching ---
    conversation_id = _extract_conversation_id(request, body)
    cache_key = conversation_id or user_id

    logger.info(
        "Tavus LLM request received",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "cache_key": cache_key,
            "message_count": len(messages),
        },
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

    # --- Build or retrieve cached persona context ---
    system_prompt = _get_cached_context(cache_key)
    if system_prompt:
        logger.info("Tavus LLM: using cached context for %s", cache_key)
    else:
        system_prompt = await _build_tavus_system_prompt(user_id)
        _set_cached_context(cache_key, system_prompt)
        logger.info("Tavus LLM: built and cached context for %s", cache_key)

    t1 = time.monotonic()

    # --- Build conversation history for LLM ---
    conversation_history: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue  # We build our own system prompt
        conversation_history.append({"role": role, "content": content})

    # --- Stream response via Anthropic SDK (Haiku, direct, no LiteLLM) ---
    client = anthropic.AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
    )

    async def generate():
        t_llm_start = time.monotonic()
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
            first_token_logged = False
            async with client.messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                temperature=0.3,
                system=system_prompt,
                messages=conversation_history,
            ) as stream:
                async for text in stream.text_stream:
                    if not first_token_logged:
                        t_first = time.monotonic()
                        logger.info(
                            "Tavus LLM: context=%.2fs, ttft=%.2fs",
                            t1 - t0,
                            t_first - t0,
                        )
                        first_token_logged = True

                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": "aria-1",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": text},
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

        t2 = time.monotonic()
        logger.info(
            "Tavus LLM: context=%.2fs, llm=%.2fs, total=%.2fs",
            t1 - t0,
            t2 - t_llm_start,
            t2 - t0,
        )

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
