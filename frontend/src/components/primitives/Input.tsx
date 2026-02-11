/**
 * Input - Text input field following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Default: bg-elevated, border-border, text-content
 * - Focus: border-interactive
 * - Error: border-critical
 *
 * @example
 * <Input placeholder="Enter text..." />
 * <Input label="Email" type="email" error="Invalid email" />
 * <Input icon={<Search />} />
 */

import { type ReactNode, forwardRef, useId } from "react";
import { AlertCircle } from "lucide-react";

export interface InputProps {
  /** Input value */
  value?: string;
  /** Default value for uncontrolled input */
  defaultValue?: string;
  /** Placeholder text */
  placeholder?: string;
  /** Input type */
  type?: "text" | "email" | "password" | "search" | "number" | "tel" | "url";
  /** Label text */
  label?: string;
  /** Helper text below input */
  helperText?: string;
  /** Error message - shows error state */
  error?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Required field */
  required?: boolean;
  /** Icon to show on the left */
  icon?: ReactNode;
  /** Icon to show on the right */
  iconRight?: ReactNode;
  /** Full width input */
  fullWidth?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Change handler */
  onChange?: (value: string) => void;
  /** Blur handler */
  onBlur?: () => void;
  /** Focus handler */
  onFocus?: () => void;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      value,
      defaultValue,
      placeholder,
      type = "text",
      label,
      helperText,
      error,
      disabled = false,
      required = false,
      icon,
      iconRight,
      fullWidth = true,
      className = "",
      onChange,
      onBlur,
      onFocus,
    },
    ref
  ) => {
    const id = useId();
    const hasError = Boolean(error);

    return (
      <div className={`${fullWidth ? "w-full" : ""} ${className}`}>
        {label && (
          <label
            htmlFor={id}
            className="block text-sm font-medium text-content mb-1.5"
          >
            {label}
            {required && <span className="text-critical ml-1">*</span>}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary pointer-events-none">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            id={id}
            type={type}
            value={value}
            defaultValue={defaultValue}
            placeholder={placeholder}
            disabled={disabled}
            required={required}
            onChange={(e) => onChange?.(e.target.value)}
            onBlur={onBlur}
            onFocus={onFocus}
            className={`
              w-full px-4 py-2.5 text-sm rounded-lg
              bg-elevated text-content placeholder:text-secondary
              border transition-colors
              ${icon ? "pl-10" : ""}
              ${iconRight ? "pr-10" : ""}
              ${hasError
                ? "border-critical focus:border-critical focus:ring-1 focus:ring-critical"
                : "border-border focus:border-interactive focus:ring-1 focus:ring-interactive"
              }
              ${disabled ? "opacity-50 cursor-not-allowed" : ""}
            `}
          />
          {iconRight && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-secondary">
              {iconRight}
            </div>
          )}
          {hasError && !iconRight && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-critical">
              <AlertCircle className="w-4 h-4" />
            </div>
          )}
        </div>
        {(helperText || error) && (
          <p
            className={`mt-1.5 text-xs ${hasError ? "text-critical" : "text-secondary"}`}
          >
            {error || helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
