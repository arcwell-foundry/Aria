import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useUndoAction } from '@/hooks/useActionQueue';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

interface UndoableAction {
  action_id: string;
  title: string;
  agent: string;
  undo_deadline: string;
  countdown_seconds: number;
}

const AGENT_LABELS: Record<string, string> = {
  scout: 'Scout',
  analyst: 'Analyst',
  hunter: 'Hunter',
  operator: 'Operator',
  scribe: 'Scribe',
  strategist: 'Strategist',
};

const AGENT_COLORS: Record<string, string> = {
  scout: 'bg-blue-500/20 text-blue-400',
  analyst: 'bg-purple-500/20 text-purple-400',
  hunter: 'bg-green-500/20 text-green-400',
  operator: 'bg-orange-500/20 text-orange-400',
  scribe: 'bg-pink-500/20 text-pink-400',
  strategist: 'bg-yellow-500/20 text-yellow-400',
};

function UndoToastItem({
  action,
  onDismiss,
}: {
  action: UndoableAction;
  onDismiss: (id: string) => void;
}) {
  const [secondsLeft, setSecondsLeft] = useState(() => {
    const deadline = new Date(action.undo_deadline).getTime();
    const now = Date.now();
    return Math.max(0, Math.ceil((deadline - now) / 1000));
  });

  const undoMutation = useUndoAction();

  useEffect(() => {
    const interval = setInterval(() => {
      const deadline = new Date(action.undo_deadline).getTime();
      const now = Date.now();
      const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));
      setSecondsLeft(remaining);

      if (remaining <= 0) {
        clearInterval(interval);
        onDismiss(action.action_id);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [action.undo_deadline, action.action_id, onDismiss]);

  const handleUndo = useCallback(() => {
    undoMutation.mutate(action.action_id, {
      onSettled: () => onDismiss(action.action_id),
    });
  }, [action.action_id, undoMutation, onDismiss]);

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const timeDisplay = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, '0')}` : `${seconds}s`;
  const progress = secondsLeft / action.countdown_seconds;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 100, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className="pointer-events-auto w-80 rounded-lg border border-white/10 bg-gray-900/95 p-4 shadow-xl backdrop-blur-sm"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ${AGENT_COLORS[action.agent] ?? 'bg-gray-500/20 text-gray-400'}`}
            >
              {AGENT_LABELS[action.agent] ?? action.agent}
            </span>
            <span className="text-xs text-gray-500">executed</span>
          </div>
          <p className="text-sm font-medium text-gray-100 truncate">{action.title}</p>
        </div>
        <span className="text-xs tabular-nums text-gray-400 shrink-0">{timeDisplay}</span>
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-0.5 w-full rounded-full bg-gray-700 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-blue-500"
          initial={{ width: '100%' }}
          animate={{ width: `${progress * 100}%` }}
          transition={{ duration: 1, ease: 'linear' }}
        />
      </div>

      {/* Undo button */}
      <div className="mt-3 flex justify-end">
        <button
          onClick={handleUndo}
          disabled={undoMutation.isPending}
          className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {undoMutation.isPending ? 'Undoing...' : 'Undo'}
        </button>
      </div>
    </motion.div>
  );
}

export function UndoToastContainer() {
  const [actions, setActions] = useState<UndoableAction[]>([]);

  useEffect(() => {
    const handleExecuted = (payload: unknown) => {
      const data = payload as UndoableAction;
      setActions((prev) => {
        // Prevent duplicates
        if (prev.some((a) => a.action_id === data.action_id)) return prev;
        return [...prev, data];
      });
    };

    const handleUndone = (payload: unknown) => {
      const data = payload as { action_id: string };
      setActions((prev) => prev.filter((a) => a.action_id !== data.action_id));
    };

    wsManager.on(WS_EVENTS.ACTION_EXECUTED_WITH_UNDO, handleExecuted);
    wsManager.on(WS_EVENTS.ACTION_UNDONE, handleUndone);

    return () => {
      wsManager.off(WS_EVENTS.ACTION_EXECUTED_WITH_UNDO, handleExecuted as (p: unknown) => void);
      wsManager.off(WS_EVENTS.ACTION_UNDONE, handleUndone as (p: unknown) => void);
    };
  }, []);

  const handleDismiss = useCallback((actionId: string) => {
    setActions((prev) => prev.filter((a) => a.action_id !== actionId));
  }, []);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {actions.map((action) => (
          <UndoToastItem key={action.action_id} action={action} onDismiss={handleDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}
