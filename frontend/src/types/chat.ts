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
