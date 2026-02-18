import { useState } from 'react';
import { CheckCircle, XCircle, RefreshCw, Clock, ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { resolveAgent } from '@/constants/agents';
import { TraceNodeDetail } from './TraceNodeDetail';
import type { DelegationTrace, TraceStatus } from '@/api/traces';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0';
  if (usd < 0.01) return '<$0.01';
  return `$${usd.toFixed(2)}`;
}

const STATUS_CONFIG: Record<
  TraceStatus,
  { icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; color: string; label: string }
> = {
  completed: { icon: CheckCircle, color: 'var(--success)', label: 'Completed' },
  failed: { icon: XCircle, color: 'var(--critical)', label: 'Failed' },
  re_delegated: { icon: RefreshCw, color: 'var(--warning)', label: 'Re-delegated' },
  dispatched: { icon: Clock, color: 'var(--text-secondary)', label: 'Dispatched' },
  executing: { icon: Clock, color: 'var(--accent)', label: 'Executing' },
  cancelled: { icon: XCircle, color: 'var(--text-secondary)', label: 'Cancelled' },
};

// ---------------------------------------------------------------------------
// Find the child trace that was re-delegated to (for re_delegated status)
// ---------------------------------------------------------------------------

function findChildAgent(trace: DelegationTrace, allTraces: DelegationTrace[]): string | null {
  if (trace.status !== 're_delegated') return null;
  const child = allTraces.find((t) => t.parent_trace_id === trace.trace_id);
  return child ? child.delegatee : null;
}

// ---------------------------------------------------------------------------
// TraceNode
// ---------------------------------------------------------------------------

interface TraceNodeProps {
  trace: DelegationTrace;
  allTraces: DelegationTrace[];
  isLast: boolean;
}

export function TraceNode({ trace, allTraces, isLast }: TraceNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const agentInfo = resolveAgent(trace.delegatee);
  const statusCfg = STATUS_CONFIG[trace.status] ?? STATUS_CONFIG.dispatched;
  const StatusIcon = statusCfg.icon;
  const childAgent = findChildAgent(trace, allTraces);

  const verificationFailed =
    trace.verification_result && !trace.verification_result.passed;
  const firstIssue = verificationFailed
    ? trace.verification_result!.issues[0]
    : null;

  return (
    <div className="relative flex gap-3">
      {/* Timeline line */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div
          className="w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 z-10"
          style={{ backgroundColor: statusCfg.color }}
        />
        {!isLast && (
          <div
            className="w-0.5 flex-1 -mb-3"
            style={{ backgroundColor: 'var(--border)' }}
          />
        )}
      </div>

      {/* Card */}
      <div className={cn('flex-1 pb-4', isLast && 'pb-0')}>
        <div
          className="border rounded-lg p-3 transition-colors"
          style={{
            borderColor: 'var(--border)',
            backgroundColor: 'var(--bg-elevated)',
          }}
        >
          {/* Header row */}
          <div className="flex items-center gap-2.5">
            <AgentAvatar agentKey={trace.delegatee} size={28} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className="font-medium text-sm"
                  style={{ color: agentInfo.color }}
                >
                  {agentInfo.name}
                </span>
                <span
                  className="text-xs truncate"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {trace.task_description}
                </span>
              </div>

              {/* Stats row */}
              <div className="flex items-center gap-2 mt-0.5 text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                <span>{formatDuration(trace.duration_ms)}</span>
                <span className="opacity-40">·</span>
                <span>{formatCost(trace.cost_usd)}</span>
                <span className="opacity-40">·</span>
                <span className="flex items-center gap-1" style={{ color: statusCfg.color }}>
                  <StatusIcon className="w-3 h-3" />
                  {statusCfg.label}
                </span>
              </div>
            </div>

            {/* Expand button */}
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--bg-subtle)]"
              style={{ color: 'var(--text-secondary)' }}
              aria-expanded={expanded}
              aria-label={expanded ? 'Collapse details' : 'Expand details'}
            >
              <ChevronRight
                className={cn(
                  'w-3.5 h-3.5 transition-transform duration-200',
                  expanded && 'rotate-90'
                )}
              />
              Details
            </button>
          </div>

          {/* Verification failure inline */}
          {verificationFailed && firstIssue && (
            <p
              className="text-xs mt-1.5 ml-[38px]"
              style={{ color: 'var(--critical)' }}
            >
              {firstIssue}
            </p>
          )}

          {/* Re-delegation indicator */}
          {childAgent && (
            <p
              className="text-xs mt-1.5 ml-[38px] flex items-center gap-1"
              style={{ color: 'var(--warning)' }}
            >
              <RefreshCw className="w-3 h-3" />
              Re-delegated to {resolveAgent(childAgent).name}
            </p>
          )}

          {/* Expandable detail */}
          {expanded && (
            <div className="mt-3 ml-[38px]">
              <TraceNodeDetail trace={trace} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
