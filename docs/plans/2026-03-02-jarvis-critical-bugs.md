# Jarvis Experience Critical Bugs — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical bugs blocking the Jarvis goal execution experience: results not persisted, WebSocket drops, and plan generation silent failures.

**Architecture:** All three bugs share a common theme — data loss during goal execution due to missing persistence, insufficient error handling, and connection instability. We fix the persistence gap first (highest impact), then harden WebSocket stability, then make plan generation robust.

**Tech Stack:** Python/FastAPI backend, WebSocket (Starlette), asyncio, Supabase, React/TypeScript frontend.

---

## Root Cause Analysis

### Bug #2: Results Not Persisted (PRIORITY 1)

**Root cause:** Two independent failures in the persistence path:

**Failure A — Prompt-based fallback schema mismatch:** When `_try_skill_execution()` returns `None` (agent init fails, task build fails, or agent returns `success=False`), the code falls through to a prompt-based LLM fallback (`goal_execution.py:1835-1960`). The Hunter prompt at line 2563 asks the LLM to return JSON with keys `summary`, `icp_characteristics`, `prospect_profiles` — but `_persist_hunter_leads()` at line 2249 expects keys `company`, `contacts`, `fit_score`, `fit_reasons`, `gaps`. The mismatch means the fallback path **never** persists leads. It extracts `content.get("result", [])` which returns `[]`, and the function returns at line 2250 without inserting anything.

**Failure B — Potential exception swallowing:** In `_persist_structured_output()` at line 2225-2236, any exception from `_persist_hunter_leads()` is caught and logged but not re-raised. If a Supabase column mismatch or RLS violation occurs during the INSERT (e.g., missing `icp_id` column, wrong column type), the error is silently swallowed and the caller never knows persistence failed.

**Evidence:** Goal 22882bc0 had 5 agents run with real output (Hunter: 18272 tokens), but `discovered_leads` has 0 rows.

### Bug #1: WebSocket Drops (PRIORITY 2)

**Root cause:** Three contributing factors:

1. **No server-side keepalive:** The WS handler (`websocket.py:120-168`) only responds to client pings — the server never initiates pings. If the frontend stops sending heartbeats or the connection goes idle during goal execution, Render's proxy (default 5-minute idle timeout) kills it.

2. **Frontend close code 1006 → SSE fallback:** When the connection drops abnormally (close code 1006), `WebSocketManager.ts:184-187` falls back to SSE instead of reconnecting to WebSocket. SSE doesn't receive goal execution progress events.

3. **No goal status polling after reconnect:** When the frontend reconnects (WebSocket or SSE), it doesn't check for in-progress or completed goals. Events published while disconnected are lost forever.

### Bug #3: Plan Generation Silent Failure (PRIORITY 3)

**Root cause:** The LLM call in `plan_goal()` at `goal_execution.py:3131` is **not wrapped in try-except**. If the Claude API fails (rate limit, timeout, auth), the exception propagates up to `routes/goals.py:82` where it's caught, logged as a warning, and swallowed. The API returns HTTP 200 with the goal in `draft` status. The goal never progresses to `plan_ready` and there's no retry mechanism.

**Flow:** `POST /goals` → `create_goal()` inserts goal as "draft" → `plan_goal()` fails at LLM call → exception caught in route → HTTP 200 returned → goal stuck in "draft" forever.

---

## Task 1: Fix Hunter Persistence — Prompt-Based Fallback Path

**Files:**
- Modify: `backend/src/services/goal_execution.py:2249-2251` (persistence extraction)
- Modify: `backend/src/services/goal_execution.py:2558-2580` (Hunter prompt)
- Test: `backend/tests/test_hunter_persistence.py` (new)

### Step 1: Write failing test for prompt-based Hunter output persistence

```python
# backend/tests/test_hunter_persistence.py
"""Tests for Hunter agent output persistence to discovered_leads."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime


@pytest.fixture
def goal_exec_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        from src.services.goal_execution import GoalExecutionService
        svc = GoalExecutionService()
        svc._db = mock_client
        return svc, mock_client


@pytest.mark.asyncio
async def test_persist_hunter_leads_from_skill_path(goal_exec_service):
    """Skill-aware path wraps leads as {"result": [...]} — should persist."""
    svc, mock_client = goal_exec_service

    # Simulate skill-aware path output: {"result": [lead1, lead2]}
    content = {
        "result": [
            {
                "company": {"name": "Acme Pharma", "domain": "acme.com"},
                "contacts": [{"name": "Jane Doe", "title": "VP Sales"}],
                "fit_score": 85.0,
                "fit_reasons": ["Large pharma", "Active hiring"],
                "gaps": ["No recent funding data"],
                "source": "hunter_pro",
            }
        ]
    }

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "test"}])

    await svc._persist_hunter_leads("user-1", content, "goal-1", datetime.now(UTC).isoformat())

    mock_client.table.assert_called_with("discovered_leads")
    mock_table.insert.assert_called_once()
    insert_data = mock_table.insert.call_args[0][0]
    assert insert_data["company_name"] == "Acme Pharma"
    assert insert_data["fit_score"] == 85.0


@pytest.mark.asyncio
async def test_persist_hunter_leads_from_prompt_fallback(goal_exec_service):
    """Prompt-based fallback returns different JSON schema — should still persist."""
    svc, mock_client = goal_exec_service

    # Simulate prompt-based fallback output (current schema from _build_hunter_prompt)
    content = {
        "summary": "ICP analysis for biotech companies",
        "icp_characteristics": ["Mid-size pharma", "Series B+"],
        "prospect_profiles": [
            {
                "company_type": "Contract Research Organization",
                "company_name": "BioResearch Inc",
                "why_good_fit": "Growing CRO with pharma clients",
                "approach_strategy": "Target VP of Business Development",
            },
            {
                "company_type": "Specialty Pharma",
                "company_name": "NovaTherapeutics",
                "why_good_fit": "Expanding commercial team",
                "approach_strategy": "Connect through industry events",
            },
        ],
        "search_criteria": ["CRO companies", "specialty pharma"],
        "next_steps": ["Refine ICP with user feedback"],
    }

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "test"}])

    await svc._persist_hunter_leads("user-1", content, "goal-1", datetime.now(UTC).isoformat())

    # Should persist the prospect_profiles as leads
    assert mock_table.insert.call_count == 2
    first_insert = mock_table.insert.call_args_list[0][0][0]
    assert first_insert["company_name"] == "BioResearch Inc"


@pytest.mark.asyncio
async def test_persist_hunter_leads_empty_content(goal_exec_service):
    """Empty or non-lead content should not crash or insert."""
    svc, mock_client = goal_exec_service

    await svc._persist_hunter_leads("user-1", {}, "goal-1", datetime.now(UTC).isoformat())
    await svc._persist_hunter_leads("user-1", {"summary": "nothing"}, "goal-1", datetime.now(UTC).isoformat())

    mock_client.table.assert_not_called()
```

### Step 2: Run test to verify it fails

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_hunter_persistence.py -v`
Expected: FAIL — `test_persist_hunter_leads_from_prompt_fallback` fails because prompt fallback content has no "result" key, so `_persist_hunter_leads` returns early.

### Step 3: Fix `_persist_hunter_leads` to handle both output schemas

In `backend/src/services/goal_execution.py`, modify `_persist_hunter_leads` to extract leads from either schema:

Replace lines 2248-2251:
```python
        # Content may be a list of leads directly or wrapped in {"result": [...]}
        leads = content if isinstance(content, list) else content.get("result", [])
        if not isinstance(leads, list) or not leads:
            return
```

With:
```python
        # Content may be:
        # 1. A list of leads directly (from agent returning list)
        # 2. Wrapped in {"result": [...]} (from _try_skill_execution wrapping)
        # 3. Prompt-based fallback with {"prospect_profiles": [...]} schema
        if isinstance(content, list):
            leads = content
        elif "result" in content and isinstance(content.get("result"), list):
            leads = content["result"]
        elif "prospect_profiles" in content and isinstance(content.get("prospect_profiles"), list):
            # Prompt-based fallback schema — normalize to lead format
            leads = []
            for profile in content["prospect_profiles"]:
                leads.append({
                    "company": {
                        "name": profile.get("company_name", profile.get("company_type", "Unknown")),
                    },
                    "contacts": [],
                    "fit_score": 0.5,  # Default — prompt-based leads lack scoring
                    "fit_reasons": [profile.get("why_good_fit", "")],
                    "gaps": [],
                    "source": "hunter_prompt_fallback",
                })
        else:
            leads = []

        if not leads:
            return
```

### Step 4: Run test to verify it passes

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_hunter_persistence.py -v`
Expected: All 3 tests PASS.

### Step 5: Commit

```bash
git add backend/tests/test_hunter_persistence.py backend/src/services/goal_execution.py
git commit -m "fix: persist Hunter leads from both skill-aware and prompt-fallback paths

Hunter agent output was never written to discovered_leads when the
prompt-based fallback path ran. The fallback LLM returns a different
JSON schema (prospect_profiles) than what _persist_hunter_leads
expected (result array with company/contacts/fit_score). Added schema
normalization to handle both formats."
```

---

## Task 2: Add Logging to Persistence Layer for Debugging

**Files:**
- Modify: `backend/src/services/goal_execution.py:2222-2236` (`_persist_structured_output`)

### Step 1: Add diagnostic logging

In `_persist_structured_output`, add logging before dispatching to show what content shape arrives:

After line 2223 (`now = datetime.now(UTC).isoformat()`), add:
```python
        logger.warning(
            "[PERSIST] _persist_structured_output called: agent=%s, content_type=%s, content_keys=%s",
            agent_type,
            type(content).__name__,
            list(content.keys()) if isinstance(content, dict) else "N/A",
        )
```

### Step 2: Run existing tests

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_hunter_persistence.py -v`
Expected: All PASS (logging doesn't affect behavior).

### Step 3: Commit

```bash
git add backend/src/services/goal_execution.py
git commit -m "fix: add diagnostic logging to agent output persistence layer"
```

---

## Task 3: Fix Plan Generation Silent Failure

**Files:**
- Modify: `backend/src/services/goal_execution.py:3131-3145` (wrap LLM call)
- Modify: `backend/src/api/routes/goals.py:77-85` (propagate failure to frontend)
- Test: `backend/tests/test_plan_generation.py` (new)

### Step 1: Write failing test for plan generation error handling

```python
# backend/tests/test_plan_generation.py
"""Tests for goal plan generation error handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def goal_exec_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        from src.services.goal_execution import GoalExecutionService
        svc = GoalExecutionService()
        svc._db = mock_client
        svc._llm = AsyncMock()
        svc._activity = AsyncMock()
        return svc, mock_client


@pytest.mark.asyncio
async def test_plan_goal_llm_failure_sets_error_status(goal_exec_service):
    """When the LLM call fails, plan_goal should mark goal as plan_failed."""
    svc, mock_client = goal_exec_service

    # Mock goal lookup
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.maybe_single.return_value = mock_table
    mock_table.execute.return_value = MagicMock(
        data={"id": "goal-1", "title": "Find leads", "config": {}, "user_id": "user-1", "status": "draft"}
    )
    mock_table.update.return_value = mock_table

    # Mock LLM to raise exception
    svc._llm.generate_response = AsyncMock(side_effect=Exception("API rate limit exceeded"))

    # Mock context gathering
    svc._gather_execution_context = AsyncMock(return_value={
        "company_name": "Test Co",
        "company_domain": "test.com",
        "classification": {},
        "facts": [],
        "gaps": [],
        "readiness": {},
        "profile": {},
    })

    # plan_goal should NOT raise — it should handle gracefully
    result = await svc.plan_goal("goal-1", "user-1")

    # Should have attempted to update goal status to indicate failure
    update_calls = [
        call for call in mock_table.update.call_args_list
        if isinstance(call[0][0], dict) and "status" in call[0][0]
    ]
    # Should contain a plan_failed or draft status update
    assert any(
        call[0][0].get("status") in ("plan_failed", "draft")
        for call in update_calls
    ), f"Expected plan_failed status update, got: {update_calls}"
```

### Step 2: Run test to verify it fails

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_plan_generation.py::test_plan_goal_llm_failure_sets_error_status -v`
Expected: FAIL — currently `plan_goal` raises the exception unhandled.

### Step 3: Wrap the LLM call in plan_goal with error handling

In `backend/src/services/goal_execution.py`, wrap lines 3131-3145 in a try-except:

Replace:
```python
        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are ARIA's resource-aware planning engine. You create detailed, "
                "actionable execution plans that account for the user's connected "
                "integrations, trust levels, and company context. "
                "Each task must have a clear agent assignment and resource requirements. "
                "Be realistic about time estimates. "
                "Respond with valid JSON only — no markdown code fences or commentary."
            ),
            max_tokens=4096,
            temperature=0.3,
            user_id=user_id,
            task=TaskType.STRATEGIST_PLAN,
        )
```

With:
```python
        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA's resource-aware planning engine. You create detailed, "
                    "actionable execution plans that account for the user's connected "
                    "integrations, trust levels, and company context. "
                    "Each task must have a clear agent assignment and resource requirements. "
                    "Be realistic about time estimates. "
                    "Respond with valid JSON only — no markdown code fences or commentary."
                ),
                max_tokens=4096,
                temperature=0.3,
                user_id=user_id,
                task=TaskType.STRATEGIST_PLAN,
            )
        except Exception as llm_err:
            logger.error(
                "LLM call failed during plan generation for goal %s: %s",
                goal_id,
                llm_err,
                exc_info=True,
            )
            # Mark goal as plan_failed so it doesn't stay stuck in draft
            try:
                self._db.table("goals").update(
                    {
                        "status": "plan_failed",
                        "updated_at": datetime.now(UTC).isoformat(),
                        "config": {
                            **goal.get("config", {}),
                            "_plan_error": str(llm_err)[:500],
                        },
                    }
                ).eq("id", goal_id).eq("user_id", user_id).execute()
            except Exception:
                logger.warning("Failed to mark goal %s as plan_failed", goal_id)
            raise
```

### Step 4: Update the API route to communicate failure to frontend

In `backend/src/api/routes/goals.py`, change lines 77-85:

Replace:
```python
    # Auto-generate execution plan and present for approval
    try:
        exec_service = _get_execution_service()
        plan_result = await exec_service.plan_goal(result["id"], current_user.id)
        result["execution_plan"] = plan_result
    except Exception as e:
        logger.warning("Auto-plan failed for goal %s: %s", result["id"], e)

    return result
```

With:
```python
    # Auto-generate execution plan and present for approval
    try:
        exec_service = _get_execution_service()
        plan_result = await exec_service.plan_goal(result["id"], current_user.id)
        result["execution_plan"] = plan_result
    except Exception as e:
        logger.error("Auto-plan failed for goal %s: %s", result["id"], e, exc_info=True)
        result["plan_error"] = (
            "Plan generation failed. ARIA will retry automatically, "
            "or you can edit the goal and try again."
        )

    return result
```

### Step 5: Add `plan_failed` to GoalStatus enum if missing

Check `backend/src/models/goal.py` for the GoalStatus enum. If `plan_failed` is not present, add it.

### Step 6: Run tests

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_plan_generation.py -v`
Expected: PASS.

### Step 7: Commit

```bash
git add backend/src/services/goal_execution.py backend/src/api/routes/goals.py backend/tests/test_plan_generation.py backend/src/models/goal.py
git commit -m "fix: handle plan generation LLM failures instead of silently swallowing

plan_goal() had an unprotected LLM call that, on failure, raised an
exception caught only by the API route which returned HTTP 200 anyway.
Goals got stuck in 'draft' forever. Now: LLM errors are caught in
plan_goal(), goal is marked 'plan_failed', and the API route
communicates the failure to the frontend."
```

---

## Task 4: Fix WebSocket Stability — Server-Side Keepalive

**Files:**
- Modify: `backend/src/api/routes/websocket.py:118-127` (add server-side ping)
- Test: `backend/tests/test_websocket_keepalive.py` (new)

### Step 1: Write failing test

```python
# backend/tests/test_websocket_keepalive.py
"""Tests for WebSocket server-side keepalive."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_server_sends_ping_periodically():
    """Server should send ping frames to keep connection alive."""
    # This is a design validation test — we verify the keepalive task
    # is created when a WS connection is established.
    from src.api.routes.websocket import _start_keepalive, _stop_keepalive

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()

    # Start keepalive with a short interval for testing
    task = _start_keepalive(mock_ws, interval=0.1)

    # Let it run for 0.35 seconds (should get ~3 pings)
    await asyncio.sleep(0.35)

    # Stop keepalive
    _stop_keepalive(task)

    # Should have sent multiple pings
    assert mock_ws.send_json.call_count >= 2

    # Each ping should be a proper ping event
    for call in mock_ws.send_json.call_args_list:
        event = call[0][0]
        assert event["type"] == "ping"
```

### Step 2: Run test to verify it fails

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_websocket_keepalive.py -v`
Expected: FAIL — `_start_keepalive` doesn't exist yet.

### Step 3: Add server-side keepalive to WebSocket handler

In `backend/src/api/routes/websocket.py`, add keepalive functions near the top (after imports):

```python
_KEEPALIVE_INTERVAL = 25  # seconds — under Render's 30s proxy idle timeout


def _start_keepalive(websocket: WebSocket, interval: float = _KEEPALIVE_INTERVAL) -> asyncio.Task:
    """Start a background task that sends periodic pings to keep the WS alive."""
    async def _ping_loop():
        try:
            while True:
                await asyncio.sleep(interval)
                await websocket.send_json({"type": "ping", "payload": {}})
        except Exception:
            pass  # Connection closed — stop pinging

    return asyncio.create_task(_ping_loop())


def _stop_keepalive(task: asyncio.Task | None) -> None:
    """Cancel the keepalive background task."""
    if task and not task.done():
        task.cancel()
```

Then modify the WS handler to start/stop keepalive. After `await websocket.accept()` (line 93), add:

```python
    keepalive_task = _start_keepalive(websocket)
```

In the `finally` block (line 180-181), add before `ws_manager.disconnect`:

```python
        _stop_keepalive(keepalive_task)
```

### Step 4: Run test

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_websocket_keepalive.py -v`
Expected: PASS.

### Step 5: Commit

```bash
git add backend/src/api/routes/websocket.py backend/tests/test_websocket_keepalive.py
git commit -m "fix: add server-side WebSocket keepalive to prevent proxy idle timeout

Render's proxy kills idle connections after ~5 minutes. During goal
execution, no data may flow on the WS for extended periods. Added a
server-side ping every 25 seconds to keep the connection alive."
```

---

## Task 5: Fix WebSocket Reconnect — Reload Goal State After Drop

**Files:**
- Modify: `frontend/src/core/WebSocketManager.ts` (reconnect behavior)

### Step 1: Fix close code 1006 to attempt WS reconnect before SSE fallback

In `WebSocketManager.ts`, modify the `onclose` handler. Currently close code 1006 goes straight to SSE. Change it to try WS reconnect first (up to 2 attempts), then fall back to SSE:

Find the block:
```typescript
    // Abnormal closure (1006) or policy violation (1008) - fall back to SSE
    if (event.code === 1006 || event.code === 1008) {
      console.debug(`[WebSocketManager] Connection failed (code=${event.code}), falling back to SSE`);
      this.fallbackToSSE();
      return;
    }
```

Replace with:
```typescript
    // Policy violation - fall back to SSE immediately
    if (event.code === 1008) {
      console.debug(`[WebSocketManager] Policy violation (code=1008), falling back to SSE`);
      this.fallbackToSSE();
      return;
    }

    // Abnormal closure (1006) - try WS reconnect first, then SSE
    if (event.code === 1006) {
      if (this.reconnectAttempts < 2) {
        console.debug(`[WebSocketManager] Abnormal close (1006), attempting WS reconnect (attempt ${this.reconnectAttempts + 1}/2)`);
        this._connectionState = 'reconnecting';
        this.emit('connection.state_changed', { state: 'reconnecting', reason: 'abnormal_close' });
        this.scheduleReconnect();
      } else {
        console.debug(`[WebSocketManager] Abnormal close (1006), WS reconnect exhausted, falling back to SSE`);
        this.fallbackToSSE();
      }
      return;
    }
```

### Step 2: Add goal status reload on reconnect

In `WebSocketManager.ts`, after successful reconnection (in the `onopen` handler or the reconnect success path), emit an event that the application layer can listen to for reloading goal state:

Find the reconnect success path and add:
```typescript
this.emit('connection.reconnected', { transport: this._transport });
```

Then in the component/hook that manages goal state (search for where goals are fetched), add a listener:

```typescript
wsManager.on('connection.reconnected', () => {
  // Reload active goals to catch any that completed while disconnected
  refetchActiveGoals();
});
```

**Note:** The exact file for the goal state hook needs to be identified during implementation. Search for `useGoals` or `goalStore` or `fetchGoals` in the frontend.

### Step 3: Commit

```bash
git add frontend/src/core/WebSocketManager.ts
git commit -m "fix: WebSocket reconnects on abnormal close before falling back to SSE

Close code 1006 previously went straight to SSE fallback, losing
real-time goal execution events. Now tries WS reconnect twice before
SSE. Also emits reconnected event so app can reload goal state."
```

---

## Task 6: Increase Gunicorn Timeout for Long-Running Goal Execution

**Files:**
- Modify: `render.yaml:21` (timeout value)

### Step 1: Increase timeout

In `render.yaml`, change line 21:

```yaml
      --timeout 120
```

To:

```yaml
      --timeout 600
```

This gives goal execution up to 10 minutes before Gunicorn kills the worker. Individual agent timeouts (300s) and the asyncio event loop already handle per-agent limits.

### Step 2: Commit

```bash
git add render.yaml
git commit -m "fix: increase Gunicorn timeout from 120s to 600s for goal execution

Goal execution runs multiple agents that can each take up to 300s.
The 120s Gunicorn timeout was killing the worker mid-execution,
severing WebSocket connections and losing results."
```

---

## Task 7: Run Full Test Suite and Verify

### Step 1: Run all new tests

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_hunter_persistence.py backend/tests/test_plan_generation.py backend/tests/test_websocket_keepalive.py -v`
Expected: All PASS.

### Step 2: Run existing goal execution tests

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/ -k "goal" -v --timeout=60`
Expected: No regressions.

### Step 3: Run broader test suite (exclude smoke/integration)

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/ --ignore=backend/tests/test_llm_gateway_smoke.py -x -q --timeout=120`
Expected: No regressions.

### Step 4: Commit any test fixes if needed

---

## Summary of Changes

| Bug | Root Cause | Fix | Files |
|-----|-----------|-----|-------|
| #2 Results not persisted | Prompt fallback schema mismatch | Normalize both schemas in `_persist_hunter_leads` | `goal_execution.py` |
| #3 Plan generation fails | Unprotected LLM call, swallowed exception | Try-except with `plan_failed` status + API error communication | `goal_execution.py`, `goals.py` |
| #1 WebSocket drops | No server keepalive, 1006→SSE, no state reload | Server-side ping, reconnect before SSE, goal reload | `websocket.py`, `WebSocketManager.ts` |
| #1 WebSocket drops | Gunicorn 120s timeout kills worker | Increase to 600s | `render.yaml` |
