"""WebSocket endpoint for ARIA real-time communication."""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.core.ws import ws_manager
from src.models.ws_events import AriaMessageEvent, ConnectedEvent, PongEvent, ThinkingEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _authenticate_ws_token(token: str) -> Any | None:
    """Validate a JWT token for WebSocket authentication.

    Args:
        token: The JWT token from query parameter.

    Returns:
        User object if valid, None if invalid.
    """
    try:
        from src.db.supabase import SupabaseClient

        client = SupabaseClient.get_client()
        response = client.auth.get_user(token)
        if response is None or response.user is None:
            return None
        return response.user
    except Exception as e:
        logger.warning("WebSocket auth failed: %s", e)
        return None


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str | None = None,
    session_id: str | None = None,
    session: str | None = None,
) -> None:
    """WebSocket endpoint for real-time ARIA communication.

    Args:
        websocket: The WebSocket connection.
        user_id: User ID from URL path.
        token: JWT token for authentication (query param).
        session_id: Optional session ID for session binding (query param).
        session: Alias for session_id (frontend compat).
    """
    # Accept both ?session_id=X and ?session=X
    resolved_session_id = session_id or session

    # Require token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Authenticate — user_id comes from JWT, not from client params
    user = await _authenticate_ws_token(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify user_id matches token (prevents impersonation)
    if user.id != user_id:
        logger.warning(
            "WebSocket user_id mismatch",
            extra={"url_user_id": user_id, "token_user_id": user.id},
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept connection
    await websocket.accept()
    await ws_manager.connect(user_id, websocket, session_id=resolved_session_id)
    logger.info("WS connected: user=%s session=%s", user_id, resolved_session_id)

    # Send connected confirmation
    connected_event = ConnectedEvent(user_id=user_id, session_id=resolved_session_id)
    try:
        await websocket.send_json(connected_event.to_ws_dict())
    except Exception:
        ws_manager.disconnect(user_id, websocket)
        return

    # Drain login message queue (deliver HIGH-priority insights queued while offline)
    await _drain_login_queue(user_id)

    # Generate proactive return greeting if user was away > 1 hour
    await _send_return_greeting(user_id)

    # Message loop
    try:
        while True:
            raw = await websocket.receive_text()

            # Handle raw "ping" string (not JSON-wrapped)
            if raw.strip() == "ping":
                pong = PongEvent()
                await websocket.send_json(pong.to_ws_dict())
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type in ("ping", "heartbeat"):
                pong = PongEvent()
                await websocket.send_json(pong.to_ws_dict())

            elif msg_type == "user.message":
                await _handle_user_message(websocket, data, user_id)

            elif msg_type == "user.navigate":
                payload = data.get("payload", {})
                route = payload.get("route", "")
                logger.info("User navigated", extra={"user_id": user_id, "route": route})

            elif msg_type == "user.approve":
                await _handle_action_approval(websocket, data, user_id)

            elif msg_type == "user.reject":
                await _handle_action_rejection(websocket, data, user_id)

            elif msg_type == "user.undo":
                await _handle_undo_request(websocket, data, user_id)

            elif msg_type == "modality.change":
                payload = data.get("payload", {})
                logger.info(
                    "Modality changed",
                    extra={"user_id": user_id, "modality": payload.get("modality")},
                )

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected",
            extra={"user_id": user_id, "session_id": resolved_session_id},
        )
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={"user_id": user_id, "error": str(e)},
        )
    finally:
        ws_manager.disconnect(user_id, websocket)


async def _drain_login_queue(user_id: str) -> None:
    """Deliver queued messages from login_message_queue on WebSocket connect.

    Fetches undelivered messages from the last 7 days (up to 10), delivers
    them via WebSocket as ARIA messages, and marks them as delivered.
    """
    try:
        from datetime import UTC, datetime, timedelta

        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()

        result = (
            db.table("login_message_queue")
            .select("id, title, message, category")
            .eq("user_id", user_id)
            .eq("delivered", False)
            .gte("created_at", cutoff)
            .order("created_at", desc=False)
            .limit(10)
            .execute()
        )

        messages = result.data or []
        if not messages:
            return

        logger.info(
            "Draining %d login queue messages for user %s",
            len(messages),
            user_id,
        )

        for msg in messages:
            try:
                await ws_manager.send_aria_message(
                    user_id=user_id,
                    message=f"While you were away: {msg['message']}",
                    suggestions=["Tell me more", "Dismiss"],
                )
            except Exception:
                logger.debug(
                    "Failed to deliver login queue message %s",
                    msg["id"],
                )

        # Mark all as delivered
        msg_ids = [m["id"] for m in messages]
        db.table("login_message_queue").update(
            {"delivered": True}
        ).in_("id", msg_ids).execute()

    except Exception:
        # Login queue drain is best-effort — don't break the WebSocket connection
        logger.debug(
            "Login queue drain failed for user %s",
            user_id,
            exc_info=True,
        )


async def _send_return_greeting(user_id: str) -> None:
    """Generate and send a personalized greeting if user was away > 2 hours.

    Checks the ConnectionManager's last_disconnect timestamp and generates
    a personalized greeting via ReturnGreetingService if the absence is
    significant enough. Returns rich content cards for agent results,
    drafts, and signals.
    """
    try:
        from src.services.return_greeting import MIN_ABSENCE_SECONDS, ReturnGreetingService

        absence = ws_manager.get_absence_duration_seconds(user_id)
        if absence is None or absence < MIN_ABSENCE_SECONDS:
            return

        service = ReturnGreetingService()
        result = await service.generate_return_greeting(user_id, absence)
        if result:
            await ws_manager.send_aria_message(
                user_id=user_id,
                message=result["message"],
                rich_content=result.get("rich_content", []),
                suggestions=result.get("suggestions", ["Show me updates"]),
            )
            logger.info(
                "Return greeting sent",
                extra={"user_id": user_id, "absence_hours": round(absence / 3600, 1)},
            )
    except Exception:
        # Return greeting is best-effort — don't break the WebSocket connection
        logger.debug("Return greeting failed for user %s", user_id, exc_info=True)


async def _handle_user_message(
    websocket: WebSocket,
    data: dict[str, Any],
    user_id: str,
) -> None:
    """Handle an incoming user chat message over WebSocket.

    Processes the message through ChatService (memory lookup, LLM streaming,
    persistence) and sends back thinking indicators, token events, and a
    final AriaMessageEvent.
    """
    from src.api.routes.chat import _analyze_ui_commands, _generate_suggestions
    from src.db.supabase import get_supabase_client
    from src.services.chat import DEFAULT_MEMORY_TYPES, ChatService

    payload = data.get("payload", {})
    message_text = payload.get("message", "")
    conversation_id = payload.get("conversation_id")

    if not conversation_id:
        # Try to find the user's most recent conversation before creating a new one
        try:
            db = get_supabase_client()
            result = (
                db.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                conversation_id = result.data[0]["id"]
                logger.info(
                    "Resumed most recent conversation (frontend did not send conversation_id)",
                    extra={"user_id": user_id, "conversation_id": conversation_id},
                )
            else:
                conversation_id = str(uuid.uuid4())
                logger.warning(
                    "Created new conversation — frontend did not send conversation_id",
                    extra={"user_id": user_id, "conversation_id": conversation_id},
                )
        except Exception:
            conversation_id = str(uuid.uuid4())
            logger.warning(
                "Created new conversation — fallback lookup failed",
                extra={"user_id": user_id, "conversation_id": conversation_id},
            )

    if not message_text:
        return

    # Send thinking indicator
    thinking = ThinkingEvent()
    await websocket.send_json(thinking.to_ws_dict())

    try:
        service = ChatService()
        memory_types = DEFAULT_MEMORY_TYPES

        # Get or create working memory
        working_memory = await service._working_memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Ensure conversation record
        await service._ensure_conversation_record(user_id, conversation_id)

        # Add user message to working memory
        working_memory.add_message("user", message_text)

        # Query relevant memories
        memories = await service._query_relevant_memories(
            user_id=user_id,
            query=message_text,
            memory_types=memory_types,
        )

        # Get conversation context
        conversation_messages = working_memory.get_context_for_llm()

        # Estimate cognitive load
        load_state = await service._cognitive_monitor.estimate_load(
            user_id=user_id,
            recent_messages=conversation_messages[-5:],
            session_id=conversation_id,
        )

        # Get proactive insights
        proactive_insights = await service._get_proactive_insights(
            user_id=user_id,
            current_message=message_text,
            conversation_messages=conversation_messages,
        )

        # Digital Twin personality & style
        personality = await service._get_personality_calibration(user_id)
        style_guidelines = await service._get_style_guidelines(user_id)
        priming_context = await service._get_priming_context(user_id, message_text)

        # Build system prompt
        system_prompt = service._build_system_prompt(
            memories,
            load_state,
            proactive_insights,
            personality,
            style_guidelines,
            priming_context,
        )

        # Stream LLM response
        full_content = ""
        try:
            async for token in service._llm_client.stream_response(
                messages=conversation_messages,
                system_prompt=system_prompt,
            ):
                full_content += token
                await websocket.send_json(
                    {
                        "type": "aria.token",
                        "payload": {"content": token, "conversation_id": conversation_id},
                    }
                )

            # Stream completed successfully
            await websocket.send_json(
                {
                    "type": "aria.stream_complete",
                    "payload": {"conversation_id": conversation_id},
                }
            )
        except Exception as stream_err:
            logger.error("LLM stream failed: %s", stream_err)
            await websocket.send_json(
                {
                    "type": "aria.stream_error",
                    "payload": {
                        "error": "I encountered an issue generating my response. Let me try again.",
                        "conversation_id": conversation_id,
                        "recoverable": True,
                    },
                }
            )
            return

        # Add assistant response to working memory
        working_memory.add_message("assistant", full_content)

        # Persist working memory state to Supabase
        await service._working_memory_manager.persist_session(conversation_id)

        # Persist messages, update metadata, extract information
        await service.persist_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message_text,
            assistant_message=full_content,
            conversation_context=conversation_messages[-2:],
        )

        # Build rich_content from proactive insights (mirrors chat service logic)
        rich_content: list[dict] = []
        for insight in proactive_insights:
            insight_dict = insight.to_dict() if hasattr(insight, "to_dict") else {}
            insight_type = insight_dict.get("type", "")
            if insight_type == "signal":
                rich_content.append({
                    "type": "signal_card",
                    "data": insight_dict,
                })
            elif insight_type in ("goal_update", "goal"):
                rich_content.append({
                    "type": "goal_plan",
                    "data": insight_dict,
                })

        # Send complete response
        ui_commands = _analyze_ui_commands(full_content)
        suggestions = _generate_suggestions(full_content, conversation_messages[-4:])

        response_event = AriaMessageEvent(
            message=full_content,
            rich_content=rich_content,
            ui_commands=ui_commands,
            suggestions=suggestions,
        )
        await websocket.send_json(
            {
                **response_event.to_ws_dict(),
                "conversation_id": conversation_id,
            }
        )

    except Exception as chat_err:
        logger.exception("WebSocket chat error: %s", chat_err)
        await websocket.send_json(
            {
                "type": "aria.message",
                "message": "I encountered an error processing your message. Please try again.",
                "rich_content": [],
                "ui_commands": [],
                "suggestions": ["Try again", "What can you help with?"],
                "conversation_id": conversation_id,
            }
        )


async def _handle_action_approval(
    websocket: WebSocket,
    data: dict[str, Any],
    user_id: str,
) -> None:
    """Handle a user.approve event for action queue items."""
    payload = data.get("payload", {})
    action_id = payload.get("action_id")
    if not action_id:
        return
    try:
        from src.services.action_queue_service import ActionQueueService

        svc = ActionQueueService()
        await svc.approve_action(action_id=action_id, user_id=user_id)
        await websocket.send_json(
            {
                "type": "action.completed",
                "payload": {"action_id": action_id, "status": "approved"},
            }
        )
    except Exception as e:
        logger.warning("Action approval failed: %s", e)


async def _handle_action_rejection(
    websocket: WebSocket,
    data: dict[str, Any],
    user_id: str,
) -> None:
    """Handle a user.reject event for action queue items."""
    payload = data.get("payload", {})
    action_id = payload.get("action_id")
    if not action_id:
        return
    try:
        from src.services.action_queue_service import ActionQueueService

        svc = ActionQueueService()
        await svc.reject_action(action_id=action_id, user_id=user_id)
        await websocket.send_json(
            {
                "type": "action.completed",
                "payload": {"action_id": action_id, "status": "rejected"},
            }
        )
    except Exception as e:
        logger.warning("Action rejection failed: %s", e)


async def _handle_undo_request(
    websocket: WebSocket,
    data: dict[str, Any],
    user_id: str,
) -> None:
    """Handle a user.undo event — undo a recently executed action."""
    payload = data.get("payload", {})
    action_id = payload.get("action_id")
    if not action_id:
        return
    try:
        from src.services.action_execution import get_action_execution_service

        svc = get_action_execution_service()
        result = await svc.request_undo(action_id=action_id, user_id=user_id)
        await websocket.send_json(
            {
                "type": "action.undo_result",
                "payload": {
                    "action_id": action_id,
                    "success": result.get("success", False),
                    "reason": result.get("reason"),
                },
            }
        )
    except Exception as e:
        logger.warning("Undo request failed: %s", e)


@router.get("/ws/health", tags=["system"])
async def ws_health() -> dict[str, Any]:
    """WebSocket subsystem health check.

    Returns connection statistics scoped by user count (not user IDs,
    to avoid leaking tenant information to unauthenticated callers).
    """
    stats = ws_manager.get_connection_stats()
    return {
        "websocket": "available",
        "active_connections": {
            "total_users": stats["total_users"],
            "total_sockets": stats["total_connections"],
        },
    }
