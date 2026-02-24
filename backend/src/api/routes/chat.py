"""Chat API routes for memory-integrated conversations."""

import asyncio
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
from src.services.chat import DEFAULT_MEMORY_TYPES, ChatService
from src.services.conversations import ConversationService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background intent detection → goal creation
# ---------------------------------------------------------------------------


async def _detect_and_create_goal(
    message_text: str, user_id: str, conversation_id: str
) -> None:
    """Background task: detect goal intent in a chat message, create a goal + plan.

    This runs fire-and-forget after the main chat response is sent.
    Errors are logged but never propagated to the caller.
    """
    logger.warning(
        "INTENT_DETECT START: msg='%.80s' user=%s conv=%s",
        message_text, user_id, conversation_id,
    )
    try:
        from src.core.llm import LLMClient
        from src.models.goal import GoalCreate, GoalType
        from src.services.goal_execution import GoalExecutionService
        from src.services.goal_service import GoalService

        # Guard: skip if user already has a pending plan_ready goal
        db = get_supabase_client()
        plan_ready = (
            db.table("goals")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "plan_ready")
            .limit(1)
            .execute()
        )
        if plan_ready.data:
            logger.warning(
                "INTENT_DETECT: skipping — user has plan_ready goal %s",
                plan_ready.data[0]["id"],
            )
            return

        intent_prompt = (
            "Analyze this user message and determine if it implies a goal "
            "or task that ARIA should plan and execute autonomously.\n\n"
            f'User message: "{message_text}"\n\n'
            "A message implies a goal if the user wants ARIA to:\n"
            "- Research, analyze, or investigate something\n"
            "- Find, compare, or evaluate options\n"
            "- Monitor, track, or watch for changes\n"
            "- Create, draft, prepare, or write something\n"
            "- Schedule, plan, or organize something\n"
            "- Build a strategy, report, or recommendation\n\n"
            "Do NOT classify as a goal if the message is:\n"
            "- Casual conversation, greetings, or small talk\n"
            "- A simple factual question (what is X, who is Y)\n"
            "- Feedback on a previous response\n"
            "- A request to explain or clarify something\n"
            "- A single-step task that doesn't need planning\n\n"
            "Respond with ONLY valid JSON (no markdown, no backticks):\n"
            "{\n"
            '  "is_goal": true or false,\n'
            '  "goal_title": "concise title if is_goal is true, else null",\n'
            '  "goal_type": "research|analysis|lead_gen|competitive_intel'
            '|outreach|meeting_prep|territory|custom",\n'
            '  "goal_description": "1-2 sentence description if is_goal '
            'is true, else null"\n'
            "}"
        )

        logger.warning("INTENT_DETECT: calling LLM for classification...")
        llm = LLMClient()
        intent_raw = await llm.generate_response(
            messages=[{"role": "user", "content": intent_prompt}],
            max_tokens=256,
            temperature=0.1,
            user_id=user_id,
        )
        logger.warning("INTENT_DETECT: LLM raw response = %.500s", intent_raw)

        # Strip markdown fences if present
        cleaned = intent_raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        intent = json.loads(cleaned)
        logger.warning("INTENT_DETECT: parsed JSON = %s", intent)

        if not intent.get("is_goal"):
            logger.warning("INTENT_DETECT: is_goal=False, skipping")
            return

        # Map goal_type to enum
        goal_type_str = intent.get("goal_type", "research")
        try:
            goal_type = GoalType(goal_type_str)
        except ValueError:
            goal_type = GoalType.RESEARCH

        goal_data = GoalCreate(
            title=intent.get("goal_title", message_text[:100]),
            description=intent.get("goal_description", message_text),
            goal_type=goal_type,
        )

        logger.warning(
            "INTENT_DETECT: creating goal '%s' type=%s",
            goal_data.title, goal_data.goal_type,
        )
        goal_svc = GoalService()
        goal = await goal_svc.create_goal(user_id, goal_data)

        logger.info(
            "Goal auto-created from chat intent",
            extra={
                "goal_id": goal["id"],
                "user_id": user_id,
                "title": goal_data.title,
            },
        )

        # Generate execution plan — sends plan card via WebSocket + persists
        logger.warning(
            "INTENT_DETECT: goal created id=%s, calling plan_goal()...",
            goal["id"],
        )
        exec_svc = GoalExecutionService()
        await exec_svc.plan_goal(goal["id"], user_id)
        logger.warning(
            "INTENT_DETECT: plan_goal() completed for goal=%s", goal["id"]
        )

    except json.JSONDecodeError as je:
        logger.error(
            "INTENT_DETECT FAILED: JSON parse error: %s | raw='%.300s'",
            je, locals().get("cleaned", "N/A"),
        )
    except Exception as e:
        logger.error(
            "INTENT_DETECT FAILED: %s: %s", type(e).__name__, e,
            exc_info=True,
        )

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


class UICommand(BaseModel):
    """A UI command ARIA can issue to control the frontend.

    Matches the frontend UICommand interface in api/chat.ts.
    """

    action: str
    route: str | None = None
    element: str | None = None
    content: dict | None = None
    effect: str | None = None  # 'glow' | 'pulse' | 'outline'
    duration: int | None = None  # highlight duration in ms
    mode: str | None = None  # 'workspace' | 'dialogue' | 'compact_avatar'
    badge_count: int | None = None
    sidebar_item: str | None = None
    notification_type: str | None = None  # 'signal' | 'alert' | 'success' | 'info'
    notification_message: str | None = None
    modal_id: str | None = None
    modal_data: dict | None = None


class RichContent(BaseModel):
    """A rich content component in ARIA's response."""

    type: str
    data: dict


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: str
    citations: list[Citation] = []
    conversation_id: str
    rich_content: list[RichContent] = []
    ui_commands: list[UICommand] = []
    suggestions: list[str] = []
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
    metadata: dict = {}


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

    # Extract ui_commands from response text if not provided by service
    raw_rich = result.get("rich_content", [])
    raw_ui = result.get("ui_commands", [])
    if not raw_ui:
        raw_ui = _analyze_ui_commands(result["message"])
    raw_suggestions = result.get("suggestions", [])
    if not raw_suggestions:
        raw_suggestions = _generate_suggestions(
            result["message"],
            [],
        )

    # Fire-and-forget intent detection
    asyncio.create_task(
        _detect_and_create_goal(
            request.message, current_user.id, conversation_id
        )
    )

    return ChatResponse(
        message=result["message"],
        citations=[Citation(**c) for c in result.get("citations", [])],
        conversation_id=result["conversation_id"],
        rich_content=[RichContent(**rc) if isinstance(rc, dict) else rc for rc in raw_rich],
        ui_commands=[UICommand(**uc) if isinstance(uc, dict) else uc for uc in raw_ui],
        suggestions=raw_suggestions,
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

        memory_types = request.memory_types or DEFAULT_MEMORY_TYPES

        # Get or create working memory
        working_memory = await service._working_memory_manager.get_or_create(
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

        # Load Digital Twin personality calibration
        personality = await service._get_personality_calibration(current_user.id)

        # Fetch Digital Twin writing style fingerprint
        style_guidelines = await service._get_style_guidelines(current_user.id)

        # Prime conversation with recent episodes, open threads, salient facts
        priming_context = await service._get_priming_context(current_user.id, request.message)

        # Query active goals and digital twin calibration for prompt injection
        active_goals = await service._get_active_goals(current_user.id)
        digital_twin_calibration = await service._get_digital_twin_calibration(current_user.id)

        # Build system prompt with all context layers
        system_prompt = service._build_system_prompt(
            memories,
            load_state,
            proactive_insights,
            personality,
            style_guidelines,
            priming_context,
            active_goals=active_goals,
            digital_twin_calibration=digital_twin_calibration,
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

        # Persist working memory state to Supabase
        await service._working_memory_manager.persist_session(conversation_id)

        # Persist messages, update metadata, extract information
        await service.persist_turn(
            user_id=current_user.id,
            conversation_id=conversation_id,
            user_message=request.message,
            assistant_message=full_content,
            conversation_context=conversation_messages[-2:],
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

        # Build rich_content from proactive insights
        rich_content: list[dict] = []
        for insight in proactive_insights:
            insight_dict = insight.to_dict() if hasattr(insight, "to_dict") else {}
            insight_type = insight_dict.get("type", "")
            if insight_type == "signal":
                rich_content.append({"type": "signal_card", "data": insight_dict})
            elif insight_type in ("goal_update", "goal"):
                rich_content.append({"type": "goal_plan", "data": insight_dict})

        # Emit completion metadata with envelope fields
        ui_commands = _analyze_ui_commands(full_content)
        suggestions = _generate_suggestions(full_content, conversation_messages[-4:])

        complete_event = {
            "type": "complete",
            "rich_content": rich_content,
            "ui_commands": ui_commands,
            "suggestions": suggestions,
        }
        yield f"data: {json.dumps(complete_event)}\n\n"

        yield "data: [DONE]\n\n"

        # Fire-and-forget intent detection after streaming completes
        asyncio.create_task(
            _detect_and_create_goal(
                request.message, current_user.id, conversation_id
            )
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Route aliases for frontend compatibility ---
# Frontend may call /chat/message and /chat/message/stream instead of /chat and /chat/stream.


@router.post("/message", response_model=ChatResponse)
async def chat_message_alias(
    current_user: CurrentUser,
    request: ChatRequest,
) -> ChatResponse:
    """Alias for POST /chat — frontend compat route."""
    return await chat(current_user=current_user, request=request)


@router.post("/message/stream")
async def chat_message_stream_alias(
    current_user: CurrentUser,
    request: ChatRequest,
) -> StreamingResponse:
    """Alias for POST /chat/stream — frontend compat route."""
    return await chat_stream(current_user=current_user, request=request)


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
    try:
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
    except Exception:
        logger.exception("Failed to list conversations")
        return ConversationListResponse(conversations=[], total=0)


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
            metadata=m.metadata or {},
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


# --- Envelope field generators ---

# Navigation keywords mapped to routes
_ROUTE_KEYWORDS: dict[str, str] = {
    "pipeline": "/pipeline",
    "intelligence": "/intelligence",
    "battle card": "/intelligence/battle-cards",
    "communication": "/communications",
    "action": "/actions",
    "briefing": "/briefing",
    "settings": "/settings",
}

# Keywords that indicate an entity should be highlighted in the Intel Panel
_HIGHLIGHT_KEYWORDS: list[tuple[str, str]] = [
    ("deal", "deal-card"),
    ("lead", "lead-card"),
    ("opportunity", "deal-card"),
    ("contact", "contact-card"),
    ("account", "account-card"),
]

# Keywords indicating Intel Panel should update with contextual modules
_INTEL_PANEL_TRIGGERS: dict[str, dict] = {
    "battle card": {"module": "battle_card", "title": "Competitive Intelligence"},
    "competitor": {"module": "competitive_landscape", "title": "Competitive Landscape"},
    "forecast": {"module": "forecast", "title": "Pipeline Forecast"},
    "risk": {"module": "risk_assessment", "title": "Risk Assessment"},
    "goal": {"module": "goal_tracker", "title": "Goal Progress"},
    "meeting": {"module": "meeting_prep", "title": "Meeting Preparation"},
    "signal": {"module": "signals", "title": "Intelligence Signals"},
}


def _analyze_ui_commands(response: str) -> list[dict]:
    """Analyze ARIA's response for UI navigation, highlight, and panel intents.

    Scans for route-related keywords and generates navigate, highlight,
    update_intel_panel, and show_notification commands. This is a heuristic
    approach; the LLM can also produce explicit ui_commands in structured
    responses.

    Args:
        response: The assistant's text response.

    Returns:
        List of UICommand dicts.
    """
    commands: list[dict] = []
    response_lower = response.lower()

    # Navigation: at most one per response
    for keyword, route in _ROUTE_KEYWORDS.items():
        if keyword in response_lower:
            commands.append({"action": "navigate", "route": route})
            break

    # Intel Panel update: surface contextual modules
    for keyword, panel_info in _INTEL_PANEL_TRIGGERS.items():
        if keyword in response_lower:
            commands.append({
                "action": "update_intel_panel",
                "content": {
                    "module": panel_info["module"],
                    "title": panel_info["title"],
                    "source": "conversation",
                },
            })
            break  # One panel update per response

    # Highlight: pulse entities mentioned in the response
    for keyword, element_id in _HIGHLIGHT_KEYWORDS:
        if keyword in response_lower:
            commands.append({
                "action": "highlight",
                "element": element_id,
                "effect": "pulse",
                "duration": 3000,
            })
            break  # One highlight per response

    # Notification for urgent/critical items
    if "urgent" in response_lower or "critical" in response_lower:
        commands.append({
            "action": "show_notification",
            "notification_type": "alert",
            "notification_message": "ARIA flagged items requiring attention",
        })

    return commands


def _generate_suggestions(
    response: str,
    conversation: list[dict],
) -> list[str]:
    """Generate contextual follow-up suggestions.

    Uses simple heuristics based on the response content and
    conversation history. Returns 2-3 follow-up prompts.

    Args:
        response: The assistant's latest response text.
        conversation: Recent conversation messages.

    Returns:
        List of 2-3 suggestion strings.
    """
    suggestions: list[str] = []
    response_lower = response.lower()

    # Conversation history available for future multi-turn heuristics
    _history_len = len(conversation)

    # Context-aware suggestions based on keywords
    if "battle card" in response_lower:
        suggestions.extend(
            [
                "Compare with other competitors",
                "Draft outreach based on this",
            ]
        )
    elif "pipeline" in response_lower:
        suggestions.extend(
            [
                "Which deals need attention?",
                "Show me the forecast",
            ]
        )
    elif "analysis" in response_lower or "landscape" in response_lower:
        suggestions.extend(
            [
                "What are the key risks?",
                "Recommend next steps",
            ]
        )
    elif "email" in response_lower or "draft" in response_lower:
        suggestions.extend(
            [
                "Make it more concise",
                "Adjust the tone",
            ]
        )

    # Always add a generic follow-up if we have fewer than 2
    if len(suggestions) < 2:
        suggestions.append("What should I focus on today?")
    if len(suggestions) < 2:
        suggestions.append("Show me my briefing")

    return suggestions[:4]
