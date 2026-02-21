import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { ServiceHealthState } from "@/hooks/useServiceHealth";
import { formatDegradedServices } from "@/hooks/useServiceHealth";

interface ServiceHealthBannerProps {
  health: ServiceHealthState;
}

/**
 * Subtle top-banner shown when backend services are degraded.
 *
 * Follows ARIA Design System v1.0:
 * - Amber color scheme for warnings
 * - Satoshi font for body text
 * - Dismissible with X button
 * - Fixed top position, z-40 (below OfflineBanner at z-50)
 */
export function ServiceHealthBanner({ health }: ServiceHealthBannerProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  // Don't render while loading, when healthy, or when dismissed
  if (health.isLoading || health.isHealthy || isDismissed) {
    return null;
  }

  const serviceNames = formatDegradedServices(health.degradedServices);

  return (
    <div
      className="fixed top-0 left-0 right-0 z-40 bg-[var(--warning)]/10 border-b border-[var(--warning)]/20 px-4 py-2.5"
      role="status"
      aria-live="polite"
      data-aria-id="service-health-banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <AlertTriangle
            className="w-4 h-4 text-[var(--warning)] flex-shrink-0"
            strokeWidth={1.5}
            aria-hidden="true"
          />
          <p className="text-[13px] font-sans text-[var(--text-primary)]">
            ARIA is experiencing some delays with {serviceNames}. Core features still available.
          </p>
        </div>

        <button
          onClick={() => setIsDismissed(true)}
          className="flex-shrink-0 p-1 rounded-md text-[var(--text-secondary)] hover:bg-[var(--warning)]/20 transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--warning)]"
          aria-label="Dismiss service health notification"
        >
          <X className="w-3.5 h-3.5" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
