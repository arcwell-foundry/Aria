/**
 * Action Queue Store — Real-time pending action tracking from WebSocket push.
 *
 * Stores pending actions received via WebSocket `action.pending` events.
 * Used by Sidebar (badge count) and PendingApprovalsModule (inline approve/reject).
 */

import { create } from 'zustand';

export interface PendingAction {
  actionId: string;
  title: string;
  agent: string;
  riskLevel: string;
  description: string | null;
  receivedAt: number;
}

export interface ActionQueueState {
  pendingActions: PendingAction[];
  addPending(action: PendingAction): void;
  removePending(actionId: string): void;
  clear(): void;
}

export const useActionQueueStore = create<ActionQueueState>((set) => ({
  pendingActions: [],

  addPending: (action) =>
    set((state) => {
      // Prevent duplicates
      if (state.pendingActions.some((a) => a.actionId === action.actionId)) {
        return state;
      }
      return { pendingActions: [...state.pendingActions, action] };
    }),

  removePending: (actionId) =>
    set((state) => ({
      pendingActions: state.pendingActions.filter((a) => a.actionId !== actionId),
    })),

  clear: () => set({ pendingActions: [] }),
}));
