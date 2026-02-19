/**
 * useExecutionProgress — Wires WebSocket execution events into executionStore.
 *
 * Listens for step_started, step_completed, step_retrying, and execution.complete
 * events, then updates the executionStore accordingly. Mounted once in ARIAWorkspace.
 */

import { useEffect } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useExecutionStore } from '@/stores/executionStore';
import type {
  StepStartedPayload,
  StepCompletedPayload,
  StepRetryingPayload,
  ExecutionCompletePayload,
} from '@/types/execution';

export function useExecutionProgress(): void {
  const updateStep = useExecutionStore((s) => s.updateStep);
  const completeExecution = useExecutionStore((s) => s.completeExecution);

  useEffect(() => {
    const handleStepStarted = (payload: unknown) => {
      const data = payload as StepStartedPayload;
      updateStep(data.goal_id, data.step_id, {
        status: 'active',
        started_at: new Date().toISOString(),
      });
    };

    const handleStepCompleted = (payload: unknown) => {
      const data = payload as StepCompletedPayload;
      updateStep(data.goal_id, data.step_id, {
        status: data.success ? 'completed' : 'failed',
        completed_at: new Date().toISOString(),
        result_summary: data.result_summary,
        error_message: data.error_message,
      });
    };

    const handleStepRetrying = (payload: unknown) => {
      const data = payload as StepRetryingPayload;
      updateStep(data.goal_id, data.step_id, {
        status: 'retrying',
        retry_count: data.retry_count,
        error_message: data.reason,
      });
    };

    const handleExecutionComplete = (payload: unknown) => {
      const data = payload as ExecutionCompletePayload;
      completeExecution(data.goal_id, data.success, data.summary);
    };

    wsManager.on(WS_EVENTS.STEP_STARTED, handleStepStarted);
    wsManager.on(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
    wsManager.on(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
    wsManager.on(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);

    return () => {
      wsManager.off(WS_EVENTS.STEP_STARTED, handleStepStarted);
      wsManager.off(WS_EVENTS.STEP_COMPLETED, handleStepCompleted);
      wsManager.off(WS_EVENTS.STEP_RETRYING, handleStepRetrying);
      wsManager.off(WS_EVENTS.EXECUTION_COMPLETE, handleExecutionComplete);
    };
  }, [updateStep, completeExecution]);
}
