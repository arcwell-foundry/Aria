import { useState, useEffect } from "react";
import { X, WifiOff } from "lucide-react";

/**
 * OfflineBanner - Network status indicator
 *
 * Monitors navigator.onLine status and displays an amber banner when offline.
 * Automatically dismisses when connection is restored.
 *
 * Follows ARIA Design System v1.0:
 * - Fixed position at top (z-50)
 * - Amber color scheme for warnings: bg-amber-500/10, border-amber-500/20
 * - Lucide icons (WifiOff, X)
 * - Accessible with ARIA labels and keyboard navigation
 */
export function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    // Check initial online status
    const updateOnlineStatus = () => setIsOffline(!navigator.onLine);
    updateOnlineStatus();

    const handleOnline = () => {
      setIsOffline(false);
      setIsDismissed(false); // Reset dismissed state when coming back online
    };

    const handleOffline = () => {
      setIsOffline(true);
      setIsDismissed(false);
    };

    // Register event listeners for online/offline changes
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Cleanup event listeners on unmount
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // Don't render if online or dismissed
  if (!isOffline || isDismissed) {
    return null;
  }

  const handleDismiss = () => {
    setIsDismissed(true);
  };

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 bg-amber-500/10 border-b border-amber-500/20 px-4 py-3"
      role="status"
      aria-live="polite"
      aria-label="You are currently offline"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Icon and message */}
        <div className="flex items-center gap-3">
          <WifiOff
            className="w-5 h-5 text-amber-600 dark:text-amber-500 flex-shrink-0"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <p className="text-[15px] font-sans text-amber-900 dark:text-amber-100">
            You are currently offline. Some features may be limited.
          </p>
        </div>

        {/* Dismiss button */}
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 p-1 rounded-md text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-500"
          aria-label="Dismiss offline notification"
        >
          <X className="w-4 h-4" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
