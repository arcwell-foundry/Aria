import { create } from 'zustand';

export interface UndoItem {
  action_id: string;
  title: string;
  description?: string;
  agent: string;
  undo_deadline: string;
  undo_duration_seconds: number;
  status: 'active' | 'undoing' | 'undone' | 'expired';
  created_at: number;
}

export interface UndoState {
  items: UndoItem[];
  addUndoItem: (item: Omit<UndoItem, 'status' | 'created_at'>) => void;
  markExpired: (actionId: string) => void;
  markUndone: (actionId: string) => void;
  markUndoing: (actionId: string) => void;
  removeItem: (actionId: string) => void;
}

export const useUndoStore = create<UndoState>((set) => ({
  items: [],

  addUndoItem: (item) =>
    set((state) => ({
      items: [
        ...state.items,
        { ...item, status: 'active' as const, created_at: Date.now() },
      ],
    })),

  markExpired: (actionId) => {
    set((state) => ({
      items: state.items.map((i) =>
        i.action_id === actionId ? { ...i, status: 'expired' as const } : i,
      ),
    }));
    // Remove after exit animation
    setTimeout(() => {
      set((state) => ({
        items: state.items.filter((i) => i.action_id !== actionId),
      }));
    }, 2000);
  },

  markUndone: (actionId) => {
    set((state) => ({
      items: state.items.map((i) =>
        i.action_id === actionId ? { ...i, status: 'undone' as const } : i,
      ),
    }));
    // Remove after success animation
    setTimeout(() => {
      set((state) => ({
        items: state.items.filter((i) => i.action_id !== actionId),
      }));
    }, 1500);
  },

  markUndoing: (actionId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.action_id === actionId ? { ...i, status: 'undoing' as const } : i,
      ),
    })),

  removeItem: (actionId) =>
    set((state) => ({
      items: state.items.filter((i) => i.action_id !== actionId),
    })),
}));
