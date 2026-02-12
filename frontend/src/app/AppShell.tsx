/**
 * AppShell - Three-column layout for ARIA
 *
 * Structure:
 *   [Sidebar 240px] [Center Outlet flex-1] [IntelPanel 320px]
 *
 * The sidebar is always visible and always dark.
 * The center outlet renders the current route via React Router <Outlet>.
 * The IntelPanel is visible on content pages, hidden on ARIA Workspace
 * and Dialogue Mode routes.
 *
 * Full viewport height; children scroll internally.
 */

import { useEffect, useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from '@/components/shell/Sidebar';
import { IntelPanel } from '@/components/shell/IntelPanel';
import { CompactAvatar } from '@/components/avatar';
import { useNavigationStore, type NavigationState } from '@/stores/navigationStore';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';

/**
 * Routes where the right IntelPanel should be hidden.
 */
const PANEL_HIDDEN_ROUTES = ['/', '/briefing', '/dialogue', '/settings'];

function shouldShowPanel(pathname: string): boolean {
  if (PANEL_HIDDEN_ROUTES.includes(pathname)) return false;
  // Also hide on sub-routes of hidden parents (e.g., /dialogue/*)
  return !PANEL_HIDDEN_ROUTES.some(
    (r) => r !== '/' && pathname.startsWith(r),
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const setIntelPanelVisible = useNavigationStore(
    (s: NavigationState) => s.setIntelPanelVisible,
  );

  useEffect(() => {
    modalityController.setNavigate(navigate);
  }, [navigate]);

  const tavusStatus = useModalityStore((s) => s.tavusSession.status);

  useEffect(() => {
    const isDialogueRoute = pathname === '/dialogue' || pathname === '/briefing';
    if (tavusStatus === 'active' && !isDialogueRoute) {
      useModalityStore.getState().setIsPipVisible(true);
    } else if (isDialogueRoute) {
      useModalityStore.getState().setIsPipVisible(false);
    }
  }, [pathname, tavusStatus]);

  const showPanel = useMemo(() => {
    const visible = shouldShowPanel(pathname);
    // Keep the Zustand store in sync so other components can read it
    setIntelPanelVisible(visible);
    return visible;
  }, [pathname, setIntelPanelVisible]);

  return (
    <>
      <div className="flex h-screen w-screen overflow-hidden" data-aria-id="app-shell">
        {/* Left: Sidebar — always visible, always dark */}
        <Sidebar />

        {/* Center: Active route content */}
        <main
          className="flex-1 min-w-0 flex flex-col overflow-hidden"
          style={{ backgroundColor: 'var(--bg-primary)' }}
        >
          <Outlet />
        </main>

        {/* Right: Intelligence Panel — conditional */}
        {showPanel && <IntelPanel />}
      </div>

      {/* Floating PiP avatar — portaled to document.body */}
      <CompactAvatar />
    </>
  );
}
