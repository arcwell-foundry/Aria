/**
 * PendingApprovalsModule — Compact intel panel module showing pending actions.
 *
 * Reads from actionQueueStore for WS-pushed items and uses useActions('pending')
 * for initial hydration. Shows up to 3 items with approve/reject buttons.
 */

import { useMemo, useState } from 'react';
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
  description: string;
  payload: Record<string, unknown>;
  reasoning: string;
}

export function PendingApprovalsModule() {
  const navigate = useNavigate();
  const wsPending = useActionQueueStore((s) => s.pendingActions);
  const { data: apiActions } = useActions('pending');
  const approveMutation = useApproveAction();
  const rejectMutation = useRejectAction();
  const [expandedId, setExpandedId] = useState<string | null>(null);

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
          description: (a as Record<string, unknown>).description as string ?? '',
          payload: {},
          reasoning: '',
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
            description: a.description ?? '',
            payload: a.payload ?? {},
            reasoning: a.reasoning ?? '',
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
          const isExpanded = expandedId === action.id;

          const payload = action.payload as Record<string, unknown>;
          const competitiveContext = (payload?.competitive_context ?? {}) as Record<string, unknown>;
          const differentiation = (competitiveContext?.differentiation ?? []) as string[];
          const weaknesses = (competitiveContext?.weaknesses ?? []) as string[];
          const pricing = (competitiveContext?.pricing ?? {}) as Record<string, unknown>;
          const hasContext = differentiation.length > 0 || weaknesses.length > 0;

          return (
            <div
              key={action.id}
              className={`rounded-lg border transition-all duration-200 cursor-pointer ${
                isExpanded ? 'ring-1 ring-[var(--accent)]/30' : ''
              }`}
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
              }}
              onClick={() => setExpandedId(isExpanded ? null : action.id)}
            >
              <div className="px-3 py-2.5">
                <div className="flex items-start gap-2 mb-2">
                  <AgentAvatar agentKey={action.agent} size={16} />
                  <div className="min-w-0 flex-1">
                    <p
                      className="font-sans text-[12px] font-medium leading-tight"
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

                {isExpanded && (
                  <div
                    className="mt-2 pt-2 border-t space-y-2"
                    style={{ borderColor: 'var(--border)' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {action.description && (
                      <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                        {action.description}
                      </p>
                    )}
                    {hasContext && (
                      <div className="space-y-1">
                        <p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                          Competitive Context
                        </p>
                        {differentiation.length > 0 && (
                          <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                            <span style={{ color: 'var(--success)' }}>Advantages: </span>
                            <span style={{ color: 'var(--text-primary)' }}>
                              {differentiation.map(String).join('; ')}
                            </span>
                          </div>
                        )}
                        {weaknesses.length > 0 && (
                          <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                            <span style={{ color: 'var(--warning)' }}>Weaknesses: </span>
                            <span style={{ color: 'var(--text-primary)' }}>
                              {weaknesses.map(String).join('; ')}
                            </span>
                          </div>
                        )}
                        {pricing && (pricing.range || pricing.notes) && (
                          <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                            <span style={{ color: 'var(--accent)' }}>Pricing: </span>
                            <span style={{ color: 'var(--text-primary)' }}>
                              {[pricing.range, pricing.notes].filter(Boolean).map(String).join(' — ')}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                    {action.reasoning && (
                      <p className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>
                        {action.reasoning}
                      </p>
                    )}
                  </div>
                )}

                <div
                  className="flex items-center gap-1.5 justify-end mt-2"
                  onClick={(e) => e.stopPropagation()}
                >
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
