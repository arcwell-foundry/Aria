/**
 * useGoalPlanSidePanel - Hook to detect goal plans and show side panel in avatar mode
 *
 * When the user is in avatar/video mode and ARIA sends a goal_plan via WebSocket,
 * this hook detects it and shows the GoalPlanSidePanel instead of rendering inline.
 *
 * Usage:
 * - Call this hook in components that handle WebSocket messages (DialogueMode, AppShell)
 * - The hook listens for aria.message events and checks for goal_plan rich content
 * - When detected AND in avatar mode, it triggers the side panel
 */

import { useEffect, useCallback } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useModalityStore } from '@/stores/modalityStore';
import { useSidePanelStore } from '@/stores/sidePanelStore';
import type { GoalPlanData } from '@/components/rich/GoalPlanCard';

interface AriaMessagePayload {
  rich_content?: Array<{
    type: string;
    data: unknown;
  }>;
  [key: string]: unknown;
}

/**
 * Hook that monitors for goal_plan rich content and shows side panel when in avatar mode.
 *
 * @returns isAvatarMode - Whether the user is currently in avatar/video mode
 */
export function useGoalPlanSidePanel() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const activeModality = useModalityStore((s) => s.activeModality);
  const setPendingGoalPlan = useSidePanelStore((s) => s.setPendingGoalPlan);

  // User is in avatar mode if:
  // 1. Active modality is 'avatar', OR
  // 2. Tavus session is active (status === 'active' and has room URL)
  const isAvatarMode =
    activeModality === 'avatar' ||
    (tavusSession.status === 'active' && tavusSession.roomUrl !== null);

  // Handle incoming aria.message events
  const handleAriaMessage = useCallback(
    (payload: unknown) => {
      if (!isAvatarMode) return;

      const data = (payload ?? {}) as Partial<AriaMessagePayload>;
      const richContent = data.rich_content ?? [];

      // Find goal_plan in rich content
      const goalPlanContent = richContent.find((item) => item.type === 'goal_plan');

      if (goalPlanContent && goalPlanContent.data) {
        // Extract the goal plan data
        const goalPlanData = goalPlanContent.data as GoalPlanData;

        // Show the side panel with the goal plan
        setPendingGoalPlan(goalPlanData);
      }
    },
    [isAvatarMode, setPendingGoalPlan],
  );

  // Subscribe to aria.message events
  useEffect(() => {
    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    };
  }, [handleAriaMessage]);

  return { isAvatarMode };
}
