import { create } from 'zustand';

export interface ThesysStore {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

export const useThesysStore = create<ThesysStore>((set) => ({
  enabled: false,
  setEnabled: (enabled) => set({ enabled }),
}));
