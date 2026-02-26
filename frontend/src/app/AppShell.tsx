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
import { CompactAvatar, GoalPlanSidePanel } from '@/components/avatar';
import { useNavigationStore, type NavigationState } from '@/stores/navigationStore';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';
import { useWebSocketStatus } from '@/hooks/useWebSocketStatus';
import { UrgentEmailNotification } from '@/components/notifications/UrgentEmailNotification';
import { useDashboardEvents } from '@/hooks/useDashboardEvents';
import { useExecutionProgress } from '@/hooks/useExecutionProgress';
import { useUICommands } from '@/hooks/useUICommands';
import { useGoalPlanSidePanel } from '@/hooks/useGoalPlanSidePanel';
import { UndoToastContainer } from '@/components/execution/UndoToast';
import { wsManager } from '@/core/WebSocketManager';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';

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
  const { isConnected } = useWebSocketStatus();
  const { session } = useSession();
  const { user } = useAuth();
  const setIntelPanelVisible = useNavigationStore(
    (s: NavigationState) => s.setIntelPanelVisible,
  );

  // Lift WebSocket connection to AppShell so it persists across all routes
  useEffect(() => {
    if (!user?.id || !session?.id) return;

    wsManager.connect(user.id, session.id);

    return () => {
      wsManager.disconnect();
    };
  }, [user?.id, session?.id]);

  // Wire dashboard WebSocket events to stores and React Query caches
  useDashboardEvents();
  // Wire execution step events to executionStore
  useExecutionProgress();
  // Wire UI commands from ARIA messages to UICommandExecutor
  useUICommands();
  // Wire goal plan side panel for avatar mode
  useGoalPlanSidePanel();

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
        <Sidebar isARIAActive={isConnected} />

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

      {/* Urgent email notifications — top-right overlay */}
      <UrgentEmailNotification />

      {/* Undo toast — persists across all routes */}
      <UndoToastContainer />

      {/* Goal plan side panel — shows in avatar mode */}
      <GoalPlanSidePanel />

      {/* Floating PiP avatar — portaled to document.body */}
      <CompactAvatar />
    </>
  );
}
