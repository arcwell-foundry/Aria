# Dialogue Mode & Conversation UX — Design Document

**Date:** 2026-02-11
**Scope:** Dialogue Mode (split-screen avatar + transcript), Tavus integration, conversation UX enhancements

---

## Overview

Build the split-screen Dialogue Mode layout with AI avatar on the left and rich transcript on the right, plus a suite of conversation UX improvements that apply to both text workspace and dialogue mode.

## Design Decisions

1. **Tavus integration with graceful fallback** — Real Tavus Daily.co iframe when API keys configured; static avatar image (`aria-avatar.png`) with animated waveform when not.
2. **Three entry points to Dialogue Mode:**
   - ARIA pushes `switch_mode: "avatar"` via ui_commands
   - Sidebar "Briefing" always opens Dialogue Mode at `/briefing`
   - Avatar icon button in ARIA Workspace header for manual switch
   - Sidebar "ARIA" always returns to text workspace at `/`
3. **Separate TranscriptPanel** — Purpose-built transcript component, not a variant of ConversationThread. Same `conversationStore` data, completely different rendering (call transcript aesthetic vs chat bubbles).
4. **CompactAvatar PiP** — Only shows when real Tavus session is active (not for static fallback). Close button dismisses PiP but keeps session alive. "End Session" button only exists in full Dialogue Mode.
5. **DialogueHeader as mode indicator** — Shows avatar icon in active state so user knows they're in Dialogue Mode and can click "ARIA" sidebar to return.

---

## Component Architecture

```
DialogueMode (full-screen, replaces center column at /dialogue and /briefing)
├── DialogueHeader (mode indicator + end session button)
├── AvatarContainer (left 50%)
│   ├── Tavus Daily.co iframe (when session active)
│   ├── Static avatar fallback (aria-avatar.png when no session)
│   ├── WaveformBars (12 bars, animated during speech)
│   ├── BriefingControls (play/pause, seek, speed — briefing sessions only)
│   └── CaptionToggle + speed label
├── TranscriptPanel (right 50%)
│   ├── TranscriptHeader ("Transcript & Analysis", share/download buttons)
│   ├── TranscriptMessages (reads from conversationStore)
│   │   └── TranscriptEntry (speaker label, timestamp, content, rich cards)
│   ├── InputBar (reused, placeholder: "Interrupt to ask a question...")
│   └── SuggestionChips (reused)

CompactAvatar (portal, fixed bottom-right, only when Tavus active + not in DialogueMode)
├── Daily.co mini iframe (120x120 circular)
├── WaveformBars (mini variant, 6 bars)
└── Close button (dismiss PiP, keep session)
```

---

## State Management

### modalityStore (Zustand)

```typescript
{
  activeModality: 'text' | 'voice' | 'avatar',
  tavusSession: {
    id: string | null,
    roomUrl: string | null,
    status: 'idle' | 'connecting' | 'active' | 'ending',
    sessionType: 'chat' | 'briefing' | 'debrief',
  },
  isSpeaking: boolean,
  isPipVisible: boolean,
  captionsEnabled: boolean,
  playbackSpeed: number, // 0.75 | 1.0 | 1.25 | 1.5
}
```

### ModalityController (service class)

- `switchTo('avatar', sessionType?)` — create Tavus session, update store, navigate to /dialogue or /briefing
- `switchTo('text')` — navigate to /, show PiP if Tavus active
- `endSession()` — end Tavus session, clear store, navigate to /
- `dismissPip()` — hide PiP, session stays alive
- `restorePip()` — show PiP (re-entering content pages with active session)

### Navigation Interactions

- User clicks content page while Tavus active → PiP appears, content page renders in center
- User clicks "ARIA" sidebar → modality=text, PiP shows if Tavus active
- User clicks "Briefing" sidebar → switchTo('avatar', 'briefing')
- User clicks CompactAvatar PiP → navigate to /dialogue, PiP hides

---

## Visual Design

### Left Half (AvatarContainer)

- Background: radial gradient #0D1117 center → #0A0A0B edges, subtle blue glow rgba(46,102,255,0.08)
- Avatar frame: 280px circle, 2px border #2E66FF, box-shadow 0 0 40px rgba(46,102,255,0.15)
- WaveformBars: 12 bars, 3px wide, 8px gap, max 40px height, #2E66FF, staggered animation-delay 0.1s each, opacity 0.3 idle / 1.0 speaking
- BriefingControls: thin progress track (#1A1A2E bg, #2E66FF fill), icon buttons #8B8FA3 hover #FFFFFF, speed in JetBrains Mono
- Labels: "CAPTIONS ON" toggle JetBrains Mono 11px #8B8FA3, "BRIEFING IN PROGRESS" with dot pulse

### Right Half (TranscriptPanel)

- Background: #0F1117
- Header: "Transcript & Analysis" Instrument Serif italic #F8FAFC, share/download icons #8B8FA3
- ARIA entries: "ARIA" label #2E66FF JetBrains Mono 11px, timestamp #8B8FA3, content Inter 300 #E2E4E9
- User entries: "YOU" label #8B8FA3, content Inter 400 #F8FAFC
- Active message full opacity, previous messages opacity 0.5
- Rich cards: dark bg #1A1A2E, #2E66FF left border
- Input placeholder: "Interrupt to ask a question..." #555770

### CompactAvatar PiP

- 120x120px circle, fixed bottom-right (24px margin), z-index 50
- 2px #2E66FF border with glow, close X on hover
- 6 mini WaveformBars below, click → /dialogue

---

## Conversation UX Enhancements

### Message Avatars (MessageAvatar.tsx)

- 32px circular, top-aligned
- ARIA: aria-avatar-transparent.png, circular crop
- User: profile photo from AuthContext, fallback initials on #1C1C1E bg with #A1A1AA text
- Only show on first message in consecutive group from same sender
- ConversationThread: ARIA left, user right. TranscriptPanel: both left-aligned

### Typing Indicator (TypingIndicator.tsx)

- ARIA avatar + three-dot bounce animation (like iMessage)
- Bounce 1.4s infinite, each dot delayed 0.16s
- Shown when isStreaming or aria.thinking event

### Timestamps

- Chat: hidden by default, hover tooltip (JetBrains Mono 11px #555770)
- Transcript: always visible inline with speaker label
- Time dividers: >30min gap → "Today, 9:14 AM" centered, Inter 400 12px #555770, thin #1A1A2E lines

### Message Animations

- ARIA: translateX(-8px) → 0, opacity 0 → 1, 200ms ease-out
- User: translateX(8px) → 0, 200ms ease-out
- Rich cards: scale(0.98) → 1, 250ms ease-out
- Respects prefers-reduced-motion

### Background Work Indicator (BackgroundWorkIndicator.tsx)

- Persistent bar above InputBar, #111318 bg
- "✦" #2E66FF + task description Inter 300 #8B8FA3 with shimmer animation
- Driven by agent.started / agent.completed WebSocket events
- Max 2 lines, then "+N more tasks" link → /actions
- Hidden when no agents active

### Unread Indicator (UnreadIndicator.tsx)

- Pill at top of thread: "3 new messages from ARIA ↓" in #2E66FF bg white text
- Tracks count when user on different route or tab unfocused
- Click scrolls to first unread, dismiss on scroll past (IntersectionObserver)
- Drives badge count on "ARIA" sidebar item

### Rich Content Collapse (CollapsibleCard.tsx)

- Cards >200px collapse by default in conversation
- Collapsed: title + 2-line summary + "Show more", gradient fade
- Approval rows always visible outside collapsible wrapper
- Content pages: always expanded (collapsible={false})

---

## Backend

### Video Session Endpoints (video.py)

```
POST /api/v1/video/sessions — create Tavus conversation, store in Supabase
GET  /api/v1/video/sessions/{id} — get session status + room URL
POST /api/v1/video/sessions/{id}/end — end session, save transcript
```

### Migration (20260211_video_sessions.sql)

- `video_sessions` table: id, user_id, tavus_conversation_id, room_url, status, session_type, started_at, ended_at, duration_seconds, created_at
- `video_transcripts` table: id, video_session_id, speaker, content, timestamp_ms, created_at
- RLS policies scoped to authenticated user

---

## File Manifest

### New Files (20)

```
backend/supabase/migrations/20260211_video_sessions.sql
backend/src/api/routes/video.py

frontend/src/stores/modalityStore.ts
frontend/src/core/ModalityController.ts

frontend/src/components/avatar/DialogueMode.tsx
frontend/src/components/avatar/AvatarContainer.tsx
frontend/src/components/avatar/WaveformBars.tsx
frontend/src/components/avatar/BriefingControls.tsx
frontend/src/components/avatar/TranscriptPanel.tsx
frontend/src/components/avatar/TranscriptEntry.tsx
frontend/src/components/avatar/CompactAvatar.tsx
frontend/src/components/avatar/DialogueHeader.tsx
frontend/src/components/avatar/index.ts

frontend/src/components/conversation/TypingIndicator.tsx
frontend/src/components/conversation/TimeDivider.tsx
frontend/src/components/conversation/BackgroundWorkIndicator.tsx
frontend/src/components/conversation/UnreadIndicator.tsx
frontend/src/components/conversation/CollapsibleCard.tsx
frontend/src/components/conversation/MessageAvatar.tsx
```

### Modified Files (8)

```
frontend/src/app/routes.tsx
frontend/src/app/AppShell.tsx
frontend/src/components/conversation/MessageBubble.tsx
frontend/src/components/conversation/ConversationThread.tsx
frontend/src/components/shell/Sidebar.tsx
frontend/src/core/UICommandExecutor.ts
frontend/src/components/pages/ARIAWorkspace.tsx
backend/src/main.py
```

---

## Implementation Order

1. Backend: migration + video routes
2. modalityStore + ModalityController
3. Conversation enhancements: MessageAvatar, TypingIndicator, TimeDivider, message animations, hover timestamps
4. UnreadIndicator + BackgroundWorkIndicator + CollapsibleCard
5. WaveformBars + AvatarContainer
6. TranscriptEntry + TranscriptPanel
7. BriefingControls + DialogueHeader
8. DialogueMode (composes all above)
9. Route + Sidebar + AppShell wiring
10. CompactAvatar PiP
11. UICommandExecutor switch_mode integration
