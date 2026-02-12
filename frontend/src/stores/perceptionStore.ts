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
