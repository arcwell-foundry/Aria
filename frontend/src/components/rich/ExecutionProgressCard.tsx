/**
 * ExecutionProgressCard — Live execution progress inline in conversation.
 *
 * Shows step-by-step execution progress with agent avatars, timeline
 * connectors, approval controls, and a completion summary with
 * "Show how ARIA did this" link to DelegationTreeDrawer.
 */

import { useState, useCallback, useMemo } from 'react';
import { GitBranch } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { apiClient } from '@/api/client';
import { approveAction, rejectAction } from '@/api/actionQueue';
import { CollapsibleCard } from '@/components/conversation/CollapsibleCard';
import { DelegationTreeDrawer } from '@/components/traces/DelegationTreeDrawer';
import { ExecutionStepRow } from './ExecutionStepRow';
import { useExecutionStore } from '@/stores/executionStore';
import type { ExecutionProgressData } from '@/types/execution';

interface ExecutionProgressCardProps {
  data: ExecutionProgressData;
}

const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  pending: { label: 'Pending', className: 'bg-[var(--text-secondary)]/20 text-[var(--text-secondary)]' },
  executing: { label: 'Executing', className: 'bg-[var(--accent)]/20 text-[var(--accent)]' },
  completed: { label: 'Complete', className: 'bg-emerald-500/20 text-emerald-400' },
  failed: { label: 'Failed', className: 'bg-[var(--warning)]/20 text-[var(--warning)]' },
};

export function ExecutionProgressCard({ data: initialData }: ExecutionProgressCardProps) {
  // Live state from store (if available), otherwise use initial data from rich_content
  const liveData = useExecutionStore((s) => s.executions[initialData.goal_id]);
  const data = liveData ?? initialData;

  const [isApproving, setIsApproving] = useState(false);
  const [treeOpen, setTreeOpen] = useState(false);

  const badge = STATUS_BADGES[data.overall_status] ?? STATUS_BADGES.pending;

  const completedCount = data.steps.filter((s) => s.status === 'completed').length;
  const totalCount = data.steps.length;

  // Find the first pending step for APPROVE_EACH mode
  const nextPendingStepId = useMemo(() => {
    if (data.approval_mode !== 'APPROVE_EACH') return null;
    const pending = data.steps.find((s) => s.status === 'pending');
    return pending?.step_id ?? null;
  }, [data.approval_mode, data.steps]);

  // APPROVE_PLAN: "Execute All" handler
  const handleExecuteAll = useCallback(async () => {
    setIsApproving(true);
    try {
      await apiClient.post(`/goals/${data.goal_id}/start`);
    } catch {
      // Error surfaced via WS or toast
    } finally {
      setIsApproving(false);
    }
  }, [data.goal_id]);

  // APPROVE_EACH: per-step approve
  const handleApproveStep = useCallback(async (stepId: string) => {
    try {
      await approveAction(stepId);
    } catch {
      // Error surfaced via WS or toast
    }
  }, []);

  // APPROVE_EACH: per-step skip
  const handleSkipStep = useCallback(async (stepId: string) => {
    try {
      await rejectAction(stepId, 'Skipped by user');
    } catch {
      // Error surfaced via WS or toast
    }
  }, []);

  const isCompleted = data.overall_status === 'completed';
  const isFailed = data.overall_status === 'failed';
  const isPendingApproval = data.approval_mode === 'APPROVE_PLAN' && data.overall_status === 'pending';

  // Approval footer for APPROVE_PLAN mode
  const approvalFooter = isPendingApproval ? (
    <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
      <button
        type="button"
        onClick={handleExecuteAll}
        disabled={isApproving}
        className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
        style={{ backgroundColor: 'var(--accent)' }}
      >
        {isApproving ? 'Starting...' : 'Execute All'}
      </button>
      <button
        type="button"
        className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
      >
        Modify Plan
      </button>
    </div>
  ) : null;

  return (
    <>
      <div
        className="rounded-lg border border-[var(--border)] overflow-hidden"
        style={{ backgroundColor: 'var(--bg-elevated)' }}
        data-aria-id={`execution-progress-${data.goal_id}`}
      >
        <CollapsibleCard approvalSlot={approvalFooter}>
          {/* Header */}
          <div className="px-4 pt-4 pb-2 flex items-start justify-between">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
                Executing
              </p>
              <h3 className="font-display italic text-base text-[var(--text-primary)]">
                {data.title}
              </h3>
            </div>
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider ${badge.className}`}
            >
              {badge.label}
            </span>
          </div>

          {/* Step list */}
          <div className="px-4 pb-3" role="list" aria-live="polite" aria-label="Execution steps">
            <AnimatePresence initial={false}>
              {data.steps.map((step, i) => (
                <motion.div
                  key={step.step_id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.15, delay: i * 0.03 }}
                  role="listitem"
                >
                  <ExecutionStepRow
                    step={step}
                    isLast={i === data.steps.length - 1}
                    approvalMode={data.approval_mode}
                    isNextPendingApproval={step.step_id === nextPendingStepId}
                    trustContext={step.step_id === nextPendingStepId ? data.trust_context : undefined}
                    onApprove={handleApproveStep}
                    onSkip={handleSkipStep}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {/* Progress footer — shown during execution */}
          {!isCompleted && !isFailed && !isPendingApproval && (
            <div className="border-t border-[var(--border)] px-4 py-2.5 flex items-center justify-between">
              <p className="text-xs text-[var(--text-secondary)]">
                {completedCount}/{totalCount} complete
                {data.estimated_remaining_seconds != null && data.estimated_remaining_seconds > 0 && (
                  <span> — ~{data.estimated_remaining_seconds}s remaining</span>
                )}
              </p>
              {/* Progress bar */}
              <div className="w-24 h-1 rounded-full bg-[var(--border)] overflow-hidden">
                <motion.div
                  className="h-full rounded-full"
                  style={{ backgroundColor: 'var(--accent)' }}
                  initial={{ width: 0 }}
                  animate={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }}
                  transition={{ duration: 0.3, ease: 'easeOut' }}
                />
              </div>
            </div>
          )}

          {/* Completion summary */}
          {(isCompleted || isFailed) && (
            <div className="border-t border-[var(--border)] px-4 py-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-[var(--text-secondary)]">
                  {isCompleted
                    ? `All ${totalCount} steps completed`
                    : `${completedCount}/${totalCount} steps completed`}
                </p>
                <button
                  type="button"
                  onClick={() => setTreeOpen(true)}
                  className="flex items-center gap-1 text-[11px] font-medium transition-colors hover:opacity-80"
                  style={{ color: 'var(--accent)' }}
                >
                  <GitBranch className="w-3 h-3" />
                  Show how ARIA did this
                </button>
              </div>
            </div>
          )}
        </CollapsibleCard>
      </div>

      <DelegationTreeDrawer
        goalId={treeOpen ? data.goal_id : null}
        goalTitle={data.title}
        onClose={() => setTreeOpen(false)}
      />
    </>
  );
}
