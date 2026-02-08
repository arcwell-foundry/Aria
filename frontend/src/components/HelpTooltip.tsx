import { HelpCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { useState } from 'react';

/**
 * HelpTooltip - Reusable help tooltip component
 *
 * Follows ARIA Design System v1.0:
 * - HelpCircle icon (16px, muted color)
 * - Tooltip with bg-white border-border
 * - Satoshi 15px text
 * - Absolute positioning based on placement prop
 * - Accessibility: aria-describedby, aria-label, role="tooltip"
 */

export interface HelpTooltipProps {
  /** Content to display in the tooltip (string or React node) */
  content: string | ReactNode;
  /** Placement of the tooltip relative to the icon */
  placement?: 'top' | 'bottom' | 'left' | 'right';
  /** Optional custom className for wrapper */
  className?: string;
}

export function HelpTooltip({
  content,
  placement = 'top',
  className = '',
}: HelpTooltipProps): ReactNode {
  const [isOpen, setIsOpen] = useState(false);

  const handleMouseEnter = () => {
    setIsOpen(true);
  };

  const handleMouseLeave = () => {
    setIsOpen(false);
  };

  const handleClick = () => {
    setIsOpen(!isOpen);
  };

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
      {/* Help Icon Button */}
      <button
        type="button"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        aria-describedby="help-tooltip-content"
        aria-label="Get help"
        className="inline-flex items-center justify-center text-interactive hover:text-secondary transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-white rounded-sm"
      >
        <HelpCircle size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>

      {/* Tooltip */}
      {isOpen && (
        <>
          {/* Tooltip Content */}
          <div
            id="help-tooltip-content"
            role="tooltip"
            className={`absolute z-50 w-64 bg-white border border-border rounded-lg shadow-lg p-3 ${positionClasses[placement]}`}
            style={{
              fontFamily: "'Satoshi', sans-serif",
              fontSize: '15px',
              lineHeight: '1.6',
            }}
          >
            <div className="text-content">
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
      )}
    </div>
  );
}
