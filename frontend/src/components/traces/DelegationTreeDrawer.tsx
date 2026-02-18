import { useEffect, useRef, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, AlertCircle, RefreshCw, Inbox } from 'lucide-react';
import { useTraceTree } from '@/hooks/useTraces';
import { TraceSummary } from './TraceSummary';
import { TraceNode } from './TraceNode';

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function DrawerSkeleton() {
  return (
    <div className="space-y-4 animate-pulse p-1">
      {/* Summary skeleton */}
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-16 rounded-lg"
            style={{ backgroundColor: 'var(--bg-subtle)' }}
          />
        ))}
      </div>
      {/* Trace skeletons */}
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex gap-3">
          <div
            className="w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0"
            style={{ backgroundColor: 'var(--border)' }}
          />
          <div
            className="flex-1 h-20 rounded-lg"
            style={{ backgroundColor: 'var(--bg-subtle)' }}
          />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DelegationTreeDrawer
// ---------------------------------------------------------------------------

interface DelegationTreeDrawerProps {
  goalId: string | null;
  goalTitle: string;
  onClose: () => void;
}

export function DelegationTreeDrawer({
  goalId,
  goalTitle,
  onClose,
}: DelegationTreeDrawerProps) {
  const isOpen = goalId != null;
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const { data, isLoading, error, refetch } = useTraceTree(goalId);

  // Auto-focus close button on open
  useEffect(() => {
    if (isOpen) {
      // Small delay to let animation start
      const timer = setTimeout(() => closeButtonRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Escape key to close
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    },
    [isOpen, onClose]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Set inert on content behind drawer
  useEffect(() => {
    const main = document.getElementById('main-content');
    if (main) {
      if (isOpen) {
        main.setAttribute('inert', '');
      } else {
        main.removeAttribute('inert');
      }
    }
    return () => {
      main?.removeAttribute('inert');
    };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40"
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.4)' }}
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Drawer panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            role="dialog"
            aria-label={`Delegation tree for ${goalTitle}`}
            aria-modal="true"
            className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-[500px] flex flex-col shadow-2xl"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            {/* Header */}
            <div
              className="flex-shrink-0 border-b px-5 py-4"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p
                    className="text-xs font-mono uppercase tracking-wider mb-1"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    Delegation Tree
                  </p>
                  <h2
                    className="font-display text-lg italic truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {goalTitle}
                  </h2>
                </div>
                <button
                  ref={closeButtonRef}
                  onClick={onClose}
                  className="flex-shrink-0 p-1.5 rounded-lg transition-colors hover:bg-[var(--bg-subtle)]"
                  style={{ color: 'var(--text-secondary)' }}
                  aria-label="Close delegation tree"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Summary */}
              {data?.summary && (
                <div className="mt-3">
                  <TraceSummary summary={data.summary} mode="full" />
                </div>
              )}
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {/* Loading */}
              {isLoading && <DrawerSkeleton />}

              {/* Error */}
              {error && !isLoading && (
                <div className="flex flex-col items-center gap-3 py-12 text-center">
                  <AlertCircle
                    className="w-8 h-8"
                    style={{ color: 'var(--critical)' }}
                  />
                  <p
                    className="text-sm"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    Failed to load delegation traces.
                  </p>
                  <button
                    onClick={() => refetch()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--bg-subtle)]"
                    style={{ color: 'var(--accent)' }}
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Retry
                  </button>
                </div>
              )}

              {/* Empty state */}
              {!isLoading && !error && data?.traces.length === 0 && (
                <div className="flex flex-col items-center gap-3 py-12 text-center">
                  <Inbox
                    className="w-8 h-8 opacity-50"
                    style={{ color: 'var(--text-secondary)' }}
                  />
                  <p
                    className="text-sm"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    No delegation traces found for this goal.
                  </p>
                </div>
              )}

              {/* Trace list */}
              {!isLoading && !error && data && data.traces.length > 0 && (
                <div>
                  {data.traces.map((trace, idx) => (
                    <TraceNode
                      key={trace.trace_id}
                      trace={trace}
                      allTraces={data.traces}
                      isLast={idx === data.traces.length - 1}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div
              className="flex-shrink-0 border-t px-5 py-3 text-center"
              style={{ borderColor: 'var(--border)' }}
            >
              <p
                className="text-[10px] font-mono"
                style={{ color: 'var(--text-secondary)', opacity: 0.6 }}
              >
                Powered by ARIA's delegation trace system
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
