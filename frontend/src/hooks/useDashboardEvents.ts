/**
 * useDashboardEvents — Central WebSocket event orchestrator for dashboard surfaces.
 *
 * Subscribes to 7 WebSocket event types and dispatches to appropriate stores
 * and React Query caches. Mounted once in AppShell so all routes benefit.
 */

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useAgentStatusStore } from '@/stores/agentStatusStore';
import { useActionQueueStore } from '@/stores/actionQueueStore';
import { useNotificationsStore } from '@/stores/notificationsStore';
import type {
  StepStartedPayload,
  StepCompletedPayload,
  StepRetryingPayload,
  ExecutionCompletePayload,
  ActionPendingPayload,
  SignalPayload,
  ProgressUpdatePayload,
} from '@/types/execution';
import { actionKeys } from '@/hooks/useActionQueue';

export function useDashboardEvents(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    // --- Agent status events ---
    const handleStepStarted = (payload: unknown) => {
      const data = payload as StepStartedPayload;
      useAgentStatusStore
        .getState()
        .setAgentActive(data.agent, data.title, data.goal_id, data.step_id);
    };

    const handleStepCompleted = (payload: unknown) => {
      const data = payload as StepCompletedPayload;
      useAgentStatusStore
        .getState()
        .setAgentCompleted(data.agent, data.success, data.result_summary ?? null);
    };

    const handleStepRetrying = (payload: unknown) => {
      const data = payload as StepRetryingPayload;
      useAgentStatusStore.getState().setAgentRetrying(data.agent, data.reason);
    };

    // --- Action queue events ---
    const handleActionPending = (payload: unknown) => {
      const data = payload as ActionPendingPayload;
      useActionQueueStore.getState().addPending({
        actionId: data.action_id,
        title: data.title,
        agent: data.agent,
        riskLevel: data.risk_level,
        description: data.description,
        receivedAt: Date.now(),
      });

      useNotificationsStore.getState().addNotification({
        type: 'info',
        title: 'Action Pending Approval',
        message: `${data.agent}: ${data.title}`,
        duration: 8000,
      });

      queryClient.invalidateQueries({ queryKey: actionKeys.all });
    };

    // --- Signal events ---
    const handleSignalDetected = (payload: unknown) => {
      const data = payload as SignalPayload;
      const notifType = data.severity === 'critical' ? 'error' : data.severity === 'high' ? 'warning' : 'info';
      useNotificationsStore.getState().addNotification({
        type: notifType as 'info' | 'warning' | 'error',
        title: data.title,
        message: `${data.signal_type} signal detected`,
        duration: 10000,
      });

      queryClient.invalidateQueries({ queryKey: ['activity'] });
    };

    // --- Execution complete ---
    const handleExecutionComplete = (payload: unknown) => {
      const data = payload as ExecutionCompletePayload;

      useNotificationsStore.getState().addNotification({
        type: data.success ? 'success' : 'error',
        title: data.success ? 'Goal Completed' : 'Goal Failed',
        message: data.summary ?? data.title,
        duration: 8000,
      });

      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({ queryKey: ['activity'] });
    };

    // --- Progress updates ---
    const handleProgressUpdate = (payload: unknown) => {
      const data = payload as ProgressUpdatePayload;
      // Optimistically update any cached goal queries that include this goal
      queryClient.setQueriesData<Array<{ id: string; progress?: number; status?: string }>>(
        { queryKey: ['goals'] },
        (old) => {
          if (!old) return old;
          return old.map((goal) =>
            goal.id === data.goal_id
              ? { ...goal, progress: data.progress, status: data.status }
              : goal,
          );
        },
      );
    };

    // Subscribe to all events
    wsManager.on(WS_EVENTS.STEP_STARTED, handleStepStarted);
    wsManager.on(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
    wsManager.on(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
    wsManager.on(WS_EVENTS.ACTION_PENDING, handleActionPending);
    wsManager.on(WS_EVENTS.SIGNAL_DETECTED, handleSignalDetected);
    wsManager.on(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);
    wsManager.on(WS_EVENTS.PROGRESS_UPDATE, handleProgressUpdate);

    return () => {
      wsManager.off(WS_EVENTS.STEP_STARTED, handleStepStarted);
      wsManager.off(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
      wsManager.off(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
      wsManager.off(WS_EVENTS.ACTION_PENDING, handleActionPending);
      wsManager.off(WS_EVENTS.SIGNAL_DETECTED, handleSignalDetected);
      wsManager.off(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);
      wsManager.off(WS_EVENTS.PROGRESS_UPDATE, handleProgressUpdate);
    };
  }, [queryClient]);
}
