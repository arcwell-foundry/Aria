# WebSocket Manager & ARIA Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the real-time transport layer and primary conversation UI so users can chat with ARIA in the default workspace.

**Architecture:** WebSocketManager (dual transport: WebSocket primary + SSE fallback) feeds a Zustand conversation store. The ARIA Workspace page renders ConversationThread + InputBar + SuggestionChips — all dark-themed, ARIA-driven.

**Tech Stack:** React 18, TypeScript (strict), Zustand 5, Tailwind CSS 4, react-markdown, lucide-react, framer-motion

---

### Task 1: Shared Type Definitions

**Files:**
- Create: `frontend/src/types/chat.ts`

**Context:** Types for WebSocket events, messages, and UI commands. The existing `frontend/src/api/chat.ts` already has `UICommand` and `RichContent` interfaces (lines 47-57) — we'll re-export those and add the new types alongside them. The project uses `verbatimModuleSyntax: true` so all type imports must use `import type`.

**Step 1: Create the shared types file**

```typescript
// frontend/src/types/chat.ts

import type { RichContent, UICommand } from '@/api/chat';

// Re-export for convenience
export type { RichContent, UICommand };

// === Message Types ===

export interface Message {
  id: string;
  role: 'aria' | 'user' | 'system';
  content: string;
  rich_content: RichContent[];
  ui_commands: UICommand[];
  suggestions: string[];
  timestamp: string;
  isStreaming?: boolean;
}

// === WebSocket Event Types ===

export const WS_EVENTS = {
  // Server → Client
  ARIA_MESSAGE: 'aria.message',
  ARIA_THINKING: 'aria.thinking',
  ARIA_SPEAKING: 'aria.speaking',
  ACTION_PENDING: 'action.pending',
  ACTION_COMPLETED: 'action.completed',
  PROGRESS_UPDATE: 'progress.update',
  SIGNAL_DETECTED: 'signal.detected',
  EMOTION_DETECTED: 'emotion.detected',
  SESSION_SYNC: 'session.sync',

  // Client → Server
  USER_MESSAGE: 'user.message',
  USER_NAVIGATE: 'user.navigate',
  USER_APPROVE: 'user.approve',
  USER_REJECT: 'user.reject',
  MODALITY_CHANGE: 'modality.change',
  HEARTBEAT: 'heartbeat',
} as const;

export type WSEventType = (typeof WS_EVENTS)[keyof typeof WS_EVENTS];

// === Event Payloads ===

export interface AriaMessagePayload {
  message: string;
  rich_content?: RichContent[];
  ui_commands?: UICommand[];
  suggestions?: string[];
  conversation_id?: string;
  message_id?: string;
  avatar_script?: string;
  voice_emotion?: 'neutral' | 'excited' | 'concerned' | 'warm';
}

export interface AriaThinkingPayload {
  is_thinking: boolean;
}

export interface UserMessagePayload {
  message: string;
  conversation_id?: string;
}

export interface WSEnvelope {
  type: string;
  payload: unknown;
}
```

**Step 2: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to `types/chat.ts`

**Step 3: Commit**

```bash
git add frontend/src/types/chat.ts
git commit -m "feat: add shared WebSocket and message type definitions"
```

---

### Task 2: WebSocketManager Core

**Files:**
- Create: `frontend/src/core/WebSocketManager.ts`

**Context:** Singleton class with typed event emitter pattern. The project uses `@/*` path aliases (tsconfig.app.json line 22). The existing `SessionManager.ts` in the same directory is a class-based service — follow the same pattern. The API base URL comes from `import.meta.env.VITE_API_URL` (see `frontend/src/api/client.ts` line 1 pattern). Token is in `localStorage.getItem('access_token')`.

**Step 1: Create WebSocketManager**

```typescript
// frontend/src/core/WebSocketManager.ts

import { WS_EVENTS, type WSEnvelope } from '@/types/chat';

type EventHandler = (payload: unknown) => void;

interface ConnectionConfig {
  userId: string;
  sessionId: string;
}

const HEARTBEAT_INTERVAL = 30_000;
const RECONNECT_BASE_DELAY = 1_000;
const RECONNECT_MAX_DELAY = 30_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const WS_UPGRADE_RETRY_INTERVAL = 60_000;

/**
 * Dual-transport event manager.
 *
 * Primary: WebSocket at /ws/{user_id}?session={session_id}
 * Fallback: SSE via POST /api/v1/chat/stream (existing endpoint)
 *
 * Both transports expose the same on/off/send interface.
 */
class WebSocketManagerImpl {
  private ws: WebSocket | null = null;
  private listeners = new Map<string, Set<EventHandler>>();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private wsUpgradeTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;
  private config: ConnectionConfig | null = null;
  private _transport: 'websocket' | 'sse' | 'disconnected' = 'disconnected';
  private _isConnected = false;
  private intentionalDisconnect = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  get transport(): 'websocket' | 'sse' | 'disconnected' {
    return this._transport;
  }

  /**
   * Connect to the backend. Tries WebSocket first, falls back to SSE.
   */
  connect(userId: string, sessionId: string): void {
    this.config = { userId, sessionId };
    this.intentionalDisconnect = false;
    this.reconnectAttempts = 0;
    this.attemptWebSocket();
  }

  /**
   * Gracefully disconnect and stop all timers.
   */
  disconnect(): void {
    this.intentionalDisconnect = true;
    this.cleanup();
    this._transport = 'disconnected';
    this._isConnected = false;
  }

  /**
   * Send a typed event to the server.
   */
  send(event: string, payload: unknown): void {
    const envelope: WSEnvelope = { type: event, payload };

    if (this._transport === 'websocket' && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(envelope));
      return;
    }

    // SSE mode: send via REST for user.message, ignore other events
    if (this._transport === 'sse' && event === WS_EVENTS.USER_MESSAGE) {
      void this.sendViaRest(payload as { message: string; conversation_id?: string });
      return;
    }
  }

  /**
   * Register an event handler.
   */
  on<T = unknown>(event: string, handler: (payload: T) => void): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler as EventHandler);
  }

  /**
   * Remove an event handler.
   */
  off(event: string, handler: EventHandler): void {
    this.listeners.get(event)?.delete(handler);
  }

  // ── Private: WebSocket transport ──────────────────────────

  private attemptWebSocket(): void {
    if (!this.config) return;

    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    const url = `${wsUrl}/ws/${this.config.userId}?session=${this.config.sessionId}`;
    const token = localStorage.getItem('access_token');

    try {
      this.ws = new WebSocket(token ? `${url}&token=${token}` : url);
    } catch {
      this.fallbackToSSE();
      return;
    }

    const connectTimeout = setTimeout(() => {
      if (this.ws?.readyState !== WebSocket.OPEN) {
        this.ws?.close();
        this.fallbackToSSE();
      }
    }, 5_000);

    this.ws.onopen = () => {
      clearTimeout(connectTimeout);
      this._transport = 'websocket';
      this._isConnected = true;
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.stopWSUpgradeRetry();
      this.emit('connection.established', { transport: 'websocket' });
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const envelope = JSON.parse(event.data as string) as WSEnvelope;
        this.emit(envelope.type, envelope.payload);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      clearTimeout(connectTimeout);
      this.stopHeartbeat();

      if (this.intentionalDisconnect) return;

      // 4xx close codes mean the endpoint rejected us — don't retry WS
      if (event.code >= 4000 && event.code < 5000) {
        this.fallbackToSSE();
        return;
      }

      // Was previously connected — try to reconnect
      if (this._transport === 'websocket') {
        this._isConnected = false;
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      clearTimeout(connectTimeout);
      // onclose will fire after onerror — handling happens there
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.fallbackToSSE();
      return;
    }

    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_DELAY,
    );
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.attemptWebSocket();
    }, delay);
  }

  // ── Private: SSE fallback transport ───────────────────────

  private fallbackToSSE(): void {
    this.ws?.close();
    this.ws = null;
    this._transport = 'sse';
    this._isConnected = true;
    this.emit('connection.established', { transport: 'sse' });
    this.startWSUpgradeRetry();
  }

  /**
   * In SSE mode, sending a message goes through the existing REST streaming
   * endpoint. We parse the SSE events and re-emit them as typed events.
   */
  private async sendViaRest(payload: { message: string; conversation_id?: string }): Promise<void> {
    const token = localStorage.getItem('access_token');
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    // Emit thinking state
    this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: true });

    try {
      const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: payload.message,
          conversation_id: payload.conversation_id,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';
      let messageId = '';
      let conversationId = payload.conversation_id || '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6);

          if (jsonStr === '[DONE]') {
            this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: false });
            this.emit(WS_EVENTS.ARIA_MESSAGE, {
              message: fullContent,
              message_id: messageId,
              conversation_id: conversationId,
            });
            return;
          }

          try {
            const event = JSON.parse(jsonStr);
            if (event.type === 'token') {
              fullContent += event.content;
              // Emit partial content for streaming display
              this.emit('aria.token', { content: event.content, full_content: fullContent });
            } else if (event.type === 'metadata') {
              messageId = event.message_id;
              conversationId = event.conversation_id;
            } else if (event.type === 'complete') {
              // Attach rich_content, ui_commands, suggestions to final message
              if (event.rich_content || event.ui_commands || event.suggestions) {
                this.emit('aria.metadata', {
                  message_id: messageId,
                  rich_content: event.rich_content || [],
                  ui_commands: event.ui_commands || [],
                  suggestions: event.suggestions || [],
                });
              }
            } else if (event.type === 'error') {
              throw new Error(event.content);
            }
          } catch (e) {
            if (e instanceof Error && e.message !== 'Unexpected end of JSON input') {
              // Re-throw real errors, ignore parse errors from partial chunks
              if (!String(e.message).includes('JSON')) throw e;
            }
          }
        }
      }
    } catch (error) {
      this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: false });
      this.emit('connection.error', { error: String(error) });
    }
  }

  /**
   * Periodically try to upgrade from SSE to WebSocket.
   */
  private startWSUpgradeRetry(): void {
    this.stopWSUpgradeRetry();
    this.wsUpgradeTimer = setInterval(() => {
      if (this._transport === 'sse' && !this.intentionalDisconnect) {
        // Try a quick WebSocket probe
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const wsUrl = baseUrl.replace(/^http/, 'ws');
        const url = `${wsUrl}/ws/${this.config?.userId}?session=${this.config?.sessionId}`;
        const probe = new WebSocket(url);
        const timeout = setTimeout(() => probe.close(), 3_000);

        probe.onopen = () => {
          clearTimeout(timeout);
          probe.close();
          // WebSocket endpoint is now available — switch
          this.stopWSUpgradeRetry();
          this.reconnectAttempts = 0;
          this.attemptWebSocket();
        };

        probe.onerror = () => {
          clearTimeout(timeout);
          // Stay on SSE
        };
      }
    }, WS_UPGRADE_RETRY_INTERVAL);
  }

  private stopWSUpgradeRetry(): void {
    if (this.wsUpgradeTimer) {
      clearInterval(this.wsUpgradeTimer);
      this.wsUpgradeTimer = null;
    }
  }

  // ── Private: Heartbeat ────────────────────────────────────

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send(WS_EVENTS.HEARTBEAT, { timestamp: Date.now() });
    }, HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ── Private: Event emission ───────────────────────────────

  private emit(event: string, payload: unknown): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(payload);
        } catch (e) {
          console.error(`[WebSocketManager] Handler error for ${event}:`, e);
        }
      }
    }
  }

  // ── Private: Cleanup ──────────────────────────────────────

  private cleanup(): void {
    this.stopHeartbeat();
    this.stopWSUpgradeRetry();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
  }
}

/** Singleton instance */
export const wsManager = new WebSocketManagerImpl();
```

**Step 2: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/core/WebSocketManager.ts
git commit -m "feat: add WebSocketManager with dual transport (WS + SSE fallback)"
```

---

### Task 3: Upgrade Conversation Store

**Files:**
- Modify: `frontend/src/stores/conversationStore.ts` (full rewrite)

**Context:** The existing store (72 lines) has `Message` with `role: 'user' | 'assistant' | 'system'` and `metadata?: Record<string, unknown>`. We need to change the role to `'aria' | 'user' | 'system'`, add `rich_content`, `ui_commands`, `suggestions`, `isStreaming` fields, and new actions for streaming. The store is exported via `frontend/src/stores/index.ts` — keep the export name `useConversationStore` and the type name `ConversationState`.

**Step 1: Rewrite the store**

Replace the entire contents of `frontend/src/stores/conversationStore.ts` with:

```typescript
/**
 * Conversation Store - Chat state management for ARIA Workspace
 *
 * Manages the message thread, streaming state, and suggestion chips.
 * Fed by WebSocketManager events (aria.message, aria.token, aria.thinking).
 */

import { create } from 'zustand';
import type { Message, RichContent, UICommand } from '@/types/chat';

export type { Message };

export interface ConversationState {
  // State
  activeConversationId: string | null;
  messages: Message[];
  inputValue: string;
  isTyping: boolean;
  isLoading: boolean;
  isStreaming: boolean;
  streamingMessageId: string | null;
  currentSuggestions: string[];

  // Actions
  setActiveConversation: (id: string | null) => void;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void;
  appendToMessage: (id: string, content: string) => void;
  updateMessageMetadata: (
    id: string,
    metadata: {
      rich_content?: RichContent[];
      ui_commands?: UICommand[];
      suggestions?: string[];
    },
  ) => void;
  setMessages: (messages: Message[]) => void;
  clearMessages: () => void;
  setInputValue: (value: string) => void;
  setIsTyping: (isTyping: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
  setStreaming: (isStreaming: boolean, messageId?: string | null) => void;
  setCurrentSuggestions: (suggestions: string[]) => void;
}

export const useConversationStore = create<ConversationState>((set) => ({
  // Initial state
  activeConversationId: null,
  messages: [],
  inputValue: '',
  isTyping: false,
  isLoading: false,
  isStreaming: false,
  streamingMessageId: null,
  currentSuggestions: [],

  // Actions
  setActiveConversation: (id) => set({ activeConversationId: id }),

  addMessage: (message) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...message,
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
          timestamp: new Date().toISOString(),
        },
      ],
    })),

  appendToMessage: (id, content) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, content: msg.content + content } : msg,
      ),
    })),

  updateMessageMetadata: (id, metadata) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id
          ? {
              ...msg,
              rich_content: metadata.rich_content ?? msg.rich_content,
              ui_commands: metadata.ui_commands ?? msg.ui_commands,
              suggestions: metadata.suggestions ?? msg.suggestions,
              isStreaming: false,
            }
          : msg,
      ),
      // Update global suggestions from the latest ARIA message
      currentSuggestions: metadata.suggestions?.length
        ? metadata.suggestions
        : state.currentSuggestions,
    })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [], currentSuggestions: [] }),

  setInputValue: (value) => set({ inputValue: value }),

  setIsTyping: (isTyping) => set({ isTyping }),

  setIsLoading: (isLoading) => set({ isLoading }),

  setStreaming: (isStreaming, messageId = null) =>
    set({ isStreaming, streamingMessageId: messageId }),

  setCurrentSuggestions: (suggestions) => set({ currentSuggestions: suggestions }),
}));
```

**Step 2: Verify it compiles (check for import breakage)**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -40`
Expected: May show errors in files that import the old `Message` type with `role: 'assistant'`. Fix any import issues — the `useChat.ts` hook and any components using `role: 'assistant'` need to be checked.

**Step 3: Fix any downstream breakage**

The `useChat.ts` hook (`frontend/src/hooks/useChat.ts`) uses `ChatMessage` from `@/api/chat` (not the store `Message` type), so it should be unaffected. Check and fix any other imports.

**Step 4: Commit**

```bash
git add frontend/src/stores/conversationStore.ts
git commit -m "feat: upgrade conversation store with streaming, rich content, and suggestions"
```

---

### Task 4: MessageBubble Component

**Files:**
- Create: `frontend/src/components/conversation/MessageBubble.tsx`

**Context:** Uses `react-markdown` (already installed, `react-markdown@^10.1.0`). Uses `lucide-react` for icons. Uses CSS variables from `frontend/src/index.css`. Fonts: `font-display` = Instrument Serif, `font-mono` = JetBrains Mono, `font-sans` = Satoshi/Inter. The Tailwind theme has `--color-accent` for electric blue.

**Step 1: Create MessageBubble**

```typescript
// frontend/src/components/conversation/MessageBubble.tsx

import ReactMarkdown from 'react-markdown';
import type { Message } from '@/types/chat';

interface MessageBubbleProps {
  message: Message;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isAria = message.role === 'aria';

  if (isAria) {
    return (
      <div className="flex justify-start animate-in" data-aria-id="message-aria">
        <div className="max-w-[85%] border-l-2 border-accent pl-4 py-2">
          <div className="prose-aria">
            <ReactMarkdown
              components={{
                h1: ({ children }) => (
                  <h1 className="font-display italic text-xl text-[var(--text-primary)] mb-2 mt-4 first:mt-0">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="font-display italic text-lg text-[var(--text-primary)] mb-2 mt-3 first:mt-0">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="font-display italic text-base text-[var(--text-primary)] mb-1 mt-3 first:mt-0">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="text-sm leading-relaxed text-[var(--text-primary)] mb-2 last:mb-0">
                    {children}
                  </p>
                ),
                ul: ({ children }) => (
                  <ul className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-disc space-y-1">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-decimal space-y-1">
                    {children}
                  </ol>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
                ),
                code: ({ children, className }) => {
                  const isBlock = className?.includes('language-');
                  if (isBlock) {
                    return (
                      <code className="block font-mono text-xs bg-[var(--bg-elevated)] rounded-md p-3 my-2 overflow-x-auto text-[var(--text-secondary)]">
                        {children}
                      </code>
                    );
                  }
                  return (
                    <code className="font-mono text-xs bg-[var(--bg-elevated)] rounded px-1.5 py-0.5 text-[var(--accent)]">
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Rich content placeholder */}
          {message.rich_content.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.rich_content.map((rc, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]"
                  data-aria-id={`rich-content-${rc.type}`}
                >
                  <span className="font-mono uppercase tracking-wider text-[var(--accent)]">
                    {rc.type}
                  </span>
                </div>
              ))}
            </div>
          )}

          <span className="block mt-2 font-mono text-[10px] text-[var(--text-secondary)] opacity-60">
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  // User message
  return (
    <div className="flex justify-end animate-in" data-aria-id="message-user">
      <div className="max-w-[75%] bg-[var(--bg-elevated)] rounded-2xl rounded-br-md px-4 py-3">
        <p className="text-sm text-[var(--text-primary)]">{message.content}</p>
        <span className="block mt-1.5 font-mono text-[10px] text-[var(--text-secondary)] opacity-60 text-right">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/MessageBubble.tsx
git commit -m "feat: add MessageBubble component with markdown and rich content support"
```

---

### Task 5: ConversationThread Component

**Files:**
- Create: `frontend/src/components/conversation/ConversationThread.tsx`

**Context:** Scrollable container that renders MessageBubble for each message. Uses `useConversationStore` for message list and streaming state. Auto-scrolls on new message via `useEffect` + `useRef` + `scrollIntoView`. Shows a breathing-dot streaming indicator when `isStreaming` is true.

**Step 1: Create ConversationThread**

```typescript
// frontend/src/components/conversation/ConversationThread.tsx

import { useEffect, useRef } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { MessageBubble } from './MessageBubble';

export function ConversationThread() {
  const messages = useConversationStore((s) => s.messages);
  const isStreaming = useConversationStore((s) => s.isStreaming);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or streaming starts
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isStreaming]);

  return (
    <div
      className="flex-1 overflow-y-auto px-6 py-4 space-y-4"
      data-aria-id="conversation-thread"
    >
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full opacity-60">
          <div className="w-12 h-12 rounded-full bg-[var(--accent-muted)] flex items-center justify-center mb-4">
            <div className="w-3 h-3 rounded-full bg-accent aria-pulse-dot" />
          </div>
          <p className="font-display italic text-lg text-[var(--text-primary)]">ARIA</p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">Your AI colleague is ready</p>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {/* Streaming indicator */}
      {isStreaming && (
        <div className="flex justify-start" data-aria-id="streaming-indicator">
          <div className="border-l-2 border-accent pl-4 py-2">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:0ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:150ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/ConversationThread.tsx
git commit -m "feat: add ConversationThread with auto-scroll and streaming indicator"
```

---

### Task 6: InputBar Component

**Files:**
- Create: `frontend/src/components/conversation/InputBar.tsx`

**Context:** Uses `lucide-react` for Mic and Send icons. The component sends messages via a callback prop (the parent wires this to WebSocketManager). Input value is stored in `useConversationStore.inputValue`. The gradient glow uses `box-shadow` with accent color. The "SPACE TO TALK" badge is a visual hint (not functional yet — voice is a future task).

**Step 1: Create InputBar**

```typescript
// frontend/src/components/conversation/InputBar.tsx

import { useCallback, type FormEvent, type KeyboardEvent } from 'react';
import { Mic, Send } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';

interface InputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, disabled = false }: InputBarProps) {
  const inputValue = useConversationStore((s) => s.inputValue);
  const setInputValue = useConversationStore((s) => s.setInputValue);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  const canSend = inputValue.trim().length > 0 && !disabled && !isStreaming;

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      if (!canSend) return;
      onSend(inputValue.trim());
      setInputValue('');
    },
    [canSend, inputValue, onSend, setInputValue],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div
      className="relative px-6 pb-4 pt-2"
      data-aria-id="input-bar"
    >
      {/* Gradient glow behind the bar */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'linear-gradient(to top, rgba(46,102,255,0.06) 0%, transparent 100%)',
        }}
      />

      <form
        onSubmit={handleSubmit}
        className="relative flex items-end gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2"
        style={{
          boxShadow: '0 -8px 40px rgba(46,102,255,0.08), 0 0 0 1px rgba(46,102,255,0.05)',
        }}
      >
        {/* Mic button */}
        <button
          type="button"
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
          aria-label="Voice input"
        >
          <Mic size={18} />
        </button>

        {/* Text input */}
        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask ARIA anything..."
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none min-h-[36px] max-h-[120px] py-1.5"
          style={{ fontFamily: 'var(--font-sans)' }}
          data-aria-id="message-input"
        />

        {/* Space-to-talk badge */}
        <div className="flex-shrink-0 hidden sm:flex items-center">
          <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)] opacity-50 mr-2 select-none">
            Space to talk
          </span>
        </div>

        {/* Send button */}
        <button
          type="submit"
          disabled={!canSend}
          className="flex-shrink-0 p-2 rounded-lg bg-accent text-white transition-all hover:bg-[var(--accent-hover)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Send message"
          data-aria-id="send-button"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/InputBar.tsx
git commit -m "feat: add InputBar with gradient glow, mic button, and space-to-talk"
```

---

### Task 7: SuggestionChips Component

**Files:**
- Create: `frontend/src/components/conversation/SuggestionChips.tsx`

**Context:** Reads `currentSuggestions` from the conversation store. Renders as outlined pills. Clicking a chip calls the parent's `onSend` callback with the chip text. Uses `framer-motion` for entrance animation (already installed, `framer-motion@^11.18.2`).

**Step 1: Create SuggestionChips**

```typescript
// frontend/src/components/conversation/SuggestionChips.tsx

import { motion, AnimatePresence } from 'framer-motion';
import { useConversationStore } from '@/stores/conversationStore';

interface SuggestionChipsProps {
  onSelect: (suggestion: string) => void;
}

export function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  const suggestions = useConversationStore((s) => s.currentSuggestions);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  if (suggestions.length === 0 || isStreaming) return null;

  return (
    <div className="px-6 pb-3" data-aria-id="suggestion-chips">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-1.5 h-1.5 rounded-full bg-accent aria-pulse-dot" />
        <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)]">
          ARIA is listening&nbsp;&nbsp;&bull;&nbsp;&nbsp;{suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''} available
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <AnimatePresence>
          {suggestions.map((suggestion, i) => (
            <motion.button
              key={suggestion}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ delay: i * 0.05, duration: 0.2 }}
              onClick={() => onSelect(suggestion)}
              className="px-3 py-1.5 rounded-full border border-[var(--border)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] hover:bg-[var(--accent-muted)] transition-all"
            >
              {suggestion}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/SuggestionChips.tsx
git commit -m "feat: add SuggestionChips with animated entrance and store integration"
```

---

### Task 8: Conversation Components Index

**Files:**
- Create: `frontend/src/components/conversation/index.ts`

**Context:** Barrel export file following the pattern in `frontend/src/components/pages/index.ts`.

**Step 1: Create index**

```typescript
// frontend/src/components/conversation/index.ts

export { ConversationThread } from './ConversationThread';
export { MessageBubble } from './MessageBubble';
export { InputBar } from './InputBar';
export { SuggestionChips } from './SuggestionChips';
```

**Step 2: Commit**

```bash
git add frontend/src/components/conversation/index.ts
git commit -m "feat: add conversation components barrel export"
```

---

### Task 9: ARIAWorkspace Page (Wire Everything Together)

**Files:**
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx` (full rewrite)

**Context:** This is the default route (`/`). The `AppShell.tsx` already hides the IntelPanel on `/`. The `ThemeContext.tsx` already applies dark theme on `/`. The page needs to:
1. Connect to WebSocketManager on mount using `userId` from `AuthContext` and `sessionId` from `SessionContext`
2. Listen for `aria.message`, `aria.thinking`, `aria.token`, and `aria.metadata` events
3. Wire `InputBar.onSend` to add user message to store + send via WebSocketManager
4. Wire `SuggestionChips.onSelect` the same way

**Step 1: Rewrite ARIAWorkspace**

Replace the entire contents of `frontend/src/components/pages/ARIAWorkspace.tsx` with:

```typescript
// frontend/src/components/pages/ARIAWorkspace.tsx

import { useEffect, useCallback, useRef } from 'react';
import { ConversationThread } from '@/components/conversation/ConversationThread';
import { InputBar } from '@/components/conversation/InputBar';
import { SuggestionChips } from '@/components/conversation/SuggestionChips';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload } from '@/types/chat';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';

export function ARIAWorkspace() {
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);

  const { session } = useSession();
  const { user } = useAuth();

  // Track the streaming message ID across event handlers
  const streamingIdRef = useRef<string | null>(null);

  // ── Connect WebSocket on mount ──────────────────────────
  useEffect(() => {
    if (!user?.id || !session?.id) return;

    wsManager.connect(user.id, session.id);

    return () => {
      wsManager.disconnect();
    };
  }, [user?.id, session?.id]);

  // ── Wire up event listeners ─────────────────────────────
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      setStreaming(false);

      // If we were streaming, update the existing message with final metadata
      if (streamingIdRef.current) {
        // Replace streaming content with final content
        const store = useConversationStore.getState();
        const existing = store.messages.find((m) => m.id === streamingIdRef.current);
        if (existing) {
          updateMessageMetadata(streamingIdRef.current, {
            rich_content: data.rich_content || [],
            ui_commands: data.ui_commands || [],
            suggestions: data.suggestions || [],
          });
        }
        streamingIdRef.current = null;
        return;
      }

      // Non-streaming: add the complete message
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
      if (data.is_thinking) {
        setStreaming(true);
      }
    };

    const handleToken = (payload: unknown) => {
      const data = payload as { content: string; full_content: string };

      // Create the streaming message placeholder if it doesn't exist
      if (!streamingIdRef.current) {
        const id = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
        streamingIdRef.current = id;
        const store = useConversationStore.getState();
        store.addMessage({
          role: 'aria',
          content: data.content,
          rich_content: [],
          ui_commands: [],
          suggestions: [],
          isStreaming: true,
        });
        // Get the actual ID that was assigned
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
        rich_content: Array<{ type: string; data: Record<string, unknown> }>;
        ui_commands: Array<{ action: string; route?: string; element?: string; content?: Record<string, unknown> }>;
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

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
    };
  }, [
    addMessage,
    appendToMessage,
    updateMessageMetadata,
    setStreaming,
    setCurrentSuggestions,
    activeConversationId,
    setActiveConversation,
  ]);

  // ── Send message handler ────────────────────────────────
  const handleSend = useCallback(
    (message: string) => {
      // Add user message to store
      addMessage({
        role: 'user',
        content: message,
        rich_content: [],
        ui_commands: [],
        suggestions: [],
      });

      // Send via WebSocket/SSE
      wsManager.send(WS_EVENTS.USER_MESSAGE, {
        message,
        conversation_id: activeConversationId,
      });
    },
    [addMessage, activeConversationId],
  );

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0A0A0B' }}
      data-aria-id="aria-workspace"
    >
      <ConversationThread />
      <SuggestionChips onSelect={handleSend} />
      <InputBar onSend={handleSend} />
    </div>
  );
}
```

**Step 2: Check for useAuth hook**

The `useAuth` hook should exist at `frontend/src/hooks/useAuth.ts`. If it doesn't, check `frontend/src/contexts/AuthContext.tsx` — the auth context exports an `AuthContext` but may not have a `useAuth` convenience hook. If missing, create a minimal one:

```typescript
// frontend/src/hooks/useAuth.ts (only if it doesn't already exist)
import { useContext } from 'react';
import { AuthContext, type AuthContextType } from '@/contexts/AuthContext';

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
```

**Step 3: Verify it compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -40`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/pages/ARIAWorkspace.tsx frontend/src/hooks/useAuth.ts
git commit -m "feat: wire ARIA Workspace with WebSocket events, conversation store, and UI"
```

---

### Task 10: Verify Full Build

**Files:** None (verification only)

**Step 1: Run TypeScript check**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty`
Expected: Clean (0 errors)

**Step 2: Run linter**

Run: `cd /Users/dhruv/aria/frontend && npm run lint 2>&1 | tail -20`
Expected: No new errors introduced

**Step 3: Run dev server**

Run: `cd /Users/dhruv/aria/frontend && npm run dev`
Expected: Vite starts successfully, no build errors. Visit http://localhost:5173/ — should see the ARIA Workspace with:
- Dark background (#0A0A0B)
- Centered "ARIA" heading with pulsing dot (empty state)
- Input bar at bottom with mic button, text field, and send button
- Gradient glow behind the input bar
- Typing a message and pressing Enter should add user message to thread

**Step 4: Commit any lint fixes**

If linting required changes, commit them:
```bash
git add -A
git commit -m "fix: resolve lint warnings in conversation components"
```
