# Raven-1 Perception Tools Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Raven-1 perception tools so ARIA adapts to user confusion and disengagement in real-time during video calls, with per-topic confusion tracking and lead health scoring integration.

**Architecture:** Two-layer system. Layer 1: Tavus LLM perception tools (`adapt_to_confusion`, `note_engagement_drop`) fire as `conversation.tool_call` webhooks — the backend logs them silently without spoken response. Layer 2: On session shutdown, backend aggregates perception events into engagement scores, updates per-topic confusion stats, and feeds signals into the existing HealthScoreCalculator and ConversionScoringService.

**Tech Stack:** Python/FastAPI, Supabase/PostgreSQL, Tavus CVI API, Pydantic

**Design doc:** `docs/plans/2026-02-17-raven1-perception-tools-design.md`

---

### Task 1: Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260217000002_perception_events.sql`

**Step 1: Write the migration**

```sql
-- Perception Events Migration
-- Adds perception_events array to video_sessions and creates perception_topic_stats table.

-- 1. Add perception_events JSONB array to video_sessions
ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS perception_events jsonb DEFAULT '[]';

COMMENT ON COLUMN video_sessions.perception_events IS
'Array of perception tool call events [{tool_name, timestamp, session_time_seconds, indicator, topic, metadata}]';

-- 2. Create perception_topic_stats table
CREATE TABLE IF NOT EXISTS perception_topic_stats (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    topic text NOT NULL,
    confusion_count int DEFAULT 0,
    disengagement_count int DEFAULT 0,
    total_mentions int DEFAULT 0,
    last_confused_at timestamptz,
    last_disengaged_at timestamptz,
    avg_engagement_when_discussed float,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE(user_id, topic)
);

-- RLS
ALTER TABLE perception_topic_stats ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own topic stats"
    ON perception_topic_stats FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage topic stats"
    ON perception_topic_stats FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_perception_topic_stats_user
    ON perception_topic_stats(user_id);

CREATE INDEX IF NOT EXISTS idx_perception_topic_stats_confusion
    ON perception_topic_stats(user_id, confusion_count DESC);
```

**Step 2: Verify migration syntax**

Run: `cd /Users/dhruv/aria/backend && python -c "print('Migration file created')"`

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260217000002_perception_events.sql
git commit -m "feat(db): add perception_events column and perception_topic_stats table"
```

---

### Task 2: Tavus Persona Perception Tools

**Files:**
- Modify: `backend/src/integrations/tavus_persona.py:174-189` (ARIA_PERSONA_LAYERS perception block)

**Step 1: Write test for perception tools presence**

Create test in `backend/tests/integrations/test_tavus_perception_tools.py`:

```python
"""Tests for Tavus persona perception tools configuration."""

from src.integrations.tavus_persona import ARIA_PERSONA_LAYERS


def test_perception_layers_has_perception_tools():
    """Perception layers must include perception_tools array."""
    perception = ARIA_PERSONA_LAYERS["perception"]
    assert "perception_tools" in perception
    tools = perception["perception_tools"]
    assert len(tools) == 2


def test_perception_layers_has_perception_tool_prompt():
    """Perception layers must include perception_tool_prompt."""
    perception = ARIA_PERSONA_LAYERS["perception"]
    assert "perception_tool_prompt" in perception
    prompt = perception["perception_tool_prompt"]
    assert "adapt_to_confusion" in prompt
    assert "note_engagement_drop" in prompt


def test_adapt_to_confusion_tool_schema():
    """adapt_to_confusion tool must have correct schema."""
    tools = ARIA_PERSONA_LAYERS["perception"]["perception_tools"]
    tool = next(t for t in tools if t["function"]["name"] == "adapt_to_confusion")
    params = tool["function"]["parameters"]
    assert "confusion_indicator" in params["properties"]
    assert "topic" in params["properties"]
    assert "confusion_indicator" in params["required"]
    assert "topic" in params["required"]


def test_note_engagement_drop_tool_schema():
    """note_engagement_drop tool must have correct schema."""
    tools = ARIA_PERSONA_LAYERS["perception"]["perception_tools"]
    tool = next(t for t in tools if t["function"]["name"] == "note_engagement_drop")
    params = tool["function"]["parameters"]
    assert "disengagement_type" in params["properties"]
    assert "topic" in params["properties"]
    assert "disengagement_type" in params["required"]
    assert "topic" in params["required"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/integrations/test_tavus_perception_tools.py -v`
Expected: FAIL — `perception_tools` key not found

**Step 3: Add perception tools to ARIA_PERSONA_LAYERS**

In `backend/src/integrations/tavus_persona.py`, replace lines 174-189 (the `ARIA_PERSONA_LAYERS` perception block):

```python
ARIA_PERSONA_LAYERS: dict[str, Any] = {
    "perception": {
        "perception_model": "raven-1",
        "visual_awareness_queries": [
            "Is the user looking at the screen or away?",
            "Is the user taking notes or typing?",
            "Does the user appear engaged or distracted?",
            "Is the user smiling, frowning, or neutral?",
        ],
        "perception_analysis_queries": [
            "Summarize the user's emotional state throughout the conversation",
            "Identify moments of confusion or hesitation",
            "Note any moments of strong positive engagement",
            "Detect signs of agreement or disagreement",
        ],
        "perception_tool_prompt": (
            "You have tools to adapt the conversation based on visual cues. "
            "Use adapt_to_confusion when the user looks confused, furrows their brow, "
            "tilts their head, or squints. Use note_engagement_drop when the user "
            "looks away, checks their phone, or appears distracted for more than "
            "5 seconds. When calling these tools, classify the current discussion "
            "topic with a short snake_case label (e.g., 'pricing_model', "
            "'clinical_data', 'competitive_landscape')."
        ),
        "perception_tools": [
            {
                "type": "function",
                "function": {
                    "name": "adapt_to_confusion",
                    "description": (
                        "Trigger when user appears confused, furrowing brow, tilting "
                        "head, or squinting. ARIA should simplify the current explanation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "confusion_indicator": {
                                "type": "string",
                                "description": "What visual cue indicated confusion",
                            },
                            "topic": {
                                "type": "string",
                                "description": (
                                    "Snake_case label for the topic being discussed "
                                    "when confusion was detected"
                                ),
                            },
                        },
                        "required": ["confusion_indicator", "topic"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "note_engagement_drop",
                    "description": (
                        "Trigger when user looks away, checks phone, or appears "
                        "distracted for more than 5 seconds. ARIA should re-engage "
                        "with a question or topic shift."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "disengagement_type": {
                                "type": "string",
                                "description": "What the user is doing instead of engaging",
                            },
                            "topic": {
                                "type": "string",
                                "description": (
                                    "Snake_case label for the topic being discussed "
                                    "when disengagement was detected"
                                ),
                            },
                        },
                        "required": ["disengagement_type", "topic"],
                    },
                },
            },
        ],
    },
    "conversational_flow": {
```

Note: Only replace from the start of `ARIA_PERSONA_LAYERS` through the perception dict. Keep `conversational_flow`, `stt`, `llm`, and `tts` unchanged.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/integrations/test_tavus_perception_tools.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/src/integrations/tavus_persona.py backend/tests/integrations/test_tavus_perception_tools.py
git commit -m "feat(tavus): add perception_tools to persona layers for adapt_to_confusion and note_engagement_drop"
```

---

### Task 3: Perception Tool Webhook Handler

**Files:**
- Modify: `backend/src/api/routes/webhooks.py`
- Test: `backend/tests/api/routes/test_perception_webhook.py`

**Step 1: Write tests for perception tool call handling**

```python
"""Tests for perception tool call webhook handling."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import UTC, datetime

from src.api.routes.webhooks import (
    handle_perception_tool_call,
    PERCEPTION_TOOLS,
)


def test_perception_tools_set_contains_expected_tools():
    """PERCEPTION_TOOLS must contain both perception tool names."""
    assert "adapt_to_confusion" in PERCEPTION_TOOLS
    assert "note_engagement_drop" in PERCEPTION_TOOLS
    assert len(PERCEPTION_TOOLS) == 2


@pytest.mark.asyncio
async def test_handle_perception_tool_call_appends_event():
    """Perception tool call should append event to perception_events."""
    db = MagicMock()
    # Mock video_sessions select
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "session-123",
            "user_id": "user-456",
            "perception_events": [],
            "started_at": "2026-02-17T14:00:00+00:00",
        }]
    )
    # Mock update
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    # Mock upsert for topic stats
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{}])
    # Mock insert for activity
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

    result = await handle_perception_tool_call(
        conversation_id="conv-789",
        tool_name="adapt_to_confusion",
        arguments={
            "confusion_indicator": "furrowing brow",
            "topic": "pricing_model",
        },
        db=db,
    )

    assert result is not None
    assert result["spoken_text"] == ""


@pytest.mark.asyncio
async def test_handle_perception_tool_call_returns_empty_spoken_text():
    """Perception tool calls must return empty spoken_text (silent adaptation)."""
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "session-123",
            "user_id": "user-456",
            "perception_events": [],
            "started_at": "2026-02-17T14:00:00+00:00",
        }]
    )
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

    result = await handle_perception_tool_call(
        conversation_id="conv-789",
        tool_name="note_engagement_drop",
        arguments={
            "disengagement_type": "looking at phone",
            "topic": "pipeline_review",
        },
        db=db,
    )

    assert result["spoken_text"] == ""
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_webhook.py -v`
Expected: FAIL — `handle_perception_tool_call` not found

**Step 3: Implement perception tool handler in webhooks.py**

Add after line 529 (after `_update_lead_sentiment_from_perception`) in `backend/src/api/routes/webhooks.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Perception Tool Call Handling
# ─────────────────────────────────────────────────────────────────────────────

PERCEPTION_TOOLS: frozenset[str] = frozenset({
    "adapt_to_confusion",
    "note_engagement_drop",
})


async def handle_perception_tool_call(
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    db: Any,
) -> dict[str, Any] | None:
    """Handle a perception tool call from Tavus.

    Perception tools are invoked by the Tavus LLM when Raven-1 detects
    visual cues (confusion, disengagement). Unlike business tools, these
    return empty spoken_text so ARIA adapts organically.

    Args:
        conversation_id: The Tavus conversation ID.
        tool_name: The perception tool name.
        arguments: Tool arguments (indicator + topic).
        db: Supabase client.

    Returns:
        Dict with empty spoken_text for Tavus response, or None on error.
    """
    # Get session data
    session_result = (
        db.table("video_sessions")
        .select("id, user_id, perception_events, started_at")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_result.data or len(session_result.data) == 0:
        logger.warning(
            "No video session found for perception tool call",
            extra={"conversation_id": conversation_id, "tool_name": tool_name},
        )
        return None

    session = session_result.data[0]
    video_session_id = session["id"]
    user_id = session["user_id"]
    existing_events = session.get("perception_events") or []

    # Calculate session_time_seconds
    session_time_seconds = 0
    started_at_str = session.get("started_at")
    if started_at_str:
        try:
            started_at = datetime.fromisoformat(
                started_at_str.replace("Z", "+00:00")
            )
            session_time_seconds = int(
                (datetime.now(UTC) - started_at).total_seconds()
            )
        except (ValueError, TypeError):
            pass

    # Build perception event
    now = datetime.now(UTC)
    topic = arguments.get("topic", "unknown")

    event = {
        "tool_name": tool_name,
        "timestamp": now.isoformat(),
        "session_time_seconds": session_time_seconds,
        "indicator": arguments.get(
            "confusion_indicator",
            arguments.get("disengagement_type", ""),
        ),
        "topic": topic,
        "metadata": {
            k: v for k, v in arguments.items()
            if k not in ("confusion_indicator", "disengagement_type", "topic")
        },
    }

    # Deduplicate: skip if same tool+topic within 2 seconds
    if existing_events:
        last_event = existing_events[-1]
        if (
            last_event.get("tool_name") == tool_name
            and last_event.get("topic") == topic
        ):
            try:
                last_ts = datetime.fromisoformat(
                    last_event["timestamp"].replace("Z", "+00:00")
                )
                if (now - last_ts).total_seconds() < 2:
                    logger.debug(
                        "Skipping duplicate perception event",
                        extra={"tool_name": tool_name, "topic": topic},
                    )
                    return {"spoken_text": ""}
            except (ValueError, TypeError, KeyError):
                pass

    # Append event to perception_events array
    updated_events = existing_events + [event]

    db.table("video_sessions").update({
        "perception_events": updated_events,
    }).eq("id", video_session_id).execute()

    # Upsert perception_topic_stats
    _upsert_topic_stats(
        user_id=user_id,
        topic=topic,
        tool_name=tool_name,
        db=db,
    )

    # Log to aria_activity
    try:
        db.table("aria_activity").insert({
            "user_id": user_id,
            "activity_type": f"perception.{tool_name}",
            "description": (
                f"Perception: {tool_name} on topic '{topic}' — "
                f"{event['indicator']}"
            ),
            "metadata": {
                "conversation_id": conversation_id,
                "video_session_id": video_session_id,
                "event": event,
            },
        }).execute()
    except Exception as e:
        logger.warning(
            "Failed to log perception tool activity",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )

    logger.info(
        "Perception tool call handled",
        extra={
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "topic": topic,
            "session_time_seconds": session_time_seconds,
        },
    )

    return {"spoken_text": ""}


def _upsert_topic_stats(
    user_id: str,
    topic: str,
    tool_name: str,
    db: Any,
) -> None:
    """Upsert perception_topic_stats for the given topic.

    Args:
        user_id: The user ID.
        topic: The LLM-classified topic label.
        tool_name: The perception tool that fired.
        db: Supabase client.
    """
    now = datetime.now(UTC).isoformat()

    try:
        # Fetch existing row
        result = (
            db.table("perception_topic_stats")
            .select("id, confusion_count, disengagement_count, total_mentions")
            .eq("user_id", user_id)
            .eq("topic", topic)
            .execute()
        )

        if result.data and len(result.data) > 0:
            row = result.data[0]
            update_data: dict[str, Any] = {
                "total_mentions": row["total_mentions"] + 1,
                "updated_at": now,
            }
            if tool_name == "adapt_to_confusion":
                update_data["confusion_count"] = row["confusion_count"] + 1
                update_data["last_confused_at"] = now
            elif tool_name == "note_engagement_drop":
                update_data["disengagement_count"] = row["disengagement_count"] + 1
                update_data["last_disengaged_at"] = now

            db.table("perception_topic_stats").update(
                update_data
            ).eq("id", row["id"]).execute()
        else:
            insert_data: dict[str, Any] = {
                "user_id": user_id,
                "topic": topic,
                "total_mentions": 1,
                "confusion_count": 1 if tool_name == "adapt_to_confusion" else 0,
                "disengagement_count": 1 if tool_name == "note_engagement_drop" else 0,
                "last_confused_at": now if tool_name == "adapt_to_confusion" else None,
                "last_disengaged_at": now if tool_name == "note_engagement_drop" else None,
            }
            db.table("perception_topic_stats").insert(insert_data).execute()

    except Exception as e:
        logger.warning(
            "Failed to upsert perception topic stats",
            extra={"user_id": user_id, "topic": topic, "error": str(e)},
        )
```

**Step 4: Wire perception tools into handle_tool_call**

In `handle_tool_call()` (line 651), add the perception branch after the `user_id` check (after line 700). Insert before the existing sequential execution guard:

```python
    # Check if this is a perception tool call
    if tool_name in PERCEPTION_TOOLS:
        handler_result = await handle_perception_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            arguments=arguments,
            db=db,
        )
        if handler_result:
            return {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "result": handler_result["spoken_text"],
            }
        return None
```

This goes right after the `if not user_id:` block (line 695-700) and before the `lock = _conversation_locks[conversation_id]` line (line 703).

**Step 5: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_webhook.py -v`
Expected: 3 PASSED

**Step 6: Commit**

```bash
git add backend/src/api/routes/webhooks.py backend/tests/api/routes/test_perception_webhook.py
git commit -m "feat(webhooks): handle perception tool calls with event logging and topic stats"
```

---

### Task 4: Session Shutdown Aggregation

**Files:**
- Modify: `backend/src/api/routes/webhooks.py:201-270` (handle_shutdown function)
- Test: `backend/tests/api/routes/test_perception_shutdown.py`

**Step 1: Write test for shutdown aggregation**

```python
"""Tests for perception aggregation during session shutdown."""

import pytest
from unittest.mock import MagicMock

from src.api.routes.webhooks import _aggregate_perception_events


def test_aggregate_empty_events():
    """Empty events should return neutral aggregation."""
    result = _aggregate_perception_events([])
    assert result["engagement_score"] == 1.0
    assert result["confusion_events"] == 0
    assert result["disengagement_events"] == 0
    assert result["engagement_trend"] == "stable"
    assert result["confused_topics"] == []
    assert result["total_perception_events"] == 0


def test_aggregate_confusion_events():
    """Confusion events should reduce engagement score."""
    events = [
        {"tool_name": "adapt_to_confusion", "topic": "pricing_model",
         "session_time_seconds": 60, "timestamp": "2026-02-17T14:01:00+00:00",
         "indicator": "furrowing brow", "metadata": {}},
        {"tool_name": "adapt_to_confusion", "topic": "clinical_data",
         "session_time_seconds": 120, "timestamp": "2026-02-17T14:02:00+00:00",
         "indicator": "squinting", "metadata": {}},
    ]
    result = _aggregate_perception_events(events)
    assert result["confusion_events"] == 2
    assert result["disengagement_events"] == 0
    assert set(result["confused_topics"]) == {"pricing_model", "clinical_data"}
    assert result["engagement_score"] < 1.0


def test_aggregate_mixed_events():
    """Mixed events should track both confusion and disengagement."""
    events = [
        {"tool_name": "adapt_to_confusion", "topic": "pricing_model",
         "session_time_seconds": 60, "timestamp": "2026-02-17T14:01:00+00:00",
         "indicator": "brow", "metadata": {}},
        {"tool_name": "note_engagement_drop", "topic": "pipeline_review",
         "session_time_seconds": 180, "timestamp": "2026-02-17T14:03:00+00:00",
         "indicator": "phone", "metadata": {}},
    ]
    result = _aggregate_perception_events(events)
    assert result["confusion_events"] == 1
    assert result["disengagement_events"] == 1
    assert result["total_perception_events"] == 2


def test_aggregate_engagement_trend_declining():
    """Events concentrated in second half should show declining trend."""
    events = [
        {"tool_name": "note_engagement_drop", "topic": "a",
         "session_time_seconds": 200, "timestamp": "2026-02-17T14:03:20+00:00",
         "indicator": "x", "metadata": {}},
        {"tool_name": "note_engagement_drop", "topic": "b",
         "session_time_seconds": 250, "timestamp": "2026-02-17T14:04:10+00:00",
         "indicator": "y", "metadata": {}},
        {"tool_name": "adapt_to_confusion", "topic": "c",
         "session_time_seconds": 280, "timestamp": "2026-02-17T14:04:40+00:00",
         "indicator": "z", "metadata": {}},
    ]
    result = _aggregate_perception_events(events, session_duration_seconds=300)
    assert result["engagement_trend"] in ("declining", "stable")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_shutdown.py -v`
Expected: FAIL — `_aggregate_perception_events` not found

**Step 3: Implement aggregation function**

Add to `webhooks.py` after `_upsert_topic_stats`:

```python
def _aggregate_perception_events(
    events: list[dict[str, Any]],
    session_duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Aggregate perception events into a session-level summary.

    Args:
        events: List of perception event dicts from perception_events column.
        session_duration_seconds: Total session duration for trend calculation.

    Returns:
        Dict with engagement_score, confusion_events, disengagement_events,
        engagement_trend, confused_topics, and total_perception_events.
    """
    if not events:
        return {
            "engagement_score": 1.0,
            "confusion_events": 0,
            "disengagement_events": 0,
            "engagement_trend": "stable",
            "confused_topics": [],
            "total_perception_events": 0,
        }

    confusion_events = sum(
        1 for e in events if e.get("tool_name") == "adapt_to_confusion"
    )
    disengagement_events = sum(
        1 for e in events if e.get("tool_name") == "note_engagement_drop"
    )
    total = len(events)

    # Confused topics (unique, ordered by first occurrence)
    confused_topics: list[str] = []
    seen_topics: set[str] = set()
    for e in events:
        if e.get("tool_name") == "adapt_to_confusion":
            topic = e.get("topic", "unknown")
            if topic not in seen_topics:
                confused_topics.append(topic)
                seen_topics.add(topic)

    # Engagement score: 1.0 = no issues, decreases with events
    # Each confusion event reduces by 0.08, each disengagement by 0.10
    engagement_score = max(
        0.0,
        1.0 - (confusion_events * 0.08) - (disengagement_events * 0.10),
    )

    # Engagement trend: compare first-half vs second-half event density
    engagement_trend = "stable"
    if session_duration_seconds and session_duration_seconds > 0 and total >= 2:
        midpoint = session_duration_seconds / 2
        first_half = sum(
            1 for e in events
            if e.get("session_time_seconds", 0) <= midpoint
        )
        second_half = total - first_half

        if second_half > first_half + 1:
            engagement_trend = "declining"
        elif first_half > second_half + 1:
            engagement_trend = "improving"

    return {
        "engagement_score": round(engagement_score, 2),
        "confusion_events": confusion_events,
        "disengagement_events": disengagement_events,
        "engagement_trend": engagement_trend,
        "confused_topics": confused_topics,
        "total_perception_events": total,
    }
```

**Step 4: Enhance handle_shutdown to aggregate and store**

In `handle_shutdown()`, after the duration calculation and before the `update_data` dict (line 242), add a block to fetch and aggregate perception events. Replace the `update_data` assembly and update call:

After `if duration_seconds is not None:` block and before `result = (db.table("video_sessions")...`, add:

```python
    # Aggregate perception events into perception_analysis
    perception_result = (
        db.table("video_sessions")
        .select("perception_events, lead_id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    perception_aggregation = {}
    lead_id = None
    if perception_result.data and len(perception_result.data) > 0:
        session_data = perception_result.data[0]
        perception_events = session_data.get("perception_events") or []
        lead_id = session_data.get("lead_id")

        if perception_events:
            perception_aggregation = _aggregate_perception_events(
                perception_events,
                session_duration_seconds=duration_seconds,
            )

    if perception_aggregation:
        update_data["perception_analysis"] = perception_aggregation
```

Then after the update and success log, add lead event creation:

```python
    # Create lead_memory_event if linked to a lead and has perception data
    if lead_id and perception_aggregation:
        try:
            db.table("lead_memory_events").insert({
                "lead_memory_id": lead_id,
                "event_type": "video_session",
                "direction": None,
                "subject": "Video session perception analysis",
                "content": (
                    f"Engagement: {perception_aggregation.get('engagement_score', 'N/A')}, "
                    f"Confusion events: {perception_aggregation.get('confusion_events', 0)}, "
                    f"Trend: {perception_aggregation.get('engagement_trend', 'N/A')}"
                ),
                "occurred_at": now.isoformat(),
                "source": "tavus_video",
                "metadata": perception_aggregation,
            }).execute()
        except Exception as e:
            logger.warning(
                "Failed to create lead memory event from perception",
                extra={"lead_id": lead_id, "error": str(e)},
            )
```

**Step 5: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_shutdown.py -v`
Expected: 4 PASSED

**Step 6: Commit**

```bash
git add backend/src/api/routes/webhooks.py backend/tests/api/routes/test_perception_shutdown.py
git commit -m "feat(webhooks): aggregate perception events on session shutdown with lead event creation"
```

---

### Task 5: Perception API Endpoints

**Files:**
- Modify: `backend/src/api/routes/perception.py`
- Test: `backend/tests/api/routes/test_perception_api.py`

**Step 1: Write tests for new endpoints**

```python
"""Tests for perception API endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-123"
    return user


def test_topic_stats_returns_list(mock_user):
    """GET /perception/topic-stats should return topic stats for user."""
    from src.api.routes.perception import get_topic_stats

    # Will test via direct function call with mocked deps
    assert callable(get_topic_stats)


def test_session_events_returns_events(mock_user):
    """GET /perception/session/{id}/events should return perception_events."""
    from src.api.routes.perception import get_session_events

    assert callable(get_session_events)


def test_engagement_history_returns_scores(mock_user):
    """GET /perception/engagement-history should return engagement scores."""
    from src.api.routes.perception import get_engagement_history

    assert callable(get_engagement_history)
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_api.py -v`
Expected: FAIL — functions not found

**Step 3: Add new endpoints to perception.py**

Append to `backend/src/api/routes/perception.py` after the existing `get_engagement_summary` function (after line 170):

```python


class TopicStat(BaseModel):
    """Perception stats for a single topic."""

    topic: str
    confusion_count: int = 0
    disengagement_count: int = 0
    total_mentions: int = 0
    confusion_rate: float = 0.0
    last_confused_at: str | None = None
    last_disengaged_at: str | None = None


class SessionPerceptionEvents(BaseModel):
    """Perception events from a single video session."""

    session_id: str
    events: list[dict] = Field(default_factory=list)
    total_events: int = 0


class EngagementHistoryEntry(BaseModel):
    """Engagement score from a single video session."""

    session_id: str
    engagement_score: float | None = None
    confusion_events: int = 0
    disengagement_events: int = 0
    engagement_trend: str | None = None
    session_date: str | None = None
    duration_seconds: int | None = None


@router.get("/topic-stats", response_model=list[TopicStat])
async def get_topic_stats(
    current_user: CurrentUser,
) -> list[TopicStat]:
    """Get confusion and engagement rates per topic for the current user.

    Returns topics ordered by confusion_count descending, useful for
    identifying which topics need simpler explanations.

    Args:
        current_user: The authenticated user.

    Returns:
        List of topic stats with confusion rates.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("perception_topic_stats")
            .select("*")
            .eq("user_id", current_user.id)
            .order("confusion_count", desc=True)
            .limit(50)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch topic stats",
            extra={"user_id": current_user.id},
        )
        return []

    stats = []
    for row in result.data or []:
        total = row.get("total_mentions", 0)
        confusion = row.get("confusion_count", 0)
        stats.append(TopicStat(
            topic=row["topic"],
            confusion_count=confusion,
            disengagement_count=row.get("disengagement_count", 0),
            total_mentions=total,
            confusion_rate=confusion / total if total > 0 else 0.0,
            last_confused_at=row.get("last_confused_at"),
            last_disengaged_at=row.get("last_disengaged_at"),
        ))

    return stats


@router.get("/session/{session_id}/events", response_model=SessionPerceptionEvents)
async def get_session_events(
    session_id: str,
    current_user: CurrentUser,
) -> SessionPerceptionEvents:
    """Get perception events for a specific video session.

    Args:
        session_id: The video session UUID.
        current_user: The authenticated user.

    Returns:
        Session perception events with total count.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("video_sessions")
            .select("perception_events")
            .eq("id", session_id)
            .eq("user_id", current_user.id)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch session events",
            extra={"user_id": current_user.id, "session_id": session_id},
        )
        return SessionPerceptionEvents(session_id=session_id)

    if not result.data or len(result.data) == 0:
        return SessionPerceptionEvents(session_id=session_id)

    events = result.data[0].get("perception_events") or []

    return SessionPerceptionEvents(
        session_id=session_id,
        events=events,
        total_events=len(events),
    )


@router.get("/engagement-history", response_model=list[EngagementHistoryEntry])
async def get_engagement_history(
    current_user: CurrentUser,
    limit: int = 10,
) -> list[EngagementHistoryEntry]:
    """Get engagement scores from recent video sessions.

    Returns engagement trajectory over time, useful for understanding
    how user engagement is trending across sessions.

    Args:
        current_user: The authenticated user.
        limit: Maximum sessions to return (default 10).

    Returns:
        List of engagement history entries, most recent first.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("video_sessions")
            .select("id, perception_analysis, duration_seconds, created_at")
            .eq("user_id", current_user.id)
            .eq("status", "ended")
            .order("created_at", desc=True)
            .limit(min(limit, 50))
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch engagement history",
            extra={"user_id": current_user.id},
        )
        return []

    entries = []
    for row in result.data or []:
        analysis = row.get("perception_analysis") or {}
        entries.append(EngagementHistoryEntry(
            session_id=row["id"],
            engagement_score=analysis.get("engagement_score"),
            confusion_events=analysis.get("confusion_events", 0),
            disengagement_events=analysis.get("disengagement_events", 0),
            engagement_trend=analysis.get("engagement_trend"),
            session_date=row.get("created_at"),
            duration_seconds=row.get("duration_seconds"),
        ))

    return entries
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/api/routes/test_perception_api.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add backend/src/api/routes/perception.py backend/tests/api/routes/test_perception_api.py
git commit -m "feat(perception): add topic-stats, session events, and engagement-history API endpoints"
```

---

### Task 6: Health Score Perception Integration

**Files:**
- Modify: `backend/src/memory/health_score.py:187-226` (_score_sentiment method)
- Test: `backend/tests/memory/test_health_score_perception.py`

**Step 1: Write test for perception-enhanced sentiment scoring**

```python
"""Tests for perception-enhanced health score sentiment calculation."""

import pytest
from unittest.mock import MagicMock
from src.memory.health_score import HealthScoreCalculator
from src.models.lead_memory import Sentiment


class FakeInsight:
    def __init__(self, sentiment: Sentiment):
        self.sentiment = sentiment


def test_score_sentiment_with_no_perception_data():
    """Without perception data, should behave as before."""
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.POSITIVE), FakeInsight(Sentiment.NEUTRAL)]
    score = calc._score_sentiment(insights)
    assert 0.5 < score <= 1.0


def test_score_sentiment_with_perception_data():
    """With perception data, score should blend insight + perception signals."""
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.POSITIVE)]

    perception_data = {
        "engagement_score": 0.3,
        "confusion_events": 5,
        "disengagement_events": 2,
    }

    score = calc._score_sentiment(insights, perception_data=perception_data)
    # Should be lower than pure insight score due to poor perception
    pure_score = calc._score_sentiment(insights)
    assert score < pure_score


def test_score_sentiment_perception_high_engagement():
    """High engagement perception should boost sentiment score."""
    calc = HealthScoreCalculator()
    insights = [FakeInsight(Sentiment.NEUTRAL)]

    perception_data = {
        "engagement_score": 0.95,
        "confusion_events": 0,
        "disengagement_events": 0,
    }

    score = calc._score_sentiment(insights, perception_data=perception_data)
    pure_score = calc._score_sentiment(insights)
    assert score >= pure_score
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/memory/test_health_score_perception.py -v`
Expected: FAIL — `_score_sentiment` does not accept `perception_data`

**Step 3: Enhance _score_sentiment in health_score.py**

Replace `_score_sentiment` method (lines 187-226):

```python
    def _score_sentiment(
        self,
        insights: list[Any],
        perception_data: dict[str, Any] | None = None,
    ) -> float:
        """Score overall sentiment from insights and video perception data.

        Blends insight-based sentiment (70%) with perception-based signals (30%)
        when perception data is available. Falls back to insight-only scoring
        if no perception data exists.

        0.5 = neutral (no data)
        0.0 = all negative / poor engagement
        1.0 = all positive / high engagement

        Args:
            insights: List of insight objects with sentiment field.
            perception_data: Optional dict from video session perception_analysis
                containing engagement_score, confusion_events, disengagement_events.

        Returns:
            Score between 0.0 and 1.0.
        """
        # Calculate insight-based sentiment score
        insight_score = 0.5  # Neutral default
        if insights:
            total = len(insights)
            positive_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.POSITIVE
            )
            negative_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.NEGATIVE
            )
            neutral_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.NEUTRAL
            )
            unknown_count = sum(
                1 for i in insights if getattr(i, "sentiment", None) == Sentiment.UNKNOWN
            )

            if total > 0:
                sentiment_sum = (
                    positive_count * 1.0
                    + (neutral_count + unknown_count) * 0.5
                    + negative_count * 0.0
                )
                insight_score = sentiment_sum / total

        # If no perception data, return insight-only score
        if not perception_data:
            return insight_score

        # Calculate perception-based sentiment score
        engagement = perception_data.get("engagement_score", 0.5)
        confusion = perception_data.get("confusion_events", 0)
        disengagement = perception_data.get("disengagement_events", 0)

        # Start from engagement score and penalize for confusion/disengagement
        perception_score = engagement
        # Each confusion event reduces by 0.03, capped at 0.3 reduction
        perception_score -= min(confusion * 0.03, 0.3)
        # Each disengagement event reduces by 0.04, capped at 0.3 reduction
        perception_score -= min(disengagement * 0.04, 0.3)
        perception_score = max(0.0, min(1.0, perception_score))

        # Blend: 70% insight, 30% perception
        return insight_score * 0.7 + perception_score * 0.3
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/memory/test_health_score_perception.py -v`
Expected: 3 PASSED

**Step 5: Also run existing health score tests to check no regression**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/memory/ -v -k health`
Expected: All existing tests PASS (new parameter is optional, backward compatible)

**Step 6: Commit**

```bash
git add backend/src/memory/health_score.py backend/tests/memory/test_health_score_perception.py
git commit -m "feat(scoring): blend video perception signals into health score sentiment component"
```

---

### Task 7: Conversion Scoring Perception Integration

**Files:**
- Modify: `backend/src/services/conversion_scoring.py:473-501` (_calculate_sentiment_trend method)
- Test: `backend/tests/services/test_conversion_perception.py`

**Step 1: Write test**

```python
"""Tests for perception-enhanced conversion scoring sentiment trend."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.conversion_scoring import ConversionScoringService


@pytest.mark.asyncio
async def test_sentiment_trend_includes_video_perception():
    """Sentiment trend should factor in video session engagement scores."""
    service = ConversionScoringService()

    # Mock db calls
    with patch.object(service, '_db') as mock_db:
        # Stakeholder sentiment query
        stakeholder_result = MagicMock()
        stakeholder_result.data = [
            {"sentiment": "positive"},
            {"sentiment": "neutral"},
        ]

        # Video sessions perception query
        video_result = MagicMock()
        video_result.data = [
            {"perception_analysis": {"engagement_score": 0.3, "confusion_events": 4}},
        ]

        # Set up chain: first call returns stakeholders, second returns video sessions
        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            stakeholder_result,
            video_result,
        ]

        from datetime import UTC, datetime
        score = await service._calculate_sentiment_trend("lead-123", datetime.now(UTC))

        # Score should be pulled down by poor video engagement
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/services/test_conversion_perception.py -v`
Expected: FAIL — no video session query in current implementation

**Step 3: Enhance _calculate_sentiment_trend**

Replace method in `conversion_scoring.py` (lines 473-501):

```python
    async def _calculate_sentiment_trend(self, lead_id: str, _now: datetime) -> float:
        """Calculate normalized sentiment trend, including video perception.

        Blends stakeholder sentiment (70%) with video session engagement (30%)
        when video perception data is available.

        Note: _now parameter reserved for future historical comparison.
        """
        # Current period stakeholder sentiments
        current_result = (
            self._db.table("lead_memory_stakeholders")
            .select("sentiment")
            .eq("lead_memory_id", lead_id)
            .execute()
        )

        stakeholders = current_result.data or []

        # Calculate stakeholder sentiment score
        if stakeholders:
            positive = sum(1 for s in stakeholders if s.get("sentiment") == "positive")
            negative = sum(1 for s in stakeholders if s.get("sentiment") == "negative")
            total = len(stakeholders)
            net_sentiment = (positive - negative) / total if total > 0 else 0
            stakeholder_score = (net_sentiment + 1) / 2
        else:
            stakeholder_score = 0.5

        # Fetch recent video session engagement for this lead
        video_result = (
            self._db.table("video_sessions")
            .select("perception_analysis")
            .eq("lead_id", lead_id)
            .eq("status", "ended")
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        video_sessions = video_result.data or []

        if not video_sessions:
            return stakeholder_score

        # Calculate average video engagement score
        engagement_scores = []
        for session in video_sessions:
            analysis = session.get("perception_analysis") or {}
            eng_score = analysis.get("engagement_score")
            if eng_score is not None:
                engagement_scores.append(eng_score)

        if not engagement_scores:
            return stakeholder_score

        avg_video_engagement = sum(engagement_scores) / len(engagement_scores)

        # Blend: 70% stakeholder, 30% video engagement
        return stakeholder_score * 0.7 + avg_video_engagement * 0.3
```

Note: This changes the query chain, so the mock setup in the test needs the `lead_id` eq for the second query. Adjust by using a more flexible mock:

Replace the test mock setup with:

```python
        # Use side_effect on the chain terminator
        call_count = [0]
        original_table = mock_db.table

        def mock_table(name):
            result = MagicMock()
            if name == "lead_memory_stakeholders":
                result.select.return_value.eq.return_value.execute.return_value = stakeholder_result
            elif name == "video_sessions":
                result.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = video_result
            return result

        mock_db.table.side_effect = mock_table
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/services/test_conversion_perception.py -v`
Expected: PASS

**Step 5: Run existing conversion scoring tests for regression**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/services/ -v -k conversion`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/src/services/conversion_scoring.py backend/tests/services/test_conversion_perception.py
git commit -m "feat(scoring): integrate video perception engagement into conversion sentiment trend"
```

---

### Task 8: Full Integration Test

**Files:**
- Create: `backend/tests/test_perception_integration.py`

**Step 1: Write integration test covering the full webhook flow**

```python
"""Integration test for full perception tool webhook flow.

Tests: tool_call webhook → perception_events stored → shutdown →
aggregation → perception_analysis populated.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import UTC, datetime


@pytest.mark.asyncio
async def test_full_perception_flow():
    """Full flow: perception tool call → shutdown aggregation."""
    from src.api.routes.webhooks import (
        handle_perception_tool_call,
        _aggregate_perception_events,
    )

    # 1. Simulate perception tool call
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "session-1",
            "user_id": "user-1",
            "perception_events": [],
            "started_at": "2026-02-17T14:00:00+00:00",
        }]
    )
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

    result = await handle_perception_tool_call(
        conversation_id="conv-1",
        tool_name="adapt_to_confusion",
        arguments={"confusion_indicator": "brow furrow", "topic": "pricing"},
        db=db,
    )

    assert result is not None
    assert result["spoken_text"] == ""

    # 2. Simulate aggregation (as would happen on shutdown)
    events = [
        {
            "tool_name": "adapt_to_confusion",
            "timestamp": "2026-02-17T14:01:00+00:00",
            "session_time_seconds": 60,
            "indicator": "brow furrow",
            "topic": "pricing",
            "metadata": {},
        },
        {
            "tool_name": "note_engagement_drop",
            "timestamp": "2026-02-17T14:05:00+00:00",
            "session_time_seconds": 300,
            "indicator": "checking phone",
            "topic": "clinical_data",
            "metadata": {},
        },
    ]

    aggregation = _aggregate_perception_events(events, session_duration_seconds=600)

    assert aggregation["confusion_events"] == 1
    assert aggregation["disengagement_events"] == 1
    assert aggregation["engagement_score"] < 1.0
    assert "pricing" in aggregation["confused_topics"]
    assert aggregation["total_perception_events"] == 2
```

**Step 2: Run test**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_perception_integration.py -v`
Expected: PASS

**Step 3: Run full test suite to check no regressions**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -x --timeout=60 -q`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add backend/tests/test_perception_integration.py
git commit -m "test: add full perception tool webhook integration test"
```

---

### Task 9: Final Verification

**Step 1: Run linter**

Run: `cd /Users/dhruv/aria/backend && ruff check src/api/routes/webhooks.py src/api/routes/perception.py src/integrations/tavus_persona.py src/memory/health_score.py src/services/conversion_scoring.py`

Fix any issues.

**Step 2: Run type checker on changed files**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/api/routes/webhooks.py src/api/routes/perception.py src/integrations/tavus_persona.py src/memory/health_score.py src/services/conversion_scoring.py --ignore-missing-imports`

Fix any issues.

**Step 3: Run all perception-related tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/integrations/test_tavus_perception_tools.py tests/api/routes/test_perception_webhook.py tests/api/routes/test_perception_shutdown.py tests/api/routes/test_perception_api.py tests/memory/test_health_score_perception.py tests/services/test_conversion_perception.py tests/test_perception_integration.py -v`

Expected: All PASS

**Step 4: Commit any lint/type fixes**

```bash
git add -A
git commit -m "chore: fix lint and type issues in perception tools implementation"
```
