/**
 * NotificationToast — Renders general notifications from useNotificationsStore.
 *
 * This component consumes notifications added by useDashboardEvents and
 * displays them as toasts. It fills a gap where notifications were being
 * added to the store but never rendered.
 */

import { useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Info,
  CheckCircle,
  AlertTriangle,
  XCircle,
  X,
  type LucideProps,
} from 'lucide-react';
import { useNotificationsStore, type Notification, type NotificationType } from '@/stores/notificationsStore';

/**
 * Icon mapping for notification types
 */
const ICON_MAP: Record<NotificationType, React.ComponentType<LucideProps>> = {
  info: Info,
  success: CheckCircle,
  warning: AlertTriangle,
  error: XCircle,
};

/**
 * Color mapping for notification types
 */
const COLOR_MAP: Record<NotificationType, { bg: string; border: string; icon: string }> = {
  info: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    icon: 'text-blue-400',
  },
  success: {
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    icon: 'text-green-400',
  },
  warning: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    icon: 'text-amber-400',
  },
  error: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    icon: 'text-red-400',
  },
};

interface NotificationItemProps {
  notification: Notification;
  onDismiss: (id: string) => void;
}

function NotificationItem({ notification, onDismiss }: NotificationItemProps) {
  const colors = COLOR_MAP[notification.type];
  const Icon = ICON_MAP[notification.type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 100, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={`pointer-events-auto w-80 rounded-lg border shadow-xl backdrop-blur-sm ${colors.bg} ${colors.border}`}
      style={{ backgroundColor: 'var(--bg-elevated, #1a1a2e)' }}
    >
      <div className="flex items-start gap-3 p-4">
        {/* Icon */}
        <div className={`flex-shrink-0 ${colors.icon}`}>
          <Icon size={18} strokeWidth={1.5} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p
            className="text-sm font-medium truncate"
            style={{ color: 'var(--text-primary, #e2e8f0)' }}
          >
            {notification.title}
          </p>
          {notification.message && (
            <p
              className="text-xs mt-1 leading-relaxed"
              style={{ color: 'var(--text-secondary, #94a3b8)' }}
            >
              {notification.message}
            </p>
          )}
        </div>

        {/* Dismiss button */}
        <button
          onClick={() => onDismiss(notification.id)}
          className="flex-shrink-0 rounded p-0.5 text-gray-500 transition-colors hover:text-gray-300 hover:bg-white/5"
          aria-label="Dismiss notification"
        >
          <X size={14} strokeWidth={1.5} />
        </button>
      </div>

      {/* Action button if present */}
      {notification.action && (
        <div className="px-4 pb-3">
          <button
            onClick={() => {
              notification.action!.onClick();
              onDismiss(notification.id);
            }}
            className="rounded-md bg-white/10 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-white/20"
          >
            {notification.action.label}
          </button>
        </div>
      )}
    </motion.div>
  );
}

/**
 * NotificationToastContainer — Renders all active notifications.
 *
 * Mount this component once at the app root (e.g., in AppShell).
 * It automatically subscribes to the notifications store and renders
 * toasts in the top-right corner.
 */
export function NotificationToastContainer() {
  const notifications = useNotificationsStore((s) => s.notifications);
  const removeNotification = useNotificationsStore((s) => s.removeNotification);

  const handleDismiss = useCallback((id: string) => {
    removeNotification(id);
  }, [removeNotification]);

  return (
    <div className="fixed top-20 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {notifications.map((notification) => (
          <NotificationItem
            key={notification.id}
            notification={notification}
            onDismiss={handleDismiss}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
