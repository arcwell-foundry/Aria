/**
 * EmailDraftCard - Email draft preview with actions
 *
 * Renders when ARIA has drafted an email for user review.
 * Shows recipient, subject, body preview, tone indicator,
 * and Approve/Edit/Dismiss action buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Mail, Send, Edit2, X } from 'lucide-react';
import type { EmailDraftCardProps } from './schemas';

const toneColors = {
  formal: 'bg-info/10 text-info border-info/20',
  friendly: 'bg-success/10 text-success border-success/20',
  urgent: 'bg-critical/10 text-critical border-critical/20',
  neutral: 'bg-subtle text-secondary border-border',
};

export function EmailDraftCard({
  email_draft_id,
  to,
  subject,
  body,
  tone = 'neutral',
  context,
}: EmailDraftCardProps) {
  const onAction = useOnAction();

  const handleApprove = () => {
    onAction("Send Email", `User approved sending email ${email_draft_id} to ${to}`);
  };

  const handleEdit = () => {
    onAction("Edit Email", `User wants to edit email draft ${email_draft_id}`);
  };

  const handleDismiss = () => {
    onAction("Dismiss Email", `User dismissed email draft ${email_draft_id}`);
  };

  // Truncate body for preview
  const bodyPreview = body.length > 200 ? `${body.slice(0, 200)}...` : body;

  return (
    <div className="bg-elevated border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-subtle/30">
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-interactive" />
          <span className="text-sm font-medium text-content">Email Draft</span>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${toneColors[tone]}`}>
          {tone}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Context (why ARIA drafted this) */}
        {context && (
          <p className="text-xs text-secondary italic">
            {context}
          </p>
        )}

        {/* To */}
        <div className="flex items-start gap-2">
          <span className="text-xs text-secondary w-8 shrink-0">To:</span>
          <span className="text-sm text-content font-medium">{to}</span>
        </div>

        {/* Subject */}
        <div className="flex items-start gap-2">
          <span className="text-xs text-secondary w-8 shrink-0">Subj:</span>
          <span className="text-sm text-content">{subject}</span>
        </div>

        {/* Body Preview */}
        <div className="mt-3 p-3 bg-subtle/50 rounded-lg">
          <p className="text-sm text-content whitespace-pre-wrap">
            {bodyPreview}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleApprove}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          Send
        </button>
        <button
          onClick={handleEdit}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-elevated text-content border border-border rounded-lg hover:bg-subtle transition-colors"
        >
          <Edit2 className="w-3.5 h-3.5" />
          Edit
        </button>
        <button
          onClick={handleDismiss}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-secondary hover:text-content transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          Dismiss
        </button>
      </div>
    </div>
  );
}
