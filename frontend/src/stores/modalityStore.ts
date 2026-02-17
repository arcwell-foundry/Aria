/**
 * Modality Store - Avatar/voice/text modality state management
 *
 * Manages:
 * - Active interaction modality (text, voice, avatar)
 * - Tavus video session lifecycle
 * - Speaking state (waveform animation driver)
 * - Picture-in-picture avatar visibility
 * - Caption and playback preferences
 */

import { create } from 'zustand';

export type Modality = 'text' | 'voice' | 'avatar';
export type TavusSessionStatus = 'idle' | 'connecting' | 'active' | 'ending';
export type TavusSessionType = 'chat' | 'briefing' | 'debrief';

export interface TavusSession {
  id: string | null;
  roomUrl: string | null;
  status: TavusSessionStatus;
  sessionType: TavusSessionType;
  isAudioOnly: boolean;
}

const INITIAL_TAVUS_SESSION: TavusSession = {
  id: null,
  roomUrl: null,
  status: 'idle',
  sessionType: 'chat',
  isAudioOnly: false,
};

export interface ModalityState {
  // State
  activeModality: Modality;
  tavusSession: TavusSession;
  isSpeaking: boolean;
  isListening: boolean;
  isPipVisible: boolean;
  captionsEnabled: boolean;
  playbackSpeed: number;

  // Actions
  setActiveModality: (modality: Modality) => void;
  setTavusSession: (partial: Partial<TavusSession>) => void;
  clearTavusSession: () => void;
  setIsSpeaking: (isSpeaking: boolean) => void;
  setIsListening: (isListening: boolean) => void;
  setIsPipVisible: (isPipVisible: boolean) => void;
  setCaptionsEnabled: (captionsEnabled: boolean) => void;
  setPlaybackSpeed: (playbackSpeed: number) => void;
}

export const useModalityStore = create<ModalityState>((set) => ({
  // Initial state
  activeModality: 'text',
  tavusSession: { ...INITIAL_TAVUS_SESSION },
  isSpeaking: false,
  isListening: false,
  isPipVisible: false,
  captionsEnabled: true,
  playbackSpeed: 1.0,

  // Actions
  setActiveModality: (modality) => set({ activeModality: modality }),

  setTavusSession: (partial) =>
    set((state) => ({
      tavusSession: { ...state.tavusSession, ...partial },
    })),

  clearTavusSession: () =>
    set({
      tavusSession: { ...INITIAL_TAVUS_SESSION },
      isPipVisible: false,
    }),

  setIsSpeaking: (isSpeaking) => set({ isSpeaking }),

  setIsListening: (isListening) => set({ isListening }),

  setIsPipVisible: (isPipVisible) => set({ isPipVisible }),

  setCaptionsEnabled: (captionsEnabled) => set({ captionsEnabled }),

  setPlaybackSpeed: (playbackSpeed) => set({ playbackSpeed }),
}));
