/**
 * Navigation Store - Navigation and sidebar state management
 *
 * Manages:
 * - Current route
 * - Sidebar state
 * - Active panel
 * - Navigation history
 */

import { create } from 'zustand';

export type SidebarItem =
  | 'aria'
  | 'briefing'
  | 'pipeline'
  | 'intelligence'
  | 'communications'
  | 'debriefs'
  | 'actions'
  | 'activity'
  | 'analytics'
  | 'settings';

export type IntelPanelMode =
  | 'context'
  | 'signals'
  | 'actions'
  | 'memory'
  | 'goals';

export interface NavigationState {
  // State
  currentRoute: string;
  sidebarCollapsed: boolean;
  activeSidebarItem: SidebarItem;
  intelPanelVisible: boolean;
  intelPanelMode: IntelPanelMode;
  navigationHistory: string[];

  // Actions
  setCurrentRoute: (route: string) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setActiveSidebarItem: (item: SidebarItem) => void;
  setIntelPanelVisible: (visible: boolean) => void;
  setIntelPanelMode: (mode: IntelPanelMode) => void;
  toggleIntelPanel: () => void;
  goBack: () => void;
}

export const useNavigationStore = create<NavigationState>((set) => ({
  // Initial state
  currentRoute: '/',
  sidebarCollapsed: false,
  activeSidebarItem: 'aria',
  intelPanelVisible: true,
  intelPanelMode: 'context',
  navigationHistory: ['/'],

  // Actions
  setCurrentRoute: (route) =>
    set((state) => ({
      currentRoute: route,
      navigationHistory: [...state.navigationHistory, route].slice(-50), // Keep last 50
    })),

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setActiveSidebarItem: (item) => set({ activeSidebarItem: item }),

  setIntelPanelVisible: (visible) => set({ intelPanelVisible: visible }),

  setIntelPanelMode: (mode) => set({ intelPanelMode: mode }),

  toggleIntelPanel: () =>
    set((state) => ({ intelPanelVisible: !state.intelPanelVisible })),

  goBack: () =>
    set((state) => {
      if (state.navigationHistory.length <= 1) return state;
      const newHistory = state.navigationHistory.slice(0, -1);
      return {
        navigationHistory: newHistory,
        currentRoute: newHistory[newHistory.length - 1] || '/',
      };
    }),
}));
