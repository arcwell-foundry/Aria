/**
 * Card - Container component following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Default: bg-elevated, border-border
 * - Elevated: shadow + elevated bg
 * - Outline: border only, transparent bg
 *
 * @example
 * <Card>Content here</Card>
 * <Card variant="elevated" padding="lg">
 *   <Card.Header>Title</Card.Header>
 *   <Card.Body>Content</Card.Body>
 * </Card>
 */

import { type ReactNode, forwardRef } from "react";

export interface CardProps {
  /** Card content */
  children?: ReactNode;
  /** Visual style variant */
  variant?: "default" | "elevated" | "outline";
  /** Padding size */
  padding?: "none" | "sm" | "md" | "lg";
  /** Additional CSS classes */
  className?: string;
  /** Click handler (makes card clickable) */
  onClick?: () => void;
}

export interface CardHeaderProps {
  /** Header content */
  children?: ReactNode;
  /** Show bottom border */
  bordered?: boolean;
  /** Additional CSS classes */
  className?: string;
}

export interface CardBodyProps {
  /** Body content */
  children?: ReactNode;
  /** Additional CSS classes */
  className?: string;
}

export interface CardFooterProps {
  /** Footer content */
  children?: ReactNode;
  /** Show top border */
  bordered?: boolean;
  /** Additional CSS classes */
  className?: string;
}

const variantStyles = {
  default: "bg-elevated border border-border",
  elevated: "bg-elevated border border-border shadow-lg shadow-black/10",
  outline: "bg-transparent border border-border",
};

const paddingStyles = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

const CardRoot = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      children,
      variant = "default",
      padding = "md",
      className = "",
      onClick,
    },
    ref
  ) => {
    return (
      <div
        ref={ref}
        onClick={onClick}
        className={`
          rounded-xl
          ${variantStyles[variant]}
          ${paddingStyles[padding]}
          ${onClick ? "cursor-pointer hover:bg-subtle transition-colors" : ""}
          ${className}
        `.trim()}
      >
        {children}
      </div>
    );
  }
);

CardRoot.displayName = "Card";

const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ children, bordered = false, className = "" }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          pb-4
          ${bordered ? "border-b border-border mb-4" : ""}
          ${className}
        `.trim()}
      >
        {children}
      </div>
    );
  }
);

CardHeader.displayName = "Card.Header";

const CardBody = forwardRef<HTMLDivElement, CardBodyProps>(
  ({ children, className = "" }, ref) => {
    return (
      <div ref={ref} className={className}>
        {children}
      </div>
    );
  }
);

CardBody.displayName = "Card.Body";

const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ children, bordered = false, className = "" }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          pt-4
          ${bordered ? "border-t border-border mt-4" : ""}
          ${className}
        `.trim()}
      >
        {children}
      </div>
    );
  }
);

CardFooter.displayName = "Card.Footer";

/** Card with compound components */
export const Card = Object.assign(CardRoot, {
  Header: CardHeader,
  Body: CardBody,
  Footer: CardFooter,
});
