# Context Bridge Service Design

**Date:** 2026-02-17
**Status:** Approved
**Principle:** "One ARIA, Many Surfaces" — chat context carries to video, video transcript saves to chat, everything persistent.

## Overview

The `ContextBridgeService` provides bidirectional context synchronization between ARIA's chat and video modalities. Users experience one continuous ARIA regardless of surface — starting in chat, switching to video, and returning to chat with zero context loss.

## Architecture

Three core methods on a single service class (`backend/src/services/context_bridge.py`):

1. **`chat_to_video_context()`** — Loads chat history into Tavus conversational context
2. **`video_to_chat_context()`** — Persists video transcript/outcomes back to chat
3. **`bridge_active_session()`** — Links a video session to a chat conversation in the DB

Follows the lazy initialization pattern used by `ChatService`. Uses `SupabaseClient.get_client()` for DB access, `ws_manager` for real-time delivery.

## Method Details

### `chat_to_video_context(user_id, conversation_id?) -> str`

1. If `conversation_id` provided, load last 10 messages from `messages` table (ordered `created_at DESC`)
2. Load working memory via `WorkingMemoryManager.get_or_create()` — grab `active_entities` and `current_goal`
3. Load top 3 active goals from `goals` table
4. Format as spoken-friendly string (not markdown — Tavus reads aloud)
5. Passed as `additional_context["extra_context"]` to `ARIAPersonaManager.build_context()`

### `video_to_chat_context(user_id, video_session_id) -> dict`

1. Look up video session to get linked `conversation_id`
2. Fetch transcript from `video_transcript_entries` ordered by `timestamp_ms`
3. Group consecutive same-speaker entries, store as messages with `metadata: {"source": "video", "video_session_id": "..."}`
4. Use LLM to extract: summary, action items, commitments
5. Action items → `ProspectiveTask` entries
6. Update working memory with session summary
7. Post summary message to chat (both DB and WebSocket real-time)
8. Returns `{"summary", "action_items", "messages_stored", "tasks_created"}`

### `bridge_active_session(user_id, video_session_id, conversation_id) -> None`

1. Update `video_sessions.conversation_id` to link the two

## Database Migration

```sql
ALTER TABLE video_sessions
ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX idx_video_sessions_conversation_id ON video_sessions(conversation_id);
```

## Integration Points

### Video Session Creation (`video.py` create route)
- Accept optional `conversation_id` in `VideoSessionCreate`
- If provided, call `bridge_active_session()` + `chat_to_video_context()`
- Pass chat context string into Tavus conversation creation

### Video Session End (`video.py` end route)
- After ending Tavus conversation, check for linked `conversation_id`
- If linked, call `video_to_chat_context()` to persist transcript and post summary

### Model Updates
- `VideoSessionCreate`: add `conversation_id: str | None = None`
- `VideoSessionResponse`: add `conversation_id: str | None = None`

## Files Touched

| File | Change |
|------|--------|
| `backend/src/services/context_bridge.py` | New service |
| `backend/src/models/video.py` | Add `conversation_id` field |
| `backend/src/api/routes/video.py` | Wire bridge into create/end |
| `backend/supabase/migrations/20260217000001_video_conversation_link.sql` | New column + index |
