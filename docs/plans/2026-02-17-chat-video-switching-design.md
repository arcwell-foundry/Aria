# Chat ↔ Video Switching — Design Document

**Date:** 2026-02-17
**Status:** Approved

## Overview

Seamless modality switching between text chat, voice calls, and video sessions — all preserving full conversation context. Users can fluidly move between surfaces while ARIA maintains continuity.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SurfaceSwitcher approach | Inline toolbar integration | Extends existing InputBar + DialogueHeader patterns; no new floating elements competing with CompactAvatar PiP |
| VideoSessionSummaryCard | Collapsed by default | Card is a reference anchor, not primary reading surface; user already knows what was discussed |
| Dashboard CTAs | Empty-state in ARIAWorkspace | ARIA drives the experience; welcome area dissolves once conversation begins |
| Chat context in video | Separate collapsible section | Clear separation between "what happened before" and "what's happening now" |

---

## 1. InputBar Modality Controls

Extend the existing InputBar phone button into a modality button group, to the left of the send button.

### Chat → Other Modalities (InputBar)

- **Phone icon** (existing) — starts audio-only call via `modalityController.switchToAudioCall('chat')`, navigates to `/dialogue`
- **Video icon** (new) — starts video call via `modalityController.switchToAvatar('chat')`, navigates to `/dialogue` with `audio_only: false`
- Both buttons use `modalityController` methods, differing only on `audio_only` flag
- Buttons are ghost style, 32x32, with tooltips ("Voice call", "Video call")
- During an active Tavus session (PiP visible), buttons become disabled with tooltip: "Already in a call"

### Video/Audio → Chat (DialogueHeader)

- Add a **chat bubble icon button** to DialogueHeader alongside the existing end-session button
- Click fires `ContextBridgeService.video_to_chat_context()` to persist transcript and extract summary, then navigates to `/`
- Tooltip: "Switch to Chat"
- Separate from "End Session" button — "End Session" fully terminates, "Switch to Chat" transitions with context preservation

### Context Continuity

Both directions pass `conversation_id`:
- Chat → Video: active conversation ID sent in video session creation request
- Video → Chat: linked conversation resumed on return

---

## 2. VideoSessionSummaryCard

Rendered as a specialized rich content card in the conversation thread when returning from video/audio to chat.

### Rich Content Type

New `rich_content` type: `video_session_summary`

```typescript
interface VideoSessionSummary {
  type: 'video_session_summary'
  session_id: string
  duration_seconds: number
  is_audio_only: boolean
  summary: string
  topics: string[]
  action_items: Array<{
    text: string
    is_tracked: boolean  // auto-created as prospective task
  }>
  transcript_entries: Array<{
    speaker: 'aria' | 'user'
    text: string
    timestamp: string
  }>
}
```

### Collapsed State (Default)

- Card with subtle border and video camera / phone icon (based on `is_audio_only`)
- Header: "Video Session" or "Voice Call"
- Duration badge: "12 min"
- Stats row: "3 topics · 2 action items"
- Chevron to expand

### Expanded State

- **Action items** — Checkbox-style list (visual only). Items auto-created as prospective tasks get a "Tracked" badge
- **Topics discussed** — Pill/tag list of topic keywords
- **Transcript** — Scrollable container (max-height ~300px), speaker-attributed entries with timestamps. Monospace timestamps, bold speaker labels
- "Watch recording" link — disabled with "(Coming soon)"

### Data Source

Backend `video_to_chat_context()` returns `{summary, action_items, messages_stored, tasks_created}`. This is packaged as a `rich_content` item of type `video_session_summary` in the ARIA message posted via WebSocket.

---

## 3. Chat Context in DialogueMode

Collapsible ChatContextSection at the top of TranscriptPanel when video/audio starts from an active chat conversation.

### Appearance

- Above live transcript, separated by divider line
- Header: "Continuing from chat" with message count badge ("4 messages") and collapse chevron
- Starts expanded on mount, auto-collapses after 10 seconds or when first video transcript entry arrives (whichever first)
- Slightly different background shade (`bg-white/5` on dark) for visual separation

### Content

- Last 5–8 chat messages from linked conversation
- Compact format: role label + text, single-line truncated
- Click expands inline to full text
- No rich content rendering — plain text only

### Data Flow

- On mount, check `modalityStore.tavusSession` for linked `conversation_id`
- If present, load recent messages from `conversationStore` or fetch `GET /conversations/{id}/messages?limit=8`
- If no linked conversation (e.g., started from briefing), section doesn't render

### Live Tool Results

During video, tool execution results appear in TranscriptPanel as normal. Backend also stores these in the linked chat conversation via ContextBridgeService for availability when switching back to chat.

---

## 4. Empty-State Welcome CTAs

When ARIAWorkspace loads with no messages, show a welcome hero area centered in the workspace.

### Layout

- Centered vertically and horizontally in conversation area
- ARIA avatar (static image, 80px circle) at top
- Greeting: "Good morning, {firstName}" (time-of-day aware)
- Subtext: contextual one-liner from ARIA (e.g., "I've been reviewing your pipeline overnight. How would you like to connect?")

### Three CTA Buttons

| Button | Icon | Subtitle | Action |
|--------|------|----------|--------|
| Morning Briefing | Video camera | "Video walkthrough" | `modalityController.switchToAvatar('briefing')` → `/briefing` |
| Quick Question | Phone | "Voice call" | `modalityController.switchToAudioCall('chat')` |
| Type a message | Chat bubble | "Text chat" | Focus InputBar textarea |

### Button Style

- Card-like, ~140px wide, dark surface with subtle border
- Icon + label + subtitle stacked vertically
- Hover lifts with shadow
- Uses existing primitives (Card, Button patterns)

### Dissolve Behavior

- Clicking any CTA or typing in InputBar fades out the welcome area (200ms opacity transition)
- Conversation thread takes over full space
- On subsequent loads within same session (messages exist), welcome area never shows

---

## Components Summary

### New Files

| File | Purpose |
|------|---------|
| `components/conversation/VideoSessionSummaryCard.tsx` | Collapsed/expanded video session summary |
| `components/avatar/ChatContextSection.tsx` | Collapsible recent chat context in TranscriptPanel |
| `components/conversation/WelcomeCTAs.tsx` | Empty-state hero with three modality buttons |

### Modified Files

| File | Change |
|------|--------|
| `components/conversation/InputBar.tsx` | Add video call button alongside existing phone button |
| `components/avatar/DialogueHeader.tsx` | Add "Switch to Chat" button |
| `components/avatar/TranscriptPanel.tsx` | Mount ChatContextSection at top |
| `components/conversation/ConversationThread.tsx` | Render VideoSessionSummaryCard for `video_session_summary` rich content |
| `components/conversation/MessageBubble.tsx` | Dispatch `video_session_summary` rich content type |
| `pages/ARIAWorkspace.tsx` | Show WelcomeCTAs when no messages; dissolve on interaction |
| `core/ModalityController.ts` | Add `switchToChat()` method that triggers context bridge before navigating |
| `types/chat.ts` | Add `VideoSessionSummary` interface |
