/**
 * ActionApprovalCard - Inline action approval in conversation thread
 *
 * Rendered when an `action.pending` WebSocket event arrives.
 * Shows action title, agent, risk level, and ARIA's reasoning.
 * User can approve or reject directly in the conversation.
 */

import { useState } from 'react';
import { Shield, Check, X, Zap, Loader2 } from 'lucide-react';
import { approveAction, rejectAction } from '@/api/actionQueue';

export interface ActionApprovalData {
  action_id: string;
  title: string;
  description?: string;
  agent: string;
  risk_level: string;
  reasoning?: string;
}

const RISK_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  low: { bg: 'rgba(34,197,94,0.1)', text: 'var(--success)', label: 'Low Risk' },
  medium: { bg: 'rgba(245,158,11,0.1)', text: '#F59E0B', label: 'Medium Risk' },
  high: { bg: 'rgba(239,68,68,0.1)', text: '#EF4444', label: 'High Risk' },
  critical: { bg: 'rgba(220,38,38,0.15)', text: '#DC2626', label: 'Critical' },
};

export function ActionApprovalCard({ data }: { data: ActionApprovalData }) {
  const [status, setStatus] = useState<'pending' | 'approving' | 'approved' | 'rejecting' | 'rejected'>('pending');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  const riskStyle = RISK_STYLES[data.risk_level] || RISK_STYLES.high;

  const handleApprove = async () => {
    setStatus('approving');
    try {
      await approveAction(data.action_id);
      setStatus('approved');
    } catch {
      setStatus('pending');
    }
  };

  const handleReject = async () => {
    setStatus('rejecting');
    try {
      await rejectAction(data.action_id, rejectReason || undefined);
      setStatus('rejected');
    } catch {
      setStatus('pending');
    }
  };

  const isResolved = status === 'approved' || status === 'rejected';

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: isResolved ? 'var(--border)' : 'var(--accent)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="action-approval-card"
      data-action-id={data.action_id}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: isResolved
            ? 'var(--bg-subtle)'
            : 'rgba(46,102,255,0.05)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Shield className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Action Approval Required
        </span>
        <span
          className="ml-auto text-[11px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: riskStyle.bg, color: riskStyle.text }}
        >
          {riskStyle.label}
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <div className="flex items-start gap-2 mb-2">
          <Zap className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {data.title}
            </p>
            {data.description && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                {data.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono mb-2" style={{ color: 'var(--text-secondary)' }}>
          <span>Agent: {data.agent}</span>
        </div>

        {data.reasoning && (
          <p className="text-xs italic mb-3" style={{ color: 'var(--text-secondary)' }}>
            {data.reasoning}
          </p>
        )}

        {/* Status or actions */}
        {status === 'approved' && (
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--success)' }}>
            <Check className="w-3.5 h-3.5" />
            Approved
          </div>
        )}

        {status === 'rejected' && (
          <div className="flex items-center gap-2 text-xs" style={{ color: '#EF4444' }}>
            <X className="w-3.5 h-3.5" />
            Rejected{rejectReason ? `: ${rejectReason}` : ''}
          </div>
        )}

        {!isResolved && (
          <div className="space-y-2">
            {showRejectInput && (
              <input
                type="text"
                placeholder="Reason (optional)"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                className="w-full text-xs px-3 py-1.5 rounded border outline-none focus:border-[var(--accent)]"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-primary)',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleReject();
                }}
              />
            )}
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={status === 'approving' || status === 'rejecting'}
                onClick={handleApprove}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {status === 'approving' ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Check className="w-3 h-3" />
                )}
                Approve
              </button>
              <button
                type="button"
                disabled={status === 'approving' || status === 'rejecting'}
                onClick={() => {
                  if (showRejectInput) {
                    handleReject();
                  } else {
                    setShowRejectInput(true);
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{
                  borderColor: 'var(--border)',
                  color: 'var(--text-secondary)',
                  backgroundColor: 'transparent',
                }}
              >
                {status === 'rejecting' ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <X className="w-3 h-3" />
                )}
                Reject
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
