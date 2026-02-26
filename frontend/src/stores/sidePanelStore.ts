/**
 * SidePanelStore - Manages side panel state for avatar/video mode
 *
 * When the user is in avatar/video mode, certain rich content (like goal plans)
 * should appear in a slide-in side panel rather than inline in the transcript.
 * This store manages that side panel's visibility and content.
 */

import { create } from 'zustand';
import type { GoalPlanData } from '@/components/rich/GoalPlanCard';

export interface SidePanelState {
  // State
  pendingGoalPlan: GoalPlanData | null;
  isVisible: boolean;

  // Actions
  setPendingGoalPlan: (plan: GoalPlanData | null) => void;
  showSidePanel: () => void;
  hideSidePanel: () => void;
  dismissSidePanel: () => void;
}

export const useSidePanelStore = create<SidePanelState>((set) => ({
  // Initial state
  pendingGoalPlan: null,
  isVisible: false,

  // Actions
  setPendingGoalPlan: (plan) =>
    set({
      pendingGoalPlan: plan,
      isVisible: plan !== null,
    }),

  showSidePanel: () => set({ isVisible: true }),

  hideSidePanel: () => set({ isVisible: false }),

  dismissSidePanel: () =>
    set({
      pendingGoalPlan: null,
      isVisible: false,
    }),
}));
