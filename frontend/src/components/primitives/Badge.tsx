/**
 * Badge - Status indicator following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Default: bg-subtle, text-secondary
 * - Success: bg-success/20, text-success
 * - Warning: bg-warning/20, text-warning
 * - Error: bg-critical/20, text-critical
 * - Info: bg-info/20, text-info
 *
 * @example
 * <Badge>Default</Badge>
 * <Badge variant="success">Active</Badge>
 * <Badge variant="warning" dot>Attention</Badge>
 */

import { type ReactNode } from "react";

export interface BadgeProps {
  /** Badge content */
  children?: ReactNode;
  /** Visual style variant */
  variant?: "default" | "success" | "warning" | "error" | "info" | "primary";
  /** Size of the badge */
  size?: "sm" | "md" | "lg";
  /** Show indicator dot */
  dot?: boolean;
  /** Animate the dot */
  pulse?: boolean;
  /** Additional CSS classes */
  className?: string;
}

const variantStyles = {
  default: "bg-subtle text-secondary border-border",
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  error: "bg-critical/10 text-critical border-critical/20",
  info: "bg-info/10 text-info border-info/20",
  primary: "bg-interactive/10 text-interactive border-interactive/20",
};

const dotVariantStyles = {
  default: "bg-secondary",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-critical",
  info: "bg-info",
  primary: "bg-interactive",
};

const sizeStyles = {
  sm: "px-2 py-0.5 text-xs gap-1",
  md: "px-2.5 py-1 text-xs gap-1.5",
  lg: "px-3 py-1.5 text-sm gap-2",
};

const dotSizeStyles = {
  sm: "w-1.5 h-1.5",
  md: "w-2 h-2",
  lg: "w-2.5 h-2.5",
};

export function Badge({
  children,
  variant = "default",
  size = "md",
  dot = false,
  pulse = false,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center rounded-full border font-medium
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `.trim()}
    >
      {dot && (
        <span
          className={`
            rounded-full
            ${dotVariantStyles[variant]}
            ${dotSizeStyles[size]}
            ${pulse ? "animate-pulse" : ""}
          `.trim()}
        />
      )}
      {children}
    </span>
  );
}
