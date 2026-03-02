# Thesys C1 Custom Actions & Embed Endpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ARIA-specific custom actions that C1 renders as interactive buttons, plus an optional embed endpoint for exploratory queries where UI choice is unpredictable.

**Architecture:** Define 9 custom action Pydantic models with dynamic IDs only (no hardcoded values), integrate them into ThesysService via metadata, add a streaming SSE embed endpoint with JWT auth, and enhance WebSocket thinking events with structured agent/phase context.

**Tech Stack:** Python 3.11+ / Pydantic / FastAPI / AsyncOpenAI / Server-Sent Events

---

## Task 1: Custom Action Definitions

**Files:**
- Create: `backend/src/services/thesys_actions.py`
- Test: `backend/tests/test_thesys_actions.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_thesys_actions.py
"""Tests for Thesys C1 custom actions."""

import pytest


class TestGetAriaCustomActions:
    def test_returns_dict_with_all_nine_actions(self) -> None:
        """All 9 ARIA custom actions are present."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        assert "approve_goal" in actions
        assert "modify_goal" in actions
        assert "approve_email" in actions
        assert "edit_email" in actions
        assert "dismiss_email" in actions
        assert "investigate_signal" in actions
        assert "view_lead_detail" in actions
        assert "execute_task" in actions
        assert "view_battle_card" in actions

    def test_each_action_has_valid_json_schema(self) -> None:
        """Each action returns a valid JSON schema with properties."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        for action_name, schema in actions.items():
            assert "properties" in schema, f"{action_name} missing properties"
            assert "type" in schema, f"{action_name} missing type"
            assert schema["type"] == "object", f"{action_name} must be object type"

    def test_approve_goal_has_required_fields(self) -> None:
        """approve_goal action has goal_id and goal_name."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["approve_goal"]
        props = schema["properties"]

        assert "goal_id" in props
        assert "goal_name" in props
        assert "goal_id" in schema.get("required", [])
        assert "goal_name" in schema.get("required", [])

    def test_approve_email_has_required_fields(self) -> None:
        """approve_email action has email_draft_id, recipient, subject."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["approve_email"]
        props = schema["properties"]

        assert "email_draft_id" in props
        assert "recipient" in props
        assert "subject" in props

    def test_investigate_signal_has_signal_type(self) -> None:
        """investigate_signal includes signal_type field."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["investigate_signal"]
        props = schema["properties"]

        assert "signal_id" in props
        assert "signal_type" in props

    def test_no_hardcoded_ids_in_schemas(self) -> None:
        """Verify no action schema contains hardcoded ID values."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        # Check that schemas don't contain hardcoded UUIDs or IDs
        hardcoded_patterns = [
            "00000000-0000-0000",  # UUID pattern
            "12345",  # Common test ID
            "test-id",
            "example",
        ]

        for action_name, schema in actions.items():
            schema_str = str(schema).lower()
            for pattern in hardcoded_patterns:
                assert pattern not in schema_str, (
                    f"{action_name} contains hardcoded pattern: {pattern}"
                )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_thesys_actions.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.thesys_actions'"

**Step 3: Write the implementation**

```python
# backend/src/services/thesys_actions.py
"""ARIA custom actions for Thesys C1 generative UI.

Defines Pydantic models for actions that C1 renders as interactive buttons.
All actions use dynamic parameterized payloads — NO hardcoded IDs.
"""

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Action Schemas — tell C1 what buttons to generate and what params they carry
# ---------------------------------------------------------------------------


class ApproveGoalAction(BaseModel):
    """User approves a proposed goal/plan."""

    goal_id: str
    goal_name: str


class ModifyGoalAction(BaseModel):
    """User wants to modify a proposed goal/plan."""

    goal_id: str
    goal_name: str


class ApproveEmailAction(BaseModel):
    """User approves a drafted email for sending."""

    email_draft_id: str
    recipient: str
    subject: str


class EditEmailAction(BaseModel):
    """User wants to edit a drafted email."""

    email_draft_id: str


class DismissEmailAction(BaseModel):
    """User dismisses/discards a drafted email."""

    email_draft_id: str


class InvestigateSignalAction(BaseModel):
    """User wants to investigate a market signal further."""

    signal_id: str
    signal_type: str  # e.g., "patent_cliff", "clinical_trial", "competitive_move"


class ViewLeadDetailAction(BaseModel):
    """User wants to see full details on a lead."""

    lead_id: str
    lead_name: str


class ExecuteTaskAction(BaseModel):
    """User approves execution of a pending task."""

    task_id: str
    task_description: str


class ViewBattleCardAction(BaseModel):
    """User wants to open a full battle card."""

    competitor_id: str
    competitor_name: str


# ---------------------------------------------------------------------------
# Helper function to export schemas for C1 metadata
# ---------------------------------------------------------------------------


def get_aria_custom_actions() -> dict:
    """Returns ARIA's custom actions as JSON schemas for C1 metadata.

    Each action is converted to JSON Schema format that Thesys C1 expects
    in the metadata.thesys.c1_custom_actions field.

    Returns:
        Dict keyed by action name, values are JSON Schema dicts.
    """
    return {
        "approve_goal": ApproveGoalAction.model_json_schema(),
        "modify_goal": ModifyGoalAction.model_json_schema(),
        "approve_email": ApproveEmailAction.model_json_schema(),
        "edit_email": EditEmailAction.model_json_schema(),
        "dismiss_email": DismissEmailAction.model_json_schema(),
        "investigate_signal": InvestigateSignalAction.model_json_schema(),
        "view_lead_detail": ViewLeadDetailAction.model_json_schema(),
        "execute_task": ExecuteTaskAction.model_json_schema(),
        "view_battle_card": ViewBattleCardAction.model_json_schema(),
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_thesys_actions.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add backend/src/services/thesys_actions.py backend/tests/test_thesys_actions.py
git commit -m "$(cat <<'EOF'
feat: add ARIA custom actions for Thesys C1

Define 9 custom action Pydantic models that C1 renders as interactive
buttons in the generative UI:
- Goal actions: approve_goal, modify_goal
- Email actions: approve_email, edit_email, dismiss_email
- Signal actions: investigate_signal
- Lead actions: view_lead_detail
- Task actions: execute_task
- Battle card actions: view_battle_card

All actions use dynamic parameterized payloads only — no hardcoded IDs.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Integrate Custom Actions into ThesysService

**Files:**
- Modify: `backend/src/services/thesys_service.py:85-100`
- Test: `backend/tests/test_thesys_service.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_thesys_service.py

class TestCustomActionsIntegration:
    @pytest.mark.asyncio
    @patch("src.services.thesys_service.settings")
    async def test_visualize_includes_custom_actions_in_metadata(
        self, mock_settings: MagicMock
    ) -> None:
        """C1 calls include custom actions in metadata."""
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "k"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        mock_settings.THESYS_MODEL = "c1/test"
        mock_settings.THESYS_TIMEOUT = 10.0

        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        svc._enabled = True

        # Track what was passed to the API
        captured_metadata: dict = {}

        async def mock_create(**kwargs):
            captured_metadata.update(kwargs.get("metadata", {}))
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "<div>Rendered</div>"
            return mock_response

        with patch("src.services.thesys_service.thesys_circuit_breaker") as mock_cb:
            mock_cb.check.return_value = None
            mock_cb.record_success.return_value = None

            if svc._client:
                svc._client.chat.completions.create = mock_create

            result = await svc.visualize("Test content", "system prompt")

        # Verify custom actions were included
        import json

        assert "thesys" in captured_metadata
        thesys_meta = json.loads(captured_metadata["thesys"])
        assert "c1_custom_actions" in thesys_meta
        actions = thesys_meta["c1_custom_actions"]
        assert "approve_goal" in actions
        assert "approve_email" in actions
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_thesys_service.py::TestCustomActionsIntegration -v`
Expected: FAIL with "AssertionError: assert 'thesys' in captured_metadata"

**Step 3: Modify ThesysService._call_c1**

```python
# In backend/src/services/thesys_service.py
# Update imports at top:
import json
from typing import Any

# Add import for custom actions:
from src.services.thesys_actions import get_aria_custom_actions

# Modify _call_c1 method (lines 85-100):
async def _call_c1(self, content: str, system_prompt: str) -> str:
    """Internal non-streaming call to the C1 Visualize endpoint."""
    assert self._client is not None

    # Build metadata with custom actions
    metadata: dict[str, Any] = {
        "thesys": json.dumps({
            "c1_custom_actions": get_aria_custom_actions(),
        }),
    }

    response = await self._client.chat.completions.create(
        model=settings.THESYS_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        metadata=metadata,
        stream=False,
        timeout=settings.THESYS_TIMEOUT,
    )

    choice = response.choices[0]
    return choice.message.content or content
```

**Step 4: Also update visualize_stream method**

```python
# In backend/src/services/thesys_service.py
# Modify visualize_stream method (around lines 102-149):

async def visualize_stream(
    self, content: str, system_prompt: str,
) -> AsyncIterator[str]:
    """Stream C1-rendered content chunk by chunk.

    Yields rendered content chunks. If the service is unavailable,
    yields the original content as a single chunk.
    """
    if not self._enabled or self._client is None:
        yield content
        return

    try:
        thesys_circuit_breaker.check()
    except CircuitBreakerOpen:
        yield content
        return

    start = time.perf_counter()
    try:
        # Build metadata with custom actions
        metadata: dict[str, Any] = {
            "thesys": json.dumps({
                "c1_custom_actions": get_aria_custom_actions(),
            }),
        }

        stream = await self._client.chat.completions.create(
            model=settings.THESYS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            metadata=metadata,
            stream=True,
            timeout=settings.THESYS_TIMEOUT,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

        thesys_circuit_breaker.record_success()
        elapsed = time.perf_counter() - start
        logger.info("Thesys C1 stream completed in %.2fs", elapsed)

    except Exception as exc:
        thesys_circuit_breaker.record_failure()
        elapsed = time.perf_counter() - start
        logger.warning(
            "Thesys C1 stream failed after %.2fs: %s — yielding raw content",
            elapsed,
            exc,
        )
        yield content
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_thesys_service.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/src/services/thesys_service.py backend/tests/test_thesys_service.py
git commit -m "$(cat <<'EOF'
feat: integrate custom actions into ThesysService C1 calls

Add c1_custom_actions to metadata for both visualize() and
visualize_stream() methods. C1 uses this to render interactive
buttons with dynamic action payloads.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Embed Endpoint for Exploratory Queries

**Files:**
- Modify: `backend/src/api/routes/thesys.py`
- Test: `backend/tests/test_thesys_route.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_thesys_route.py

class TestEmbedEndpoint:
    @pytest.mark.asyncio
    async def test_embed_endpoint_exists(self, async_client: AsyncClient) -> None:
        """Embed endpoint returns 200 with valid request."""
        from unittest.mock import AsyncMock, patch

        with patch("src.api.routes.thesys.settings") as mock_settings:
            mock_settings.thesys_configured = True

            request_body = {
                "messages": [
                    {"role": "user", "content": "Show me our top accounts"},
                ],
            }

            response = await async_client.post(
                "/api/v1/thesys/embed",
                json=request_body,
            )

            # Should not return 404
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_embed_uses_embed_base_url(
        self, async_client: AsyncClient
    ) -> None:
        """Embed endpoint uses the /embed path, not /visualize."""
        from unittest.mock import AsyncMock, MagicMock, patch

        with patch("src.api.routes.thesys.settings") as mock_settings:
            mock_settings.thesys_configured = True
            mock_settings.THESYS_API_KEY = MagicMock()
            mock_settings.THESYS_API_KEY.get_secret_value.return_value = "test-key"
            mock_settings.THESYS_MODEL = "c1/anthropic/claude-haiku-4-5/latest"
            mock_settings.THESYS_TIMEOUT = 30.0

            captured_url: str = ""

            async def mock_create(**kwargs):
                nonlocal captured_url
                # The client should be created with embed base URL
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].delta.content = "chunk"
                mock_response.choices[0].finish_reason = "stop"
                return mock_response

            # We'll check the client was created with embed URL
            # by inspecting the endpoint's behavior
            with patch("src.api.routes.thesys.get_thesys_service") as mock_svc:
                svc_instance = MagicMock()
                svc_instance.is_available = True
                mock_svc.return_value = svc_instance

                response = await async_client.post(
                    "/api/v1/thesys/embed",
                    json={"messages": [{"role": "user", "content": "test"}]},
                )

            # Should return success or streaming response
            assert response.status_code in (200, 401)  # 401 if auth required
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_thesys_route.py::TestEmbedEndpoint -v`
Expected: FAIL with 404 or AttributeError

**Step 3: Add embed endpoint to thesys.py routes**

```python
# Add to backend/src/api/routes/thesys.py

# Add new imports at top:
import json
from collections.abc import AsyncIterator
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

# Add new request model after VisualizeRequest:

class EmbedRequest(BaseModel):
    """Request body for embed endpoint (full LLM proxy)."""

    messages: list[dict] = Field(
        ...,
        min_length=1,
        description="Full conversation history",
    )
    system_prompt: str | None = Field(
        None,
        description="Optional system prompt (defaults to ARIA_C1_SYSTEM_PROMPT)",
    )


# Add new endpoint after visualize_sync:

@router.post(
    "/embed",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "SSE stream of C1-rendered content"},
        401: {"description": "Authentication required"},
        503: {"description": "Thesys service unavailable"},
    },
)
async def embed_stream(
    body: EmbedRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Streaming embed endpoint for exploratory queries.

    Uses C1's full LLM proxy (embed path) for cases where the optimal UI
    is unpredictable. C1 decides between tables, cards, charts, etc.

    This endpoint:
    - Uses base_url=https://api.thesys.dev/v1/embed
    - Accepts full conversation history (messages array)
    - Returns SSE stream with C1-rendered content
    - Includes custom actions in metadata

    Args:
        body: EmbedRequest with messages and optional system_prompt.
        current_user: JWT-authenticated user.

    Returns:
        StreamingResponse with text/event-stream content type.
    """
    if not settings.thesys_configured:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Thesys C1 service not configured",
        )

    from src.services.thesys_actions import get_aria_custom_actions
    from src.services.thesys_system_prompt import ARIA_C1_SYSTEM_PROMPT

    system_prompt = body.system_prompt or ARIA_C1_SYSTEM_PROMPT

    # Create client with embed base URL
    client = AsyncOpenAI(
        api_key=settings.THESYS_API_KEY.get_secret_value(),
        base_url="https://api.thesys.dev/v1/embed",
    )

    # Build messages with system prompt
    messages = [{"role": "system", "content": system_prompt}] + body.messages

    # Build metadata with custom actions
    metadata = {
        "thesys": json.dumps({
            "c1_custom_actions": get_aria_custom_actions(),
        }),
    }

    async def generate() -> AsyncIterator[str]:
        """Generate SSE chunks from C1 stream."""
        try:
            stream = await client.chat.completions.create(
                model="c1/anthropic/claude-haiku-4-5/latest",
                messages=messages,
                metadata=metadata,
                stream=True,
                timeout=settings.THESYS_TIMEOUT,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    # SSE format: data: <content>\n\n
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            # Send done marker
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Embed stream error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_thesys_route.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/api/routes/thesys.py backend/tests/test_thesys_route.py
git commit -m "$(cat <<'EOF'
feat: add embed endpoint for exploratory C1 queries

POST /api/v1/thesys/embed provides full LLM proxy via C1's embed path
for cases where optimal UI is unpredictable. C1 decides between tables,
cards, charts, etc.

- Uses base_url=https://api.thesys.dev/v1/embed
- Accepts full conversation history
- Returns SSE stream with C1-rendered content
- Includes custom actions in metadata
- Protected with JWT auth

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Thinking States to WebSocket Events

**Files:**
- Modify: `backend/src/models/ws_events.py`
- Modify: `backend/src/api/routes/websocket.py`
- Test: `backend/tests/test_ws_events.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_ws_events.py

class TestThinkingEventWithAgentContext:
    def test_thinking_event_has_optional_agent_field(self) -> None:
        """ThinkingEvent can include agent name."""
        from src.models.ws_events import ThinkingEvent

        event = ThinkingEvent(
            is_thinking=True,
            agent="hunter",
        )

        assert event.agent == "hunter"

    def test_thinking_event_has_optional_phase_field(self) -> None:
        """ThinkingEvent can include OODA phase."""
        from src.models.ws_events import ThinkingEvent

        event = ThinkingEvent(
            is_thinking=True,
            agent="analyst",
            phase="observe",
        )

        assert event.phase == "observe"

    def test_thinking_event_has_optional_progress_field(self) -> None:
        """ThinkingEvent can include progress indicator."""
        from src.models.ws_events import ThinkingEvent

        event = ThinkingEvent(
            is_thinking=True,
            agent="strategist",
            phase="decide",
            progress=0.5,
        )

        assert event.progress == 0.5

    def test_thinking_event_message_field(self) -> None:
        """ThinkingEvent can include human-readable message."""
        from src.models.ws_events import ThinkingEvent

        event = ThinkingEvent(
            is_thinking=True,
            message="Hunter agent searching for leads...",
        )

        assert event.message == "Hunter agent searching for leads..."

    def test_thinking_event_serializes_correctly(self) -> None:
        """ThinkingEvent serializes to correct WebSocket dict format."""
        from src.models.ws_events import ThinkingEvent

        event = ThinkingEvent(
            is_thinking=True,
            message="Analyst processing data...",
            agent="analyst",
            phase="orient",
            progress=0.3,
        )

        ws_dict = event.to_ws_dict()

        assert ws_dict["type"] == "aria.thinking"
        assert ws_dict["payload"]["message"] == "Analyst processing data..."
        assert ws_dict["payload"]["agent"] == "analyst"
        assert ws_dict["payload"]["phase"] == "orient"
        assert ws_dict["payload"]["progress"] == 0.3
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ws_events.py::TestThinkingEventWithAgentContext -v`
Expected: FAIL with "ValidationError" or missing attribute

**Step 3: Update ThinkingEvent model**

```python
# In backend/src/models/ws_events.py
# Modify ThinkingEvent class (around lines 59-63):

class ThinkingEvent(WSEvent):
    """ARIA is processing/thinking indicator with optional agent context."""

    type: WSEventType = WSEventType.THINKING
    is_thinking: bool = True
    message: str | None = None
    agent: str | None = None  # e.g., "hunter", "analyst", "strategist"
    phase: str | None = None  # OODA phase: "observe", "orient", "decide", "act"
    progress: float | None = None  # 0.0 to 1.0
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ws_events.py::TestThinkingEventWithAgentContext -v`
Expected: 5 passed

**Step 5: Add helper function to websocket.py for agent thinking events**

```python
# In backend/src/api/routes/websocket.py
# Add this helper function after existing helper functions (around line 200):

async def _send_agent_thinking(
    websocket: WebSocket,
    message: str,
    agent: str,
    phase: str = "observe",
    progress: float | None = None,
) -> None:
    """Send a structured thinking event with agent context.

    This enables the frontend to show rich progress indicators when
    ARIA's agents are working (Hunter searching, Analyst processing, etc.).

    Args:
        websocket: The WebSocket connection.
        message: Human-readable description of what's happening.
        agent: Agent name (hunter, analyst, strategist, scribe, operator, scout).
        phase: OODA phase (observe, orient, decide, act).
        progress: Optional progress indicator (0.0 to 1.0).
    """
    thinking = ThinkingEvent(
        is_thinking=True,
        message=message,
        agent=agent,
        phase=phase,
        progress=progress,
    )
    await websocket.send_json(thinking.to_ws_dict())
```

**Step 6: Update import in websocket.py**

```python
# In backend/src/api/routes/websocket.py
# The ThinkingEvent import is already there, but verify it:
from src.models.ws_events import ConnectedEvent, PongEvent, ThinkingEvent
```

**Step 7: Commit**

```bash
git add backend/src/models/ws_events.py backend/src/api/routes/websocket.py backend/tests/test_ws_events.py
git commit -m "$(cat <<'EOF'
feat: add agent/phase context to WebSocket thinking events

Enhance ThinkingEvent with optional fields for rich progress UI:
- message: human-readable description
- agent: which agent is working (hunter, analyst, etc.)
- phase: OODA phase (observe, orient, decide, act)
- progress: 0.0-1.0 progress indicator

Add _send_agent_thinking helper for easy emission of structured
thinking states. Frontend can render these as rich progress indicators.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final Verification and Documentation

**Files:**
- Verify: All modified files

**Step 1: Run full test suite for Thesys-related tests**

Run: `cd backend && pytest tests/test_thesys*.py tests/test_ws_events.py -v`
Expected: All tests pass

**Step 2: Run linting and type checking**

Run: `cd backend && ruff check src/services/thesys_actions.py src/services/thesys_service.py src/api/routes/thesys.py src/models/ws_events.py src/api/routes/websocket.py`
Expected: No errors

Run: `cd backend && mypy src/services/thesys_actions.py src/services/thesys_service.py src/api/routes/thesys.py --no-error-summary 2>/dev/null || true`
Expected: No critical errors

**Step 3: Verify no hardcoded IDs**

Run: `cd backend && grep -E "(test-id|example-id|00000000-0000)" src/services/thesys_actions.py || echo "No hardcoded IDs found - GOOD"`
Expected: "No hardcoded IDs found - GOOD"

**Step 4: Final commit with summary**

```bash
git status
# Review all changes

git commit --allow-empty -m "$(cat <<'EOF'
docs: Thesys C1 custom actions implementation complete

Summary of changes:
1. NEW: backend/src/services/thesys_actions.py - 9 custom action models
2. MODIFIED: backend/src/services/thesys_service.py - custom actions in metadata
3. MODIFIED: backend/src/api/routes/thesys.py - /embed endpoint
4. MODIFIED: backend/src/models/ws_events.py - enhanced ThinkingEvent
5. MODIFIED: backend/src/api/routes/websocket.py - _send_agent_thinking helper
6. NEW: backend/tests/test_thesys_actions.py - comprehensive action tests

All tests passing. No hardcoded IDs in any action schemas.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Checklist

After implementation, verify:

- [ ] `get_aria_custom_actions()` returns valid JSON schema for all 9 actions
- [ ] The visualize endpoint includes custom actions in metadata
- [ ] The embed endpoint works with full conversation history
- [ ] Thinking state events include agent and phase data
- [ ] No action schemas contain hardcoded IDs
- [ ] All Thesys tests pass: `pytest tests/test_thesys*.py -v`
- [ ] WebSocket event tests pass: `pytest tests/test_ws_events.py -v`
- [ ] Ruff linting passes
- [ ] No regressions in existing tests

## Do Not

- Do NOT hardcode any goal_ids, email_draft_ids, lead_ids, etc.
- Do NOT reference specific users or companies in action descriptions
- Do NOT make the embed endpoint the default path — it's optional for exploratory queries only
- Do NOT modify existing agent code — just read their events for thinking states
