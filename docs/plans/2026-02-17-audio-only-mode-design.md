# Audio-Only Mode Design

**Date:** 2026-02-17
**Goal:** Field reps driving between meetings can "call" ARIA for audio-only conversations with full Sparrow-1 turn-taking and Raven-1 audio emotion analysis, without video bandwidth overhead.

---

## Decisions

- **Tracking:** `is_audio_only` boolean column on `video_sessions` (not a new session_type). Session purpose (chat/briefing/debrief/consultation) and modality (video/audio) are orthogonal.
- **Mobile:** Responsive DialogueMode layout, not a separate mobile component.
- **Entry point:** Phone icon button in the ARIA Workspace InputBar.

## What Audio-Only Gets

- Sparrow-1 turn-taking (natural conversation flow)
- Raven-1 audio emotion analysis
- Full LLM reasoning + all 12 tool calls
- Live transcripts
- Rich content cards (battle cards, pipeline charts, etc.)
- Memory pipeline (identical to video sessions)

## What Audio-Only Does NOT Get

- Phoenix-4 avatar rendering (no video)
- Visual perception (no camera analysis)
- Screen share

---

## Backend Changes

### 1. Model Update (`backend/src/models/video.py`)

- Add `audio_only: bool = False` to `VideoSessionCreate`
- Add `is_audio_only: bool = False` to `VideoSessionResponse`

### 2. Route Update (`backend/src/api/routes/video.py`)

In `create_video_session`:
- Pass `request.audio_only` to `tavus.create_conversation(audio_only=request.audio_only)`
- Include `is_audio_only=request.audio_only` in the database insert

No changes to: transcript capture, memory pipeline, tool execution, WebSocket events, session end.

### 3. Database Migration

```sql
ALTER TABLE video_sessions ADD COLUMN is_audio_only boolean NOT NULL DEFAULT false;
ALTER TABLE video_sessions DROP CONSTRAINT IF EXISTS video_sessions_session_type_check;
ALTER TABLE video_sessions ADD CONSTRAINT video_sessions_session_type_check
  CHECK (session_type IN ('chat', 'briefing', 'debrief', 'consultation'));
```

### 4. Tavus Client (`backend/src/integrations/tavus.py`)

No changes needed — `audio_only` parameter already exists and is passed to the Tavus API.

---

## Frontend Changes

### 1. API Client (`frontend/src/api/video.ts`)

- Add `audio_only?: boolean` to `VideoSessionCreate`
- Add `is_audio_only?: boolean` to `VideoSession`

### 2. Modality Store (`frontend/src/stores/modalityStore.ts`)

- Add `isAudioOnly: boolean` to `TavusSession` interface (default `false`)

### 3. Modality Controller (`frontend/src/core/ModalityController.ts`)

New method: `switchToAudioCall(sessionType: TavusSessionType)`
- Same flow as `switchToAvatar` but:
  - Passes `audio_only: true` to `POST /video/sessions`
  - Sets `isAudioOnly: true` in the modality store
- `endSession()` unchanged — same teardown path

### 4. InputBar — Audio Call Button

Add a phone icon button in the InputBar (ARIA Workspace). Clicking calls `ModalityController.switchToAudioCall('chat')` and navigates to `/dialogue`.

### 5. DialogueMode — Audio-Only Layout

Check `tavusSession.isAudioOnly` to choose layout:

**Video mode (existing, unchanged):**
- Left: AvatarContainer (iframe) | Right: TranscriptPanel

**Audio-only mode (new):**
- Single centered column:
  - Static ARIA avatar (circular) + animated WaveformBars
  - Full-width live transcript (scrollable)
  - Call controls bar: mute toggle, end call, duration timer
  - Rich content cards (full width)

**Mobile responsive:**
- Avatar shrinks to small header
- Transcript takes full width
- Large end-call button at bottom

### 6. AvatarContainer — Audio-Only Rendering

When `isAudioOnly`:
- Render static avatar image + larger WaveformBars (not iframe)
- Daily.co room still connects for audio — just no video element

### 7. AudioCallControls Component (new)

Small component rendered in audio-only mode:
- Microphone mute/unmute toggle
- End call button → `ModalityController.endSession()`
- Call duration timer (elapsed since `started_at`)

---

## Data Flow

```
User clicks phone icon in InputBar
  → ModalityController.switchToAudioCall('chat')
  → POST /video/sessions { session_type: 'chat', audio_only: true }
  → Backend: tavus.create_conversation(audio_only=True)
  → Tavus returns { conversation_id, conversation_url }
  → DB: video_sessions { room_url: <daily_url>, is_audio_only: true }
  → Frontend: tavusSession { roomUrl: <daily_url>, isAudioOnly: true }
  → Navigate to /dialogue
  → DialogueMode renders audio-only layout
  → Daily.co connects audio-only via room_url
  → User hears ARIA, speaks to ARIA
  → Transcripts, tools, memory all work identically
```

---

## Files Changed

| File | Change |
|------|--------|
| `backend/src/models/video.py` | Add `audio_only` to create model, `is_audio_only` to response |
| `backend/src/api/routes/video.py` | Pass `audio_only` to Tavus, store in DB |
| `backend/supabase/migrations/` | New migration: add `is_audio_only` column |
| `frontend/src/api/video.ts` | Add `audio_only` and `is_audio_only` fields |
| `frontend/src/stores/modalityStore.ts` | Add `isAudioOnly` to TavusSession |
| `frontend/src/core/ModalityController.ts` | New `switchToAudioCall` method |
| `frontend/src/components/conversation/InputBar.tsx` | Phone icon button |
| `frontend/src/components/avatar/DialogueMode.tsx` | Audio-only layout branch |
| `frontend/src/components/avatar/AvatarContainer.tsx` | Audio-only rendering |
| `frontend/src/components/avatar/AudioCallControls.tsx` | New: mute, end call, timer |
