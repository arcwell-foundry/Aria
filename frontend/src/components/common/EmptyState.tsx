/**
 * EmptyState - Centered placeholder for empty content areas
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Centered layout with icon, title, description, and action
 * - No emoji - uses Lucide icons
 *
 * @example
 * <EmptyState
 *   title="No leads found"
 *   description="ARIA will surface leads as intelligence is gathered"
 *   suggestion="Start a conversation"
 *   onSuggestion={() => navigate('/')}
 *   icon={<Search />}
 * />
 */

import { type ReactNode } from 'react';
import { Inbox } from 'lucide-react';

export interface EmptyStateProps {
  /** Title text */
  title: string;
  /** Description text */
  description?: string;
  /** Suggestion button text */
  suggestion?: string;
  /** Callback when suggestion button is clicked */
  onSuggestion?: () => void;
  /** Optional custom icon (defaults to Inbox) */
  icon?: ReactNode;
  /** Additional CSS classes */
  className?: string;
}

export function EmptyState({
  title,
  description,
  suggestion,
  onSuggestion,
  icon,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`
        flex flex-col items-center justify-center
        py-16 px-8 text-center
        ${className}
      `.trim()}
    >
      {/* Icon Circle */}
      <div
        className="
          w-16 h-16 rounded-full
          flex items-center justify-center
          mb-4
        "
        style={{
          backgroundColor: 'var(--bg-subtle)',
          color: 'var(--text-secondary)',
        }}
      >
        {icon || <Inbox className="w-8 h-8" />}
      </div>

      {/* Title */}
      <h3
        className="text-lg font-medium mb-2"
        style={{ color: 'var(--text-primary)' }}
      >
        {title}
      </h3>

      {/* Description */}
      {description && (
        <p
          className="text-sm mb-6 max-w-sm"
          style={{ color: 'var(--text-secondary)' }}
        >
          {description}
        </p>
      )}

      {/* Suggestion Button */}
      {suggestion && onSuggestion && (
        <button
          onClick={onSuggestion}
          className="px-4 py-2 rounded-lg font-sans text-sm font-medium transition-all duration-200 hover:opacity-90"
          style={{
            backgroundColor: 'var(--accent)',
            color: 'white',
          }}
        >
          {suggestion}
        </button>
      )}
    </div>
  );
}
