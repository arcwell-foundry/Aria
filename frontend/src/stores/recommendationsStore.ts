/**
 * Recommendations Store — Real-time recommendations from WebSocket events.
 *
 * Captures signal.detected and recommendation.new events as actionable
 * recommendations. Used by NextBestActionModule for live updates.
 */

import { create } from 'zustand';

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  agent: string;
  source: 'signal' | 'recommendation';
  receivedAt: number;
  dismissed: boolean;
}

export interface RecommendationsState {
  items: Recommendation[];
  addRecommendation(item: Omit<Recommendation, 'id' | 'receivedAt' | 'dismissed'>): void;
  dismiss(id: string): void;
  clear(): void;
}

const MAX_ITEMS = 20;

export const useRecommendationsStore = create<RecommendationsState>((set) => ({
  items: [],

  addRecommendation: (item) =>
    set((state) => {
      const id = `rec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const newItem: Recommendation = {
        ...item,
        id,
        receivedAt: Date.now(),
        dismissed: false,
      };
      return {
        items: [newItem, ...state.items].slice(0, MAX_ITEMS),
      };
    }),

  dismiss: (id) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.id === id ? { ...item, dismissed: true } : item,
      ),
    })),

  clear: () => set({ items: [] }),
}));
