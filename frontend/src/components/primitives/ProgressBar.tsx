/**
 * ProgressBar - Progress indicator following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Default: bg-interactive
 * - Success: bg-success
 * - Warning: bg-warning
 * - Error: bg-critical
 *
 * @example
 * <ProgressBar value={75} />
 * <ProgressBar value={30} variant="warning" label="Storage used" />
 */

import { type ReactNode } from "react";

export interface ProgressBarProps {
  /** Current progress value (0-100) */
  value: number;
  /** Visual style variant */
  variant?: "default" | "success" | "warning" | "error" | "info";
  /** Size of the progress bar */
  size?: "sm" | "md" | "lg";
  /** Label text */
  label?: string;
  /** Show percentage text */
  showValue?: boolean;
  /** Animate the progress fill */
  animated?: boolean;
  /** Custom value formatter */
  formatValue?: (value: number) => string;
  /** Additional CSS classes */
  className?: string;
}

const variantStyles = {
  default: "bg-interactive",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-critical",
  info: "bg-info",
};

const bgVariantStyles = {
  default: "bg-interactive/10",
  success: "bg-success/10",
  warning: "bg-warning/10",
  error: "bg-critical/10",
  info: "bg-info/10",
};

const sizeStyles = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-4",
};

export function ProgressBar({
  value,
  variant = "default",
  size = "md",
  label,
  showValue = false,
  animated = false,
  formatValue = (v) => `${Math.round(v)}%`,
  className = "",
}: ProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value));

  return (
    <div className={`${className}`}>
      {(label || showValue) && (
        <div className="flex items-center justify-between mb-1.5">
          {label && (
            <span className="text-sm text-secondary">{label}</span>
          )}
          {showValue && (
            <span className="text-sm font-medium text-content">
              {formatValue(clampedValue)}
            </span>
          )}
        </div>
      )}
      <div
        className={`
          w-full rounded-full overflow-hidden
          ${sizeStyles[size]}
          ${bgVariantStyles[variant]}
        `.trim()}
        role="progressbar"
        aria-valuenow={clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`
            h-full rounded-full transition-all duration-300 ease-out
            ${variantStyles[variant]}
            ${animated ? "animate-pulse" : ""}
          `.trim()}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
    </div>
  );
}
