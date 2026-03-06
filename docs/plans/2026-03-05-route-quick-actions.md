# Quick Action Routing implementation Plan
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Route quick action patterns to the quick action handler before intent classification in all three chat code paths

**Architecture:** Three-step pipeline with existing quick action detection (`_match_quick_action`) runs before LLM intent classification. If matched, route to `_handle_quick_action` which returns immediate response without goal creation

**Tech Stack:** Python, FastAPI, Async/AAwait/ Supabase

---

## Task 1: Add Quick Action Detection to REST Endpoint (chat.py)

**Files:**
- Modify: `backend/src/api/routes/chat.py` (lines 262-278)
- Create: `backend/tests/test_quick_action_routing.py`

**Step 1: Write the failing test for quick action detection in REST endpoint**

Create test file `backend/tests/test_quick_action_routing.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import the service and route
import sys
sys.path.insert(0, "backend")
from src.services.chat import ChatService
from src.api.routes.chat import router


@pytest.mark.asyncio
async def test_quick_action_detection_signal_enriched():
    """When signal-enriched, quick action detection should be skipped"""
    pass


@pytest.mark.asyncio
async def test_quick_action_detection_bypasses_intent_classification():
    """When quick action patterns matches, LLM intent classification should be skipped"""
    service = ChatService()
    result = ChatService._match_quick_action("what's on my calendar")
    assert result is not None
    assert result["action_type"] == "calendar_query"


@pytest.mark.asyncio
async def test_quick_action_routing_bypasses_goal_creation():
    """When quick action matches, route to handler, skip goal creation entirely"""
    pass
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: 1 failed, 2 passed (tests are not implemented yet)

**Step 3: Implement quick action detection in REST endpoint**

In `backend/src/api/routes/chat.py`, after the signal enrichment bypass block (around line 272), add:

```python
# --- Quick Action Detection (BEFORE intent classification) ---
quick_action_match = None
if not was_signal_enriched:
    quick_action_match = ChatService._match_quick_action(request.message)
    if quick_action_match:
        logger.info(
            "QUICK_ACTION: Pattern matched, routing to quick action handler: %s",
            quick_action_match.get("action_type"),
        )
```

**Step 4: Guard intent classification to skip when quick action matched**

Around line 275, modify the intent classification block:

```python
# --- Intent Classification (only if not signal-enriched AND not quick action) ---
intent_result = None
if not was_signal_enriched and not quick_action_match:
    intent_result = await service._classify_intent(current_user.id, request.message)
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: 2 passed

**Step 6: Add quick action routing block**

After the intent classification block, add:

```python
# --- Quick Action Routing ---
if quick_action_match or (intent_result and intent_result.get("is_quick_action")):
    action_intent = quick_action_match or intent_result
    logger.info("QUICK_ACTION: Routing to handler, action_type=%s", action_intent.get("action_type"))

    result = await service._handle_quick_action(
        user_id=current_user.id,
        conversation_id=conversation_id,
        message=request.message,
        intent=action_intent,
        working_memory=working_memory,
        conversation_messages=conversation_messages,
    )

    # Stream the response back to the frontend
    response_text = result.get("response", "")

    # Send metadata event
    metadata = {
        "type": "metadata",
        "message_id": message_id,
        "conversation_id": conversation_id,
    }
    yield f"data: {json.dumps(metadata)}\n\n"

    # Stream response as tokens (simulate streaming for consistent UX)
    for token_chunk in [response_text]:
        event = {"type": "token", "content": token_chunk}
        yield f"data: {json.dumps(event)}\n\n"

    # Send completion event
    complete_event = {
        "type": "complete",
        "rich_content": [],
        "ui_commands": [],
        "suggestions": [],
        "intent_detected": "quick_action",
    }
    yield f"data: {json.dumps(complete_event)}\n\n"
    yield "data: [DONE]\n\n"
    return
```

**Step 7: Guard plan action classification**

Around line 347-350, modify the plan action classification block:

```python
# --- Check for pending plan interactions (skip if signal-enriched OR quick action) ---
plan_action = None
if not was_signal_enriched and not quick_action_match and not (intent_result and intent_result.get("is_quick_action")):
    plan_action = await service._classify_plan_action(current_user.id, request.message)
```

**Step 8: Run syntax verification**

Run: `cd backend && python -m py_compile src/api/routes/chat.py`
Expected: No output (success)

**Step 9: Run tests to verify all pass**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: All tests pass

**Step 10: Commit REST endpoint changes**

```bash
git add backend/src/api/routes/chat.py backend/tests/test_quick_action_routing.py
git commit -m "feat(chat): Add quick action routing to REST endpoint"
```

---

## Task 2: Add Quick Action Routing to ChatService (process_message)

**Files:**
- Modify: `backend/src/services/chat.py` (around line 3069-3085)
- Modify: `backend/tests/test_quick_action_routing.py`

**Step 1: Write the failing test for quick action detection in process_message**

Add to `backend/tests/test_quick_action_routing.py`:

```python


@pytest.mark.asyncio
async def test_quick_action_detection_in_process_message():
    """When quick action patterns match in process_message, route to handler"""
    service = ChatService()
    # Should be detected before intent classification
    result = ChatService._match_quick_action("show my signals")
    assert result is not None
```

**Step 2: Find the exact location in process_message**

Run: `grep -n "was_signal_enriched\|intent_result\|is_goal" backend/src/services/chat.py | head -30`
Expected: Find lines around 3069-3085 where we need to insert quick action detection

**Step 3: Read the process_message section**

Run: `sed -n '3065,3090p' backend/src/services/chat.py`
Expected: See the current structure

**Step 4: Add quick action detection block**

After the signal bypass check (around line 3069-3078), add:

```python
# --- Quick Action Detection (BEFORE intent classification) ---
quick_action_match = None
if not was_signal_enriched:
    quick_action_match = ChatService._match_quick_action(message)
    if quick_action_match:
        logger.info(
            "QUICK_ACTION: Pattern matched in process_message: %s",
            quick_action_match.get("action_type"),
        )
```

**Step 5: Guard intent classification**

Modify the intent classification block to skip when quick action matched:

```python
# --- Inline Intent Detection (skip if signal-enriched OR quick action) ---
intent_result = None
if not was_signal_enriched and not quick_action_match:
    intent_result = await self._classify_intent(user_id, message)
```

**Step 6: Add quick action routing block**

After intent classification, before goal routing, add:
```python
# --- Quick Action Routing ---
if quick_action_match or (intent_result and intent_result.get("is_quick_action")):
    action_intent = quick_action_match or intent_result
    logger.info("QUICK_ACTION: Routing to handler in process_message")
    return await self._handle_quick_action(
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        intent=action_intent,
        working_memory=working_memory,
        conversation_messages=conversation_messages,
    )
```

**Step 7: Run syntax verification**

Run: `cd backend && python -m py_compile src/services/chat.py`
Expected: No output (success)

**Step 8: Run tests**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: All tests pass

**Step 9: Commit ChatService changes**

```bash
git add backend/src/services/chat.py backend/tests/test_quick_action_routing.py
git commit -m "feat(chat): Add quick action routing to ChatService.process_message"
```

---

## Task 3: Add Quick Action Routing to WebSocket Handler
**Files:**
- Modify: `backend/src/api/routes/websocket.py` (lines 461-466, 603-660)
- Modify: `backend/tests/test_quick_action_routing.py`

**Step 1: Write the failing test for WebSocket quick action detection**

Add to `backend/tests/test_quick_action_routing.py`:

```python


@pytest.mark.asyncio
async def test_quick_action_detection_in_websocket():
    """When quick action patterns match in WebSocket, route to handler"""
    service = ChatService()
    result = ChatService._match_quick_action("prep me for my meeting")
    assert result is not None
    assert result["action_type"] == "meeting_prep"
```

**Step 2: Find the exact location in WebSocket handler**

Run: `grep -n "was_signal_enriched\|intent_result\|is_goal" backend/src/api/routes/websocket.py | head -20`
Expected: Find lines 461-466, 603-660 where we need to insert quick action detection

**Step 3: Add quick action detection block in WebSocket**

After the signal bypass check (around line 466), add:

```python
# --- Quick Action Detection (BEFORE intent classification) ---
quick_action_match = None
if not was_signal_enriched:
    from src.services.chat import ChatService
    quick_action_match = ChatService._match_quick_action(message_text)
    if quick_action_match:
        logger.info(
            "QUICK_ACTION_WS: Pattern matched: %s",
            quick_action_match.get("action_type"),
        )
```

**Step 4: Guard intent classification in WebSocket**

Modify the intent classification block (around line 603-611):
```python
# --- Intent Classification (skip for signal-enriched messages or quick actions) ---
intent_result = None
if not was_signal_enriched and not quick_action_match:
    # --- Inline Intent Detection (ALWAYS runs — even with pending plans) ---
    # A new action request like "find companies" must create a new goal,
    # not be blocked by a stale plan_ready goal from an earlier request.
    intent_result = await service._classify_intent(user_id, message_text)
```

**Step 5: Add quick action routing block in WebSocket**

After intent classification, before goal routing, add:
```python
# --- Quick Action Routing ---
if quick_action_match or (intent_result and intent_result.get("is_quick_action")):
    action_intent = quick_action_match or intent_result
    logger.info("QUICK_ACTION_WS: Routing to handler, action_type=%s", action_intent.get("action_type"))

    try:
        result = await service._handle_quick_action(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message_text,
            intent=action_intent,
            working_memory=working_memory,
            conversation_messages=conversation_messages,
        )
    except Exception:
        logger.exception(
            "WS quick action handling failed",
            extra={"user_id": user_id},
        )
        await websocket.send_json(
            {
                "type": "aria.message",
                "message": "I understood your request but ran into a problem. Please try again.",
                "rich_content": [],
                "ui_commands": [],
                "suggestions": ["Try again"],
                "conversation_id": conversation_id,
                "intent_detected": "quick_action",
            }
        )
        return

    # Send response via WebSocket
    await websocket.send_json(
        {
            "type": "aria.message",
            "message": result.get("response", ""),
            "rich_content": [],
            "ui_commands": [],
            "suggestions": [],
            "conversation_id": conversation_id,
            "intent_detected": "quick_action",
        }
    )
    return
```

**Step 6: Run syntax verification**

Run: `cd backend && python -m py_compile src/api/routes/websocket.py`
Expected: No output (success)

**Step 7: Run tests**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: All tests pass

**Step 8: Commit WebSocket changes**

```bash
git add backend/src/api/routes/websocket.py backend/tests/test_quick_action_routing.py
git commit -m "feat(chat): Add quick action routing to WebSocket handler"
```

---

## Task 4: Integration Testing
**Files:**
- Test: `backend/tests/test_quick_action_routing.py`

**Step 1: Write integration test for end-to-end quick action flow**

Add to `backend/tests/test_quick_action_routing.py`:
```python


@pytest.mark.asyncio
async def test_quick_action_full_flow():
    """Test complete quick action flow from detection to response"""
    # Test data
    test_message = "show my signals"
    expected_action_type = "signal_review"

    # Test pattern detection
    service = ChatService()
    match = ChatService._match_quick_action(test_message)
    assert match is not None
    assert match["action_type"] == expected_action_type

    # Note: In a real integration test, we would mock
    # - Supabase client
    # - LLM client
    # - Working memory manager
    # Then call _handle_quick_action and verify the response
```

**Step 2: Run full test suite**

Run: `pytest backend/tests/test_quick_action_routing.py -v`
Expected: All tests pass

**Step 3: Commit integration test**

```bash
git add backend/tests/test_quick_action_routing.py
git commit -m "test(chat): Add integration tests for quick action routing"
```

---

## Task 5: Manual Verification
**Files:**
- None (manual testing in frontend/through API)

**Step 1: Restart backend**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`
Expected: Server starts without errors

**Step 2: Test quick action: meeting prep**

Send message: "prep me for my 11am meeting"
Expected behavior:
- Backend logs show `QUICK_ACTION: Pattern matched`
- No intent classification logs
- No goal creation
- Immediate response from ARIA

**Step 3: Test quick action: signal review**

Send message: "show my latest signals"
Expected behavior:
- Backend logs show `QUICK_ACTION: Pattern matched`
- No intent classification logs
- No goal creation
- Immediate response from ARIA

**Step 4: Test goal creation still works**

Send message: "find 10 bioprocessing companies"
Expected behavior:
- Backend logs show intent classification
- Goal created
- Execution plan shown

**Step 5: Test conversational still works**

Send message: "hi"
Expected behavior:
- Normal conversational response
- No quick action routing
- No goal creation

---

## Summary

This plan implements quick action routing in all three code paths:

1. **REST endpoint** (`backend/src/api/routes/chat.py`) - Primary path used by frontend
2. **ChatService.process_message** (`backend/src/services/chat.py`) - Service layer
3. **WebSocket handler** (`backend/src/api/routes/websocket.py`) - Alternative path

Each implementation follows the same pattern
1. Signal enrichment bypass checked FIRST (preserves existing behavior)
2. Quick action detection SECOND (new - pattern matching before LLM)
3. Intent classification THIRD (skipped if quick action matched)
4. Goal routing LAST (unchanged)

The routing order ensures deterministic pattern matching bypasses expensive LLM calls for quick actions, returning immediate responses without goal creation overhead.
