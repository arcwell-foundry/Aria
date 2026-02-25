/**
 * TTS Store - Global text-to-speech state management
 *
 * Manages:
 * - Current speaking message ID
 * - Speaking/paused state
 * - Global TTS instance
 */

import { create } from 'zustand';

interface TTSState {
  // State
  speakingMessageId: string | null;
  isPaused: boolean;

  // Actions
  setSpeakingMessageId: (id: string | null) => void;
  setIsPaused: (isPaused: boolean) => void;
  stopSpeaking: () => void;
}

export const useTTSStore = create<TTSState>((set) => ({
  // Initial state
  speakingMessageId: null,
  isPaused: false,

  // Actions
  setSpeakingMessageId: (id) => set({ speakingMessageId: id, isPaused: false }),

  setIsPaused: (isPaused) => set({ isPaused }),

  stopSpeaking: () => set({ speakingMessageId: null, isPaused: false }),
}));
