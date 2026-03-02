# Thesys C1 Message Rendering Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire C1Component into ARIA's message rendering pipeline with dual-mode support (C1 when enabled, markdown fallback).

**Architecture:** Create C1MessageRenderer wrapper component that handles ARIA-specific action routing. Modify MessageBubble to conditionally render C1 or markdown based on message.render_mode and Thesys enabled status. Update conversation store types and WebSocket handlers to pass through render_mode and c1_response fields from backend.

**Tech Stack:** React 18, TypeScript, @thesysai/genui-sdk, Zustand, React Router

---

## Task 1: Update Message Type Definition

**Files:**
- Modify: `frontend/src/types/chat.ts:11-20`

**Step 1: Add render_mode and c1_response fields to Message interface**

```typescript
// In frontend/src/types/chat.ts, update the Message interface:

export interface Message {
  id: string;
  role: 'aria' | 'user' | 'system';
  content: string;
  rich_content: RichContent[];
  ui_commands: UICommand[];
  suggestions: string[];
  timestamp: string;
  isStreaming?: boolean;
  render_mode?: 'c1' | 'markdown';  // NEW: determines which renderer to use
  c1_response?: string | null;       // NEW: the C1 visualized content (JSON string)
}
```

**Step 2: Update AriaMessagePayload to include new fields**

```typescript
// In frontend/src/types/chat.ts, update AriaMessagePayload:

export interface AriaMessagePayload {
  message: string;
  rich_content?: RichContent[];
  ui_commands?: UICommand[];
  suggestions?: string[];
  conversation_id?: string;
  message_id?: string;
  avatar_script?: string;
  voice_emotion?: 'neutral' | 'excited' | 'concerned' | 'warm';
  render_mode?: 'c1' | 'markdown';  // NEW
  c1_response?: string | null;       // NEW
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/chat.ts
git commit -m "feat(types): add render_mode and c1_response to Message type"
```

---

## Task 2: Create C1MessageRenderer Component

**Files:**
- Create: `frontend/src/components/conversation/C1MessageRenderer.tsx`

**Step 1: Create the C1MessageRenderer component**

```typescript
// frontend/src/components/conversation/C1MessageRenderer.tsx

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { C1Component } from '@thesysai/genui-sdk';
import { approveGoalPlan, startGoal } from '@/api/goals';
import { approveDraft, dismissDraft, sendDraft } from '@/api/drafts';
import { markSignalRead } from '@/api/signals';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

interface C1MessageRendererProps {
  c1Response: string;
  isStreaming: boolean;
  onSendMessage: (message: string) => void;
}

/**
 * C1MessageRenderer - Wraps C1Component with ARIA-specific action routing.
 *
 * Handles custom actions from C1-generated UI and maps them to
 * existing ARIA backend endpoints and WebSocket events.
 */
export function C1MessageRenderer({
  c1Response,
  isStreaming,
  onSendMessage,
}: C1MessageRendererProps) {
  const navigate = useNavigate();

  const handleAction = useCallback(
    async (event: { type: string; params: Record<string, unknown> }) => {
      try {
        switch (event.type) {
          // --- Goal Actions ---
          case 'approve_goal':
          case 'approve_plan': {
            const goalId = event.params.goal_id as string;
            await approveGoalPlan(goalId);
            // Navigate to goal detail to show execution starting
            navigate(`/goals/${goalId}`);
            break;
          }

          case 'modify_goal':
          case 'modify_plan': {
            const goalId = event.params.goal_id as string;
            // Navigate to goal edit or send modification message
            onSendMessage(`I'd like to modify the plan for goal ${goalId}`);
            break;
          }

          case 'start_goal': {
            const goalId = event.params.goal_id as string;
            await startGoal(goalId);
            navigate(`/goals/${goalId}`);
            break;
          }

          // --- Email Actions ---
          case 'approve_email':
          case 'send_email': {
            const draftId = event.params.email_draft_id as string;
            await sendDraft(draftId);
            break;
          }

          case 'edit_email': {
            const draftId = event.params.email_draft_id as string;
            // Navigate to email editor or open modal
            onSendMessage(`I'd like to edit email draft ${draftId}`);
            break;
          }

          case 'dismiss_email': {
            const draftId = event.params.email_draft_id as string;
            await dismissDraft(draftId);
            break;
          }

          case 'save_to_client': {
            const draftId = event.params.email_draft_id as string;
            // TODO: Implement save-to-client endpoint call
            console.log('[C1MessageRenderer] save_to_client for draft:', draftId);
            break;
          }

          // --- Signal Actions ---
          case 'investigate_signal': {
            const signalId = event.params.signal_id as string;
            const signalType = event.params.signal_type as string | undefined;
            await markSignalRead(signalId);
            // Navigate to signals page filtered by this signal
            navigate(`/intelligence/signals?highlight=${signalId}`);
            break;
          }

          case 'dismiss_signal': {
            const signalId = event.params.signal_id as string;
            await markSignalRead(signalId);
            break;
          }

          // --- Navigation Actions ---
          case 'view_lead_detail': {
            const leadId = event.params.lead_id as string;
            navigate(`/pipeline/leads/${leadId}`);
            break;
          }

          case 'view_battle_card': {
            const competitorId = event.params.competitor_id as string;
            navigate(`/intelligence/battle-cards/${competitorId}`);
            break;
          }

          case 'view_goal_detail': {
            const goalId = event.params.goal_id as string;
            navigate(`/goals/${goalId}`);
            break;
          }

          // --- Task Actions ---
          case 'execute_task': {
            const taskId = event.params.task_id as string;
            // TODO: Implement task execution endpoint
            console.log('[C1MessageRenderer] execute_task:', taskId);
            wsManager.send('task.execute', { task_id: taskId });
            break;
          }

          // --- C1 Built-in Actions ---
          case 'open_url': {
            const url = event.params.url as string;
            window.open(url, '_blank', 'noopener,noreferrer');
            break;
          }

          case 'continue_conversation':
          default: {
            // Extract LLM-friendly message for follow-up
            const { llmFriendlyMessage, humanFriendlyMessage } = event.params as {
              llmFriendlyMessage?: string;
              humanFriendlyMessage?: string;
            };
            const message = llmFriendlyMessage || humanFriendlyMessage || '';
            if (message) {
              onSendMessage(message);
            }
            break;
          }
        }
      } catch (error) {
        console.error('[C1MessageRenderer] Action failed:', event.type, error);
        // Could emit an error event or show a toast notification
      }
    },
    [navigate, onSendMessage]
  );

  // Fallback: if c1Response is empty, return null (parent will use markdown)
  if (!c1Response || c1Response.trim() === '') {
    return null;
  }

  return (
    <div className="c1-component-wrapper">
      <C1Component
        c1Response={c1Response}
        isStreaming={isStreaming}
        onAction={handleAction}
      />
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/conversation/C1MessageRenderer.tsx
git commit -m "feat(conversation): create C1MessageRenderer with ARIA action routing"
```

---

## Task 3: Update Conversation Store for C1 Fields

**Files:**
- Modify: `frontend/src/stores/conversationStore.ts:28-35`

**Step 1: Update updateMessageMetadata to accept render_mode and c1_response**

```typescript
// In frontend/src/stores/conversationStore.ts, update the metadata type:

updateMessageMetadata: (
  id: string,
  metadata: {
    rich_content?: RichContent[];
    ui_commands?: UICommand[];
    suggestions?: string[];
    render_mode?: 'c1' | 'markdown';  // NEW
    c1_response?: string | null;       // NEW
  },
) => void;
```

**Step 2: Update the implementation to pass through new fields**

```typescript
// In the store implementation, update the updateMessageMetadata action:

updateMessageMetadata: (id, metadata) =>
  set((state) => ({
    messages: state.messages.map((msg) =>
      msg.id === id
        ? {
            ...msg,
            rich_content: metadata.rich_content ?? msg.rich_content,
            ui_commands: metadata.ui_commands ?? msg.ui_commands,
            suggestions: metadata.suggestions ?? msg.suggestions,
            render_mode: metadata.render_mode ?? msg.render_mode,
            c1_response: metadata.c1_response ?? msg.c1_response,
            isStreaming: false,
          }
        : msg,
    ),
    currentSuggestions: metadata.suggestions?.length
      ? metadata.suggestions
      : state.currentSuggestions,
  })),
```

**Step 3: Commit**

```bash
git add frontend/src/stores/conversationStore.ts
git commit -m "feat(store): add render_mode and c1_response to message metadata"
```

---

## Task 4: Update ARIAWorkspace WebSocket Handlers

**Files:**
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx:160-189`

**Step 1: Update handleAriaMessage to pass render_mode and c1_response**

```typescript
// In ARIAWorkspace.tsx, update the handleAriaMessage function:

const handleAriaMessage = (payload: unknown) => {
  const data = (payload ?? {}) as Partial<AriaMessagePayload>;
  setStreaming(false);

  if (streamingIdRef.current) {
    updateMessageMetadata(streamingIdRef.current, {
      rich_content: data.rich_content ?? [],
      ui_commands: data.ui_commands ?? [],
      suggestions: data.suggestions ?? [],
      render_mode: data.render_mode ?? 'markdown',  // NEW
      c1_response: data.c1_response ?? null,         // NEW
    });
    streamingIdRef.current = null;
    return;
  }

  addMessage({
    role: 'aria',
    content: data.message ?? '',
    rich_content: data.rich_content ?? [],
    ui_commands: data.ui_commands ?? [],
    suggestions: data.suggestions ?? [],
    render_mode: data.render_mode ?? 'markdown',  // NEW
    c1_response: data.c1_response ?? null,         // NEW
  });

  if (data.suggestions?.length) {
    setCurrentSuggestions(data.suggestions);
  }

  if (data.conversation_id && !activeConversationId) {
    setActiveConversation(data.conversation_id);
  }
};
```

**Step 2: Update handleMetadata to include render_mode and c1_response**

```typescript
// In ARIAWorkspace.tsx, update the handleMetadata function:

const handleMetadata = (payload: unknown) => {
  const data = (payload ?? {}) as Partial<{
    message_id: string;
    rich_content: RichContent[];
    ui_commands: UICommand[];
    suggestions: string[];
    render_mode: 'c1' | 'markdown';  // NEW
    c1_response: string | null;       // NEW
  }>;

  if (streamingIdRef.current) {
    updateMessageMetadata(streamingIdRef.current, {
      rich_content: data.rich_content ?? [],
      ui_commands: data.ui_commands ?? [],
      suggestions: data.suggestions ?? [],
      render_mode: data.render_mode,    // NEW
      c1_response: data.c1_response,    // NEW
    });
  }
};
```

**Step 3: Commit**

```bash
git add frontend/src/components/pages/ARIAWorkspace.tsx
git commit -m "feat(workspace): pass render_mode and c1_response from WebSocket events"
```

---

## Task 5: Modify MessageBubble for Dual Rendering

**Files:**
- Modify: `frontend/src/components/conversation/MessageBubble.tsx`

**Step 1: Add imports for Thesys context and C1MessageRenderer**

```typescript
// At the top of MessageBubble.tsx, add imports:

import { memo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { useNavigate } from 'react-router-dom';
import type { Message } from '@/types/chat';
import { MessageAvatar } from './MessageAvatar';
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';
import { SpeakButton } from './SpeakButton';
import { useMessageSpeech } from '@/hooks/useMessageSpeech';
import { useThesys } from '@/contexts/ThesysContext';  // NEW
import { C1MessageRenderer } from './C1MessageRenderer';  // NEW
import { useConversationStore } from '@/stores/conversationStore';  // NEW
import { wsManager } from '@/core/WebSocketManager';  // NEW
import { WS_EVENTS } from '@/types/chat';  // NEW
```

**Step 2: Add navigate hook at the start of the component**

```typescript
// Inside MessageBubble component, add navigate:

export const MessageBubble = memo(function MessageBubble({ message, isFirstInGroup = true }: MessageBubbleProps) {
  const isAria = message.role === 'aria';
  const navigate = useNavigate();  // NEW
  const { enabled: thesysEnabled } = useThesys();  // NEW
  const addMessage = useConversationStore((s) => s.addMessage);  // NEW

  // ... existing speech hooks ...
```

**Step 3: Add helper function to handle sending messages from C1 actions**

```typescript
// Add inside MessageBubble component, after the hooks:

const handleSendMessage = useCallback((msg: string) => {
  // Add user message to store
  addMessage({
    role: 'user',
    content: msg,
    rich_content: [],
    ui_commands: [],
    suggestions: [],
  });

  // Send via WebSocket
  const activeConversationId = useConversationStore.getState().activeConversationId;

  wsManager.send(WS_EVENTS.USER_MESSAGE, {
    message: msg,
    conversation_id: activeConversationId,
  });
}, [addMessage]);
```

**Step 4: Replace the ARIA message rendering section with dual-mode logic**

```typescript
// Replace the ARIA rendering block (lines 85-130) with:

if (isAria) {
  // Check if we should render with C1
  const shouldUseC1 =
    thesysEnabled &&
    message.render_mode === 'c1' &&
    message.c1_response &&
    message.c1_response.trim() !== '';

  return (
    <div
      className={`group flex items-start gap-3 justify-start ${
        message.isStreaming
          ? 'aria-message-streaming'
          : 'motion-safe:animate-[slideInLeft_200ms_ease-out] aria-message-settle'
      }`}
      data-aria-id="message-aria"
      data-message-id={message.id}
    >
      <MessageAvatar role="aria" visible={isFirstInGroup} />

      <div className="relative max-w-[85%] border-l-2 border-accent pl-4 py-2">
        {shouldUseC1 ? (
          // C1 rendering mode
          <C1MessageRenderer
            c1Response={message.c1_response!}
            isStreaming={message.isStreaming || false}
            onSendMessage={handleSendMessage}
          />
        ) : (
          // Markdown rendering mode (fallback)
          <div className="prose-aria">
            <ReactMarkdown
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Rich content renders after main content in both modes */}
        {message.rich_content.length > 0 && (
          <RichContentRenderer items={message.rich_content} />
        )}

        {/* Message actions: speak button + timestamp */}
        <div className="flex items-center gap-2 mt-1">
          <SpeakButton
            text={message.content}
            isSpeaking={isSpeaking}
            isPaused={isPaused}
            onSpeak={(text) => speakMessage(message.id, text)}
            onStop={stopSpeaking}
            onResume={togglePause}
            isSupported={isTTSSupported && !message.isStreaming}
          />
        </div>

        {/* Hover timestamp tooltip */}
        <span className="absolute -bottom-5 left-4 hidden group-hover:block font-mono text-[11px] text-[#555770] bg-[#111318] px-2 py-1 rounded whitespace-nowrap z-10">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
```

**Step 5: Commit**

```bash
git add frontend/src/components/conversation/MessageBubble.tsx
git commit -m "feat(message-bubble): add dual C1/markdown rendering based on render_mode"
```

---

## Task 6: Update WebSocketManager SSE Fallback for C1 Fields

**Files:**
- Modify: `frontend/src/core/WebSocketManager.ts:297-324`

**Step 1: Update SSE event handling to include render_mode and c1_response**

```typescript
// In WebSocketManager.ts sendViaRest method, update the complete event handling:

} else if (event.type === 'complete') {
  if (event.rich_content || event.ui_commands || event.suggestions || event.render_mode) {
    this.emit('aria.metadata', {
      message_id: messageId,
      rich_content: event.rich_content || [],
      ui_commands: event.ui_commands || [],
      suggestions: event.suggestions || [],
      render_mode: event.render_mode || 'markdown',  // NEW
      c1_response: event.c1_response || null,         // NEW
    });
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/core/WebSocketManager.ts
git commit -m "feat(websocket): pass render_mode and c1_response in SSE fallback"
```

---

## Task 7: Add Barrel Export for C1MessageRenderer

**Files:**
- Modify: `frontend/src/components/conversation/index.ts`

**Step 1: Export C1MessageRenderer from conversation index**

```typescript
// In frontend/src/components/conversation/index.ts, add:

export { C1MessageRenderer } from './C1MessageRenderer';
```

**Step 2: Commit**

```bash
git add frontend/src/components/conversation/index.ts
git commit -m "feat(conversation): export C1MessageRenderer from barrel"
```

---

## Task 8: Manual Verification Checklist

**Files:**
- No file changes - manual testing

**Step 1: Verify render mode switching**

1. Start the frontend dev server: `cd frontend && npm run dev`
2. Ensure `VITE_THESYS_ENABLED=true` in `.env`
3. Send a message to ARIA that triggers a C1 response (goal proposal, email draft, etc.)
4. Verify C1Component renders the response
5. Toggle `VITE_THESYS_ENABLED=false` and restart
6. Verify the same message type falls back to markdown rendering

**Step 2: Verify action handlers**

1. Trigger a goal proposal from ARIA
2. Click the "Approve" button in the C1-rendered card
3. Verify the approve API is called and navigation occurs
4. Trigger an email draft from ARIA
5. Click "Send" button
6. Verify the sendDraft API is called

**Step 3: Verify streaming behavior**

1. Send a message that triggers a long C1 response
2. Verify `isStreaming` prop is passed correctly
3. Verify streaming animation is shown

**Step 4: Verify fallback edge cases**

1. Send a message with `render_mode: "c1"` but empty `c1_response`
2. Verify markdown fallback is used
3. Verify no blank/empty C1Component is rendered

---

## Summary

This plan implements C1 message rendering in ARIA's conversation pipeline with:

1. **Type Safety**: Updated Message interface with `render_mode` and `c1_response`
2. **Dual Rendering**: MessageBubble conditionally renders C1 or markdown
3. **Action Routing**: C1MessageRenderer maps C1 actions to ARIA API calls
4. **WebSocket Integration**: aria.message and aria.metadata events include C1 fields
5. **SSE Fallback**: REST streaming also passes C1 fields
6. **Feature Flag Gating**: `useThesys()` hook ensures C1 only renders when enabled

**Key Design Decisions:**
- C1 is ONLY for ARIA responses (role === 'aria'), never user messages
- Markdown is ALWAYS the fallback if C1 is disabled or c1_response is empty
- Rich content renders AFTER the C1/markdown content (same as before)
- TTS button uses markdown content (message.content) regardless of render mode
- Navigation actions use React Router's navigate() for SPA routing
- API calls use existing functions from goals.ts, drafts.ts, signals.ts

**Files Modified:**
- `frontend/src/types/chat.ts` - Type definitions
- `frontend/src/stores/conversationStore.ts` - Store actions
- `frontend/src/components/conversation/MessageBubble.tsx` - Dual rendering
- `frontend/src/components/conversation/C1MessageRenderer.tsx` - NEW component
- `frontend/src/components/conversation/index.ts` - Barrel export
- `frontend/src/components/pages/ARIAWorkspace.tsx` - WebSocket handlers
- `frontend/src/core/WebSocketManager.ts` - SSE fallback
