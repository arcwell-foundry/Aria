import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';

/**
 * OnboardingTooltip - Tooltip for onboarding guidance and tips
 *
 * Follows ARIA Design System v1.0:
 * - White bg, border-border, rounded-lg, shadow-sm
 * - X dismiss button (Lucide X icon)
 * - Arrow element pointing to parent
 * - Placement classes for top/bottom/left/right
 * - State tracked in React (NOT localStorage per design system restrictions)
 *
 * US-933 Content & Help System - Task 11
 */

export interface OnboardingTooltipProps {
  /** Child element that the tooltip positions relative to */
  children: ReactNode;
  /** Title text for the tooltip header */
  title: string;
  /** Main content to display in the tooltip body */
  content: string | ReactNode;
  /** Placement of the tooltip relative to children */
  placement?: 'top' | 'bottom' | 'left' | 'right';
  /** Optional custom className for wrapper */
  className?: string;
  /** Whether the tooltip starts in dismissed state */
  initiallyDismissed?: boolean;
  /** Callback when tooltip is dismissed */
  onDismiss?: () => void;
}

export function OnboardingTooltip({
  children,
  title,
  content,
  placement = 'top',
  className = '',
  initiallyDismissed = false,
  onDismiss,
}: OnboardingTooltipProps): ReactNode {
  const [isDismissed, setIsDismissed] = useState(initiallyDismissed);

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  // Return null if dismissed - nothing to render
  if (isDismissed) {
    return <>{children}</>;
  }

  // Position classes based on placement
  const positionClasses: Record<string, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  // Arrow position classes
  const arrowClasses: Record<string, string> = {
    top: 'top-full left-1/2 -translate-x-1/2 border-t-white border-t-8 border-x-transparent border-x-8 border-b-0',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-white border-b-8 border-x-transparent border-x-8 border-t-0',
    left: 'left-full top-1/2 -translate-y-1/2 border-l-white border-l-8 border-y-transparent border-y-8 border-r-0',
    right: 'right-full top-1/2 -translate-y-1/2 border-r-white border-r-8 border-y-transparent border-y-8 border-l-0',
  };

  return (
    <div className={`relative inline-flex ${className}`}>
      {children}

      {/* Tooltip */}
      <>
        {/* Tooltip Content Card */}
        <div
          role="dialog"
          aria-labelledby="onboarding-tooltip-title"
          aria-describedby="onboarding-tooltip-content"
          className={`absolute z-50 w-72 bg-white border border-border rounded-lg shadow-sm ${positionClasses[placement]}`}
          style={{
            fontFamily: "'Satoshi', sans-serif",
            fontSize: '15px',
            lineHeight: '1.6',
          }}
        >
          {/* Header with title and dismiss button */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h3
              id="onboarding-tooltip-title"
              className="text-content font-semibold text-sm m-0"
            >
              {title}
            </h3>
            <button
              type="button"
              onClick={handleDismiss}
              aria-label="Dismiss tooltip"
              className="inline-flex items-center justify-center text-interactive hover:text-content transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-white rounded-sm p-0.5"
            >
              <X size={16} strokeWidth={1.5} aria-hidden="true" />
            </button>
          </div>

          {/* Content Body */}
          <div
            id="onboarding-tooltip-content"
            className="px-4 py-3 text-content"
          >
            {typeof content === 'string' ? (
              <p className="m-0">{content}</p>
            ) : (
              content
            )}
          </div>
        </div>

        {/* Arrow */}
        <div
          className={`absolute z-50 w-0 h-0 ${arrowClasses[placement]}`}
          aria-hidden="true"
        />
      </>
    </div>
  );
}
