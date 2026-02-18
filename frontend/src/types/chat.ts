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
  PROGRESS_UPDATE: 'progress.update',
  SIGNAL_DETECTED: 'signal.detected',
  EMOTION_DETECTED: 'emotion.detected',
  SESSION_SYNC: 'session.sync',

  // Server → Client: Friction
  FRICTION_CHALLENGE: 'friction.challenge',
  FRICTION_FLAG: 'friction.flag',

  // Server → Client: Undo window
  ACTION_EXECUTED_WITH_UNDO: 'action.executed_with_undo',
  ACTION_UNDO_EXPIRED: 'action.undo_expired',
  ACTION_UNDO_COMPLETED: 'action.undo_completed',

  // Client → Server
  USER_MESSAGE: 'user.message',
  USER_NAVIGATE: 'user.navigate',
  USER_APPROVE: 'user.approve',
  USER_REJECT: 'user.reject',
  USER_CONFIRM_FRICTION: 'user.confirm_friction',
  USER_REQUEST_UNDO: 'user.request_undo',
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

// === Friction Payloads ===

export interface FrictionChallengePayload {
  challenge_id: string;
  user_message: string;
  reasoning: string;
  original_request: string;
  proceed_if_confirmed: boolean;
  conversation_id?: string;
}

export interface FrictionFlagPayload {
  flag_message: string;
  message_id?: string;
}

// === Undo Window Payloads ===

export interface ActionExecutedWithUndoPayload {
  action_id: string;
  title: string;
  description?: string;
  agent: string;
  undo_deadline: string;
  undo_duration_seconds: number;
}

export interface ActionUndoExpiredPayload {
  action_id: string;
}

export interface ActionUndoCompletedPayload {
  action_id: string;
  reversal_summary?: string;
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
