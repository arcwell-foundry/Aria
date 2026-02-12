/**
 * DraftDetailPage - Email draft editor
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Breadcrumb navigation
 * - Header with subject line, status badge, action buttons
 * - Email preview section (To, Subject, Body)
 * - Bottom actions bar: Send Email, Save Draft, Regenerate
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft,
  Send,
  Save,
  RefreshCw,
  Eye,
  CheckCircle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useDraft, useUpdateDraft, useSendDraft, useRegenerateDraft } from '@/hooks/useDrafts';
import type { EmailDraftTone } from '@/api/drafts';

// Status badge styles
const STATUS_STYLES: Record<string, { label: string; bg: string; text: string }> = {
  draft: { label: 'DRAFTING', bg: 'var(--accent)', text: 'white' },
  sent: { label: 'SENT', bg: 'var(--success)', text: 'white' },
  failed: { label: 'FAILED', bg: 'var(--critical)', text: 'white' },
};

// Tone options
const TONE_OPTIONS: { value: EmailDraftTone; label: string }[] = [
  { value: 'formal', label: 'Professional' },
  { value: 'friendly', label: 'Casual' },
  { value: 'urgent', label: 'Urgent' },
];

interface DraftDetailPageProps {
  draftId: string;
}

export function DraftDetailPage({ draftId }: DraftDetailPageProps) {
  const navigate = useNavigate();
  const [isEditing, setIsEditing] = useState(false);
  const [editedRecipient, setEditedRecipient] = useState('');
  const [editedSubject, setEditedSubject] = useState('');

  // Queries and mutations
  const { data: draft, isLoading, error } = useDraft(draftId);
  const updateDraft = useUpdateDraft();
  const sendDraft = useSendDraft();
  const regenerateDraft = useRegenerateDraft();

  const isSaving = updateDraft.isPending;
  const isSending = sendDraft.isPending;
  const isRegenerating = regenerateDraft.isPending;
  const isBusy = isSaving || isSending || isRegenerating;

  // Initialize edited values when draft loads
  if (draft && !editedRecipient && !editedSubject) {
    setEditedRecipient(draft.recipient_email);
    setEditedSubject(draft.subject);
  }

  // Handlers
  const handleSave = async () => {
    if (!draft) return;
    await updateDraft.mutateAsync({
      draftId,
      data: {
        recipient_email: editedRecipient,
        subject: editedSubject,
      },
    });
    setIsEditing(false);
  };

  const handleSend = async () => {
    if (!draft) return;
    await sendDraft.mutateAsync(draftId);
    navigate('/communications');
  };

  const handleRegenerate = async (tone?: EmailDraftTone) => {
    await regenerateDraft.mutateAsync({
      draftId,
      data: tone ? { tone } : undefined,
    });
  };

  // Loading state
  if (isLoading) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="flex-1 overflow-y-auto p-8">
          <div className="animate-pulse space-y-6">
            <div className="h-4 w-32 bg-[var(--border)] rounded" />
            <div className="h-8 w-2/3 bg-[var(--border)] rounded" />
            <div className="border border-[var(--border)] rounded-lg p-6 space-y-4">
              <div className="h-4 w-1/2 bg-[var(--border)] rounded" />
              <div className="h-4 w-full bg-[var(--border)] rounded" />
              <div className="h-4 w-3/4 bg-[var(--border)] rounded" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !draft) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="flex-1 overflow-y-auto p-8">
          <button
            onClick={() => navigate('/communications')}
            className="flex items-center gap-2 text-sm mb-6 hover:opacity-80 transition-opacity"
            style={{ color: 'var(--text-secondary)' }}
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Drafts
          </button>
          <div
            className="text-center py-8"
            style={{ color: 'var(--text-secondary)' }}
          >
            Error loading draft. Please try again.
          </div>
        </div>
      </div>
    );
  }

  const statusStyle = STATUS_STYLES[draft.status] || STATUS_STYLES.draft;
  const isSent = draft.status === 'sent';

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Breadcrumb */}
        <button
          onClick={() => navigate('/communications')}
          className="flex items-center gap-2 text-sm mb-6 hover:opacity-80 transition-opacity"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ChevronLeft className="w-4 h-4" />
          Drafts
        </button>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2">
              <h1
                className="font-display text-2xl italic truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {draft.subject}
              </h1>
              <span
                className="px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0"
                style={{
                  backgroundColor: statusStyle.bg,
                  color: statusStyle.text,
                }}
              >
                {statusStyle.label}
              </span>
            </div>
            {draft.recipient_name && (
              <p
                className="text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                To: {draft.recipient_name} &lt;{draft.recipient_email}&gt;
              </p>
            )}
          </div>

          {/* Action buttons */}
          {!isSent && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => setIsEditing(!isEditing)}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  isEditing
                    ? 'bg-[var(--accent)] text-white'
                    : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
                )}
                style={{
                  color: isEditing ? 'white' : 'var(--text-primary)',
                }}
              >
                <Eye className="w-4 h-4 inline-block mr-2" />
                {isEditing ? 'Preview' : 'Edit'}
              </button>
            </div>
          )}
        </div>

        {/* Email Preview Section */}
        <div
          className="border rounded-lg overflow-hidden"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          {/* Email Header */}
          <div
            className="border-b p-4 space-y-3"
            style={{ borderColor: 'var(--border)' }}
          >
            {/* To field */}
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-medium w-12"
                style={{ color: 'var(--text-secondary)' }}
              >
                To:
              </span>
              {isEditing ? (
                <input
                  type="email"
                  value={editedRecipient}
                  onChange={(e) => setEditedRecipient(e.target.value)}
                  className={cn(
                    'flex-1 px-3 py-1.5 rounded border text-sm',
                    'border-[var(--border)] bg-[var(--bg-subtle)]',
                    'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
                  )}
                  style={{ color: 'var(--text-primary)' }}
                />
              ) : (
                <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                  {draft.recipient_name ? `${draft.recipient_name} <${draft.recipient_email}>` : draft.recipient_email}
                </span>
              )}
            </div>

            {/* Subject field */}
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-medium w-12"
                style={{ color: 'var(--text-secondary)' }}
              >
                Subject:
              </span>
              {isEditing ? (
                <input
                  type="text"
                  value={editedSubject}
                  onChange={(e) => setEditedSubject(e.target.value)}
                  className={cn(
                    'flex-1 px-3 py-1.5 rounded border text-sm',
                    'border-[var(--border)] bg-[var(--bg-subtle)]',
                    'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
                  )}
                  style={{ color: 'var(--text-primary)' }}
                />
              ) : (
                <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                  {draft.subject}
                </span>
              )}
            </div>

            {/* Tone selector */}
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-medium w-12"
                style={{ color: 'var(--text-secondary)' }}
              >
                Tone:
              </span>
              <div className="flex items-center gap-2">
                {TONE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => !isBusy && handleRegenerate(option.value)}
                    disabled={isBusy || isSent}
                    className={cn(
                      'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                      draft.tone === option.value
                        ? 'bg-[var(--accent)] text-white'
                        : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
                    )}
                    style={{
                      color: draft.tone === option.value ? 'white' : 'var(--text-secondary)',
                      opacity: isBusy || isSent ? 0.5 : 1,
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Email Body */}
          <div className="p-6">
            <div
              className="prose prose-sm max-w-none"
              style={{ color: 'var(--text-primary)' }}
            >
              {/* Render body with line breaks */}
              {draft.body.split('\n').map((paragraph, i) => (
                <p key={i} className="mb-4 last:mb-0 leading-relaxed">
                  {paragraph || '\u00A0'}
                </p>
              ))}
            </div>
          </div>
        </div>

        {/* Refinement highlights indicator */}
        {draft.style_match_score !== undefined && (
          <div
            className="mt-4 flex items-center gap-2 text-sm"
            style={{ color: 'var(--text-secondary)' }}
          >
            <CheckCircle className="w-4 h-4" style={{ color: 'var(--success)' }} />
            Style match score: {Math.round(draft.style_match_score * 100)}%
          </div>
        )}
      </div>

      {/* Bottom Actions Bar */}
      {!isSent && (
        <div
          className="flex-shrink-0 border-t p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center justify-between gap-4">
            {/* Left: Regenerate */}
            <button
              onClick={() => handleRegenerate()}
              disabled={isBusy}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                'border border-[var(--border)] transition-colors',
                'hover:bg-[var(--bg-subtle)]',
                isBusy && 'opacity-50 cursor-not-allowed'
              )}
              style={{ color: 'var(--text-primary)' }}
            >
              {isRegenerating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              Regenerate
            </button>

            {/* Right: Save and Send */}
            <div className="flex items-center gap-3">
              {isEditing && (
                <button
                  onClick={handleSave}
                  disabled={isBusy}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                    'border border-[var(--border)] transition-colors',
                    'hover:bg-[var(--bg-subtle)]',
                    isBusy && 'opacity-50 cursor-not-allowed'
                  )}
                  style={{ color: 'var(--text-primary)' }}
                >
                  {isSaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  Save Draft
                </button>
              )}

              <button
                onClick={handleSend}
                disabled={isBusy}
                className={cn(
                  'flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium',
                  'transition-colors',
                  isBusy && 'opacity-50 cursor-not-allowed'
                )}
                style={{
                  backgroundColor: 'var(--accent)',
                  color: 'white',
                }}
              >
                {isSending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Send Email
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sent state footer */}
      {isSent && draft.sent_at && (
        <div
          className="flex-shrink-0 border-t p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center justify-center gap-2 text-sm" style={{ color: 'var(--success)' }}>
            <CheckCircle className="w-4 h-4" />
            Email sent on {new Date(draft.sent_at).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}
