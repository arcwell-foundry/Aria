import { useState } from 'react';
import { Mail, Send, Pencil, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export interface EmailDraftData {
  to: string;
  subject: string;
  body: string;
  draft_id?: string;
  tone?: string;
}

export function EmailDraftCard({ data }: { data: EmailDraftData }) {
  const [expanded, setExpanded] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const navigate = useNavigate();

  const previewLines = data.body.split('\n').slice(0, 4).join('\n');
  const hasMore = data.body.split('\n').length > 4;

  const handleSend = async () => {
    setSending(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/communications/send', {
        draft_id: data.draft_id,
        to: data.to,
        subject: data.subject,
        body: data.body,
      });
      setSent(true);
    } catch {
      setSending(false);
    }
  };

  const handleEdit = () => {
    navigate(`/communications?draft=${data.draft_id || ''}`);
  };

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="email-draft-card"
    >
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <Mail className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Email Draft
        </span>
        {data.tone && (
          <span className="ml-auto text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
            {data.tone}
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-2">
        <div className="flex gap-2 text-xs">
          <span className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5" style={{ color: 'var(--text-secondary)' }}>
            To
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{data.to}</span>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5" style={{ color: 'var(--text-secondary)' }}>
            Re
          </span>
          <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{data.subject}</span>
        </div>

        <div
          className="mt-2 pt-2 text-xs whitespace-pre-wrap leading-relaxed"
          style={{
            borderTop: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          {expanded ? data.body : previewLines}
        </div>

        {hasMore && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider"
            style={{ color: 'var(--accent)' }}
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? 'Collapse' : 'Show full email'}
          </button>
        )}
      </div>

      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {!sent ? (
          <>
            <button
              type="button"
              disabled={sending}
              onClick={handleSend}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {sending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Send className="w-3 h-3" />
              )}
              Send
            </button>
            <button
              type="button"
              onClick={handleEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'transparent',
              }}
            >
              <Pencil className="w-3 h-3" />
              Edit
            </button>
          </>
        ) : (
          <span className="text-xs text-emerald-400 flex items-center gap-1.5">
            <Send className="w-3 h-3" />
            Sent
          </span>
        )}
      </div>
    </div>
  );
}
