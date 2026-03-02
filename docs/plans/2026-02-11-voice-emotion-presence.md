# Voice Input, Raven-0 Emotion Detection & Presence Animations

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire space-to-talk voice input, Raven-0 emotion perception, and presence polish across ARIA's frontend and backend.

**Architecture:** Three independent feature tracks that share the modality store. Voice input uses the Web SpeechRecognition API with a global keyboard listener (Space key when textarea unfocused) plus mic-click toggle. Raven-0 listens for `emotion.detected` WebSocket events and posts to a new backend perception endpoint. Presence animations are CSS-only additions wired to existing streaming state.

**Tech Stack:** React 18, Zustand, Framer Motion, Web SpeechRecognition API, FastAPI, Supabase, Tailwind CSS

---

## Task 1: Add `isListening` state to modality store

**Files:**
- Modify: `frontend/src/stores/modalityStore.ts` (add 2 fields)

**Step 1: Add `isListening` and `setIsListening` to store**

In `frontend/src/stores/modalityStore.ts`, add to the `ModalityState` interface and initial state:

```typescript
// Add to ModalityState interface (after isSpeaking line ~36):
isListening: boolean;
setIsListening: (isListening: boolean) => void;

// Add to create() initial state (after isSpeaking: false line ~55):
isListening: false,

// Add to create() actions (after setIsSpeaking line ~74):
setIsListening: (isListening) => set({ isListening }),
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/stores/modalityStore.ts
git commit -m "feat: add isListening state to modality store for voice input"
```

---

## Task 2: Create `useVoiceInput` hook

**Files:**
- Create: `frontend/src/hooks/useVoiceInput.ts`

**Step 1: Create the hook**

Create `frontend/src/hooks/useVoiceInput.ts`:

```typescript
/**
 * useVoiceInput — Space-to-talk and mic-click voice input
 *
 * Uses the Web SpeechRecognition API. Space key activates when textarea
 * is NOT focused (so typing works). Mic click toggles listen on/off.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useModalityStore } from '@/stores/modalityStore';
import { useConversationStore } from '@/stores/conversationStore';

// SpeechRecognition type shim for browsers
type SpeechRecognitionType = typeof window extends { SpeechRecognition: infer T } ? T : never;

function getSpeechRecognition(): SpeechRecognitionType | null {
  const w = window as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as SpeechRecognitionType | null;
}

interface UseVoiceInputOptions {
  onTranscript: (text: string) => void;
}

export function useVoiceInput({ onTranscript }: UseVoiceInputOptions) {
  const isListening = useModalityStore((s) => s.isListening);
  const setIsListening = useModalityStore((s) => s.setIsListening);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  const recognitionRef = useRef<InstanceType<SpeechRecognitionType> | null>(null);
  const isSpaceHeldRef = useRef(false);
  const transcriptRef = useRef('');

  const isSupported = typeof window !== 'undefined' && getSpeechRecognition() !== null;

  const startListening = useCallback(() => {
    if (!isSupported || isStreaming || isListening) return;

    const SpeechRecognition = getSpeechRecognition()!;
    const recognition = new (SpeechRecognition as unknown as new () => SpeechRecognitionInstance)();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    transcriptRef.current = '';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let transcript = '';
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      transcriptRef.current = transcript;
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error !== 'aborted') {
        console.warn('SpeechRecognition error:', event.error);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      // If still marked as listening, it ended unexpectedly — don't send
      if (useModalityStore.getState().isListening) {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
      setIsListening(true);
    } catch {
      // Already started or mic blocked
      setIsListening(false);
    }
  }, [isSupported, isStreaming, isListening, setIsListening]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Already stopped
      }
      recognitionRef.current = null;
    }

    setIsListening(false);

    const transcript = transcriptRef.current.trim();
    if (transcript) {
      onTranscript(transcript);
    }
    transcriptRef.current = '';
  }, [onTranscript, setIsListening]);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Global Space key listener (push-to-talk)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      if (isSpaceHeldRef.current) return;

      // Don't activate if typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement)?.contentEditable === 'true') return;

      e.preventDefault();
      isSpaceHeldRef.current = true;
      startListening();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      if (!isSpaceHeldRef.current) return;

      isSpaceHeldRef.current = false;
      stopListening();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [startListening, stopListening]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch { /* noop */ }
      }
    };
  }, []);

  return {
    isListening,
    isSupported,
    toggleListening,
    startListening,
    stopListening,
  };
}

// Type helpers for SpeechRecognition (not in all TS libs)
interface SpeechRecognitionInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  [index: number]: { transcript: string; confidence: number };
  isFinal: boolean;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useVoiceInput.ts
git commit -m "feat: create useVoiceInput hook with space-to-talk and mic toggle"
```

---

## Task 3: Create `VoiceIndicator` component

**Files:**
- Create: `frontend/src/components/conversation/VoiceIndicator.tsx`

**Step 1: Create the component**

Create `frontend/src/components/conversation/VoiceIndicator.tsx`:

```typescript
/**
 * VoiceIndicator — Shows listening state in the input bar.
 *
 * Idle: mic icon + "SPACE TO TALK" label
 * Listening: pulsing mic + waveform bars + "LISTENING..." label
 */

import { motion, AnimatePresence } from 'framer-motion';
import { Mic } from 'lucide-react';

interface VoiceIndicatorProps {
  isListening: boolean;
  isSupported: boolean;
  onToggle: () => void;
}

export function VoiceIndicator({ isListening, isSupported, onToggle }: VoiceIndicatorProps) {
  if (!isSupported) return null;

  return (
    <div className="flex items-center gap-2" data-aria-id="voice-indicator">
      <button
        type="button"
        onClick={onToggle}
        className={`
          flex-shrink-0 p-2 rounded-lg transition-all
          ${isListening
            ? 'text-accent bg-[var(--accent-muted)] shadow-[0_0_12px_rgba(46,102,255,0.3)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
          }
        `}
        aria-label={isListening ? 'Stop listening' : 'Start voice input'}
      >
        <Mic size={18} />
      </button>

      <AnimatePresence mode="wait">
        {isListening ? (
          <motion.div
            key="listening"
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{ opacity: 0, width: 0 }}
            className="flex items-center gap-2 overflow-hidden"
          >
            {/* Compact waveform */}
            <div className="flex items-center gap-[2px] h-4">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="w-[3px] bg-accent rounded-full"
                  style={{
                    animation: `waveform 0.6s ease-in-out ${i * 0.1}s infinite`,
                    height: '100%',
                  }}
                />
              ))}
            </div>

            <span className="font-mono text-[9px] tracking-widest uppercase text-accent whitespace-nowrap select-none">
              Listening...
            </span>
          </motion.div>
        ) : (
          <motion.span
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="hidden sm:block font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)] opacity-50 select-none whitespace-nowrap"
          >
            Space to talk
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/conversation/VoiceIndicator.tsx
git commit -m "feat: create VoiceIndicator component with listening state animation"
```

---

## Task 4: Wire voice input into InputBar

**Files:**
- Modify: `frontend/src/components/conversation/InputBar.tsx`

**Step 1: Replace static mic button with VoiceIndicator**

Replace the entire content of `InputBar.tsx` with:

```typescript
import { useCallback } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { Send } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { VoiceIndicator } from './VoiceIndicator';

interface InputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function InputBar({ onSend, disabled = false, placeholder = 'Ask ARIA anything...' }: InputBarProps) {
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

  const { isListening, isSupported, toggleListening } = useVoiceInput({
    onTranscript: (text) => {
      onSend(text);
    },
  });

  return (
    <div className="relative px-6 pb-4 pt-2" data-aria-id="input-bar">
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
          boxShadow: isListening
            ? '0 0 20px rgba(46,102,255,0.15), 0 0 0 1px rgba(46,102,255,0.2)'
            : '0 -8px 40px rgba(46,102,255,0.08), 0 0 0 1px rgba(46,102,255,0.05)',
          transition: 'box-shadow 0.3s ease',
        }}
      >
        <VoiceIndicator
          isListening={isListening}
          isSupported={isSupported}
          onToggle={toggleListening}
        />

        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isListening ? 'Listening...' : placeholder}
          rows={1}
          disabled={disabled || isListening}
          className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none min-h-[36px] max-h-[120px] py-1.5"
          style={{ fontFamily: 'var(--font-sans)' }}
          data-aria-id="message-input"
        />

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

Key changes:
- Removed the static `Mic` button and "Space to talk" span
- Added `useVoiceInput` hook wired to `onSend`
- Added `VoiceIndicator` component
- Input bar box-shadow glows brighter when listening
- Textarea disabled and shows "Listening..." placeholder when voice active

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Verify visually**

Run: `cd frontend && npm run dev`
- Open browser, verify InputBar renders with mic icon and "SPACE TO TALK" label
- Click mic icon → should show waveform + "LISTENING..."
- Press Space outside textarea → should activate listening
- Release Space → should stop and send transcript

**Step 4: Commit**

```bash
git add frontend/src/components/conversation/InputBar.tsx
git commit -m "feat: wire voice input into InputBar with VoiceIndicator"
```

---

## Task 5: Create perception store and emotion detection hook

**Files:**
- Create: `frontend/src/stores/perceptionStore.ts`
- Create: `frontend/src/hooks/useEmotionDetection.ts`

**Step 1: Create the perception store**

Create `frontend/src/stores/perceptionStore.ts`:

```typescript
/**
 * Perception Store — Tracks Raven-0 emotion detection state
 *
 * Stores the latest detected emotion and a rolling history for
 * engagement pattern analysis. Fed by useEmotionDetection hook.
 */

import { create } from 'zustand';

export type DetectedEmotion =
  | 'neutral'
  | 'engaged'
  | 'frustrated'
  | 'confused'
  | 'excited'
  | 'distracted'
  | 'focused';

export interface EmotionReading {
  emotion: DetectedEmotion;
  confidence: number;
  timestamp: string;
}

export interface PerceptionState {
  // State
  currentEmotion: EmotionReading | null;
  emotionHistory: EmotionReading[];
  engagementLevel: 'high' | 'medium' | 'low' | 'unknown';

  // Actions
  setCurrentEmotion: (reading: EmotionReading) => void;
  setEngagementLevel: (level: PerceptionState['engagementLevel']) => void;
  clearPerception: () => void;
}

const MAX_HISTORY = 20;

export const usePerceptionStore = create<PerceptionState>((set) => ({
  currentEmotion: null,
  emotionHistory: [],
  engagementLevel: 'unknown',

  setCurrentEmotion: (reading) =>
    set((state) => {
      const history = [...state.emotionHistory, reading].slice(-MAX_HISTORY);

      // Derive engagement from recent readings
      const recent = history.slice(-5);
      const engagedCount = recent.filter(
        (r) => r.emotion === 'engaged' || r.emotion === 'focused' || r.emotion === 'excited',
      ).length;

      let engagementLevel: PerceptionState['engagementLevel'] = 'unknown';
      if (recent.length >= 3) {
        if (engagedCount >= 4) engagementLevel = 'high';
        else if (engagedCount >= 2) engagementLevel = 'medium';
        else engagementLevel = 'low';
      }

      return {
        currentEmotion: reading,
        emotionHistory: history,
        engagementLevel,
      };
    }),

  setEngagementLevel: (level) => set({ engagementLevel: level }),

  clearPerception: () =>
    set({
      currentEmotion: null,
      emotionHistory: [],
      engagementLevel: 'unknown',
    }),
}));
```

**Step 2: Create the emotion detection hook**

Create `frontend/src/hooks/useEmotionDetection.ts`:

```typescript
/**
 * useEmotionDetection — Listens for Raven-0 emotion events
 *
 * Receives emotion.detected events from WebSocket (sent by Tavus
 * Raven-0 via the backend) and posts them to the perception API.
 * Updates the perceptionStore for UI consumption.
 */

import { useEffect, useRef } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { usePerceptionStore, type DetectedEmotion, type EmotionReading } from '@/stores/perceptionStore';

interface EmotionEventPayload {
  emotion: string;
  confidence: number;
  timestamp?: string;
}

const DEBOUNCE_MS = 2000; // Don't flood backend — max 1 emotion event per 2s

export function useEmotionDetection() {
  const setCurrentEmotion = usePerceptionStore((s) => s.setCurrentEmotion);
  const lastSentRef = useRef(0);

  useEffect(() => {
    const handleEmotion = (payload: unknown) => {
      const data = payload as EmotionEventPayload;
      const now = Date.now();

      const reading: EmotionReading = {
        emotion: data.emotion as DetectedEmotion,
        confidence: data.confidence,
        timestamp: data.timestamp ?? new Date().toISOString(),
      };

      // Update local store immediately
      setCurrentEmotion(reading);

      // Debounce backend calls
      if (now - lastSentRef.current < DEBOUNCE_MS) return;
      lastSentRef.current = now;

      // Fire-and-forget POST to perception endpoint
      fetch('/api/v1/perception/emotion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          emotion: reading.emotion,
          confidence: reading.confidence,
          timestamp: reading.timestamp,
        }),
      }).catch(() => {
        // Swallow — perception is non-critical
      });
    };

    wsManager.on(WS_EVENTS.EMOTION_DETECTED, handleEmotion);

    return () => {
      wsManager.off(WS_EVENTS.EMOTION_DETECTED, handleEmotion);
    };
  }, [setCurrentEmotion]);
}
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 4: Commit**

```bash
git add frontend/src/stores/perceptionStore.ts frontend/src/hooks/useEmotionDetection.ts
git commit -m "feat: add perception store and emotion detection hook for Raven-0"
```

---

## Task 6: Create `EmotionIndicator` component

**Files:**
- Create: `frontend/src/components/shell/EmotionIndicator.tsx`

**Step 1: Create the component**

Create `frontend/src/components/shell/EmotionIndicator.tsx`:

```typescript
/**
 * EmotionIndicator — Subtle perception readout in ARIA workspace
 *
 * Shows the current detected emotion as a minimal text indicator.
 * Designed to be noticed by observant investors without cluttering the UI.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { usePerceptionStore } from '@/stores/perceptionStore';

const EMOTION_LABELS: Record<string, string> = {
  neutral: 'Neutral',
  engaged: 'Engaged',
  frustrated: 'Needs attention',
  confused: 'Processing',
  excited: 'Energized',
  distracted: 'Distracted',
  focused: 'Deep focus',
};

const ENGAGEMENT_COLORS: Record<string, string> = {
  high: 'var(--success)',
  medium: 'var(--accent)',
  low: 'var(--warning)',
  unknown: 'var(--text-secondary)',
};

export function EmotionIndicator() {
  const currentEmotion = usePerceptionStore((s) => s.currentEmotion);
  const engagementLevel = usePerceptionStore((s) => s.engagementLevel);

  if (!currentEmotion) return null;

  const label = EMOTION_LABELS[currentEmotion.emotion] ?? currentEmotion.emotion;
  const color = ENGAGEMENT_COLORS[engagementLevel];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.3 }}
        className="flex items-center gap-1.5"
        data-aria-id="emotion-indicator"
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span
          className="font-mono text-[9px] tracking-widest uppercase select-none"
          style={{ color }}
        >
          {label}
        </span>
        {currentEmotion.confidence > 0.8 && (
          <span className="font-mono text-[8px] text-[var(--text-secondary)] opacity-40">
            {Math.round(currentEmotion.confidence * 100)}%
          </span>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/shell/EmotionIndicator.tsx
git commit -m "feat: create EmotionIndicator for subtle Raven-0 perception display"
```

---

## Task 7: Create backend perception route

**Files:**
- Create: `backend/src/api/routes/perception.py`
- Modify: `backend/src/main.py` (register router)

**Step 1: Create the perception route**

Create `backend/src/api/routes/perception.py`:

```python
"""Perception API routes for Raven-0 emotion detection and engagement tracking."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/perception", tags=["perception"])


class EmotionEvent(BaseModel):
    """A single emotion detection event from Raven-0."""

    emotion: str = Field(
        ...,
        description="Detected emotion label (neutral, engaged, frustrated, etc.)",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Detection confidence score"
    )
    timestamp: str | None = Field(
        default=None, description="ISO timestamp of the detection"
    )


class EmotionResponse(BaseModel):
    """Response after processing an emotion event."""

    stored: bool
    engagement_hint: str | None = None


class EngagementSummary(BaseModel):
    """Summary of user engagement patterns."""

    engagement_level: str
    dominant_emotion: str | None = None
    reading_count: int = 0
    period_start: str | None = None
    period_end: str | None = None


@router.post("/emotion", response_model=EmotionResponse)
async def record_emotion(
    current_user: CurrentUser,
    event: EmotionEvent,
) -> EmotionResponse:
    """Record a Raven-0 emotion detection event.

    Stores the reading in procedural_patterns for long-term engagement
    analysis. Returns an optional hint the frontend can use to adjust
    ARIA's response style.

    Args:
        current_user: The authenticated user.
        event: The emotion detection event.

    Returns:
        Storage confirmation and optional engagement hint.
    """
    now = event.timestamp or datetime.now(UTC).isoformat()

    db = get_supabase_client()

    try:
        db.table("procedural_patterns").insert(
            {
                "user_id": current_user.id,
                "pattern_type": "emotion_detection",
                "pattern_data": {
                    "emotion": event.emotion,
                    "confidence": event.confidence,
                    "source": "raven_0",
                },
                "created_at": now,
            }
        ).execute()
    except Exception:
        logger.exception(
            "Failed to store emotion event",
            extra={"user_id": current_user.id, "emotion": event.emotion},
        )
        return EmotionResponse(stored=False)

    # Generate engagement hint based on emotion
    engagement_hint = None
    if event.emotion in ("frustrated", "confused"):
        engagement_hint = "concise"  # ARIA should be more direct
    elif event.emotion in ("excited", "engaged"):
        engagement_hint = "elaborate"  # ARIA can go deeper
    elif event.emotion == "distracted":
        engagement_hint = "re-engage"  # ARIA should grab attention

    logger.info(
        "Emotion recorded",
        extra={
            "user_id": current_user.id,
            "emotion": event.emotion,
            "confidence": event.confidence,
            "hint": engagement_hint,
        },
    )

    return EmotionResponse(stored=True, engagement_hint=engagement_hint)


@router.get("/engagement", response_model=EngagementSummary)
async def get_engagement_summary(
    current_user: CurrentUser,
) -> EngagementSummary:
    """Get a summary of the user's recent engagement patterns.

    Aggregates the last 20 emotion readings to determine overall
    engagement level.

    Args:
        current_user: The authenticated user.

    Returns:
        Engagement summary with dominant emotion and level.
    """
    db = get_supabase_client()

    try:
        result = (
            db.table("procedural_patterns")
            .select("pattern_data, created_at")
            .eq("user_id", current_user.id)
            .eq("pattern_type", "emotion_detection")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to fetch engagement data",
            extra={"user_id": current_user.id},
        )
        return EngagementSummary(engagement_level="unknown")

    if not result.data:
        return EngagementSummary(engagement_level="unknown", reading_count=0)

    readings = result.data
    emotions = [r["pattern_data"]["emotion"] for r in readings]

    # Count engaged-type emotions
    engaged_emotions = {"engaged", "focused", "excited"}
    engaged_count = sum(1 for e in emotions if e in engaged_emotions)

    if len(emotions) < 3:
        level = "unknown"
    elif engaged_count / len(emotions) >= 0.7:
        level = "high"
    elif engaged_count / len(emotions) >= 0.4:
        level = "medium"
    else:
        level = "low"

    # Most common emotion
    from collections import Counter

    emotion_counts = Counter(emotions)
    dominant = emotion_counts.most_common(1)[0][0] if emotion_counts else None

    return EngagementSummary(
        engagement_level=level,
        dominant_emotion=dominant,
        reading_count=len(readings),
        period_start=readings[-1]["created_at"] if readings else None,
        period_end=readings[0]["created_at"] if readings else None,
    )
```

**Step 2: Register the router in main.py**

In `backend/src/main.py`:
- Add to imports (after line 44, `predictions`): `perception,`
- Add router registration (after line 182, predictions): `app.include_router(perception.router, prefix="/api/v1")`

**Step 3: Verify backend starts**

Run: `cd backend && python -c "from src.api.routes import perception; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/api/routes/perception.py backend/src/main.py
git commit -m "feat: add perception API routes for Raven-0 emotion detection"
```

---

## Task 8: Add presence animations — sidebar breathing glow

**Files:**
- Modify: `frontend/src/components/shell/Sidebar.tsx` (logo section, lines 211-221)
- Modify: `frontend/src/index.css` (add aria-logo-glow animation)

**Step 1: Add CSS for the logo glow**

Add to `frontend/src/index.css` before the `@media (prefers-reduced-motion)` block (before line 367):

```css
/* === ARIA Logo Presence — breathing glow on sidebar logo === */

.aria-logo-glow {
  text-shadow:
    0 0 20px rgba(46, 102, 255, 0.15),
    0 0 40px rgba(46, 102, 255, 0.08);
  animation: aria-logo-breathe 4s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes aria-logo-breathe {
  0%, 100% {
    text-shadow:
      0 0 20px rgba(46, 102, 255, 0.08),
      0 0 40px rgba(46, 102, 255, 0.04);
  }
  50% {
    text-shadow:
      0 0 24px rgba(46, 102, 255, 0.2),
      0 0 48px rgba(46, 102, 255, 0.1);
  }
}
```

Also add `.aria-logo-glow` to the reduced-motion block (with the other disabled animations).

**Step 2: Apply glow class to sidebar ARIA logo**

In `frontend/src/components/shell/Sidebar.tsx`, update the logo `<span>` (line 213):

Change:
```tsx
<span
  className="text-xl tracking-tight text-[#E8E6E1] italic"
  style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
>
```

To:
```tsx
<span
  className={`text-xl tracking-tight text-[#E8E6E1] italic ${isARIAActive ? 'aria-logo-glow' : ''}`}
  style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
>
```

**Step 3: Verify visually**

Run: `cd frontend && npm run dev`
Check the sidebar — the "ARIA" text should have a subtle breathing blue glow.

**Step 4: Commit**

```bash
git add frontend/src/index.css frontend/src/components/shell/Sidebar.tsx
git commit -m "feat: add breathing glow presence animation to sidebar ARIA logo"
```

---

## Task 9: Add presence animations — arrival sweep and chunk fade

**Files:**
- Modify: `frontend/src/index.css` (add 2 new animations)
- Modify: `frontend/src/components/conversation/ConversationThread.tsx` (arrival sweep)
- Modify: `frontend/src/components/conversation/MessageBubble.tsx` (settle effect)

**Step 1: Add CSS animations**

Add to `frontend/src/index.css` (before the reduced-motion block):

```css
/* === ARIA Arrival — light sweep when ARIA starts responding === */

@keyframes aria-arrival-sweep {
  0% {
    opacity: 0;
    transform: translateX(-100%);
  }
  30% {
    opacity: 0.6;
  }
  100% {
    opacity: 0;
    transform: translateX(100%);
  }
}

.aria-arrival-sweep::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(46, 102, 255, 0.06) 40%,
    rgba(46, 102, 255, 0.12) 50%,
    rgba(46, 102, 255, 0.06) 60%,
    transparent 100%
  );
  animation: aria-arrival-sweep 0.8s ease-out forwards;
  pointer-events: none;
  z-index: 0;
}

/* === Streaming chunk fade-in === */

@keyframes chunk-fade-in {
  from {
    opacity: 0.4;
  }
  to {
    opacity: 1;
  }
}

.aria-message-streaming .prose-aria > *:last-child {
  animation: chunk-fade-in 0.15s ease-out;
}

/* === ARIA Message Settle — micro-ease when response completes === */

.aria-message-settle {
  animation: aria-settle 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
```

Also add `.aria-arrival-sweep::before, .aria-message-settle` to the reduced-motion block.

**Step 2: Add arrival sweep to ConversationThread**

In `frontend/src/components/conversation/ConversationThread.tsx`, update the container `<div>`:

Change the outermost div (line 38):
```tsx
<div
  className="flex-1 overflow-y-auto px-6 py-4 space-y-4"
  data-aria-id="conversation-thread"
>
```

To:
```tsx
<div
  className={`flex-1 overflow-y-auto px-6 py-4 space-y-4 relative ${isStreaming ? 'aria-arrival-sweep' : ''}`}
  data-aria-id="conversation-thread"
>
```

Note: `isStreaming` is already imported from the store on line 29.

**Step 3: Add settle and streaming class to MessageBubble**

In `frontend/src/components/conversation/MessageBubble.tsx`:

1. Add `isStreaming` to the `Message` type check. The ARIA message container div (line 21) should add classes based on message state:

Change the ARIA message outer div (line 21):
```tsx
<div
  className="group flex items-start gap-3 justify-start motion-safe:animate-[slideInLeft_200ms_ease-out]"
```

To:
```tsx
<div
  className={`group flex items-start gap-3 justify-start ${
    message.isStreaming
      ? 'aria-message-streaming'
      : 'motion-safe:animate-[slideInLeft_200ms_ease-out] aria-message-settle'
  }`}
```

This means:
- While streaming: apply `aria-message-streaming` (chunk fade-in on last child)
- When complete: apply the entrance slide + settle micro-ease

**Step 4: Verify visually**

Run: `cd frontend && npm run dev`
- Send a message — when ARIA starts responding, you should see a subtle blue light sweep
- The streaming text should fade in slightly per chunk
- When response completes, the message settles with a micro-ease

**Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/components/conversation/ConversationThread.tsx frontend/src/components/conversation/MessageBubble.tsx
git commit -m "feat: add arrival sweep, chunk fade-in, and settle presence animations"
```

---

## Task 10: Wire EmotionIndicator and useEmotionDetection into the app

**Files:**
- Modify: `frontend/src/components/avatar/DialogueMode.tsx` (add emotion hook + indicator)
- Modify: `frontend/src/components/avatar/DialogueHeader.tsx` (add EmotionIndicator)

**Step 1: Read DialogueHeader to understand layout**

Read `frontend/src/components/avatar/DialogueHeader.tsx` to find where to place the indicator.

**Step 2: Add useEmotionDetection to DialogueMode**

In `frontend/src/components/avatar/DialogueMode.tsx`, add import:
```typescript
import { useEmotionDetection } from '@/hooks/useEmotionDetection';
```

Inside the `DialogueMode` component function body (after `useUICommands()` on line 32), add:
```typescript
useEmotionDetection();
```

**Step 3: Add EmotionIndicator to DialogueHeader**

In `frontend/src/components/avatar/DialogueHeader.tsx`, import and render the `EmotionIndicator` in the header bar (right-aligned, subtle):

```typescript
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';
```

Place `<EmotionIndicator />` in the header's right section.

**Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

**Step 5: Commit**

```bash
git add frontend/src/components/avatar/DialogueMode.tsx frontend/src/components/avatar/DialogueHeader.tsx
git commit -m "feat: wire emotion detection and indicator into Dialogue Mode"
```

---

## Task 11: Final integration — add emotion detection to ARIA Workspace

**Files:**
- Determine: the main ARIA Workspace page component (find via routes or pages directory)

**Step 1: Find the ARIA Workspace page**

Look for the component that renders at `/` route — likely in `frontend/src/components/pages/` or `frontend/src/app/`. It should render `ConversationThread` and `InputBar`.

**Step 2: Add useEmotionDetection hook**

Import and call `useEmotionDetection()` in the workspace component so emotion events are captured even when not in Dialogue Mode (they can still come via WebSocket from backend-side perception).

**Step 3: Add EmotionIndicator to workspace header**

Place the `EmotionIndicator` component in the ARIA Workspace header area, matching the same subtle placement as in DialogueHeader.

**Step 4: Verify TypeScript compiles and visual check**

Run: `cd frontend && npx tsc --noEmit`
Run: `cd frontend && npm run dev`

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: wire emotion detection into ARIA Workspace"
```

---

## Task 12: Run full build + lint check

**Step 1: Frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean

**Step 2: Frontend lint**

Run: `cd frontend && npm run lint`
Expected: Clean or only pre-existing warnings

**Step 3: Backend lint**

Run: `cd backend && ruff check src/api/routes/perception.py`
Expected: Clean

**Step 4: Fix any issues and commit**

```bash
git add -A
git commit -m "chore: fix lint and type issues from voice/emotion/presence work"
```

---

## Summary of all changes

| # | What | Files | Type |
|---|------|-------|------|
| 1 | isListening in modality store | modalityStore.ts | Modify |
| 2 | useVoiceInput hook | useVoiceInput.ts | Create |
| 3 | VoiceIndicator component | VoiceIndicator.tsx | Create |
| 4 | Wire voice into InputBar | InputBar.tsx | Modify |
| 5 | Perception store + emotion hook | perceptionStore.ts, useEmotionDetection.ts | Create |
| 6 | EmotionIndicator component | EmotionIndicator.tsx | Create |
| 7 | Backend perception route | perception.py, main.py | Create + Modify |
| 8 | Sidebar breathing glow | Sidebar.tsx, index.css | Modify |
| 9 | Arrival sweep + chunk fade + settle | index.css, ConversationThread.tsx, MessageBubble.tsx | Modify |
| 10 | Wire into Dialogue Mode | DialogueMode.tsx, DialogueHeader.tsx | Modify |
| 11 | Wire into ARIA Workspace | Workspace page component | Modify |
| 12 | Full build + lint | — | Verify |
