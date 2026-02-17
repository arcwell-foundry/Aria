# Raven-1 Perception Tools Design

**Date:** 2026-02-17
**Status:** Approved

## Overview

Add Raven-1 perception tools (`adapt_to_confusion`, `note_engagement_drop`) to ARIA's Tavus video persona so ARIA reacts to visual cues in real-time, logs engagement data, tracks per-topic confusion rates, and feeds perception signals into lead health scoring.

## Architecture

Two layers working in parallel:

**Layer 1 — Tavus LLM Tools (Real-time):** `adapt_to_confusion` and `note_engagement_drop` are defined as perception tools in the persona layers. When Raven-1 detects visual cues, the Tavus-hosted LLM invokes these tools. Tavus fires `conversation.tool_call` webhooks. Our backend distinguishes perception tool calls from business tool calls, logs the event, and stores it in a `perception_events` JSONB array on `video_sessions`.

**Layer 2 — Backend Analytics (Post-hoc):** On session shutdown, the backend aggregates all perception events into an `engagement_score`, tracks per-topic confusion rates in a `perception_topic_stats` table, and feeds signals into the existing `HealthScoreCalculator` (via the sentiment component) and `ConversionScoringService` (via sentiment_trend).

## Data Model

### `video_sessions` — new column

```sql
perception_events JSONB DEFAULT '[]'
```

Each element:

```json
{
  "tool_name": "adapt_to_confusion",
  "timestamp": "2026-02-17T14:30:00Z",
  "session_time_seconds": 142,
  "indicator": "furrowing brow while reviewing pipeline data",
  "topic": "pipeline_conversion_rates",
  "metadata": {}
}
```

### New table: `perception_topic_stats`

```sql
perception_topic_stats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users NOT NULL,
  topic TEXT NOT NULL,
  confusion_count INT DEFAULT 0,
  total_mentions INT DEFAULT 0,
  last_confused_at TIMESTAMPTZ,
  avg_engagement_when_discussed FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, topic)
)
```

### Session-level aggregation on shutdown

Stored in `video_sessions.perception_analysis`:

```json
{
  "engagement_score": 0.72,
  "confusion_events": 3,
  "disengagement_events": 1,
  "engagement_trend": "declining",
  "confused_topics": ["pricing_model", "clinical_data"],
  "total_perception_events": 4
}
```

## Tavus Persona Configuration

Added to `ARIA_PERSONA_LAYERS["perception"]`:

- `perception_tool_prompt`: Instructs the Tavus LLM to use `adapt_to_confusion` when the user looks confused (furrowing brow, head tilt, squinting) and `note_engagement_drop` when the user appears distracted (looks away, checks phone, >5 seconds disengaged). Both tools require a `topic` parameter — a snake_case label classifying the current discussion topic.
- `perception_tools`: Array of two function definitions with `confusion_indicator`/`disengagement_type` + `topic` as required parameters.

## Webhook Handling

In `handle_tool_call()`:

1. Check if `tool_name` is in `PERCEPTION_TOOLS = {"adapt_to_confusion", "note_engagement_drop"}`
2. If perception tool:
   - Append event to `video_sessions.perception_events` JSONB array
   - Upsert `perception_topic_stats` (increment confusion_count or update avg_engagement)
   - Log to `aria_activity` with `activity_type: "perception.{tool_name}"`
   - Return `{"spoken_text": ""}` — ARIA adapts organically, does not announce detection
3. If business tool: existing execution flow (unchanged)

## Lead Health Scoring Integration

### `HealthScoreCalculator._score_sentiment()` — 20% weight

Enhanced to blend existing insight-based sentiment (70%) with perception-based sentiment (30%):
- High confusion rates from `perception_topic_stats` drag sentiment down
- Frequent disengagement events in recent video sessions lower the score
- Net effect: perception influences 6% of total health score (30% of 20% sentiment weight)

### `ConversionScoringService` — `sentiment_trend` (12% weight)

Enhanced to factor in `engagement_score` from recent video sessions with this lead:
- Declining engagement across sessions = negative sentiment trend signal
- High confusion on core topics (pricing, product) = risk signal

### Post-session trigger in `handle_shutdown()`

1. Aggregate `perception_events` into `perception_analysis` summary
2. If `lead_id` is set, create `lead_memory_event` with `event_type: "video_session"` containing perception summary
3. Trigger `HealthScoreCalculator.calculate()` for that lead

## Perception API Endpoints

- `GET /perception/topic-stats` — Confusion rates per topic for current user
- `GET /perception/session/{session_id}/events` — Full perception_events for a session
- `GET /perception/engagement-history` — engagement_score from last N video sessions

## Files Changed

| File | Change |
|------|--------|
| `backend/src/integrations/tavus_persona.py` | Add `perception_tools` + `perception_tool_prompt` to layers |
| `backend/src/api/routes/webhooks.py` | Branch `handle_tool_call()`, add `handle_perception_tool_call()`, enhance `handle_shutdown()` aggregation |
| `backend/src/api/routes/perception.py` | 3 new GET endpoints |
| `backend/src/memory/health_score.py` | Enhance `_score_sentiment()` with perception data |
| `backend/src/services/conversion_scoring.py` | Factor video engagement into `sentiment_trend` |
| New migration | `perception_events` column + `perception_topic_stats` table |
| New test file | `tests/test_perception_tools.py` |

## Testing

- Unit: `handle_perception_tool_call()` — event appending, topic stats upsert, activity logging
- Unit: enhanced `_score_sentiment()` — perception blending with insight scoring
- Integration: full webhook flow → perception_events → shutdown → aggregation → lead score update
- Edge cases: no lead_id (skip scoring), empty events (neutral score), duplicate calls within 2s (deduplicate)
