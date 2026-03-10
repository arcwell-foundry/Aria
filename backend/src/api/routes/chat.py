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
from src.core.task_types import TaskType
from src.db.supabase import get_supabase_client
from src.services.chat import DEFAULT_MEMORY_TYPES, ChatService
from src.services.conversations import ConversationService
from src.services.email_tools import get_email_context_for_chat, get_email_integration

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
    intent_detected: str | None = None


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

    raw_rich = result.get("rich_content", [])
    raw_ui = result.get("ui_commands", [])
    raw_suggestions = result.get("suggestions", [])
    if not raw_suggestions:
        raw_suggestions = await _generate_personalized_suggestions(
            result["message"],
            [],
            current_user.id,
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
        intent_detected=result.get("intent_detected"),
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

        # --- Signal Enrichment Bypass (MUST BE FIRST ROUTING DECISION) ---
        # If the message matches a known signal headline, enrich with signal context
        # and skip ALL goal routing to preserve signal context in conversational response
        enriched_message = await service._enrich_message_with_signal_context(
            current_user.id, request.message
        )
        was_signal_enriched = (enriched_message != request.message)

        if was_signal_enriched:
            logger.info(
                "SIGNAL_BYPASS: Message was signal-enriched, skipping intent classification "
                "and routing to conversational response"
            )
            # Update working memory with enriched message for LLM context
            working_memory.messages.pop()  # Remove original message
            working_memory.add_message("user", enriched_message)  # Add enriched version

        # --- Quick Action Detection (BEFORE intent classification) ---
        quick_action_match = None
        if not was_signal_enriched:
            quick_action_match = ChatService._match_quick_action(request.message)
            if quick_action_match:
                logger.info(
                    "QUICK_ACTION: Pattern matched, routing to quick action handler: %s",
                    quick_action_match.get("action_type"),
                )

        # --- Direct Execute Detection (BEFORE intent classification) ---
        direct_execute_match = None
        if not was_signal_enriched and not quick_action_match:
            direct_execute_match = ChatService._match_direct_execute(request.message)
            if direct_execute_match:
                logger.info(
                    "DIRECT_EXECUTE: Pattern matched, routing to direct handler: %s",
                    direct_execute_match.get("action_type"),
                )

        # --- Inline Intent Detection (before building system prompt) ---
        # Skip if signal-enriched OR quick action matched OR direct execute matched
        intent_result = None
        if not was_signal_enriched and not quick_action_match and not direct_execute_match:
            intent_result = await service._classify_intent(current_user.id, request.message)

        # --- Quick Action Routing ---
        if quick_action_match or (intent_result and intent_result.get("is_quick_action")):
            action_intent = quick_action_match or intent_result
            logger.info("QUICK_ACTION: Routing to handler, action_type=%s", action_intent.get("action_type"))

            # Send metadata event
            metadata = {
                "type": "metadata",
                "message_id": message_id,
                "conversation_id": conversation_id,
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            try:
                result = await service._handle_quick_action(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    message=request.message,
                    intent=action_intent,
                    working_memory=working_memory,
                    conversation_messages=conversation_messages,
                )
            except Exception:
                logger.exception(
                    "Quick action handling failed",
                    extra={"user_id": current_user.id},
                )
                error_event = {
                    "type": "token",
                    "content": "I understood your request but ran into a problem. Please try again.",
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                complete_event = {
                    "type": "complete",
                    "rich_content": [],
                    "ui_commands": [],
                    "suggestions": ["Try again"],
                    "intent_detected": "quick_action",
                }
                yield f"data: {json.dumps(complete_event)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Stream response as a single token chunk (simulated streaming for consistent UX)
            response_text = result.get("response", "")
            token_event = {"type": "token", "content": response_text}
            yield f"data: {json.dumps(token_event)}\n\n"

            # Send completion event
            complete_event = {
                "type": "complete",
                "rich_content": result.get("rich_content", []),
                "ui_commands": result.get("ui_commands", []),
                "suggestions": result.get("suggestions", []),
                "intent_detected": "quick_action",
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
            yield "data: [DONE]\n\n"
            return

        # --- Direct Execute Routing ---
        if direct_execute_match or (intent_result and intent_result.get("is_direct_execute")):
            execute_intent = direct_execute_match or intent_result
            logger.info(
                "DIRECT_EXECUTE: Routing to handler, action_type=%s",
                execute_intent.get("action_type"),
            )

            # Send metadata event
            metadata = {
                "type": "metadata",
                "message_id": message_id,
                "conversation_id": conversation_id,
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            try:
                result = await service._handle_direct_execute(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    message=request.message,
                    intent=execute_intent,
                    working_memory=working_memory,
                    conversation_messages=conversation_messages,
                )
            except Exception:
                logger.exception(
                    "Direct execute handling failed",
                    extra={"user_id": current_user.id},
                )
                error_event = {
                    "type": "token",
                    "content": "I tried to handle that directly but ran into a problem. Please try again.",
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                complete_event = {
                    "type": "complete",
                    "rich_content": [],
                    "ui_commands": [],
                    "suggestions": ["Try again"],
                    "intent_detected": "direct_execute",
                }
                yield f"data: {json.dumps(complete_event)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Stream response as a single token chunk
            response_text = result.get("response", "")
            token_event = {"type": "token", "content": response_text}
            yield f"data: {json.dumps(token_event)}\n\n"

            # Send completion event
            complete_event = {
                "type": "complete",
                "rich_content": result.get("rich_content", []),
                "ui_commands": result.get("ui_commands", []),
                "suggestions": result.get("suggestions", []),
                "intent_detected": "direct_execute",
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
            yield "data: [DONE]\n\n"
            return

        if intent_result and intent_result.get("is_goal"):
            # Short-circuit: emit goal plan instead of streaming a chat response
            metadata = {
                "type": "metadata",
                "message_id": message_id,
                "conversation_id": conversation_id,
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            # Handle goal creation + planning
            try:
                goal_response = await service._handle_goal_intent(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    message=request.message,
                    intent=intent_result,
                    working_memory=working_memory,
                    conversation_messages=conversation_messages,
                    load_state=load_state,
                )
            except Exception:
                logger.exception(
                    "Goal intent handling failed",
                    extra={
                        "user_id": current_user.id,
                        "conversation_id": conversation_id,
                    },
                )
                error_event = {
                    "type": "token",
                    "content": (
                        "I understood your request but ran into a problem setting "
                        "it up. Please try again or check the Actions page."
                    ),
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                complete_event = {
                    "type": "complete",
                    "rich_content": [],
                    "ui_commands": [{"action": "navigate", "route": "/actions"}],
                    "suggestions": ["Try again", "Show me my goals"],
                    "intent_detected": "goal",
                }
                yield f"data: {json.dumps(complete_event)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Emit the brief ARIA text as token events
            for token_chunk in [goal_response["message"]]:
                event = {"type": "token", "content": token_chunk}
                yield f"data: {json.dumps(event)}\n\n"

            # Emit completion with rich_content containing the execution plan
            goal_ui_commands = goal_response.get("ui_commands", [])
            if not goal_ui_commands:
                goal_ui_commands = [{"action": "navigate", "route": "/actions"}]
            complete_event = {
                "type": "complete",
                "rich_content": goal_response.get("rich_content", []),
                "ui_commands": goal_ui_commands,
                "suggestions": goal_response.get("suggestions", []),
                "intent_detected": "goal",
            }
            yield f"data: {json.dumps(complete_event)}\n\n"

            yield "data: [DONE]\n\n"
            return

        # --- Check for pending plan interactions (skip if signal-enriched, quick action, or direct execute) ---
        plan_action = None
        if not was_signal_enriched and not quick_action_match and not direct_execute_match and not (intent_result and intent_result.get("is_quick_action")):
            plan_action = await service._classify_plan_action(current_user.id, request.message)
        if plan_action and plan_action["action"] in ("approve", "modify", "retry_plan"):
            # Short-circuit: handle plan action
            metadata = {
                "type": "metadata",
                "message_id": message_id,
                "conversation_id": conversation_id,
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            try:
                if plan_action["action"] == "retry_plan":
                    plan_response = await service._handle_goal_intent(
                        user_id=current_user.id,
                        conversation_id=conversation_id,
                        message=request.message,
                        intent={
                            "is_goal": True,
                            "goal_title": plan_action["goal"].get("title", request.message[:100]),
                            "goal_type": plan_action["goal"].get("goal_type", "research"),
                            "goal_description": plan_action["goal"].get("description", request.message),
                            "existing_goal_id": plan_action["goal_id"],
                        },
                        working_memory=working_memory,
                        conversation_messages=conversation_messages,
                        load_state=load_state,
                    )
                elif plan_action["action"] == "approve":
                    plan_response = await service._handle_plan_approval_from_chat(
                        user_id=current_user.id,
                        conversation_id=conversation_id,
                        message=request.message,
                        goal_id=plan_action["goal_id"],
                        goal=plan_action["goal"],
                        working_memory=working_memory,
                        load_state=load_state,
                    )
                else:
                    plan_response = await service._handle_plan_modification(
                        user_id=current_user.id,
                        conversation_id=conversation_id,
                        message=request.message,
                        goal_id=plan_action["goal_id"],
                        goal=plan_action["goal"],
                        current_tasks=plan_action["plan_tasks"],
                        working_memory=working_memory,
                        load_state=load_state,
                    )
            except Exception:
                logger.exception(
                    "Plan action handling failed",
                    extra={
                        "user_id": current_user.id,
                        "goal_id": plan_action["goal_id"],
                        "action": plan_action["action"],
                    },
                )
                error_event = {
                    "type": "token",
                    "content": (
                        "I ran into a problem processing your plan action. "
                        "Please try again."
                    ),
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                complete_event = {
                    "type": "complete",
                    "rich_content": [],
                    "ui_commands": [],
                    "suggestions": ["Try again", "Show me the plan"],
                }
                yield f"data: {json.dumps(complete_event)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Emit response as token + complete events
            token_event = {"type": "token", "content": plan_response["message"]}
            yield f"data: {json.dumps(token_event)}\n\n"

            complete_event = {
                "type": "complete",
                "rich_content": plan_response.get("rich_content", []),
                "ui_commands": plan_response.get("ui_commands", []),
                "suggestions": plan_response.get("suggestions", []),
                "intent_detected": plan_response.get("intent_detected"),
            }
            yield f"data: {json.dumps(complete_event)}\n\n"

            yield "data: [DONE]\n\n"
            return

        # --- Normal conversational streaming path ---

        # --- Cognitive Friction check (fail-open) ---
        from src.core.cognitive_friction import (
            FRICTION_CHALLENGE,
            FRICTION_FLAG,
            FRICTION_REFUSE,
            get_cognitive_friction_engine,
        )

        friction_decision = None
        try:
            friction_engine = get_cognitive_friction_engine()
            friction_decision = await friction_engine.evaluate(
                user_id=current_user.id,
                user_request=request.message,
            )

            if friction_decision and friction_decision.level in (
                FRICTION_CHALLENGE,
                FRICTION_REFUSE,
            ):
                # Short-circuit: emit friction pushback as response
                metadata_evt = {
                    "type": "metadata",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                }
                yield f"data: {json.dumps(metadata_evt)}\n\n"

                friction_msg = friction_decision.user_message or (
                    "Let me make sure I understand what you're asking before proceeding."
                )
                token_event = {"type": "token", "content": friction_msg}
                yield f"data: {json.dumps(token_event)}\n\n"

                complete_event = {
                    "type": "complete",
                    "rich_content": [
                        {
                            "type": "friction_decision",
                            "data": {
                                "level": friction_decision.level,
                                "message": friction_msg,
                            },
                        }
                    ],
                    "ui_commands": [],
                    "suggestions": ["Yes, proceed", "Let me rephrase"],
                }
                yield f"data: {json.dumps(complete_event)}\n\n"
                yield "data: [DONE]\n\n"
                return
        except Exception as e:
            logger.warning("SSE cognitive friction check failed (proceeding): %s", e)

        # --- Parallel context gathering (fail-open, 5s timeout per subsystem) ---
        import asyncio as _aio

        _CTX_TIMEOUT = 5.0

        async def _safe(coro, default=None, label="unknown"):
            try:
                return await _aio.wait_for(coro, timeout=_CTX_TIMEOUT)
            except Exception as e:
                logger.warning("SSE %s failed (%.1fs): %s", label, _CTX_TIMEOUT, e)
                return default

        # Lazy-init services (synchronous, cheap)
        if service._web_grounding is None:
            from src.services.chat import WebGroundingService

            service._web_grounding = WebGroundingService()
        if service._causal_reasoning is None:
            from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

            service._causal_reasoning = SalesCausalReasoningEngine(
                db_client=get_supabase_client()
            )
        if service._user_model_service is None:
            from src.intelligence.user_model import UserMentalModelService

            service._user_model_service = UserMentalModelService(
                db_client=get_supabase_client()
            )
        if service._companion_orchestrator is None:
            from src.companion.factory import create_companion_orchestrator

            service._companion_orchestrator = create_companion_orchestrator()

        (
            web_context,
            proactive_insights,
            causal_result,
            user_mental_model,
            companion_ctx,
            email_integration,
            email_activity_ctx,
            priming_context,
            active_goals,
            digital_twin_calibration,
            capability_context,
        ) = await _aio.gather(
            _safe(service._web_grounding.detect_and_ground(request.message), None, "web_grounding"),
            _safe(service._get_proactive_insights(
                user_id=current_user.id,
                current_message=request.message,
                conversation_messages=conversation_messages,
            ), [], "proactive"),
            _safe(service._causal_reasoning.analyze_recent_signals(
                current_user.id, limit=3, hours_back=24,
            ), None, "causal"),
            _safe(service._user_model_service.get_model(current_user.id), None, "user_model"),
            _safe(service._companion_orchestrator.build_full_context(
                user_id=current_user.id,
                message=request.message,
                conversation_history=conversation_messages,
                session_id=conversation_id,
            ), None, "companion"),
            _safe(get_email_integration(current_user.id), None, "email_integration"),
            _safe(get_email_context_for_chat(current_user.id), None, "email_context"),
            _safe(service._get_priming_context(current_user.id, request.message), None, "priming"),
            _safe(service._get_active_goals(current_user.id), [], "goals"),
            _safe(service._get_digital_twin_calibration(current_user.id), None, "digital_twin"),
            _safe(service._get_capability_context(current_user.id), None, "capability"),
        )

        # Extract causal actions from result
        causal_actions = (
            causal_result.actions
            if causal_result and hasattr(causal_result, "actions")
            else []
        )

        # Fall back to individual calls if companion orchestrator failed
        if companion_ctx is not None:
            personality = None
            style_guidelines = None
        else:
            personality = await service._get_personality_calibration(current_user.id)
            style_guidelines = await service._get_style_guidelines(current_user.id)

        # Build system prompt — use PersonaBuilder (v2) for full ARIA identity
        if service._use_persona_builder:
            system_prompt = await service._build_system_prompt_v2(
                current_user.id,
                memories,
                load_state,
                proactive_insights,
                priming_context,
                web_context,
                companion_context=companion_ctx,
                active_goals=active_goals,
                digital_twin_calibration=digital_twin_calibration,
                capability_context=capability_context,
                causal_actions=causal_actions,
                user_mental_model=user_mental_model,
            )
        else:
            system_prompt = service._build_system_prompt(
                memories,
                load_state,
                proactive_insights,
                personality,
                style_guidelines,
                priming_context,
                web_context,
                companion_context=companion_ctx,
                active_goals=active_goals,
                digital_twin_calibration=digital_twin_calibration,
                capability_context=capability_context,
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

        # Inject email awareness into system prompt
        if email_integration:
            provider_name = email_integration.get("integration_type", "email").title()
            system_prompt += (
                f"\n\n## Email Access\n"
                f"You have access to the user's {provider_name} email. "
                f"When they ask about emails, inbox, messages, or anything email-related, "
                f"you CAN see their emails. Do NOT say you can't access emails.\n"
                f"You can also DRAFT replies to emails."
                f"\n\n## Email Intelligence Rules\n"
                f"1. FACTS you can state directly: sender name, subject line, date, "
                f"direct quotes from email content.\n"
                f"2. INFERENCES you must hedge: any connection between an email and "
                f"a goal, deal, or lead.\n"
                f"3. When presenting email summaries, distinguish what you read in "
                f"the email from what you are inferring about its significance.\n"
                f"4. If you are uncertain about a connection, say so."
            )
        if email_activity_ctx:
            system_prompt += email_activity_ctx

        # Inject pending plan context for discuss/unrelated plan interactions
        pending_plan_ctx = await service._get_pending_plan_context(current_user.id)
        if pending_plan_ctx:
            system_prompt += f"\n\n{pending_plan_ctx}"

        # Debug: log system prompt to verify ARIA identity
        logger.info(
            "SSE_SYSTEM_PROMPT_DEBUG_START\n%s\nSSE_SYSTEM_PROMPT_DEBUG_END",
            system_prompt[:2000],
        )

        # --- Skill-aware routing (before LLM streaming) ---
        skill_result = None
        try:
            extend_plan_id = await service._detect_plan_extension(
                current_user.id, conversation_id, request.message
            )
            if extend_plan_id:
                skill_result = await service._route_through_skill(
                    current_user.id,
                    conversation_id,
                    request.message,
                    extend_plan_id=extend_plan_id,
                )
            else:
                should_route, _ranked, _conf = await service._detect_skill_match(
                    request.message
                )
                if should_route:
                    skill_result = await service._route_through_skill(
                        current_user.id,
                        conversation_id,
                        request.message,
                    )
        except Exception as e:
            logger.warning("SSE skill detection/routing error: %s", e)

        if skill_result and skill_result.get("message"):
            # Short-circuit: emit skill result as token events
            metadata_evt = {
                "type": "metadata",
                "message_id": message_id,
                "conversation_id": conversation_id,
            }
            yield f"data: {json.dumps(metadata_evt)}\n\n"

            skill_msg = skill_result["message"]
            token_event = {"type": "token", "content": skill_msg}
            yield f"data: {json.dumps(token_event)}\n\n"

            working_memory.add_message("assistant", skill_msg)
            await service._working_memory_manager.persist_session(conversation_id)
            await service.persist_turn(
                user_id=current_user.id,
                conversation_id=conversation_id,
                user_message=request.message,
                assistant_message=skill_msg,
                assistant_metadata={"skill_execution": True},
                conversation_context=conversation_messages[-2:],
            )

            skill_rich = skill_result.get("rich_content", [])
            skill_ui = skill_result.get("ui_commands", [])
            skill_sug = skill_result.get("suggestions", [])
            if not skill_sug:
                skill_sug = await _generate_personalized_suggestions(
                    skill_msg, conversation_messages[-4:], current_user.id,
                )

            complete_event = {
                "type": "complete",
                "rich_content": skill_rich,
                "ui_commands": skill_ui,
                "suggestions": skill_sug,
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
            yield "data: [DONE]\n\n"
            return

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
                task=TaskType.CHAT_STREAM,
                agent_id="chat",
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

        # Companion post-response hooks (narrative increment + theory of mind)
        if companion_ctx is not None and service._companion_orchestrator is not None:
            try:
                await service._companion_orchestrator.post_response_hooks(
                    user_id=current_user.id,
                    mental_state_dict=companion_ctx.mental_state,
                    session_id=conversation_id,
                )
            except Exception as e:
                logger.warning("SSE companion post-response hooks failed: %s", e)

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
        ui_commands: list[dict] = []

        # Generate companion-driven ui_commands from response + context
        if companion_ctx is not None and service._companion_orchestrator is not None:
            try:
                companion_commands = service._companion_orchestrator.generate_ui_commands(
                    full_content, companion_ctx
                )
                ui_commands.extend(companion_commands)
            except Exception as e:
                logger.warning("SSE companion ui_commands generation failed: %s", e)

        suggestions = await _generate_personalized_suggestions(
            full_content, conversation_messages[-4:], current_user.id,
        )

        complete_event = {
            "type": "complete",
            "rich_content": rich_content,
            "ui_commands": ui_commands,
            "suggestions": suggestions,
        }
        yield f"data: {json.dumps(complete_event)}\n\n"

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


async def _generate_personalized_suggestions(
    response: str,
    conversation: list[dict],
    user_id: str,
) -> list[str]:
    """Generate personalized follow-up suggestions using LLM.

    Calls a cheap/fast Haiku model to produce 2-3 context-aware follow-ups
    based on the full conversation and response. Falls back to the keyword
    heuristic ``_generate_suggestions()`` on any error.

    Args:
        response: The assistant's latest response text.
        conversation: Recent conversation messages.
        user_id: The user ID (for tracing).

    Returns:
        List of 2-3 suggestion strings.
    """
    try:
        from src.core.llm import LLMClient

        llm = LLMClient()
        recent = conversation[-4:] if len(conversation) > 4 else conversation
        history_text = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent
        )
        prompt_messages = [
            {
                "role": "user",
                "content": (
                    "Based on this conversation, suggest 2-3 short follow-up questions "
                    "the user might want to ask. Return ONLY a JSON array of strings, "
                    "no other text.\n\n"
                    f"Recent conversation:\n{history_text}\n\n"
                    f"Latest assistant response:\n{response[:500]}"
                ),
            }
        ]
        raw = await llm.generate(
            prompt_messages,
            task=TaskType.SUGGEST_FOLLOWUP,
            system_prompt="You are ARIA, an autonomous AI colleague. Generate short, actionable follow-up suggestions that move work forward.",
            user_id=user_id,
        )
        import json as _json

        suggestions = _json.loads(raw)
        if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
            return suggestions[:4]
    except Exception:
        logger.debug("Personalized suggestion generation failed, using heuristics", exc_info=True)

    return _generate_suggestions(response, conversation)
