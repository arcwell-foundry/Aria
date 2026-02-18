/**
 * UndoToast - Single undo toast with countdown timer
 *
 * Shows an action that was auto-executed with a countdown until the
 * undo window expires. User can click "Undo" to reverse the action.
 * Recalculates remaining time from absolute undo_deadline (drift-resistant).
 */

import { useState, useEffect } from 'react';
import { Clock, Loader2, Check } from 'lucide-react';
import type { UndoItem } from '@/stores/undoStore';

interface UndoToastProps {
  item: UndoItem;
  onUndo: (actionId: string) => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function UndoToast({ item, onUndo }: UndoToastProps) {
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const deadline = new Date(item.undo_deadline).getTime();
    return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
  });

  useEffect(() => {
    if (item.status !== 'active') return;

    const interval = setInterval(() => {
      const deadline = new Date(item.undo_deadline).getTime();
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setRemainingSeconds(remaining);
    }, 1000);

    return () => clearInterval(interval);
  }, [item.undo_deadline, item.status]);

  const progress =
    item.undo_duration_seconds > 0
      ? (remainingSeconds / item.undo_duration_seconds) * 100
      : 0;

  return (
    <div
      className="rounded-xl border overflow-hidden min-w-[340px] max-w-[420px]"
      style={{
        borderColor: 'rgba(46,102,255,0.3)',
        backgroundColor: 'var(--bg-elevated)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
      data-aria-id="undo-toast"
      data-action-id={item.action_id}
    >
      {/* Progress bar */}
      {item.status === 'active' && (
        <div
          className="h-1 transition-all duration-1000 ease-linear"
          style={{
            width: `${progress}%`,
            backgroundColor: 'var(--accent)',
          }}
        />
      )}

      {/* Content */}
      <div className="flex items-center gap-3 px-4 py-3">
        {item.status === 'active' && (
          <Clock className="w-4 h-4 shrink-0" style={{ color: 'var(--accent)' }} />
        )}
        {item.status === 'undoing' && (
          <Loader2
            className="w-4 h-4 shrink-0 animate-spin"
            style={{ color: 'var(--accent)' }}
          />
        )}
        {item.status === 'undone' && (
          <Check className="w-4 h-4 shrink-0" style={{ color: 'var(--success)' }} />
        )}
        {item.status === 'expired' && (
          <Check
            className="w-4 h-4 shrink-0"
            style={{ color: 'var(--text-secondary)' }}
          />
        )}

        <div className="flex-1 min-w-0">
          <p
            className="text-sm font-medium truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {item.title}
          </p>
          {item.status === 'active' && (
            <p
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {formatTime(remainingSeconds)} remaining
            </p>
          )}
          {item.status === 'undoing' && (
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Undoing&hellip;
            </p>
          )}
          {item.status === 'undone' && (
            <p className="text-xs" style={{ color: 'var(--success)' }}>
              Action reversed
            </p>
          )}
          {item.status === 'expired' && (
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Completed
            </p>
          )}
        </div>

        {item.status === 'active' && (
          <button
            type="button"
            onClick={() => onUndo(item.action_id)}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            Undo
          </button>
        )}
      </div>
    </div>
  );
}
