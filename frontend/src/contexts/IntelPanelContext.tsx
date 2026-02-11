/**
 * IntelPanelContext - State for the ARIA Intelligence Panel
 *
 * Stores current panel content that can be updated by:
 * 1. Route changes (auto-selects appropriate modules)
 * 2. ARIA via update_intel_panel UICommand
 * 3. Direct programmatic updates
 *
 * ARIA content overrides are scoped to the route where they were set.
 * Navigating to a different page automatically clears the override
 * (the ariaContent is ignored when currentRoute !== the route it was set on).
 */

import { createContext, useState, useCallback, useMemo, useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { uiCommandExecutor } from '@/core/UICommandExecutor';

interface InternalState {
  titleOverride: string | null;
  ariaContent: Record<string, unknown> | null;
  lastAriaUpdate: string | null;
  /** The route on which the ARIA content was pushed */
  setOnRoute: string | null;
}

export interface IntelPanelState {
  titleOverride: string | null;
  ariaContent: Record<string, unknown> | null;
  lastAriaUpdate: string | null;
}

export interface IntelPanelContextValue {
  state: IntelPanelState;
  updateFromAria: (content: Record<string, unknown>) => void;
  clearAriaContent: () => void;
  currentRoute: string;
}

const EMPTY_INTERNAL: InternalState = {
  titleOverride: null,
  ariaContent: null,
  lastAriaUpdate: null,
  setOnRoute: null,
};

const EMPTY_STATE: IntelPanelState = {
  titleOverride: null,
  ariaContent: null,
  lastAriaUpdate: null,
};

export const IntelPanelCtx = createContext<IntelPanelContextValue | null>(null);

export function IntelPanelProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [internal, setInternal] = useState<InternalState>(EMPTY_INTERNAL);

  const updateFromAria = useCallback(
    (content: Record<string, unknown>) => {
      setInternal({
        titleOverride: typeof content.title === 'string' ? content.title : null,
        ariaContent: content,
        lastAriaUpdate: new Date().toISOString(),
        setOnRoute: location.pathname,
      });
    },
    [location.pathname],
  );

  const clearAriaContent = useCallback(() => {
    setInternal(EMPTY_INTERNAL);
  }, []);

  // Register the handler on the UICommandExecutor
  useEffect(() => {
    uiCommandExecutor.setIntelPanelHandler(updateFromAria);
  }, [updateFromAria]);

  // Derive the effective state: ARIA content only applies on the route it was set on
  const state: IntelPanelState = useMemo(() => {
    if (internal.ariaContent && internal.setOnRoute === location.pathname) {
      return {
        titleOverride: internal.titleOverride,
        ariaContent: internal.ariaContent,
        lastAriaUpdate: internal.lastAriaUpdate,
      };
    }
    return EMPTY_STATE;
  }, [internal, location.pathname]);

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
