import { useState, useEffect, useCallback } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useIntegrations } from "@/hooks/useIntegrations";
import { wsManager } from "@/core/WebSocketManager";
import { WS_EVENTS } from "@/types/chat";

interface IntegrationReconnectBannerProps {
  isAuthenticated: boolean;
}

interface SignalPayload {
  signal_type?: string;
  data?: {
    integration_type?: string;
  };
}

/**
 * IntegrationReconnectBanner - Surfaces auth failures for email integrations
 *
 * Monitors two sources:
 * 1. Polling: useIntegrations() query data for sync_status === 'failed'
 * 2. Real-time: WebSocket signal.detected events with signal_type === 'integration_auth_failed'
 *
 * Follows ARIA Design System v1.0:
 * - Fixed top position, z-30 (below ServiceHealthBanner z-40, OfflineBanner z-50)
 * - Amber color scheme for warnings
 * - Dismissible with X, auto-reappears on new failure events
 */
export function IntegrationReconnectBanner({
  isAuthenticated,
}: IntegrationReconnectBannerProps) {
  const navigate = useNavigate();
  const { data: integrations } = useIntegrations();
  const [isDismissed, setIsDismissed] = useState(false);
  const [wsFailedType, setWsFailedType] = useState<string | null>(null);

  // Listen for real-time auth failure signals via WebSocket
  const handleSignal = useCallback((payload: unknown) => {
    const p = payload as SignalPayload;
    if (p?.signal_type === "integration_auth_failed") {
      const intType = p.data?.integration_type || "email";
      setWsFailedType(intType);
      setIsDismissed(false); // Force re-show on new failure
    }
  }, []);

  useEffect(() => {
    wsManager.on(WS_EVENTS.SIGNAL_DETECTED, handleSignal);
    return () => {
      wsManager.off(WS_EVENTS.SIGNAL_DETECTED, handleSignal);
    };
  }, [handleSignal]);

  // Find failed integrations from polling data
  const failedIntegration = integrations?.find(
    (i) => i.sync_status === "failed" && i.status === "active"
  );

  const failedType =
    wsFailedType || failedIntegration?.integration_type || null;

  // Don't render when not authenticated, no failure, or dismissed
  if (!isAuthenticated || !failedType || isDismissed) {
    return null;
  }

  const displayName =
    failedType === "outlook"
      ? "Outlook"
      : failedType === "gmail"
        ? "Gmail"
        : failedType.charAt(0).toUpperCase() + failedType.slice(1);

  return (
    <div
      className="fixed top-0 left-0 right-0 z-30 bg-[var(--warning)]/10 border-b border-[var(--warning)]/20 px-4 py-2.5"
      role="status"
      aria-live="polite"
      data-aria-id="integration-reconnect-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <AlertTriangle
            className="w-4 h-4 text-[var(--warning)] flex-shrink-0"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <p className="text-[13px] font-sans text-[var(--text-primary)]">
            Your {displayName} connection needs attention.{" "}
            <button
              onClick={() => navigate("/settings/integrations")}
              className="underline underline-offset-2 hover:text-[var(--warning)] transition-colors cursor-pointer"
            >
              Reconnect
            </button>
          </p>
        </div>

        <button
          onClick={() => setIsDismissed(true)}
          className="flex-shrink-0 p-1 rounded-md text-[var(--text-secondary)] hover:bg-[var(--warning)]/20 transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--warning)]"
          aria-label="Dismiss integration reconnect notification"
        >
          <X className="w-3.5 h-3.5" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
