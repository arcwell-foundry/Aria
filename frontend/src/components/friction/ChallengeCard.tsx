import { useState } from 'react';
import { motion } from 'framer-motion';
import { respondToFriction } from '@/api/friction';

export interface ChallengeCardProps {
  frictionId: string;
  level: 'flag' | 'challenge' | 'refuse';
  reasoning: string;
  userMessage: string;
  onApprove?: () => void;
  onModify?: () => void;
  onCancel?: () => void;
}

const LEVEL_STYLES: Record<
  ChallengeCardProps['level'],
  { bg: string; border: string; icon: string; label: string }
> = {
  flag: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    icon: 'info',
    label: 'Note',
  },
  challenge: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    icon: 'warning',
    label: 'Pushback',
  },
  refuse: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    icon: 'refuse',
    label: 'Declined',
  },
};

function FrictionIcon({ type, className }: { type: string; className?: string }) {
  const cls = className ?? 'h-5 w-5';
  switch (type) {
    case 'info':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'warning':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'refuse':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
            clipRule="evenodd"
          />
        </svg>
      );
    default:
      return null;
  }
}

export function ChallengeCard({
  frictionId,
  level,
  reasoning,
  userMessage,
  onApprove,
  onModify,
  onCancel,
}: ChallengeCardProps) {
  const [isResponding, setIsResponding] = useState(false);
  const [resolved, setResolved] = useState(false);
  const style = LEVEL_STYLES[level];

  const handleResponse = async (response: 'approve' | 'modify' | 'cancel') => {
    setIsResponding(true);
    try {
      await respondToFriction(frictionId, response);
      setResolved(true);

      if (response === 'approve') onApprove?.();
      else if (response === 'modify') onModify?.();
      else onCancel?.();
    } catch {
      // Let the global error handler surface the issue
    } finally {
      setIsResponding(false);
    }
  };

  if (resolved) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={`rounded-lg border ${style.border} ${style.bg} p-4`}
      data-aria-id={`friction-card-${level}`}
    >
      {/* Header */}
      <div className="mb-2 flex items-center gap-2">
        <FrictionIcon type={style.icon} className="h-5 w-5 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
          {style.label}
        </span>
      </div>

      {/* ARIA's message */}
      <p className="text-sm leading-relaxed text-[var(--text-content)]">{userMessage}</p>

      {/* Internal reasoning — hidden from the main display, available for audit */}
      <input type="hidden" data-friction-reasoning={reasoning} />

      {/* Action buttons */}
      <div className="mt-3 flex items-center gap-2">
        {level === 'challenge' && (
          <>
            <button
              onClick={() => handleResponse('approve')}
              disabled={isResponding}
              className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-[var(--text-content)] transition-colors hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Proceed Anyway
            </button>
            <button
              onClick={() => handleResponse('modify')}
              disabled={isResponding}
              className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-[var(--text-content)] transition-colors hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Modify Request
            </button>
            <button
              onClick={() => handleResponse('cancel')}
              disabled={isResponding}
              className="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
          </>
        )}

        {level === 'refuse' && (
          <button
            onClick={() => handleResponse('cancel')}
            disabled={isResponding}
            className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-[var(--text-content)] transition-colors hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Understood
          </button>
        )}
      </div>

      {/* flag level renders no buttons — informational only */}
    </motion.div>
  );
}
