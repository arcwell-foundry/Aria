import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Mail, X } from 'lucide-react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS, type AriaMessagePayload } from '@/types/chat';

interface UrgentEmail {
  id: string;
  email_id: string;
  sender: string;
  sender_email: string;
  subject: string;
  urgency_reason: string;
  draft_id: string | null;
  draft_saved: boolean;
  topic_summary: string;
  timestamp: string;
}

const AUTO_DISMISS_MS = 15_000;
const MAX_VISIBLE = 3;

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '\u2026' : text;
}

function UrgentEmailItem({
  email,
  onDismiss,
}: {
  email: UrgentEmail;
  onDismiss: (id: string) => void;
}) {
  const navigate = useNavigate();

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(email.id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [email.id, onDismiss]);

  const handleViewDraft = useCallback(() => {
    onDismiss(email.id);
    if (email.draft_id) {
      navigate(`/communications/drafts/${email.draft_id}`);
    }
  }, [email.id, email.draft_id, navigate, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 100, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className="pointer-events-auto w-80 rounded-lg border border-white/10 shadow-xl backdrop-blur-sm"
      style={{ backgroundColor: 'var(--bg-elevated, #1a1a2e)' }}
    >
      {/* Amber accent border */}
      <div className="flex rounded-lg overflow-hidden">
        <div className="w-1 shrink-0 bg-amber-500" />

        <div className="flex-1 p-4">
          {/* Header row */}
          <div className="flex items-start gap-2">
            <Mail size={16} className="mt-0.5 shrink-0 text-amber-400" strokeWidth={1.5} />
            <div className="flex-1 min-w-0">
              <p
                className="text-sm font-medium truncate"
                style={{ color: 'var(--text-primary, #e2e8f0)' }}
              >
                {email.sender}
              </p>
              <p
                className="text-xs truncate mt-0.5"
                style={{ color: 'var(--text-secondary, #94a3b8)' }}
              >
                {truncate(email.subject, 60)}
              </p>
            </div>
            <button
              onClick={() => onDismiss(email.id)}
              className="shrink-0 rounded p-0.5 text-gray-500 transition-colors hover:text-gray-300 hover:bg-white/5"
              aria-label="Dismiss notification"
            >
              <X size={14} strokeWidth={1.5} />
            </button>
          </div>

          {/* Urgency reason */}
          <p className="mt-2 text-xs text-amber-400/80">{email.urgency_reason}</p>

          {/* Actions */}
          <div className="mt-3 flex items-center gap-2">
            {email.draft_id && (
              <button
                onClick={handleViewDraft}
                className="rounded-md bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-300 transition-colors hover:bg-amber-500/25"
              >
                View Draft
              </button>
            )}
            <button
              onClick={() => onDismiss(email.id)}
              className="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium transition-colors hover:bg-white/10"
              style={{ color: 'var(--text-secondary, #94a3b8)' }}
            >
              Dismiss
            </button>
          </div>

          {/* Auto-dismiss progress */}
          <div className="mt-3 h-0.5 w-full rounded-full bg-white/5 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-amber-500/40"
              initial={{ width: '100%' }}
              animate={{ width: '0%' }}
              transition={{ duration: AUTO_DISMISS_MS / 1000, ease: 'linear' }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function UrgentEmailNotification() {
  const [emails, setEmails] = useState<UrgentEmail[]>([]);

  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      if (!payload || typeof payload !== 'object') return;
      const data = payload as AriaMessagePayload;
      const richContent = data.rich_content;
      if (!Array.isArray(richContent)) return;

      for (const item of richContent) {
        // Backend sends rich_content items as flat objects with type + fields
        const raw = item as unknown as Record<string, unknown>;
        if (raw.type !== 'urgent_email') continue;

        const urgentEmail: UrgentEmail = {
          id: `urgent-${raw.email_id ?? Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          email_id: String(raw.email_id ?? ''),
          sender: String(raw.sender ?? 'Unknown'),
          sender_email: String(raw.sender_email ?? ''),
          subject: String(raw.subject ?? '(No subject)'),
          urgency_reason: String(raw.urgency_reason ?? 'Marked urgent'),
          draft_id: raw.draft_id ? String(raw.draft_id) : null,
          draft_saved: Boolean(raw.draft_saved),
          topic_summary: String(raw.topic_summary ?? ''),
          timestamp: String(raw.timestamp ?? new Date().toISOString()),
        };

        setEmails((prev) => {
          // Deduplicate by email_id
          if (prev.some((e) => e.email_id === urgentEmail.email_id)) return prev;
          const updated = [...prev, urgentEmail];
          // Keep only the most recent MAX_VISIBLE
          return updated.length > MAX_VISIBLE ? updated.slice(-MAX_VISIBLE) : updated;
        });
      }
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage as (p: unknown) => void);
    };
  }, []);

  const handleDismiss = useCallback((id: string) => {
    setEmails((prev) => prev.filter((e) => e.id !== id));
  }, []);

  return (
    <div className="fixed top-16 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {emails.map((email) => (
          <UrgentEmailItem key={email.id} email={email} onDismiss={handleDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}
