# Dialogue Mode & Conversation UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the split-screen Dialogue Mode with Tavus avatar integration and a suite of conversation UX enhancements (typing indicator, message avatars, timestamps, animations, unread indicators, background work indicator, collapsible cards).

**Architecture:** Three layers — (1) backend video session endpoints wired to existing TavusClient, (2) Zustand modalityStore + ModalityController service for modality state, (3) React components split between `components/avatar/` (Dialogue Mode) and `components/conversation/` (shared UX enhancements). All components share the existing `conversationStore` for message data.

**Tech Stack:** React 18, TypeScript strict, Zustand, Tailwind CSS, Framer Motion (already installed), FastAPI, Pydantic, Supabase (PostgreSQL + RLS)

---

## Task 1: Backend — Video Sessions Migration

**Files:**
- Create: `backend/supabase/migrations/20260211_video_sessions.sql`

**Step 1: Write the migration**

```sql
-- Video sessions for Tavus avatar integration
CREATE TABLE IF NOT EXISTS video_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tavus_conversation_id text,
  room_url text,
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'active', 'ended', 'error')),
  session_type text NOT NULL DEFAULT 'chat' CHECK (session_type IN ('chat', 'briefing', 'debrief')),
  started_at timestamptz,
  ended_at timestamptz,
  duration_seconds integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_sessions_user_id ON video_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_video_sessions_status ON video_sessions(status);

ALTER TABLE video_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own video sessions"
  ON video_sessions FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can create own video sessions"
  ON video_sessions FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own video sessions"
  ON video_sessions FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

-- Video transcripts
CREATE TABLE IF NOT EXISTS video_transcripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  video_session_id uuid NOT NULL REFERENCES video_sessions(id) ON DELETE CASCADE,
  speaker text NOT NULL CHECK (speaker IN ('aria', 'user')),
  content text NOT NULL,
  timestamp_ms integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_transcripts_session ON video_transcripts(video_session_id);

ALTER TABLE video_transcripts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own transcripts"
  ON video_transcripts FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM video_sessions
      WHERE video_sessions.id = video_transcripts.video_session_id
      AND video_sessions.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can create own transcripts"
  ON video_transcripts FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM video_sessions
      WHERE video_sessions.id = video_transcripts.video_session_id
      AND video_sessions.user_id = auth.uid()
    )
  );
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260211_video_sessions.sql
git commit -m "feat: add video_sessions and video_transcripts migration"
```

---

## Task 2: Backend — Video Session API Routes

**Files:**
- Create: `backend/src/api/routes/video.py`
- Modify: `backend/src/main.py` (add import + router registration)

**Step 1: Create the video routes**

Create `backend/src/api/routes/video.py` with three endpoints using existing `TavusClient` and `VideoSession` models:

```python
"""Video session API routes for Tavus avatar integration."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client
from src.integrations.tavus import get_tavus_client
from src.models.video import (
    SessionType,
    VideoSessionCreate,
    VideoSessionResponse,
    VideoSessionStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/sessions", response_model=VideoSessionResponse)
async def create_video_session(
    body: VideoSessionCreate,
    user: CurrentUser,
) -> VideoSessionResponse:
    """Create a new video session with Tavus."""
    user_id = user.id
    supabase = get_supabase_client()
    tavus = get_tavus_client()

    try:
        tavus_response = await tavus.create_conversation(
            user_id=user_id,
            conversation_name=f"ARIA {body.session_type.value} - {user_id}",
            context=body.context,
            custom_greeting=body.custom_greeting,
        )
    except Exception as e:
        logger.exception("Failed to create Tavus conversation")
        raise HTTPException(status_code=502, detail="Failed to create video session") from e

    tavus_conversation_id = str(tavus_response.get("conversation_id", ""))
    room_url = str(tavus_response.get("conversation_url", "")) or None

    result = (
        supabase.table("video_sessions")
        .insert(
            {
                "user_id": user_id,
                "tavus_conversation_id": tavus_conversation_id,
                "room_url": room_url,
                "status": VideoSessionStatus.ACTIVE.value,
                "session_type": body.session_type.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
    )

    row = result.data[0]
    return VideoSessionResponse(
        id=row["id"],
        user_id=row["user_id"],
        tavus_conversation_id=row["tavus_conversation_id"],
        room_url=row["room_url"],
        status=VideoSessionStatus(row["status"]),
        session_type=SessionType(row["session_type"]),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        duration_seconds=row.get("duration_seconds"),
        created_at=row["created_at"],
    )


@router.get("/sessions/{session_id}", response_model=VideoSessionResponse)
async def get_video_session(
    session_id: str,
    user: CurrentUser,
) -> VideoSessionResponse:
    """Get video session details."""
    supabase = get_supabase_client()

    result = (
        supabase.table("video_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user.id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Video session not found")

    row = result.data[0]
    return VideoSessionResponse(
        id=row["id"],
        user_id=row["user_id"],
        tavus_conversation_id=row["tavus_conversation_id"],
        room_url=row["room_url"],
        status=VideoSessionStatus(row["status"]),
        session_type=SessionType(row["session_type"]),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        duration_seconds=row.get("duration_seconds"),
        created_at=row["created_at"],
    )


@router.post("/sessions/{session_id}/end", response_model=VideoSessionResponse)
async def end_video_session(
    session_id: str,
    user: CurrentUser,
) -> VideoSessionResponse:
    """End an active video session."""
    supabase = get_supabase_client()
    tavus = get_tavus_client()

    result = (
        supabase.table("video_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user.id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Video session not found")

    row = result.data[0]
    if row["status"] == VideoSessionStatus.ENDED.value:
        raise HTTPException(status_code=400, detail="Session already ended")

    # End the Tavus conversation
    tavus_id = row.get("tavus_conversation_id")
    if tavus_id:
        try:
            await tavus.end_conversation(tavus_id)
        except Exception:
            logger.warning("Failed to end Tavus conversation %s", tavus_id)

    now = datetime.now(timezone.utc)
    started = row.get("started_at")
    duration = None
    if started:
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        duration = int((now - started_dt).total_seconds())

    updated = (
        supabase.table("video_sessions")
        .update(
            {
                "status": VideoSessionStatus.ENDED.value,
                "ended_at": now.isoformat(),
                "duration_seconds": duration,
            }
        )
        .eq("id", session_id)
        .execute()
    )

    updated_row = updated.data[0]
    return VideoSessionResponse(
        id=updated_row["id"],
        user_id=updated_row["user_id"],
        tavus_conversation_id=updated_row["tavus_conversation_id"],
        room_url=updated_row["room_url"],
        status=VideoSessionStatus(updated_row["status"]),
        session_type=SessionType(updated_row["session_type"]),
        started_at=updated_row.get("started_at"),
        ended_at=updated_row.get("ended_at"),
        duration_seconds=updated_row.get("duration_seconds"),
        created_at=updated_row["created_at"],
    )
```

**Step 2: Register the router in main.py**

In `backend/src/main.py`:
- Add `video` to the import block (line ~13, add to the `from src.api.routes import` block)
- Add `app.include_router(video.router, prefix="/api/v1")` after the existing router registrations (~line 189)

**Step 3: Commit**

```bash
git add backend/src/api/routes/video.py backend/src/main.py
git commit -m "feat: add video session API endpoints for Tavus integration"
```

---

## Task 3: Frontend — Modality Store

**Files:**
- Create: `frontend/src/stores/modalityStore.ts`

**Step 1: Create the store**

```typescript
/**
 * Modality Store — Manages avatar/voice/text modality state.
 *
 * Tracks active Tavus sessions, speaking state, and PiP visibility.
 * Driven by ModalityController service and WebSocket events.
 */

import { create } from 'zustand';

export type Modality = 'text' | 'voice' | 'avatar';
export type TavusSessionStatus = 'idle' | 'connecting' | 'active' | 'ending';
export type SessionType = 'chat' | 'briefing' | 'debrief';

export interface TavusSession {
  id: string | null;
  roomUrl: string | null;
  status: TavusSessionStatus;
  sessionType: SessionType;
}

export interface ModalityState {
  activeModality: Modality;
  tavusSession: TavusSession;
  isSpeaking: boolean;
  isPipVisible: boolean;
  captionsEnabled: boolean;
  playbackSpeed: number;

  setActiveModality: (modality: Modality) => void;
  setTavusSession: (session: Partial<TavusSession>) => void;
  clearTavusSession: () => void;
  setIsSpeaking: (speaking: boolean) => void;
  setIsPipVisible: (visible: boolean) => void;
  setCaptionsEnabled: (enabled: boolean) => void;
  setPlaybackSpeed: (speed: number) => void;
}

const INITIAL_TAVUS_SESSION: TavusSession = {
  id: null,
  roomUrl: null,
  status: 'idle',
  sessionType: 'chat',
};

export const useModalityStore = create<ModalityState>((set) => ({
  activeModality: 'text',
  tavusSession: { ...INITIAL_TAVUS_SESSION },
  isSpeaking: false,
  isPipVisible: false,
  captionsEnabled: true,
  playbackSpeed: 1.0,

  setActiveModality: (modality) => set({ activeModality: modality }),

  setTavusSession: (updates) =>
    set((state) => ({
      tavusSession: { ...state.tavusSession, ...updates },
    })),

  clearTavusSession: () =>
    set({ tavusSession: { ...INITIAL_TAVUS_SESSION }, isPipVisible: false }),

  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),

  setIsPipVisible: (visible) => set({ isPipVisible: visible }),

  setCaptionsEnabled: (enabled) => set({ captionsEnabled: enabled }),

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
}));
```

**Step 2: Commit**

```bash
git add frontend/src/stores/modalityStore.ts
git commit -m "feat: add modalityStore for avatar/voice/text state management"
```

---

## Task 4: Frontend — ModalityController Service

**Files:**
- Create: `frontend/src/core/ModalityController.ts`

**Step 1: Create the controller**

```typescript
/**
 * ModalityController — Orchestrates modality switches between text, voice, and avatar.
 *
 * Manages Tavus session lifecycle: create, end, PiP visibility.
 * Singleton pattern matching UICommandExecutor and WebSocketManager.
 */

import { apiClient } from '@/api/client';
import { useModalityStore, type SessionType } from '@/stores/modalityStore';

type NavigateFunction = (to: string) => void;

interface VideoSessionResponse {
  id: string;
  room_url: string | null;
  tavus_conversation_id: string;
  status: string;
  session_type: string;
}

class ModalityControllerImpl {
  private navigateFn: NavigateFunction | null = null;

  setNavigate(fn: NavigateFunction): void {
    this.navigateFn = fn;
  }

  async switchTo(modality: 'text' | 'avatar', sessionType?: SessionType): Promise<void> {
    const store = useModalityStore.getState();

    if (modality === 'text') {
      store.setActiveModality('text');
      // Show PiP if Tavus session is active
      if (store.tavusSession.status === 'active') {
        store.setIsPipVisible(true);
      }
      this.navigateFn?.('/');
      return;
    }

    if (modality === 'avatar') {
      const type = sessionType || 'chat';
      store.setActiveModality('avatar');
      store.setIsPipVisible(false);

      // If no active Tavus session, create one
      if (store.tavusSession.status !== 'active') {
        store.setTavusSession({ status: 'connecting', sessionType: type });

        try {
          const response = await apiClient.post<VideoSessionResponse>('/video/sessions', {
            session_type: type,
          });
          const data = response.data;
          store.setTavusSession({
            id: data.id,
            roomUrl: data.room_url,
            status: 'active',
            sessionType: type,
          });
        } catch {
          store.setTavusSession({ status: 'idle' });
          // Fallback: still navigate to dialogue mode with static avatar
        }
      }

      const route = type === 'briefing' ? '/briefing' : '/dialogue';
      this.navigateFn?.(route);
    }
  }

  async endSession(): Promise<void> {
    const store = useModalityStore.getState();
    const sessionId = store.tavusSession.id;

    if (sessionId) {
      store.setTavusSession({ status: 'ending' });
      try {
        await apiClient.post(`/video/sessions/${sessionId}/end`);
      } catch {
        // Session may already be ended on Tavus side
      }
    }

    store.clearTavusSession();
    store.setActiveModality('text');
    this.navigateFn?.('/');
  }

  dismissPip(): void {
    useModalityStore.getState().setIsPipVisible(false);
  }

  restorePip(): void {
    const store = useModalityStore.getState();
    if (store.tavusSession.status === 'active' && store.activeModality !== 'avatar') {
      store.setIsPipVisible(true);
    }
  }
}

export const modalityController = new ModalityControllerImpl();
```

**Step 2: Commit**

```bash
git add frontend/src/core/ModalityController.ts
git commit -m "feat: add ModalityController for Tavus session lifecycle"
```

---

## Task 5: Frontend — MessageAvatar Component

**Files:**
- Create: `frontend/src/components/conversation/MessageAvatar.tsx`

**Step 1: Create the component**

```typescript
/**
 * MessageAvatar — 32px circular avatar for message groups.
 *
 * ARIA: static avatar image (aria-avatar-transparent.png)
 * User: profile photo from auth, or initials fallback
 */

import ariaAvatarSrc from '@/assets/aria-avatar-transparent.png';
import { useAuth } from '@/hooks/useAuth';

interface MessageAvatarProps {
  role: 'aria' | 'user' | 'system';
  visible: boolean;
}

export function MessageAvatar({ role, visible }: MessageAvatarProps) {
  const { user } = useAuth();

  if (!visible) {
    // Spacer to keep alignment when avatar is hidden in a consecutive group
    return <div className="w-8 h-8 shrink-0" />;
  }

  if (role === 'aria') {
    return (
      <img
        src={ariaAvatarSrc}
        alt="ARIA"
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
    );
  }

  // User avatar
  if (user?.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.full_name || 'User'}
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
    );
  }

  // Initials fallback
  const initials = (user?.full_name || 'U')
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-[#1C1C1E] text-[#A1A1AA] text-xs font-medium">
      {initials}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/conversation/MessageAvatar.tsx
git commit -m "feat: add MessageAvatar component for conversation bubbles"
```

---

## Task 6: Frontend — TypingIndicator, TimeDivider, Message Animations

**Files:**
- Create: `frontend/src/components/conversation/TypingIndicator.tsx`
- Create: `frontend/src/components/conversation/TimeDivider.tsx`

**Step 1: Create TypingIndicator**

```typescript
/**
 * TypingIndicator — Three-dot bounce animation with ARIA avatar.
 * Shown when ARIA is thinking or streaming is about to start.
 */

import ariaAvatarSrc from '@/assets/aria-avatar-transparent.png';

export function TypingIndicator() {
  return (
    <div className="flex items-start gap-3" data-aria-id="typing-indicator">
      <img
        src={ariaAvatarSrc}
        alt="ARIA"
        className="w-8 h-8 rounded-full object-cover shrink-0"
      />
      <div className="border-l-2 border-accent pl-4 py-3">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-accent animate-[typing-bounce_1.4s_infinite_0s]" />
          <span className="w-2 h-2 rounded-full bg-accent animate-[typing-bounce_1.4s_infinite_0.16s]" />
          <span className="w-2 h-2 rounded-full bg-accent animate-[typing-bounce_1.4s_infinite_0.32s]" />
        </div>
      </div>
    </div>
  );
}
```

Also add to `frontend/tailwind.config.js` (or `tailwind.config.ts`) in the `extend.keyframes` section:

```js
'typing-bounce': {
  '0%, 60%, 100%': { transform: 'translateY(0)', opacity: '0.4' },
  '30%': { transform: 'translateY(-6px)', opacity: '1' },
},
```

And in `extend.animation`:

```js
'typing-bounce': 'typing-bounce 1.4s infinite',
```

**Step 2: Create TimeDivider**

```typescript
/**
 * TimeDivider — Centered timestamp between messages with 30+ minute gaps.
 * Format: "Today, 9:14 AM" or "Feb 10, 3:30 PM"
 */

interface TimeDividerProps {
  timestamp: string;
}

function formatDividerTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  if (isToday) return `Today, ${time}`;

  const month = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  return `${month}, ${time}`;
}

export function TimeDivider({ timestamp }: TimeDividerProps) {
  return (
    <div className="flex items-center gap-3 py-3">
      <div className="flex-1 h-px bg-[#1A1A2E]" />
      <span className="font-sans text-xs text-[#555770] select-none">
        {formatDividerTime(timestamp)}
      </span>
      <div className="flex-1 h-px bg-[#1A1A2E]" />
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/TypingIndicator.tsx frontend/src/components/conversation/TimeDivider.tsx
git commit -m "feat: add TypingIndicator and TimeDivider conversation components"
```

---

## Task 7: Frontend — Update ConversationThread & MessageBubble

**Files:**
- Modify: `frontend/src/components/conversation/ConversationThread.tsx`
- Modify: `frontend/src/components/conversation/MessageBubble.tsx`
- Modify: `frontend/src/components/conversation/index.ts`

**Step 1: Update MessageBubble**

Add `MessageAvatar`, hover timestamps, message entrance animations, and message grouping support.

Key changes to `MessageBubble.tsx`:
- Add `isFirstInGroup` prop to control avatar visibility
- Add `MessageAvatar` to each message layout
- Replace always-visible timestamp with hover tooltip
- Add entrance animation classes using CSS (not Framer Motion — keep it lightweight)
- Add `prefers-reduced-motion` media query support

The ARIA message layout changes from:
```
[border-l message]
```
to:
```
[avatar 32px] [border-l message with hover timestamp]
```

The user message layout changes from:
```
[right-aligned pill]
```
to:
```
[right-aligned pill] [avatar 32px]
```

Hover timestamp: wrap the message container with a `group` class, render a hidden tooltip that becomes visible on `group-hover`. Font: JetBrains Mono 11px, color `#555770`.

Animation: add Tailwind classes `animate-in slide-in-from-left-2` for ARIA, `animate-in slide-in-from-right-2` for user. Add `motion-safe:` prefix so it respects `prefers-reduced-motion`.

**Step 2: Update ConversationThread**

Key changes to `ConversationThread.tsx`:
- Import `TimeDivider` and `TypingIndicator`
- Compute `isFirstInGroup` for each message (different role from previous, or previous was 30+ min ago)
- Compute whether a `TimeDivider` should appear between messages (30+ min gap)
- Replace the existing streaming dots indicator with `<TypingIndicator />`
- Pass `isFirstInGroup` to each `MessageBubble`

**Step 3: Update index.ts exports**

Add exports for new components:
```typescript
export { MessageAvatar } from './MessageAvatar';
export { TypingIndicator } from './TypingIndicator';
export { TimeDivider } from './TimeDivider';
```

**Step 4: Commit**

```bash
git add frontend/src/components/conversation/
git commit -m "feat: add message avatars, hover timestamps, typing indicator, time dividers"
```

---

## Task 8: Frontend — UnreadIndicator + BackgroundWorkIndicator + CollapsibleCard

**Files:**
- Create: `frontend/src/components/conversation/UnreadIndicator.tsx`
- Create: `frontend/src/components/conversation/BackgroundWorkIndicator.tsx`
- Create: `frontend/src/components/conversation/CollapsibleCard.tsx`

**Step 1: Create UnreadIndicator**

```typescript
/**
 * UnreadIndicator — Pill at top of conversation when ARIA sent messages while user was away.
 *
 * Tracks: route changes (user on content page) and tab visibility (document.hidden).
 * Uses IntersectionObserver to dismiss when user scrolls past unread.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useNotificationsStore } from '@/stores/notificationsStore';

export function UnreadIndicator() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [firstUnreadId, setFirstUnreadId] = useState<string | null>(null);
  const location = useLocation();
  const isAwayRef = useRef(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Track whether user is "away" (different route or tab hidden)
  useEffect(() => {
    const isAriaRoute = location.pathname === '/' || location.pathname === '/dialogue' || location.pathname === '/briefing';
    isAwayRef.current = !isAriaRoute;
  }, [location.pathname]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        isAwayRef.current = true;
      } else {
        const isAriaRoute = location.pathname === '/' || location.pathname === '/dialogue' || location.pathname === '/briefing';
        isAwayRef.current = !isAriaRoute;
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [location.pathname]);

  // Listen for new ARIA messages while away
  useEffect(() => {
    const handleAriaMessage = () => {
      if (isAwayRef.current) {
        setUnreadCount((prev) => {
          if (prev === 0) {
            // Capture the ID of the first unread
            const messages = useConversationStore.getState().messages;
            const lastMsg = messages[messages.length - 1];
            if (lastMsg) setFirstUnreadId(lastMsg.id);
          }
          const newCount = prev + 1;
          // Update sidebar badge
          useNotificationsStore.getState().addNotification({
            type: 'info',
            title: `${newCount} new message${newCount > 1 ? 's' : ''} from ARIA`,
          });
          return newCount;
        });
      }
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    return () => wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
  }, []);

  const scrollToUnread = useCallback(() => {
    if (!firstUnreadId) return;
    const el = document.querySelector(`[data-message-id="${firstUnreadId}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [firstUnreadId]);

  // Dismiss when user scrolls past unread messages
  useEffect(() => {
    if (!firstUnreadId || unreadCount === 0) return;

    const el = document.querySelector(`[data-message-id="${firstUnreadId}"]`);
    if (!el) return;

    observerRef.current = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setUnreadCount(0);
          setFirstUnreadId(null);
          observerRef.current?.disconnect();
        }
      },
      { threshold: 0.5 },
    );

    observerRef.current.observe(el);
    return () => observerRef.current?.disconnect();
  }, [firstUnreadId, unreadCount]);

  if (unreadCount === 0) return null;

  return (
    <div className="sticky top-0 z-10 flex justify-center py-2">
      <button
        onClick={scrollToUnread}
        className="px-4 py-1.5 rounded-full bg-accent text-white text-xs font-medium shadow-lg hover:bg-[var(--accent-hover)] transition-colors"
      >
        {unreadCount} new message{unreadCount > 1 ? 's' : ''} from ARIA ↓
      </button>
    </div>
  );
}
```

**Step 2: Create BackgroundWorkIndicator**

```typescript
/**
 * BackgroundWorkIndicator — Shows active agent tasks above InputBar.
 *
 * Driven by agent.started / agent.completed WebSocket events.
 * Max 2 lines, then "+N more tasks" link to /actions.
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { wsManager } from '@/core/WebSocketManager';

interface AgentTask {
  id: string;
  description: string;
}

export function BackgroundWorkIndicator() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const handleStarted = (payload: unknown) => {
      const data = payload as { task_id: string; description: string };
      setTasks((prev) => [...prev, { id: data.task_id, description: data.description }]);
    };

    const handleCompleted = (payload: unknown) => {
      const data = payload as { task_id: string };
      setTasks((prev) => prev.filter((t) => t.id !== data.task_id));
    };

    wsManager.on('agent.started', handleStarted);
    wsManager.on('agent.completed', handleCompleted);
    return () => {
      wsManager.off('agent.started', handleStarted);
      wsManager.off('agent.completed', handleCompleted);
    };
  }, []);

  if (tasks.length === 0) return null;

  const visible = tasks.slice(0, 2);
  const remaining = tasks.length - visible.length;

  return (
    <div
      className="px-6 py-2 bg-[#111318] border-t border-[#1A1A2E] cursor-pointer"
      onClick={() => navigate('/actions')}
      data-aria-id="background-work-indicator"
    >
      {visible.map((task) => (
        <div key={task.id} className="flex items-center gap-2 py-0.5">
          <span className="text-accent text-sm">✦</span>
          <span className="text-xs text-[#8B8FA3] truncate animate-shimmer">
            ARIA is {task.description}...
          </span>
        </div>
      ))}
      {remaining > 0 && (
        <span className="text-xs text-[#555770] pl-5">
          +{remaining} more task{remaining > 1 ? 's' : ''}
        </span>
      )}
    </div>
  );
}
```

Also add a `shimmer` keyframe to tailwind config:
```js
'shimmer': {
  '0%': { backgroundPosition: '-200% 0' },
  '100%': { backgroundPosition: '200% 0' },
},
```

**Step 3: Create CollapsibleCard**

```typescript
/**
 * CollapsibleCard — Wraps rich content cards taller than ~200px in conversation.
 *
 * Collapsed by default: title + 2-line summary + "Show more".
 * Approval rows are always visible outside the collapse.
 */

import { useState, useRef, useEffect, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface CollapsibleCardProps {
  children: ReactNode;
  collapsible?: boolean;
  approvalSlot?: ReactNode;
}

const COLLAPSE_THRESHOLD = 200;

export function CollapsibleCard({ children, collapsible = true, approvalSlot }: CollapsibleCardProps) {
  const [isExpanded, setIsExpanded] = useState(!collapsible);
  const [needsCollapse, setNeedsCollapse] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!collapsible) return;
    const el = contentRef.current;
    if (el && el.scrollHeight > COLLAPSE_THRESHOLD) {
      setNeedsCollapse(true);
    }
  }, [collapsible, children]);

  if (!collapsible || !needsCollapse) {
    return (
      <div>
        {children}
        {approvalSlot}
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <div
          ref={contentRef}
          className={isExpanded ? '' : 'max-h-[200px] overflow-hidden'}
        >
          {children}
        </div>
        {!isExpanded && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-[var(--bg-elevated)] to-transparent pointer-events-none" />
        )}
      </div>
      <button
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex items-center gap-1 mt-1 text-xs text-accent hover:text-[var(--accent-hover)] transition-colors"
      >
        {isExpanded ? (
          <>
            <ChevronUp size={14} />
            Show less
          </>
        ) : (
          <>
            <ChevronDown size={14} />
            Show more
          </>
        )}
      </button>
      {approvalSlot}
    </div>
  );
}
```

**Step 4: Update ConversationThread** to include `UnreadIndicator` and `BackgroundWorkIndicator` in the ARIAWorkspace layout.

In `ARIAWorkspace.tsx`, add `BackgroundWorkIndicator` between `SuggestionChips` and `InputBar`. Add `UnreadIndicator` as the first child inside `ConversationThread`.

**Step 5: Commit**

```bash
git add frontend/src/components/conversation/UnreadIndicator.tsx frontend/src/components/conversation/BackgroundWorkIndicator.tsx frontend/src/components/conversation/CollapsibleCard.tsx frontend/src/components/pages/ARIAWorkspace.tsx frontend/src/components/conversation/index.ts
git commit -m "feat: add UnreadIndicator, BackgroundWorkIndicator, CollapsibleCard"
```

---

## Task 9: Frontend — WaveformBars Component

**Files:**
- Create: `frontend/src/components/avatar/WaveformBars.tsx`

**Step 1: Create the component**

```typescript
/**
 * WaveformBars — Animated vertical bars that respond to ARIA's speech.
 *
 * Variants:
 * - 'default': 12 bars, used in AvatarContainer
 * - 'mini': 6 bars, used in CompactAvatar PiP
 */

import { useModalityStore } from '@/stores/modalityStore';

interface WaveformBarsProps {
  variant?: 'default' | 'mini';
}

export function WaveformBars({ variant = 'default' }: WaveformBarsProps) {
  const isSpeaking = useModalityStore((s) => s.isSpeaking);

  const barCount = variant === 'mini' ? 6 : 12;
  const barHeight = variant === 'mini' ? 20 : 40;
  const barWidth = variant === 'mini' ? 2 : 3;
  const gap = variant === 'mini' ? 4 : 8;

  return (
    <div
      className="flex items-end justify-center"
      style={{ gap: `${gap}px`, height: `${barHeight}px` }}
    >
      {Array.from({ length: barCount }).map((_, i) => (
        <div
          key={i}
          className="rounded-full transition-opacity duration-300"
          style={{
            width: `${barWidth}px`,
            height: '100%',
            backgroundColor: '#2E66FF',
            opacity: isSpeaking ? 1 : 0.3,
            animation: isSpeaking
              ? `waveform 1.2s ease-in-out ${i * 0.1}s infinite`
              : 'none',
            transform: isSpeaking ? undefined : 'scaleY(0.3)',
          }}
        />
      ))}
    </div>
  );
}
```

Add `waveform` keyframe to tailwind config:
```js
'waveform': {
  '0%, 100%': { transform: 'scaleY(0.3)' },
  '50%': { transform: 'scaleY(1)' },
},
```

**Step 2: Commit**

```bash
git add frontend/src/components/avatar/WaveformBars.tsx
git commit -m "feat: add WaveformBars component with speaking animation"
```

---

## Task 10: Frontend — AvatarContainer Component

**Files:**
- Create: `frontend/src/components/avatar/AvatarContainer.tsx`

**Step 1: Create the component**

```typescript
/**
 * AvatarContainer — Left half of Dialogue Mode.
 *
 * Shows either:
 * - Tavus Daily.co iframe (when session active, room URL available)
 * - Static avatar fallback (aria-avatar.png) with animated border
 *
 * Background: dark radial gradient with subtle blue glow.
 * Renders WaveformBars below the avatar frame.
 */

import { useModalityStore } from '@/stores/modalityStore';
import { WaveformBars } from './WaveformBars';
import ariaAvatarSrc from '@/assets/aria-avatar.png';

export function AvatarContainer() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const hasActiveSession = tavusSession.status === 'active' && tavusSession.roomUrl;

  return (
    <div
      className="flex-1 flex flex-col items-center justify-center relative overflow-hidden"
      style={{
        background: 'radial-gradient(circle at center, #0D1117 0%, #0A0A0B 100%)',
      }}
    >
      {/* Subtle blue glow behind avatar */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, rgba(46,102,255,0.08) 0%, transparent 60%)',
        }}
      />

      {/* Avatar frame */}
      <div className="relative z-10 flex flex-col items-center gap-6">
        <div
          className="w-[280px] h-[280px] rounded-full overflow-hidden border-2 border-[#2E66FF]"
          style={{
            boxShadow: '0 0 40px rgba(46,102,255,0.15), 0 0 80px rgba(46,102,255,0.05)',
          }}
        >
          {hasActiveSession ? (
            <iframe
              src={tavusSession.roomUrl!}
              className="w-full h-full border-0"
              allow="camera; microphone; autoplay; display-capture"
              title="ARIA Avatar"
            />
          ) : (
            <img
              src={ariaAvatarSrc}
              alt="ARIA"
              className="w-full h-full object-cover motion-safe:animate-in motion-safe:zoom-in-95 motion-safe:duration-500"
            />
          )}
        </div>

        {/* Waveform bars */}
        <WaveformBars />

        {/* Connection status */}
        {tavusSession.status === 'connecting' && (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="font-mono text-[11px] text-[#8B8FA3]">CONNECTING...</span>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/avatar/AvatarContainer.tsx
git commit -m "feat: add AvatarContainer with Tavus iframe and static fallback"
```

---

## Task 11: Frontend — TranscriptEntry + TranscriptPanel

**Files:**
- Create: `frontend/src/components/avatar/TranscriptEntry.tsx`
- Create: `frontend/src/components/avatar/TranscriptPanel.tsx`

**Step 1: Create TranscriptEntry**

```typescript
/**
 * TranscriptEntry — Single message in the Dialogue Mode transcript.
 *
 * Always left-aligned. Speaker label + timestamp always visible.
 * ARIA messages: "ARIA" in electric blue, content in lighter weight.
 * User messages: "YOU" in muted gray, content in regular weight.
 * Active (latest) message at full opacity, older messages dimmed.
 */

import ReactMarkdown from 'react-markdown';
import { MessageAvatar } from '@/components/conversation/MessageAvatar';
import type { Message } from '@/types/chat';

interface TranscriptEntryProps {
  message: Message;
  isActive: boolean;
  isFirstInGroup: boolean;
}

function formatTranscriptTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function TranscriptEntry({ message, isActive, isFirstInGroup }: TranscriptEntryProps) {
  const isAria = message.role === 'aria';

  return (
    <div
      className={`flex items-start gap-3 transition-opacity duration-300 ${isActive ? 'opacity-100' : 'opacity-50'}`}
      data-message-id={message.id}
    >
      <MessageAvatar role={message.role} visible={isFirstInGroup} />

      <div className="flex-1 min-w-0">
        {isFirstInGroup && (
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`font-mono text-[11px] tracking-wider ${isAria ? 'text-[#2E66FF]' : 'text-[#8B8FA3]'}`}
            >
              {isAria ? 'ARIA' : 'YOU'}
            </span>
            <span className="font-mono text-[11px] text-[#555770]">
              {formatTranscriptTime(message.timestamp)}
            </span>
          </div>
        )}

        {isAria ? (
          <div className="prose-aria text-sm leading-relaxed text-[#E2E4E9] font-light">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-[#F8FAFC]">{message.content}</p>
        )}

        {/* Rich content cards */}
        {message.rich_content.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.rich_content.map((rc, i) => (
              <div
                key={i}
                className="rounded-lg bg-[#1A1A2E] border-l-2 border-[#2E66FF] px-3 py-2 text-xs text-[#E2E4E9]"
              >
                <span className="font-mono uppercase tracking-wider text-[#2E66FF] text-[10px]">
                  {rc.type}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Create TranscriptPanel**

```typescript
/**
 * TranscriptPanel — Right half of Dialogue Mode.
 *
 * Renders conversation messages as a call transcript aesthetic.
 * Reads from conversationStore (same data as ConversationThread).
 * Timestamps always visible. Active message full opacity, rest dimmed.
 */

import { useEffect, useRef } from 'react';
import { Share2, Download } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';
import { TranscriptEntry } from './TranscriptEntry';
import { InputBar } from '@/components/conversation/InputBar';
import { SuggestionChips } from '@/components/conversation/SuggestionChips';
import { TimeDivider } from '@/components/conversation/TimeDivider';

interface TranscriptPanelProps {
  onSend: (message: string) => void;
}

function shouldShowTimeDivider(current: string, previous: string): boolean {
  const gap = new Date(current).getTime() - new Date(previous).getTime();
  return gap > 30 * 60 * 1000; // 30 minutes
}

export function TranscriptPanel({ onSend }: TranscriptPanelProps) {
  const messages = useConversationStore((s) => s.messages);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0F1117' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1A1A2E]">
        <h2
          className="text-lg text-[#F8FAFC] italic"
          style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
        >
          Transcript & Analysis
        </h2>
        <div className="flex items-center gap-2">
          <button
            className="p-2 rounded-lg text-[#8B8FA3] hover:text-[#F8FAFC] hover:bg-[#1A1A2E] transition-colors"
            aria-label="Share transcript"
          >
            <Share2 size={16} />
          </button>
          <button
            className="p-2 rounded-lg text-[#8B8FA3] hover:text-[#F8FAFC] hover:bg-[#1A1A2E] transition-colors"
            aria-label="Download transcript"
          >
            <Download size={16} />
          </button>
        </div>
      </div>

      {/* Transcript messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((message, index) => {
          const prevMessage = messages[index - 1];
          const isFirstInGroup = !prevMessage || prevMessage.role !== message.role;
          const showDivider = prevMessage && shouldShowTimeDivider(message.timestamp, prevMessage.timestamp);
          const isActive = index === messages.length - 1;

          return (
            <div key={message.id}>
              {showDivider && <TimeDivider timestamp={message.timestamp} />}
              <TranscriptEntry
                message={message}
                isActive={isActive}
                isFirstInGroup={isFirstInGroup}
              />
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <SuggestionChips onSelect={onSend} />
      <InputBar onSend={onSend} placeholder="Interrupt to ask a question..." />
    </div>
  );
}
```

Note: The `InputBar` component needs a minor update to accept an optional `placeholder` prop. Modify `InputBar.tsx` to accept `placeholder?: string` in its props interface and pass it to the textarea.

**Step 3: Commit**

```bash
git add frontend/src/components/avatar/TranscriptEntry.tsx frontend/src/components/avatar/TranscriptPanel.tsx frontend/src/components/conversation/InputBar.tsx
git commit -m "feat: add TranscriptEntry and TranscriptPanel for Dialogue Mode"
```

---

## Task 12: Frontend — BriefingControls + DialogueHeader

**Files:**
- Create: `frontend/src/components/avatar/BriefingControls.tsx`
- Create: `frontend/src/components/avatar/DialogueHeader.tsx`

**Step 1: Create BriefingControls**

```typescript
/**
 * BriefingControls — Playback controls shown in AvatarContainer during briefing sessions.
 *
 * Progress bar, rewind/forward 10s, play/pause, speed control.
 * Only rendered when sessionType === 'briefing'.
 */

import { useState } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';

interface BriefingControlsProps {
  progress: number; // 0-100
  isPlaying: boolean;
  onPlayPause: () => void;
  onRewind: () => void;
  onForward: () => void;
}

const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5];

export function BriefingControls({
  progress,
  isPlaying,
  onPlayPause,
  onRewind,
  onForward,
}: BriefingControlsProps) {
  const playbackSpeed = useModalityStore((s) => s.playbackSpeed);
  const setPlaybackSpeed = useModalityStore((s) => s.setPlaybackSpeed);
  const captionsEnabled = useModalityStore((s) => s.captionsEnabled);
  const setCaptionsEnabled = useModalityStore((s) => s.setCaptionsEnabled);

  const [speedIndex, setSpeedIndex] = useState(SPEED_OPTIONS.indexOf(playbackSpeed));

  const cycleSpeed = () => {
    const next = (speedIndex + 1) % SPEED_OPTIONS.length;
    setSpeedIndex(next);
    setPlaybackSpeed(SPEED_OPTIONS[next]);
  };

  return (
    <div className="w-full max-w-xs flex flex-col items-center gap-3">
      {/* Progress bar */}
      <div className="w-full h-1 rounded-full bg-[#1A1A2E] overflow-hidden">
        <div
          className="h-full bg-[#2E66FF] rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4">
        <button
          onClick={onRewind}
          className="p-2 text-[#8B8FA3] hover:text-white transition-colors"
          aria-label="Rewind 10 seconds"
        >
          <SkipBack size={18} />
        </button>

        <button
          onClick={onPlayPause}
          className="p-3 rounded-full bg-[#1A1A2E] text-white hover:bg-[#2E66FF] transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause size={20} /> : <Play size={20} />}
        </button>

        <button
          onClick={onForward}
          className="p-2 text-[#8B8FA3] hover:text-white transition-colors"
          aria-label="Forward 10 seconds"
        >
          <SkipForward size={18} />
        </button>
      </div>

      {/* Bottom labels */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => setCaptionsEnabled(!captionsEnabled)}
          className={`font-mono text-[11px] tracking-wider transition-colors ${captionsEnabled ? 'text-[#F8FAFC]' : 'text-[#555770]'}`}
        >
          CAPTIONS {captionsEnabled ? 'ON' : 'OFF'}
        </button>

        <button
          onClick={cycleSpeed}
          className="font-mono text-[11px] text-[#8B8FA3] hover:text-white transition-colors"
        >
          {playbackSpeed}x
        </button>
      </div>

      {/* Briefing status */}
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-[#2E66FF] animate-pulse" />
        <span className="font-mono text-[11px] text-[#8B8FA3] tracking-wider">
          BRIEFING IN PROGRESS
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Create DialogueHeader**

```typescript
/**
 * DialogueHeader — Top bar of Dialogue Mode.
 *
 * Shows mode indicator (avatar icon in active state), session status,
 * and "End Session" button. Users see this as a visual cue that they're
 * in Dialogue Mode and can click "ARIA" in sidebar to return to text.
 */

import { Video, VideoOff, X } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';

export function DialogueHeader() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isActive = tavusSession.status === 'active';

  return (
    <div className="flex items-center justify-between px-6 py-3 border-b border-[#1A1A2E] bg-[#0A0A0B]">
      <div className="flex items-center gap-3">
        {/* Mode indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#2E66FF]/10 border border-[#2E66FF]/20">
          <Video size={16} className="text-[#2E66FF]" />
          <span className="font-mono text-[11px] text-[#2E66FF] tracking-wider">
            DIALOGUE MODE
          </span>
        </div>

        {/* Session status */}
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              isActive
                ? 'bg-emerald-400 animate-pulse'
                : tavusSession.status === 'connecting'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-[#555770]'
            }`}
          />
          <span className="font-mono text-[11px] text-[#8B8FA3]">
            {isActive ? 'LIVE' : tavusSession.status === 'connecting' ? 'CONNECTING' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* End session */}
      {(isActive || tavusSession.status === 'connecting') && (
        <button
          onClick={() => modalityController.endSession()}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-red-400 hover:bg-red-400/10 transition-colors"
        >
          <VideoOff size={14} />
          <span className="text-xs">End Session</span>
        </button>
      )}
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/avatar/BriefingControls.tsx frontend/src/components/avatar/DialogueHeader.tsx
git commit -m "feat: add BriefingControls and DialogueHeader for Dialogue Mode"
```

---

## Task 13: Frontend — DialogueMode (Composite Layout)

**Files:**
- Create: `frontend/src/components/avatar/DialogueMode.tsx`
- Create: `frontend/src/components/avatar/index.ts`

**Step 1: Create DialogueMode**

```typescript
/**
 * DialogueMode — Full-screen split layout: avatar (left) + transcript (right).
 *
 * Replaces center column at /dialogue and /briefing routes.
 * Reuses same conversationStore and WebSocket event flow as ARIAWorkspace.
 */

import { useEffect, useCallback, useRef } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useModalityStore } from '@/stores/modalityStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload, RichContent, UICommand } from '@/types/chat';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';
import { useUICommands } from '@/hooks/useUICommands';
import { AvatarContainer } from './AvatarContainer';
import { TranscriptPanel } from './TranscriptPanel';
import { DialogueHeader } from './DialogueHeader';
import { BriefingControls } from './BriefingControls';

interface DialogueModeProps {
  sessionType?: 'chat' | 'briefing' | 'debrief';
}

export function DialogueMode({ sessionType = 'chat' }: DialogueModeProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);
  const setIsSpeaking = useModalityStore((s) => s.setIsSpeaking);
  const tavusSession = useModalityStore((s) => s.tavusSession);

  const { session } = useSession();
  const { user } = useAuth();
  useUICommands();

  const streamingIdRef = useRef<string | null>(null);

  // Connect WebSocket on mount (same as ARIAWorkspace)
  useEffect(() => {
    if (!user?.id || !session?.id) return;
    wsManager.connect(user.id, session.id);
    return () => { wsManager.disconnect(); };
  }, [user?.id, session?.id]);

  // Wire up event listeners (same as ARIAWorkspace)
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      setStreaming(false);
      setIsSpeaking(false);

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content || [],
          ui_commands: data.ui_commands || [],
          suggestions: data.suggestions || [],
        });
        streamingIdRef.current = null;
        return;
      }

      addMessage({
        role: 'aria',
        content: data.message,
        rich_content: data.rich_content || [],
        ui_commands: data.ui_commands || [],
        suggestions: data.suggestions || [],
      });

      if (data.suggestions?.length) {
        setCurrentSuggestions(data.suggestions);
      }
      if (data.conversation_id && !activeConversationId) {
        setActiveConversation(data.conversation_id);
      }
    };

    const handleThinking = (payload: unknown) => {
      const data = payload as AriaThinkingPayload;
      if (data.is_thinking) setStreaming(true);
    };

    const handleToken = (payload: unknown) => {
      const data = payload as { content: string; full_content: string };
      if (!streamingIdRef.current) {
        const store = useConversationStore.getState();
        store.addMessage({
          role: 'aria',
          content: data.content,
          rich_content: [],
          ui_commands: [],
          suggestions: [],
          isStreaming: true,
        });
        const msgs = useConversationStore.getState().messages;
        streamingIdRef.current = msgs[msgs.length - 1]?.id ?? null;
        setStreaming(true, streamingIdRef.current);
      } else {
        appendToMessage(streamingIdRef.current, data.content);
      }
    };

    const handleMetadata = (payload: unknown) => {
      const data = payload as {
        message_id: string;
        rich_content: RichContent[];
        ui_commands: UICommand[];
        suggestions: string[];
      };
      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content,
          ui_commands: data.ui_commands,
          suggestions: data.suggestions,
        });
      }
    };

    const handleSpeaking = (payload: unknown) => {
      const data = payload as { is_speaking: boolean };
      setIsSpeaking(data.is_speaking);
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
    };
  }, [addMessage, appendToMessage, updateMessageMetadata, setStreaming, setCurrentSuggestions, activeConversationId, setActiveConversation, setIsSpeaking]);

  const handleSend = useCallback(
    (message: string) => {
      addMessage({
        role: 'user',
        content: message,
        rich_content: [],
        ui_commands: [],
        suggestions: [],
      });
      wsManager.send(WS_EVENTS.USER_MESSAGE, {
        message,
        conversation_id: activeConversationId,
      });
    },
    [addMessage, activeConversationId],
  );

  const isBriefing = sessionType === 'briefing' || tavusSession.sessionType === 'briefing';

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0A0A0B' }}
      data-aria-id="dialogue-mode"
    >
      <DialogueHeader />

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Avatar */}
        <div className="flex-1 flex flex-col items-center justify-center relative">
          <AvatarContainer />
          {isBriefing && (
            <div className="absolute bottom-8 z-10">
              <BriefingControls
                progress={0}
                isPlaying={true}
                onPlayPause={() => {}}
                onRewind={() => {}}
                onForward={() => {}}
              />
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px bg-[#1A1A2E]" />

        {/* Right: Transcript */}
        <TranscriptPanel onSend={handleSend} />
      </div>
    </div>
  );
}
```

**Step 2: Create index.ts**

```typescript
export { DialogueMode } from './DialogueMode';
export { AvatarContainer } from './AvatarContainer';
export { WaveformBars } from './WaveformBars';
export { BriefingControls } from './BriefingControls';
export { TranscriptPanel } from './TranscriptPanel';
export { TranscriptEntry } from './TranscriptEntry';
export { DialogueHeader } from './DialogueHeader';
export { CompactAvatar } from './CompactAvatar';
```

Note: `CompactAvatar` will be created in the next task. Leave the export for now — TypeScript will warn but we'll fix it immediately.

**Step 3: Commit**

```bash
git add frontend/src/components/avatar/DialogueMode.tsx frontend/src/components/avatar/index.ts
git commit -m "feat: add DialogueMode composite layout"
```

---

## Task 14: Frontend — Route + Sidebar + AppShell Wiring

**Files:**
- Modify: `frontend/src/app/routes.tsx` — add /dialogue route
- Modify: `frontend/src/components/shell/Sidebar.tsx` — Briefing → /briefing, add avatar toggle button
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx` — add avatar mode entry button
- Modify: `frontend/src/components/pages/index.ts` — export DialogueMode
- Modify: `frontend/src/app/AppShell.tsx` — wire ModalityController navigate

**Step 1: Update routes.tsx**

Add imports for DialogueMode and add two routes inside the AppShell route group:
```tsx
import { DialogueMode } from '@/components/avatar';

// Inside the Route group:
<Route path="dialogue" element={<DialogueMode />} />
<Route path="briefing" element={<DialogueMode sessionType="briefing" />} />
```

Remove the existing `<Route path="briefing" element={<BriefingPage />} />` line and replace with the DialogueMode version above.

**Step 2: Update Sidebar.tsx**

The Briefing nav item already routes to `/briefing` which will now render DialogueMode. No change needed to the nav entries.

**Step 3: Update ARIAWorkspace.tsx**

Add a small avatar button in the workspace header area. Add it as a button above the ConversationThread:

```tsx
import { Video } from 'lucide-react';
import { modalityController } from '@/core/ModalityController';

// Add a header bar above ConversationThread with the avatar toggle:
<div className="flex items-center justify-end px-6 py-2">
  <button
    onClick={() => modalityController.switchTo('avatar')}
    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-[#2E66FF] hover:bg-[#2E66FF]/10 transition-colors"
    aria-label="Switch to Dialogue Mode"
  >
    <Video size={14} />
    <span className="text-xs">Avatar</span>
  </button>
</div>
```

**Step 4: Update AppShell.tsx**

Wire ModalityController's navigate function using `useNavigate`:

```tsx
import { useNavigate } from 'react-router-dom';
import { modalityController } from '@/core/ModalityController';
import { useEffect } from 'react';

// Inside AppShell component:
const navigate = useNavigate();
useEffect(() => {
  modalityController.setNavigate(navigate);
}, [navigate]);
```

**Step 5: Commit**

```bash
git add frontend/src/app/routes.tsx frontend/src/components/shell/Sidebar.tsx frontend/src/components/pages/ARIAWorkspace.tsx frontend/src/app/AppShell.tsx
git commit -m "feat: wire Dialogue Mode to routes, sidebar, and AppShell"
```

---

## Task 15: Frontend — CompactAvatar PiP

**Files:**
- Create: `frontend/src/components/avatar/CompactAvatar.tsx`
- Modify: `frontend/src/app/AppShell.tsx` — render CompactAvatar

**Step 1: Create CompactAvatar**

```typescript
/**
 * CompactAvatar — Floating 120x120 PiP when user navigates away from Dialogue Mode
 * while a Tavus session is active.
 *
 * Click → navigate back to /dialogue
 * Close button → dismiss PiP, keep session alive
 * Only renders when: tavusSession.status === 'active' AND isPipVisible
 */

import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';
import { WaveformBars } from './WaveformBars';

export function CompactAvatar() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isPipVisible = useModalityStore((s) => s.isPipVisible);

  if (tavusSession.status !== 'active' || !isPipVisible || !tavusSession.roomUrl) {
    return null;
  }

  return createPortal(
    <div
      className="fixed bottom-6 right-6 z-50 group cursor-pointer"
      onClick={() => modalityController.switchTo('avatar')}
    >
      {/* Close button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          modalityController.dismissPip();
        }}
        className="absolute -top-2 -right-2 z-10 w-6 h-6 rounded-full bg-[#0A0A0B] border border-[#1A1A2E] flex items-center justify-center text-[#8B8FA3] hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <X size={12} />
      </button>

      {/* Avatar circle */}
      <div
        className="w-[120px] h-[120px] rounded-full overflow-hidden border-2 border-[#2E66FF]"
        style={{
          boxShadow: '0 0 20px rgba(46,102,255,0.2), 0 4px 20px rgba(0,0,0,0.5)',
        }}
      >
        <iframe
          src={tavusSession.roomUrl}
          className="w-full h-full border-0"
          allow="camera; microphone; autoplay"
          title="ARIA Avatar (compact)"
        />
      </div>

      {/* Mini waveform */}
      <div className="flex justify-center mt-2">
        <WaveformBars variant="mini" />
      </div>
    </div>,
    document.body,
  );
}
```

**Step 2: Render CompactAvatar in AppShell**

Add `<CompactAvatar />` inside the AppShell component (after the closing `</div>` of the three-column layout, but still inside the component return):

```tsx
import { CompactAvatar } from '@/components/avatar';

// In the return:
return (
  <>
    <div className="flex h-screen w-screen overflow-hidden" data-aria-id="app-shell">
      <Sidebar />
      <main ...>
        <Outlet />
      </main>
      {showPanel && <IntelPanel />}
    </div>
    <CompactAvatar />
  </>
);
```

Also wire PiP restore on route change — when user navigates to a content page while Tavus is active:

```tsx
import { useModalityStore } from '@/stores/modalityStore';

// Inside AppShell:
const tavusStatus = useModalityStore((s) => s.tavusSession.status);
const activeModality = useModalityStore((s) => s.activeModality);

useEffect(() => {
  // Show PiP when navigating away from dialogue with active session
  const isDialogueRoute = pathname === '/dialogue' || pathname === '/briefing';
  if (tavusStatus === 'active' && !isDialogueRoute) {
    useModalityStore.getState().setIsPipVisible(true);
  } else if (isDialogueRoute) {
    useModalityStore.getState().setIsPipVisible(false);
  }
}, [pathname, tavusStatus]);
```

**Step 3: Commit**

```bash
git add frontend/src/components/avatar/CompactAvatar.tsx frontend/src/app/AppShell.tsx frontend/src/components/avatar/index.ts
git commit -m "feat: add CompactAvatar PiP with route-aware visibility"
```

---

## Task 16: Frontend — UICommandExecutor switch_mode Integration

**Files:**
- Modify: `frontend/src/core/UICommandExecutor.ts`

**Step 1: Wire switch_mode to ModalityController**

Update the `handleSwitchMode` method in `UICommandExecutor.ts` to use `modalityController`:

Replace the current `handleSwitchMode`:
```typescript
private handleSwitchMode(cmd: UICommand): void {
  if (!cmd.mode || !this.navigateFn) return;

  const modeRoutes: Record<string, string> = {
    workspace: '/',
    dialogue: '/dialogue',
    compact_avatar: '/',
  };
  const route = modeRoutes[cmd.mode];
  if (route) {
    this.navigateFn(route);
    useNavigationStore.getState().setCurrentRoute(route);
  }
}
```

With:
```typescript
private handleSwitchMode(cmd: UICommand): void {
  if (!cmd.mode) return;

  // Import at top of file: import { modalityController } from './ModalityController';
  switch (cmd.mode) {
    case 'dialogue':
      void modalityController.switchTo('avatar');
      break;
    case 'workspace':
      void modalityController.switchTo('text');
      break;
    case 'compact_avatar':
      // Navigate away but keep PiP
      void modalityController.switchTo('text');
      break;
    default:
      console.warn(`[UICommandExecutor] Unknown mode: ${cmd.mode}`);
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/core/UICommandExecutor.ts
git commit -m "feat: wire UICommandExecutor switch_mode to ModalityController"
```

---

## Task 17: Tailwind Config — Custom Keyframes & Animations

**Files:**
- Modify: `frontend/tailwind.config.js` (or `.ts`)

**Step 1: Add all custom keyframes**

Add these to `theme.extend.keyframes`:

```js
'typing-bounce': {
  '0%, 60%, 100%': { transform: 'translateY(0)', opacity: '0.4' },
  '30%': { transform: 'translateY(-6px)', opacity: '1' },
},
'waveform': {
  '0%, 100%': { transform: 'scaleY(0.3)' },
  '50%': { transform: 'scaleY(1)' },
},
'shimmer': {
  '0%': { backgroundPosition: '-200% 0' },
  '100%': { backgroundPosition: '200% 0' },
},
```

Add to `theme.extend.animation`:

```js
'typing-bounce': 'typing-bounce 1.4s infinite',
'waveform': 'waveform 1.2s ease-in-out infinite',
'shimmer': 'shimmer 2s linear infinite',
```

**Step 2: Commit**

```bash
git add frontend/tailwind.config.*
git commit -m "feat: add typing-bounce, waveform, shimmer keyframes to Tailwind config"
```

---

## Task 18: Verify & Fix TypeScript Compilation

**Step 1: Run typecheck**

```bash
cd frontend && npm run typecheck
```

Fix any TypeScript errors that arise — common issues:
- Missing image module declarations (add to `vite-env.d.ts` if needed)
- Import path issues
- Prop type mismatches

**Step 2: Run lint**

```bash
npm run lint
```

Fix any lint issues.

**Step 3: Run build**

```bash
npm run build
```

Verify clean build with no errors.

**Step 4: Commit fixes**

```bash
git add -A
git commit -m "fix: resolve TypeScript and lint issues for Dialogue Mode"
```

---

## Task 19: Verify & Fix Backend

**Step 1: Run ruff check**

```bash
cd backend && ruff check src/api/routes/video.py
```

**Step 2: Run ruff format**

```bash
ruff format src/api/routes/video.py
```

**Step 3: Commit fixes if any**

```bash
git add backend/
git commit -m "fix: format video routes with ruff"
```

---

## Task 20: Final Commit — All Changes

Verify everything is committed and the working directory is clean:

```bash
git status
```

If there are uncommitted changes, stage and commit them.
