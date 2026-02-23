// frontend/src/types/chat.ts
// Shared type definitions for WebSocket events, messages, and UI commands.

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
  ARIA_STREAM_COMPLETE: 'aria.stream_complete',
  ARIA_STREAM_ERROR: 'aria.stream_error',
  ACTION_PENDING: 'action.pending',
  ACTION_COMPLETED: 'action.completed',
  ACTION_EXECUTED_WITH_UNDO: 'action.executed_with_undo',
  ACTION_UNDONE: 'action.undone',
  PROGRESS_UPDATE: 'progress.update',
  SIGNAL_DETECTED: 'signal.detected',
  EMOTION_DETECTED: 'emotion.detected',
  SESSION_SYNC: 'session.sync',
  STEP_STARTED: 'execution.step_started',
  STEP_COMPLETED: 'execution.step_completed',
  STEP_RETRYING: 'execution.step_retrying',
  EXECUTION_COMPLETE: 'execution.complete',
  RECOMMENDATION_NEW: 'recommendation.new',

  // Client → Server
  USER_MESSAGE: 'user.message',
  USER_NAVIGATE: 'user.navigate',
  USER_APPROVE: 'user.approve',
  USER_REJECT: 'user.reject',
  USER_UNDO: 'user.undo',
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

export interface StreamErrorPayload {
  error: string;
  conversation_id?: string;
  recoverable?: boolean;
}

export interface WSEnvelope {
  type: string;
  payload: unknown;
}

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
