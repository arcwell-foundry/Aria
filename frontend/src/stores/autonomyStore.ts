/**
 * Autonomy Store - Manages ARIA trust level state
 *
 * Fetched on app init. Refreshed on tier change, action completion,
 * and when app regains focus.
 */

import { create } from 'zustand';
import {
  getAutonomyStatus,
  setAutonomyTier,
  type AutonomyTier,
  type AutonomyStats,
  type RecentAction,
} from '@/api/autonomy';

export interface AutonomyState {
  currentTier: AutonomyTier | null;
  recommendedTier: AutonomyTier | null;
  canSelectTiers: AutonomyTier[];
  stats: AutonomyStats | null;
  recentActions: RecentAction[];
  loading: boolean;
  error: string | null;

  fetchStatus: () => Promise<void>;
  setTier: (tier: AutonomyTier) => Promise<void>;
}

export const useAutonomyStore = create<AutonomyState>((set) => ({
  currentTier: null,
  recommendedTier: null,
  canSelectTiers: [],
  stats: null,
  recentActions: [],
  loading: false,
  error: null,

  fetchStatus: async () => {
    set({ loading: true, error: null });
    try {
      const status = await getAutonomyStatus();
      set({
        currentTier: status.current_tier,
        recommendedTier: status.recommended_tier,
        canSelectTiers: status.can_select_tiers,
        stats: status.stats,
        recentActions: status.recent_actions,
        loading: false,
      });
    } catch {
      set({ loading: false, error: 'Failed to load autonomy status' });
    }
  },

  setTier: async (tier: AutonomyTier) => {
    const prev = useAutonomyStore.getState().currentTier;
    // Optimistic update
    set({ currentTier: tier, error: null });
    try {
      const status = await setAutonomyTier(tier);
      set({
        currentTier: status.current_tier,
        recommendedTier: status.recommended_tier,
        canSelectTiers: status.can_select_tiers,
        stats: status.stats,
        recentActions: status.recent_actions,
      });
    } catch {
      // Rollback on failure
      set({ currentTier: prev, error: 'Failed to update autonomy level' });
    }
  },
}));
