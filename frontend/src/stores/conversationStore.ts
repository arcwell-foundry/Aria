/**
 * Conversation Store - Chat and conversation state management
 *
 * Manages:
 * - Active conversation ID
 * - Message history
 * - Input state
 * - Typing indicators
 */

import { create } from 'zustand';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

export interface ConversationState {
  // State
  activeConversationId: string | null;
  messages: Message[];
  inputValue: string;
  isTyping: boolean;
  isLoading: boolean;

  // Actions
  setActiveConversation: (id: string | null) => void;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void;
  setMessages: (messages: Message[]) => void;
  clearMessages: () => void;
  setInputValue: (value: string) => void;
  setIsTyping: (isTyping: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
}

export const useConversationStore = create<ConversationState>((set) => ({
  // Initial state
  activeConversationId: null,
  messages: [],
  inputValue: '',
  isTyping: false,
  isLoading: false,

  // Actions
  setActiveConversation: (id) => set({ activeConversationId: id }),

  addMessage: (message) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...message,
          id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          timestamp: new Date(),
        },
      ],
    })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [] }),

  setInputValue: (value) => set({ inputValue: value }),

  setIsTyping: (isTyping) => set({ isTyping }),

  setIsLoading: (isLoading) => set({ isLoading }),
}));
