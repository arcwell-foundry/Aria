/**
 * Button - Primary interactive element following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Primary: bg-interactive, hover:bg-interactive-hover
 * - Secondary: bg-elevated, border-border
 * - Ghost: transparent
 * - Danger: bg-critical
 *
 * @example
 * <Button variant="primary" size="md">Click me</Button>
 * <Button variant="ghost" icon={<Plus />}>Add Item</Button>
 * <Button loading>Processing...</Button>
 */

import { type ReactNode, forwardRef } from "react";
import { Loader2 } from "lucide-react";

export interface ButtonProps {
  /** Button content */
  children?: ReactNode;
  /** Visual style variant */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  /** Size of the button */
  size?: "sm" | "md" | "lg";
  /** Loading state - shows spinner and disables */
  loading?: boolean;
  /** Disabled state */
  disabled?: boolean;
  /** Icon to show on the left */
  icon?: ReactNode;
  /** Icon to show on the right */
  iconRight?: ReactNode;
  /** Full width button */
  fullWidth?: boolean;
  /** HTML button type */
  type?: "button" | "submit" | "reset";
  /** Additional CSS classes */
  className?: string;
  /** Click handler */
  onClick?: () => void;
}

const variantStyles = {
  primary:
    "bg-interactive text-white hover:bg-interactive-hover shadow-sm transition-colors",
  secondary:
    "bg-elevated text-content border border-border hover:bg-subtle transition-colors",
  ghost:
    "bg-transparent text-interactive hover:bg-subtle hover:text-content transition-colors",
  danger:
    "bg-critical text-white hover:opacity-90 shadow-sm transition-opacity",
};

const sizeStyles = {
  sm: "px-3 py-1.5 text-sm gap-1.5 rounded-lg",
  md: "px-4 py-2 text-sm gap-2 rounded-lg",
  lg: "px-6 py-3 text-base gap-2 rounded-xl",
};

const iconSizes = {
  sm: "w-4 h-4",
  md: "w-4 h-4",
  lg: "w-5 h-5",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = "primary",
      size = "md",
      loading = false,
      disabled = false,
      icon,
      iconRight,
      fullWidth = false,
      type = "button",
      className = "",
      onClick,
    },
    ref
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        onClick={onClick}
        className={`
          inline-flex items-center justify-center font-medium
          ${variantStyles[variant]}
          ${sizeStyles[size]}
          ${fullWidth ? "w-full" : ""}
          ${isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
          ${className}
        `.trim()}
      >
        {loading ? (
          <Loader2 className={`${iconSizes[size]} animate-spin`} />
        ) : (
          icon && <span className={iconSizes[size]}>{icon}</span>
        )}
        {children}
        {iconRight && !loading && (
          <span className={iconSizes[size]}>{iconRight}</span>
        )}
      </button>
    );
  }
);

Button.displayName = "Button";
