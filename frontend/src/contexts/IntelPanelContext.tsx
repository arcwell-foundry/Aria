/**
 * IntelPanelContext - State for the ARIA Intelligence Panel
 *
 * Stores current panel content that can be updated by:
 * 1. Route changes (auto-selects appropriate modules)
 * 2. ARIA via update_intel_panel UICommand
 * 3. Direct programmatic updates
 */

import { createContext, useContext, useState, useCallback, useMemo, useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { uiCommandExecutor } from '@/core/UICommandExecutor';

export interface IntelPanelState {
  /** Current panel title override (null = use route default) */
  titleOverride: string | null;
  /** Custom content pushed by ARIA via update_intel_panel */
  ariaContent: Record<string, unknown> | null;
  /** Timestamp of last ARIA update */
  lastAriaUpdate: string | null;
}

interface IntelPanelContextValue {
  state: IntelPanelState;
  /** Push custom content from ARIA */
  updateFromAria: (content: Record<string, unknown>) => void;
  /** Clear ARIA override and revert to route-based defaults */
  clearAriaContent: () => void;
  /** Get the current route for module selection */
  currentRoute: string;
}

const IntelPanelCtx = createContext<IntelPanelContextValue | null>(null);

export function IntelPanelProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [state, setState] = useState<IntelPanelState>({
    titleOverride: null,
    ariaContent: null,
    lastAriaUpdate: null,
  });

  const updateFromAria = useCallback((content: Record<string, unknown>) => {
    setState({
      titleOverride: typeof content.title === 'string' ? content.title : null,
      ariaContent: content,
      lastAriaUpdate: new Date().toISOString(),
    });
  }, []);

  const clearAriaContent = useCallback(() => {
    setState({
      titleOverride: null,
      ariaContent: null,
      lastAriaUpdate: null,
    });
  }, []);

  // Register the handler on the UICommandExecutor
  useEffect(() => {
    uiCommandExecutor.setIntelPanelHandler(updateFromAria);
  }, [updateFromAria]);

  // Clear ARIA content on route change so route defaults take over
  useEffect(() => {
    clearAriaContent();
  }, [location.pathname, clearAriaContent]);

  const value = useMemo(
    () => ({
      state,
      updateFromAria,
      clearAriaContent,
      currentRoute: location.pathname,
    }),
    [state, updateFromAria, clearAriaContent, location.pathname],
  );

  return <IntelPanelCtx.Provider value={value}>{children}</IntelPanelCtx.Provider>;
}

export function useIntelPanel(): IntelPanelContextValue {
  const ctx = useContext(IntelPanelCtx);
  if (!ctx) {
    throw new Error('useIntelPanel must be used within IntelPanelProvider');
  }
  return ctx;
}
