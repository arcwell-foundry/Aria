/**
 * Error Event System
 *
 * Event-based error notification system that works outside React's render cycle.
 * This allows error notifications to be triggered from API interceptors and other
 * non-React contexts.
 *
 * @example
 * // In an API interceptor
 * import { showError } from '@/lib/errorEvents';
 * showError('network', 'Connection failed', 'Please check your internet');
 *
 * @example
 * // In a React component
 * import { ErrorToaster } from '@/components/ErrorToaster';
 * import { onError } from '@/lib/errorEvents';
 *
 * function App() {
 *   useEffect(() => {
 *     const unsubscribe = onError((error) => {
 *       console.log('Error received:', error);
 *     });
 *     return unsubscribe;
 *   }, []);
 *
 *   return <ErrorToaster />;
 * }
 */

/**
 * Error types for categorization
 */
export type ErrorType =
  | "auth" // Authentication/authorization errors
  | "network" // Network connectivity issues
  | "server" // Server errors (5xx)
  | "client" // Client errors (4xx, excluding auth)
  | "retry" // Retry in progress
  | "rate_limit" // Rate limiting (429)
  | "permission" // Permission denied (403)
  | "not_found" // Resource not found (404)
  | "validation"; // Validation errors

/**
 * Error event structure
 */
export interface ErrorEvent {
  /** Type/category of error */
  type: ErrorType;
  /** Short title for display */
  title: string;
  /** Detailed description */
  description: string;
  /** Timestamp when error occurred */
  timestamp: number;
  /** Unique identifier for this error event */
  id: string;
}

/**
 * Listener callback type
 */
type ErrorListener = (error: ErrorEvent) => void;

/**
 * Array of registered error listeners
 */
const listeners: ErrorListener[] = [];

/**
 * Subscribe to error events
 * @param callback - Function to call when an error occurs
 * @returns Unsubscribe function
 */
export function onError(callback: ErrorListener): () => void {
  listeners.push(callback);

  // Return unsubscribe function
  return () => {
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
    }
  };
}

/**
 * Show an error notification
 * Creates an error event and notifies all listeners
 *
 * @param type - Type of error
 * @param title - Short title
 * @param description - Detailed description
 */
export function showError(
  type: ErrorType,
  title: string,
  description: string
): void {
  const errorEvent: ErrorEvent = {
    type,
    title,
    description,
    timestamp: Date.now(),
    id: `error-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
  };

  // Notify all listeners
  listeners.forEach((listener) => {
    try {
      listener(errorEvent);
    } catch (err) {
      // Prevent listener errors from breaking the error system
      console.error("Error in error event listener:", err);
    }
  });
}

/**
 * Clear all error listeners
 * Useful for testing or cleanup
 */
export function clearAllErrorListeners(): void {
  listeners.length = 0;
}

/**
 * Get icon component name for error type
 * Maps error types to appropriate icons
 */
export function getIconForErrorType(type: ErrorType): string {
  switch (type) {
    case "auth":
      return "Lock";
    case "network":
      return "WifiOff";
    case "server":
      return "Server";
    case "retry":
      return "RefreshCw";
    case "rate_limit":
      return "Clock";
    case "permission":
      return "ShieldAlert";
    case "not_found":
      return "SearchX";
    case "validation":
      return "AlertCircle";
    default:
      return "AlertTriangle";
  }
}

/**
 * Get color class for error type
 * Maps error types to appropriate colors
 */
export function getColorForErrorType(type: ErrorType): {
  bg: string;
  border: string;
  icon: string;
} {
  switch (type) {
    case "auth":
      return {
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        icon: "text-amber-400",
      };
    case "network":
      return {
        bg: "bg-orange-500/10",
        border: "border-orange-500/20",
        icon: "text-orange-400",
      };
    case "retry":
      return {
        bg: "bg-blue-500/10",
        border: "border-blue-500/20",
        icon: "text-blue-400",
      };
    case "rate_limit":
      return {
        bg: "bg-purple-500/10",
        border: "border-purple-500/20",
        icon: "text-purple-400",
      };
    case "permission":
      return {
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        icon: "text-amber-400",
      };
    case "not_found":
      return {
        bg: "bg-slate-500/10",
        border: "border-slate-500/20",
        icon: "text-slate-400",
      };
    case "validation":
      return {
        bg: "bg-yellow-500/10",
        border: "border-yellow-500/20",
        icon: "text-yellow-400",
      };
    default:
      // server, client errors
      return {
        bg: "bg-red-500/10",
        border: "border-red-500/20",
        icon: "text-red-400",
      };
  }
}

/**
 * Get auto-dismiss duration for error type
 * Some errors (like auth) should persist longer
 */
export function getDismissDelay(type: ErrorType): number {
  switch (type) {
    case "retry":
      return 2000; // Retry toasts should dismiss quickly
    case "auth":
      return 6000; // Auth errors need more time to read
    default:
      return 4000; // Default 4 seconds
  }
}
