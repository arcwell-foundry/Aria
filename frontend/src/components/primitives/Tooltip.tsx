/**
 * Tooltip - Contextual information following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Background: bg-elevated (with shadow)
 * - Text: text-content
 * - Border: border-border
 *
 * @example
 * <Tooltip content="Helpful information">
 *   <Button>Hover me</Button>
 * </Tooltip>
 */

import { type ReactNode, useState, useRef, useEffect } from "react";

export interface TooltipProps {
  /** Tooltip content */
  content: ReactNode;
  /** Element that triggers the tooltip */
  children: ReactNode;
  /** Position relative to trigger */
  position?: "top" | "bottom" | "left" | "right";
  /** Delay before showing (ms) */
  delay?: number;
  /** Show arrow pointer */
  arrow?: boolean;
  /** Additional CSS classes for tooltip */
  className?: string;
}

const positionStyles = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

const arrowStyles = {
  top: "top-full left-1/2 -translate-x-1/2 border-t-border border-x-transparent border-b-transparent",
  bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-border border-x-transparent border-t-transparent",
  left: "left-full top-1/2 -translate-y-1/2 border-l-border border-y-transparent border-r-transparent",
  right: "right-full top-1/2 -translate-y-1/2 border-r-border border-y-transparent border-l-transparent",
};

export function Tooltip({
  content,
  children,
  position = "top",
  delay = 200,
  arrow = true,
  className = "",
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  };

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsVisible(false);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative inline-flex"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {isVisible && (
        <div
          className={`
            absolute z-50 px-3 py-2
            bg-elevated text-content text-sm rounded-lg
            border border-border shadow-lg shadow-black/20
            whitespace-nowrap
            animate-in fade-in duration-150
            ${positionStyles[position]}
            ${className}
          `.trim()}
          role="tooltip"
        >
          {content}
          {arrow && (
            <div
              className={`
                absolute w-0 h-0
                border-4
                ${arrowStyles[position]}
              `.trim()}
            />
          )}
        </div>
      )}
    </div>
  );
}
