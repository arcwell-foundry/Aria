/**
 * Trust Store - Manages per-category trust profile state
 *
 * Fetched when Autonomy settings tab is opened. Supports
 * category selection for history filtering and optimistic
 * override updates with rollback.
 */

import { create } from "zustand";
import {
  getTrustProfiles,
  getTrustHistory,
  setTrustOverride,
  type TrustProfile,
  type TrustHistoryPoint,
  type OverrideMode,
} from "@/api/trust";

export interface TrustState {
  profiles: TrustProfile[];
  history: TrustHistoryPoint[];
  selectedCategory: string | null;
  loading: boolean;
  historyLoading: boolean;
  error: string | null;

  fetchProfiles: () => Promise<void>;
  fetchHistory: (category?: string, days?: number) => Promise<void>;
  setOverride: (category: string, mode: OverrideMode) => Promise<void>;
  selectCategory: (category: string | null) => void;
}

export const useTrustStore = create<TrustState>((set, get) => ({
  profiles: [],
  history: [],
  selectedCategory: null,
  loading: false,
  historyLoading: false,
  error: null,

  fetchProfiles: async () => {
    set({ loading: true, error: null });
    try {
      const profiles = await getTrustProfiles();
      set({ profiles, loading: false });
    } catch {
      set({ loading: false, error: "Failed to load trust profiles" });
    }
  },

  fetchHistory: async (category?: string, days = 30) => {
    set({ historyLoading: true });
    try {
      const history = await getTrustHistory(category, days);
      set({ history, historyLoading: false });
    } catch {
      set({ historyLoading: false });
    }
  },

  setOverride: async (category: string, mode: OverrideMode) => {
    const prev = get().profiles;
    // Optimistic update
    set({
      profiles: prev.map((p) =>
        p.action_category === category
          ? { ...p, override_mode: mode === "aria_decides" ? null : mode }
          : p
      ),
    });
    try {
      const updated = await setTrustOverride(category, mode);
      set({
        profiles: get().profiles.map((p) =>
          p.action_category === category ? updated : p
        ),
      });
    } catch {
      // Rollback on failure
      set({ profiles: prev, error: "Failed to update override" });
    }
  },

  selectCategory: (category: string | null) => {
    set({ selectedCategory: category });
    if (category) {
      get().fetchHistory(category);
    } else {
      get().fetchHistory();
    }
  },
}));
