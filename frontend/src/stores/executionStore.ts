/**
 * Execution Store — Zustand store for live execution progress state.
 *
 * Keyed by goal_id. Stores ExecutionProgressData per execution so that
 * WebSocket step-level updates can mutate state without re-rendering the
 * entire conversation thread. Separated from conversationStore because:
 *   - Steps update live via WS after the message renders
 *   - Virtuoso may unmount the card — local state would be lost
 *   - Matches existing pattern used by autonomyStore and trustStore
 */

import { create } from 'zustand';
import type { ExecutionProgressData, ExecutionStepStatus } from '@/types/execution';

export interface ExecutionState {
  /** Active executions keyed by goal_id. */
  executions: Record<string, ExecutionProgressData>;

  /** Initialize a new execution from an execution_progress rich content payload. */
  initExecution: (data: ExecutionProgressData) => void;

  /** Update a single step within an execution. */
  updateStep: (
    goalId: string,
    stepId: string,
    partial: Partial<{ status: ExecutionStepStatus; error_message: string; result_summary: string; retry_count: number; started_at: string; completed_at: string }>,
  ) => void;

  /** Mark an execution as completed and optionally set a summary. */
  completeExecution: (goalId: string, success: boolean, summary?: string) => void;

  /** Remove an execution from the store (cleanup). */
  removeExecution: (goalId: string) => void;
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  executions: {},

  initExecution: (data) =>
    set((state) => ({
      executions: { ...state.executions, [data.goal_id]: data },
    })),

  updateStep: (goalId, stepId, partial) =>
    set((state) => {
      const execution = state.executions[goalId];
      if (!execution) return state;

      const steps = execution.steps.map((step) =>
        step.step_id === stepId ? { ...step, ...partial } : step,
      );

      // Derive overall_status from step states
      const hasActive = steps.some((s) => s.status === 'active' || s.status === 'retrying');
      const hasFailed = steps.some((s) => s.status === 'failed');
      const allCompleted = steps.every((s) => s.status === 'completed');
      let overall_status = execution.overall_status;
      if (hasActive) overall_status = 'executing';
      else if (allCompleted) overall_status = 'completed';
      else if (hasFailed && !hasActive) overall_status = 'failed';

      return {
        executions: {
          ...state.executions,
          [goalId]: { ...execution, steps, overall_status },
        },
      };
    }),

  completeExecution: (goalId, success, summary) =>
    set((state) => {
      const execution = state.executions[goalId];
      if (!execution) return state;

      return {
        executions: {
          ...state.executions,
          [goalId]: {
            ...execution,
            overall_status: success ? 'completed' : 'failed',
            steps: execution.steps.map((step) =>
              step.status === 'pending' || step.status === 'active'
                ? { ...step, status: success ? ('completed' as const) : ('failed' as const) }
                : step,
            ),
            ...(summary ? { trust_context: summary } : {}),
          },
        },
      };
    }),

  removeExecution: (goalId) =>
    set((state) => {
      const { [goalId]: _removed, ...rest } = state.executions;
      void _removed;
      return { executions: rest };
    }),
}));
