# Chat ↔ Video Switching Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable seamless switching between text chat, voice, and video surfaces with full context preservation.

**Architecture:** Extend existing InputBar and DialogueHeader with modality controls. Add VideoSessionSummaryCard as a new rich content type rendered by RichContentRenderer. Add ChatContextSection to TranscriptPanel. Replace ConversationThread empty state with WelcomeCTAs.

**Tech Stack:** React 18, TypeScript, Zustand, Tailwind CSS, lucide-react icons, existing ModalityController + ContextBridgeService.

---

### Task 1: Add VideoSessionSummary type definition

**Files:**
- Modify: `frontend/src/types/chat.ts`

**Step 1: Add the type**

Add after the `WSEnvelope` interface (line 80):

```typescript
// === Video Session Summary ===

export interface VideoSessionSummaryData {
  session_id: string;
  duration_seconds: number;
  is_audio_only: boolean;
  summary: string;
  topics: string[];
  action_items: Array<{
    text: string;
    is_tracked: boolean;
  }>;
  transcript_entries: Array<{
    speaker: 'aria' | 'user';
    text: string;
    timestamp: string;
  }>;
}
```

**Step 2: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to `VideoSessionSummaryData`

**Step 3: Commit**

```bash
git add frontend/src/types/chat.ts
git commit -m "feat: add VideoSessionSummaryData type definition"
```

---

### Task 2: Create VideoSessionSummaryCard component

**Files:**
- Create: `frontend/src/components/rich/VideoSessionSummaryCard.tsx`
- Modify: `frontend/src/components/rich/RichContentRenderer.tsx`
- Modify: `frontend/src/components/rich/index.ts`

**Step 1: Create the card component**

Create `frontend/src/components/rich/VideoSessionSummaryCard.tsx`:

```tsx
import { useState } from 'react';
import { Video, Phone, ChevronDown, ChevronUp, CheckCircle2, Clock } from 'lucide-react';
import type { VideoSessionSummaryData } from '@/types/chat';

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  if (mins < 1) return '<1 min';
  return `${mins} min`;
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function VideoSessionSummaryCard({ data }: { data: VideoSessionSummaryData }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = data.is_audio_only ? Phone : Video;
  const label = data.is_audio_only ? 'Voice Call' : 'Video Session';
  const topicCount = data.topics.length;
  const actionCount = data.action_items.length;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="video-session-summary"
    >
      {/* Collapsed header — always visible */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[rgba(46,102,255,0.04)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#2E66FF]/10 flex items-center justify-center flex-shrink-0">
            <Icon size={16} className="text-[#2E66FF]" />
          </div>
          <div>
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {label}
            </span>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="flex items-center gap-1 font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                <Clock size={10} />
                {formatDuration(data.duration_seconds)}
              </span>
              {topicCount > 0 && (
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {topicCount} topic{topicCount !== 1 ? 's' : ''}
                </span>
              )}
              {actionCount > 0 && (
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {actionCount} action item{actionCount !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </div>

        {expanded ? (
          <ChevronUp size={16} className="text-[var(--text-secondary)]" />
        ) : (
          <ChevronDown size={16} className="text-[var(--text-secondary)]" />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[var(--border)] px-4 py-3 space-y-4">
          {/* Action items */}
          {data.action_items.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Action Items
              </h4>
              <ul className="space-y-1.5">
                {data.action_items.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2
                      size={14}
                      className="mt-0.5 flex-shrink-0"
                      style={{ color: item.is_tracked ? '#2E66FF' : 'var(--text-secondary)' }}
                    />
                    <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                      {item.text}
                    </span>
                    {item.is_tracked && (
                      <span className="ml-auto flex-shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#2E66FF]/10 text-[#2E66FF]">
                        Tracked
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Topics */}
          {data.topics.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Topics Discussed
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {data.topics.map((topic, i) => (
                  <span
                    key={i}
                    className="text-[11px] px-2 py-0.5 rounded-full border border-[var(--border)]"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Transcript */}
          {data.transcript_entries.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Transcript
              </h4>
              <div
                className="max-h-[300px] overflow-y-auto space-y-2 rounded-lg p-3"
                style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}
              >
                {data.transcript_entries.map((entry, i) => (
                  <div key={i} className="flex gap-2 text-xs">
                    <span className="font-mono text-[10px] flex-shrink-0 mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {formatTimestamp(entry.timestamp)}
                    </span>
                    <span className="font-semibold flex-shrink-0" style={{ color: entry.speaker === 'aria' ? '#2E66FF' : 'var(--text-primary)' }}>
                      {entry.speaker === 'aria' ? 'ARIA' : 'You'}:
                    </span>
                    <span style={{ color: 'var(--text-primary)' }}>{entry.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Watch recording — future */}
          <div className="pt-1">
            <span className="text-[11px] italic" style={{ color: 'var(--text-secondary)' }}>
              Watch recording (coming soon)
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Register in RichContentRenderer**

In `frontend/src/components/rich/RichContentRenderer.tsx`:

Add import at top (after existing imports, around line 16):
```typescript
import { VideoSessionSummaryCard } from './VideoSessionSummaryCard';
import type { VideoSessionSummaryData } from '@/types/chat';
```

Add case in `RichContentItem` switch (before the `default:` case, around line 116):
```typescript
    case 'video_session_summary':
      return <VideoSessionSummaryCard data={item.data as unknown as VideoSessionSummaryData} />;
```

**Step 3: Export from index**

In `frontend/src/components/rich/index.ts`, add:
```typescript
export { VideoSessionSummaryCard } from './VideoSessionSummaryCard';
```

**Step 4: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to VideoSessionSummaryCard

**Step 5: Commit**

```bash
git add frontend/src/components/rich/VideoSessionSummaryCard.tsx frontend/src/components/rich/RichContentRenderer.tsx frontend/src/components/rich/index.ts
git commit -m "feat: add VideoSessionSummaryCard rich content component"
```

---

### Task 3: Add video call button to InputBar

**Files:**
- Modify: `frontend/src/components/conversation/InputBar.tsx`

**Step 1: Add video call button**

In `frontend/src/components/conversation/InputBar.tsx`:

Add `Video` to the lucide-react import (line 3):
```typescript
import { Send, Phone, Video } from 'lucide-react';
```

Add import for modalityStore (after line 7):
```typescript
import { useModalityStore } from '@/stores/modalityStore';
```

Inside the component function, after the `handleAudioCall` callback (line 54), add:
```typescript
  const handleVideoCall = useCallback(() => {
    modalityController.switchTo('avatar', 'chat');
  }, []);

  const tavusStatus = useModalityStore((s) => s.tavusSession.status);
  const hasActiveSession = tavusStatus === 'active' || tavusStatus === 'connecting';
```

After the Phone button (line 96), add a Video button:
```tsx
        <button
          type="button"
          onClick={handleVideoCall}
          disabled={hasActiveSession}
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] transition-colors hover:text-[#2E66FF] hover:bg-[rgba(46,102,255,0.1)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Video call ARIA"
          data-aria-id="video-call-button"
          title={hasActiveSession ? 'Already in a call' : 'Video call'}
        >
          <Video size={16} />
        </button>
```

Also update the existing Phone button to be disabled when there's an active session. Replace the Phone button (lines 87-96) with:
```tsx
        <button
          type="button"
          onClick={handleAudioCall}
          disabled={hasActiveSession}
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] transition-colors hover:text-[#2E66FF] hover:bg-[rgba(46,102,255,0.1)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Call ARIA (audio only)"
          data-aria-id="audio-call-button"
          title={hasActiveSession ? 'Already in a call' : 'Call ARIA'}
        >
          <Phone size={16} />
        </button>
```

**Step 2: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/InputBar.tsx
git commit -m "feat: add video call button and disable state to InputBar"
```

---

### Task 4: Add switchToChat to ModalityController and "Switch to Chat" button in DialogueHeader

**Files:**
- Modify: `frontend/src/core/ModalityController.ts`
- Modify: `frontend/src/components/avatar/DialogueHeader.tsx`

**Step 1: Add switchToChat method to ModalityController**

In `frontend/src/core/ModalityController.ts`, add a new method after `endSession()` (after line 84):

```typescript
  /**
   * Switch from video/audio back to text chat.
   *
   * Unlike endSession(), this calls the context bridge endpoint first
   * to persist the transcript and extract a summary before ending the
   * Tavus session and navigating to /.
   */
  async switchToChat(): Promise<void> {
    const store = useModalityStore.getState();
    const sessionId = store.tavusSession.id;

    if (sessionId) {
      store.setTavusSession({ status: 'ending' });

      // Fire context bridge before tearing down — this persists the
      // transcript and posts a video_session_summary via WebSocket.
      try {
        await apiClient.post(`/video/sessions/${sessionId}/bridge-to-chat`);
      } catch (err) {
        console.warn('[ModalityController] Context bridge call failed:', err);
      }

      try {
        await apiClient.post(`/video/sessions/${sessionId}/end`);
      } catch (err) {
        console.warn('[ModalityController] Failed to end Tavus session:', err);
      }
    }

    store.clearTavusSession();
    store.setActiveModality('text');
    store.setIsSpeaking(false);
    this.navigateFn?.('/');
  }
```

**Step 2: Add "Switch to Chat" button to DialogueHeader**

In `frontend/src/components/avatar/DialogueHeader.tsx`:

Update the lucide-react import (line 1):
```typescript
import { Video, VideoOff, MessageSquare } from 'lucide-react';
```

Replace the end-session button block (lines 38-46) with both buttons:
```tsx
      {(isActive || tavusSession.status === 'connecting') && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => modalityController.switchToChat()}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-[#2E66FF] hover:bg-[#2E66FF]/10 transition-colors"
            title="Switch to Chat"
          >
            <MessageSquare size={14} />
            <span className="text-xs">Chat</span>
          </button>
          <button
            onClick={() => modalityController.endSession()}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-red-400 hover:bg-red-400/10 transition-colors"
          >
            <VideoOff size={14} />
            <span className="text-xs">End Session</span>
          </button>
        </div>
      )}
```

**Step 3: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

**Step 4: Commit**

```bash
git add frontend/src/core/ModalityController.ts frontend/src/components/avatar/DialogueHeader.tsx
git commit -m "feat: add switchToChat with context bridge and chat button in DialogueHeader"
```

---

### Task 5: Create ChatContextSection for TranscriptPanel

**Files:**
- Create: `frontend/src/components/avatar/ChatContextSection.tsx`
- Modify: `frontend/src/components/avatar/TranscriptPanel.tsx`
- Modify: `frontend/src/components/avatar/index.ts`

**Step 1: Create ChatContextSection**

Create `frontend/src/components/avatar/ChatContextSection.tsx`:

```tsx
import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, MessageSquare } from 'lucide-react';
import type { Message } from '@/types/chat';

interface ChatContextSectionProps {
  messages: Message[];
}

export function ChatContextSection({ messages }: ChatContextSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const autoCollapsedRef = useRef(false);

  // Auto-collapse after 10 seconds
  useEffect(() => {
    if (autoCollapsedRef.current) return;
    const timer = setTimeout(() => {
      autoCollapsedRef.current = true;
      setExpanded(false);
    }, 10_000);
    return () => clearTimeout(timer);
  }, []);

  if (messages.length === 0) return null;

  return (
    <div
      className="border-b border-[#1A1A2E]"
      style={{ backgroundColor: 'rgba(255,255,255,0.03)' }}
      data-aria-id="chat-context-section"
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-2.5 text-left hover:bg-[rgba(255,255,255,0.02)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-[#2E66FF]" />
          <span className="text-xs font-medium text-[#F8FAFC]">
            Continuing from chat
          </span>
          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#1A1A2E] text-[#8B8FA3]">
            {messages.length} message{messages.length !== 1 ? 's' : ''}
          </span>
        </div>
        {expanded ? (
          <ChevronUp size={14} className="text-[#8B8FA3]" />
        ) : (
          <ChevronDown size={14} className="text-[#8B8FA3]" />
        )}
      </button>

      {expanded && (
        <div className="px-6 pb-3 space-y-1.5">
          {messages.map((msg) => (
            <ChatContextMessage key={msg.id} message={msg} />
          ))}
        </div>
      )}
    </div>
  );
}

function ChatContextMessage({ message }: { message: Message }) {
  const [showFull, setShowFull] = useState(false);
  const isLong = message.content.length > 120;
  const displayText = isLong && !showFull
    ? message.content.slice(0, 120) + '...'
    : message.content;

  return (
    <div
      className="flex gap-2 text-xs cursor-pointer"
      onClick={() => isLong && setShowFull((v) => !v)}
    >
      <span
        className="font-semibold flex-shrink-0"
        style={{
          color: message.role === 'aria' ? '#2E66FF' : '#8B8FA3',
        }}
      >
        {message.role === 'aria' ? 'ARIA' : 'You'}:
      </span>
      <span className="text-[#C0C4D0] leading-relaxed">{displayText}</span>
    </div>
  );
}
```

**Step 2: Mount ChatContextSection in TranscriptPanel**

In `frontend/src/components/avatar/TranscriptPanel.tsx`:

Add imports (after line 12):
```typescript
import { ChatContextSection } from './ChatContextSection';
import { useModalityStore } from '@/stores/modalityStore';
import { useConversationStore } from '@/stores/conversationStore';
import { useMemo } from 'react';
```

Update the existing `useEffect` and `useRef` import (line 9) — `useMemo` is now needed:
```typescript
import { useEffect, useRef, useMemo } from 'react';
```

Wait — `useEffect` and `useRef` are already imported on line 9. Just add `useMemo` there:
```typescript
import { useEffect, useRef, useMemo } from 'react';
```

Remove the duplicate standalone `useMemo` import if it was added separately.

Inside the `TranscriptPanel` component, before the `return` statement (around line 33), add:
```typescript
  // Load chat context when video started from an active conversation
  const conversationId = useModalityStore((s) => s.tavusSession.id);
  const allMessages = useConversationStore((s) => s.messages);
  const chatContextMessages = useMemo(() => {
    // Show last 8 messages that existed before video started
    // (messages already in store when TranscriptPanel mounts)
    return allMessages.slice(-8);
  }, []); // Empty deps: capture messages at mount time only
```

Inside the JSX, after the header div (after line 61), before the transcript messages div, add:
```tsx
      {/* Chat context from linked conversation */}
      {chatContextMessages.length > 0 && (
        <ChatContextSection messages={chatContextMessages} />
      )}
```

**Step 3: Export from index**

In `frontend/src/components/avatar/index.ts`, add:
```typescript
export { ChatContextSection } from './ChatContextSection';
```

**Step 4: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

**Step 5: Commit**

```bash
git add frontend/src/components/avatar/ChatContextSection.tsx frontend/src/components/avatar/TranscriptPanel.tsx frontend/src/components/avatar/index.ts
git commit -m "feat: add ChatContextSection showing recent chat in DialogueMode"
```

---

### Task 6: Create WelcomeCTAs and integrate into ARIAWorkspace

**Files:**
- Create: `frontend/src/components/conversation/WelcomeCTAs.tsx`
- Modify: `frontend/src/components/pages/ARIAWorkspace.tsx`
- Modify: `frontend/src/components/conversation/ConversationThread.tsx`

**Step 1: Create WelcomeCTAs component**

Create `frontend/src/components/conversation/WelcomeCTAs.tsx`:

```tsx
import { Video, Phone, MessageSquare } from 'lucide-react';
import { modalityController } from '@/core/ModalityController';
import { useAuth } from '@/hooks/useAuth';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

interface WelcomeCTAsProps {
  onStartTyping: () => void;
}

interface CTAButtonProps {
  icon: React.ReactNode;
  label: string;
  subtitle: string;
  onClick: () => void;
}

function CTAButton({ icon, label, subtitle, onClick }: CTAButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-2 w-[140px] px-4 py-5 rounded-xl border border-[#1A1A2E] bg-[#111318] hover:border-[#2E66FF]/30 hover:bg-[#111318]/80 transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-[#2E66FF]/5"
    >
      <div className="w-10 h-10 rounded-lg bg-[#2E66FF]/10 flex items-center justify-center">
        {icon}
      </div>
      <span className="text-sm font-medium text-[#F8FAFC]">{label}</span>
      <span className="text-[11px] text-[#8B8FA3]">{subtitle}</span>
    </button>
  );
}

export function WelcomeCTAs({ onStartTyping }: WelcomeCTAsProps) {
  const { user } = useAuth();
  const firstName = user?.user_metadata?.first_name || user?.email?.split('@')[0] || 'there';
  const greeting = getGreeting();

  return (
    <div
      className="flex flex-col items-center justify-center h-full"
      data-aria-id="welcome-ctas"
    >
      {/* Avatar */}
      <div className="w-20 h-20 rounded-full overflow-hidden mb-5 border-2 border-[#2E66FF]/20" style={{ boxShadow: '0 0 30px rgba(46,102,255,0.15)' }}>
        <img
          src="/aria-avatar.png"
          alt="ARIA"
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      </div>

      {/* Greeting */}
      <h1
        className="text-2xl text-[#F8FAFC] mb-1"
        style={{ fontFamily: "'Instrument Serif', Georgia, serif", fontStyle: 'italic' }}
      >
        {greeting}, {firstName}
      </h1>
      <p className="text-sm text-[#8B8FA3] mb-8 max-w-[320px] text-center">
        I've been reviewing your pipeline overnight. How would you like to connect?
      </p>

      {/* CTA buttons */}
      <div className="flex items-center gap-4">
        <CTAButton
          icon={<Video size={20} className="text-[#2E66FF]" />}
          label="Morning Briefing"
          subtitle="Video walkthrough"
          onClick={() => modalityController.switchTo('avatar', 'briefing')}
        />
        <CTAButton
          icon={<Phone size={20} className="text-[#2E66FF]" />}
          label="Quick Question"
          subtitle="Voice call"
          onClick={() => modalityController.switchToAudioCall('chat')}
        />
        <CTAButton
          icon={<MessageSquare size={20} className="text-[#2E66FF]" />}
          label="Type a message"
          subtitle="Text chat"
          onClick={onStartTyping}
        />
      </div>
    </div>
  );
}
```

**Step 2: Replace EmptyState in ConversationThread**

In `frontend/src/components/conversation/ConversationThread.tsx`:

Add import (after line 8):
```typescript
import { WelcomeCTAs } from './WelcomeCTAs';
```

Add a prop to ConversationThread for the typing callback. Update the component signature (line 40):
```typescript
interface ConversationThreadProps {
  onStartTyping?: () => void;
}

export function ConversationThread({ onStartTyping }: ConversationThreadProps = {}) {
```

Replace the empty state block (lines 80-90) with:
```typescript
  if (messages.length === 0) {
    return (
      <div
        className={`flex-1 overflow-y-auto px-6 py-4 relative ${isStreaming ? 'aria-arrival-sweep' : ''}`}
        data-aria-id="conversation-thread"
      >
        <UnreadIndicator />
        {onStartTyping ? <WelcomeCTAs onStartTyping={onStartTyping} /> : <EmptyState />}
      </div>
    );
  }
```

**Step 3: Wire onStartTyping in ARIAWorkspace**

In `frontend/src/components/pages/ARIAWorkspace.tsx`:

Add a ref for the input focus (after line 37, near `streamingIdRef`):
```typescript
  const inputRef = useRef<HTMLTextAreaElement>(null);
```

Add a callback for starting typing (after `handleSend`, around line 281):
```typescript
  const handleStartTyping = useCallback(() => {
    // Focus the input bar textarea
    const textarea = document.querySelector('[data-aria-id="message-input"]') as HTMLTextAreaElement | null;
    textarea?.focus();
  }, []);
```

Pass `onStartTyping` to ConversationThread (line 381):
```tsx
      <ConversationThread onStartTyping={handleStartTyping} />
```

**Step 4: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

**Step 5: Commit**

```bash
git add frontend/src/components/conversation/WelcomeCTAs.tsx frontend/src/components/conversation/ConversationThread.tsx frontend/src/components/pages/ARIAWorkspace.tsx
git commit -m "feat: add WelcomeCTAs with modality quick-start buttons in empty state"
```

---

### Task 7: Add backend bridge-to-chat endpoint

**Files:**
- Modify: `backend/src/api/routes/video.py` (find the video routes file)

**Context:** The `switchToChat()` method in ModalityController calls `POST /video/sessions/{id}/bridge-to-chat`. This endpoint needs to invoke `ContextBridgeService.video_to_chat_context()`. Check the existing video routes file to find where `/video/sessions/{session_id}/end` is defined, and add the bridge endpoint nearby.

**Step 1: Find the video routes file**

Search for the file containing the video session end endpoint. It should be in `backend/src/api/routes/video.py` or similar.

**Step 2: Add the bridge endpoint**

Add a new route after the end session endpoint:

```python
@router.post("/sessions/{session_id}/bridge-to-chat")
async def bridge_to_chat(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Transfer video session context back to the linked chat conversation.

    Persists transcript, extracts action items, and posts a summary
    message via WebSocket for real-time delivery to the frontend.
    """
    from src.services.context_bridge import ContextBridgeService

    bridge = ContextBridgeService()
    result = await bridge.video_to_chat_context(
        user_id=current_user["id"],
        video_session_id=session_id,
    )
    return result
```

**Step 3: Verify the backend starts**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.api.routes.video import router; print('OK')"`
Expected: OK (no import errors)

**Step 4: Commit**

```bash
git add backend/src/api/routes/video.py
git commit -m "feat: add bridge-to-chat endpoint for video→chat context transfer"
```

---

### Task 8: Pass conversation_id when creating video sessions from chat

**Files:**
- Modify: `frontend/src/core/ModalityController.ts`

**Context:** When switching from chat to video, the active conversation_id needs to be sent to the backend so it can link the video session to the chat conversation. This enables the context bridge to work in both directions.

**Step 1: Import conversationStore**

At the top of `frontend/src/core/ModalityController.ts`, add (after line 12):
```typescript
import { useConversationStore } from '@/stores/conversationStore';
```

**Step 2: Pass conversation_id in switchToAudioCall**

In the `switchToAudioCall` method, update the API call (around line 128-131) to include conversation_id:

```typescript
      const conversationId = useConversationStore.getState().activeConversationId;
      const response = await apiClient.post<TavusCreateResponse>('/video/sessions', {
        session_type: type,
        audio_only: true,
        ...(conversationId && { conversation_id: conversationId }),
      });
```

**Step 3: Pass conversation_id in switchToAvatar**

In the `switchToAvatar` method, update the API call (around line 168-170) to include conversation_id:

```typescript
      const conversationId = useConversationStore.getState().activeConversationId;
      const response = await apiClient.post<TavusCreateResponse>('/video/sessions', {
        session_type: sessionType,
        ...(conversationId && { conversation_id: conversationId }),
      });
```

**Step 4: Verify types compile**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

**Step 5: Commit**

```bash
git add frontend/src/core/ModalityController.ts
git commit -m "feat: pass conversation_id when creating video sessions from chat"
```

---

### Task 9: Final verification

**Step 1: Full type check**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | tail -20`
Expected: No new errors introduced by our changes

**Step 2: Lint check**

Run: `cd /Users/dhruv/aria/frontend && npx eslint src/components/rich/VideoSessionSummaryCard.tsx src/components/avatar/ChatContextSection.tsx src/components/conversation/WelcomeCTAs.tsx src/core/ModalityController.ts src/components/conversation/InputBar.tsx src/components/avatar/DialogueHeader.tsx src/components/avatar/TranscriptPanel.tsx src/components/conversation/ConversationThread.tsx src/components/pages/ARIAWorkspace.tsx --max-warnings 50 2>&1 | tail -20`
Expected: No blocking errors

**Step 3: Build check**

Run: `cd /Users/dhruv/aria/frontend && npm run build 2>&1 | tail -20`
Expected: Build succeeds

**Step 4: Commit any lint fixes**

If lint or type errors were found, fix them and commit:
```bash
git add -u
git commit -m "fix: resolve lint and type issues in chat-video switching"
```
