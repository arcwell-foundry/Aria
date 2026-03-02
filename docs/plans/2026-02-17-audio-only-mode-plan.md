# Audio-Only Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable field reps to "call" ARIA with audio-only mode — full Sparrow-1 + Raven-1 intelligence without video bandwidth.

**Architecture:** Add `audio_only` flag to existing video session creation flow. Backend passes it to Tavus API (already supported). Frontend gets a new `switchToAudioCall` method on ModalityController, an audio-only layout in DialogueMode, and a phone button in InputBar.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), Supabase (DB), Tavus API, Daily.co WebRTC

**Design doc:** `docs/plans/2026-02-17-audio-only-mode-design.md`

---

### Task 1: Backend — Database Migration

**Files:**
- Create: `backend/supabase/migrations/20260217000001_audio_only_sessions.sql`

**Step 1: Write the migration file**

```sql
-- Add is_audio_only flag to video_sessions
-- Audio-only sessions use Tavus Sparrow-1 + Raven-1 without Phoenix-4 video rendering

ALTER TABLE video_sessions ADD COLUMN is_audio_only boolean NOT NULL DEFAULT false;

-- Also fix session_type constraint to include 'consultation' (existing enum value
-- used in code but missing from original CHECK constraint)
ALTER TABLE video_sessions DROP CONSTRAINT IF EXISTS video_sessions_session_type_check;
ALTER TABLE video_sessions ADD CONSTRAINT video_sessions_session_type_check
  CHECK (session_type IN ('chat', 'briefing', 'debrief', 'consultation'));
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260217000001_audio_only_sessions.sql
git commit -m "feat(db): add is_audio_only column to video_sessions"
```

---

### Task 2: Backend — Pydantic Models

**Files:**
- Modify: `backend/src/models/video.py:32-38` (VideoSessionCreate)
- Modify: `backend/src/models/video.py:41-56` (VideoSessionResponse)
- Test: `backend/tests/api/routes/test_video.py`

**Step 1: Write failing test**

Add to `TestCreateVideoSession` class in `backend/tests/api/routes/test_video.py`:

```python
def test_create_audio_only_session(
    self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
) -> None:
    """Verify audio_only=True is passed to Tavus and stored in DB."""
    mock_insert_result = MagicMock()
    mock_insert_result.data = [{
        "id": "session-123",
        "user_id": "test-user-123",
        "tavus_conversation_id": "tavus-conv-123",
        "room_url": "https://daily.co/room/test-room",
        "status": VideoSessionStatus.ACTIVE.value,
        "session_type": SessionType.CHAT.value,
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": None,
        "duration_seconds": None,
        "created_at": datetime.now(UTC).isoformat(),
        "lead_id": None,
        "perception_analysis": {},
        "is_audio_only": True,
    }]

    with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            with patch.object(_video_mod, "build_aria_context", return_value="Test context"):
                with patch.object(_video_mod, "ws_manager") as mock_ws:
                    mock_ws.send_to_user = AsyncMock()
                    mock_db.table.return_value.insert.return_value.execute.return_value = (
                        mock_insert_result
                    )

                    response = test_client.post(
                        "/api/v1/video/sessions",
                        json={"audio_only": True},
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["is_audio_only"] is True

                    # Verify Tavus was called with audio_only=True
                    mock_tavus.create_conversation.assert_called_once()
                    call_kwargs = mock_tavus.create_conversation.call_args[1]
                    assert call_kwargs["audio_only"] is True

                    # Verify DB insert includes is_audio_only
                    insert_call = mock_db.table.return_value.insert.call_args[0][0]
                    assert insert_call["is_audio_only"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/api/routes/test_video.py::TestCreateVideoSession::test_create_audio_only_session -v`
Expected: FAIL — `audio_only` not recognized in VideoSessionCreate, `is_audio_only` not in response

**Step 3: Update Pydantic models**

In `backend/src/models/video.py`:

Add to `VideoSessionCreate` (after line 38):
```python
audio_only: bool = False
```

Add to `VideoSessionResponse` (after line 54, before `perception_analysis`):
```python
is_audio_only: bool = False
```

**Step 4: Update route to pass audio_only through**

In `backend/src/api/routes/video.py`:

In `create_video_session` function, update the `tavus.create_conversation()` call (around line 187) to add:
```python
audio_only=request.audio_only,
```

In the `row` dict (around line 220), add:
```python
"is_audio_only": request.audio_only,
```

In the `VideoSessionResponse(...)` constructor (around line 258), add:
```python
is_audio_only=saved.get("is_audio_only", False),
```

Also update the response constructors in `list_video_sessions` (around line 312), `get_video_session` (around line 399), and `end_video_session` (around line 510) to include:
```python
is_audio_only=session.get("is_audio_only", False),
```
(Use `updated` instead of `session` for end_video_session.)

**Step 5: Run test to verify it passes**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/api/routes/test_video.py::TestCreateVideoSession::test_create_audio_only_session -v`
Expected: PASS

**Step 6: Run all video tests to check for regressions**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/api/routes/test_video.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add backend/src/models/video.py backend/src/api/routes/video.py backend/tests/api/routes/test_video.py
git commit -m "feat(backend): add audio_only support to video session creation"
```

---

### Task 3: Frontend — API Client & Modality Store

**Files:**
- Modify: `frontend/src/api/video.ts:12-17` (VideoSessionCreate)
- Modify: `frontend/src/api/video.ts:31-45` (VideoSession)
- Modify: `frontend/src/stores/modalityStore.ts:18-23` (TavusSession)
- Modify: `frontend/src/stores/modalityStore.ts:25-30` (INITIAL_TAVUS_SESSION)

**Step 1: Update frontend API types**

In `frontend/src/api/video.ts`, add to `VideoSessionCreate` interface (after `lead_id`):
```typescript
audio_only?: boolean;
```

Add to `VideoSession` interface (after `lead_id`):
```typescript
is_audio_only?: boolean;
```

**Step 2: Update modality store**

In `frontend/src/stores/modalityStore.ts`, add to `TavusSession` interface (after `sessionType`):
```typescript
isAudioOnly: boolean;
```

Update `INITIAL_TAVUS_SESSION` to include:
```typescript
isAudioOnly: false,
```

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors (existing errors may exist)

**Step 4: Commit**

```bash
git add frontend/src/api/video.ts frontend/src/stores/modalityStore.ts
git commit -m "feat(frontend): add audio_only types to API client and modality store"
```

---

### Task 4: Frontend — ModalityController.switchToAudioCall

**Files:**
- Modify: `frontend/src/core/ModalityController.ts:17-20` (TavusCreateResponse)
- Modify: `frontend/src/core/ModalityController.ts:40-61` (switchTo method)
- Modify: `frontend/src/core/ModalityController.ts:104-142` (add new method after switchToAvatar)

**Step 1: Add switchToAudioCall method**

In `frontend/src/core/ModalityController.ts`:

Update the `TavusCreateResponse` interface to add:
```typescript
is_audio_only?: boolean;
```

Add a new public method after `restorePip()` (after line 102):

```typescript
/**
 * Switch to audio-only call mode.
 * Creates a Tavus session with audio_only=true, navigates to /dialogue.
 */
async switchToAudioCall(sessionType?: TavusSessionType): Promise<void> {
  const store = useModalityStore.getState();
  const type = sessionType || 'chat';
  const route = type === 'briefing' ? '/briefing' : '/dialogue';

  // If there's already an active audio session, just navigate
  if (store.tavusSession.status === 'active' && store.tavusSession.id && store.tavusSession.isAudioOnly) {
    store.setActiveModality('avatar');
    store.setTavusSession({ sessionType: type });
    store.setIsPipVisible(false);
    this.navigateFn?.(route);
    return;
  }

  // Start connecting
  store.setActiveModality('avatar');
  store.setTavusSession({ status: 'connecting', sessionType: type, isAudioOnly: true });
  store.setIsPipVisible(false);

  try {
    const response = await apiClient.post<TavusCreateResponse>('/video/sessions', {
      session_type: type,
      audio_only: true,
    });

    const { session_id, room_url } = response.data;

    store.setTavusSession({
      id: session_id,
      roomUrl: room_url,
      status: 'active',
      isAudioOnly: true,
    });
  } catch (err) {
    console.warn('[ModalityController] Failed to create audio session:', err);
    store.setTavusSession({ status: 'idle', isAudioOnly: false });
  }

  this.navigateFn?.(route);
}
```

**Step 2: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/core/ModalityController.ts
git commit -m "feat(frontend): add switchToAudioCall method to ModalityController"
```

---

### Task 5: Frontend — AudioCallControls Component

**Files:**
- Create: `frontend/src/components/avatar/AudioCallControls.tsx`

**Step 1: Create the component**

```tsx
/**
 * AudioCallControls — Call controls bar for audio-only sessions.
 *
 * Shows: mute/unmute toggle, end call button, elapsed time.
 * Rendered at the bottom of DialogueMode in audio-only layout.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, PhoneOff } from 'lucide-react';
import { modalityController } from '@/core/ModalityController';

interface AudioCallControlsProps {
  startedAt?: string | null;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function AudioCallControls({ startedAt }: AudioCallControlsProps) {
  const [isMuted, setIsMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const start = startedAt ? new Date(startedAt).getTime() : Date.now();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    intervalRef.current = setInterval(tick, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [startedAt]);

  const handleMuteToggle = useCallback(() => {
    setIsMuted((prev) => !prev);
    // Daily.co mute/unmute would be handled by the iframe's own audio track.
    // For audio-only Tavus sessions, the Daily room handles mic state internally.
  }, []);

  const handleEndCall = useCallback(() => {
    modalityController.endSession();
  }, []);

  return (
    <div
      className="flex items-center justify-center gap-6 py-4 px-6"
      data-aria-id="audio-call-controls"
    >
      {/* Duration */}
      <span className="font-mono text-xs text-[#8B8FA3] min-w-[48px] text-center">
        {formatDuration(elapsed)}
      </span>

      {/* Mute toggle */}
      <button
        onClick={handleMuteToggle}
        className={`p-3 rounded-full transition-colors ${
          isMuted
            ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
            : 'bg-[#1A1A2E] text-[#8B8FA3] hover:bg-[#252540] hover:text-white'
        }`}
        aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
      >
        {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
      </button>

      {/* End call */}
      <button
        onClick={handleEndCall}
        className="p-3 rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors"
        aria-label="End call"
      >
        <PhoneOff size={20} />
      </button>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/avatar/AudioCallControls.tsx
git commit -m "feat(frontend): add AudioCallControls component for audio-only sessions"
```

---

### Task 6: Frontend — DialogueMode Audio-Only Layout

**Files:**
- Modify: `frontend/src/components/avatar/DialogueMode.tsx:342-379` (render block)
- Modify: `frontend/src/components/avatar/AvatarContainer.tsx`

**Step 1: Update AvatarContainer for audio-only**

In `frontend/src/components/avatar/AvatarContainer.tsx`, the component currently renders an iframe when `hasActiveSession` (line 43-49). For audio-only, we want to always show the static avatar + waveform (no iframe).

Update the component to accept an `audioOnly` prop:

```tsx
interface AvatarContainerProps {
  audioOnly?: boolean;
}

export function AvatarContainer({ audioOnly = false }: AvatarContainerProps) {
```

Change the `hasActiveSession` check (line 18) to:
```tsx
const hasActiveSession = !audioOnly && tavusSession.status === 'active' && tavusSession.roomUrl;
```

This means when `audioOnly` is true, it always renders the static avatar + waveform, which is the desired audio-only visual.

**Step 2: Update DialogueMode to branch on isAudioOnly**

In `frontend/src/components/avatar/DialogueMode.tsx`:

Add import at top:
```tsx
import { AudioCallControls } from './AudioCallControls';
```

Read `isAudioOnly` from the store (around line 34, after `tavusSession`):
```tsx
const isAudioOnly = tavusSession.isAudioOnly;
```

Replace the render block (lines 342-379) with:

```tsx
return (
  <div
    className="flex-1 flex flex-col h-full"
    style={{ backgroundColor: '#0A0A0B' }}
    data-aria-id="dialogue-mode"
  >
    <DialogueHeader />

    {isAudioOnly ? (
      /* Audio-only layout: single column */
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Compact avatar + waveform header */}
        <div className="flex flex-col items-center py-6 shrink-0">
          <AvatarContainer audioOnly />
        </div>

        {/* Full-width transcript */}
        <div className="flex-1 overflow-hidden">
          <TranscriptPanel onSend={handleSend} />
        </div>

        {/* Call controls */}
        <AudioCallControls />

        {/* Toast stack for rich content */}
        <VideoToastStack
          toasts={toasts}
          onDismiss={handleToastDismiss}
          onToastClick={handleToastClick}
        />
      </div>
    ) : (
      /* Video layout: split screen */
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Avatar */}
        <div className="flex-1 flex flex-col items-center justify-center relative">
          <AvatarContainer />
          <VideoToastStack
            toasts={toasts}
            onDismiss={handleToastDismiss}
            onToastClick={handleToastClick}
          />
          {isBriefing && (
            <div className="absolute bottom-8 z-10">
              <BriefingControls
                progress={briefingProgress}
                isPlaying={isBriefingPlaying}
                onPlayPause={handlePlayPause}
                onRewind={handleRewind}
                onForward={handleForward}
              />
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px bg-[#1A1A2E]" />

        {/* Right: Transcript */}
        <TranscriptPanel onSend={handleSend} />
      </div>
    )}
  </div>
);
```

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors

**Step 4: Commit**

```bash
git add frontend/src/components/avatar/DialogueMode.tsx frontend/src/components/avatar/AvatarContainer.tsx
git commit -m "feat(frontend): add audio-only layout to DialogueMode"
```

---

### Task 7: Frontend — InputBar Phone Button

**Files:**
- Modify: `frontend/src/components/conversation/InputBar.tsx:1-107`

**Step 1: Add phone icon to InputBar**

In `frontend/src/components/conversation/InputBar.tsx`:

Update Lucide import (line 3):
```tsx
import { Send, Phone } from 'lucide-react';
```

Add ModalityController import:
```tsx
import { modalityController } from '@/core/ModalityController';
```

Add a callback for the phone button (after `handleKeyDown`, around line 49):
```tsx
const handleAudioCall = useCallback(() => {
  modalityController.switchToAudioCall('chat');
}, []);
```

Add the phone button in the form, between the VoiceIndicator and the textarea (after line 80, before line 82):

```tsx
<button
  type="button"
  onClick={handleAudioCall}
  className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] transition-colors hover:text-[#2E66FF] hover:bg-[rgba(46,102,255,0.1)]"
  aria-label="Call ARIA (audio only)"
  data-aria-id="audio-call-button"
  title="Call ARIA"
>
  <Phone size={16} />
</button>
```

**Step 2: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/InputBar.tsx
git commit -m "feat(frontend): add audio call button to InputBar"
```

---

### Task 8: Verify End-to-End

**Step 1: Run all backend video tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/api/routes/test_video.py -v`
Expected: All tests PASS (including the new audio_only test)

**Step 2: Run frontend typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors from our changes

**Step 3: Run frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npx eslint src/components/avatar/AudioCallControls.tsx src/components/avatar/DialogueMode.tsx src/components/avatar/AvatarContainer.tsx src/components/conversation/InputBar.tsx src/core/ModalityController.ts src/stores/modalityStore.ts src/api/video.ts`
Expected: No errors

**Step 4: Final commit (if any lint fixes needed)**

```bash
git add -A
git commit -m "fix: lint cleanup for audio-only mode"
```
