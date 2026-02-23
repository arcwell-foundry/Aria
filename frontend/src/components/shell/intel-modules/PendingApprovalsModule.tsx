/**
 * PendingApprovalsModule — Compact intel panel module showing pending actions.
 *
 * Reads from actionQueueStore for WS-pushed items and uses useActions('pending')
 * for initial hydration. Shows up to 3 items with approve/reject buttons.
 */

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, X } from 'lucide-react';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { useActionQueueStore } from '@/stores/actionQueueStore';
import { useActions, useApproveAction, useRejectAction } from '@/hooks/useActionQueue';

const RISK_COLORS: Record<string, string> = {
  low: 'bg-green-500/15 text-green-400 border-green-500/20',
  medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  critical: 'bg-red-500/15 text-red-400 border-red-500/20',
};

const MAX_VISIBLE = 3;

interface MergedAction {
  id: string;
  title: string;
  agent: string;
  riskLevel: string;
}

export function PendingApprovalsModule() {
  const navigate = useNavigate();
  const wsPending = useActionQueueStore((s) => s.pendingActions);
  const { data: apiActions } = useActions('pending');
  const approveMutation = useApproveAction();
  const rejectMutation = useRejectAction();

  // Merge WS-pushed items with API-fetched items (WS items take precedence, dedup by id)
  const actions = useMemo<MergedAction[]>(() => {
    const seen = new Set<string>();
    const result: MergedAction[] = [];

    // WS items first (more recent)
    for (const a of wsPending) {
      if (!seen.has(a.actionId)) {
        seen.add(a.actionId);
        result.push({
          id: a.actionId,
          title: a.title,
          agent: a.agent,
          riskLevel: a.riskLevel,
        });
      }
    }

    // API items as fallback
    if (apiActions) {
      for (const a of apiActions) {
        if (!seen.has(a.id)) {
          seen.add(a.id);
          result.push({
            id: a.id,
            title: a.title,
            agent: a.agent,
            riskLevel: a.risk_level,
          });
        }
      }
    }

    return result;
  }, [wsPending, apiActions]);

  if (actions.length === 0) return null;

  const visible = actions.slice(0, MAX_VISIBLE);
  const remaining = actions.length - MAX_VISIBLE;

  return (
    <div data-aria-id="intel-pending-approvals" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Pending Approvals
        <span
          className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full text-[10px] font-mono px-1"
          style={{ backgroundColor: 'var(--critical)', color: 'white' }}
        >
          {actions.length}
        </span>
      </h3>

      <div className="space-y-2">
        {visible.map((action) => {
          const riskClass = RISK_COLORS[action.riskLevel] ?? RISK_COLORS.medium;
          const isApproving = approveMutation.isPending && approveMutation.variables === action.id;
          const isRejecting = rejectMutation.isPending && rejectMutation.variables?.actionId === action.id;
          const isProcessing = isApproving || isRejecting;

          return (
            <div
              key={action.id}
              className="rounded-lg border px-3 py-2.5"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
              }}
            >
              <div className="flex items-start gap-2 mb-2">
                <AgentAvatar agentKey={action.agent} size={16} />
                <div className="min-w-0 flex-1">
                  <p
                    className="font-sans text-[12px] font-medium leading-tight truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {action.title}
                  </p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span
                      className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium border ${riskClass}`}
                    >
                      {action.riskLevel}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-1.5 justify-end">
                <button
                  onClick={() => rejectMutation.mutate({ actionId: action.id })}
                  disabled={isProcessing}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50"
                  style={{
                    color: 'var(--critical)',
                    backgroundColor: 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <X size={12} />
                  Reject
                </button>
                <button
                  onClick={() => approveMutation.mutate(action.id)}
                  disabled={isProcessing}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50"
                  style={{
                    color: 'var(--success)',
                    backgroundColor: 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <Check size={12} />
                  Approve
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {remaining > 0 && (
        <button
          onClick={() => navigate('/actions')}
          className="w-full text-center font-sans text-[11px] font-medium py-1.5 rounded transition-colors"
          style={{ color: 'var(--accent)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
        >
          View all ({actions.length})
        </button>
      )}
    </div>
  );
}
