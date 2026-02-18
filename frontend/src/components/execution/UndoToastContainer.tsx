/**
 * UndoToastContainer - Stacked toast container mounted at app root
 *
 * Positioned fixed at bottom-center. Uses framer-motion AnimatePresence
 * for smooth enter/exit animations. Multiple toasts stack vertically
 * with newest at the bottom.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { useUndoStore } from '@/stores/undoStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { UndoToast } from './UndoToast';

export function UndoToastContainer() {
  const items = useUndoStore((s) => s.items);
  const markUndoing = useUndoStore((s) => s.markUndoing);

  const handleUndo = (actionId: string) => {
    markUndoing(actionId);
    wsManager.send(WS_EVENTS.USER_REQUEST_UNDO, { action_id: actionId });
  };

  if (items.length === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col-reverse gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {items.map((item) => (
          <motion.div
            key={item.action_id}
            layout
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="pointer-events-auto"
          >
            <UndoToast item={item} onUndo={handleUndo} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
