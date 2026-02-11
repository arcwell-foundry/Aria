# WebSocket Manager & ARIA Workspace Design

**Date:** 2026-02-11
**Status:** Approved

## Overview

Build the real-time transport layer (WebSocket + SSE fallback) and the primary ARIA Workspace conversation interface — the default screen users see when they open ARIA.

## 1. Transport Layer: WebSocketManager

**File:** `frontend/src/core/WebSocketManager.ts`

Singleton event manager with dual transport backends:

### WebSocket Transport (Primary)
- Connects to `ws://{host}/ws/{user_id}?session={session_id}`
- Auto-reconnect: exponential backoff (1s base, 2x multiplier, 30s max, 10 attempts)
- Heartbeat: 30-second interval
- Full bidirectional event handling

### SSE Fallback (Interim)
- Used when WebSocket endpoint doesn't exist or fails to connect
- Sends via REST `POST /api/v1/chat/stream`
- Receives via SSE fetch reader (existing streaming infrastructure)
- Same public API as WebSocket transport

### Connection Strategy
1. Attempt WebSocket connection
2. If fails (404, timeout, error) → fall back to SSE adapter
3. Retry WebSocket upgrade every 60 seconds in background
4. Auto-switch to WebSocket when it becomes available

### Public API
```typescript
class WebSocketManager {
  connect(userId: string, sessionId: string): void
  disconnect(): void
  send(event: string, payload: unknown): void
  on<T>(event: string, handler: (payload: T) => void): void
  off(event: string, handler: Function): void
  get isConnected(): boolean
  get transport(): 'websocket' | 'sse' | 'disconnected'
}
```

### Typed Events

**Server → Client:**
- `aria.message` — message + rich_content + ui_commands + suggestions
- `aria.thinking` — processing indicator
- `aria.speaking` — avatar script + emotion
- `action.pending` — action needs approval
- `action.completed` — action finished
- `progress.update` — goal progress
- `signal.detected` — intelligence signal
- `emotion.detected` — Raven-0 emotion
- `session.sync` — session state delta

**Client → Server:**
- `user.message` — text or voice transcript
- `user.navigate` — route change
- `user.approve` / `user.reject` — action approval
- `modality.change` — mode switch
- `heartbeat` — keep-alive

## 2. Conversation Store (Zustand)

**File:** `frontend/src/stores/conversationStore.ts` (upgrade existing)

### Message Type
```typescript
interface Message {
  id: string
  role: 'aria' | 'user' | 'system'
  content: string
  rich_content: RichContent[]
  ui_commands: UICommand[]
  suggestions: string[]
  timestamp: string
  isStreaming?: boolean
}
```

### State
- `messages: Message[]` — conversation thread
- `isStreaming: boolean` — ARIA is generating
- `streamingMessageId: string | null` — which message is streaming
- `currentSuggestions: string[]` — latest suggestion chips
- Existing: `activeConversationId`, `inputValue`, `isTyping`, `isLoading`

### Actions
- `addMessage(message)` — add complete message
- `appendToMessage(id, content)` — streaming token append
- `updateMessageMetadata(id, {rich_content, ui_commands, suggestions})` — on stream complete
- `setCurrentSuggestions(suggestions)` — update chips
- `setStreaming(boolean)` — toggle streaming state
- Existing: `setActiveConversation`, `clearMessages`, `setInputValue`

## 3. Components

### ARIAWorkspace (`components/pages/ARIAWorkspace.tsx`)
- Full-width (no IntelPanel on this route)
- Dark theme: `#0A0A0B` background
- Flex column: ConversationThread (flex-1) + InputBar + SuggestionChips
- Connects to WebSocketManager on mount, listens for `aria.message` / `aria.thinking`

### ConversationThread (`components/conversation/ConversationThread.tsx`)
- Scrollable message list with auto-scroll on new messages
- Maps messages → MessageBubble components
- Shows StreamingIndicator when `isStreaming` is true
- Ref-based scroll management (scrollIntoView on new message)

### MessageBubble (`components/conversation/MessageBubble.tsx`)
- **ARIA messages:** Left-aligned, `border-l-2` in electric blue, no bubble bg
  - Instrument Serif italic for key section headings
  - Markdown rendering via react-markdown
  - Rich content rendered inline via RichContentRenderer (placeholder for now)
- **User messages:** Right-aligned, `bg-[var(--bg-elevated)]` rounded surface
- Timestamps: JetBrains Mono, muted color, 10px

### InputBar (`components/conversation/InputBar.tsx`)
- Full-width bar at bottom
- Left: microphone button (lucide Mic icon)
- Center: text input, placeholder "Ask ARIA anything..."
- Right: send button (electric blue), "SPACE TO TALK" badge
- Gradient glow: `box-shadow: 0 -20px 60px rgba(46,102,255,0.08)`
- Submit: sends via WebSocketManager `user.message`, adds to store

### SuggestionChips (`components/conversation/SuggestionChips.tsx`)
- Renders `currentSuggestions` from store (2-3 pills)
- Header: "ARIA IS LISTENING • {n} SUGGESTIONS AVAILABLE"
- Click → sends as user message
- Styled as outlined pills with hover highlight

## 4. Type Definitions

**File:** `frontend/src/types/chat.ts`

Shared types for Message, RichContent, UICommand, WSEvent enums, and event payloads. Imported by store, components, and WebSocketManager.
