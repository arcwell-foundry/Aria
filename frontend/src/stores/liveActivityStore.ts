/**
 * Live Activity Store — Captures WebSocket events as real-time activity entries.
 *
 * These are prepended to the ActivityFeed above poll-based items,
 * giving users instant feedback on ARIA's autonomous operations.
 * When the poll-based feed refreshes, these items get deduplicated.
 */

import { create } from 'zustand';

export interface LiveActivityEntry {
  id: string;
  agent: string;
  title: string;
  description: string;
  activity_type: string;
  created_at: string;
}

export interface LiveActivityState {
  entries: LiveActivityEntry[];
  addEntry(entry: Omit<LiveActivityEntry, 'id' | 'created_at'>): void;
  removeOlderThan(timestamp: string): void;
  clear(): void;
}

const MAX_LIVE_ENTRIES = 50;

export const useLiveActivityStore = create<LiveActivityState>((set) => ({
  entries: [],

  addEntry: (entry) =>
    set((state) => {
      const id = `live-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const newEntry: LiveActivityEntry = {
        ...entry,
        id,
        created_at: new Date().toISOString(),
      };
      return {
        entries: [newEntry, ...state.entries].slice(0, MAX_LIVE_ENTRIES),
      };
    }),

  removeOlderThan: (timestamp) =>
    set((state) => ({
      entries: state.entries.filter(
        (e) => new Date(e.created_at).getTime() > new Date(timestamp).getTime(),
      ),
    })),

  clear: () => set({ entries: [] }),
}));
