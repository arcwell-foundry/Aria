/**
 * useDashboardEvents — Central WebSocket event orchestrator for dashboard surfaces.
 *
 * Subscribes to 7 WebSocket event types and dispatches to appropriate stores
 * and React Query caches. Mounted once in AppShell so all routes benefit.
 */

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useAgentStatusStore } from '@/stores/agentStatusStore';
import { useActionQueueStore } from '@/stores/actionQueueStore';
import { useNotificationsStore } from '@/stores/notificationsStore';
import { useRecommendationsStore } from '@/stores/recommendationsStore';
import { useLiveActivityStore } from '@/stores/liveActivityStore';
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

// Track previous progress values to detect milestone crossings
const MILESTONES = [25, 50, 75, 100];

export function useDashboardEvents(): void {
  const queryClient = useQueryClient();
  const progressMapRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    // --- Agent status events ---
    const handleStepStarted = (payload: unknown) => {
      const data = payload as StepStartedPayload;
      useAgentStatusStore
        .getState()
        .setAgentActive(data.agent, data.title, data.goal_id, data.step_id);

      useLiveActivityStore.getState().addEntry({
        agent: data.agent,
        title: `${data.agent} started: ${data.title}`,
        description: data.title,
        activity_type: 'agent_started',
      });
    };

    const handleStepCompleted = (payload: unknown) => {
      const data = payload as StepCompletedPayload;
      useAgentStatusStore
        .getState()
        .setAgentCompleted(data.agent, data.success, data.result_summary ?? null);

      useLiveActivityStore.getState().addEntry({
        agent: data.agent,
        title: data.success
          ? `${data.agent} completed: ${data.result_summary ?? 'Task done'}`
          : `${data.agent} failed: ${data.error_message ?? 'Task failed'}`,
        description: data.result_summary ?? data.error_message ?? '',
        activity_type: data.success ? 'agent_completed' : 'agent_failed',
      });
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

      // Push to recommendations store as actionable recommendation
      const priority = data.severity === 'critical' || data.severity === 'high'
        ? 'high' : data.severity === 'medium' ? 'medium' : 'low';
      useRecommendationsStore.getState().addRecommendation({
        title: data.title,
        description: `${data.signal_type} signal detected`,
        priority: priority as 'high' | 'medium' | 'low',
        agent: (data.data?.agent as string) ?? 'Scout',
        source: 'signal',
      });

      queryClient.invalidateQueries({ queryKey: ['activity'] });
    };

    // --- Recommendation events ---
    const handleRecommendation = (payload: unknown) => {
      const data = payload as {
        title: string;
        description?: string;
        priority?: string;
        agent?: string;
      };
      useRecommendationsStore.getState().addRecommendation({
        title: data.title,
        description: data.description ?? '',
        priority: (data.priority as 'high' | 'medium' | 'low') ?? 'medium',
        agent: data.agent ?? 'Strategist',
        source: 'recommendation',
      });

      useNotificationsStore.getState().addNotification({
        type: 'info',
        title: 'New Recommendation',
        message: data.title,
        duration: 8000,
      });
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

      useLiveActivityStore.getState().addEntry({
        agent: 'orchestrator',
        title: data.success
          ? `Goal completed: ${data.title}`
          : `Goal failed: ${data.title}`,
        description: data.summary ?? `${data.steps_completed}/${data.steps_total} steps completed`,
        activity_type: data.success ? 'goal_completed' : 'goal_failed',
      });

      queryClient.invalidateQueries({ queryKey: ['goals'] });
      queryClient.invalidateQueries({ queryKey: ['activity'] });
    };

    // --- Progress updates ---
    const handleProgressUpdate = (payload: unknown) => {
      const data = payload as ProgressUpdatePayload;

      // Check for milestone crossings
      const prevProgress = progressMapRef.current.get(data.goal_id) ?? 0;
      progressMapRef.current.set(data.goal_id, data.progress);

      for (const milestone of MILESTONES) {
        if (prevProgress < milestone && data.progress >= milestone) {
          const msg = milestone === 100
            ? `Goal completed: ${data.message ?? 'All tasks done'}`
            : `${milestone}% milestone reached${data.message ? `: ${data.message}` : ''}`;

          useNotificationsStore.getState().addNotification({
            type: milestone === 100 ? 'success' : 'info',
            title: milestone === 100 ? 'Goal Complete' : `${milestone}% Milestone`,
            message: msg,
            duration: milestone === 100 ? 10000 : 6000,
          });
          break; // Only fire one notification per update
        }
      }

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

      // Invalidate activity feed so it picks up progress events
      queryClient.invalidateQueries({ queryKey: ['activity'] });
    };

    // Subscribe to all events
    wsManager.on(WS_EVENTS.STEP_STARTED, handleStepStarted);
    wsManager.on(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
    wsManager.on(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
    wsManager.on(WS_EVENTS.ACTION_PENDING, handleActionPending);
    wsManager.on(WS_EVENTS.SIGNAL_DETECTED, handleSignalDetected);
    wsManager.on(WS_EVENTS.RECOMMENDATION_NEW, handleRecommendation);
    wsManager.on(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);
    wsManager.on(WS_EVENTS.PROGRESS_UPDATE, handleProgressUpdate);

    return () => {
      wsManager.off(WS_EVENTS.STEP_STARTED, handleStepStarted);
      wsManager.off(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
      wsManager.off(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
      wsManager.off(WS_EVENTS.ACTION_PENDING, handleActionPending);
      wsManager.off(WS_EVENTS.SIGNAL_DETECTED, handleSignalDetected);
      wsManager.off(WS_EVENTS.RECOMMENDATION_NEW, handleRecommendation);
      wsManager.off(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);
      wsManager.off(WS_EVENTS.PROGRESS_UPDATE, handleProgressUpdate);
    };
  }, [queryClient]);
}
