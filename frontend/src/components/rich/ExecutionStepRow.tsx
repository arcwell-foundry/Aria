/**
 * ExecutionStepRow — Single step in an execution progress timeline.
 *
 * Renders a vertical timeline connector, status icon, agent badge,
 * and optional approve/skip buttons for APPROVE_EACH mode.
 */

import { memo } from 'react';
import { Check, AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { getAgentColor, resolveAgent } from '@/constants/agents';
import type { ExecutionStep, ApprovalMode } from '@/types/execution';

interface ExecutionStepRowProps {
  step: ExecutionStep;
  isLast: boolean;
  approvalMode: ApprovalMode;
  /** Whether this is the next step awaiting per-step approval. */
  isNextPendingApproval: boolean;
  trustContext?: string;
  onApprove?: (stepId: string) => void;
  onSkip?: (stepId: string) => void;
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <span className="text-sm leading-none" style={{ color: 'var(--text-secondary)' }}>{'\u25CB'}</span>,
  active: <Loader2 className="w-3.5 h-3.5 motion-safe:animate-spin" style={{ color: 'var(--accent)' }} />,
  completed: (
    <motion.div
      initial={{ scale: 0 }}
      animate={{ scale: 1 }}
      transition={{ type: 'spring', stiffness: 400, damping: 15 }}
      className=""
    >
      <Check className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
    </motion.div>
  ),
  failed: (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
      <AlertTriangle className="w-3.5 h-3.5" style={{ color: 'var(--warning)' }} />
    </motion.div>
  ),
  retrying: <RefreshCw className="w-3.5 h-3.5 motion-safe:animate-spin" style={{ color: 'var(--warning)' }} />,
};

export const ExecutionStepRow = memo(function ExecutionStepRow({
  step,
  isLast,
  approvalMode,
  isNextPendingApproval,
  trustContext,
  onApprove,
  onSkip,
}: ExecutionStepRowProps) {
  const agentMeta = resolveAgent(step.agent);
  const agentColor = getAgentColor(step.agent);

  return (
    <div className="flex gap-3">
      {/* Timeline column */}
      <div className="flex flex-col items-center w-5 shrink-0">
        <div className="mt-1">{STATUS_ICON[step.status] ?? STATUS_ICON.pending}</div>
        {!isLast && <div className="w-px flex-1 min-h-[24px] bg-[var(--border)]" />}
      </div>

      {/* Content */}
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-[var(--text-primary)] truncate">
            {step.title}
          </p>
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider shrink-0"
            style={{ backgroundColor: `${agentColor}15`, color: agentColor }}
          >
            <AgentAvatar agentKey={step.agent} size={14} />
            {agentMeta.name}
          </span>
        </div>

        {step.description && (
          <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
            {step.description}
          </p>
        )}

        {/* Result summary on completion */}
        {step.status === 'completed' && step.result_summary && (
          <p className="text-xs text-[var(--text-secondary)] mt-1 italic">
            {step.result_summary}
          </p>
        )}

        {/* Retry message */}
        <AnimatePresence>
          {step.status === 'retrying' && (
            <motion.p
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="text-xs mt-1 italic"
              style={{ color: 'var(--warning)' }}
            >
              ARIA is trying another approach
              {step.retry_count != null && step.retry_count > 1 && ` (attempt ${step.retry_count})`}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Failure message */}
        {step.status === 'failed' && step.error_message && (
          <p className="text-xs mt-1" style={{ color: 'var(--warning)' }}>
            {step.error_message}
          </p>
        )}

        {/* Per-step approval buttons (APPROVE_EACH mode) */}
        {approvalMode === 'APPROVE_EACH' && isNextPendingApproval && (
          <div className="mt-2">
            {trustContext && (
              <p className="text-xs italic text-[var(--text-secondary)] mb-1.5">
                {trustContext}
              </p>
            )}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onApprove?.(step.step_id)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                <Check className="w-3 h-3" />
                Approve
              </button>
              <button
                type="button"
                onClick={() => onSkip?.(step.step_id)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Skip
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
