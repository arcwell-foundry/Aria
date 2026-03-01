/**
 * EmailDraftApprovalCard - Inline email draft approval in conversation thread
 *
 * Rendered when an `email_draft_approval` WebSocket event arrives.
 * Shows draft preview, confidence badge, style match indicator,
 * and ARIA's notes. User can approve, edit inline, or dismiss.
 */

import { useState, useCallback } from 'react';
import {
  Mail,
  Check,
  Pencil,
  X,
  ChevronDown,
  ChevronUp,
  Loader2,
  Info,
} from 'lucide-react';

export interface EmailDraftApprovalData {
  draft_id: string;
  recipient_name: string;
  recipient_email: string;
  subject: string;
  preview: string;
  full_body: string;
  confidence: number;
  style_match: number;
  aria_notes: string;
  context_sources: string[];
}

type CardStatus =
  | 'pending'
  | 'approving'
  | 'approved'
  | 'editing'
  | 'saving'
  | 'saved'
  | 'dismissing'
  | 'dismissed';

const CONFIDENCE_TIERS: Record<string, { bg: string; text: string; label: string }> = {
  HIGH: { bg: 'rgba(34,197,94,0.1)', text: 'var(--success)', label: 'HIGH' },
  MEDIUM: { bg: 'rgba(245,158,11,0.1)', text: '#F59E0B', label: 'MEDIUM' },
  LOW: { bg: 'rgba(239,68,68,0.1)', text: '#EF4444', label: 'LOW' },
};

function getConfidenceTier(confidence: number): string {
  if (confidence >= 0.8) return 'HIGH';
  if (confidence >= 0.5) return 'MEDIUM';
  return 'LOW';
}

function getStyleMatchColor(score: number): string {
  if (score >= 0.8) return 'var(--success)';
  if (score >= 0.5) return '#F59E0B';
  return '#EF4444';
}

export function EmailDraftApprovalCard({ data }: { data: EmailDraftApprovalData }) {
  const [status, setStatus] = useState<CardStatus>('pending');
  const [expanded, setExpanded] = useState(false);
  const [editBody, setEditBody] = useState('');

  const draftId = data?.draft_id ?? '';
  const recipientName = data?.recipient_name ?? '';
  const recipientEmail = data?.recipient_email ?? '';
  const subject = data?.subject ?? '';
  const preview = data?.preview ?? '';
  const fullBody = data?.full_body ?? '';
  const confidence = data?.confidence ?? 0;
  const styleMatch = data?.style_match ?? 0;
  const ariaNotes = data?.aria_notes ?? '';
  const contextSources = data?.context_sources ?? [];

  const tier = getConfidenceTier(confidence);
  const tierStyle = CONFIDENCE_TIERS[tier];
  const styleMatchColor = getStyleMatchColor(styleMatch);
  const styleMatchPct = Math.round(styleMatch * 100);

  const isResolved = status === 'approved' || status === 'dismissed' || status === 'saved';
  const isLoading = status === 'approving' || status === 'dismissing' || status === 'saving';

  const handleApprove = useCallback(async () => {
    setStatus('approving');
    try {
      const { approveDraft } = await import('@/api/drafts');
      await approveDraft(draftId);
      setStatus('approved');
    } catch {
      setStatus('pending');
    }
  }, [draftId]);

  const handleEdit = useCallback(() => {
    setEditBody(fullBody);
    setStatus('editing');
  }, [fullBody]);

  const handleSaveEdit = useCallback(async () => {
    setStatus('saving');
    try {
      const { updateDraft } = await import('@/api/drafts');
      await updateDraft(draftId, { body: editBody });
      setStatus('saved');
    } catch {
      setStatus('editing');
    }
  }, [draftId, editBody]);

  const handleCancelEdit = useCallback(() => {
    setStatus('pending');
    setEditBody('');
  }, []);

  const handleDismiss = useCallback(async () => {
    setStatus('dismissing');
    try {
      const { dismissDraft } = await import('@/api/drafts');
      await dismissDraft(draftId);
      setStatus('dismissed');
    } catch {
      setStatus('pending');
    }
  }, [draftId]);

  if (!data) return null;

  // Dismissed cards fade out
  if (status === 'dismissed') {
    return (
      <div
        className="rounded-lg border overflow-hidden opacity-40 transition-opacity duration-500"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        data-aria-id="email-draft-approval-card"
      >
        <div className="flex items-center gap-2 px-4 py-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <X className="w-3.5 h-3.5" />
          Draft dismissed
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: isResolved ? 'var(--border)' : 'var(--accent)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="email-draft-approval-card"
      data-draft-id={draftId}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: isResolved ? 'var(--bg-subtle)' : 'rgba(46,102,255,0.05)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Mail className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Draft Reply Ready
        </span>
        <span
          className="ml-auto text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
          style={{ backgroundColor: tierStyle.bg, color: tierStyle.text }}
        >
          {tierStyle.label}
        </span>
      </div>

      {/* Recipient & Subject */}
      <div className="px-4 py-3 space-y-1.5">
        <div className="flex gap-2 text-xs">
          <span
            className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5"
            style={{ color: 'var(--text-secondary)' }}
          >
            To
          </span>
          <span style={{ color: 'var(--text-primary)' }}>
            {recipientName}
            {recipientEmail && (
              <span className="ml-1" style={{ color: 'var(--text-secondary)' }}>
                &lt;{recipientEmail}&gt;
              </span>
            )}
          </span>
        </div>
        <div className="flex gap-2 text-xs">
          <span
            className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5"
            style={{ color: 'var(--text-secondary)' }}
          >
            Re
          </span>
          <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
            {subject}
          </span>
        </div>
      </div>

      {/* Body preview / full / edit */}
      <div
        className="px-4 pb-3"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {status === 'editing' || status === 'saving' ? (
          <div className="pt-3 space-y-2">
            <textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              rows={10}
              className="w-full text-xs leading-relaxed rounded border outline-none focus:border-[var(--accent)] px-3 py-2 resize-y"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
                color: 'var(--text-primary)',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') handleCancelEdit();
              }}
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={status === 'saving'}
                onClick={handleSaveEdit}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {status === 'saving' ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Check className="w-3 h-3" />
                )}
                Save Changes
              </button>
              <button
                type="button"
                disabled={status === 'saving'}
                onClick={handleCancelEdit}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{
                  borderColor: 'var(--border)',
                  color: 'var(--text-secondary)',
                  backgroundColor: 'transparent',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="pt-3">
            <div
              className="text-xs whitespace-pre-wrap leading-relaxed"
              style={{ color: 'var(--text-primary)' }}
            >
              {expanded ? fullBody : preview}
            </div>
            {fullBody && fullBody.length > (preview?.length ?? 0) && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1 mt-2 text-[10px] font-mono uppercase tracking-wider"
                style={{ color: 'var(--accent)' }}
              >
                {expanded ? (
                  <ChevronUp className="w-3 h-3" />
                ) : (
                  <ChevronDown className="w-3 h-3" />
                )}
                {expanded ? 'Collapse' : 'Show full email'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* ARIA Notes callout */}
      {ariaNotes && (
        <div
          className="mx-4 mb-3 rounded px-3 py-2"
          style={{ backgroundColor: 'rgba(46,102,255,0.05)', border: '1px solid rgba(46,102,255,0.1)' }}
        >
          <div className="flex items-start gap-2">
            <Info className="w-3 h-3 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
            <div>
              <span
                className="text-[10px] font-mono uppercase tracking-wider block mb-1"
                style={{ color: 'var(--accent)' }}
              >
                ARIA&apos;s Notes
              </span>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {ariaNotes}
              </p>
              {contextSources.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {contextSources.map((source, i) => (
                    <span
                      key={i}
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: 'var(--bg-subtle)',
                        color: 'var(--text-secondary)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {source}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Style match indicator */}
      <div className="mx-4 mb-3">
        <div className="flex items-center justify-between mb-1">
          <span
            className="text-[10px] font-mono uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Style Match
          </span>
          <span className="text-[10px] font-mono" style={{ color: styleMatchColor }}>
            {styleMatchPct}%
          </span>
        </div>
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${styleMatchPct}%`,
              backgroundColor: styleMatchColor,
            }}
          />
        </div>
      </div>

      {/* Action buttons */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {status === 'approved' && (
          <span className="text-xs flex items-center gap-1.5" style={{ color: 'var(--success)' }}>
            <Check className="w-3.5 h-3.5" />
            Approved &amp; saved to drafts
          </span>
        )}

        {status === 'saved' && (
          <span className="text-xs flex items-center gap-1.5" style={{ color: 'var(--success)' }}>
            <Check className="w-3.5 h-3.5" />
            Edits saved
          </span>
        )}

        {!isResolved && status !== 'editing' && status !== 'saving' && (
          <>
            <button
              type="button"
              disabled={isLoading}
              onClick={handleApprove}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {status === 'approving' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Check className="w-3 h-3" />
              )}
              Approve &amp; Save to Drafts
            </button>
            <button
              type="button"
              disabled={isLoading}
              onClick={handleEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'transparent',
              }}
            >
              <Pencil className="w-3 h-3" />
              Edit
            </button>
            <button
              type="button"
              disabled={isLoading}
              onClick={handleDismiss}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'transparent',
              }}
            >
              {status === 'dismissing' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <X className="w-3 h-3" />
              )}
              Dismiss
            </button>
          </>
        )}
      </div>
    </div>
  );
}
