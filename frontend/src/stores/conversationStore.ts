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
