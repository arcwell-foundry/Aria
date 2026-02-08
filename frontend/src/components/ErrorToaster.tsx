import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Lock,
  WifiOff,
  Server,
  RefreshCw,
  Clock,
  ShieldAlert,
  SearchX,
  AlertCircle,
  X,
} from "lucide-react";
import type { ErrorEvent, ErrorType } from "@/lib/errorEvents";
import { onError, getColorForErrorType, getDismissDelay } from "@/lib/errorEvents";

/**
 * Icon mapping for error types
 */
const ICON_MAP: Record<ErrorType, React.ComponentType<{ className?: string; size?: number; strokeWidth?: number }>> = {
  auth: Lock,
  network: WifiOff,
  server: Server,
  client: AlertTriangle,
  retry: RefreshCw,
  rate_limit: Clock,
  permission: ShieldAlert,
  not_found: SearchX,
  validation: AlertCircle,
};

/**
 * Toast position settings
 */
const TOAST_POSITION = {
  bottom: 24,
  right: 24,
};

/**
 * Max number of toasts to show at once
 */
const MAX_TOASTS = 3;

/**
 * Individual toast component
 */
interface ToastProps {
  error: ErrorEvent;
  onDismiss: () => void;
}

function Toast({ error, onDismiss }: ToastProps) {
  const colors = getColorForErrorType(error.type);
  const Icon = ICON_MAP[error.type];
  const dismissDelay = getDismissDelay(error.type);

  useEffect(() => {
    // Auto-dismiss after delay
    const timer = setTimeout(onDismiss, dismissDelay);
    return () => clearTimeout(timer);
  }, [dismissDelay, onDismiss]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 50, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ type: "spring", damping: 25, stiffness: 300 }}
      className={`
        relative overflow-hidden rounded-xl border shadow-lg
        ${colors.bg} ${colors.border}
        backdrop-blur-sm
      `}
      style={{
        minWidth: "320px",
        maxWidth: "420px",
      }}
    >
      {/* Progress bar for auto-dismiss */}
      <motion.div
        className={`absolute bottom-0 left-0 h-0.5 ${colors.icon.replace("text-", "bg-").replace("-400", "-500")}`}
        initial={{ width: "100%" }}
        animate={{ width: "0%" }}
        transition={{ duration: dismissDelay / 1000, ease: "linear" }}
      />

      <div className="flex items-start gap-3 p-4">
        {/* Icon */}
        <div
          className={`
            flex-shrink-0 flex items-center justify-center
            w-8 h-8 rounded-lg
            ${colors.icon}
          `}
        >
          <Icon size={18} strokeWidth={1.5} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-content mb-0.5">
            {error.title}
          </h4>
          <p className="text-xs text-secondary leading-relaxed">
            {error.description}
          </p>
        </div>

        {/* Dismiss button */}
        <button
          onClick={onDismiss}
          className="
            flex-shrink-0 flex items-center justify-center
            w-6 h-6 rounded-lg
            text-secondary hover:text-content
            hover:bg-white/5
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-primary
          "
          aria-label="Dismiss"
        >
          <X size={14} strokeWidth={1.5} />
        </button>
      </div>
    </motion.div>
  );
}

/**
 * ErrorToaster Component
 *
 * Displays error notifications from the error event system.
 * Should be mounted once at the root of the app.
 *
 * @example
 * import { ErrorToaster } from '@/components/ErrorToaster';
 *
 * function App() {
 *   return (
 *     <>
 *       <YourRoutes />
 *       <ErrorToaster />
 *     </>
 *   );
 * }
 */
export function ErrorToaster() {
  const [toasts, setToasts] = useState<ErrorEvent[]>([]);

  useEffect(() => {
    // Subscribe to error events
    const unsubscribe = onError((error) => {
      setToasts((current) => {
        // Add new toast, remove oldest if we exceed max
        const updated = [...current, error];
        if (updated.length > MAX_TOASTS) {
          return updated.slice(-MAX_TOASTS);
        }
        return updated;
      });
    });

    return unsubscribe;
  }, []);

  const handleDismiss = (id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  };

  return (
    <div
      className="fixed z-50 flex flex-col gap-2"
      style={{
        bottom: TOAST_POSITION.bottom,
        right: TOAST_POSITION.right,
      }}
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <Toast key={toast.id} error={toast} onDismiss={() => handleDismiss(toast.id)} />
        ))}
      </AnimatePresence>
    </div>
  );
}
